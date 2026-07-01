"""Detection of explicit treatment section markers in primary DOCX text."""
from __future__ import annotations

import re

from medical_text_utils import normalize_match, normalize_text

# Treat only explicit section labels as evidence that the primary document has
# its own treatment field. Ordinary phrases like "за время лечения" or
# "находится на лечении" must not suppress the doctor popup.
_TREATMENT_LABEL = r"(?:назначенное\s+лечение|план\s+лечения|лечение|zalecone\s+leczenie|zastosowane\s+leczenie|plan\s+leczenia|leczenie|terapia)"
_TREATMENT_MARKER_WITH_SEPARATOR_RE = re.compile(
    # Strict section labels: "Лечение:", "Назначенное лечение - ...",
    # "План лечения".  This is the safest signal that the primary document
    # already contains its own treatment field.
    rf"^\s*{_TREATMENT_LABEL}\b\s*(?:[:№#Nn.\-–—]|$)",
    flags=re.IGNORECASE,
)
_TREATMENT_MARKER_MERGED_VALUE_RE = re.compile(
    # Some DOCX table exports merge the label and the value without punctuation:
    # "Лечение терапия по схеме".  Keep that support, but filter obvious prose
    # below so a sentence like "Лечение получал амбулаторно" does not suppress
    # the doctor's popup.
    rf"^\s*{_TREATMENT_LABEL}\b\s+(?P<tail>\S.+)$",
    flags=re.IGNORECASE,
)

_PROSE_AFTER_TREATMENT_LABEL_PREFIXES = (
    "было",
    "был",
    "проводилось",
    "проводится",
    "назначалось",
    "получал",
    "получала",
    "получает",
    "переносил",
    "переносила",
    "осуществлялось",
    "не проводилось",
    "ранее",
    "było",
    "bylo",
    "prowadzono",
    "otrzymywał",
    "otrzymywal",
    "otrzymywała",
    "otrzymywala",
    "w trakcie",
)


def line_has_treatment_marker(line: str) -> bool:
    """Return True when a single text line is an explicit treatment label."""
    cleaned = normalize_text(line or "").strip()
    if not cleaned:
        return False
    normalized = normalize_match(cleaned)
    # Guard against prose sentences that only contain the word treatment.
    if normalized.startswith(("за время лечения", "находится на лечении", "получал лечение", "получает лечение", "w trakcie leczenia", "przebieg leczenia")):
        return False
    if _TREATMENT_MARKER_WITH_SEPARATOR_RE.match(cleaned):
        return True
    merged = _TREATMENT_MARKER_MERGED_VALUE_RE.match(cleaned)
    if not merged:
        return False
    tail = normalize_match(merged.group("tail"))
    if tail.startswith(_PROSE_AFTER_TREATMENT_LABEL_PREFIXES):
        return False
    return True


def has_treatment_section_marker(text: str) -> bool:
    """Scan the full parsed primary-document text for a treatment section row."""
    for line in normalize_text(text or "").splitlines():
        if line_has_treatment_marker(line):
            return True
    return False
