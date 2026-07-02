from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
from urllib.request import Request

from bookbuddarr.audiobook_search import candidates_from_prowlarr, classify_candidate_completeness, parse_torznab_rss, read_search_queue
from bookbuddarr.bookbuddy import dedupe_records, read_bookbuddy_export
from bookbuddarr.cli import main
from bookbuddarr.config import redact_endpoint, redact_structure
from bookbuddarr.rules import audiobook_rule
from bookbuddarr.stack import StackSettings
from bookbuddarr.torznab import AudioBookBayClient, _redact_log_message, parse_size_bytes, render_caps, render_rss
from bookbuddarr.web import APP_HTML, _safe_settings
from bookbuddarr.workflow import WorkflowPaths, run_monitored_workflow


FIXTURE_DIR = Path(__file__).parent / "fixtures"
SERVICE_SCRIPT = Path(__file__).parents[1] / "deploy" / "service" / "prowlarr_generic_torznab.py"

HEADERS = [
    "Title",
    "Original Title",
    "Subtitle",
    "Series",
    "Volume",
    "Author",
    "Publisher",
    "Year Published",
    "Language",
    "ISBN",
    "Status",
    "Date Added",
    "Position",
    "Google VolumeID",
]


def write_export(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def test_read_and_dedupe_by_isbn(tmp_path: Path) -> None:
    export = tmp_path / "bookbuddy.csv"
    write_export(
        export,
        [
            {
                "Title": "Dune",
                "Author": "Frank Herbert",
                "Language": "français",
                "ISBN": "978-0-441-17271-9",
            },
            {
                "Title": "Dune",
                "Author": "Frank Herbert",
                "Language": "français",
                "ISBN": "9780441172719",
            },
        ],
    )

    records = read_bookbuddy_export(export)
    unique, duplicates = dedupe_records(records)

    assert len(unique) == 1
    assert len(duplicates) == 1
    assert unique[0].record_id == "isbn:9780441172719"
    assert unique[0].language_code == "fr"


def test_ingest_registry_is_incremental(tmp_path: Path) -> None:
    export1 = tmp_path / "export1.csv"
    export2 = tmp_path / "export2.csv"
    registry = tmp_path / "registry.csv"
    new_csv = tmp_path / "new.csv"
    readarr_csv = tmp_path / "readarr.csv"
    audio_csv = tmp_path / "audio.csv"

    write_export(
        export1,
        [
            {"Title": "Dune", "Author": "Frank Herbert", "Language": "français", "ISBN": "9780441172719"},
        ],
    )
    write_export(
        export2,
        [
            {"Title": "Dune", "Author": "Frank Herbert", "Language": "français", "ISBN": "9780441172719"},
            {"Title": "Foundation", "Author": "Isaac Asimov", "Language": "anglais", "ISBN": "9780553293357"},
        ],
    )

    assert main(["ingest", str(export1), "--registry", str(registry), "--new-csv", str(new_csv), "--readarr-csv", str(readarr_csv), "--audiobook-csv", str(audio_csv)]) == 0
    assert main(["ingest", str(export2), "--registry", str(registry), "--new-csv", str(new_csv), "--readarr-csv", str(readarr_csv), "--audiobook-csv", str(audio_csv)]) == 0

    with new_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["title"] == "Foundation"
    assert rows[0]["language_code"] == "en"

    with readarr_csv.open(encoding="utf-8", newline="") as handle:
        readarr_rows = list(csv.DictReader(handle))

    assert len(readarr_rows) == 1
    assert readarr_rows[0]["metadata_profile"] == "Standard"
    assert readarr_rows[0]["root_folder_hint"] == "/Data/Ebooks/English"


def test_plan_reports_first_run_counts_without_writing_registry(tmp_path: Path, capsys) -> None:
    export = FIXTURE_DIR / "bookbuddy_good.csv"
    registry = tmp_path / "registry.csv"

    assert main(["plan", str(export), "--registry", str(registry)]) == 0
    summary = json.loads(capsys.readouterr().out)

    assert summary["input_rows"] == 2
    assert summary["unique_rows"] == 2
    assert summary["known_records_before"] == 0
    assert summary["known_records_in_export"] == 0
    assert summary["new_records"] == 2
    assert summary["language_split"] == {"en": 1, "fr": 1}
    assert summary["registry_updated"] is False
    assert not registry.exists()


def test_plan_reports_known_and_new_counts_on_later_run(tmp_path: Path, capsys) -> None:
    export1 = tmp_path / "export1.csv"
    export2 = tmp_path / "export2.csv"
    registry = tmp_path / "registry.csv"
    new_csv = tmp_path / "new.csv"
    readarr_csv = tmp_path / "readarr.csv"
    audio_csv = tmp_path / "audio.csv"
    write_export(
        export1,
        [
            {"Title": "Dune", "Author": "Frank Herbert", "Language": "francais", "ISBN": "9780441172719"},
        ],
    )
    write_export(
        export2,
        [
            {"Title": "Dune", "Author": "Frank Herbert", "Language": "francais", "ISBN": "9780441172719"},
            {"Title": "Foundation", "Author": "Isaac Asimov", "Language": "anglais", "ISBN": "9780553293357"},
        ],
    )

    assert main(["ingest", str(export1), "--registry", str(registry), "--new-csv", str(new_csv), "--readarr-csv", str(readarr_csv), "--audiobook-csv", str(audio_csv)]) == 0
    capsys.readouterr()
    assert main(["plan", str(export2), "--registry", str(registry)]) == 0
    summary = json.loads(capsys.readouterr().out)

    assert summary["known_records_before"] == 1
    assert summary["known_records_in_export"] == 1
    assert summary["new_records"] == 1
    assert summary["registry_updated"] is False


def test_missing_required_columns_return_clear_error(capsys) -> None:
    export = FIXTURE_DIR / "bookbuddy_missing_required.csv"

    assert main(["plan", str(export)]) == 1
    captured = capsys.readouterr()

    assert "missing required column(s): Author" in captured.err
    assert "Present columns:" in captured.err


def test_doctor_reports_good_csv_and_does_not_print_secret_values(tmp_path: Path, capsys, monkeypatch) -> None:
    export = FIXTURE_DIR / "bookbuddy_good.csv"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "READARR_URL=http://user:pass@127.0.0.1:8787/path?apikey=super-secret-url-key\n"
        "READARR_API_KEY=super-secret-test-key\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("READARR_URL", raising=False)
    monkeypatch.delenv("READARR_API_KEY", raising=False)

    assert main(["--env-file", str(env_file), "doctor", str(export), "--registry", str(tmp_path / "registry.csv")]) == 0
    output = capsys.readouterr().out
    summary = json.loads(output)

    assert summary["ok"] is True
    assert summary["checks"]["export_csv"]["rows"] == 2
    assert summary["checks"]["registry"]["first_run"] is True
    assert summary["checks"]["optional_endpoints"]["READARR_URL"]["configured"] is True
    assert summary["checks"]["optional_endpoints"]["READARR_URL"]["value"] == "http://127.0.0.1:8787/path"
    assert "super-secret-test-key" not in output
    assert "super-secret-url-key" not in output
    assert "user:pass" not in output


def test_doctor_reports_missing_required_columns(capsys) -> None:
    export = FIXTURE_DIR / "bookbuddy_missing_required.csv"

    assert main(["doctor", str(export)]) == 1
    summary = json.loads(capsys.readouterr().out)

    assert summary["ok"] is False
    assert "missing required column(s): Author" in summary["checks"]["export_csv"]["error"]


def test_french_readarr_queue_uses_french_profile_and_root(tmp_path: Path) -> None:
    export = tmp_path / "export.csv"
    registry = tmp_path / "registry.csv"
    new_csv = tmp_path / "new.csv"
    readarr_csv = tmp_path / "readarr.csv"
    audio_csv = tmp_path / "audio.csv"
    write_export(
        export,
        [
            {"Title": "Dune", "Author": "Frank Herbert", "Language": "français", "ISBN": "9780441172719"},
        ],
    )

    assert main(["ingest", str(export), "--registry", str(registry), "--new-csv", str(new_csv), "--readarr-csv", str(readarr_csv), "--audiobook-csv", str(audio_csv)]) == 0

    with readarr_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["language_code"] == "fr"
    assert rows[0]["metadata_profile"] == "French Preferred"
    assert rows[0]["root_folder_hint"] == "/Data/Ebooks/Francais"


def test_audiobook_rules_preserve_language_intent(tmp_path: Path) -> None:
    export = tmp_path / "export.csv"
    write_export(
        export,
        [
            {"Title": "Dune", "Author": "Frank Herbert", "Language": "français", "ISBN": "9780441172719"},
            {"Title": "Foundation", "Author": "Isaac Asimov", "Language": "anglais", "ISBN": "9780553293357"},
        ],
    )
    records = read_bookbuddy_export(export)

    french = audiobook_rule(records[0])
    english = audiobook_rule(records[1])

    assert french.wanted_language == "French"
    assert french.root_folder_hint == "/Data/Audiobooks/Francais"
    assert "French audiobook" in french.query
    assert english.wanted_language == "English"
    assert english.root_folder_hint == "/Data/Audiobooks/English"


def test_audiobook_search_queue_includes_record_id(tmp_path: Path) -> None:
    export = tmp_path / "export.csv"
    registry = tmp_path / "registry.csv"
    new_csv = tmp_path / "new.csv"
    readarr_csv = tmp_path / "readarr.csv"
    audio_csv = tmp_path / "audio.csv"
    write_export(
        export,
        [
            {"Title": "Dune", "Author": "Frank Herbert", "Language": "francais", "ISBN": "9780441172719"},
        ],
    )

    assert main(["ingest", str(export), "--registry", str(registry), "--new-csv", str(new_csv), "--readarr-csv", str(readarr_csv), "--audiobook-csv", str(audio_csv)]) == 0

    with audio_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["record_id"] == "isbn:9780441172719"


def test_parse_torznab_rss_uses_detail_url_not_grab_link() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
      <channel>
        <item>
          <title>Dune - Frank Herbert VF</title>
          <guid>https://audiobook.example/dune-fr</guid>
          <link>http://127.0.0.1:8765/api?t=get&amp;id=secret</link>
          <comments>https://audiobook.example/dune-fr</comments>
          <torznab:attr name="language" value="French" />
        </item>
      </channel>
    </rss>
    """

    candidates = parse_torznab_rss(xml)

    assert len(candidates) == 1
    assert candidates[0].url == "https://audiobook.example/dune-fr"
    assert "t=get" not in candidates[0].url


def test_prowlarr_candidates_keep_grab_metadata(tmp_path: Path) -> None:
    queue = tmp_path / "audiobook_search_queue.csv"
    with queue.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "record_id",
                "title",
                "author",
                "isbn",
                "language_code",
                "wanted_language",
                "language_policy",
                "query",
                "alternate_query",
                "root_folder_hint",
                "audiobookbay_search_url",
                "manual_review_required",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "record_id": "isbn:1",
                "title": "Dune",
                "author": "Frank Herbert",
                "language_code": "fr",
                "query": "Dune Frank Herbert French audiobook",
            }
        )
    row = read_search_queue(queue)[0]
    ranked = candidates_from_prowlarr(
        row,
        [
            {
                "title": "Dune - Frank Herbert VF",
                "guid": "prowlarr-guid",
                "indexerId": 7,
                "infoUrl": "https://indexer.example/dune",
                "language": "French",
                "protocol": "torrent",
                "size": 123,
            }
        ],
    )

    csv_row = ranked[0].as_csv_row()

    assert csv_row["candidate_guid"] == "prowlarr-guid"
    assert csv_row["prowlarr_indexer_id"] == "7"
    assert csv_row["download_protocol"] == "torrent"


def test_audiobook_search_writes_review_candidates_and_language_mismatch(tmp_path: Path, capsys, monkeypatch) -> None:
    queue = tmp_path / "audiobook_search_queue.csv"
    matches = tmp_path / "audiobook_matches.csv"
    with queue.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "record_id",
                "title",
                "author",
                "isbn",
                "language_code",
                "wanted_language",
                "language_policy",
                "query",
                "alternate_query",
                "root_folder_hint",
                "audiobookbay_search_url",
                "manual_review_required",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "record_id": "isbn:9780441172719",
                "title": "Dune",
                "author": "Frank Herbert",
                "isbn": "9780441172719",
                "language_code": "fr",
                "wanted_language": "French",
                "language_policy": "require_french_or_manual_review",
                "query": "Dune Frank Herbert French audiobook",
                "alternate_query": "Dune Frank Herbert livre audio francais",
                "root_folder_hint": "/Data/Audiobooks/Francais",
                "audiobookbay_search_url": "",
                "manual_review_required": "true",
            }
        )
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
      <channel>
        <item>
          <title>Dune - Frank Herbert VF</title>
          <guid>https://audiobook.example/dune-fr</guid>
          <comments>https://audiobook.example/dune-fr</comments>
          <torznab:attr name="language" value="French" />
        </item>
        <item>
          <title>Dune - Frank Herbert English</title>
          <guid>https://audiobook.example/dune-en</guid>
          <comments>https://audiobook.example/dune-en</comments>
          <torznab:attr name="language" value="English" />
        </item>
      </channel>
    </rss>
    """
    requested_urls: list[str] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return xml

    def fake_urlopen(request: Request, timeout: int):
        requested_urls.append(request.full_url)
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    assert main(["audiobook-search", "--queue-csv", str(queue), "--matches-csv", str(matches), "--torznab-url", "http://user:pass@127.0.0.1:8765/api?apikey=secret"]) == 0
    output = capsys.readouterr().out
    summary = json.loads(output)

    with matches.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert summary["candidate_rows"] == 2
    assert summary["grabbed"] == 0
    assert "secret" not in output
    assert "user:pass" not in output
    assert all("t=get" not in url for url in requested_urls)
    assert rows[0]["candidate_language_code"] == "fr"
    assert rows[0]["decision_status"] == "pending_review"
    assert rows[1]["candidate_language_code"] == "en"
    assert rows[1]["decision_status"] == "language_mismatch"

    rows[0]["decision_status"] = "rejected"
    rows[0]["notes"] = "wrong narrator"
    with matches.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    assert main(["audiobook-search", "--queue-csv", str(queue), "--matches-csv", str(matches), "--torznab-url", "http://127.0.0.1:8765/api"]) == 0
    capsys.readouterr()
    with matches.open(encoding="utf-8", newline="") as handle:
        rerun_rows = list(csv.DictReader(handle))

    assert rerun_rows[0]["decision_status"] == "rejected"
    assert rerun_rows[0]["notes"] == "wrong narrator"


def test_candidates_can_be_approved_rejected_and_exported_without_grabbing(tmp_path: Path, capsys) -> None:
    matches = tmp_path / "audiobook_matches.csv"
    approved = tmp_path / "approved.csv"
    with matches.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "record_id",
                "book_title",
                "book_author",
                "book_language_code",
                "search_query",
                "candidate_title",
                "candidate_language",
                "candidate_language_code",
                "candidate_url",
                "score",
                "decision_status",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "record_id": "isbn:1",
                "book_title": "Public Domain Book",
                "book_author": "Author",
                "book_language_code": "en",
                "search_query": "Public Domain Book audiobook",
                "candidate_title": "Public Domain Book",
                "candidate_language": "English",
                "candidate_language_code": "en",
                "candidate_url": "https://librivox.example/books/1",
                "score": "91",
                "decision_status": "pending_review",
                "notes": "",
            }
        )

    assert main(["candidates", "approve", "isbn:1", "https://librivox.example/books/1", "--matches-csv", str(matches), "--notes", "public domain source"]) == 0
    approved_summary = json.loads(capsys.readouterr().out)
    assert approved_summary["updated"]["decision_status"] == "approved"
    assert approved_summary["grabbed"] == 0

    assert main(["candidates", "export-approved", "--matches-csv", str(matches), "--output", str(approved)]) == 0
    export_summary = json.loads(capsys.readouterr().out)
    assert export_summary["approved_rows"] == 1
    assert export_summary["grabbed"] == 0
    assert export_summary["downloaded"] == 0

    with approved.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["decision_status"] == "approved"
    assert rows[0]["candidate_url"] == "https://librivox.example/books/1"

    assert main(["candidates", "reject", "isbn:1", "https://librivox.example/books/1", "--matches-csv", str(matches), "--notes", "wrong edition"]) == 0
    rejected_summary = json.loads(capsys.readouterr().out)
    assert rejected_summary["updated"]["decision_status"] == "rejected"


def test_part_volume_candidate_requires_completeness_review(tmp_path: Path, capsys) -> None:
    status, notes = classify_candidate_completeness(
        "Ainsi parlait Zarathoustra",
        "Ainsi parlait Zarathoustra 1 - Le declin",
    )
    assert status == "needs_completeness_review"
    assert "numbered part" in notes

    matches = tmp_path / "audiobook_matches.csv"
    with matches.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "record_id",
                "book_title",
                "book_author",
                "book_language_code",
                "search_query",
                "candidate_title",
                "candidate_language",
                "candidate_language_code",
                "candidate_url",
                "score",
                "candidate_completeness_status",
                "candidate_completeness_notes",
                "decision_status",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "record_id": "text:zarathoustra",
                "book_title": "Ainsi parlait Zarathoustra",
                "book_author": "Friedrich Nietzsche",
                "book_language_code": "fr",
                "search_query": "Ainsi parlait Zarathoustra Friedrich Nietzsche livre audio francais",
                "candidate_title": "Ainsi parlait Zarathoustra 1 - Le declin",
                "candidate_language": "French",
                "candidate_language_code": "fr",
                "candidate_url": "https://example.test/zarathoustra-1",
                "score": "90",
                "candidate_completeness_status": "needs_completeness_review",
                "candidate_completeness_notes": "Candidate title appears to be a numbered part/volume of a larger audiobook.",
                "decision_status": "needs_completeness_review",
                "notes": "",
            }
        )

    assert main(["candidates", "approve", "text:zarathoustra", "https://example.test/zarathoustra-1", "--matches-csv", str(matches)]) == 1
    captured = capsys.readouterr()
    assert "one part/volume" in captured.err

    assert main(
        [
            "candidates",
            "approve",
            "text:zarathoustra",
            "https://example.test/zarathoustra-1",
            "--matches-csv",
            str(matches),
            "--allow-incomplete",
            "--notes",
            "all parts handled together",
        ]
    ) == 0


def test_workflow_marks_single_part_as_needs_parts(tmp_path: Path, monkeypatch) -> None:
    export = tmp_path / "export.csv"
    write_export(
        export,
        [
            {
                "Title": "Ainsi parlait Zarathoustra",
                "Author": "Friedrich Nietzsche",
                "Language": "francais",
                "ISBN": "9780000000003",
            }
        ],
    )

    def fake_search(settings: StackSettings, query: str):
        return [
            {
                "title": "Ainsi parlait Zarathoustra 1 - Le declin",
                "guid": "guid-1",
                "indexerId": 9,
                "infoUrl": "https://example.test/zara-1",
                "language": "French",
                "protocol": "torrent",
            }
        ]

    monkeypatch.setattr("bookbuddarr.workflow.prowlarr_search", fake_search)
    summary = run_monitored_workflow(
        export,
        paths=WorkflowPaths(
            registry=tmp_path / "registry.csv",
            new_csv=tmp_path / "new.csv",
            readarr_csv=tmp_path / "readarr.csv",
            audiobook_csv=tmp_path / "audio.csv",
            matches_csv=tmp_path / "matches.csv",
            workflow_status_csv=tmp_path / "workflow.csv",
        ),
        stack=StackSettings.from_mapping(
            {
                "prowlarr_url": "http://prowlarr.test",
                "prowlarr_api_key": "secret",
                "download_mode": "approved_or_eligible",
                "candidate_score_threshold": 1,
            }
        ),
        dry_run=True,
    )

    with (tmp_path / "workflow.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert summary["states"] == {"needs_parts": 1}
    assert rows[0]["state"] == "needs_parts"
    assert rows[0]["parts_found"] == "1"
    assert rows[0]["parts_missing"] == "unknown"


def test_workflow_imports_existing_completed_download_without_grab(tmp_path: Path, monkeypatch) -> None:
    export = tmp_path / "export.csv"
    completed = tmp_path / "completed" / "Dune - Frank Herbert VF"
    completed.mkdir(parents=True)
    (completed / "track.m4b").write_text("synthetic", encoding="utf-8")
    target_root = tmp_path / "Audiobooks" / "Francais"
    write_export(
        export,
        [
            {"Title": "Dune", "Author": "Frank Herbert", "Language": "francais", "ISBN": "9780441172719"},
        ],
    )

    def fake_search(settings: StackSettings, query: str):
        return [
            {
                "title": "Dune - Frank Herbert VF",
                "guid": "guid-1",
                "indexerId": 9,
                "infoUrl": "https://example.test/dune",
                "language": "French",
                "protocol": "torrent",
            }
        ]

    def fake_completed(settings: StackSettings, title: str):
        return {"name": "Dune - Frank Herbert VF", "content_path": str(completed), "progress": 1}

    def fail_grab(*args, **kwargs):
        raise AssertionError("workflow should not grab when completed qBittorrent item already exists")

    monkeypatch.setattr("bookbuddarr.workflow.prowlarr_search", fake_search)
    monkeypatch.setattr("bookbuddarr.workflow.find_completed_download", fake_completed)
    monkeypatch.setattr("bookbuddarr.workflow.prowlarr_grab", fail_grab)

    summary = run_monitored_workflow(
        export,
        paths=WorkflowPaths(
            registry=tmp_path / "registry.csv",
            new_csv=tmp_path / "new.csv",
            readarr_csv=tmp_path / "readarr.csv",
            audiobook_csv=tmp_path / "audio.csv",
            matches_csv=tmp_path / "matches.csv",
            workflow_status_csv=tmp_path / "workflow.csv",
        ),
        stack=StackSettings.from_mapping(
            {
                "prowlarr_url": "http://prowlarr.test",
                "prowlarr_api_key": "secret",
                "qbittorrent_url": "http://qbit.test",
                "audiobook_root_fr": str(target_root),
                "download_mode": "approved_or_eligible",
                "candidate_score_threshold": 1,
            }
        ),
    )

    with (tmp_path / "workflow.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert summary["states"] == {"complete": 1}
    assert rows[0]["state"] == "complete"
    assert (target_root / "Dune" / "track.m4b").exists()


def test_workflow_preserves_existing_approval_when_search_returns_no_rows(tmp_path: Path, monkeypatch) -> None:
    export = tmp_path / "export.csv"
    completed = tmp_path / "completed" / "Dune - Frank Herbert VF"
    completed.mkdir(parents=True)
    (completed / "track.m4b").write_text("synthetic", encoding="utf-8")
    target_root = tmp_path / "Audiobooks" / "Francais"
    matches = tmp_path / "matches.csv"
    write_export(
        export,
        [
            {"Title": "Dune", "Author": "Frank Herbert", "Language": "francais", "ISBN": "9780441172719"},
        ],
    )
    with matches.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "record_id",
                "book_title",
                "book_author",
                "book_language_code",
                "search_query",
                "candidate_title",
                "candidate_language",
                "candidate_language_code",
                "candidate_url",
                "candidate_guid",
                "prowlarr_indexer_id",
                "download_protocol",
                "download_size",
                "score",
                "candidate_completeness_status",
                "candidate_completeness_notes",
                "decision_status",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "record_id": "isbn:9780441172719",
                "book_title": "Dune",
                "book_author": "Frank Herbert",
                "book_language_code": "fr",
                "search_query": "Dune Frank Herbert French audiobook",
                "candidate_title": "Dune - Frank Herbert VF",
                "candidate_language": "French",
                "candidate_language_code": "fr",
                "candidate_url": "https://example.test/dune",
                "score": "90",
                "candidate_completeness_status": "unknown",
                "candidate_completeness_notes": "",
                "decision_status": "approved",
                "notes": "already reviewed",
            }
        )

    monkeypatch.setattr("bookbuddarr.workflow.prowlarr_search", lambda settings, query: [])
    monkeypatch.setattr(
        "bookbuddarr.workflow.find_completed_download",
        lambda settings, title: {"name": "Dune - Frank Herbert VF", "content_path": str(completed), "progress": 1},
    )
    summary = run_monitored_workflow(
        export,
        paths=WorkflowPaths(
            registry=tmp_path / "registry.csv",
            new_csv=tmp_path / "new.csv",
            readarr_csv=tmp_path / "readarr.csv",
            audiobook_csv=tmp_path / "audio.csv",
            matches_csv=matches,
            workflow_status_csv=tmp_path / "workflow.csv",
        ),
        stack=StackSettings.from_mapping(
            {
                "prowlarr_url": "http://prowlarr.test",
                "prowlarr_api_key": "secret",
                "qbittorrent_url": "http://qbit.test",
                "audiobook_root_fr": str(target_root),
                "download_mode": "approved_only",
            }
        ),
    )

    assert summary["states"] == {"complete": 1}
    with matches.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["decision_status"] == "approved"


def test_workflow_groups_completed_multipart_downloads(tmp_path: Path, monkeypatch) -> None:
    export = tmp_path / "export.csv"
    part1 = tmp_path / "completed" / "Ainsi parlait Zarathoustra 1 - Le declin"
    part2 = tmp_path / "completed" / "Ainsi parlait Zarathoustra 2 - Le Grand Midi"
    part1.mkdir(parents=True)
    part2.mkdir(parents=True)
    (part1 / "a.m4b").write_text("synthetic", encoding="utf-8")
    (part2 / "b.m4b").write_text("synthetic", encoding="utf-8")
    target_root = tmp_path / "Audiobooks" / "Francais"
    write_export(
        export,
        [
            {
                "Title": "Ainsi parlait Zarathoustra",
                "Author": "Friedrich Nietzsche",
                "Language": "francais",
                "ISBN": "9780000000003",
            }
        ],
    )

    def fake_search(settings: StackSettings, query: str):
        return [
            {
                "title": "Ainsi parlait Zarathoustra 1 - Le declin",
                "guid": "guid-1",
                "indexerId": 9,
                "infoUrl": "https://example.test/zara-1",
                "language": "French",
                "protocol": "torrent",
            }
        ]

    def fake_torrents(settings: StackSettings):
        return [
            {"name": part1.name, "content_path": str(part1), "progress": 1, "state": "uploading"},
            {"name": part2.name, "content_path": str(part2), "progress": 1, "state": "uploading"},
        ]

    monkeypatch.setattr("bookbuddarr.workflow.prowlarr_search", fake_search)
    monkeypatch.setattr("bookbuddarr.workflow.qbit_torrents", fake_torrents)
    summary = run_monitored_workflow(
        export,
        paths=WorkflowPaths(
            registry=tmp_path / "registry.csv",
            new_csv=tmp_path / "new.csv",
            readarr_csv=tmp_path / "readarr.csv",
            audiobook_csv=tmp_path / "audio.csv",
            matches_csv=tmp_path / "matches.csv",
            workflow_status_csv=tmp_path / "workflow.csv",
        ),
        stack=StackSettings.from_mapping(
            {
                "prowlarr_url": "http://prowlarr.test",
                "prowlarr_api_key": "secret",
                "qbittorrent_url": "http://qbit.test",
                "audiobook_root_fr": str(target_root),
                "download_mode": "approved_or_eligible",
                "candidate_score_threshold": 1,
            }
        ),
    )

    with (tmp_path / "workflow.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    grouped = target_root / "Ainsi parlait Zarathoustra"

    assert summary["states"] == {"complete_grouped": 1}
    assert rows[0]["state"] == "complete_grouped"
    assert rows[0]["parts_found"] == "1,2"
    assert (grouped / part1.name / "a.m4b").exists()
    assert (grouped / part2.name / "b.m4b").exists()


def test_audiobook_root_map_overrides_default_roots(tmp_path: Path) -> None:
    export = tmp_path / "export.csv"
    registry = tmp_path / "registry.csv"
    new_csv = tmp_path / "new.csv"
    readarr_csv = tmp_path / "readarr.csv"
    audio_csv = tmp_path / "audio.csv"
    root_map = tmp_path / "roots.json"
    root_map.write_text(json.dumps({"fr": "/Library/FR", "en": "/Library/EN", "unknown": "/Library/Review"}), encoding="utf-8")
    write_export(
        export,
        [
            {"Title": "Dune", "Author": "Frank Herbert", "Language": "francais", "ISBN": "9780441172719"},
            {"Title": "Foundation", "Author": "Isaac Asimov", "Language": "anglais", "ISBN": "9780553293357"},
        ],
    )

    assert main(
        [
            "ingest",
            str(export),
            "--registry",
            str(registry),
            "--new-csv",
            str(new_csv),
            "--readarr-csv",
            str(readarr_csv),
            "--audiobook-csv",
            str(audio_csv),
            "--audiobook-root-map",
            str(root_map),
        ]
    ) == 0

    with audio_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["root_folder_hint"] == "/Library/FR"
    assert rows[1]["root_folder_hint"] == "/Library/EN"


def test_diff_exports_is_read_only_and_reports_added_removed(tmp_path: Path, capsys) -> None:
    old_export = tmp_path / "old.csv"
    new_export = tmp_path / "new.csv"
    write_export(
        old_export,
        [
            {"Title": "Dune", "Author": "Frank Herbert", "Language": "francais", "ISBN": "9780441172719"},
            {"Title": "Old Book", "Author": "Writer", "Language": "anglais", "ISBN": "9780000000001"},
        ],
    )
    write_export(
        new_export,
        [
            {"Title": "Dune", "Author": "Frank Herbert", "Language": "francais", "ISBN": "9780441172719"},
            {"Title": "New Book", "Author": "Writer", "Language": "anglais", "ISBN": "9780000000002"},
        ],
    )

    assert main(["diff-exports", str(old_export), str(new_export)]) == 0
    summary = json.loads(capsys.readouterr().out)

    assert summary["added_count"] == 1
    assert summary["removed_count"] == 1
    assert summary["unchanged_count"] == 1
    assert summary["touches_registry"] is False


def test_torznab_xml_helpers() -> None:
    caps = render_caps().decode("utf-8")
    assert "<caps>" in caps
    assert 'name="Audiobook"' in caps
    assert parse_size_bytes("1.5 GB") == 1610612736


def test_torznab_log_redacts_api_key() -> None:
    message = 'GET /api?t=search&q=dune&apikey=secret-key-value HTTP/1.1'

    redacted = _redact_log_message(message)

    assert "secret-key-value" not in redacted
    assert "apikey=***redacted***" in redacted


def test_redaction_covers_stack_credentials_and_urls() -> None:
    endpoint = redact_endpoint("http://user:pass@host.local:9696/api?apikey=secret&query=dune")
    payload = redact_structure(
        {
            "prowlarr_api_key": "secret",
            "qbittorrent_password": "password",
            "download_url": "http://u:p@host.local/file?token=abc",
            "safe": "value",
        }
    )

    assert endpoint == "http://host.local:9696/api"
    encoded = json.dumps(payload)
    assert "secret" not in encoded
    assert payload["qbittorrent_password"] == "***redacted***"
    assert "token=abc" not in encoded
    assert payload["safe"] == "value"


def test_audiobookbay_client_parses_search_html() -> None:
    html = """
    <div class="post">
      <div class="postTitle"><h2><a href="/abss/dune-frank-herbert/">Dune - Frank Herbert</a></h2></div>
      <div class="postInfo">Language: French Keywords: science fiction</div>
      <div class="postContent"><p style="text-align:center">Posted: Wed, 01 Jul 2026 00:00:00 GMT<br>
      Format:<span> M4B </span> Bitrate:<span> 128 Kbps </span> File Size:<span> 1.2 </span> GB</p></div>
    </div>
    """

    class FakeClient(AudioBookBayClient):
        def _get_text(self, url: str) -> str:
            return html

    results = FakeClient(page_limit=1).search("dune")
    rss = render_rss(results, "http://127.0.0.1:8765/api", "dune").decode("utf-8")

    assert len(results) == 1
    assert results[0].language == "French"
    assert "Dune - Frank Herbert" in rss
    assert "torznab:attr" in rss


def test_torznab_cli_exposes_default_query() -> None:
    from bookbuddarr.cli import build_parser

    args = build_parser().parse_args(["torznab-serve"])
    assert args.default_query == "audiobook"


def test_web_cli_defaults_to_localhost() -> None:
    from bookbuddarr.cli import build_parser

    args = build_parser().parse_args(["web"])
    assert args.bind == "127.0.0.1"
    assert args.port == 8788


def test_web_settings_redact_secret_values() -> None:
    safe = _safe_settings(
        {
            "registry": "data/book_registry.csv",
            "torznab_url": "http://user:pass@127.0.0.1:8765/api?apikey=secret",
            "torznab_api_key": "secret-key",
        }
    )

    assert safe["torznab_url"] == "http://127.0.0.1:8765/api"
    assert safe["torznab_api_key"] == ""
    assert safe["torznab_api_key_configured"] is True


def test_web_html_exposes_upload_settings_and_review_only_ui() -> None:
    assert "Drop BookBuddy CSV file here" in APP_HTML
    assert "Save Settings" in APP_HTML
    assert "APPROVAL-GATED MODE" in APP_HTML
    assert "Audiobook Search" in APP_HTML
    assert "Run Workflow" in APP_HTML
    assert "qBittorrent URL" in APP_HTML


def test_prowlarr_helper_splits_torznab_api_url() -> None:
    helper = load_module(SERVICE_SCRIPT, "prowlarr_helper")

    assert helper.split_torznab_url("http://bookbuddarr-torznab:8765/api") == (
        "http://bookbuddarr-torznab:8765",
        "/api",
    )
    assert helper.split_torznab_url("http://bookbuddarr-torznab:8765") == (
        "http://bookbuddarr-torznab:8765",
        "/api",
    )


def test_prowlarr_helper_builds_payload_and_redacts_secrets() -> None:
    helper = load_module(SERVICE_SCRIPT, "prowlarr_helper_payload")
    schema = {
        "name": "Generic Torznab",
        "implementation": "Torznab",
        "configContract": "TorznabSettings",
        "fields": [
            {"name": "baseUrl", "value": ""},
            {"name": "apiPath", "value": ""},
            {"name": "apiKey", "value": ""},
            {"name": "categories", "value": []},
        ],
    }
    payload = helper.build_indexer_payload(
        schema,
        {
            "indexer_name": "AudioBookBay Bridge",
            "torznab_url": "http://user:pass@bookbuddarr-torznab:8765/api?apikey=secret",
            "torznab_api_key": "bridge-secret",
        },
    )
    fields = {field["name"]: field["value"] for field in payload["fields"]}
    redacted = helper.redact(payload)

    assert payload["name"] == "AudioBookBay Bridge"
    assert fields["baseUrl"] == "http://bookbuddarr-torznab:8765"
    assert fields["apiPath"] == "/api"
    assert fields["apiKey"] == "bridge-secret"
    assert fields["categories"] == [3030]
    assert "bridge-secret" not in json.dumps(redacted)
    assert "apikey=secret" not in json.dumps(redacted)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
