"""Разделённый слой заполнителя дневников.

Файл создан при архитектурной нарезке бывшего diary_filler.py.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from docx import Document

from diagnostic_logging import record_soft_exception
from medical_formatting import redact_technical_text, technical_ref
from medical_formatting import technical_report_path

from diary_dates import parse_admission_month_year, parse_full_date, parse_full_datetime, parse_optional_discharge_date
from diary_gender import detect_gender_from_patient_name
from diary_models import DiaryBatchResult
from diary_paths import available_path, make_diary_output_name, safe_filename_part
from diary_table import detect_first_month_year_from_docx
from diary_text_parser import extract_statuses_from_docx
from diary_writer import fill_diary_file

def _existing_docx_files(paths: Iterable[str | Path], label: str) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for raw_path in paths:
        if raw_path is None or str(raw_path).strip() == "":
            raise ValueError(f"Пустой путь к файлу ({label}).")
        path = Path(raw_path).expanduser()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Не найден файл ({label}): {path}")
        if path.suffix.lower() not in {".docx", ".docm"}:
            raise ValueError(f"Неверный формат файла ({label}): {path.suffix or 'без расширения'}. Разрешено: .docx, .docm.")
        key = path.resolve()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _resolve_output_dir(output_dir: str | Path | None, fallback_dir: Path) -> Path:
    if output_dir is None or str(output_dir).strip() == "":
        result = fallback_dir
    else:
        result = Path(output_dir).expanduser()
    if result.exists() and not result.is_dir():
        raise ValueError(f"Папка результата указывает на файл, а не на папку: {result}")
    result.mkdir(parents=True, exist_ok=True)
    return result


def read_statuses_from_files(paths: Iterable[str | Path]) -> list[str]:
    statuses: list[str] = []
    seen: set[str] = set()
    for path in _existing_docx_files(paths, "тексты дневников"):
        for status in extract_statuses_from_docx(path):
            status = status.strip()
            key = " ".join(status.lower().replace("ё", "е").split())
            if key not in seen:
                statuses.append(status)
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


def fill_diary_batch(
    *,
    status_files: Sequence[str | Path],
    diary_files: Sequence[str | Path],
    output_dir: str | Path | None,
    patient_name: str,
    admission_value: str,
    gender_source_name: str | None = None,
    discharge_value: str = "",
    repeat_statuses: bool = True,
    reset_each_file: bool = True,
    keep_signature: bool = True,
    fill_months: bool = True,
    force_final_diary: bool = True,
    remove_holiday_rows: bool = True,
    open_result_folder: bool = False,
    write_report: bool = False,
    diary_day_offsets: Sequence[int] = (),
    diary_hour_offsets: Sequence[int] = (),
    diary_frequency_mode: str = "daily",
    allow_empty_statuses: bool = False,
) -> DiaryBatchResult:
    """Implement the fill_diary_batch workflow with validation, UI state updates and diagnostics."""
    if not diary_files:
        raise ValueError("Сначала выберите файлы-таблицы дневников, которые нужно заполнить.")
    diary_file_paths = _existing_docx_files(diary_files, "таблица дневников")
    status_file_paths = _existing_docx_files(status_files, "тексты дневников") if status_files else []
    if not status_files and not allow_empty_statuses:
        raise ValueError(
            "Сначала выберите тексты дневников или положите DOCX с текстами рядом с первичным документом. "
            "Программа не будет создавать пустые дневники без текстов."
        )
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

    first_dir = diary_file_paths[0].parent
    result_dir = _resolve_output_dir(output_dir, first_dir)

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
        f"Принцип дневников: {redact_technical_text(diary_frequency_mode, limit=40)}; "
        f"дни={len(tuple(diary_day_offsets))}; часы={len(tuple(diary_hour_offsets))}",
        "",
    ]

    total_filled = 0
    total_detected = 0
    total_months = 0
    total_final = 0
    total_gender = 0
    total_holidays = 0
    total_after_discharge = 0

    for n, src_path in enumerate(diary_file_paths, start=1):
        out_name = make_diary_output_name(patient_filename, file_index=n, total_files=len(diary_file_paths))
        dst = available_path(result_dir / out_name)
        shutil.copy2(src_path, dst)
        effective_start_idx = 0 if reset_each_file else idx
        result = fill_diary_file(
            dst,
            statuses,
            start_idx=effective_start_idx,
            repeat_statuses=repeat_statuses,
            keep_signature=keep_signature,
            fill_months=fill_months,
            start_month=start_month,
            start_year=start_year,
            admission_date_value=admission_date_value,
            admission_datetime_value=admission_datetime_value,
            discharge_date=discharge_date_value,
            force_final_diary=force_final_diary,
            remove_holiday_rows=remove_holiday_rows,
            patient_gender=patient_gender,
            diary_day_offsets=tuple(int(x) for x in diary_day_offsets),
            diary_hour_offsets=tuple(int(x) for x in diary_hour_offsets),
            diary_frequency_mode=diary_frequency_mode,
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
        technical_lines.append(
            f"шаблон #{n}: строк найдено {result.detected_rows}; дневников заполнено {result.filled_rows}; "
            f"месяц/год {result.month_cells_filled}; финальных записей {result.final_rows_filled}; "
            f"замен пола {result.gender_replacements}; удалено праздников {result.removed_holiday_rows}; "
            f"удалено после выписки {result.removed_after_discharge_rows}"
        )

    technical_lines.extend(
        [
            "",
            f"Файлов обработано: {len(created_files)}/{len(diary_file_paths)}",
            f"Дневников заполнено: {total_filled}",
            f"Строк дневников найдено: {total_detected}",
            f"Дат месяц/год заполнено: {total_months}",
            f"Финальных записей: {total_final}",
            f"Грамматических замен по полу: {total_gender}",
            f"Удалено праздничных строк: {total_holidays}",
            f"Удалено строк после выписки: {total_after_discharge}",
        ]
    )
    report_path: Path | None = None
    if write_report:
        report_path = technical_report_path(result_dir, "ОТЧЁТ_дневники.txt")
        report_path.write_text("\n".join(technical_lines) + "\n", encoding="utf-8")
    if open_result_folder:
        open_folder(result_dir)

    return DiaryBatchResult(
        created_files=created_files,
        report_path=report_path,
        processed_files=len(created_files),
        filled_rows=total_filled,
        detected_rows=total_detected,
        month_cells_filled=total_months,
        final_rows_filled=total_final,
        gender_replacements=total_gender,
        removed_holiday_rows=total_holidays,
        removed_after_discharge_rows=total_after_discharge,
    )
