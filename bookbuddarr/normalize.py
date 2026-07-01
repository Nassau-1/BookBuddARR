from __future__ import annotations

import hashlib
import re
import unicodedata


ISBN_RE = re.compile(r"[^0-9Xx]")


def clean_text(value: str | None) -> str:
    return " ".join((value or "").replace("\ufeff", "").split()).strip()


def normalize_for_key(value: str | None) -> str:
    text = clean_text(value).casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_isbn(value: str | None) -> str:
    raw = ISBN_RE.sub("", value or "").upper()
    if len(raw) in {10, 13}:
        return raw
    return raw


def language_code(value: str | None) -> str:
    normalized = normalize_for_key(value)
    if normalized in {"fr", "fra", "fre", "french", "francais", "francaise"}:
        return "fr"
    if normalized in {"en", "eng", "english", "anglais", "anglaise"}:
        return "en"
    if "franc" in normalized:
        return "fr"
    if "engl" in normalized or "angl" in normalized:
        return "en"
    return ""


def stable_record_id(title: str, author: str, isbn: str, language: str) -> str:
    if isbn:
        return f"isbn:{isbn}"
    key = "|".join(
        [
            normalize_for_key(title),
            normalize_for_key(author),
            language_code(language),
        ]
    )
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return f"text:{digest}"
