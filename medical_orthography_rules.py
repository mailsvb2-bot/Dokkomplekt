"""Conservative multilingual orthography rules for medical text.

Rules here are intentionally small and auditable.  The product must not silently
rewrite diagnoses, identifiers, codes or doctor-specific formulations.
"""

from __future__ import annotations

ORTHOGRAPHY_RULES_LOCK_VERSION = "v1.0"

# Exact token/phrase replacements, lower-cased for matching.  These are common
# label/heading mistakes or safe typography normalizations, not clinical edits.
PHRASE_CORRECTIONS: dict[str, dict[str, str]] = {
    "ru": {
        "диагнозз": "диагноз",
        "анамнезз": "анамнез",
        "рекоммендации": "рекомендации",
        "рекомендаци": "рекомендации",
        "лечениее": "лечение",
        "жалобыы": "жалобы",
        "исторя болезни": "история болезни",
    },
    "uk": {
        "діагнозз": "діагноз",
        "скаргии": "скарги",
        "лікуванняя": "лікування",
        "рекомендациї": "рекомендації",
    },
    "be": {"дыягнозз": "дыягназ", "лячэннее": "лячэнне"},
    "az": {"diaqnozz": "diaqnoz", "mualicə": "müalicə", "tovsiyə": "tövsiyə"},
    "uz": {"tashxiss": "tashxis", "davolashh": "davolash"},
    "kk": {"диагнозз": "диагноз", "емдеуу": "емдеу"},
    "hy": {"ախտորոշւմ": "ախտորոշում"},
    "ka": {"დიაგნოზზი": "დიაგნოზი"},
    "tg": {"ташхисс": "ташхис"},
    "tk": {"diagnozz": "diagnoz"},
    "en": {"diagnosiss": "diagnosis", "treatement": "treatment", "reccomendations": "recommendations"},
}

MEDICAL_SAFE_SKIP_REASONS = (
    "{{field.placeholders}}",
    "МКБ/ICD codes",
    "dates and numbers",
    "document identifiers",
    "all-caps medical abbreviations",
)


def assert_orthography_rules_lock() -> None:
    if ORTHOGRAPHY_RULES_LOCK_VERSION != "v1.0":
        raise AssertionError("Orthography rules lock changed unexpectedly")
    if "рекоммендации" not in PHRASE_CORRECTIONS["ru"]:
        raise AssertionError("Russian conservative correction fixture is missing")
    if "treatement" not in PHRASE_CORRECTIONS["en"]:
        raise AssertionError("English conservative correction fixture is missing")
