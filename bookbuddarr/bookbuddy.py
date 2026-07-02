from __future__ import annotations

import csv
from pathlib import Path

from .models import BookRecord
from .normalize import clean_text, language_code, normalize_isbn, stable_record_id


REQUIRED_BOOKBUDDY_COLUMNS = [
    "Title",
    "Author",
    "Language",
    "ISBN",
]


class BookBuddyCsvError(ValueError):
    pass


def read_bookbuddy_export(path: Path) -> list[BookRecord]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        validate_bookbuddy_columns(reader.fieldnames)
        return [_row_to_record(row) for row in reader]


def validate_bookbuddy_columns(fieldnames: list[str] | None) -> None:
    if fieldnames is None:
        raise BookBuddyCsvError("BookBuddy CSV is missing a header row.")
    missing = [field for field in REQUIRED_BOOKBUDDY_COLUMNS if field not in fieldnames]
    if missing:
        present = ", ".join(fieldnames) if fieldnames else "none"
        required = ", ".join(REQUIRED_BOOKBUDDY_COLUMNS)
        missing_text = ", ".join(missing)
        raise BookBuddyCsvError(
            f"BookBuddy CSV is missing required column(s): {missing_text}. "
            f"Required columns: {required}. Present columns: {present}."
        )


def _row_to_record(row: dict[str, str]) -> BookRecord:
    title = clean_text(row.get("Title"))
    author = clean_text(row.get("Author"))
    isbn = normalize_isbn(row.get("ISBN"))
    language = clean_text(row.get("Language"))
    return BookRecord(
        record_id=stable_record_id(title, author, isbn, language),
        title=title,
        author=author,
        isbn=isbn,
        language=language,
        language_code=language_code(language),
        year=clean_text(row.get("Year Published")),
        publisher=clean_text(row.get("Publisher")),
        source_position=clean_text(row.get("Position")),
        source_added_at=clean_text(row.get("Date Added")),
        original_title=clean_text(row.get("Original Title")),
        series=clean_text(row.get("Series")),
        volume=clean_text(row.get("Volume")),
        google_volume_id=clean_text(row.get("Google VolumeID")),
        status=clean_text(row.get("Status")),
    )


def dedupe_records(records: list[BookRecord]) -> tuple[list[BookRecord], list[BookRecord]]:
    seen: set[str] = set()
    unique: list[BookRecord] = []
    duplicates: list[BookRecord] = []
    for record in records:
        if record.record_id in seen:
            duplicates.append(record)
            continue
        seen.add(record.record_id)
        unique.append(record)
    return unique, duplicates
