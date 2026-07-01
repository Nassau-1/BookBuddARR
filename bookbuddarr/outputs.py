from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import quote_plus

from .models import BookRecord


NEW_FIELDS = [
    "record_id",
    "title",
    "author",
    "isbn",
    "language",
    "language_code",
    "year",
    "publisher",
    "series",
    "volume",
    "google_volume_id",
    "source_position",
    "source_added_at",
    "status",
    "search_query",
    "audiobook_query",
]

READARR_FIELDS = [
    "title",
    "author",
    "isbn",
    "language_code",
    "quality_profile",
    "metadata_profile",
    "root_folder_hint",
    "monitored",
    "search_for_missing",
]

AUDIOBOOK_SEARCH_FIELDS = [
    "title",
    "author",
    "isbn",
    "language_code",
    "query",
    "audiobookbay_search_url",
    "manual_review_required",
]


def write_new_records(path: Path, records: list[BookRecord]) -> None:
    _write_rows(path, NEW_FIELDS, [record.as_new_row() for record in records])


def write_readarr_queue(path: Path, records: list[BookRecord]) -> None:
    rows = []
    for record in records:
        rows.append(
            {
                "title": record.title,
                "author": record.author,
                "isbn": record.isbn,
                "language_code": record.language_code,
                "quality_profile": "eBook",
                "metadata_profile": "French Preferred" if record.language_code == "fr" else "Standard",
                "root_folder_hint": _root_hint(record),
                "monitored": "true",
                "search_for_missing": "false",
            }
        )
    _write_rows(path, READARR_FIELDS, rows)


def write_audiobook_search_queue(path: Path, records: list[BookRecord], base_url: str) -> None:
    rows = []
    for record in records:
        query = record.audiobook_query()
        rows.append(
            {
                "title": record.title,
                "author": record.author,
                "isbn": record.isbn,
                "language_code": record.language_code,
                "query": query,
                "audiobookbay_search_url": f"{base_url.rstrip('/')}/?s={quote_plus(query)}",
                "manual_review_required": "true",
            }
        )
    _write_rows(path, AUDIOBOOK_SEARCH_FIELDS, rows)


def _root_hint(record: BookRecord) -> str:
    if record.language_code == "fr":
        return "/Data/Ebooks/Francais"
    if record.language_code == "en":
        return "/Data/Ebooks/English"
    return "/Data/Ebooks"


def _write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
