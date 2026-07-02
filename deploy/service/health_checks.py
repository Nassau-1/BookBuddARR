#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run BookBuddARR Service health checks without printing secrets.")
    parser.add_argument("--env-file", type=Path, default=Path("/srv/media-stack/compose/bookbuddarr-torznab.env"))
    parser.add_argument("--bridge-url")
    parser.add_argument("--bridge-api-key")
    parser.add_argument("--prowlarr-url")
    parser.add_argument("--prowlarr-api-key")
    parser.add_argument("--readarr-url")
    parser.add_argument("--readarr-api-key")
    parser.add_argument("--indexer-name")
    args = parser.parse_args(argv)

    env = load_env_file(args.env_file)
    config = {
        "bridge_url": args.bridge_url or env.get("BOOKBUDDARR_TORZNAB_URL") or "http://127.0.0.1:8765/api",
        "bridge_api_key": args.bridge_api_key
        or env.get("BOOKBUDDARR_TORZNAB_API_KEY")
        or os.environ.get("BOOKBUDDARR_TORZNAB_API_KEY", ""),
        "prowlarr_url": args.prowlarr_url or env.get("PROWLARR_URL") or os.environ.get("PROWLARR_URL", ""),
        "prowlarr_api_key": args.prowlarr_api_key or env.get("PROWLARR_API_KEY") or os.environ.get("PROWLARR_API_KEY", ""),
        "readarr_url": args.readarr_url or env.get("READARR_URL") or os.environ.get("READARR_URL", ""),
        "readarr_api_key": args.readarr_api_key or env.get("READARR_API_KEY") or os.environ.get("READARR_API_KEY", ""),
        "indexer_name": args.indexer_name or env.get("PROWLARR_INDEXER_NAME") or "AudioBookBay Bridge",
    }
    checks = [
        bridge_caps_without_key(config["bridge_url"]),
        bridge_caps_with_key(config["bridge_url"], config["bridge_api_key"]),
    ]
    if config["prowlarr_url"] and config["prowlarr_api_key"]:
        checks.append(arr_indexer_visibility("prowlarr", config["prowlarr_url"], config["prowlarr_api_key"], config["indexer_name"]))
    if config["readarr_url"] and config["readarr_api_key"]:
        checks.append(arr_indexer_visibility("readarr", config["readarr_url"], config["readarr_api_key"], config["indexer_name"]))
    ok = all(check["ok"] for check in checks)
    print(json.dumps({"ok": ok, "checks": checks}, indent=2))
    return 0 if ok else 1


def bridge_caps_without_key(base_url: str) -> dict[str, Any]:
    status, _ = get_url(endpoint(base_url, {"t": "caps"}))
    return {
        "name": "bridge_caps_without_key",
        "url": redact_url(base_url),
        "expected": 401,
        "status": status,
        "ok": status == 401,
    }


def bridge_caps_with_key(base_url: str, api_key: str) -> dict[str, Any]:
    if not api_key:
        return {"name": "bridge_caps_with_key", "url": redact_url(base_url), "ok": False, "error": "missing bridge API key"}
    status, body = get_url(endpoint(base_url, {"t": "caps", "apikey": api_key}))
    return {
        "name": "bridge_caps_with_key",
        "url": redact_url(base_url),
        "expected": 200,
        "status": status,
        "ok": status == 200 and b"<caps>" in body,
    }


def arr_indexer_visibility(kind: str, base_url: str, api_key: str, indexer_name: str) -> dict[str, Any]:
    status, body = get_url(base_url.rstrip("/") + "/api/v1/indexer", api_key=api_key)
    if status != 200:
        return {"name": f"{kind}_indexer_visibility", "url": redact_url(base_url), "status": status, "ok": False}
    try:
        indexers = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return {"name": f"{kind}_indexer_visibility", "url": redact_url(base_url), "status": status, "ok": False}
    names = [str(indexer.get("name", "")) for indexer in indexers]
    visible = any(indexer_name.casefold() in name.casefold() for name in names)
    return {
        "name": f"{kind}_indexer_visibility",
        "url": redact_url(base_url),
        "indexer_name": indexer_name,
        "visible": visible,
        "ok": visible,
    }


def get_url(url: str, *, api_key: str = "", timeout: int = 15) -> tuple[int, bytes]:
    headers = {"X-Api-Key": api_key} if api_key else {}
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()
    except URLError as exc:
        return 0, str(exc).encode("utf-8")


def endpoint(base_url: str, params: dict[str, str]) -> str:
    separator = "&" if "?" in base_url else "?"
    return base_url + separator + urlencode(params)


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        env[key.strip()] = value.strip().strip("'\"")
    return env


def redact_url(value: str) -> str:
    if not value:
        return ""
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return value.split("?", 1)[0]
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


if __name__ == "__main__":
    raise SystemExit(main())
