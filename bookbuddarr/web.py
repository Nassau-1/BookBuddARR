from __future__ import annotations

import argparse
import csv
import json
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .audiobook_search import (
    approved_matches,
    export_approved_matches,
    read_search_queue,
    search_candidates,
    update_match_decision,
    write_matches,
)
from .bookbuddy import BookBuddyCsvError, read_bookbuddy_export
from .config import load_dotenv, redact_endpoint
from .outputs import write_audiobook_search_queue, write_new_records, write_readarr_queue
from .pipeline import build_plan
from .registry import read_registry_rows, write_registry
from .rules import load_audiobook_root_map
from .stack import StackSettings, test_connections
from .workflow import WorkflowPaths, run_monitored_workflow


DATA_DIR = Path(os.environ.get("BOOKBUDDARR_DATA_DIR", "data"))
SETTINGS_PATH = DATA_DIR / "bookbuddarr_settings.json"
UPLOAD_DIR = DATA_DIR / "uploads"
SECRET_FIELDS = {
    "torznab_api_key",
    "readarr_api_key",
    "prowlarr_api_key",
    "qbittorrent_password",
    "sabnzbd_api_key",
    "nzbget_password",
    "audiobookshelf_api_key",
}


DEFAULT_SETTINGS = {
    "registry": str(DATA_DIR / "book_registry.csv"),
    "new_csv": str(DATA_DIR / "new_books.csv"),
    "readarr_csv": str(DATA_DIR / "readarr_queue.csv"),
    "audiobook_csv": str(DATA_DIR / "audiobook_search_queue.csv"),
    "matches_csv": str(DATA_DIR / "audiobook_matches.csv"),
    "approved_export_csv": str(DATA_DIR / "approved_audiobook_candidates.csv"),
    "audiobook_root_map": "",
    "torznab_url": "http://127.0.0.1:8765/api",
    "torznab_api_key": "",
    "prowlarr_url": "",
    "prowlarr_api_key": "",
    "qbittorrent_url": "",
    "qbittorrent_username": "",
    "qbittorrent_password": "",
    "qbittorrent_category": "audiobooks",
    "sabnzbd_url": "",
    "sabnzbd_api_key": "",
    "nzbget_url": "",
    "nzbget_username": "",
    "nzbget_password": "",
    "audiobookshelf_url": "",
    "audiobookshelf_api_key": "",
    "audiobookshelf_library_path": "",
    "audiobook_root_fr": "/Data/Audiobooks/Francais",
    "audiobook_root_en": "/Data/Audiobooks/English",
    "audiobook_root_unknown": "/Data/Audiobooks",
    "download_mode": "approved_only",
    "import_mode": "copy",
    "workflow_state_csv": str(DATA_DIR / "workflow_status.csv"),
    "activity_log": str(DATA_DIR / "workflow_activity.jsonl"),
    "candidate_score_threshold": "85",
    "readarr_url": "",
    "readarr_api_key": "",
}


DATA_PATH_SETTINGS = {
    "registry",
    "new_csv",
    "readarr_csv",
    "audiobook_csv",
    "matches_csv",
    "approved_export_csv",
    "workflow_state_csv",
    "activity_log",
}


ENV_SETTING_MAP = {
    "torznab_url": ["BOOKBUDDARR_TORZNAB_URL", "TORZNAB_URL"],
    "torznab_api_key": ["BOOKBUDDARR_TORZNAB_API_KEY", "TORZNAB_API_KEY"],
    "prowlarr_url": ["PROWLARR_URL"],
    "prowlarr_api_key": ["PROWLARR_API_KEY"],
    "qbittorrent_url": ["QBITTORRENT_URL"],
    "qbittorrent_username": ["QBITTORRENT_USERNAME"],
    "qbittorrent_password": ["QBITTORRENT_PASSWORD"],
    "qbittorrent_category": ["QBITTORRENT_CATEGORY"],
    "sabnzbd_url": ["SABNZBD_URL"],
    "sabnzbd_api_key": ["SABNZBD_API_KEY"],
    "nzbget_url": ["NZBGET_URL"],
    "nzbget_username": ["NZBGET_USERNAME"],
    "nzbget_password": ["NZBGET_PASSWORD"],
    "audiobookshelf_url": ["AUDIOBOOKSHELF_URL"],
    "audiobookshelf_api_key": ["AUDIOBOOKSHELF_API_KEY"],
    "audiobookshelf_library_path": ["AUDIOBOOKSHELF_LIBRARY_PATH"],
    "audiobook_root_fr": ["AUDIOBOOK_ROOT_FR"],
    "audiobook_root_en": ["AUDIOBOOK_ROOT_EN"],
    "audiobook_root_unknown": ["AUDIOBOOK_ROOT_UNKNOWN"],
    "download_mode": ["BOOKBUDDARR_DOWNLOAD_MODE"],
    "import_mode": ["BOOKBUDDARR_IMPORT_MODE"],
    "readarr_url": ["READARR_URL"],
    "readarr_api_key": ["READARR_API_KEY"],
}


def serve(args: argparse.Namespace) -> None:
    load_dotenv(args.env_file)
    handler = type("BookBuddarrWebHandler", (WebHandler,), {"settings_path": args.settings})
    server = ThreadingHTTPServer((args.bind, args.port), handler)
    print(f"BookBuddARR web UI listening on http://{args.bind}:{args.port}")
    server.serve_forever()


class WebHandler(BaseHTTPRequestHandler):
    settings_path: Path = SETTINGS_PATH

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/?"):
            self._send_html(APP_HTML)
            return
        if self.path == "/api/state":
            self._send_json(self._state())
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        try:
            if self.path == "/api/upload":
                self._send_json(self._upload(self._read_json()))
                return
            if self.path == "/api/settings":
                self._send_json(self._save_settings(self._read_json()))
                return
            if self.path == "/api/doctor":
                self._send_json(self._doctor(self._read_json()))
                return
            if self.path == "/api/plan":
                self._send_json(self._plan(self._read_json()))
                return
            if self.path == "/api/ingest":
                self._send_json(self._ingest(self._read_json()))
                return
            if self.path == "/api/audiobook-search":
                self._send_json(self._audiobook_search(self._read_json()))
                return
            if self.path == "/api/candidate-decision":
                self._send_json(self._candidate_decision(self._read_json()))
                return
            if self.path == "/api/export-approved":
                self._send_json(self._export_approved(self._read_json()))
                return
            if self.path == "/api/test-connections":
                self._send_json(self._test_connections())
                return
            if self.path == "/api/workflow":
                self._send_json(self._workflow(self._read_json()))
                return
        except (BookBuddyCsvError, OSError, ValueError) as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _state(self) -> dict[str, Any]:
        settings = _load_settings(self.settings_path)
        return {
            "settings": _safe_settings(settings),
            "uploads": [str(path) for path in sorted(UPLOAD_DIR.glob("*.csv"), reverse=True)[:8]],
            "matches": _read_csv_preview(Path(settings["matches_csv"]), limit=20),
            "workflow": _read_csv_preview(Path(settings["workflow_state_csv"]), limit=40),
            "workflow_summary": _csv_value_counts(Path(settings["workflow_state_csv"]), "state"),
            "approved_count": len(approved_matches(Path(settings["matches_csv"]))),
            "reviewOnly": settings.get("download_mode") == "approved_only",
        }

    def _upload(self, payload: dict[str, Any]) -> dict[str, Any]:
        filename = _safe_filename(str(payload.get("filename") or "bookbuddy-upload.csv"))
        content = str(payload.get("content") or "")
        if not content.strip():
            raise ValueError("Uploaded CSV is empty.")
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        path = UPLOAD_DIR / filename
        path.write_text(content, encoding="utf-8")
        read_bookbuddy_export(path)
        return {"ok": True, "path": str(path), "filename": filename}

    def _save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = _load_settings(self.settings_path)
        next_settings = dict(current)
        for key in DEFAULT_SETTINGS:
            if key not in payload:
                continue
            value = str(payload.get(key) or "")
            if key in SECRET_FIELDS and not value:
                continue
            next_settings[key] = value
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(next_settings, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "settings": _safe_settings(next_settings)}

    def _doctor(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = _load_settings(self.settings_path)
        export_path = _require_uploaded_csv(payload.get("export_csv"))
        records = read_bookbuddy_export(export_path)
        registry = Path(settings["registry"])
        return {
            "ok": True,
            "export_csv": str(export_path),
            "rows": len(records),
            "registry_exists": registry.exists(),
            "output_parent_ready": Path(settings["new_csv"]).parent.exists(),
        }

    def _plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = _load_settings(self.settings_path)
        export_path = _require_uploaded_csv(payload.get("export_csv"))
        plan = build_plan(export_path, Path(settings["registry"]))
        return {"ok": True, "plan": plan.summary(registry_updated=False)}

    def _ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = _load_settings(self.settings_path)
        export_path = _require_uploaded_csv(payload.get("export_csv"))
        plan = build_plan(export_path, Path(settings["registry"]))
        root_map = load_audiobook_root_map(Path(settings["audiobook_root_map"])) if settings.get("audiobook_root_map") else None
        write_new_records(Path(settings["new_csv"]), plan.new_records)
        write_readarr_queue(Path(settings["readarr_csv"]), plan.new_records)
        write_audiobook_search_queue(
            Path(settings["audiobook_csv"]),
            plan.new_records,
            "https://audiobookbay.lu",
            language_roots=root_map,
        )
        write_registry(Path(settings["registry"]), read_registry_rows(Path(settings["registry"])), plan.new_records)
        return {"ok": True, "plan": plan.summary(registry_updated=True)}

    def _audiobook_search(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = _load_settings(self.settings_path)
        queue_csv = Path(str(payload.get("queue_csv") or settings["audiobook_csv"]))
        if not queue_csv.exists():
            raise ValueError("Run ingest before audiobook candidate search.")
        rows = read_search_queue(queue_csv)
        matches = search_candidates(
            rows,
            torznab_url=settings["torznab_url"],
            api_key=settings.get("torznab_api_key", ""),
            limit_per_book=5,
        )
        write_matches(Path(settings["matches_csv"]), matches)
        return {
            "ok": True,
            "queue_rows": len(rows),
            "candidate_rows": len(matches),
            "matches_csv": settings["matches_csv"],
            "torznab_url": redact_endpoint(settings["torznab_url"]),
            "grabbed": 0,
        }

    def _candidate_decision(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = _load_settings(self.settings_path)
        action = str(payload.get("action") or "").strip().lower()
        if action not in {"approve", "reject"}:
            raise ValueError("Candidate action must be approve or reject.")
        row = update_match_decision(
            Path(settings["matches_csv"]),
            record_id=str(payload.get("record_id") or ""),
            candidate_url=str(payload.get("candidate_url") or ""),
            decision_status="approved" if action == "approve" else "rejected",
            notes=str(payload.get("notes") or ""),
        )
        return {"ok": True, "updated": row, "grabbed": 0}

    def _export_approved(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = _load_settings(self.settings_path)
        output = Path(str(payload.get("output") or settings["approved_export_csv"]))
        fmt = str(payload.get("format") or "csv")
        return export_approved_matches(Path(settings["matches_csv"]), output, output_format=fmt)

    def _test_connections(self) -> dict[str, Any]:
        settings = _load_settings(self.settings_path)
        return {"ok": True, "connections": test_connections(StackSettings.from_mapping(settings))}

    def _workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = _load_settings(self.settings_path)
        export_path = _require_uploaded_csv(payload.get("export_csv"))
        paths = WorkflowPaths(
            registry=Path(settings["registry"]),
            new_csv=Path(settings["new_csv"]),
            readarr_csv=Path(settings["readarr_csv"]),
            audiobook_csv=Path(settings["audiobook_csv"]),
            matches_csv=Path(settings["matches_csv"]),
            workflow_status_csv=Path(settings["workflow_state_csv"]),
            audiobook_root_map=Path(settings["audiobook_root_map"]) if settings.get("audiobook_root_map") else None,
            torznab_url=settings["torznab_url"],
            torznab_api_key=settings.get("torznab_api_key", ""),
        )
        return run_monitored_workflow(
            export_path,
            paths=paths,
            stack=StackSettings.from_mapping(settings),
            dry_run=bool(payload.get("dry_run", False)),
        )

    def _read_json(self) -> dict[str, Any]:
        size = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(size)
        return json.loads(body.decode("utf-8") or "{}")

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _load_settings(path: Path) -> dict[str, str]:
    settings = _default_settings()
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in DEFAULT_SETTINGS:
            if key in data:
                settings[key] = str(data[key])
    _normalize_data_paths(settings)
    return settings


def _default_settings() -> dict[str, str]:
    settings = dict(DEFAULT_SETTINGS)
    for setting_key, env_names in ENV_SETTING_MAP.items():
        for env_name in env_names:
            value = os.environ.get(env_name, "").strip()
            if value:
                settings[setting_key] = value
                break
    return settings


def _safe_settings(settings: dict[str, str]) -> dict[str, Any]:
    safe = {}
    for key, value in settings.items():
        if key in SECRET_FIELDS:
            safe[key] = ""
            safe[f"{key}_configured"] = bool(value)
        elif key.endswith("_url"):
            safe[key] = redact_endpoint(value)
        else:
            safe[key] = value
    return safe


def _normalize_data_paths(settings: dict[str, str]) -> None:
    if DATA_DIR == Path("data"):
        return
    for key in DATA_PATH_SETTINGS:
        value = settings.get(key, "").strip()
        if value == "data":
            settings[key] = str(DATA_DIR)
            continue
        if value.startswith("data/") or value.startswith("data\\"):
            settings[key] = str(DATA_DIR / value[5:])


def _require_uploaded_csv(value: object) -> Path:
    path = Path(str(value or ""))
    if not path.is_file():
        raise ValueError("Upload or select a BookBuddy CSV first.")
    return path


def _read_csv_preview(path: Path, *, limit: int) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))[:limit]


def _csv_value_counts(path: Path, field: str) -> dict[str, int]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        counts: dict[str, int] = {}
        for row in csv.DictReader(handle):
            value = row.get(field, "") or "unknown"
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _safe_filename(value: str) -> str:
    name = Path(value).name
    name = re.sub(r"[^A-Za-z0-9_. -]+", "-", name).strip(" .")
    if not name.lower().endswith(".csv"):
        name += ".csv"
    return name or "bookbuddy-upload.csv"


APP_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>BookBuddARR</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #071018;
      --rail: #0a1420;
      --panel: #101b27;
      --panel-2: #0d1722;
      --line: #273645;
      --line-soft: #1c2b39;
      --text: #e6edf4;
      --muted: #9aa8b6;
      --accent: #27c6d8;
      --accent-2: #3f7df6;
      --good: #68d36d;
      --warn: #f1a534;
      --bad: #ec6a6a;
      --radius: 6px;
      --font: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Arial, sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); font-family: var(--font); font-size: 14px; }
    button, input { font: inherit; }
    .app { min-height: 100vh; display: grid; grid-template-columns: 220px minmax(0, 1fr); }
    .sidebar { background: linear-gradient(180deg, #091520, #071018); border-right: 1px solid var(--line-soft); padding: 18px 10px; display: flex; flex-direction: column; gap: 22px; }
    .brand { display: flex; align-items: center; gap: 10px; padding: 0 10px 16px; border-bottom: 1px solid var(--line-soft); }
    .mark { width: 34px; height: 34px; border: 1px solid var(--accent); color: var(--accent); display: grid; place-items: center; border-radius: 4px; }
    .brand strong { font-size: 21px; letter-spacing: 0; }
    .brand span { color: var(--accent); }
    .nav { display: grid; gap: 6px; }
    .nav button { display: flex; align-items: center; gap: 12px; width: 100%; color: var(--muted); background: transparent; border: 0; border-radius: var(--radius); padding: 11px 14px; text-align: left; cursor: pointer; }
    .nav button.active, .nav button:hover { color: var(--text); background: #102a38; border-left: 3px solid var(--accent); }
    .system { margin-top: auto; border: 1px solid var(--line); border-radius: var(--radius); padding: 12px; color: var(--muted); display: grid; gap: 9px; }
    .system div { display: flex; justify-content: space-between; gap: 12px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--good); display: inline-block; margin-right: 6px; }
    .topbar { height: 52px; border-bottom: 1px solid var(--line-soft); display: flex; align-items: center; justify-content: space-between; padding: 0 18px; background: #0b1520; }
    .status { display: flex; align-items: center; gap: 12px; color: var(--muted); }
    .review { border: 1px solid #7454d8; color: #cfbfff; padding: 7px 12px; border-radius: 5px; font-weight: 600; font-size: 12px; }
    main { padding: 18px; max-width: 1180px; margin: 0 auto; }
    .title h1 { margin: 0; font-size: 22px; }
    .title p { margin: 6px 0 18px; color: var(--muted); }
    .workflow-strip { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
    .step { border: 1px solid var(--line); background: #0d1925; border-radius: var(--radius); padding: 12px; display: grid; gap: 5px; min-height: 78px; }
    .step strong { font-size: 13px; }
    .step span { color: var(--muted); }
    .step.ready { border-color: #2f7d5d; background: #0e211d; }
    .step.warn { border-color: #806228; background: #241d0e; }
    .grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; }
    .panel { background: linear-gradient(180deg, var(--panel), var(--panel-2)); border: 1px solid var(--line); border-radius: var(--radius); padding: 14px; }
    .panel h2 { margin: 0 0 14px; font-size: 16px; }
    .drop { border: 1px dashed #516271; background: #0d1a27; border-radius: var(--radius); min-height: 118px; display: grid; place-items: center; text-align: center; color: var(--muted); cursor: pointer; }
    .drop.has-file { border-color: #2f7d5d; background: #0e211d; }
    .drop strong { color: var(--text); display: block; font-size: 16px; margin-bottom: 4px; }
    .drop span { color: var(--accent); }
    .file-row { margin-top: 10px; color: var(--muted); display: flex; justify-content: space-between; gap: 12px; }
    .summary { margin-top: 14px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .metric { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--line-soft); }
    .metric strong { font-weight: 600; }
    .actions { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-top: 16px; }
    .actions button, .save { border: 1px solid #2c93b7; background: #102637; color: #75e7f3; border-radius: var(--radius); padding: 11px 10px; cursor: pointer; font-weight: 700; min-height: 44px; }
    .actions button.primary { border-color: #4d7efa; background: #17386f; color: #dbe8ff; }
    .actions button:disabled { opacity: .45; cursor: not-allowed; }
    #workflowBtn { grid-column: span 2; }
    .settings-panel { margin-top: 12px; }
    .settings-panel > summary { cursor: pointer; font-weight: 800; list-style: none; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .settings-panel > summary::-webkit-details-marker { display: none; }
    .settings-panel > summary::after { content: "Open"; color: var(--accent); font-size: 12px; }
    .settings-panel[open] > summary { margin-bottom: 14px; }
    .settings-panel[open] > summary::after { content: "Close"; }
    .mini-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 7px; }
    .mini-actions button { border: 1px solid #395a74; background: #102333; color: #d9edf7; border-radius: 4px; padding: 6px 8px; cursor: pointer; font-size: 12px; font-weight: 700; }
    .mini-actions button.approve { border-color: #3a894a; color: #bff5c5; }
    .mini-actions button.reject { border-color: #9b4c4c; color: #ffd0d0; }
    .form { display: grid; gap: 10px; }
    .field { display: grid; grid-template-columns: 150px 1fr; align-items: center; gap: 10px; }
    label { color: var(--text); font-weight: 600; font-size: 13px; }
    input { width: 100%; border: 1px solid #344757; background: #0c1620; color: var(--text); border-radius: 5px; padding: 9px 10px; outline: none; }
    input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(39,198,216,.12); }
    .divider { border-top: 1px solid var(--line-soft); margin: 4px 0; }
    .table-panel { margin-top: 12px; }
    .table-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
    .table-head input { max-width: 320px; }
    table { width: 100%; border-collapse: collapse; border: 1px solid var(--line-soft); }
    th, td { border-bottom: 1px solid var(--line-soft); padding: 9px 10px; text-align: left; vertical-align: top; }
    th { background: #13202d; color: #c9d5e1; font-size: 12px; text-transform: uppercase; letter-spacing: 0; }
    td { color: #d7e1eb; }
    .muted { color: var(--muted); }
    .pill { display: inline-flex; padding: 3px 8px; border: 1px solid #2f68b8; background: #102d58; color: #84b8ff; border-radius: 999px; font-size: 12px; }
    .pill.fr { border-color: #417c79; background: #113735; color: #74e5d9; }
    .pill.warn { border-color: #8f671e; background: #30240e; color: #f5be58; }
    .score { color: var(--good); font-weight: 700; }
    .log { margin-top: 12px; min-height: 42px; max-height: 260px; overflow: auto; border: 1px solid var(--line-soft); border-radius: var(--radius); padding: 10px; color: var(--muted); background: #09131d; white-space: pre-wrap; }
    .log.error { color: #ffd0d0; border-color: #7a3737; background: #211011; }
    .hidden { display: none; }
    @media (max-width: 980px) {
      .app { grid-template-columns: 1fr; }
      .sidebar { display: none; }
      .grid, .summary, .workflow-strip { grid-template-columns: 1fr; }
      .actions { grid-template-columns: 1fr 1fr; }
      #workflowBtn { grid-column: span 2; }
      .field { grid-template-columns: 1fr; }
      main { padding: 12px; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand"><div class="mark">BB</div><strong>Book<span>BuddARR</span></strong></div>
      <div class="nav">
        <button>Dashboard</button>
        <button class="active">Import</button>
        <button>Audiobooks</button>
        <button>Settings</button>
        <button>Activity</button>
      </div>
      <div class="system">
        <div><span>System</span><span><i class="dot"></i>Healthy</span></div>
        <div><span>Mode</span><span>Review</span></div>
        <div><span>Downloads</span><span>Gated</span></div>
      </div>
    </aside>
    <section>
      <div class="topbar"><div class="status"><span>localhost web UI</span><span>v0.1</span></div><div class="review">APPROVAL-GATED MODE</div></div>
      <main>
        <div class="title"><h1>Import / CSV Workflow</h1><p>Upload a BookBuddy CSV export, configure stack links, then run the monitored audiobook workflow.</p></div>
        <div class="workflow-strip">
          <div id="stackStep" class="step"><strong>Stack</strong><span>Not tested yet</span></div>
          <div id="csvStep" class="step"><strong>CSV</strong><span>No file selected</span></div>
          <div id="runStep" class="step"><strong>Workflow</strong><span>Waiting for CSV</span></div>
        </div>
        <div class="grid">
          <section class="panel">
            <h2>1. Upload BookBuddy CSV</h2>
            <div id="drop" class="drop"><div><strong>Drop BookBuddy CSV file here</strong><span>or click to browse</span></div></div>
            <input id="file" class="hidden" type="file" accept=".csv,text/csv" />
            <div class="file-row"><span id="fileName">No file uploaded</span><span id="filePath"></span></div>
            <div class="summary">
              <div>
                <h2>Plan Summary</h2>
                <div class="metric"><span>Input Rows</span><strong id="inputRows">-</strong></div>
                <div class="metric"><span>New Books</span><strong id="newBooks">-</strong></div>
                <div class="metric"><span>Known Books</span><strong id="knownBooks">-</strong></div>
                <div class="metric"><span>Duplicates</span><strong id="duplicates">-</strong></div>
              </div>
              <div>
                <h2>Language Split</h2>
                <div id="languageSplit" class="muted">No plan yet</div>
              </div>
            </div>
            <div class="actions">
              <button id="doctorBtn">Doctor</button>
              <button id="planBtn">Plan</button>
              <button id="ingestBtn" class="primary">Ingest</button>
              <button id="searchBtn">Audiobook Search</button>
              <button id="exportBtn">Export Approved</button>
              <button id="testBtn">Test Stack</button>
              <button id="workflowBtn" class="primary">Run Workflow</button>
            </div>
          </section>
          <details class="panel settings-panel">
            <summary>2. Stack and Import Settings</summary>
            <div class="form" id="settingsForm"></div>
            <button id="saveBtn" class="save">Save Settings</button>
          </details>
        </div>
        <section class="panel table-panel">
          <div class="table-head"><h2>3. Workflow Status</h2><span class="muted">pending, searching, grabbing, downloading, importing, complete, blocked, needs parts</span></div>
          <table>
            <thead><tr><th>Book</th><th>State</th><th>Candidate</th><th>Parts</th><th>Target</th><th>Details</th></tr></thead>
            <tbody id="workflowRows"><tr><td colspan="6" class="muted">No workflow rows yet.</td></tr></tbody>
          </table>
          <div id="log" class="log">Ready.</div>
        </section>
        <section class="panel table-panel">
          <div class="table-head"><h2>4. Candidate Review</h2><input id="filter" placeholder="Filter books, candidates, status..." /></div>
          <table>
            <thead><tr><th>Book</th><th>Language</th><th>Candidate</th><th>Score</th><th>Decision</th><th>Notes</th><th>Review</th></tr></thead>
            <tbody id="matches"><tr><td colspan="7" class="muted">No candidate review rows yet.</td></tr></tbody>
          </table>
        </section>
      </main>
    </section>
  </div>
  <script>
    const fields = [
      ["registry", "Registry Path", "text"],
      ["new_csv", "New CSV", "text"],
      ["readarr_csv", "Readarr CSV", "text"],
      ["audiobook_csv", "Audiobook Queue CSV", "text"],
      ["matches_csv", "Matches CSV", "text"],
      ["approved_export_csv", "Approved Export CSV", "text"],
      ["audiobook_root_map", "Root Map JSON", "text"],
      ["torznab_url", "Torznab URL", "text"],
      ["torznab_api_key", "Torznab API Key", "password"],
      ["prowlarr_url", "Prowlarr URL", "text"],
      ["prowlarr_api_key", "Prowlarr API Key", "password"],
      ["qbittorrent_url", "qBittorrent URL", "text"],
      ["qbittorrent_username", "qBittorrent User", "text"],
      ["qbittorrent_password", "qBittorrent Password", "password"],
      ["qbittorrent_category", "qBittorrent Category", "text"],
      ["sabnzbd_url", "SABnzbd URL", "text"],
      ["sabnzbd_api_key", "SABnzbd API Key", "password"],
      ["nzbget_url", "NZBGet URL", "text"],
      ["nzbget_username", "NZBGet User", "text"],
      ["nzbget_password", "NZBGet Password", "password"],
      ["audiobookshelf_url", "Audiobookshelf URL", "text"],
      ["audiobookshelf_api_key", "Audiobookshelf API Key", "password"],
      ["audiobookshelf_library_path", "ABS Library Path", "text"],
      ["audiobook_root_fr", "French Root", "text"],
      ["audiobook_root_en", "English Root", "text"],
      ["audiobook_root_unknown", "Unknown Root", "text"],
      ["download_mode", "Download Mode", "text"],
      ["import_mode", "Import Mode", "text"],
      ["workflow_state_csv", "Workflow Status CSV", "text"],
      ["activity_log", "Activity Log", "text"],
      ["candidate_score_threshold", "Auto Score Min", "text"],
      ["readarr_url", "Readarr URL", "text"],
      ["readarr_api_key", "Readarr API Key", "password"],
    ];
    let currentExport = "";
    let stackOk = false;
    let state = {};

    const $ = (id) => document.getElementById(id);
    const log = (message, kind = "info") => {
      $("log").classList.toggle("error", kind === "error");
      $("log").textContent = typeof message === "string" ? message : JSON.stringify(message, null, 2);
    };
    const post = async (url, body) => {
      const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || "Request failed");
      return data;
    };
    async function runAction(label, fn) {
      log(label + "...");
      setBusy(true);
      try {
        const data = await fn();
        log(data);
        await loadState();
        return data;
      } catch (error) {
        log(error.message || String(error), "error");
      } finally {
        setBusy(false);
        updateActionState();
      }
    }

    async function loadState() {
      state = await (await fetch("/api/state")).json();
      renderSettings(state.settings);
      renderMatches(state.matches || []);
      renderWorkflow(state.workflow || []);
      restoreLatestUpload();
      updateActionState();
      renderSteps();
    }

    function renderSettings(settings) {
      $("settingsForm").innerHTML = fields.map(([key, label, type]) => `
        <div class="field">
          <label for="${key}">${label}</label>
          <input id="${key}" type="${type}" value="${settings[key] || ""}" placeholder="${settings[key + "_configured"] ? "Configured; leave blank to keep" : ""}" />
        </div>
      `).join("") + '<div class="divider"></div>';
    }

    function settingsPayload() {
      const payload = {};
      for (const [key] of fields) payload[key] = $(key).value;
      return payload;
    }
    function restoreLatestUpload() {
      if (currentExport || !(state.uploads || []).length) return;
      currentExport = state.uploads[0];
      $("fileName").textContent = currentExport.split(/[\\/]/).pop();
      $("filePath").textContent = currentExport;
      $("drop").classList.add("has-file");
    }
    function setBusy(value) {
      document.querySelectorAll("button").forEach(button => button.disabled = value);
    }
    function updateActionState() {
      const hasCsv = Boolean(currentExport);
      for (const id of ["doctorBtn", "planBtn", "ingestBtn", "searchBtn", "workflowBtn"]) $(id).disabled = !hasCsv;
      $("exportBtn").disabled = !(state.approved_count > 0);
      $("saveBtn").disabled = false;
      $("testBtn").disabled = false;
    }
    function renderSteps() {
      const settings = state.settings || {};
      const stackConfigured = Boolean(settings.prowlarr_url && settings.qbittorrent_url && settings.audiobookshelf_library_path);
      const workflowSummary = state.workflow_summary || {};
      const workflowTotal = Object.values(workflowSummary).reduce((sum, value) => sum + Number(value || 0), 0);
      renderStep("stackStep", stackOk ? "ready" : (stackConfigured ? "warn" : ""), "Stack", stackOk ? "Connections passed" : (stackConfigured ? "Configured; run Test Stack" : "Configure Prowlarr, qBittorrent, Audiobookshelf"));
      renderStep("csvStep", currentExport ? "ready" : "", "CSV", currentExport ? currentExport.split(/[\\/]/).pop() : "No file selected");
      if (workflowTotal) {
        const summaryText = Object.entries(workflowSummary).map(([key, value]) => `${value} ${key}`).join(", ");
        const hasProblem = Boolean(workflowSummary.blocked || workflowSummary.needs_parts || workflowSummary.needs_review);
        renderStep("runStep", hasProblem ? "warn" : "ready", "Workflow", summaryText);
      } else {
        renderStep("runStep", currentExport && stackConfigured ? "ready" : "", "Workflow", currentExport && stackConfigured ? "Ready to run" : "Waiting for CSV and stack");
      }
    }
    function renderStep(id, cls, title, text) {
      const node = $(id);
      node.className = `step ${cls}`.trim();
      node.innerHTML = `<strong>${esc(title)}</strong><span>${esc(text)}</span>`;
    }

    function renderPlan(plan) {
      $("inputRows").textContent = plan.input_rows ?? "-";
      $("newBooks").textContent = plan.new_records ?? "-";
      $("knownBooks").textContent = plan.known_records_in_export ?? "-";
      $("duplicates").textContent = plan.duplicates_in_export ?? "-";
      const split = plan.language_split || {};
      $("languageSplit").innerHTML = Object.keys(split).length ? Object.entries(split).map(([k, v]) => `<div class="metric"><span>${k}</span><strong>${v}</strong></div>`).join("") : "No language data";
    }

    function renderMatches(rows) {
      const query = ($("filter").value || "").toLowerCase();
      const visible = rows.filter(row => JSON.stringify(row).toLowerCase().includes(query));
      $("matches").innerHTML = visible.length ? visible.map(row => {
        const lang = row.book_language_code || "unknown";
        const cls = lang === "fr" ? "fr" : (row.decision_status === "language_mismatch" ? "warn" : "");
        return `<tr>
          <td><strong>${esc(row.book_title || "")}</strong><br><span class="muted">${esc(row.book_author || "")}</span></td>
          <td><span class="pill ${cls}">${esc(lang)}</span></td>
          <td>${esc(row.candidate_title || "")}<br><span class="muted">${esc(row.candidate_language || "")}</span></td>
          <td class="score">${esc(row.score || "")}</td>
          <td>${esc(row.decision_status || "")}</td>
          <td>${esc(row.notes || "")}</td>
          <td><div class="mini-actions">
            <button class="approve" data-action="approve" data-record="${escAttr(row.record_id || "")}" data-url="${escAttr(row.candidate_url || "")}">Approve</button>
            <button class="reject" data-action="reject" data-record="${escAttr(row.record_id || "")}" data-url="${escAttr(row.candidate_url || "")}">Reject</button>
          </div></td>
        </tr>`;
      }).join("") : '<tr><td colspan="7" class="muted">No candidate review rows yet.</td></tr>';
      document.querySelectorAll("[data-action]").forEach(button => button.onclick = () => reviewCandidate(button.dataset.action, button.dataset.record, button.dataset.url));
    }

    function renderWorkflow(rows) {
      $("workflowRows").innerHTML = rows.length ? rows.map(row => `
        <tr>
          <td><strong>${esc(row.book_title || "")}</strong><br><span class="muted">${esc(row.book_author || "")}</span></td>
          <td><span class="pill ${row.state === "blocked" || row.state === "needs_parts" ? "warn" : ""}">${esc(row.state || "")}</span></td>
          <td>${esc(row.candidate_title || "")}</td>
          <td>${esc([row.parts_found, row.parts_missing].filter(Boolean).join(" / "))}</td>
          <td>${esc(row.target_path || "")}</td>
          <td>${esc(row.details || "")}</td>
        </tr>
      `).join("") : '<tr><td colspan="6" class="muted">No workflow rows yet.</td></tr>';
    }

    function esc(value) {
      return String(value).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
    }
    function escAttr(value) { return esc(value).replace(/`/g, "&#96;"); }

    $("drop").onclick = () => $("file").click();
    $("drop").ondragover = (event) => { event.preventDefault(); };
    $("drop").ondrop = (event) => { event.preventDefault(); uploadFile(event.dataTransfer.files[0]); };
    $("file").onchange = (event) => uploadFile(event.target.files[0]);
    async function uploadFile(file) {
      if (!file) return;
      const content = await file.text();
      const data = await post("/api/upload", { filename: file.name, content });
      currentExport = data.path;
      $("fileName").textContent = file.name;
      $("filePath").textContent = data.path;
      $("drop").classList.add("has-file");
      log("Uploaded and validated header.");
      updateActionState();
      renderSteps();
    }

    $("saveBtn").onclick = async () => runAction("Saving settings", async () => {
      const data = await post("/api/settings", settingsPayload());
      renderSettings(data.settings);
      return { ok: true, message: "Settings saved." };
    });
    $("doctorBtn").onclick = async () => runAction("Checking CSV", () => post("/api/doctor", { export_csv: currentExport }));
    $("planBtn").onclick = async () => runAction("Planning import", async () => {
      const data = await post("/api/plan", { export_csv: currentExport });
      renderPlan(data.plan);
      return data.plan;
    });
    $("ingestBtn").onclick = async () => runAction("Ingesting CSV", async () => {
      const data = await post("/api/ingest", { export_csv: currentExport });
      renderPlan(data.plan);
      return data.plan;
    });
    $("searchBtn").onclick = async () => runAction("Searching audiobook candidates", () => post("/api/audiobook-search", {}));
    $("exportBtn").onclick = async () => runAction("Exporting approved candidates", () => post("/api/export-approved", { output: $("approved_export_csv").value, format: "csv" }));
    $("testBtn").onclick = async () => runAction("Testing stack connections", async () => {
      const data = await post("/api/test-connections", {});
      stackOk = data.ok && Object.values(data.connections || {}).filter(item => item.configured && !item.optional).every(item => item.ok);
      renderSteps();
      return data;
    });
    $("workflowBtn").onclick = async () => runAction("Running monitored workflow", () => post("/api/workflow", { export_csv: currentExport }));
    async function reviewCandidate(action, record_id, candidate_url) {
      const notes = prompt(action === "approve" ? "Approval notes" : "Rejection notes", "") || "";
      const data = await post("/api/candidate-decision", { action, record_id, candidate_url, notes });
      log(data);
      await loadState();
    }
    $("filter").oninput = () => renderMatches(state.matches || []);
    loadState().catch(error => log(error.message));
  </script>
</body>
</html>
"""
