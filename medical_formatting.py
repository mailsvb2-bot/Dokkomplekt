"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from medical_constants import DATE_FMT
from medical_text_utils import normalize_text

def format_date_with_russian_year_suffix(value: str) -> str:
    """Return UI date text with exactly one trailing " г." for document headers."""
    value = normalize_text(value)
    if not value:
        return ""
    value = re.sub(r"\s*(?:г\.?|год)\s*$", "", value, flags=re.IGNORECASE).strip()
    return f"{value} г."


def format_birth_for_person_line(value: str) -> str:
    """Format birth value for compact lines without duplicating ``г.р.``."""
    value = normalize_text(value)
    if not value:
        return ""
    if re.search(r"г\.?\s*р\.?(?:\s|$)", value, flags=re.IGNORECASE):
        return value
    return f"{value} г.р."


# -----------------------------------------------------------------------------
# Расчёт сроков лечения
# -----------------------------------------------------------------------------

def calculate_inclusive_treatment_days(admission_date: str, commission_date: str) -> int | None:
    """Количество дней лечения от даты поступления до даты комиссии включительно."""
    start = parse_date(admission_date)
    finish = parse_date(commission_date)
    if not start or not finish:
        return None
    days = (finish.date() - start.date()).days + 1
    return days if days >= 1 else None


def _decline_russian_district_name(value: str) -> str:
    """Return genitive masculine form for common district names.

    Нужно для фразы: "военного комиссариата <...> района".
    Врач вводит привычно "Автозаводский"/"Ленинский"/"Сормовский",
    а документ должен получить "Автозаводского"/"Ленинского"/"Сормовского".
    """
    value = normalize_text(value).strip(" .,;:")
    if not value:
        return ""
    low = value.lower().replace("ё", "е")
    explicit = {
        "автозаводский": "Автозаводского",
        "автозаводского": "Автозаводского",
        "ленинский": "Ленинского",
        "ленинского": "Ленинского",
        "советский": "Советского",
        "советского": "Советского",
        "московский": "Московского",
        "московского": "Московского",
        "канавинский": "Канавинского",
        "канавинского": "Канавинского",
        # Частая опечатка пользователя/документа без второй "а".
        "канвинский": "Канавинского",
        "канвинского": "Канавинского",
        "нижегородский": "Нижегородского",
        "нижегородского": "Нижегородского",
        "приокский": "Приокского",
        "приокского": "Приокского",
        "сормовский": "Сормовского",
        "сормовского": "Сормовского",
    }
    if low in explicit:
        return explicit[low]
    if low.endswith(("ского", "цкого", "ого")):
        return value
    if low.endswith("ский"):
        return value[:-4] + "ского"
    if low.endswith("цкий"):
        return value[:-4] + "цкого"
    if low.endswith(("ый", "ой")):
        return value[:-2] + "ого"
    return value


def format_military_commissariat_area(value: str) -> str:
    """Normalize user input for phrase: военного комиссариата <...> района.

    Поддерживает один район и связки: "Сормовский и Канвинского",
    "Автозаводский, Ленинский". Слово "района" добавляется один раз в конце.
    """
    value = normalize_text(value)
    if not value:
        return ""
    base = value.strip(" .,;")
    base = re.sub(r"^по\s+направлению\s+из\s+", "", base, flags=re.IGNORECASE).strip(" .,;")
    base = re.sub(r"^(?:военного\s+комиссариата|военкомата)\s+", "", base, flags=re.IGNORECASE).strip(" .,;")
    base = re.sub(r"\s+(?:военного\s+комиссариата|военкомат)(?:а|у|е|ом)?\s*$", "", base, flags=re.IGNORECASE).strip(" .,;")
    base = re.sub(r"\s+район(?:а|у|е|ом)?\s*$", "", base, flags=re.IGNORECASE).strip(" .,;")
    if not base:
        return ""

    tokens = re.split(r"(\s+и\s+|\s*,\s*|\s*/\s*|\s*\\\s*)", base, flags=re.IGNORECASE)
    out: list[str] = []
    for token in tokens:
        if not token:
            continue
        if re.fullmatch(r"\s+и\s+", token, flags=re.IGNORECASE):
            out.append(" и ")
        elif re.fullmatch(r"\s*,\s*", token):
            out.append(", ")
        elif re.fullmatch(r"\s*/\s*|\s*\\\s*", token):
            out.append(" и ")
        else:
            out.append(_decline_russian_district_name(token))
    normalized = "".join(out).strip(" ,;")
    normalized = re.sub(r"\s+", " ", normalized)
    return f"{normalized} района" if normalized else ""



def format_military_commissariat_referral(value: str) -> str:
    """Phrase for primary exam: «По направлению из ... военкомата».

    The RVK act needs «военного комиссариата <...> района», while the
    primary exam must use the doctor's requested wording with «из ...
    военкомата».
    """
    value = normalize_text(value)
    if not value:
        return ""
    base = value.strip(" .,;")
    base = re.sub(r"^по\s+направлению\s+из\s+", "", base, flags=re.IGNORECASE).strip(" .,;")
    base = re.sub(r"^(?:военного\s+комиссариата|военкомата)\s+", "", base, flags=re.IGNORECASE).strip(" .,;")
    base = re.sub(r"\s+(?:военного\s+комиссариата|военкомат)(?:а|у|е|ом)?\s*$", "", base, flags=re.IGNORECASE).strip(" .,;")
    base = re.sub(r"\s+район(?:а|у|е|ом)?\s*$", "", base, flags=re.IGNORECASE).strip(" .,;")
    if not base:
        return ""
    tokens = re.split(r"(\s+и\s+|\s*,\s*|\s*/\s*|\s*\\\s*)", base, flags=re.IGNORECASE)
    out: list[str] = []
    for token in tokens:
        if not token:
            continue
        if re.fullmatch(r"\s+и\s+", token, flags=re.IGNORECASE):
            out.append(" и ")
        elif re.fullmatch(r"\s*,\s*", token):
            out.append(", ")
        elif re.fullmatch(r"\s*/\s*|\s*\\\s*", token):
            out.append(" и ")
        else:
            out.append(_decline_russian_district_name(token))
    normalized = re.sub(r"\s+", " ", "".join(out).strip(" ,;"))
    return f"По направлению из {normalized} военкомата" if normalized else ""

def russian_day_word(days: int) -> str:
    if 11 <= days % 100 <= 14:
        return "дней"
    last = days % 10
    if last == 1:
        return "день"
    if 2 <= last <= 4:
        return "дня"
    return "дней"


def treatment_period_text(admission_date: str, commission_date: str) -> str:
    days = calculate_inclusive_treatment_days(admission_date, commission_date)
    if admission_date and days:
        return f"Находится на лечении с {admission_date} ({days} {russian_day_word(days)})"
    if admission_date:
        return f"Находится на лечении с {admission_date} (всего дней)"
    return "Находится на лечении с (всего дней)"


def _two_digit_year_to_full(year: int) -> int:
    return year + (2000 if year < 70 else 1900) if year < 100 else year


def _candidate_date(year: int, month: int, day: int) -> Optional[datetime]:
    year = _two_digit_year_to_full(year)
    # Medical document dates are patient/episode dates, not arbitrary calendar
    # values. Keeping the same sane bounds as the diary parser prevents a typo
    # like 01.01.3026 or 01.01.1800 from silently entering generated DOCX.
    if year < 1900 or year > 2200:
        return None
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def _parse_compact_date_digits(digits: str) -> Optional[datetime]:
    """Parse date digits typed without separators.

    Supported examples:
    - 10052026 -> 10.05.2026
    - 100526   -> 10.05.2026
    - 1126     -> 01.01.2026

    The 4/5/7 digit modes intentionally support missing leading zeroes in
    day/month fields (``1`` means ``01``) without treating a bare year like
    ``2026`` as a date.
    """
    if not re.fullmatch(r"\d{4,8}", digits or ""):
        return None

    def make(d_len: int, m_len: int, y_len: int) -> Optional[datetime]:
        if d_len + m_len + y_len != len(digits):
            return None
        day = int(digits[:d_len])
        month = int(digits[d_len:d_len + m_len])
        year = int(digits[d_len + m_len:])
        return _candidate_date(year, month, day)

    ordered_patterns: list[tuple[int, int, int]] = []
    if len(digits) == 8:
        ordered_patterns = [(2, 2, 4)]
    elif len(digits) == 6:
        ordered_patterns = [(2, 2, 2)]
    elif len(digits) == 4:
        # 1126 -> 01.01.2026. Avoid false-positive bare years: 2026 has
        # month 0 and therefore fails validation.
        ordered_patterns = [(1, 1, 2)]
    elif len(digits) == 5:
        # Prefer 1/05/26 for 10526, but 31/1/26 for 31126.
        ordered_patterns = [(2, 1, 2), (1, 2, 2)] if int(digits[:2]) > 12 else [(1, 2, 2), (2, 1, 2)]
    elif len(digits) == 7:
        # Prefer 1/05/2026 for 1052026, but 31/1/2026 for 3112026.
        ordered_patterns = [(2, 1, 4), (1, 2, 4)] if int(digits[:2]) > 12 else [(1, 2, 4), (2, 1, 4)]

    for pattern in ordered_patterns:
        parsed = make(*pattern)
        if parsed:
            return parsed
    return None

_PL_MONTHS = {
    "stycznia": 1, "styczen": 1, "styczeń": 1,
    "lutego": 2, "luty": 2,
    "marca": 3, "marzec": 3,
    "kwietnia": 4, "kwiecien": 4, "kwiecień": 4,
    "maja": 5, "maj": 5,
    "czerwca": 6, "czerwiec": 6,
    "lipca": 7, "lipiec": 7,
    "sierpnia": 8, "sierpien": 8, "sierpień": 8,
    "wrzesnia": 9, "września": 9, "wrzesien": 9, "wrzesień": 9,
    "pazdziernika": 10, "października": 10, "pazdziernik": 10, "październik": 10,
    "listopada": 11, "listopad": 11,
    "grudnia": 12, "grudzien": 12, "grudzień": 12,
}


def _parse_polish_textual_date(value: str) -> Optional[datetime]:
    match = re.fullmatch(r"(\d{1,2})\s+([A-Za-zĄąĆćĘęŁłŃńÓóŚśŹźŻż]+)\s+(\d{2}|\d{4})", value.strip(), flags=re.IGNORECASE)
    if not match:
        return None
    month_key = match.group(2).lower()
    month_key = month_key.replace("ą", "a").replace("ć", "c").replace("ę", "e").replace("ł", "l").replace("ń", "n").replace("ó", "o").replace("ś", "s").replace("ź", "z").replace("ż", "z")
    month = _PL_MONTHS.get(match.group(2).lower()) or _PL_MONTHS.get(month_key)
    if not month:
        return None
    return _candidate_date(int(match.group(3)), month, int(match.group(1)))

def parse_date(value: str) -> Optional[datetime]:
    value = normalize_text(value)
    value = re.sub(r"\s*(?:г\.?|год)\s*$", "", value, flags=re.IGNORECASE).strip()
    if not value:
        return None

    textual = _parse_polish_textual_date(value)
    if textual:
        return textual

    match = re.fullmatch(r"(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2}|\d{4})", value)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))
        return _candidate_date(year, month, day)

    # Врач часто вводит дату без разделителей: 10052026, 100526 или
    # совсем коротко 1126 (= 01.01.2026).
    return _parse_compact_date_digits(value)


def safe_filename(value: str) -> str:
    value = normalize_text(value) or "Пациент"
    # Windows запрещает эти символы в имени файла. Заменяем их пробелами,
    # а не подчёркиваниями: итоговые документы должны сохраняться как
    # «Сидоров Иван Михайлович Выписной эпикриз.docx».
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", value)
    value = re.sub(r"\s+", " ", value)
    value = value.strip(". ")[:80].rstrip(". ") or "Пациент"
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    # Windows treats device names as reserved even when an extension is present
    # (for example ``CON.txt`` / ``LPT1.docx``). Protect both exact names and
    # dotted variants before appending document suffixes.
    stem_for_reserved_check = value.split(".", 1)[0].upper()
    if stem_for_reserved_check in reserved:
        value = f"{value}_"
    return value


def available_path(path: Path) -> Path:
    if not path.exists():
        return path
    base = path.with_suffix("")
    ext = path.suffix
    for counter in range(2, 10000):
        candidate = Path(f"{base} ({counter}){ext}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Не удалось подобрать имя файла для {path}")


def strip_leading_epi_label(text: str) -> str:
    """Убирает дублирующую метку из ЭПИ-файла: «ЭПИ: ...» -> «...»."""
    text = normalize_text(text)
    text = re.sub(r"^эпи\s*[:()№N#.-]*\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


# --- Technical privacy helpers for logs/reports ---
import hashlib as _hashlib
import re as _re

TECHNICAL_PRIVACY_LOCK_VERSION = "v1.0"

_PATH_RE = _re.compile(r"(?:[A-Za-z]:\\[^\n\r\t]+|/[^\n\r\t]+)")
_DATE_RE = _re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")
_CASE_RE = _re.compile(r"(?:истори[яи]\s*болезни\s*)?№\s*[\w\-/.]+", flags=_re.I)


def technical_ref(*values: object) -> str:
    """Return a stable non-reversible short reference for support logs."""

    material = "\u241f".join(str(value or "").strip() for value in values if str(value or "").strip())
    if not material:
        material = "empty"
    return "ref-" + _hashlib.sha256(material.encode("utf-8", errors="ignore")).hexdigest()[:12]


def path_kind(value: object) -> str:
    """Describe a path without exposing its folder/name contents."""

    suffix = Path(str(value or "")).suffix.lower().lstrip(".")
    return suffix or "path"


def redact_technical_text(value: object, *, limit: int = 220) -> str:
    """Remove obvious paths, dates and case numbers from technical text."""

    text = " ".join(str(value or "").split())
    text = _PATH_RE.sub("<path>", text)
    text = _DATE_RE.sub("<date>", text)
    text = _CASE_RE.sub("<case>", text)
    text = re.sub(r"\b[А-ЯЁ][а-яё]+_[А-ЯЁ][а-яё]+(?:_[А-ЯЁ][а-яё]+)?\b", "<person>", text)
    text = re.sub(r"\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\b", "<person>", text)
    text = re.sub(r"[^\s\"']+\.(?:docx|docm|pdf|txt|json|jsonl|csv)\b", "<file>", text, flags=re.IGNORECASE)
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def technical_count_label(paths) -> str:
    """Return a count-only path summary for technical reports."""

    items = list(paths or ())
    return f"{len(items)} файл(ов)"



def technical_history_root() -> Path:
    """Return the root app-data folder for support history."""

    import os

    configured = os.environ.get("MEDICAL_AUTOFILL_HISTORY_DIR", "").strip()
    if configured:
        return Path(configured).expanduser() / "_medical_autofill_history"
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return base / "MedicalDiaryAutofill" / "_medical_autofill_history"
    return Path.home() / ".medical_diary_autofill" / "_medical_autofill_history"


def history_dir(base_dir: str | Path) -> Path:
    """Return a deterministic support folder outside the patient/output folder."""

    root = Path(base_dir).expanduser()
    key = _hashlib.sha1(str(root).encode("utf-8", errors="ignore")).hexdigest()[:16]
    return technical_history_root() / "generation" / key


def technical_report_path(base_dir: str | Path, filename: str) -> Path:
    """Return a technical report path outside patient/output folders."""

    safe_name = Path(str(filename or "report.txt")).name
    folder = history_dir(base_dir)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / safe_name

def assert_technical_privacy_lock() -> None:
    if TECHNICAL_PRIVACY_LOCK_VERSION != "v1.0":
        raise AssertionError("Technical privacy lock changed unexpectedly")
    sample = r"C:\Users\Doctor\Выписанные пациенты\Иванов И.И\custom.docx 11.06.2026 история болезни № 123"
    redacted = redact_technical_text(sample)
    forbidden = ("Иванов", "11.06.2026", "123", "Users")
    if any(item in redacted for item in forbidden):
        raise AssertionError("Technical privacy redaction leaked identifying sample data")
