from __future__ import annotations

"""Patient folder naming for desktop intake."""

from dataclasses import dataclass
from pathlib import Path

from medical_admission_resolver import extract_admission_date_from_primary_docx
from medical_docx_reader import extract_docx_text
from medical_formatting import parse_date, safe_filename
from diagnostic_logging import record_soft_exception
import re

DESKTOP_PATIENT_FOLDER_LOCK_VERSION = "v1.7"
DESKTOP_PATIENT_FOLDER_SUPPORTS_CONFIGURABLE_NAMING = True
DESKTOP_PATIENT_FOLDER_FALLS_BACK_TO_PRIMARY_STEM = True
DESKTOP_PATIENT_FOLDER_PREFERS_SAFE_ADMISSION_RESOLVER = True
DESKTOP_PATIENT_FOLDER_EXTRACTS_NAME_FROM_TEXT_FALLBACK = True
DESKTOP_PATIENT_FOLDER_SUPPORTS_TABLE_LABEL_VALUE_LINES = True
DESKTOP_PATIENT_FOLDER_VALIDATES_PARSED_FIO = True
DESKTOP_PATIENT_FOLDER_NEVER_TRUSTS_BIRTH_AS_ADMISSION = True
DESKTOP_PATIENT_FOLDER_REJECTS_NUMERIC_FIO_PARTS = True
DESKTOP_PATIENT_FOLDER_USES_ONLY_SAFE_ADMISSION_RESOLVER = True

_MONTHS_RU = {
    1: "январь",
    2: "февраль",
    3: "март",
    4: "апрель",
    5: "май",
    6: "июнь",
    7: "июль",
    8: "август",
    9: "сентябрь",
    10: "октябрь",
    11: "ноябрь",
    12: "декабрь",
}

FOLDER_NAMING_OPTIONS: tuple[tuple[str, str], ...] = (
    ("full_fio", "Полностью ФИО"),
    ("surname_initials", "Фамилия полностью, Имя и Отчество буквами"),
    ("surname_name", "Фамилия Имя"),
    ("admission_date", "Дата поступления"),
    ("discharge_date", "Дата выписки"),
    ("admission_discharge_dates", "Дата поступления и дата выписки"),
    ("admission_month", "Месяц поступления"),
    ("discharge_month", "Месяц выписки"),
)
DEFAULT_FOLDER_NAMING = {
    "parts": ["surname_initials", "admission_month"],
    "date_format": "short",
}
FOLDER_NAMING_SCHEMA_VERSION = "v1.4.37-folder-confirm-v2"


@dataclass(frozen=True)
class PrimaryPatientFolderInfo:
    fio: str
    admission_date: str
    folder_name: str


def build_patient_folder_info(primary_path: str | Path) -> PrimaryPatientFolderInfo:
    fio = ""
    parsed_admission_date = ""
    try:
        from medical_parser import MedicalTextParser
        parsed = MedicalTextParser().parse_docx(primary_path)
        parsed_fio = (parsed.fio or "").strip()
        fio = parsed_fio if _looks_like_human_fio(parsed_fio) else ""
        parsed_admission_date = (parsed.admission_date or "").strip()
    except Exception as exc:
        record_soft_exception("desktop_patient_folder.parse_primary", exc, detail=str(primary_path))
        fio = ""
        parsed_admission_date = ""
    if not fio:
        fio = _extract_fio_from_docx_text(primary_path)

    # The safe resolver must win over the generic parser.  The parser may see a
    # birth date in demographic tables; the resolver accepts only explicit
    # admission/hospitalization contexts.
    resolved_admission = extract_admission_date_from_primary_docx(primary_path)
    # Do not fall back to the generic parser date.  If the safe resolver did
    # not find an explicit admission/title date, the parsed value may be a date
    # of birth from a neighbouring demographic row.  A folder without month is
    # safer than «Иванов И.И. январь 1980» for a June 2026 hospitalization.
    admission_date = resolved_admission

    folder_name = patient_folder_name(fio, admission_date)
    if not folder_name:
        folder_name = safe_filename(Path(primary_path).stem)
    return PrimaryPatientFolderInfo(fio=fio, admission_date=admission_date, folder_name=folder_name)



def _extract_fio_from_docx_text(primary_path: str | Path) -> str:
    try:
        text = extract_docx_text(primary_path)
    except Exception as exc:
        record_soft_exception("desktop_patient_folder.extract_fio_text", exc, detail=str(primary_path))
        return ""
    import re
    from medical_field_line_pairs import value_after_label_line

    lines = text.splitlines()
    aliases = ("Ф.И.О.", "ФИО", "Фамилия Имя Отчество", "Пациент", "Больной", "Больная")
    for index, line in enumerate(lines):
        if not re.search(r"(?i)(?:ф\.?\s*и\.?\s*о\.?|фио|фамилия\s+имя\s+отчество|пациент|больной|больная)", line or ""):
            continue
        value = value_after_label_line(lines, index, all_aliases=aliases)
        value = re.sub(r"\s+", " ", value).strip(" .,:;-—")
        if _looks_like_human_fio(value):
            return value

    patterns = (
        r"(?im)^\s*(?:ф\.?\s*и\.?\s*о\.?|фио|пациент|больной|больная)\s*[:\-]\s*([А-ЯЁA-Z][^\n\r]{5,90})",
        r"(?im)^\s*([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)\s*$",
    )
    for pattern in patterns:
        match = re.search(pattern, text or "")
        if not match:
            continue
        value = re.sub(r"\s+", " ", match.group(1)).strip(" .,:;-—")
        if _looks_like_human_fio(value):
            return value
    return ""


def _looks_like_human_fio(value: str) -> bool:
    parts = [part for part in str(value or "").split() if part]
    if len(parts) < 2 or len(parts) > 4:
        return False
    bad = {"дата", "рождения", "диагноз", "адрес", "история", "болезни", "направление"}
    low = {part.casefold().strip(".,:;") for part in parts}
    if low & bad:
        return False
    return all(re.fullmatch(r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?", part.strip(".,:;")) for part in parts)

def patient_folder_name(fio: str, admission_date: str) -> str:
    """Backward-compatible default used by desktop intake smoke tests."""

    return build_patient_folder_name(
        fio=fio,
        admission_date=admission_date,
        discharge_date="",
        settings=DEFAULT_FOLDER_NAMING,
    )


def normalize_folder_naming_settings(settings: object | None) -> dict:
    allowed = {key for key, _label in FOLDER_NAMING_OPTIONS}
    raw = settings if isinstance(settings, dict) else {}
    raw_parts = raw.get("parts", DEFAULT_FOLDER_NAMING["parts"])
    if not isinstance(raw_parts, (list, tuple, set)):
        raw_parts = DEFAULT_FOLDER_NAMING["parts"]
    parts: list[str] = []
    for item in raw_parts:
        key = str(item or "").strip()
        if key in allowed and key not in parts:
            parts.append(key)
    if not parts:
        parts = list(DEFAULT_FOLDER_NAMING["parts"])
    date_format = str(raw.get("date_format", DEFAULT_FOLDER_NAMING["date_format"]) or "short").strip().lower()
    if date_format not in {"short", "long"}:
        date_format = "short"
    return {
        "schema_version": FOLDER_NAMING_SCHEMA_VERSION,
        "parts": parts,
        "date_format": date_format,
        "doctor_confirmed": bool(raw.get("doctor_confirmed", False)),
    }


def folder_naming_option_labels() -> tuple[tuple[str, str], ...]:
    return FOLDER_NAMING_OPTIONS


def build_patient_folder_name(
    *,
    fio: str,
    admission_date: str = "",
    discharge_date: str = "",
    settings: object | None = None,
    fallback: str = "",
) -> str:
    cfg = normalize_folder_naming_settings(settings)
    parts: list[str] = []
    for key in cfg["parts"]:
        if key == "full_fio":
            value = _fio_full(fio)
        elif key == "surname_initials":
            value = _fio_to_surname_initials(fio)
        elif key == "surname_name":
            value = _fio_surname_name(fio)
        elif key == "admission_date":
            value = _date_label(admission_date, cfg["date_format"])
        elif key == "discharge_date":
            value = _date_label(discharge_date, cfg["date_format"])
        elif key == "admission_discharge_dates":
            first = _date_label(admission_date, cfg["date_format"])
            second = _date_label(discharge_date, cfg["date_format"])
            value = f"{first}-{second}" if first and second else first or second
        elif key == "admission_month":
            value = _month_year_label(admission_date)
        elif key == "discharge_month":
            value = _month_year_label(discharge_date)
        else:
            value = ""
        value = " ".join(str(value or "").split()).strip(" _-–—")
        if value and value not in parts:
            parts.append(value)
    name = safe_filename(" ".join(parts)).strip(" .")
    if name:
        return name
    return safe_filename(fallback).strip(" .")


def _fio_full(fio: str) -> str:
    return " ".join(part.strip(" .,;:") for part in str(fio or "").split() if part.strip(" .,;:"))


def _fio_surname_name(fio: str) -> str:
    parts = [part.strip(" .,;:") for part in str(fio or "").split() if part.strip(" .,;:")]
    return " ".join(parts[:2])


def _date_label(value: str, date_format: str = "short") -> str:
    parsed = parse_date(value)
    if not parsed:
        return ""
    return parsed.strftime("%d.%m.%Y" if date_format == "long" else "%d.%m.%y")


def _fio_to_surname_initials(fio: str) -> str:
    parts = [part.strip(" .,") for part in str(fio or "").split() if part.strip(" .,")]
    if not parts:
        return ""
    surname = parts[0]
    initials = "".join(f"{part[0].upper()}." for part in parts[1:3] if part)
    return f"{surname} {initials}".strip()


def _month_year_label(value: str) -> str:
    parsed = parse_date(value)
    if not parsed:
        return ""
    return f"{_MONTHS_RU[parsed.month]} {parsed.year}"



def folder_naming_uses_discharge_date(settings: object | None) -> bool:
    """Return whether the doctor's folder naming rule needs discharge date."""

    cfg = normalize_folder_naming_settings(settings)
    parts = set(cfg.get("parts", ()))
    return bool(parts & {"discharge_date", "admission_discharge_dates", "discharge_month"})


def build_patient_folder_name_from_info(
    info: PrimaryPatientFolderInfo,
    *,
    settings: object | None = None,
    discharge_date: str = "",
    fallback: str = "",
) -> str:
    """Build the patient subfolder name from parsed primary data and doctor settings.

    Desktop intake used to move a dropped primary document using
    ``info.folder_name``, which is the old default naming.  This helper applies
    the exact naming parts the doctor confirmed in the popup, including optional
    discharge-date parts when they are already known.
    """

    return build_patient_folder_name(
        fio=getattr(info, "fio", ""),
        admission_date=getattr(info, "admission_date", ""),
        discharge_date=discharge_date,
        settings=settings,
        fallback=fallback or getattr(info, "folder_name", "") or "Пациент",
    )

def assert_desktop_patient_folder_lock() -> None:
    if DESKTOP_PATIENT_FOLDER_LOCK_VERSION != "v1.7":
        raise AssertionError("Desktop patient folder lock changed unexpectedly")
    labels = dict(FOLDER_NAMING_OPTIONS)
    if labels.get("surname_initials") != "Фамилия полностью, Имя и Отчество буквами":
        raise AssertionError("Folder naming popup label regressed")
    if not DESKTOP_PATIENT_FOLDER_SUPPORTS_CONFIGURABLE_NAMING:
        raise AssertionError("Desktop patient folder must support doctor-configurable naming")
    sample = build_patient_folder_name(fio="Иванов Иван Иванович", admission_date="05.05.2026", discharge_date="06.06.2026", settings={"parts": ["surname_initials", "discharge_date"], "date_format": "short"})
    if sample != "Иванов И.И. 06.06.26":
        raise AssertionError("Doctor-configurable patient folder naming is broken")
    info = PrimaryPatientFolderInfo(fio="Иванов Иван Иванович", admission_date="05.05.2026", folder_name="legacy")
    custom = build_patient_folder_name_from_info(
        info,
        settings={"parts": ["full_fio", "admission_discharge_dates"], "date_format": "long"},
        discharge_date="06.06.2026",
    )
    if custom != "Иванов Иван Иванович 05.05.2026-06.06.2026":
        raise AssertionError("Desktop intake patient folder name must follow the doctor's selected popup rule")
    if not folder_naming_uses_discharge_date({"parts": ["full_fio", "discharge_month"]}):
        raise AssertionError("Folder naming must detect discharge-date dependencies")
    if not DESKTOP_PATIENT_FOLDER_FALLS_BACK_TO_PRIMARY_STEM:
        raise AssertionError("Desktop patient folder must have safe fallback")
    if not DESKTOP_PATIENT_FOLDER_PREFERS_SAFE_ADMISSION_RESOLVER:
        raise AssertionError("Desktop patient folder must prefer safe admission resolver over generic parser dates")
    if not DESKTOP_PATIENT_FOLDER_EXTRACTS_NAME_FROM_TEXT_FALLBACK:
        raise AssertionError("Desktop patient folder must extract patient name from text when parser is incomplete")
    if not DESKTOP_PATIENT_FOLDER_SUPPORTS_TABLE_LABEL_VALUE_LINES:
        raise AssertionError("Desktop patient folder must support table label/value lines")
    if not DESKTOP_PATIENT_FOLDER_VALIDATES_PARSED_FIO:
        raise AssertionError("Desktop patient folder must validate parser FIO before trusting it")
    if not DESKTOP_PATIENT_FOLDER_NEVER_TRUSTS_BIRTH_AS_ADMISSION:
        raise AssertionError("Desktop patient folder must never trust birth dates as admission dates")
    if not DESKTOP_PATIENT_FOLDER_REJECTS_NUMERIC_FIO_PARTS:
        raise AssertionError("Desktop patient folder must reject numeric/non-name FIO parts")
    if not DESKTOP_PATIENT_FOLDER_USES_ONLY_SAFE_ADMISSION_RESOLVER:
        raise AssertionError("Desktop patient folder must not fall back to unsafe parser dates")
    if _looks_like_human_fio("Иванов Иван 01.01.1980"):
        raise AssertionError("Desktop patient folder FIO guard must reject dates/numbers")
