#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


SECRET_KEYS = {"apiKey", "apikey", "api_key", "PROWLARR_API_KEY", "BOOKBUDDARR_TORZNAB_API_KEY"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or update a Prowlarr Generic Torznab indexer for BookBuddARR.")
    parser.add_argument("--env-file", type=Path, default=Path("/srv/media-stack/compose/bookbuddarr-torznab.env"))
    parser.add_argument("--apply", action="store_true", help="Actually create or update the Prowlarr indexer.")
    parser.add_argument("--prowlarr-url")
    parser.add_argument("--prowlarr-api-key")
    parser.add_argument("--indexer-name")
    parser.add_argument("--torznab-url")
    parser.add_argument("--torznab-api-key")
    args = parser.parse_args(argv)

    env = load_env_file(args.env_file)
    config = {
        "prowlarr_url": args.prowlarr_url or env.get("PROWLARR_URL") or os.environ.get("PROWLARR_URL", ""),
        "prowlarr_api_key": args.prowlarr_api_key or env.get("PROWLARR_API_KEY") or os.environ.get("PROWLARR_API_KEY", ""),
        "indexer_name": args.indexer_name or env.get("PROWLARR_INDEXER_NAME") or "AudioBookBay Bridge",
        "torznab_url": args.torznab_url or env.get("BOOKBUDDARR_TORZNAB_URL") or "http://bookbuddarr-torznab:8765/api",
        "torznab_api_key": args.torznab_api_key
        or env.get("BOOKBUDDARR_TORZNAB_API_KEY")
        or os.environ.get("BOOKBUDDARR_TORZNAB_API_KEY", ""),
    }
    missing = [key for key, value in config.items() if key.endswith("url") is False and key.endswith("name") is False and not value]
    if not config["prowlarr_url"]:
        missing.append("prowlarr_url")
    if missing:
        print(json.dumps({"ok": False, "error": f"Missing required config: {', '.join(sorted(set(missing)))}"}, indent=2))
        return 2

    client = ProwlarrClient(config["prowlarr_url"], config["prowlarr_api_key"])
    schemas = client.get("/api/v1/indexer/schema")
    schema = find_generic_torznab_schema(schemas)
    existing = find_existing_indexer(client.get("/api/v1/indexer"), config["indexer_name"])
    payload = build_indexer_payload(schema, config)
    action = "update" if existing else "create"

    result: dict[str, Any] = {
        "ok": True,
        "mode": "apply" if args.apply else "dry_run",
        "action": action,
        "indexer_name": config["indexer_name"],
        "prowlarr_url": redact_url(config["prowlarr_url"]),
        "torznab_url": redact_url(config["torznab_url"]),
        "payload_preview": redact(payload),
    }
    if not args.apply:
        print(json.dumps(result, indent=2))
        return 0

    if existing:
        payload["id"] = existing["id"]
        response = client.put(f"/api/v1/indexer/{existing['id']}", payload)
    else:
        response = client.post("/api/v1/indexer", payload)
    result["response"] = redact(response)
    print(json.dumps(result, indent=2))
    return 0


class ProwlarrClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("POST", path, payload)

    def put(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("PUT", path, payload)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={
                "X-Api-Key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"Prowlarr API {method} {path} failed with {exc.code}: {detail}") from exc
        except URLError as exc:
            raise SystemExit(f"Prowlarr API {method} {path} failed: {exc.reason}") from exc
        return json.loads(data) if data else {}


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


def find_generic_torznab_schema(schemas: list[dict[str, Any]]) -> dict[str, Any]:
    for schema in schemas:
        haystack = " ".join(str(schema.get(key, "")) for key in ["name", "implementation", "configContract"]).lower()
        if "torznab" in haystack and ("generic" in haystack or schema.get("implementation") == "Torznab"):
            return schema
    raise SystemExit("Could not find a Generic Torznab schema in Prowlarr.")


def find_existing_indexer(indexers: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for indexer in indexers:
        if str(indexer.get("name", "")).casefold() == name.casefold():
            return indexer
    return None


def build_indexer_payload(schema: dict[str, Any], config: dict[str, str]) -> dict[str, Any]:
    payload = json.loads(json.dumps(schema))
    base_url, api_path = split_torznab_url(config["torznab_url"])
    payload["name"] = config["indexer_name"]
    payload["enable"] = True
    payload["priority"] = payload.get("priority") or 25
    payload["protocol"] = payload.get("protocol") or "torrent"
    payload["appProfileId"] = payload.get("appProfileId") or 1
    set_field(payload, ["baseUrl", "base_url", "url"], base_url)
    set_field(payload, ["apiPath", "api_path"], api_path)
    set_field(payload, ["apiKey", "apikey", "api_key"], config["torznab_api_key"])
    set_field(payload, ["categories"], [3030])
    return payload


def split_torznab_url(value: str) -> tuple[str, str]:
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    path = parsed.path.rstrip("/") or "/api"
    if path.endswith("/api"):
        base_path = path[: -len("/api")]
        base_url = urlunsplit((parsed.scheme, host, base_path, "", ""))
        return base_url.rstrip("/"), "/api"
    base_url = urlunsplit((parsed.scheme, host, path, "", "")) if parsed.scheme and host else value.split("?", 1)[0]
    return base_url.rstrip("/"), "/api"


def set_field(payload: dict[str, Any], names: list[str], value: Any) -> None:
    for field in payload.get("fields", []):
        if field.get("name") in names:
            field["value"] = value


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        if value.get("name") in SECRET_KEYS and "value" in value:
            out = dict(value)
            out["value"] = "***redacted***" if out["value"] else ""
            return out
        out = {}
        for key, item in value.items():
            if key in SECRET_KEYS or "key" in key.lower() or "password" in key.lower():
                out[key] = "***redacted***" if item else ""
            elif key.lower().endswith("url"):
                out[key] = redact_url(str(item))
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


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
