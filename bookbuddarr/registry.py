from __future__ import annotations

import csv
from pathlib import Path

from .models import BookRecord


REGISTRY_FIELDS = [
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
]


def load_registry_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {
            row["record_id"]
            for row in csv.DictReader(handle)
            if row.get("record_id")
        }


def read_registry_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_registry(path: Path, existing_rows: list[dict[str, str]], new_records: list[BookRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = existing_rows + [record.as_registry_row() for record in new_records]
    rows = _dedupe_rows(rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REGISTRY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _dedupe_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for row in rows:
        record_id = row.get("record_id", "")
        if not record_id or record_id in seen:
            continue
        seen.add(record_id)
        out.append({field: row.get(field, "") for field in REGISTRY_FIELDS})
    return out
