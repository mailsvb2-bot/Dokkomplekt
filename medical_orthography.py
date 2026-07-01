"""Medical-safe multilingual orthography pipeline.

The service corrects only conservative, auditable mistakes and typography.  It
must never alter clinical codes, dates, document numbers, placeholders or
unknown doctor wording.  This is a product safety lock, not a limitation.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re

from medical_language_catalog import normalize_language_id
from medical_language_detector import detect_text_language
from medical_orthography_rules import PHRASE_CORRECTIONS

ORTHOGRAPHY_MEDICAL_SAFE_LOCK_VERSION = "v1.1"
ORTHOGRAPHY_IS_CONSERVATIVE = True
ORTHOGRAPHY_CORRECTION_CACHE_ENABLED = True

_PROTECTED_RE = re.compile(
    r"(\{\{[^{}]+\}\}|\b[A-ZА-Я]\s?\d{2}(?:\.\d+)?\b|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b\d{2,}[-/\\]\d+\b|\b[А-ЯA-Z]{2,}\b)"
)


@dataclass(frozen=True)
class OrthographyResult:
    original: str
    corrected: str
    language_id: str
    changed: bool
    applied_rules: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "language_id": self.language_id,
            "changed": self.changed,
            "applied_rules": list(self.applied_rules),
            "corrected": self.corrected,
        }


def correct_medical_text(text: str, *, language_id: str = "auto", enabled: bool = True) -> OrthographyResult:
    return _correct_medical_text_cached(str(text or ""), str(language_id or "auto"), bool(enabled))


@lru_cache(maxsize=8192)
def _correct_medical_text_cached(original: str, language_id: str, enabled: bool) -> OrthographyResult:
    if not enabled or not original:
        return OrthographyResult(original, original, normalize_language_id(language_id), False, ())
    lang = normalize_language_id(language_id)
    if lang == "auto":
        lang = detect_text_language(original).language_id
    lang = normalize_language_id(lang, default="ru")
    protected: list[str] = []

    def protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"\uFFF0{len(protected) - 1}\uFFF1"

    working = _PROTECTED_RE.sub(protect, original)
    applied: list[str] = []
    working = _normalize_typography(working)
    for wrong, right in PHRASE_CORRECTIONS.get(lang, {}).items():
        pattern = _phrase_pattern(lang, wrong)
        if pattern.search(working):
            working = pattern.sub(_case_preserving_replacement(right), working)
            applied.append(f"{lang}:{wrong}->{right}")
    for index, value in enumerate(protected):
        working = working.replace(f"\uFFF0{index}\uFFF1", value)
    return OrthographyResult(original, working, lang, working != original, tuple(applied))


@lru_cache(maxsize=4096)
def _phrase_pattern(_lang: str, wrong: str) -> re.Pattern[str]:
    return re.compile(rf"(?iu)(?<![\w]){re.escape(wrong)}(?![\w])")


def correct_case_values(values: dict[str, str], *, language_id: str = "auto", enabled: bool = True) -> dict[str, str]:
    """Correct only free-text values before rendering custom DOCX output."""

    result: dict[str, str] = {}
    for field_id, value in values.items():
        if _is_safe_to_correct_field(field_id):
            result[field_id] = correct_medical_text(value, language_id=language_id, enabled=enabled).corrected
        else:
            result[field_id] = value
    return result


def _normalize_typography(text: str) -> str:
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])([^\s\n])", r"\1 \2", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip() if "\n" not in text else "\n".join(line.strip() for line in text.splitlines())


def _case_preserving_replacement(replacement: str):
    def repl(match: re.Match[str]) -> str:
        src = match.group(0)
        if src.isupper():
            return replacement.upper()
        if src[:1].isupper():
            return replacement[:1].upper() + replacement[1:]
        return replacement
    return repl


def _is_safe_to_correct_field(field_id: str) -> bool:
    field = str(field_id or "").lower()
    if any(marker in field for marker in ("icd", "mkb", "number", "date", "snils", "passport", "signature")):
        return False
    if field.startswith("document."):
        return False
    return True


def assert_orthography_medical_safe_lock() -> None:
    if ORTHOGRAPHY_MEDICAL_SAFE_LOCK_VERSION != "v1.1" or not ORTHOGRAPHY_IS_CONSERVATIVE:
        raise AssertionError("Orthography medical-safe lock changed")
    if not ORTHOGRAPHY_CORRECTION_CACHE_ENABLED:
        raise AssertionError("Orthography correction cache must stay enabled for batch rendering")
    text = "Диагноз: K35.8. Рекоммендации: наблюдение 10.06.2026 {{patient.fio}}"
    corrected = correct_medical_text(text, language_id="ru").corrected
    if "K35.8" not in corrected or "10.06.2026" not in corrected or "{{patient.fio}}" not in corrected:
        raise AssertionError("Orthography changed protected medical tokens")
    if "Рекомендации" not in corrected:
        raise AssertionError("Orthography did not apply conservative correction")
    if correct_medical_text(text, language_id="ru").corrected != corrected:
        raise AssertionError("Orthography cache changed correction result")
