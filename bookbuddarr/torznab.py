from __future__ import annotations

import argparse
import html
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterable
from xml.etree.ElementTree import Element, SubElement, register_namespace, tostring


USER_AGENT = "BookBuddARR-Torznab/0.1 (+https://github.com/Nassau-1/BookBuddARR)"
TORZNAB_NS = "http://torznab.com/schemas/2015/feed"
register_namespace("torznab", TORZNAB_NS)


@dataclass(frozen=True)
class AbbResult:
    title: str
    detail_url: str
    cover_url: str
    language: str
    post_date: str
    book_format: str
    bitrate: str
    file_size: str


class AudioBookBayClient:
    def __init__(self, hostname: str = "audiobookbay.lu", page_limit: int = 2, timeout: int = 15):
        self.hostname = hostname
        self.page_limit = page_limit
        self.timeout = timeout

    def search(self, query: str) -> list[AbbResult]:
        results: list[AbbResult] = []
        for page in range(1, self.page_limit + 1):
            url = f"https://{self.hostname}/page/{page}/?s={urllib.parse.quote_plus(query)}"
            try:
                body = self._get_text(url)
            except urllib.error.URLError:
                break
            posts = re.findall(r'<div[^>]+class="[^"]*post[^"]*"[^>]*>(.*?)</div>\s*</div>', body, flags=re.I | re.S)
            if not posts:
                posts = body.split('<div class="post"')[1:]
            if not posts:
                break
            for post in posts:
                result = self._parse_post(post)
                if result:
                    results.append(result)
        return _dedupe_results(results)

    def magnet(self, detail_url: str) -> str | None:
        body = self._get_text(detail_url)
        info_hash = _first_match(body, r"<td[^>]*>\s*Info Hash\s*</td>\s*<td[^>]*>([^<]+)</td>")
        if not info_hash:
            info_hash = _first_match(body, r"Info Hash.*?<td[^>]*>([A-Fa-f0-9]{32,40})</td>")
        if not info_hash:
            return None
        trackers = re.findall(r"<td[^>]*>\s*((?:udp|https?)://[^<]+)</td>", body, flags=re.I)
        query = urllib.parse.urlencode({"xt": f"urn:btih:{info_hash.strip()}"})
        for tracker in trackers:
            query += "&" + urllib.parse.urlencode({"tr": html.unescape(tracker.strip())})
        return "magnet:?" + query

    def _parse_post(self, post: str) -> AbbResult | None:
        link_match = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', post, flags=re.I | re.S)
        if not link_match:
            return None
        raw_link, raw_title = link_match.groups()
        title = _strip_tags(raw_title)
        if not title:
            return None
        detail_url = urllib.parse.urljoin(f"https://{self.hostname}", html.unescape(raw_link))
        cover_url = _first_match(post, r'<img[^>]+src="([^"]+)"') or ""
        info_text = _strip_tags(_first_match(post, r'<div[^>]+class="[^"]*postInfo[^"]*"[^>]*>(.*?)</div>') or "")
        language = _first_match(info_text, r"Language:\s*(.*?)(?:\s*Keywords:|$)") or ""
        centered = _first_match(post, r'<p[^>]+text-align:\s*center[^>]*>(.*?)</p>') or ""
        return AbbResult(
            title=title,
            detail_url=detail_url,
            cover_url=html.unescape(cover_url),
            language=language.strip(),
            post_date=_first_match(centered, r"Posted:\s*([^<]+)") or "",
            book_format=_first_match(centered, r"Format:\s*<span[^>]*>([^<]+)</span>") or "",
            bitrate=_first_match(centered, r"Bitrate:\s*<span[^>]*>([^<]+)</span>") or "",
            file_size=_parse_file_size(centered),
        )

    def _get_text(self, url: str) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read().decode("utf-8", errors="replace")


def render_caps() -> bytes:
    root = Element("caps")
    server = SubElement(root, "server")
    server.set("version", "0.1.0")
    server.set("title", "BookBuddARR AudioBookBay Torznab Bridge")
    searching = SubElement(root, "searching")
    for name in ["search", "book"]:
        item = SubElement(searching, name)
        item.set("available", "yes")
        item.set("supportedParams", "q")
    categories = SubElement(root, "categories")
    category = SubElement(categories, "category")
    category.set("id", "3030")
    category.set("name", "Audiobook")
    return _xml(root)


def render_rss(results: Iterable[AbbResult], self_url: str, query: str) -> bytes:
    rss = Element("rss")
    rss.set("version", "2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "BookBuddARR AudioBookBay"
    SubElement(channel, "description").text = f"AudioBookBay results for {query}"
    SubElement(channel, "link").text = self_url
    for result in results:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = result.title
        SubElement(item, "guid").text = result.detail_url
        SubElement(item, "link").text = _get_url(self_url, result.detail_url)
        SubElement(item, "comments").text = result.detail_url
        SubElement(item, "category").text = "Audiobook"
        if result.post_date:
            SubElement(item, "pubDate").text = result.post_date
        if result.file_size:
            size = parse_size_bytes(result.file_size)
            if size:
                enclosure = SubElement(item, "enclosure")
                enclosure.set("url", _get_url(self_url, result.detail_url))
                enclosure.set("length", str(size))
                enclosure.set("type", "application/x-bittorrent")
                attr = SubElement(item, f"{{{TORZNAB_NS}}}attr")
                attr.set("name", "size")
                attr.set("value", str(size))
        for name, value in [
            ("category", "3030"),
            ("language", result.language),
            ("format", result.book_format),
            ("bitrate", result.bitrate),
        ]:
            if value:
                attr = SubElement(item, f"{{{TORZNAB_NS}}}attr")
                attr.set("name", name)
                attr.set("value", value)
    return _xml(rss)


class TorznabHandler(BaseHTTPRequestHandler):
    client: AudioBookBayClient
    api_key: str

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if self.api_key and params.get("apikey", [""])[0] != self.api_key:
            self.send_error(401, "Unauthorized")
            return
        action = params.get("t", ["search"])[0]
        if action == "caps":
            self._send_xml(render_caps())
            return
        if action == "get":
            target = params.get("id", [""])[0]
            if not target:
                self.send_error(400, "Missing id")
                return
            magnet = self.client.magnet(target)
            if not magnet:
                self.send_error(404, "Magnet not found")
                return
            self.send_response(302)
            self.send_header("Location", magnet)
            self.end_headers()
            return
        query = params.get("q", [""])[0] or params.get("term", [""])[0]
        results = self.client.search(query) if query else []
        self._send_xml(render_rss(results, self._self_url(parsed.path), query))

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _self_url(self, path: str) -> str:
        host = self.headers.get("Host", "127.0.0.1")
        return f"http://{host}{path}"

    def _send_xml(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(args: argparse.Namespace) -> None:
    client = AudioBookBayClient(args.hostname, args.page_limit, args.timeout)
    handler = type(
        "ConfiguredTorznabHandler",
        (TorznabHandler,),
        {"client": client, "api_key": args.api_key},
    )
    server = ThreadingHTTPServer((args.bind, args.port), handler)
    print(f"BookBuddARR Torznab bridge listening on {args.bind}:{args.port}")
    server.serve_forever()


def parse_size_bytes(value: str) -> int:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?B)", value, flags=re.I)
    if not match:
        return 0
    number = float(match.group(1))
    unit = match.group(2).upper()
    factor = {"KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}.get(unit, 1)
    return int(number * factor)


def _get_url(base_url: str, detail_url: str) -> str:
    return f"{base_url}?t=get&id={urllib.parse.quote(detail_url, safe='')}"


def _xml(root: Element) -> bytes:
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding="utf-8")


def _dedupe_results(results: list[AbbResult]) -> list[AbbResult]:
    seen: set[str] = set()
    out: list[AbbResult] = []
    for result in results:
        if result.detail_url in seen:
            continue
        seen.add(result.detail_url)
        out.append(result)
    return out


def _first_match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.I | re.S)
    return html.unescape(match.group(1).strip()) if match else None


def _parse_file_size(text: str) -> str:
    match = re.search(r"File Size:\s*<span[^>]*>([^<]+)</span>\s*([^<]+)", text, flags=re.I)
    if not match:
        return ""
    return f"{match.group(1).strip()} {match.group(2).strip()}"


def _strip_tags(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", value)).strip()
