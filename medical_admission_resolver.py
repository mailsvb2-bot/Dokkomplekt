from __future__ import annotations

"""Robust admission/discharge date resolvers for primary medical documents.

Admission and discharge dates are separate patient-event dates.  The program must
not fill a discharge epicrisis with a random title date, a birth date, an
admission date or a stale UI value.  Both resolvers therefore accept only dates
near explicit semantic markers and reject demographic contexts.
"""

from diagnostic_logging import record_soft_exception
import re
from pathlib import Path

from medical_constants import DATE_FMT
from medical_docx_date_patterns import _TITLE_DATE_RE, _normalize_full_date_match
from medical_docx_reader import extract_docx_text
from medical_docx_title_context import _date_match_has_birth_context
from medical_docx_title_finder import extract_admission_date_from_title_docx
from medical_text_utils import normalize_match, normalize_text

ADMISSION_RESOLVER_LOCK_VERSION = "v1.4"
ADMISSION_RESOLVER_REJECTS_BIRTH_CONTEXT = True
ADMISSION_RESOLVER_USES_EXPLICIT_ADMISSION_MARKERS = True
ADMISSION_RESOLVER_EXPLICIT_MARKERS_OVERRIDE_BIRTHY_TITLE = True
ADMISSION_RESOLVER_COMPARES_MARKER_DISTANCE_WITH_ORIGINAL_POSITIONS = True
DISCHARGE_RESOLVER_USES_EXPLICIT_DISCHARGE_MARKERS = True
DISCHARGE_RESOLVER_REJECTS_ADMISSION_AND_BIRTH_CONTEXT = True

_ADMISSION_MARKERS = (
    "дата поступления",
    "дата госпитализации",
    "поступил",
    "поступила",
    "поступает",
    "госпитализирован",
    "госпитализирована",
    "госпитализируется",
    "принят",
    "принята",
    "направлен на госпитализацию",
    "направлена на госпитализацию",
    "направление на госпитализацию",
    "в отделение поступ",
    "в 3 отделение кдп поступ",
    "data przyjęcia",
    "data przyjecia",
    "data hospitalizacji",
    "przyjęty",
    "przyjety",
    "przyjęta",
    "przyjeta",
    "przyjęcie",
    "przyjecie",
    "hospitalizacja od",
    "skierowanie na hospitalizację",
    "skierowanie na hospitalizacje",
    "skierowanie do szpitala",
)
_DISCHARGE_MARKERS = (
    "дата выписки",
    "дата выписания",
    "дата выписного эпикриза",
    "выписан",
    "выписана",
    "выписывается",
    "выписать",
    "к выписке",
    "окончание госпитализации",
    "окончание лечения",
    "data wypisu",
    "data wypisania",
    "wypisany",
    "wypisana",
    "wypisano",
    "wypis",
)
_BIRTH_MARKERS = (
    "дата рождения",
    "год рождения",
    "г.р",
    "возраст",
    "родился",
    "родилась",
    "data urodzenia",
    "urodzony",
    "urodzona",
    "pesel",
    "wiek",
)


def extract_admission_date_from_primary_docx(path: str | Path) -> str:
    """Return a safe admission date from a primary/referral DOCX.

    Priority:
    1. explicit admission/hospitalization markers in the full DOCX text;
    2. strict title/header date when no explicit admission marker exists.

    It deliberately does not use a random first date from the document.
    """

    title_date = ""
    try:
        title_date = extract_admission_date_from_title_docx(path)
    except Exception as exc:
        record_soft_exception("medical_admission_resolver.title_date", exc, detail=str(path))
        title_date = ""

    try:
        text = extract_docx_text(path)
    except Exception as exc:
        record_soft_exception("medical_admission_resolver.extract_text", exc, detail=str(path))
        return title_date

    explicit_date = extract_admission_date_from_primary_text(text)
    # Explicit rows like «Дата поступления: 23.06.2026» or table cells
    # «Дата поступления» -> «23.06.2026» are more reliable than a generic
    # title/table-neighbour date.  This prevents demographic rows from turning a
    # birth date into an admission date while still preserving legacy title-only
    # documents when no explicit admission marker exists.
    return explicit_date or title_date


def extract_discharge_date_from_primary_docx(path: str | Path) -> str:
    """Return a safe discharge date from a primary/discharge-source DOCX.

    Unlike admission, there is no title fallback here: a random title date is too
    often the document date or admission date.  Discharge is accepted only from
    explicit discharge/wypis context, so the renderer either uses the true date
    from the source or asks the doctor in the popup.
    """

    try:
        text = extract_docx_text(path)
    except Exception as exc:
        record_soft_exception("medical_discharge_resolver.extract_text", exc, detail=str(path))
        return ""
    return extract_discharge_date_from_primary_text(text)


def extract_admission_date_from_primary_text(text: str) -> str:
    value = normalize_text(text or "")
    if not value:
        return ""
    lines = [line.strip() for line in value.splitlines() if line.strip()]

    # Prefer line-level matches: labels and their values are normally in one row
    # or adjacent rows.  This also avoids accidentally crossing from patient
    # demographics into clinical text.
    for idx, line in enumerate(lines[:220]):
        line_date = _date_from_admission_context(line)
        if line_date:
            return line_date
        if _has_admission_marker(line):
            # Prefer the label line and the following cells/rows.  Including the
            # previous row first can capture a birth date from a demographic table
            # cell immediately above «Дата поступления».
            forward_neighbors = lines[idx: min(len(lines), idx + 4)]
            joined = " | ".join(forward_neighbors)
            joined_date = _date_from_admission_context(joined)
            if joined_date:
                return joined_date
            backward_neighbors = lines[max(0, idx - 1): min(len(lines), idx + 3)]
            joined = " | ".join(backward_neighbors)
            joined_date = _date_from_admission_context(joined)
            if joined_date:
                return joined_date

    # Whole-text fallback with a tight window around explicit admission markers.
    flat = normalize_text(" | ".join(lines[:260]))
    low = normalize_match(flat)
    for marker in _ADMISSION_MARKERS:
        start = 0
        marker_norm = normalize_match(marker)
        while True:
            pos = low.find(marker_norm, start)
            if pos < 0:
                break
            window_start = max(0, pos - 90)
            window_end = min(len(flat), pos + len(marker) + 140)
            window = flat[window_start:window_end]
            found = _best_non_birth_date(window)
            if found:
                return found
            start = pos + max(1, len(marker_norm))
    return ""


def extract_discharge_date_from_primary_text(text: str) -> str:
    value = normalize_text(text or "")
    if not value:
        return ""
    lines = [line.strip() for line in value.splitlines() if line.strip()]

    for idx, line in enumerate(lines[:260]):
        line_date = _date_from_discharge_context(line)
        if line_date:
            return line_date
        if _has_discharge_marker(line):
            forward_neighbors = lines[idx: min(len(lines), idx + 4)]
            joined = " | ".join(forward_neighbors)
            joined_date = _date_from_discharge_context(joined)
            if joined_date:
                return joined_date
            backward_neighbors = lines[max(0, idx - 1): min(len(lines), idx + 3)]
            joined = " | ".join(backward_neighbors)
            joined_date = _date_from_discharge_context(joined)
            if joined_date:
                return joined_date

    flat = normalize_text(" | ".join(lines[:320]))
    low = normalize_match(flat)
    for marker in _DISCHARGE_MARKERS:
        start = 0
        marker_norm = normalize_match(marker)
        while True:
            pos = low.find(marker_norm, start)
            if pos < 0:
                break
            window_start = max(0, pos - 90)
            window_end = min(len(flat), pos + len(marker) + 160)
            window = flat[window_start:window_end]
            found = _best_discharge_date(window)
            if found:
                return found
            start = pos + max(1, len(marker_norm))
    return ""


def _has_admission_marker(text: str) -> bool:
    low = normalize_match(text or "")
    return any(normalize_match(marker) in low for marker in _ADMISSION_MARKERS)


def _has_discharge_marker(text: str) -> bool:
    low = normalize_match(text or "")
    return any(normalize_match(marker) in low for marker in _DISCHARGE_MARKERS)


def _date_from_admission_context(text: str) -> str:
    if not _has_admission_marker(text):
        return ""
    return _best_non_birth_date(text)


def _date_from_discharge_context(text: str) -> str:
    if not _has_discharge_marker(text):
        return ""
    return _best_discharge_date(text)


def _best_non_birth_date(text: str) -> str:
    normalized = normalize_text(text or "")
    if not normalized:
        return ""
    candidates: list[tuple[int, str]] = []
    for match in _TITLE_DATE_RE.finditer(normalized):
        # In full-text admission windows a bare four-digit token is far more
        # often a birth year than a compact admission date. Keep compact
        # four-digit support in the title resolver, but do not let it override
        # a safe title date from full clinical text.
        if re.fullmatch(r"\d{4}", match.group(0).strip()):
            continue
        date_value = _normalize_full_date_match(match)
        if not date_value:
            continue
        if _date_has_birth_context_strict(normalized, match):
            continue
        distance = _distance_to_admission_marker(normalized, match.start())
        if distance is None:
            continue
        candidates.append((distance, date_value))
    if not candidates:
        return ""
    return sorted(candidates, key=lambda item: item[0])[0][1]


def _best_discharge_date(text: str) -> str:
    normalized = normalize_text(text or "")
    if not normalized:
        return ""
    candidates: list[tuple[int, str]] = []
    for match in _TITLE_DATE_RE.finditer(normalized):
        if re.fullmatch(r"\d{4}", match.group(0).strip()):
            continue
        date_value = _normalize_full_date_match(match)
        if not date_value:
            continue
        if _date_has_non_discharge_context(normalized, match):
            continue
        distance = _distance_to_discharge_marker(normalized, match.start())
        if distance is None:
            continue
        candidates.append((distance, date_value))
    if not candidates:
        return ""
    return sorted(candidates, key=lambda item: item[0])[0][1]


def _distance_to_admission_marker(text: str, pos: int) -> int | None:
    low = normalize_match(text or "")
    positions = [low.find(normalize_match(marker)) for marker in _ADMISSION_MARKERS if low.find(normalize_match(marker)) >= 0]
    if not positions:
        return None
    return min(abs(pos - marker_pos) for marker_pos in positions)


def _distance_to_discharge_marker(text: str, pos: int) -> int | None:
    low = normalize_match(text or "")
    positions = [low.find(normalize_match(marker)) for marker in _DISCHARGE_MARKERS if low.find(normalize_match(marker)) >= 0]
    if not positions:
        return None
    return min(abs(pos - marker_pos) for marker_pos in positions)


def _date_has_birth_context_strict(text: str, match: re.Match[str]) -> bool:
    if _date_match_has_birth_context(text, match):
        return True
    low = (text or "").lower().replace("ё", "е")
    before = low[max(0, match.start() - 120):match.start()]
    after = low[match.end():min(len(low), match.end() + 80)]
    around = before + " " + after
    admission_near = any(marker in normalize_match(around) for marker in _ADMISSION_MARKERS)
    birth_near = any(marker in around for marker in _BIRTH_MARKERS)
    if birth_near and not admission_near:
        return True
    if birth_near and admission_near:
        match_pos = match.start()
        birth_distance = _nearest_marker_distance(low, match_pos, _BIRTH_MARKERS)
        admission_distance = _nearest_marker_distance(normalize_match(text or ""), match_pos, _ADMISSION_MARKERS)
        if birth_distance is not None and admission_distance is not None and birth_distance <= admission_distance:
            return True
    return False


def _date_has_non_discharge_context(text: str, match: re.Match[str]) -> bool:
    if _date_match_has_birth_context(text, match):
        return True
    low_original = (text or "").lower().replace("ё", "е")
    around_original = low_original[max(0, match.start() - 140):min(len(low_original), match.end() + 100)]
    around = normalize_match(around_original)
    discharge_near = any(normalize_match(marker) in around for marker in _DISCHARGE_MARKERS)
    blocking_markers = _BIRTH_MARKERS + _ADMISSION_MARKERS
    blocker_near = any(normalize_match(marker) in around for marker in blocking_markers)
    if blocker_near and not discharge_near:
        return True
    if blocker_near and discharge_near:
        match_pos = match.start()
        blocker_distance = _nearest_marker_distance(normalize_match(text or ""), match_pos, blocking_markers)
        discharge_distance = _nearest_marker_distance(normalize_match(text or ""), match_pos, _DISCHARGE_MARKERS)
        if blocker_distance is not None and discharge_distance is not None and blocker_distance <= discharge_distance:
            return True
    return False


def _nearest_marker_distance(text: str, pos: int, markers: tuple[str, ...]) -> int | None:
    distances: list[int] = []
    normalized_text = normalize_match(text or "")
    for marker in markers:
        marker_norm = normalize_match(marker)
        start = 0
        while True:
            found = normalized_text.find(marker_norm, start)
            if found < 0:
                break
            distances.append(abs(pos - found))
            start = found + max(1, len(marker_norm))
    return min(distances) if distances else None


def assert_admission_resolver_lock() -> None:
    if ADMISSION_RESOLVER_LOCK_VERSION != "v1.4":
        raise AssertionError("Admission resolver lock changed unexpectedly")
    if not ADMISSION_RESOLVER_REJECTS_BIRTH_CONTEXT:
        raise AssertionError("Admission resolver must reject birth-date contexts")
    if not ADMISSION_RESOLVER_USES_EXPLICIT_ADMISSION_MARKERS:
        raise AssertionError("Admission resolver must require explicit admission markers")
    if not ADMISSION_RESOLVER_EXPLICIT_MARKERS_OVERRIDE_BIRTHY_TITLE:
        raise AssertionError("Admission resolver must prefer explicit admission markers over birth-like title-neighbour dates")
    if not ADMISSION_RESOLVER_COMPARES_MARKER_DISTANCE_WITH_ORIGINAL_POSITIONS:
        raise AssertionError("Admission resolver must compare birth/admission marker distance using stable positions")
    if not DISCHARGE_RESOLVER_USES_EXPLICIT_DISCHARGE_MARKERS:
        raise AssertionError("Discharge resolver must require explicit discharge markers")
    if not DISCHARGE_RESOLVER_REJECTS_ADMISSION_AND_BIRTH_CONTEXT:
        raise AssertionError("Discharge resolver must reject admission/birth contexts")
    if extract_admission_date_from_primary_text("Data urodzenia\n04.01.2000\nData przyjęcia\n23.06.2026") != "23.06.2026":
        raise AssertionError("Polish admission resolver must not prefer birth date over admission date")
    if extract_admission_date_from_primary_text("Дата рождения\n04.01.2000\nДата поступления\n23.06.2026") != "23.06.2026":
        raise AssertionError("Admission resolver must not prefer birth date over adjacent admission date")
    if extract_admission_date_from_primary_text("10.06.2026 Первичный осмотр\nГод рождения: 1980\nВ 3 отделение КДП поступает добровольно") == "01.09.1980":
        raise AssertionError("Bare birth years must not override the admission/title date")
    if extract_discharge_date_from_primary_text("Дата рождения\n04.01.2000\nДата поступления\n23.06.2026\nДата выписки\n30.06.2026") != "30.06.2026":
        raise AssertionError("Discharge resolver must pick explicit discharge date")
    if extract_discharge_date_from_primary_text("Дата рождения 04.01.2000 Дата поступления 23.06.2026"):
        raise AssertionError("Discharge resolver must not invent discharge date from birth/admission dates")
