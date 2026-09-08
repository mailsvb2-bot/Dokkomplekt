from __future__ import annotations

"""High-confidence current-episode dates for a selected primary/referral DOCX.

The generic medical date resolver intentionally understands narrative phrases
such as ``госпитализирован ... выписан ...``. That is useful when parsing a
known discharge narrative, but a primary examination/referral often contains
old hospitalizations in the anamnesis. This module is the stricter boundary
used by the live patient-selection path: current dates come from explicit
current-episode labels, and admission may additionally come from the document
title. Historical narrative dates must not populate the current UI fields.
"""

from pathlib import Path

from diagnostic_logging import record_soft_exception
from medical_admission_resolver import extract_admission_date_from_primary_text
from medical_docx_date_patterns import _TITLE_DATE_RE, _normalize_full_date_match
from medical_docx_reader import extract_docx_text
from medical_docx_title_finder import extract_admission_date_from_title_docx
from medical_text_utils import normalize_match, normalize_text

CURRENT_EPISODE_DATES_LOCK_VERSION = "v1.0"
CURRENT_ADMISSION_LABELS = (
    "дата поступления",
    "дата госпитализации",
    "дата приема",
    "дата приёма",
    "data przyjęcia",
    "data przyjecia",
    "data hospitalizacji",
)
CURRENT_DISCHARGE_LABELS = (
    "дата выписки",
    "дата выписания",
    "дата выписного эпикриза",
    "data wypisu",
    "data wypisania",
)


def _date_after_explicit_label(text: str, labels: tuple[str, ...]) -> str:
    """Return the first valid date after the nearest explicit label."""
    value = normalize_text(text or "")
    if not value:
        return ""
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    for idx, line in enumerate(lines[:320]):
        line_norm = normalize_match(line)
        matching = [label for label in labels if normalize_match(label) in line_norm]
        if not matching:
            continue
        # DOCX table extraction commonly emits label/value as adjacent lines.
        # A forward-only window prevents a date from the preceding demographic
        # or historical row from being attached to this current-episode label.
        window = " | ".join(lines[idx:min(len(lines), idx + 4)])
        window_norm = normalize_match(window)
        label_positions = [
            window_norm.find(normalize_match(label))
            for label in matching
            if window_norm.find(normalize_match(label)) >= 0
        ]
        if not label_positions:
            continue
        label_pos = min(label_positions)
        candidates: list[tuple[int, str]] = []
        for match in _TITLE_DATE_RE.finditer(window):
            if match.start() < label_pos:
                continue
            normalized = _normalize_full_date_match(match)
            if normalized:
                candidates.append((match.start() - label_pos, normalized))
        if candidates:
            return min(candidates, key=lambda item: item[0])[1]
    return ""


def extract_current_admission_date_from_primary_text(text: str) -> str:
    """Prefer explicit current admission labels in already extracted text."""
    return _date_after_explicit_label(text, CURRENT_ADMISSION_LABELS) or extract_admission_date_from_primary_text(text)


def extract_current_discharge_date_from_primary_text(text: str) -> str:
    """Accept discharge only from an explicit current-episode label."""
    return _date_after_explicit_label(text, CURRENT_DISCHARGE_LABELS)


def extract_current_admission_date_from_primary_docx(path: str | Path) -> str:
    """Resolve current admission as labeled field > title date > narrative fallback."""
    title_date = ""
    try:
        title_date = extract_admission_date_from_title_docx(path)
    except Exception as exc:
        record_soft_exception("medical_current_episode_dates.admission_title", exc, detail=str(path))
    try:
        text = extract_docx_text(path)
    except Exception as exc:
        record_soft_exception("medical_current_episode_dates.admission_text", exc, detail=str(path))
        return title_date
    labeled = _date_after_explicit_label(text, CURRENT_ADMISSION_LABELS)
    if labeled:
        return labeled
    if title_date:
        return title_date
    return extract_admission_date_from_primary_text(text)


def extract_current_discharge_date_from_primary_docx(path: str | Path) -> str:
    """Resolve current discharge only from a labeled current-episode field."""
    try:
        text = extract_docx_text(path)
    except Exception as exc:
        record_soft_exception("medical_current_episode_dates.discharge_text", exc, detail=str(path))
        return ""
    return _date_after_explicit_label(text, CURRENT_DISCHARGE_LABELS)


def assert_current_episode_dates_lock() -> None:
    if CURRENT_EPISODE_DATES_LOCK_VERSION != "v1.0":
        raise AssertionError("Current-episode date contract changed unexpectedly")
    historical = "Анамнез: госпитализирован 01.02.2023, выписан 07.02.2023."
    if extract_current_discharge_date_from_primary_text(historical):
        raise AssertionError("Historical discharge narrative must not become current discharge")
    labeled = "Дата поступления: 30.09.2025. Дата выписки: 10.10.2025."
    if extract_current_admission_date_from_primary_text(labeled) != "30.09.2025":
        raise AssertionError("Explicit admission label must populate current admission")
    if extract_current_discharge_date_from_primary_text(labeled) != "10.10.2025":
        raise AssertionError("Explicit discharge label must populate current discharge")
