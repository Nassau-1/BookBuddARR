from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .audiobook_search import (
    RankedCandidate,
    candidates_from_prowlarr,
    read_matches,
    read_search_queue,
    search_candidates,
    write_matches,
)
from .outputs import write_audiobook_search_queue, write_new_records, write_readarr_queue
from .pipeline import build_plan
from .registry import read_registry_rows, write_registry
from .rules import load_audiobook_root_map
from .stack import (
    StackSettings,
    append_activity,
    find_completed_download,
    import_download,
    import_download_group,
    prowlarr_grab,
    prowlarr_search,
    qbit_torrents,
    verify_audiobookshelf_path,
)


WORKFLOW_STATUS_FIELDS = [
    "record_id",
    "book_title",
    "book_author",
    "language_code",
    "state",
    "candidate_title",
    "candidate_url",
    "parts_found",
    "parts_missing",
    "target_path",
    "details",
]


@dataclass(frozen=True)
class WorkflowPaths:
    registry: Path = Path("data/book_registry.csv")
    new_csv: Path = Path("data/new_books.csv")
    readarr_csv: Path = Path("data/readarr_queue.csv")
    audiobook_csv: Path = Path("data/audiobook_search_queue.csv")
    matches_csv: Path = Path("data/audiobook_matches.csv")
    workflow_status_csv: Path = Path("data/workflow_status.csv")
    audiobook_root_map: Path | None = None
    torznab_url: str = "http://127.0.0.1:8765/api"
    torznab_api_key: str = ""


def run_monitored_workflow(
    export_csv: Path,
    *,
    paths: WorkflowPaths,
    stack: StackSettings,
    update_registry: bool = True,
    dry_run: bool = False,
    limit_per_book: int = 5,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    activity_path = Path(stack.activity_log)

    plan = build_plan(export_csv, paths.registry)
    roots = load_audiobook_root_map(paths.audiobook_root_map) if paths.audiobook_root_map else None
    write_new_records(paths.new_csv, plan.new_records)
    write_readarr_queue(paths.readarr_csv, plan.new_records)
    write_audiobook_search_queue(paths.audiobook_csv, plan.new_records, "https://audiobookbay.lu", language_roots=roots)
    if update_registry:
        write_registry(paths.registry, read_registry_rows(paths.registry), plan.new_records)
    _event(events, activity_path, "ingested", {"new_records": len(plan.new_records), "registry_updated": update_registry})

    queue_rows = read_search_queue(paths.audiobook_csv)
    existing_review_rows = read_matches(paths.matches_csv)
    matches = _search_workflow_candidates(queue_rows, paths=paths, stack=stack, limit_per_book=limit_per_book)
    write_matches(paths.matches_csv, matches)
    persisted_matches = _restore_existing_approved_rows(read_matches(paths.matches_csv), existing_review_rows, queue_rows)
    if len(persisted_matches) > len(read_matches(paths.matches_csv)):
        _write_match_dicts(paths.matches_csv, persisted_matches)
    _event(events, activity_path, "searched", {"queue_rows": len(queue_rows), "candidate_rows": len(persisted_matches)})

    status_rows = []
    selected_rows = _select_rows(persisted_matches, stack)
    for queue_row in queue_rows:
        rows_for_book = [row for row in persisted_matches if row.get("record_id") == queue_row.record_id]
        selected = selected_rows.get(queue_row.record_id)
        if not rows_for_book:
            status_rows.append(_status(queue_row, "blocked", details="no_candidates_found"))
            continue
        if selected is None:
            multipart = _multipart_status(rows_for_book[0], rows_for_book)
            if multipart["state"] == "needs_parts":
                completed_parts = _completed_part_downloads(stack, queue_row.title) if stack.qbittorrent_url and not dry_run else {}
                if len(completed_parts) >= 2:
                    grouped = _import_completed_part_group(queue_row, rows_for_book[0], completed_parts, stack)
                    status_rows.append(grouped)
                    continue
                status_rows.append(
                    _status(
                        queue_row,
                        "needs_parts",
                        candidate=rows_for_book[0],
                        details=multipart["details"],
                        parts_found=multipart["parts_found"],
                        parts_missing=multipart["parts_missing"],
                    )
                )
                continue
            status_rows.append(_status(queue_row, "needs_review", candidate=rows_for_book[0], details=rows_for_book[0].get("decision_status", "")))
            continue
        multipart = _multipart_status(selected, rows_for_book)
        if multipart["state"] == "needs_parts":
            completed_parts = _completed_part_downloads(stack, queue_row.title) if stack.qbittorrent_url and not dry_run else {}
            if len(completed_parts) >= 2:
                status_rows.append(_import_completed_part_group(queue_row, selected, completed_parts, stack))
                continue
            status_rows.append(_status(queue_row, "needs_parts", candidate=selected, details=multipart["details"], parts_found=multipart["parts_found"], parts_missing=multipart["parts_missing"]))
            continue
        completed = find_completed_download(stack, selected.get("candidate_title", "")) if stack.qbittorrent_url and not dry_run else None
        if completed is None:
            release = _release_from_match(selected)
            grab = prowlarr_grab(stack, release, dry_run=dry_run) if stack.prowlarr_url else {"ok": False, "state": "blocked", "reason": "prowlarr_not_configured"}
            _event(events, activity_path, "grab", {"record_id": queue_row.record_id, "state": grab.get("state"), "ok": grab.get("ok")})
            if not grab.get("ok"):
                status_rows.append(_status(queue_row, "blocked", candidate=selected, details=str(grab.get("reason") or grab.get("state"))))
                continue
            if dry_run or not stack.qbittorrent_url:
                status_rows.append(_status(queue_row, "grabbing", candidate=selected, details=str(grab.get("state"))))
                continue
            completed = find_completed_download(stack, selected.get("candidate_title", ""))
        if completed is None:
            status_rows.append(_status(queue_row, "downloading", candidate=selected, details="waiting_for_qbittorrent_completion"))
            continue
        source = _download_path(completed)
        if source is None:
            status_rows.append(_status(queue_row, "blocked", candidate=selected, details="completed_download_path_unknown"))
            continue
        root = Path(stack.root_for_language(queue_row.language_code))
        imported = import_download(source, root, queue_row.title, mode=stack.import_mode)
        if not imported.get("ok"):
            status_rows.append(_status(queue_row, "blocked", candidate=selected, details=str(imported.get("reason"))))
            continue
        verified = verify_audiobookshelf_path(Path(str(imported.get("target"))))
        state = "complete_grouped" if multipart["state"] == "complete_grouped" else "complete"
        status_rows.append(
            _status(
                queue_row,
                state if verified.get("ok") else "blocked",
                candidate=selected,
                details=str(verified.get("state") or verified.get("reason")),
                target_path=str(imported.get("target", "")),
                parts_found=multipart["parts_found"],
                parts_missing=multipart["parts_missing"],
            )
        )

    _write_status(paths.workflow_status_csv, status_rows)
    counts = _state_counts(status_rows)
    summary = {
        "ok": not counts.get("blocked"),
        "mode": "monitored_workflow",
        "dry_run": dry_run,
        "plan": plan.summary(registry_updated=update_registry),
        "matches_csv": str(paths.matches_csv),
        "workflow_status_csv": str(paths.workflow_status_csv),
        "states": counts,
        "events": events[-20:],
    }
    _event(events, activity_path, "workflow_finished", {"states": counts})
    return summary


def _search_workflow_candidates(
    queue_rows: list[Any],
    *,
    paths: WorkflowPaths,
    stack: StackSettings,
    limit_per_book: int,
) -> list[RankedCandidate]:
    if stack.prowlarr_url and stack.prowlarr_api_key:
        matches: list[RankedCandidate] = []
        for row in queue_rows:
            releases = prowlarr_search(stack, row.query)
            matches.extend(candidates_from_prowlarr(row, releases)[:limit_per_book])
        return matches
    return search_candidates(
        queue_rows,
        torznab_url=paths.torznab_url,
        api_key=paths.torznab_api_key,
        limit_per_book=limit_per_book,
    )


def _select_rows(rows: list[dict[str, str]], stack: StackSettings) -> dict[str, dict[str, str]]:
    selected: dict[str, dict[str, str]] = {}
    for row in sorted(rows, key=lambda item: int(item.get("score") or 0), reverse=True):
        if row.get("record_id") in selected:
            continue
        if row.get("decision_status") == "approved":
            selected[row["record_id"]] = row
            continue
        if stack.download_mode != "approved_or_eligible":
            continue
        if _eligible(row, stack):
            selected[row["record_id"]] = row
    return selected


def _restore_existing_approved_rows(
    new_rows: list[dict[str, str]],
    existing_rows: list[dict[str, str]],
    queue_rows: list[Any],
) -> list[dict[str, str]]:
    queue_ids = {row.record_id for row in queue_rows}
    seen = {(row.get("record_id", ""), row.get("candidate_url", "")) for row in new_rows}
    restored = list(new_rows)
    for row in existing_rows:
        key = (row.get("record_id", ""), row.get("candidate_url", ""))
        if row.get("record_id") in queue_ids and row.get("decision_status") == "approved" and key not in seen:
            restored.append(row)
            seen.add(key)
    return restored


def _write_match_dicts(path: Path, rows: list[dict[str, str]]) -> None:
    from .audiobook_search import MATCH_FIELDS

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MATCH_FIELDS)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in MATCH_FIELDS} for row in rows])


def _eligible(row: dict[str, str], stack: StackSettings) -> bool:
    if row.get("decision_status") != "pending_review":
        return False
    if row.get("candidate_completeness_status") == "needs_completeness_review":
        return False
    if row.get("book_language_code") and row.get("candidate_language_code") and row.get("book_language_code") != row.get("candidate_language_code"):
        return False
    return int(row.get("score") or 0) >= stack.candidate_score_threshold


def _multipart_status(selected: dict[str, str], rows_for_book: list[dict[str, str]]) -> dict[str, str]:
    if selected.get("candidate_completeness_status") != "needs_completeness_review":
        return {"state": "single", "parts_found": "", "parts_missing": "", "details": ""}
    parts = sorted({part for row in rows_for_book for part in [_part_marker(row.get("candidate_title", ""))] if part})
    if len(parts) >= 2:
        return {"state": "complete_grouped", "parts_found": ",".join(parts), "parts_missing": "", "details": "multiple_part_candidates_found"}
    missing = "unknown"
    return {"state": "needs_parts", "parts_found": ",".join(parts), "parts_missing": missing, "details": "candidate_is_single_numbered_part"}


def _part_marker(title: str) -> str:
    import re

    match = re.search(r"\b(?:vol|volume|tome|part|partie|book|livre|disc|disque|cd)\s*(0?[1-9]|[ivxlcdm]+)\b", title, flags=re.I)
    if match:
        return match.group(1).lstrip("0").lower()
    match = re.search(r"\b(0?[1-9]|[ivxlcdm]+)\s*(?:-|:)\s+", title, flags=re.I)
    return match.group(1).lstrip("0").lower() if match else ""


def _release_from_match(row: dict[str, str]) -> dict[str, Any]:
    return {
        "guid": row.get("candidate_guid") or row.get("candidate_url"),
        "indexerId": row.get("prowlarr_indexer_id"),
        "infoUrl": row.get("candidate_url"),
        "downloadUrl": row.get("candidate_guid"),
    }


def _download_path(torrent: dict[str, Any]) -> Path | None:
    for key in ("content_path", "contentPath"):
        value = str(torrent.get(key) or "").strip()
        if value:
            return Path(value)
    save_path = str(torrent.get("save_path") or torrent.get("savePath") or "").strip()
    name = str(torrent.get("name") or "").strip()
    return Path(save_path) / name if save_path and name else None


def _completed_part_downloads(stack: StackSettings, book_title: str) -> dict[str, Path]:
    completed: dict[str, Path] = {}
    book_key = _simple_key(book_title)
    if not book_key:
        return completed
    try:
        torrents = qbit_torrents(stack)
    except Exception:
        return completed
    for torrent in torrents:
        name = str(torrent.get("name") or "")
        state = str(torrent.get("state") or "")
        progress = float(torrent.get("progress") or 0)
        if book_key not in _simple_key(name):
            continue
        marker = _part_marker(name)
        if not marker:
            continue
        if progress < 1 and not state.lower().startswith(("upload", "stalledup", "pausedup")):
            continue
        path = _download_path(torrent)
        if path is not None:
            completed[marker] = path
    return completed


def _import_completed_part_group(
    queue_row: Any,
    candidate: dict[str, str],
    completed_parts: dict[str, Path],
    stack: StackSettings,
) -> dict[str, str]:
    root = Path(stack.root_for_language(queue_row.language_code))
    imported = import_download_group(list(completed_parts.values()), root, queue_row.title, mode=stack.import_mode)
    if not imported.get("ok"):
        return _status(queue_row, "blocked", candidate=candidate, details=str(imported.get("reason")))
    verified = verify_audiobookshelf_path(Path(str(imported.get("target"))))
    return _status(
        queue_row,
        "complete_grouped" if verified.get("ok") else "blocked",
        candidate=candidate,
        details=str(verified.get("state") or verified.get("reason")),
        target_path=str(imported.get("target", "")),
        parts_found=",".join(sorted(completed_parts)),
        parts_missing="",
    )


def _simple_key(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").replace("-", " ").split())


def _status(
    row: Any,
    state: str,
    *,
    candidate: dict[str, str] | None = None,
    details: str = "",
    parts_found: str = "",
    parts_missing: str = "",
    target_path: str = "",
) -> dict[str, str]:
    return {
        "record_id": row.record_id,
        "book_title": row.title,
        "book_author": row.author,
        "language_code": row.language_code,
        "state": state,
        "candidate_title": (candidate or {}).get("candidate_title", ""),
        "candidate_url": (candidate or {}).get("candidate_url", ""),
        "parts_found": parts_found,
        "parts_missing": parts_missing,
        "target_path": target_path,
        "details": details,
    }


def _write_status(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=WORKFLOW_STATUS_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _state_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    return dict(sorted(counts.items()))


def _event(events: list[dict[str, Any]], path: Path, event: str, payload: dict[str, Any]) -> None:
    item = {"event": event, **payload}
    events.append(item)
    append_activity(path, item)
