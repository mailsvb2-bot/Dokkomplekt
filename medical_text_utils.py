"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

from diagnostic_logging import record_soft_exception
import re
from dataclasses import fields, is_dataclass
from typing import Any, Sequence


FORBIDDEN_HOSPITALIZATION_PHRASE = "Целесообразна госпитализация пациентки в 3 отделение КДП"
_FORBIDDEN_HOSPITALIZATION_PATTERNS = (
    re.compile(
        r"\s*Целесообразна\s+госпитализация\s+пациент(?:а|ки)?\s+в\s+3\s+отделение\s+КДП\s*[\.;,]?\s*",
        flags=re.IGNORECASE,
    ),
)


def remove_forbidden_hospitalization_phrases(text: str) -> str:
    """Remove service hospitalization-decision phrase from parsed/final text."""
    value = str(text or "")
    if not value:
        return ""
    updated = value
    for pattern in _FORBIDDEN_HOSPITALIZATION_PATTERNS:
        updated = pattern.sub(" ", updated)
    updated = re.sub(r"[ \t]{2,}", " ", updated)
    updated = re.sub(r"\s+([,.;:])", r"\1", updated)
    updated = re.sub(r"(?:^|\n)\s*\.\s*(?=\n|$)", "\n", updated)
    return updated.strip()


def sanitize_patient_data_forbidden_phrases(data: Any) -> Any:
    """Sanitize all string fields of a dataclass-like patient object in-place."""
    if data is None:
        return data
    names = [field.name for field in fields(data)] if is_dataclass(data) else [name for name in dir(data) if not name.startswith("_")]
    for name in names:
        try:
            value = getattr(data, name)
        except Exception as exc:
            record_soft_exception("medical_text_utils.getattr", exc, detail=name)
            continue
        if isinstance(value, str) and value:
            cleaned = remove_forbidden_hospitalization_phrases(value)
            if cleaned != value:
                try:
                    setattr(data, name, cleaned)
                except Exception as exc:
                    record_soft_exception("medical_text_utils.setattr", exc, detail=name)
                    continue
    return data


DASHES = {
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2212": "-",
}


def normalize_text(text: str) -> str:
    if not text:
        return ""
    for src, dst in DASHES.items():
        text = text.replace(src, dst)
    text = text.replace("\xa0", " ")
    text = text.replace("\v", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_match(text: str) -> str:
    text = normalize_text(text).lower().replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_value(text: str) -> str:
    text = normalize_text(text)
    text = text.strip(" \t:-—–,;")
    text = re.sub(r"^сюда\s+подстав(?:лять|ляется).*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^нужно\s*/\s*не\s*нужно$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(состоит\s*/\s*не\s*состоит)\s*[:.-]?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(нужен\s*/\s*не\s*нужен)\s*[:.-]?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(нужно\s*/\s*не\s*нужно)\s*[:.-]?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(да\s*/\s*нет)\s*[:.-]?\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def looks_like_label(value: str) -> bool:
    """Return True for standalone field captions, including Polish aliases.

    This guard prevents parser/scanner values from swallowing the next caption
    in doctor-owned DOCX/DOCM templates while staying country-neutral: labels are
    used only as stop markers and never as embedded document content.
    """
    value = normalize_match(value)
    if not value:
        return False
    known = [
        "год рождения",
        "дата рождения",
        "зарегистрирован",
        "проживает",
        "на учете",
        "работает",
        "место работы",
        "должность",
        "больничный лист",
        "оформление инвалидности",
        "направление от рвк",
        "в 3 отделение",
        "жалобы",
        "анамнез",
        "психический статус",
        "соматический статус",
        "сомато-неврологический статус",
        "план обследования",
        "план лечения",
        "на основании",
        "клинический диагноз",
        "предварительный диагноз",
        "основной диагноз",
        "заключительный диагноз",
        "диагноз",
        "эпидемиологический",
        "врач",
        "зав",
        "data urodzenia",
        "nr historii choroby",
        "numer historii choroby",
        "data przyjęcia",
        "data przyjecia",
        "data wypisu",
        "skargi",
        "dolegliwości",
        "dolegliwosci",
        "wywiad",
        "stan psychiczny",
        "stan somatyczny",
        "stan przedmiotowy",
        "rozpoznanie",
        "diagnoza",
        "leczenie",
        "plan leczenia",
        "zalecenia",
        "lekarz",
        "ordynator",
    ]
    return any(value.startswith(k) for k in known)

DIAGNOSIS_STOP_MARKERS: Sequence[str] = (
    "Дата, время", "Дата поступления", "Дата госпитализации", "Дата приема", "Дата приёма", "Дата осмотра", "Дата выписки",
    "История болезни №", "Ф.И.О.", "ФИО", "Год рождения", "Дата рождения",
    "Зарегистрирован", "Проживает", "Место жительства", "Адрес", "Работает", "Место работы",
    "Должность", "Больничный лист", "Оформление инвалидности", "Направление от РВК",
    "В 3 отделение КДП поступает", "Жалобы на момент осмотра", "Жалобы при поступлении", "Жалобы",
    "Анамнез жизни", "Анамнез заболевания", "Психический статус при поступлении", "Психический статус",
    "Соматический статус", "Сомато-неврологический статус", "План обследования", "План лечения", "Назначенное лечение",
    "Клинический диагноз", "Предварительный диагноз", "Основной диагноз", "Заключительный диагноз", "Диагноз", "Назначенное лечение", "Лечение", "Эпидемиологический анамнез", "Результаты обследований", "Результаты исследований",
    "ЭЭГ", "ЭПИ", "За время лечения", "Рекомендовано", "Экспертный анамнез",
    "Врач психиатр", "Врач-психиатр", "Лечащий врач", "Зав. отделением", "Зав.отделением",
    "Зав. отд.", "Зав отд", "Зам глав врача", "Зам. гл. врача",
    "Data przyjęcia", "Data przyjecia", "Data hospitalizacji", "Data wypisu",
    "Historia choroby", "Nr historii choroby", "Numer historii choroby", "Pacjent", "Pacjentka",
    "Imię i nazwisko", "Imie i nazwisko", "Data urodzenia", "PESEL",
    "Skargi", "Dolegliwości", "Dolegliwosci", "Wywiad chorobowy", "Wywiad życiowy", "Wywiad zyciowy",
    "Stan psychiczny", "Stan somatyczny", "Stan przedmiotowy", "Plan leczenia", "Zalecone leczenie",
    "Zastosowane leczenie", "Leczenie", "Rozpoznanie kliniczne", "Rozpoznanie", "Diagnoza",
    "Wyniki badań", "Wyniki badan", "Zalecenia", "Lekarz", "Lekarz prowadzący", "Lekarz prowadzacy",
    "Ordynator", "Kierownik oddziału", "Kierownik oddzialu",
)


# --- Case/history number guards ---
_CASE_LABEL_RE = re.compile(
    r"^\s*(?:история\s+болезни|ист\.?\s*бол\.?|иб|№\s*истории\s*болезни)\s*(?:№|n|no|#)?\s*[:№n#.-]*\s*",
    re.IGNORECASE,
)
_CASE_LABEL_ANYWHERE_RE = re.compile(
    r"(?:история\s+болезни|ист\.?\s*бол\.?|иб|№\s*истории\s*болезни)\s*(?:№|n|no|#)?\s*[:№n#.-]*\s*(.+)$",
    re.IGNORECASE,
)
_LEADING_CASE_SIGN_RE = re.compile(r"^\s*(?:№|n|no|#)\s*", re.IGNORECASE)
_PATIENT_LABEL_RE = re.compile(
    r"^\s*(?:ф\.?\s*и\.?\s*о\.?|фио|фамилия\s+имя\s+отчество|пациент|больной)\s*[:№n#.-]*\s*",
    re.IGNORECASE,
)
_NAME_WORD_RE = re.compile(r"^[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?$")
_CASE_TOKEN_RE = re.compile(r"^(?:№\s*)?[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9/_.-]*\d[A-Za-zА-Яа-яЁё0-9/_.-]*$")
_FIO_WITH_CASE_TAIL_RE = re.compile(
    r"^\s*"
    r"(?:[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+){1,3}"
    r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?"
    r"\s+(?P<tail>(?:№\s*)?[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9/_.-]*\d[A-Za-zА-Яа-яЁё0-9/_.-]*)\s*$"
)
_SURNAME_INITIALS_WITH_CASE_TAIL_RE = re.compile(
    r"^\s*"
    r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+"
    r"(?:[А-ЯЁ]\.\s*){1,2}"
    r"(?P<tail>(?:№\s*)?[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9/_.-]*\d[A-Za-zА-Яа-яЁё0-9/_.-]*)\s*$"
)


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip(" \t\r\n,;:.—–-")


def _strip_case_number_prefix(value: str) -> str:
    text = _compact(value)
    while True:
        cleaned = _compact(_LEADING_CASE_SIGN_RE.sub("", text))
        if cleaned == text:
            return cleaned
        text = cleaned


def _case_number_tail_from_name_spillover(text: str) -> str:
    """Extract numeric case-number tail from accidental patient-name capture.

    Real DOCX tables sometimes expose neighbouring cells as one stream, for
    example ``История болезни № Иванов Иван Иванович 123``.  Rejecting the whole
    value loses the real number; accepting it puts ФИО into every popup.  Keep
    only a compact tail that has a clear case-number signal.
    """
    for pattern in (_FIO_WITH_CASE_TAIL_RE, _SURNAME_INITIALS_WITH_CASE_TAIL_RE):
        match = pattern.match(text or "")
        if not match:
            continue
        tail = _strip_case_number_prefix(match.group("tail"))
        if _CASE_TOKEN_RE.match(tail):
            return tail
    return ""


def _normalize_for_compare(value: str) -> str:
    value = _compact(value).lower().replace("ё", "е")
    value = re.sub(r"[^а-яa-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def looks_like_patient_name(value: str, *, patient_name: str = "") -> bool:
    """Return True for values that look like an FIO, not a case number."""
    text = _compact(_PATIENT_LABEL_RE.sub("", _CASE_LABEL_RE.sub("", value or "")))
    if not text:
        return False

    normalized = _normalize_for_compare(text)
    patient_normalized = _normalize_for_compare(patient_name)
    if patient_normalized and (
        normalized == patient_normalized
        or normalized.startswith(patient_normalized + " ")
        or patient_normalized.startswith(normalized + " ")
    ):
        return True

    # Case numbers almost always contain digits or compact delimiters.  A value
    # made from two/three title-cased Cyrillic words is almost certainly ФИО.
    if any(ch.isdigit() for ch in text):
        return False
    words = [part for part in re.split(r"[\s,;]+", text) if part]
    cyrillic_name_words = [word for word in words if _NAME_WORD_RE.match(word)]
    if len(cyrillic_name_words) >= 2 and len(cyrillic_name_words) == len(words):
        return True
    return False


def sanitize_case_number_candidate(value: str, *, patient_name: str = "") -> str:
    """Clean a parsed/default case number and reject patient-name spillover."""
    text = _compact(value or "")
    if not text:
        return ""

    # If a noisy line contains the case-number label after the patient name,
    # trust the labelled tail instead of rejecting the whole line as ФИО.
    labelled_inside = _CASE_LABEL_ANYWHERE_RE.search(text)
    if labelled_inside and labelled_inside.start() > 0:
        return sanitize_case_number_candidate(labelled_inside.group(1), patient_name=patient_name)

    text = _compact(_CASE_LABEL_RE.sub("", text))
    text = _compact(_PATIENT_LABEL_RE.sub("", text))
    text = _strip_case_number_prefix(text)
    if not text:
        return ""

    tail = _case_number_tail_from_name_spillover(text)
    if tail:
        return tail

    # Common parser spillover: "Иванов Иван Иванович, 123".  Keep only the
    # useful numeric tail if it exists; otherwise reject the FIO completely.
    comma_parts = [_compact(part) for part in re.split(r"[,;]", text) if _compact(part)]
    if comma_parts and looks_like_patient_name(comma_parts[0], patient_name=patient_name):
        for part in comma_parts[1:]:
            if re.search(r"\d", part) and not looks_like_patient_name(part, patient_name=patient_name):
                return part
        return ""

    if looks_like_patient_name(text, patient_name=patient_name):
        return ""
    return _strip_case_number_prefix(text)


def is_valid_case_number_value(value: str, *, patient_name: str = "") -> bool:
    cleaned = sanitize_case_number_candidate(value, patient_name=patient_name)
    return bool(cleaned) and cleaned == _compact(value or "")
