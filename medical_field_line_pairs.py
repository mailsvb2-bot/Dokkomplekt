from __future__ import annotations

"""Conservative label/value extraction from flattened DOCX text.

python-docx returns table cells as separate lines.  A very common medical
layout is therefore flattened from:

    Ф.И.О. | Иванов Иван Иванович

into two lines:

    Ф.И.О.
    Иванов Иван Иванович

The ordinary inline parser sees the label line but no value after it.  This
module provides a small deterministic helper for that specific table/row shape.
It does not try to understand the whole document and it never executes code.
"""

import re
from typing import Iterable, Sequence

from medical_text_utils import clean_value, looks_like_label, normalize_match, normalize_text

FIELD_LINE_PAIRS_LOCK_VERSION = "v1.0"
FIELD_LINE_PAIRS_READS_NEXT_TABLE_CELL_VALUE = True
FIELD_LINE_PAIRS_DOES_NOT_CROSS_SECTION_LABELS = True
FIELD_LINE_PAIRS_MAX_LOOKAHEAD = 3


def value_after_label_line(
    lines: Sequence[str],
    index: int,
    *,
    all_aliases: Iterable[str],
    allow_label_values: bool = False,
) -> str:
    """Return the next-cell value after a label-only line.

    The helper looks only a few lines ahead and stops when it sees another known
    field/section label.  This keeps it useful for table cells while preventing
    accidental cross-block captures.
    """

    if index < 0 or index >= len(lines):
        return ""
    alias_patterns = tuple(_alias_patterns(all_aliases))
    for offset in range(1, FIELD_LINE_PAIRS_MAX_LOOKAHEAD + 1):
        next_index = index + offset
        if next_index >= len(lines):
            break
        raw = normalize_text(lines[next_index] or "")
        value = clean_value(raw)
        if not value:
            continue
        if _starts_with_known_label(value, alias_patterns):
            # Some real values are also valid labels elsewhere in the form.
            # Example: a table row ``Должность | врач``; ``врач`` is a doctor
            # label in other contexts, but here it is the patient's position.
            # ``allow_label_values`` is enabled only by field-specific callers
            # (position/doctor/head), so it is safe to keep the popup/UI value
            # instead of erasing it as a foreign label.
            if not allow_label_values:
                return ""
            return value
        if not allow_label_values and looks_like_label(value):
            return ""
        return value
    return ""


def line_starts_with_label(value: str, aliases: Iterable[str]) -> bool:
    return _starts_with_known_label(value, tuple(_alias_patterns(aliases)))


def _alias_patterns(aliases: Iterable[str]) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for alias in aliases:
        alias_text = str(alias or "").strip()
        if not alias_text:
            continue
        alias_pattern = re.escape(alias_text).replace(r"\ ", r"\s+")
        patterns.append(re.compile(rf"^\s*{alias_pattern}(?![А-Яа-яA-Za-z0-9])\s*(?:[:№N#.-]|$)", re.IGNORECASE))
    return patterns


def _starts_with_known_label(value: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    text = normalize_text(value or "")
    if not text:
        return False
    if any(pattern.search(text) for pattern in patterns):
        return True
    normalized = normalize_match(text)
    # Broad fallback for section headers that may not be in FIELD_ALIASES.
    return normalized in {
        "жалобы", "анамнез жизни", "анамнез заболевания", "психический статус",
        "соматический статус", "план обследования", "план лечения", "диагноз",
        "лечение", "рекомендовано", "рекомендации",
    }


def assert_field_line_pairs_lock() -> None:
    if FIELD_LINE_PAIRS_LOCK_VERSION != "v1.0":
        raise AssertionError("Field line-pairs lock changed unexpectedly")
    if not FIELD_LINE_PAIRS_READS_NEXT_TABLE_CELL_VALUE:
        raise AssertionError("Field line-pairs must support next-cell values")
    if not FIELD_LINE_PAIRS_DOES_NOT_CROSS_SECTION_LABELS:
        raise AssertionError("Field line-pairs must not cross section labels")
    if FIELD_LINE_PAIRS_MAX_LOOKAHEAD != 3:
        raise AssertionError("Field line-pairs lookahead changed unexpectedly")
