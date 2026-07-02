from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .bookbuddy import dedupe_records, read_bookbuddy_export
from .models import BookRecord
from .registry import load_registry_ids


@dataclass(frozen=True)
class PipelinePlan:
    records: list[BookRecord]
    unique_records: list[BookRecord]
    duplicate_records: list[BookRecord]
    known_ids: set[str]
    new_records: list[BookRecord]

    @property
    def known_records_in_export(self) -> int:
        return len(self.unique_records) - len(self.new_records)

    def summary(self, *, registry_updated: bool) -> dict[str, object]:
        return {
            "input_rows": len(self.records),
            "unique_rows": len(self.unique_records),
            "duplicates_in_export": len(self.duplicate_records),
            "known_records_before": len(self.known_ids),
            "known_records_in_export": self.known_records_in_export,
            "new_records": len(self.new_records),
            "language_split": language_split(self.unique_records),
            "registry_updated": registry_updated,
        }


def build_plan(export_csv: Path, registry: Path) -> PipelinePlan:
    records = read_bookbuddy_export(export_csv)
    unique_records, duplicate_records = dedupe_records(records)
    known_ids = load_registry_ids(registry)
    new_records = [record for record in unique_records if record.record_id not in known_ids]
    return PipelinePlan(records, unique_records, duplicate_records, known_ids, new_records)


def language_split(records: list[BookRecord]) -> dict[str, int]:
    counts = Counter(record.language_code or "unknown" for record in records)
    return dict(sorted(counts.items()))


def diff_exports(old_export_csv: Path, new_export_csv: Path) -> dict[str, object]:
    old_records = dedupe_records(read_bookbuddy_export(old_export_csv))[0]
    new_records = dedupe_records(read_bookbuddy_export(new_export_csv))[0]
    old_by_id = {record.record_id: record for record in old_records}
    new_by_id = {record.record_id: record for record in new_records}
    old_ids = set(old_by_id)
    new_ids = set(new_by_id)
    added = [new_by_id[record_id] for record_id in sorted(new_ids - old_ids)]
    removed = [old_by_id[record_id] for record_id in sorted(old_ids - new_ids)]
    unchanged = sorted(old_ids & new_ids)
    return {
        "old_export": str(old_export_csv),
        "new_export": str(new_export_csv),
        "old_unique_rows": len(old_records),
        "new_unique_rows": len(new_records),
        "added_count": len(added),
        "removed_count": len(removed),
        "unchanged_count": len(unchanged),
        "added": [_record_summary(record) for record in added],
        "removed": [_record_summary(record) for record in removed],
        "touches_registry": False,
    }


def _record_summary(record: BookRecord) -> dict[str, str]:
    return {
        "record_id": record.record_id,
        "title": record.title,
        "author": record.author,
        "isbn": record.isbn,
        "language_code": record.language_code,
    }
