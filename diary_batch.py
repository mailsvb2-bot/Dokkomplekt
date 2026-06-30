from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import shutil
from typing import Iterable, Sequence

from docx import Document

from diagnostic_logging import record_soft_exception
from diary_dates import parse_admission_month_year, parse_full_date, parse_full_datetime, parse_optional_discharge_date
from diary_gender import adapt_text_to_patient_gender, detect_gender_from_patient_name
from diary_models import DiaryBatchResult
from diary_paths import available_path, make_diary_output_name, safe_filename_part
from diary_text_parser import clean_status_text, extract_statuses_from_docx
from diary_writer import fill_diary_file
from medical_docx_xml_fragments import ensure_docx_compatible, existing_word_file
from medical_formatting import redact_technical_text, safe_filename, technical_ref, technical_report_path

_FIXED_HOLIDAY_RANGES: tuple[tuple[int, int, int], ...] = ((1, 1, 9), (5, 1, 9))


@dataclass(frozen=True)
class DynamicEpicrisisInput:
    patient_name: str = ""
    birth_date: str = ""
    sick_leave_from: str = ""
    complaints: str = ""
    treatment: str = ""
    profile_status: str = ""
    treatment_correction: str = ""


def is_fixed_holiday(day: date) -> bool:
    return any(month == day.month and start <= day.day <= end for month, start, end in _FIXED_HOLIDAY_RANGES)


def is_non_working_day(day: date) -> bool:
    return day.weekday() >= 5 or is_fixed_holiday(day)


def next_working_day(day: date, *, used: Iterable[date] = ()) -> date:
    used_set = set(used)
    current = day
    for _ in range(370):
        if not is_non_working_day(current) and current not in used_set:
            return current
        current += timedelta(days=1)
    raise RuntimeError("Cannot find a working diary date within one year.")


def default_observation_diary_dates(admission: date, *, limit: int = 20, discharge_date: date | None = None) -> tuple[date, ...]:
    if limit <= 0:
        return ()
    offsets: list[int] = [0, 1, 2, 7]
    next_offset = 10
    toggle = 0
    while len(offsets) < max(limit * 3, 12):
        offsets.append(next_offset)
        next_offset += 3 if toggle % 2 == 0 else 4
        toggle += 1
    result: list[date] = []
    for offset in offsets:
        planned = admission + timedelta(days=max(0, int(offset)))
        if discharge_date is not None and planned > discharge_date:
            break
        adjusted = next_working_day(planned, used=result)
        if discharge_date is not None and adjusted > discharge_date:
            break
        result.append(adjusted)
        if len(result) >= limit:
            break
    return tuple(result)


def dynamic_epicrisis_dates(admission: date, *, discharge_date: date | None = None, limit: int = 12) -> tuple[date, ...]:
    result: list[date] = []
    current = admission + timedelta(days=10)
    while len(result) < limit:
        if discharge_date is not None and current > discharge_date:
            break
        adjusted = next_working_day(current, used=result)
        if discharge_date is not None and adjusted > discharge_date:
            break
        result.append(adjusted)
        current += timedelta(days=10)
    return tuple(result)


def build_dynamic_epicrisis_text(data: DynamicEpicrisisInput) -> str:
    correction = str(data.treatment_correction or "").strip() or "Лекарства принимает согласно назначениям."
    return "\n".join([
        "Динамический эпикриз.",
        f"ФИО: {data.patient_name or 'не указано'}.",
        f"Дата рождения: {data.birth_date or 'не указана'}.",
        f"Лечится с: {data.sick_leave_from or 'не указано'}.",
        f"Жалобы: {data.complaints or 'без существенной динамики'}.",
        f"Принимает: {data.treatment or 'согласно листу назначений'}.",
        f"Профильный статус: {data.profile_status or 'без существенной динамики'}.",
        correction,
        "Продолжение лечения по листу нетрудоспособности.",
        "Заведующий отделением ____________________",
        "Лечащий врач ____________________",
    ])


def _existing_docx_files(paths: Iterable[str | Path], label: str) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for raw_path in paths:
        if raw_path is None or str(raw_path).strip() == "":
            raise ValueError(f"Пустой путь к файлу ({label}).")
        source = existing_word_file(raw_path, label)
        path = ensure_docx_compatible(source, label=label)
        key = path.resolve()
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def _resolve_output_dir(output_dir: str | Path | None, fallback_dir: Path) -> Path:
    result = fallback_dir if output_dir is None or str(output_dir).strip() == "" else Path(output_dir).expanduser()
    if result.exists() and not result.is_dir():
        raise ValueError(f"Папка результата указывает на файл, а не на папку: {result}")
    result.mkdir(parents=True, exist_ok=True)
    return result


def read_statuses_from_files(paths: Iterable[str | Path]) -> list[str]:
    statuses: list[str] = []
    seen: set[str] = set()
    for path in _existing_docx_files(paths, "тексты дневников"):
        for status in extract_statuses_from_docx(path):
            key = " ".join(status.strip().lower().replace("ё", "е").split())
            if key not in seen:
                statuses.append(status.strip())
                seen.add(key)
    return statuses


def open_folder(path: str | Path) -> bool:
    folder = Path(path).expanduser()
    try:
        from printer_platform import open_desktop_path
        if open_desktop_path(folder, require_dir=True):
            return True
        return False
    except Exception as exc:
        record_soft_exception("diary_batch.open_folder", exc, detail=str(folder))
        return False


def _build_dated_entries(statuses: Sequence[str], dates: Sequence[date], patient_gender: str | None, repeat_statuses: bool) -> tuple[str, ...]:
    entries: list[str] = []
    status_index = 0
    for item_date in dates:
        if not statuses:
            text = ""
        else:
            if status_index >= len(statuses):
                if repeat_statuses:
                    status_index = 0
                else:
                    break
            text = statuses[status_index]
            status_index += 1
        adapted, _changed = adapt_text_to_patient_gender(text, patient_gender)
        entries.append(f"{item_date:%d.%m.%y} {clean_status_text(adapted)}".rstrip())
    return tuple(entries)


def _create_text_diary_document(output_dir: Path, patient_name: str, entries: Sequence[str], epicrisis_entries: Sequence[tuple[date, str]]) -> Path:
    target = available_path(output_dir / safe_filename(make_diary_output_name(safe_filename_part(patient_name), file_index=1, total_files=1)))
    doc = Document()
    for entry in entries:
        doc.add_paragraph(str(entry or "").strip())
    for item_date, text in epicrisis_entries:
        if doc.paragraphs:
            doc.add_paragraph("")
        lines = text.splitlines()
        doc.add_paragraph(f"{item_date:%d.%m.%y} {lines[0] if lines else ''}".rstrip())
        for line in lines[1:]:
            doc.add_paragraph(line)
    doc.save(str(target))
    return target


def _fill_text_diary_batch(
    *, statuses: Sequence[str], result_dir: Path, patient_name: str, admission_value: str,
    admission_date_value, discharge_date_value, gender_source_name: str, repeat_statuses: bool,
    patient_gender: str | None, sick_leave_dynamic_epicrisis: bool, treatment_correction: str,
    birth_date: str, complaints: str, treatment: str, profile_status: str, sick_leave_from: str,
    write_report: bool,
) -> DiaryBatchResult:
    if admission_date_value is None:
        admission_date_value = parse_full_date(admission_value)
    rough_limit = max(10, min(80, (discharge_date_value - admission_date_value).days + 10)) if discharge_date_value else max(10, len(statuses) or 10)
    dates = default_observation_diary_dates(admission_date_value, limit=rough_limit, discharge_date=discharge_date_value)
    entries = _build_dated_entries(statuses, dates, patient_gender, repeat_statuses)
    epicrisis_entries: list[tuple[date, str]] = []
    if sick_leave_dynamic_epicrisis:
        data = DynamicEpicrisisInput(patient_name, birth_date, sick_leave_from or admission_value, complaints, treatment, profile_status, treatment_correction)
        epicrisis_entries = [(d, build_dynamic_epicrisis_text(data)) for d in dynamic_epicrisis_dates(admission_date_value, discharge_date=discharge_date_value, limit=12)]
    created = _create_text_diary_document(result_dir, patient_name, entries, epicrisis_entries)
    report_path: Path | None = None
    if write_report:
        lines = [
            "ОТЧЁТ: текстовые дневники",
            f"Дата запуска: {datetime.now():%d.%m.%Y %H:%M:%S}",
            "Карточка пациента: обезличена",
            "Технический идентификатор: " + technical_ref(patient_name, gender_source_name, admission_value),
            f"Дневниковых дат: {len(dates)}",
            f"Динамических эпикризов: {len(epicrisis_entries)}",
        ]
        report_path = technical_report_path(result_dir, "ОТЧЁТ_дневники.txt")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return DiaryBatchResult([created], report_path, 1, len(entries), len(entries), 0, len(epicrisis_entries), 0, 0, 0)


def fill_diary_batch(
    *,
    status_files: Sequence[str | Path], diary_files: Sequence[str | Path], output_dir: str | Path | None,
    patient_name: str, admission_value: str, gender_source_name: str | None = None,
    discharge_value: str = "", repeat_statuses: bool = True, reset_each_file: bool = True,
    keep_signature: bool = True, fill_months: bool = True, force_final_diary: bool = True,
    remove_holiday_rows: bool = True, open_result_folder: bool = False, write_report: bool = False,
    diary_day_offsets: Sequence[int] = (), diary_hour_offsets: Sequence[int] = (),
    diary_frequency_mode: str = "daily", allow_empty_statuses: bool = False, text_output: bool = False,
    sick_leave_dynamic_epicrisis: bool = False, treatment_correction: str = "", birth_date: str = "",
    complaints: str = "", treatment: str = "", profile_status: str = "", sick_leave_from: str = "",
) -> DiaryBatchResult:
    """Create diary documents from selected doctor-owned text and date sources.

    This public batch boundary keeps the old table workflow working while also
    supporting the text-output contract. It validates selected Word files,
    converts legacy DOC files locally when possible, adapts diary text by patient
    gender, keeps output folders safe, and optionally adds periodic dynamic
    epicrisis entries for sick-leave cases.
    """
    if not diary_files and not text_output:
        raise ValueError("Сначала выберите файлы-таблицы дневников, которые нужно заполнить.")
    diary_file_paths = _existing_docx_files(diary_files, "таблица дневников") if diary_files else []
    status_file_paths = _existing_docx_files(status_files, "тексты дневников") if status_files else []
    if not status_files and not allow_empty_statuses:
        raise ValueError("Сначала выберите тексты дневников или положите DOCX/DOC/DOCM с текстами рядом с первичным документом. Программа не будет создавать пустые дневники без текстов.")
    if not status_files and not fill_months and not force_final_diary:
        raise ValueError("Сначала выберите файл(ы) с текстами дневников, включите месяц/год или финальную запись выписки.")

    start_month, start_year = parse_admission_month_year(admission_value)
    try:
        admission_datetime_value = parse_full_datetime(admission_value)
        admission_date_value = admission_datetime_value.date()
    except ValueError:
        admission_datetime_value = None
        admission_date_value = None
    discharge_date_value = parse_optional_discharge_date(discharge_value)
    if admission_date_value is not None and discharge_date_value is not None and discharge_date_value < admission_date_value:
        raise ValueError("Дата выписки не может быть раньше даты поступления.")
    patient_filename = safe_filename_part(patient_name)
    gender_name = safe_filename_part(gender_source_name or patient_name)
    patient_gender = detect_gender_from_patient_name(gender_name)
    if patient_gender is None:
        raise ValueError("Введите ФИО так, чтобы первым словом была фамилия пациента. Например: Иванов И.И. или Петрова А.А.")
    statuses = read_statuses_from_files(status_file_paths)
    if status_files and not statuses:
        raise ValueError("В выбранных файлах с текстами дневников не найдено подходящих текстов.")
    first_dir = diary_file_paths[0].parent if diary_file_paths else Path.cwd()
    result_dir = _resolve_output_dir(output_dir, first_dir)

    if text_output:
        result = _fill_text_diary_batch(
            statuses=statuses, result_dir=result_dir, patient_name=patient_name,
            admission_value=admission_value, admission_date_value=admission_date_value,
            discharge_date_value=discharge_date_value, gender_source_name=gender_name,
            repeat_statuses=repeat_statuses, patient_gender=patient_gender,
            sick_leave_dynamic_epicrisis=sick_leave_dynamic_epicrisis,
            treatment_correction=treatment_correction, birth_date=birth_date,
            complaints=complaints, treatment=treatment, profile_status=profile_status,
            sick_leave_from=sick_leave_from, write_report=write_report,
        )
        if open_result_folder:
            open_folder(result_dir)
        return result

    idx = 0
    created_files: list[Path] = []
    technical_lines = [
        "ОТЧЁТ: заполнение дневников",
        f"Дата запуска: {datetime.now():%d.%m.%Y %H:%M:%S}",
        "Карточка пациента: обезличена",
        "Технический идентификатор: " + technical_ref(patient_filename, gender_name, admission_value),
        f"Файлов текстов дневников: {len(status_file_paths)}",
        f"Файлов таблиц дневников: {len(diary_file_paths)}",
        f"Текстов дневников найдено: {len(statuses)}",
        f"Принцип дневников: {redact_technical_text(diary_frequency_mode, limit=40)}; дни={len(tuple(diary_day_offsets))}; часы={len(tuple(diary_hour_offsets))}",
        "",
    ]
    total_filled = total_detected = total_months = total_final = total_gender = total_holidays = total_after_discharge = 0
    for n, src_path in enumerate(diary_file_paths, start=1):
        dst = available_path(result_dir / make_diary_output_name(patient_filename, file_index=n, total_files=len(diary_file_paths)))
        shutil.copy2(src_path, dst)
        result = fill_diary_file(
            dst, statuses, start_idx=0 if reset_each_file else idx,
            repeat_statuses=repeat_statuses, keep_signature=keep_signature, fill_months=fill_months,
            start_month=start_month, start_year=start_year, admission_date_value=admission_date_value,
            admission_datetime_value=admission_datetime_value, discharge_date=discharge_date_value,
            force_final_diary=force_final_diary, remove_holiday_rows=remove_holiday_rows,
            patient_gender=patient_gender, diary_day_offsets=tuple(int(x) for x in diary_day_offsets),
            diary_hour_offsets=tuple(int(x) for x in diary_hour_offsets), diary_frequency_mode=diary_frequency_mode,
        )
        if not reset_each_file:
            idx = result.next_status_index
        created_files.append(dst)
        total_filled += result.filled_rows
        total_detected += result.detected_rows
        total_months += result.month_cells_filled
        total_final += result.final_rows_filled
        total_gender += result.gender_replacements
        total_holidays += result.removed_holiday_rows
        total_after_discharge += result.removed_after_discharge_rows
        technical_lines.append(f"шаблон #{n}: строк найдено {result.detected_rows}; дневников заполнено {result.filled_rows}; месяц/год {result.month_cells_filled}; финальных записей {result.final_rows_filled}; замен пола {result.gender_replacements}; удалено праздников {result.removed_holiday_rows}; удалено после выписки {result.removed_after_discharge_rows}")
    technical_lines.extend(["", f"Файлов обработано: {len(created_files)}/{len(diary_file_paths)}", f"Дневников заполнено: {total_filled}", f"Строк дневников найдено: {total_detected}", f"Дат месяц/год заполнено: {total_months}", f"Финальных записей: {total_final}", f"Грамматических замен по полу: {total_gender}", f"Удалено праздничных строк: {total_holidays}", f"Удалено строк после выписки: {total_after_discharge}"])
    report_path: Path | None = None
    if write_report:
        report_path = technical_report_path(result_dir, "ОТЧЁТ_дневники.txt")
        report_path.write_text("\n".join(technical_lines) + "\n", encoding="utf-8")
    if open_result_folder:
        open_folder(result_dir)
    return DiaryBatchResult(created_files, report_path, len(created_files), total_filled, total_detected, total_months, total_final, total_gender, total_holidays, total_after_discharge)
