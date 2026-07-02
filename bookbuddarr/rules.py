from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .models import BookRecord

DEFAULT_AUDIOBOOK_ROOTS = {
    "fr": "/Data/Audiobooks/Francais",
    "en": "/Data/Audiobooks/English",
    "unknown": "/Data/Audiobooks",
}


@dataclass(frozen=True)
class AudiobookRule:
    wanted_language: str
    language_policy: str
    query: str
    alternate_query: str
    root_folder_hint: str
    manual_review_required: bool = True


def audiobook_rule(record: BookRecord, language_roots: dict[str, str] | None = None) -> AudiobookRule:
    roots = audiobook_root_map(language_roots)
    if record.language_code == "fr":
        return AudiobookRule(
            wanted_language="French",
            language_policy="require_french_or_manual_review",
            query=_join(record.title, record.author, "French audiobook"),
            alternate_query=_join(record.title, record.author, "livre audio francais"),
            root_folder_hint=roots["fr"],
        )
    if record.language_code == "en":
        return AudiobookRule(
            wanted_language="English",
            language_policy="require_english_or_manual_review",
            query=_join(record.title, record.author, "English audiobook"),
            alternate_query=_join(record.title, record.author, "audiobook"),
            root_folder_hint=roots["en"],
        )
    return AudiobookRule(
        wanted_language="Unknown",
        language_policy="manual_language_review_required",
        query=_join(record.title, record.author, "audiobook"),
        alternate_query=_join(record.original_title, record.author, "audiobook"),
        root_folder_hint=roots["unknown"],
    )


def audiobook_root_map(overrides: dict[str, str] | None = None) -> dict[str, str]:
    roots = dict(DEFAULT_AUDIOBOOK_ROOTS)
    for key, value in (overrides or {}).items():
        normalized_key = key.strip().lower()
        if normalized_key in {"fr", "french"}:
            roots["fr"] = value
        elif normalized_key in {"en", "english"}:
            roots["en"] = value
        elif normalized_key in {"unknown", "manual", ""}:
            roots["unknown"] = value
    return roots


def load_audiobook_root_map(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Language root mapping must be a JSON object.")
    return {str(key): str(value) for key, value in data.items()}


def _join(*parts: str) -> str:
    return " ".join(part for part in parts if part).strip()
