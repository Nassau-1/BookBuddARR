from __future__ import annotations

from dataclasses import dataclass

from .models import BookRecord


@dataclass(frozen=True)
class AudiobookRule:
    wanted_language: str
    language_policy: str
    query: str
    alternate_query: str
    root_folder_hint: str
    manual_review_required: bool = True


def audiobook_rule(record: BookRecord) -> AudiobookRule:
    if record.language_code == "fr":
        return AudiobookRule(
            wanted_language="French",
            language_policy="require_french_or_manual_review",
            query=_join(record.title, record.author, "French audiobook"),
            alternate_query=_join(record.title, record.author, "livre audio francais"),
            root_folder_hint="/Data/Audiobooks/Francais",
        )
    if record.language_code == "en":
        return AudiobookRule(
            wanted_language="English",
            language_policy="require_english_or_manual_review",
            query=_join(record.title, record.author, "English audiobook"),
            alternate_query=_join(record.title, record.author, "audiobook"),
            root_folder_hint="/Data/Audiobooks/English",
        )
    return AudiobookRule(
        wanted_language="Unknown",
        language_policy="manual_language_review_required",
        query=_join(record.title, record.author, "audiobook"),
        alternate_query=_join(record.original_title, record.author, "audiobook"),
        root_folder_hint="/Data/Audiobooks",
    )


def _join(*parts: str) -> str:
    return " ".join(part for part in parts if part).strip()
