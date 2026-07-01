"""Разделённый слой заполнителя дневников.

Файл создан при архитектурной нарезке бывшего diary_filler.py.
"""

from __future__ import annotations

import re

from diary_constants import GENDER_WORD_PAIRS, RUSSIAN_VOWELS
from diary_text_parser import normalize_text

_POLISH_FEMALE_SUFFIXES = ("ska", "cka", "dzka", "owa", "ina")
_POLISH_MALE_SUFFIXES = ("ski", "cki", "dzki")
_POLISH_FEMALE_FIRST_NAMES = {
    "anna", "ewa", "maria", "joanna", "agnieszka", "katarzyna", "magdalena", "małgorzata", "malgorzata",
    "aleksandra", "barbara", "monika", "natalia", "paulina", "karolina", "zofia", "alicja", "marta",
}
_POLISH_MALE_FIRST_NAMES = {
    "jan", "piotr", "paweł", "pawel", "tomasz", "adam", "marek", "krzysztof", "michał", "michal",
    "andrzej", "marcin", "grzegorz", "jakub", "wojciech", "łukasz", "lukasz", "kamil", "maciej",
}


def detect_gender_from_patient_name(patient_name: str) -> str | None:
    """Detect patient gender by the first visible name token.

    Russian/Cyrillic surnames keep the historical vowel heuristic.  Polish
    constructor profiles often pass either ``Kowalska Anna`` or ``Anna Kowalska``;
    both must be accepted for diary text agreement without adding country-bound
    templates.
    """
    value = normalize_text(patient_name)
    if not value:
        return None
    tokens = [re.sub(r"[^A-Za-zА-Яа-яЁёĄąĆćĘęŁłŃńÓóŚśŹźŻż-]+", "", token).strip("-") for token in value.split()]
    tokens = [token for token in tokens if token]
    if not tokens:
        return None
    lowered = [token.lower() for token in tokens]
    for token in lowered[:2]:
        if token in _POLISH_FEMALE_FIRST_NAMES or token.endswith(_POLISH_FEMALE_SUFFIXES):
            return "female"
        if token in _POLISH_MALE_FIRST_NAMES or token.endswith(_POLISH_MALE_SUFFIXES):
            return "male"
    surname = lowered[0]
    last = surname[-1]
    if last in RUSSIAN_VOWELS or last in {"a", "ą", "ę"}:
        return "female"
    return "male"


def gender_label(gender: str | None) -> str:
    if gender == "male":
        return "мужской"
    if gender == "female":
        return "женский"
    return "не определён"


def _preserve_case(source: str, target: str) -> str:
    if source.isupper():
        return target.upper()
    if source[:1].isupper():
        return target[:1].upper() + target[1:]
    return target


def _replace_gender_pair(text: str, source: str, target: str) -> tuple[str, int]:
    pattern = re.compile(rf"(?<![A-Za-zА-Яа-яЁёĄąĆćĘęŁłŃńÓóŚśŹźŻż]){re.escape(source)}(?![A-Za-zА-Яа-яЁёĄąĆćĘęŁłŃńÓóŚśŹźŻż])", re.IGNORECASE)
    count = 0

    def repl(match: re.Match) -> str:
        nonlocal count
        count += 1
        return _preserve_case(match.group(0), target)

    return pattern.sub(repl, text), count


def adapt_text_to_patient_gender(text: str, gender: str | None) -> tuple[str, int]:
    """Adapt known gendered diary words to the detected patient gender."""
    if gender not in {"male", "female"} or not text:
        return text, 0

    pairs = sorted(GENDER_WORD_PAIRS, key=lambda pair: max(len(pair[0]), len(pair[1])), reverse=True)
    result = text
    replacements = 0
    for male, female in pairs:
        source, target = (female, male) if gender == "male" else (male, female)
        result, changed = _replace_gender_pair(result, source, target)
        replacements += changed
    return result, replacements


def convert_text_gender(text: str, gender: str | None) -> tuple[str, int]:
    """Backward-compatible alias used by the combined application."""
    return adapt_text_to_patient_gender(text, gender)
