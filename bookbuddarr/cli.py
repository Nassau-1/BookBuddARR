from __future__ import annotations

import argparse
import json
from pathlib import Path

from .bookbuddy import dedupe_records, read_bookbuddy_export
from .outputs import write_audiobook_search_queue, write_new_records, write_readarr_queue
from .registry import load_registry_ids, read_registry_rows, write_registry


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "ingest":
        return run_ingest(args)
    parser.error("unknown command")
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bookbuddarr",
        description="Ingest BookBuddy CSV exports and produce incremental queues for book/audiobook workflows.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="Import a BookBuddy CSV export incrementally.")
    ingest.add_argument("export_csv", type=Path, help="Path to the BookBuddy CSV export.")
    ingest.add_argument("--registry", type=Path, default=Path("data/book_registry.csv"))
    ingest.add_argument("--new-csv", type=Path, default=Path("data/new_books.csv"))
    ingest.add_argument("--readarr-csv", type=Path, default=Path("data/readarr_queue.csv"))
    ingest.add_argument("--audiobook-csv", type=Path, default=Path("data/audiobook_search_queue.csv"))
    ingest.add_argument("--audiobookbay-base-url", default="https://audiobookbay.lu")
    ingest.add_argument("--no-update-registry", action="store_true")
    ingest.add_argument("--summary-json", type=Path)
    return parser


def run_ingest(args: argparse.Namespace) -> int:
    records = read_bookbuddy_export(args.export_csv)
    unique_records, duplicate_records = dedupe_records(records)
    known_ids = load_registry_ids(args.registry)
    new_records = [record for record in unique_records if record.record_id not in known_ids]

    write_new_records(args.new_csv, new_records)
    write_readarr_queue(args.readarr_csv, new_records)
    write_audiobook_search_queue(args.audiobook_csv, new_records, args.audiobookbay_base_url)

    if not args.no_update_registry:
        write_registry(args.registry, read_registry_rows(args.registry), new_records)

    summary = {
        "input_rows": len(records),
        "unique_rows": len(unique_records),
        "duplicates_in_export": len(duplicate_records),
        "known_records_before": len(known_ids),
        "new_records": len(new_records),
        "registry_updated": not args.no_update_registry,
        "outputs": {
            "new_csv": str(args.new_csv),
            "readarr_csv": str(args.readarr_csv),
            "audiobook_csv": str(args.audiobook_csv),
            "registry": str(args.registry),
        },
    }
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
