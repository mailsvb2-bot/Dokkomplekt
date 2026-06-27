from __future__ import annotations

import re

from medical_text_utils import DIAGNOSIS_STOP_MARKERS, clean_value, looks_like_label

def _looks_like_template_or_admin_noise(value: str) -> bool:
    """Reject non-diagnosis fragments captured from templates or setup notes.

    The parser should be universal, but the UI diagnosis field must never show
    phrases such as "лечение и подпись...", names of commissions, template
    instructions, button names, or other document-construction text.  Such text
    is safer to leave blank and ask the doctor than to inject into documents.
    """
    cleaned = clean_value(value)
    if not cleaned:
        return True
    low = cleaned.lower()

    # A real ICD-10 style code is a strong signal that the value is a diagnosis.
    if re.search(r"(?<![A-Za-zА-Яа-я])[A-ZА-Я][0-9]{2}(?:\.[0-9A-ZА-Я]+)?(?![A-Za-zА-Яа-я0-9])", cleaned, flags=re.IGNORECASE):
        return False

    if re.match(r"^\s*(?:лечение|назначенное\s+лечение|план\s+лечения)\b", low):
        return True

    admin_words = (
        "подпись", "подпис", "кнопк", "шаблон", "документ", "попап",
        "вк на мсэ", "мсэ", "рвк", "комисс", "эпикриз", "лист",
        "галочк", "выбира", "созда", "встав", "подстав", "поле",
        "части", "часть", "название", "файл", "блок 03",
    )
    hits = sum(1 for word in admin_words if word in low)
    if hits >= 2:
        return True
    if hits >= 1 and re.search(r"\b(?:где|куда|котор|нужно|надо|для|чтобы|или)\b", low):
        return True

    # Long comma-separated task/instruction fragments with no code and no clear
    # disease wording are not diagnoses.  Leave them empty for doctor override.
    if len(cleaned) > 90 and hits >= 1:
        return True
    return False


def sanitize_diagnosis(value: str) -> str:
    """Вернуть только медицинскую формулировку диагноза без соседних блоков.

    В реальных первичных DOCX диагноз встречается в разных стилях:
    "Диагноз: F...", "был выставлен диагноз: F...", "установлен диагноз: F...".
    Раньше при однострочной записи парсер мог захватить следующий раздел
    (например, "Жалобы"/"Лечение"/"Врач") и подставить его в строку диагноза.
    Здесь диагноз жёстко очищается перед показом в UI и перед рендерингом.
    """
    value = clean_value(value)
    if not value:
        return ""

    # Если в значение попала вся фраза "На основании... установлен диагноз:",
    # оставляем только хвост после служебной формулы. Не режем диагнозы, где
    # слово "диагноз" является частью пользовательского текста после кода F.
    value = re.sub(
        r"^\s*(?:на\s+основании\s+данных.*?\s+)?(?:был\s+выставлен|выставлен|установлен)?\s*диагноз\s*[:.-]?\s*",
        "",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()
    value = clean_value(value)

    # Обрезаем всё, что начинается как следующий раздел документа. Поддерживаем
    # и перенос строки, и компактную запись в одну строку: "F20... Жалобы: ...".
    best = len(value)
    for marker in DIAGNOSIS_STOP_MARKERS:
        marker_pattern = re.escape(marker).replace(r"\ ", r"\s+")
        patterns = (
            rf"\n\s*{marker_pattern}\s*(?:[:№N#.-]|\n|$)",
            rf"(?<![А-Яа-яA-Za-z0-9]){marker_pattern}(?![А-Яа-яA-Za-z0-9])\s*(?:[:№N#.-]|\n|$)",
        )
        for pattern in patterns:
            m = re.search(pattern, value, flags=re.IGNORECASE)
            if m and 0 < m.start() < best:
                best = m.start()
    value = clean_value(value[:best])

    # Частые шаблонные остатки. "F" в пустом шаблоне — не диагноз.
    if re.fullmatch(r"[A-ZА-Я]?\s*\.?", value, flags=re.IGNORECASE):
        return ""
    if looks_like_label(value):
        return ""
    if _looks_like_template_or_admin_noise(value):
        return ""
    return value
