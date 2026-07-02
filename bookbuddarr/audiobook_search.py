from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
import urllib.request
from xml.etree import ElementTree

from .normalize import language_code, normalize_for_key


TORZNAB_NS = "{http://torznab.com/schemas/2015/feed}"

MATCH_FIELDS = [
    "record_id",
    "book_title",
    "book_author",
    "book_language_code",
    "search_query",
    "candidate_title",
    "candidate_language",
    "candidate_language_code",
    "candidate_url",
    "candidate_guid",
    "prowlarr_indexer_id",
    "download_protocol",
    "download_size",
    "score",
    "candidate_completeness_status",
    "candidate_completeness_notes",
    "decision_status",
    "notes",
]

APPROVED_EXPORT_FIELDS = [
    "record_id",
    "book_title",
    "book_author",
    "book_language_code",
    "search_query",
    "candidate_title",
    "candidate_language",
    "candidate_language_code",
    "candidate_url",
    "candidate_guid",
    "prowlarr_indexer_id",
    "download_protocol",
    "download_size",
    "score",
    "candidate_completeness_status",
    "candidate_completeness_notes",
    "decision_status",
    "notes",
]

MUTABLE_DECISION_STATUSES = {
    "pending_review",
    "approved",
    "rejected",
    "needs_language_review",
    "language_mismatch",
    "needs_completeness_review",
}


@dataclass(frozen=True)
class SearchQueueRow:
    record_id: str
    title: str
    author: str
    language_code: str
    query: str
    alternate_query: str
    language_policy: str


@dataclass(frozen=True)
class TorznabCandidate:
    title: str
    url: str
    language: str
    guid: str = ""
    prowlarr_indexer_id: str = ""
    protocol: str = ""
    size: str = ""


@dataclass(frozen=True)
class RankedCandidate:
    row: SearchQueueRow
    candidate: TorznabCandidate
    score: int
    decision_status: str
    completeness_status: str = "unknown"
    completeness_notes: str = ""
    notes: str = ""

    def as_csv_row(self) -> dict[str, str]:
        return {
            "record_id": self.row.record_id,
            "book_title": self.row.title,
            "book_author": self.row.author,
            "book_language_code": self.row.language_code,
            "search_query": self.row.query,
            "candidate_title": self.candidate.title,
            "candidate_language": self.candidate.language,
            "candidate_language_code": language_code(self.candidate.language),
            "candidate_url": self.candidate.url,
            "candidate_guid": self.candidate.guid,
            "prowlarr_indexer_id": self.candidate.prowlarr_indexer_id,
            "download_protocol": self.candidate.protocol,
            "download_size": self.candidate.size,
            "score": str(self.score),
            "candidate_completeness_status": self.completeness_status,
            "candidate_completeness_notes": self.completeness_notes,
            "decision_status": self.decision_status,
            "notes": self.notes,
        }


def read_search_queue(path: Path) -> list[SearchQueueRow]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = []
        for row in csv.DictReader(handle):
            rows.append(
                SearchQueueRow(
                    record_id=row.get("record_id", ""),
                    title=row.get("title", ""),
                    author=row.get("author", ""),
                    language_code=row.get("language_code", ""),
                    query=row.get("query", ""),
                    alternate_query=row.get("alternate_query", ""),
                    language_policy=row.get("language_policy", ""),
                )
            )
        return rows


def search_candidates(
    rows: list[SearchQueueRow],
    *,
    torznab_url: str,
    api_key: str = "",
    timeout: int = 15,
    limit_per_book: int = 5,
) -> list[RankedCandidate]:
    matches: list[RankedCandidate] = []
    for row in rows:
        candidates = query_torznab(torznab_url, row.query, api_key=api_key, timeout=timeout)
        ranked = [rank_candidate(row, candidate) for candidate in candidates]
        ranked.sort(key=lambda item: item.score, reverse=True)
        matches.extend(ranked[:limit_per_book])
    return matches


def query_torznab(torznab_url: str, query: str, *, api_key: str = "", timeout: int = 15) -> list[TorznabCandidate]:
    params = {"t": "search", "q": query}
    if api_key:
        params["apikey"] = api_key
    separator = "&" if "?" in torznab_url else "?"
    url = f"{torznab_url}{separator}{urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "BookBuddARR/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
    return parse_torznab_rss(body)


def parse_torznab_rss(body: bytes | str) -> list[TorznabCandidate]:
    if isinstance(body, str):
        body = body.encode("utf-8")
    root = ElementTree.fromstring(body)
    candidates: list[TorznabCandidate] = []
    for item in root.findall(".//item"):
        title = _text(item, "title")
        url = _candidate_url(item)
        if not title or not url:
            continue
        candidates.append(
            TorznabCandidate(
                title=title,
                url=url,
                language=_torznab_attr(item, "language"),
            )
        )
    return candidates


def rank_candidate(row: SearchQueueRow, candidate: TorznabCandidate) -> RankedCandidate:
    title_score = _token_overlap(row.title, candidate.title, weight=45)
    author_score = _token_overlap(row.author, candidate.title, weight=25)
    candidate_language_code = language_code(candidate.language)
    language_points, status = _language_result(row.language_code, candidate_language_code)
    score = max(0, min(100, title_score + author_score + language_points))
    completeness_status, completeness_notes = classify_candidate_completeness(row.title, candidate.title)
    if status == "pending_review" and completeness_status == "needs_completeness_review":
        status = "needs_completeness_review"
    return RankedCandidate(
        row=row,
        candidate=candidate,
        score=score,
        decision_status=status,
        completeness_status=completeness_status,
        completeness_notes=completeness_notes,
    )


def write_matches(path: Path, matches: list[RankedCandidate]) -> None:
    existing = _existing_review_state(path)
    rows = []
    for match in matches:
        row = match.as_csv_row()
        previous = existing.get((row["record_id"], row["candidate_url"]))
        if previous:
            row["decision_status"] = previous.get("decision_status", row["decision_status"])
            row["notes"] = previous.get("notes", "")
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MATCH_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_matches(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [_normalize_match_row(row) for row in csv.DictReader(handle)]


def candidates_from_prowlarr(row: SearchQueueRow, releases: list[dict[str, object]]) -> list[RankedCandidate]:
    ranked: list[RankedCandidate] = []
    for release in releases:
        candidate = TorznabCandidate(
            title=str(release.get("title") or ""),
            url=str(release.get("infoUrl") or release.get("guid") or release.get("downloadUrl") or ""),
            language=_release_language(release),
            guid=str(release.get("guid") or release.get("downloadUrl") or ""),
            prowlarr_indexer_id=str(release.get("indexerId") or ""),
            protocol=str(release.get("protocol") or ""),
            size=str(release.get("size") or ""),
        )
        if candidate.title and candidate.url:
            ranked.append(rank_candidate(row, candidate))
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked


def update_match_decision(
    path: Path,
    *,
    record_id: str,
    candidate_url: str,
    decision_status: str,
    notes: str | None = None,
    allow_incomplete: bool = False,
) -> dict[str, str]:
    decision_status = decision_status.strip().lower()
    if decision_status not in MUTABLE_DECISION_STATUSES:
        allowed = ", ".join(sorted(MUTABLE_DECISION_STATUSES))
        raise ValueError(f"Unsupported decision status '{decision_status}'. Allowed: {allowed}.")
    rows = read_matches(path)
    updated: dict[str, str] | None = None
    for row in rows:
        if row.get("record_id") == record_id and row.get("candidate_url") == candidate_url:
            if (
                decision_status == "approved"
                and not allow_incomplete
                and row.get("candidate_completeness_status") == "needs_completeness_review"
            ):
                raise ValueError(
                    "Candidate appears to be one part/volume of a larger audiobook. "
                    "Reject it or approve with an explicit incomplete override after confirming all parts are handled."
                )
            row["decision_status"] = decision_status
            if notes is not None:
                row["notes"] = notes
            updated = row
            break
    if updated is None:
        raise ValueError("No candidate matched the provided record_id and candidate_url.")
    _write_match_rows(path, rows)
    return updated


def approved_matches(path: Path) -> list[dict[str, str]]:
    return [row for row in read_matches(path) if row.get("decision_status") == "approved"]


def export_approved_matches(
    matches_path: Path,
    output_path: Path,
    *,
    output_format: str = "csv",
    source_label: str = "BookBuddARR approved candidates",
) -> dict[str, object]:
    rows = approved_matches(matches_path)
    output_format = output_format.strip().lower()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "csv":
        _write_export_csv(output_path, rows)
    elif output_format in {"audiobookshelf-json", "json"}:
        output_path.write_text(
            json.dumps(_audiobookshelf_export(rows, source_label=source_label), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        raise ValueError("Unsupported export format. Use csv or audiobookshelf-json.")
    return {
        "ok": True,
        "mode": "export_only_review_gate",
        "approved_rows": len(rows),
        "output": str(output_path),
        "format": output_format,
        "grabbed": 0,
        "downloaded": 0,
    }


def _existing_review_state(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {
            (row.get("record_id", ""), row.get("candidate_url", "")): row
            for row in csv.DictReader(handle)
            if row.get("record_id") and row.get("candidate_url")
        }


def _normalize_match_row(row: dict[str, str]) -> dict[str, str]:
    normalized = {field: row.get(field, "") for field in MATCH_FIELDS}
    return normalized


def classify_candidate_completeness(book_title: str, candidate_title: str) -> tuple[str, str]:
    candidate = normalize_for_key(candidate_title)
    book = normalize_for_key(book_title)
    complete_markers = {"complete", "complet", "completee", "integral", "integrale", "unabridged"}
    if any(marker in candidate.split() for marker in complete_markers):
        return "likely_complete", "Candidate title contains a complete/integral marker."
    part_patterns = [
        r"\b(?:vol|volume|tome|part|partie|book|livre|disc|disque|cd)\s*(?:0?[1-9]|[ivxlcdm]+)\b",
        r"\b(?:0?[1-9]|[ivxlcdm]+)\s*(?:-|:)\s+",
    ]
    candidate_has_part = any(re.search(pattern, candidate) for pattern in part_patterns)
    book_has_part = any(re.search(pattern, book) for pattern in part_patterns)
    if book and candidate.startswith(book + " "):
        remainder = candidate[len(book) :].strip().split()
        if remainder and re.fullmatch(r"0?[1-9]|[ivxlcdm]+", remainder[0]):
            candidate_has_part = True
    if candidate_has_part:
        if book_has_part:
            return "part_as_requested", "Candidate and BookBuddy title both appear to target a numbered part."
        return "needs_completeness_review", "Candidate title appears to be a numbered part/volume of a larger audiobook."
    return "unknown", "No explicit complete or part marker detected."


def _write_match_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MATCH_FIELDS)
        writer.writeheader()
        writer.writerows([_normalize_match_row(row) for row in rows])


def _write_export_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=APPROVED_EXPORT_FIELDS)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in APPROVED_EXPORT_FIELDS} for row in rows])


def _audiobookshelf_export(rows: list[dict[str, str]], *, source_label: str) -> dict[str, object]:
    return {
        "source": source_label,
        "mode": "export_only_review_gate",
        "mutates_audiobookshelf": False,
        "items": [
            {
                "bookTitle": row.get("book_title", ""),
                "bookAuthor": row.get("book_author", ""),
                "bookLanguageCode": row.get("book_language_code", ""),
                "candidateTitle": row.get("candidate_title", ""),
                "candidateLanguage": row.get("candidate_language", ""),
                "candidateUrl": row.get("candidate_url", ""),
                "downloadProtocol": row.get("download_protocol", ""),
                "notes": row.get("notes", ""),
            }
            for row in rows
        ],
    }


def _release_language(release: dict[str, object]) -> str:
    value = release.get("language") or release.get("languages") or ""
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


def _language_result(book_language_code: str, candidate_language_code: str) -> tuple[int, str]:
    if not book_language_code:
        return 0, "needs_language_review"
    if not candidate_language_code:
        return 5, "pending_review"
    if book_language_code == candidate_language_code:
        return 30, "pending_review"
    return -35, "language_mismatch"


def _token_overlap(expected: str, actual: str, *, weight: int) -> int:
    expected_tokens = set(normalize_for_key(expected).split())
    actual_tokens = set(normalize_for_key(actual).split())
    if not expected_tokens or not actual_tokens:
        return 0
    return round(weight * (len(expected_tokens & actual_tokens) / len(expected_tokens)))


def _candidate_url(item: ElementTree.Element) -> str:
    for tag in ["comments", "guid", "link"]:
        value = _text(item, tag)
        if value:
            return value
    return ""


def _torznab_attr(item: ElementTree.Element, name: str) -> str:
    for attr in item.findall(f"{TORZNAB_NS}attr"):
        if attr.attrib.get("name") == name:
            return attr.attrib.get("value", "")
    return ""


def _text(item: ElementTree.Element, tag: str) -> str:
    child = item.find(tag)
    return (child.text or "").strip() if child is not None else ""
