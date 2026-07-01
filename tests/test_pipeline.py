from __future__ import annotations

import csv
from pathlib import Path

from bookbuddarr.bookbuddy import dedupe_records, read_bookbuddy_export
from bookbuddarr.cli import main
from bookbuddarr.rules import audiobook_rule
from bookbuddarr.torznab import AudioBookBayClient, parse_size_bytes, render_caps, render_rss


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


def test_torznab_xml_helpers() -> None:
    caps = render_caps().decode("utf-8")
    assert "<caps>" in caps
    assert 'name="Audiobook"' in caps
    assert parse_size_bytes("1.5 GB") == 1610612736


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
