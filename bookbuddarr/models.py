from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BookRecord:
    record_id: str
    title: str
    author: str
    isbn: str
    language: str
    language_code: str
    year: str
    publisher: str
    source_position: str
    source_added_at: str
    original_title: str = ""
    series: str = ""
    volume: str = ""
    google_volume_id: str = ""
    status: str = ""

    def as_registry_row(self) -> dict[str, str]:
        return {
            "record_id": self.record_id,
            "title": self.title,
            "author": self.author,
            "isbn": self.isbn,
            "language": self.language,
            "language_code": self.language_code,
            "year": self.year,
            "publisher": self.publisher,
            "series": self.series,
            "volume": self.volume,
            "google_volume_id": self.google_volume_id,
            "source_position": self.source_position,
            "source_added_at": self.source_added_at,
            "status": self.status,
        }

    def as_new_row(self) -> dict[str, str]:
        row = self.as_registry_row()
        row["search_query"] = self.search_query()
        row["audiobook_query"] = self.audiobook_query()
        return row

    def search_query(self) -> str:
        parts = [self.title, self.author, self.year]
        return " ".join(part for part in parts if part).strip()

    def audiobook_query(self) -> str:
        marker = {
            "fr": "livre audio francais",
            "en": "audiobook english",
        }.get(self.language_code, "audiobook")
        return " ".join(part for part in [self.title, self.author, marker] if part).strip()
