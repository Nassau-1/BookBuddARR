from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .audiobook_search import (
    approved_matches,
    export_approved_matches,
    read_matches,
    read_search_queue,
    search_candidates,
    update_match_decision,
    write_matches,
)
from .bookbuddy import BookBuddyCsvError, read_bookbuddy_export
from .config import endpoint_status, load_dotenv, redact_endpoint, safe_env_summary
from .outputs import write_audiobook_search_queue, write_new_records, write_readarr_queue
from .pipeline import build_plan, diff_exports
from .registry import read_registry_rows, write_registry
from .rules import load_audiobook_root_map
from .stack import StackSettings, test_connections
from .torznab import serve as serve_torznab
from .web import serve as serve_web
from .workflow import WorkflowPaths, run_monitored_workflow


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    loaded_env = load_dotenv(args.env_file)
    if args.command == "ingest":
        return _run_safely(lambda: run_ingest(args))
    if args.command == "plan":
        return _run_safely(lambda: run_plan(args))
    if args.command == "doctor":
        return run_doctor(args, loaded_env)
    if args.command == "audiobook-search":
        return _run_safely(lambda: run_audiobook_search(args))
    if args.command == "candidates":
        return _run_safely(lambda: run_candidates(args))
    if args.command == "diff-exports":
        return _run_safely(lambda: run_diff_exports(args))
    if args.command == "test-connections":
        return _run_safely(lambda: run_test_connections(args))
    if args.command == "workflow":
        return _run_safely(lambda: run_workflow(args))
    if args.command == "torznab-serve":
        serve_torznab(args)
        return 0
    if args.command == "web":
        serve_web(args)
        return 0
    parser.error("unknown command")
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bookbuddarr",
        description="Ingest BookBuddy CSV exports and produce incremental queues for book/audiobook workflows.",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="Optional local .env file to load.")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="Import a BookBuddy CSV export incrementally.")
    ingest.add_argument("export_csv", type=Path, help="Path to the BookBuddy CSV export.")
    ingest.add_argument("--registry", type=Path, default=Path("data/book_registry.csv"))
    ingest.add_argument("--new-csv", type=Path, default=Path("data/new_books.csv"))
    ingest.add_argument("--readarr-csv", type=Path, default=Path("data/readarr_queue.csv"))
    ingest.add_argument("--audiobook-csv", type=Path, default=Path("data/audiobook_search_queue.csv"))
    ingest.add_argument("--audiobookbay-base-url", default="https://audiobookbay.lu")
    ingest.add_argument("--audiobook-root-map", type=Path, help="Optional JSON map for audiobook roots, e.g. fr/en/unknown.")
    ingest.add_argument("--no-update-registry", action="store_true")
    ingest.add_argument("--summary-json", type=Path)
    plan = sub.add_parser("plan", help="Dry-run a BookBuddy export without writing queues or updating the registry.")
    plan.add_argument("export_csv", type=Path, help="Path to the BookBuddy CSV export.")
    plan.add_argument("--registry", type=Path, default=Path("data/book_registry.csv"))
    doctor = sub.add_parser("doctor", help="Validate local CSV, registry, output paths, and optional endpoints.")
    doctor.add_argument("export_csv", type=Path, help="Path to the BookBuddy CSV export.")
    doctor.add_argument("--registry", type=Path, default=Path("data/book_registry.csv"))
    doctor.add_argument("--new-csv", type=Path, default=Path("data/new_books.csv"))
    doctor.add_argument("--readarr-csv", type=Path, default=Path("data/readarr_queue.csv"))
    doctor.add_argument("--audiobook-csv", type=Path, default=Path("data/audiobook_search_queue.csv"))
    doctor.add_argument("--summary-json", type=Path)
    audiobook_search = sub.add_parser(
        "audiobook-search",
        help="Query a Torznab endpoint and persist audiobook candidates for manual review.",
    )
    audiobook_search.add_argument("--queue-csv", type=Path, default=Path("data/audiobook_search_queue.csv"))
    audiobook_search.add_argument("--matches-csv", type=Path, default=Path("data/audiobook_matches.csv"))
    audiobook_search.add_argument("--torznab-url", default=None, help="Torznab API URL. Defaults to TORZNAB_URL or localhost bridge.")
    audiobook_search.add_argument("--api-key", default=None, help="Torznab API key. Prefer TORZNAB_API_KEY in .env.")
    audiobook_search.add_argument("--timeout", type=int, default=15)
    audiobook_search.add_argument("--limit-per-book", type=int, default=5)
    audiobook_search.add_argument("--summary-json", type=Path)
    candidates = sub.add_parser("candidates", help="List, approve, reject, or export audiobook candidate review rows.")
    candidates_sub = candidates.add_subparsers(dest="candidate_command", required=True)
    candidate_list = candidates_sub.add_parser("list", help="List candidate review rows.")
    candidate_list.add_argument("--matches-csv", type=Path, default=Path("data/audiobook_matches.csv"))
    candidate_list.add_argument("--status", help="Filter by decision status.")
    candidate_list.add_argument("--approved-only", action="store_true", help="Shortcut for --status approved.")
    candidate_list.add_argument("--summary-json", type=Path)
    candidate_approve = candidates_sub.add_parser("approve", help="Approve one candidate by record ID and candidate URL.")
    candidate_approve.add_argument("record_id")
    candidate_approve.add_argument("candidate_url")
    candidate_approve.add_argument("--matches-csv", type=Path, default=Path("data/audiobook_matches.csv"))
    candidate_approve.add_argument("--notes", default=None)
    candidate_approve.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Allow approval of a candidate flagged as a numbered part/volume after manual confirmation.",
    )
    candidate_reject = candidates_sub.add_parser("reject", help="Reject one candidate by record ID and candidate URL.")
    candidate_reject.add_argument("record_id")
    candidate_reject.add_argument("candidate_url")
    candidate_reject.add_argument("--matches-csv", type=Path, default=Path("data/audiobook_matches.csv"))
    candidate_reject.add_argument("--notes", default=None)
    candidate_export = candidates_sub.add_parser("export-approved", help="Export approved candidates without grabbing or downloading.")
    candidate_export.add_argument("--matches-csv", type=Path, default=Path("data/audiobook_matches.csv"))
    candidate_export.add_argument("--output", type=Path, default=Path("data/approved_audiobook_candidates.csv"))
    candidate_export.add_argument("--format", choices=["csv", "audiobookshelf-json"], default="csv")
    candidate_export.add_argument("--summary-json", type=Path)
    diff = sub.add_parser("diff-exports", help="Diff two BookBuddy exports without touching the registry.")
    diff.add_argument("old_export_csv", type=Path)
    diff.add_argument("new_export_csv", type=Path)
    diff.add_argument("--summary-json", type=Path)
    test = sub.add_parser("test-connections", help="Test configured stack connections with redacted output.")
    test.add_argument("--settings-json", type=Path, help="Optional settings JSON produced by the web UI.")
    test.add_argument("--summary-json", type=Path)
    workflow = sub.add_parser("workflow", help="Run the monitored CSV -> search -> grab -> import workflow.")
    workflow.add_argument("export_csv", type=Path, help="Path to the BookBuddy CSV export.")
    workflow.add_argument("--registry", type=Path, default=Path("data/book_registry.csv"))
    workflow.add_argument("--new-csv", type=Path, default=Path("data/new_books.csv"))
    workflow.add_argument("--readarr-csv", type=Path, default=Path("data/readarr_queue.csv"))
    workflow.add_argument("--audiobook-csv", type=Path, default=Path("data/audiobook_search_queue.csv"))
    workflow.add_argument("--matches-csv", type=Path, default=Path("data/audiobook_matches.csv"))
    workflow.add_argument("--workflow-status-csv", type=Path, default=Path("data/workflow_status.csv"))
    workflow.add_argument("--audiobook-root-map", type=Path)
    workflow.add_argument("--torznab-url", default=None)
    workflow.add_argument("--torznab-api-key", default=None)
    workflow.add_argument("--settings-json", type=Path, help="Optional settings JSON produced by the web UI.")
    workflow.add_argument("--download-mode", choices=["approved_only", "approved_or_eligible"], default=None)
    workflow.add_argument("--import-mode", choices=["copy", "move", "none"], default=None)
    workflow.add_argument("--dry-run", action="store_true", help="Run through search and grab planning without mutating Prowlarr/qBittorrent/imports.")
    workflow.add_argument("--no-update-registry", action="store_true")
    workflow.add_argument("--summary-json", type=Path)
    torznab = sub.add_parser("torznab-serve", help="Expose AudioBookBay search as a Torznab-compatible bridge.")
    torznab.add_argument("--bind", default="127.0.0.1")
    torznab.add_argument("--port", type=int, default=8765)
    torznab.add_argument("--hostname", default="audiobookbay.lu")
    torznab.add_argument("--page-limit", type=int, default=2)
    torznab.add_argument("--timeout", type=int, default=15)
    torznab.add_argument("--api-key", default="")
    torznab.add_argument("--default-query", default="audiobook")
    web = sub.add_parser("web", help="Run the local BookBuddARR web UI.")
    web.add_argument("--bind", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8788)
    web.add_argument("--settings", type=Path, default=Path("data/bookbuddarr_settings.json"))
    return parser


def run_ingest(args: argparse.Namespace) -> int:
    plan = build_plan(args.export_csv, args.registry)
    language_roots = load_audiobook_root_map(args.audiobook_root_map)

    write_new_records(args.new_csv, plan.new_records)
    write_readarr_queue(args.readarr_csv, plan.new_records)
    write_audiobook_search_queue(
        args.audiobook_csv,
        plan.new_records,
        args.audiobookbay_base_url,
        language_roots=language_roots,
    )

    if not args.no_update_registry:
        write_registry(args.registry, read_registry_rows(args.registry), plan.new_records)

    summary = plan.summary(registry_updated=not args.no_update_registry)
    summary["outputs"] = {
        "new_csv": str(args.new_csv),
        "readarr_csv": str(args.readarr_csv),
        "audiobook_csv": str(args.audiobook_csv),
        "registry": str(args.registry),
    }
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def run_candidates(args: argparse.Namespace) -> int:
    if args.candidate_command == "list":
        rows = approved_matches(args.matches_csv) if args.approved_only else read_matches(args.matches_csv)
        status = "approved" if args.approved_only else args.status
        if status:
            rows = [row for row in rows if row.get("decision_status") == status]
        summary = {
            "matches_csv": str(args.matches_csv),
            "rows": len(rows),
            "candidates": rows,
            "grabbed": 0,
        }
        _write_optional_json(args.summary_json, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    if args.candidate_command == "approve":
        row = update_match_decision(
            args.matches_csv,
            record_id=args.record_id,
            candidate_url=args.candidate_url,
            decision_status="approved",
            notes=args.notes,
            allow_incomplete=args.allow_incomplete,
        )
        print(json.dumps({"ok": True, "updated": row, "grabbed": 0}, ensure_ascii=False, indent=2))
        return 0
    if args.candidate_command == "reject":
        row = update_match_decision(
            args.matches_csv,
            record_id=args.record_id,
            candidate_url=args.candidate_url,
            decision_status="rejected",
            notes=args.notes,
        )
        print(json.dumps({"ok": True, "updated": row, "grabbed": 0}, ensure_ascii=False, indent=2))
        return 0
    if args.candidate_command == "export-approved":
        summary = export_approved_matches(args.matches_csv, args.output, output_format=args.format)
        _write_optional_json(args.summary_json, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    raise ValueError("Unknown candidates command.")


def run_diff_exports(args: argparse.Namespace) -> int:
    summary = diff_exports(args.old_export_csv, args.new_export_csv)
    _write_optional_json(args.summary_json, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def run_test_connections(args: argparse.Namespace) -> int:
    stack = _stack_settings(args.settings_json)
    summary = {"ok": True, "connections": test_connections(stack)}
    summary["ok"] = all(item.get("ok") or item.get("optional") or not item.get("configured") for item in summary["connections"].values())
    _write_optional_json(args.summary_json, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["ok"] else 1


def run_workflow(args: argparse.Namespace) -> int:
    stack = _stack_settings(args.settings_json)
    overrides = {}
    if args.download_mode:
        overrides["download_mode"] = args.download_mode
    if args.import_mode:
        overrides["import_mode"] = args.import_mode
    if str(args.workflow_status_csv):
        overrides["workflow_state_csv"] = str(args.workflow_status_csv)
    stack = StackSettings.from_mapping({**stack.__dict__, **overrides})
    paths = WorkflowPaths(
        registry=args.registry,
        new_csv=args.new_csv,
        readarr_csv=args.readarr_csv,
        audiobook_csv=args.audiobook_csv,
        matches_csv=args.matches_csv,
        workflow_status_csv=args.workflow_status_csv,
        audiobook_root_map=args.audiobook_root_map,
        torznab_url=args.torznab_url or os.environ.get("TORZNAB_URL") or "http://127.0.0.1:8765/api",
        torznab_api_key=args.torznab_api_key if args.torznab_api_key is not None else os.environ.get("TORZNAB_API_KEY", ""),
    )
    summary = run_monitored_workflow(
        args.export_csv,
        paths=paths,
        stack=stack,
        update_registry=not args.no_update_registry,
        dry_run=args.dry_run,
    )
    _write_optional_json(args.summary_json, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("ok") else 1


def _stack_settings(settings_json: Path | None) -> StackSettings:
    if settings_json and settings_json.exists():
        return StackSettings.from_mapping(json.loads(settings_json.read_text(encoding="utf-8")))
    return StackSettings.from_mapping()


def _write_optional_json(path: Path | None, payload: dict[str, object]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_plan(args: argparse.Namespace) -> int:
    plan = build_plan(args.export_csv, args.registry)
    summary = plan.summary(registry_updated=False)
    summary["registry"] = str(args.registry)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def run_doctor(args: argparse.Namespace, loaded_env: dict[str, str]) -> int:
    checks: dict[str, object] = {
        "export_csv": _check_export_csv(args.export_csv),
        "registry": _check_registry(args.registry),
        "outputs": {
            "new_csv": _check_output_path(args.new_csv),
            "readarr_csv": _check_output_path(args.readarr_csv),
            "audiobook_csv": _check_output_path(args.audiobook_csv),
        },
        "env": safe_env_summary(loaded_env),
        "optional_endpoints": endpoint_status(),
    }
    ok = _checks_ok(checks)
    summary = {"ok": ok, "checks": checks}
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def run_audiobook_search(args: argparse.Namespace) -> int:
    torznab_url = args.torznab_url or os.environ.get("TORZNAB_URL") or "http://127.0.0.1:8765/api"
    api_key = args.api_key if args.api_key is not None else os.environ.get("TORZNAB_API_KEY", "")
    rows = read_search_queue(args.queue_csv)
    matches = search_candidates(
        rows,
        torznab_url=torznab_url,
        api_key=api_key,
        timeout=args.timeout,
        limit_per_book=args.limit_per_book,
    )
    write_matches(args.matches_csv, matches)
    summary = {
        "queue_rows": len(rows),
        "candidate_rows": len(matches),
        "matches_csv": str(args.matches_csv),
        "torznab_url": redact_endpoint(torznab_url),
        "mode": "dry_run_review_only",
        "grabbed": 0,
    }
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _check_export_csv(path: Path) -> dict[str, object]:
    try:
        records = read_bookbuddy_export(path)
    except (BookBuddyCsvError, OSError) as exc:
        return {"ok": False, "path": str(path), "error": str(exc)}
    return {"ok": True, "path": str(path), "rows": len(records)}


def _check_registry(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"ok": True, "path": str(path), "exists": False, "first_run": True}
    try:
        rows = read_registry_rows(path)
    except OSError as exc:
        return {"ok": False, "path": str(path), "exists": True, "error": str(exc)}
    return {"ok": True, "path": str(path), "exists": True, "rows": len(rows), "first_run": False}


def _check_output_path(path: Path) -> dict[str, object]:
    parent = path.parent if str(path.parent) else Path(".")
    if parent.exists():
        return {
            "ok": os.access(parent, os.W_OK),
            "path": str(path),
            "parent": str(parent),
            "parent_exists": True,
        }
    return {
        "ok": _nearest_existing_parent_writable(parent),
        "path": str(path),
        "parent": str(parent),
        "parent_exists": False,
        "will_create_parent": True,
    }


def _nearest_existing_parent_writable(path: Path) -> bool:
    current = path
    while not current.exists() and current != current.parent:
        current = current.parent
    return current.exists() and os.access(current, os.W_OK)


def _checks_ok(value: object) -> bool:
    if isinstance(value, dict):
        if value.get("ok") is False:
            return False
        return all(_checks_ok(item) for item in value.values())
    if isinstance(value, list):
        return all(_checks_ok(item) for item in value)
    return True


def _run_safely(command: object) -> int:
    try:
        return command()
    except (BookBuddyCsvError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
