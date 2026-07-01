from __future__ import annotations

import csv
from pathlib import Path

from bookbuddarr.bookbuddy import dedupe_records, read_bookbuddy_export
from bookbuddarr.cli import main


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
