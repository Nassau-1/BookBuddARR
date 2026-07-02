from __future__ import annotations

import json
import os
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import redact_endpoint, redact_structure


@dataclass(frozen=True)
class StackSettings:
    prowlarr_url: str = ""
    prowlarr_api_key: str = ""
    qbittorrent_url: str = ""
    qbittorrent_username: str = ""
    qbittorrent_password: str = ""
    qbittorrent_category: str = "audiobooks"
    sabnzbd_url: str = ""
    sabnzbd_api_key: str = ""
    nzbget_url: str = ""
    nzbget_username: str = ""
    nzbget_password: str = ""
    audiobookshelf_url: str = ""
    audiobookshelf_api_key: str = ""
    audiobookshelf_library_path: str = ""
    audiobook_root_fr: str = "/Data/Audiobooks/Francais"
    audiobook_root_en: str = "/Data/Audiobooks/English"
    audiobook_root_unknown: str = "/Data/Audiobooks"
    download_mode: str = "approved_only"
    import_mode: str = "copy"
    workflow_state_csv: str = "data/workflow_status.csv"
    activity_log: str = "data/workflow_activity.jsonl"
    candidate_score_threshold: int = 85

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None = None) -> "StackSettings":
        values = {field: getattr(cls(), field) for field in cls.__dataclass_fields__}
        env_map = {
            "prowlarr_url": "PROWLARR_URL",
            "prowlarr_api_key": "PROWLARR_API_KEY",
            "qbittorrent_url": "QBITTORRENT_URL",
            "qbittorrent_username": "QBITTORRENT_USERNAME",
            "qbittorrent_password": "QBITTORRENT_PASSWORD",
            "qbittorrent_category": "QBITTORRENT_CATEGORY",
            "sabnzbd_url": "SABNZBD_URL",
            "sabnzbd_api_key": "SABNZBD_API_KEY",
            "nzbget_url": "NZBGET_URL",
            "nzbget_username": "NZBGET_USERNAME",
            "nzbget_password": "NZBGET_PASSWORD",
            "audiobookshelf_url": "AUDIOBOOKSHELF_URL",
            "audiobookshelf_api_key": "AUDIOBOOKSHELF_API_KEY",
            "audiobookshelf_library_path": "AUDIOBOOKSHELF_LIBRARY_PATH",
            "audiobook_root_fr": "AUDIOBOOK_ROOT_FR",
            "audiobook_root_en": "AUDIOBOOK_ROOT_EN",
            "audiobook_root_unknown": "AUDIOBOOK_ROOT_UNKNOWN",
            "download_mode": "BOOKBUDDARR_DOWNLOAD_MODE",
            "import_mode": "BOOKBUDDARR_IMPORT_MODE",
            "workflow_state_csv": "BOOKBUDDARR_WORKFLOW_STATE_CSV",
            "activity_log": "BOOKBUDDARR_ACTIVITY_LOG",
            "candidate_score_threshold": "BOOKBUDDARR_CANDIDATE_SCORE_THRESHOLD",
        }
        for key, env_name in env_map.items():
            value = os.environ.get(env_name, "").strip()
            if value:
                values[key] = value
        for key, value in (data or {}).items():
            if key in values and value not in (None, ""):
                values[key] = value
        values["candidate_score_threshold"] = int(values["candidate_score_threshold"])
        return cls(**values)

    def root_for_language(self, language_code: str) -> str:
        if language_code == "fr":
            return self.audiobook_root_fr
        if language_code == "en":
            return self.audiobook_root_en
        return self.audiobook_root_unknown

    def safe_summary(self) -> dict[str, Any]:
        return redact_structure(self.__dict__)


def test_connections(settings: StackSettings, *, timeout: int = 10) -> dict[str, dict[str, Any]]:
    return {
        "prowlarr": _test_prowlarr(settings, timeout=timeout),
        "qbittorrent": _test_qbittorrent(settings, timeout=timeout),
        "sabnzbd": _test_sabnzbd(settings, timeout=timeout),
        "nzbget": _test_nzbget(settings, timeout=timeout),
        "audiobookshelf": _test_audiobookshelf(settings, timeout=timeout),
    }


def prowlarr_search(settings: StackSettings, query: str, *, timeout: int = 30) -> list[dict[str, Any]]:
    if not settings.prowlarr_url or not settings.prowlarr_api_key:
        raise ValueError("Prowlarr URL and API key are required for aggregate search.")
    params = urllib.parse.urlencode({"query": query, "categories": "3030"})
    url = _api_url(settings.prowlarr_url, f"/api/v1/search?{params}")
    payload = _json_request(url, api_key=settings.prowlarr_api_key, timeout=timeout)
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def prowlarr_grab(settings: StackSettings, release: dict[str, Any], *, timeout: int = 30, dry_run: bool = False) -> dict[str, Any]:
    guid = str(release.get("guid") or release.get("downloadUrl") or release.get("infoUrl") or "").strip()
    indexer_id = release.get("indexerId") or release.get("indexer_id")
    if not guid or indexer_id in (None, ""):
        return {"ok": False, "state": "blocked", "reason": "missing_prowlarr_grab_metadata"}
    if dry_run:
        return {"ok": True, "state": "grab_preview", "guid": guid, "indexerId": indexer_id}
    params = urllib.parse.urlencode({"guid": guid, "indexerId": indexer_id})
    url = _api_url(settings.prowlarr_url, f"/api/v1/search?{params}")
    try:
        payload = _json_request(url, api_key=settings.prowlarr_api_key, method="POST", data=b"{}", timeout=timeout)
        return {"ok": True, "state": "grabbed", "response": redact_structure(payload)}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "state": "blocked", "status": exc.code, "reason": _safe_http_error(exc)}


def qbit_torrents(settings: StackSettings, *, timeout: int = 15) -> list[dict[str, Any]]:
    opener = _qbit_opener(settings, timeout=timeout)
    params = {"category": settings.qbittorrent_category} if settings.qbittorrent_category else {}
    url = _api_url(settings.qbittorrent_url, "/api/v2/torrents/info")
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with opener.open(urllib.request.Request(url), timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, list) else []


def find_completed_download(settings: StackSettings, title: str, *, timeout: int = 15) -> dict[str, Any] | None:
    title_key = _norm(title)
    for item in qbit_torrents(settings, timeout=timeout):
        name = str(item.get("name") or "")
        state = str(item.get("state") or "")
        progress = float(item.get("progress") or 0)
        if title_key and title_key not in _norm(name):
            continue
        if progress >= 1 or state.lower().startswith(("upload", "stalledup", "pausedup")):
            return item
    return None


def import_download(source_path: Path, target_root: Path, book_title: str, *, mode: str = "copy") -> dict[str, Any]:
    if mode == "none":
        return {"ok": True, "state": "import_skipped", "target": str(target_root)}
    if not source_path.exists():
        return {"ok": False, "state": "blocked", "reason": "download_path_missing", "source_path": str(source_path)}
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / _safe_folder_name(book_title)
    if source_path.is_dir():
        if target.exists():
            shutil.rmtree(target)
        if mode == "move":
            shutil.move(str(source_path), str(target))
        else:
            shutil.copytree(source_path, target)
    else:
        target.mkdir(parents=True, exist_ok=True)
        destination = target / source_path.name
        if mode == "move":
            shutil.move(str(source_path), str(destination))
        else:
            shutil.copy2(source_path, destination)
    return {"ok": True, "state": "imported", "target": str(target), "files": _count_files(target)}


def import_download_group(source_paths: list[Path], target_root: Path, book_title: str, *, mode: str = "copy") -> dict[str, Any]:
    if mode == "none":
        return {"ok": True, "state": "import_skipped", "target": str(target_root)}
    missing = [str(path) for path in source_paths if not path.exists()]
    if missing:
        return {"ok": False, "state": "blocked", "reason": "download_path_missing", "missing": missing}
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / _safe_folder_name(book_title)
    target.mkdir(parents=True, exist_ok=True)
    for source_path in source_paths:
        if source_path.is_dir():
            destination = target / _safe_folder_name(source_path.name)
            if destination.exists():
                shutil.rmtree(destination)
            if mode == "move":
                shutil.move(str(source_path), str(destination))
            else:
                shutil.copytree(source_path, destination)
        else:
            destination = target / source_path.name
            if mode == "move":
                shutil.move(str(source_path), str(destination))
            else:
                shutil.copy2(source_path, destination)
    return {"ok": True, "state": "imported_group", "target": str(target), "files": _count_files(target)}


def verify_audiobookshelf_path(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "state": "blocked", "reason": "target_not_visible", "path": str(path)}
    return {"ok": True, "state": "verified", "path": str(path), "files": _count_files(path)}


def append_activity(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": int(time.time()), **redact_structure(event)}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _test_prowlarr(settings: StackSettings, *, timeout: int) -> dict[str, Any]:
    if not settings.prowlarr_url:
        return {"configured": False, "ok": False, "state": "not_configured"}
    try:
        payload = _json_request(_api_url(settings.prowlarr_url, "/api/v1/system/status"), api_key=settings.prowlarr_api_key, timeout=timeout)
        return {"configured": True, "ok": True, "state": "connected", "url": redact_endpoint(settings.prowlarr_url), "version": payload.get("version", "")}
    except Exception as exc:
        return {"configured": True, "ok": False, "state": "blocked", "url": redact_endpoint(settings.prowlarr_url), "error": _safe_error(exc)}


def _test_qbittorrent(settings: StackSettings, *, timeout: int) -> dict[str, Any]:
    if not settings.qbittorrent_url:
        return {"configured": False, "ok": False, "state": "not_configured"}
    try:
        opener = _qbit_opener(settings, timeout=timeout)
        with opener.open(urllib.request.Request(_api_url(settings.qbittorrent_url, "/api/v2/app/version")), timeout=timeout) as response:
            version = response.read().decode("utf-8").strip()
        return {"configured": True, "ok": True, "state": "connected", "url": redact_endpoint(settings.qbittorrent_url), "version": version}
    except Exception as exc:
        return {"configured": True, "ok": False, "state": "blocked", "url": redact_endpoint(settings.qbittorrent_url), "error": _safe_error(exc)}


def _test_sabnzbd(settings: StackSettings, *, timeout: int) -> dict[str, Any]:
    if not settings.sabnzbd_url:
        return {"configured": False, "ok": False, "state": "not_configured", "optional": True}
    params = urllib.parse.urlencode({"mode": "version", "output": "json", "apikey": settings.sabnzbd_api_key})
    try:
        payload = _json_request(_join_url(settings.sabnzbd_url, f"/api?{params}"), timeout=timeout)
        return {"configured": True, "ok": True, "state": "connected", "url": redact_endpoint(settings.sabnzbd_url), "version": payload.get("version", "")}
    except Exception as exc:
        return {"configured": True, "ok": False, "state": "blocked", "optional": True, "url": redact_endpoint(settings.sabnzbd_url), "error": _safe_error(exc)}


def _test_nzbget(settings: StackSettings, *, timeout: int) -> dict[str, Any]:
    if not settings.nzbget_url:
        return {"configured": False, "ok": False, "state": "not_configured", "optional": True}
    return {"configured": True, "ok": False, "state": "todo", "optional": True, "url": redact_endpoint(settings.nzbget_url)}


def _test_audiobookshelf(settings: StackSettings, *, timeout: int) -> dict[str, Any]:
    if settings.audiobookshelf_library_path:
        path = Path(settings.audiobookshelf_library_path)
        return {"configured": True, **verify_audiobookshelf_path(path)}
    if not settings.audiobookshelf_url:
        return {"configured": False, "ok": False, "state": "not_configured"}
    headers = {"Authorization": f"Bearer {settings.audiobookshelf_api_key}"} if settings.audiobookshelf_api_key else {}
    try:
        _json_request(_join_url(settings.audiobookshelf_url, "/api/libraries"), headers=headers, timeout=timeout)
        return {"configured": True, "ok": True, "state": "connected", "url": redact_endpoint(settings.audiobookshelf_url)}
    except Exception as exc:
        return {"configured": True, "ok": False, "state": "blocked", "url": redact_endpoint(settings.audiobookshelf_url), "error": _safe_error(exc)}


def _json_request(url: str, *, api_key: str = "", headers: dict[str, str] | None = None, method: str = "GET", data: bytes | None = None, timeout: int = 15) -> Any:
    request_headers = {"User-Agent": "BookBuddARR/0.1"}
    if api_key:
        request_headers["X-Api-Key"] = api_key
    request_headers.update(headers or {})
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body.strip() else {}


def _qbit_opener(settings: StackSettings, *, timeout: int) -> urllib.request.OpenerDirector:
    if not settings.qbittorrent_url:
        raise ValueError("qBittorrent URL is not configured.")
    jar = urllib.request.HTTPCookieProcessor()
    opener = urllib.request.build_opener(jar)
    if settings.qbittorrent_username or settings.qbittorrent_password:
        login_url = _api_url(settings.qbittorrent_url, "/api/v2/auth/login")
        data = urllib.parse.urlencode({"username": settings.qbittorrent_username, "password": settings.qbittorrent_password}).encode("utf-8")
        request = urllib.request.Request(login_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with opener.open(request, timeout=timeout) as response:
            if response.read().decode("utf-8").strip().lower() != "ok.":
                raise ValueError("qBittorrent authentication failed.")
    return opener


def _api_url(base_url: str, path: str) -> str:
    return _join_url(base_url, path)


def _join_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _safe_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read(300).decode("utf-8", errors="replace")
    except Exception:
        return exc.reason if isinstance(exc.reason, str) else "http_error"


def _safe_error(exc: Exception) -> str:
    text = str(exc)
    text = re.sub(r"([?&](?:apikey|api_key|token|password|pass)=)[^&\s'\"]+", r"\1***redacted***", text, flags=re.I)
    text = re.sub(r"(https?://)[^:/\s'\"]+:[^@\s'\"]+@", r"\1***redacted***@", text, flags=re.I)
    return text


def _safe_folder_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in " ._-" else "-" for ch in value).strip(" .")
    return cleaned or "Audiobook"


def _count_files(path: Path) -> int:
    if path.is_file():
        return 1
    return sum(1 for item in path.rglob("*") if item.is_file())


def _norm(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").replace("-", " ").split())
