from __future__ import annotations

import os
from typing import Any
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


OPTIONAL_ENDPOINT_VARS = [
    "READARR_URL",
    "PROWLARR_URL",
    "QBITTORRENT_URL",
    "SABNZBD_URL",
    "NZBGET_URL",
    "AUDIOBOOKSHELF_URL",
    "TORZNAB_URL",
    "AUDIOBOOK_SEARCH_BASE_URL",
]

SECRET_NAME_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASS")


def load_dotenv(path: Path = Path(".env")) -> dict[str, str]:
    if not path.exists():
        return {}
    loaded: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, value = _parse_env_line(line)
        if not key:
            continue
        if key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


def endpoint_status() -> dict[str, dict[str, str | bool]]:
    return {
        name: {
            "configured": bool(os.environ.get(name, "").strip()),
            "value": redact_endpoint(os.environ.get(name, "").strip()),
        }
        for name in OPTIONAL_ENDPOINT_VARS
    }


def safe_env_summary(loaded: dict[str, str]) -> dict[str, object]:
    return {
        "loaded_names": sorted(loaded),
        "loaded_secret_names": sorted(name for name in loaded if is_secret_name(name)),
    }


def is_secret_name(name: str) -> bool:
    upper = name.upper()
    return any(marker in upper for marker in SECRET_NAME_MARKERS)


def redact_value(name: str, value: object) -> object:
    if value is None:
        return None
    if is_secret_name(name):
        return "***redacted***" if str(value) else ""
    if name.lower().endswith("_url") or "url" in name.lower():
        return redact_endpoint(str(value))
    return value


def redact_structure(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: redact_value(str(key), redact_structure(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_structure(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_structure(item) for item in value)
    return value


def redact_endpoint(value: str) -> str:
    if not value:
        return ""
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return value.split("?", 1)[0]
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def _parse_env_line(line: str) -> tuple[str, str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return "", ""
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return "", ""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value
