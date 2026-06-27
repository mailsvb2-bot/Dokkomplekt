"""Language-aware ICD-10 row model used by the local diagnosis selector."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from medical_language_catalog import normalize_language_id


@dataclass(frozen=True)
class ICD10Diagnosis:
    """One ICD-10 catalog row.

    ``title`` remains the Russian title for backward compatibility with older
    renderer and smoke code. ``titles`` stores optional localized titles used by
    the UI/search layer when the program language is changed.
    """

    code: str
    title: str
    titles: Mapping[str, str] = field(default_factory=dict)
    kind: str = "diagnosis"

    def title_for_language(self, language_id: str | None = "ru") -> str:
        lang = normalize_language_id(language_id, default="ru")
        if lang == "auto":
            lang = "ru"
        return (
            str(self.titles.get(lang) or "").strip()
            or str(self.titles.get("ru") or "").strip()
            or str(self.titles.get("en") or "").strip()
            or self.title
        )

    def display_for_language(self, language_id: str | None = "ru") -> str:
        return f"{self.code} {self.title_for_language(language_id)}"

    @property
    def display(self) -> str:
        return self.display_for_language("ru")
