from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from diary_dates import add_month, safe_row_date
from diary_schedule import expand_day_offsets, expand_hour_intervals
from diary_table import (
    cell_int,
    find_day_column,
    find_diary_column,
    find_hospitalization_day_column,
    find_month_year_column,
    is_data_row,
    is_holiday_skip_date,
)

DiaryEntry = tuple[object, int, int | None, int | None, int | None]
DatedEntry = dict[str, object]


def _row_text(row) -> str:
    return " ".join(str(cell.text or "").strip() for cell in row.cells if str(cell.text or "").strip())


def _looks_like_table_header(row) -> bool:
    text = _row_text(row).lower().replace("ё", "е")
    return any(token in text for token in ("дневник", "число", "месяц", "день госпитализации", "наблюдения"))


def _looks_like_blank_diary_row(row, *, diary_col: int, day_col: int | None, month_year_col: int | None, hospitalization_day_col: int | None) -> bool:
    """Accept blank calendar rows from doctor-owned diary templates.

    Some Word tables are empty forms: all date/day cells are blank and the
    program is expected to write hospitalization dates and diary texts from
    scratch. Older detection ignored these rows, so the created «Дневники» file
    stayed empty.
    """
    if len(row.cells) <= diary_col:
        return False
    if _looks_like_table_header(row):
        return False
    ignored = {idx for idx in (day_col, month_year_col, hospitalization_day_col, diary_col) if idx is not None}
    outside_text = " ".join(str(cell.text or "").strip() for idx, cell in enumerate(row.cells) if idx not in ignored)
    low = outside_text.lower().replace("ё", "е")
    if any(marker in low for marker in ("подпись", "врач", "завед", "итого")):
        return False
    return True


def collect_data_entries(doc: Any) -> list[DiaryEntry]:
    entries: list[DiaryEntry] = []
    for table in doc.tables:
        diary_col = find_diary_column(table)
        day_col = find_day_column(table)
        month_year_col = find_month_year_column(table)
        hospitalization_day_col = find_hospitalization_day_column(table)
        if diary_col is None:
            continue
        header_passed = False
        for row in table.rows:
            if _looks_like_table_header(row):
                header_passed = True
                continue
            row_is_data = is_data_row(row, day_col, hospitalization_day_col)
            if not row_is_data and header_passed:
                row_is_data = _looks_like_blank_diary_row(
                    row,
                    diary_col=diary_col,
                    day_col=day_col,
                    month_year_col=month_year_col,
                    hospitalization_day_col=hospitalization_day_col,
                )
            if not row_is_data:
                continue
            if len(row.cells) <= diary_col:
                continue
            entries.append((row, diary_col, day_col, month_year_col, hospitalization_day_col))
    return entries


def build_dated_entries(
    data_entries: list[DiaryEntry],
    *,
    start_month: int,
    start_year: int,
    admission_date_value: date | None,
    admission_datetime_value: datetime | None = None,
    diary_day_offsets: tuple[int, ...] = (),
    diary_hour_offsets: tuple[int, ...] = (),
    diary_frequency_mode: str = "daily",
) -> list[DatedEntry]:
    """Implement the build_dated_entries workflow with validation, UI state updates and diagnostics."""
    dated_entries: list[DatedEntry] = []
    current_month = start_month
    current_year = start_year
    previous_day: int | None = None

    expanded_day_offsets = expand_day_offsets(diary_day_offsets, len(data_entries)) if diary_day_offsets else ()
    expanded_hour_offsets = expand_hour_intervals(diary_hour_offsets, len(data_entries)) if diary_hour_offsets else ()

    for entry_index, (row, _diary_col, day_col, _month_year_col, hospitalization_day_col) in enumerate(data_entries):
        day_value: int | None = None
        if day_col is not None and len(row.cells) > day_col:
            day_value = cell_int(row.cells[day_col].text)

        hospitalization_day_value: int | None = None
        if hospitalization_day_col is not None and len(row.cells) > hospitalization_day_col:
            hospitalization_day_value = cell_int(row.cells[hospitalization_day_col].text)

        time_text = ""
        if admission_date_value is not None and diary_frequency_mode == "hourly" and expanded_hour_offsets:
            hour_offset = expanded_hour_offsets[entry_index]
            base_dt = admission_datetime_value or datetime.combine(admission_date_value, time(hour=0, minute=0))
            row_dt = base_dt + timedelta(hours=max(0, hour_offset))
            row_date = row_dt.date()
            time_text = row_dt.strftime("%H:%M")
            day_value = row_date.day
            current_month = row_date.month
            current_year = row_date.year
            previous_day = day_value
        elif admission_date_value is not None and expanded_day_offsets:
            day_offset = expanded_day_offsets[entry_index]
            row_date = admission_date_value + timedelta(days=max(0, day_offset))
            day_value = row_date.day
            current_month = row_date.month
            current_year = row_date.year
            previous_day = day_value
        elif admission_date_value is not None and hospitalization_day_value is not None:
            row_date = admission_date_value + timedelta(days=max(0, hospitalization_day_value - 1))
            day_value = row_date.day
            current_month = row_date.month
            current_year = row_date.year
            previous_day = day_value
        elif admission_date_value is not None and day_value is None:
            # Blank diary templates are forms: fill calendar rows starting from
            # the hospitalization date instead of leaving «Число» empty.
            row_date = admission_date_value + timedelta(days=entry_index)
            day_value = row_date.day
            current_month = row_date.month
            current_year = row_date.year
            previous_day = day_value
        else:
            if day_value is not None and previous_day is not None and day_value < previous_day:
                current_month, current_year = add_month(current_month, current_year, 1)
            if day_value is not None:
                previous_day = day_value
            row_date = safe_row_date(current_year, current_month, day_value)

        dated_entries.append(
            {
                "month": current_month,
                "year": current_year,
                "day": day_value,
                "date": row_date,
                "after_discharge": False,
                "skip_holiday": False,
                "skip_after_discharge": False,
                "time_text": time_text,
            }
        )
    return dated_entries


def find_final_entry_index(
    data_entries: list[DiaryEntry],
    dated_entries: list[DatedEntry],
    *,
    discharge_date: date | None,
    remove_holiday_rows: bool,
) -> int | None:
    if discharge_date is not None:
        for entry_index in range(len(data_entries) - 1, -1, -1):
            row_date = dated_entries[entry_index]["date"]
            if isinstance(row_date, date) and row_date <= discharge_date:
                return entry_index
        if data_entries:
            raise ValueError(
                "В выбранной таблице не найдено ни одной строки до даты выписки. "
                "Проверьте месяц/год поступления и дату выписки."
            )
        return None

    for entry_index in range(len(data_entries) - 1, -1, -1):
        day_value = dated_entries[entry_index]["day"]
        row_month = int(dated_entries[entry_index]["month"])
        if not (remove_holiday_rows and is_holiday_skip_date(day_value if isinstance(day_value, int) else None, row_month)):
            return entry_index
    return None


def mark_skip_flags(
    dated_entries: list[DatedEntry],
    *,
    final_entry_index: int | None,
    discharge_date: date | None,
    remove_holiday_rows: bool,
) -> None:
    for entry_index, entry in enumerate(dated_entries):
        day_value = entry["day"]
        row_month = int(entry["month"])
        is_final_row = final_entry_index is not None and entry_index == final_entry_index
        after_final_discharge_row = (
            discharge_date is not None
            and final_entry_index is not None
            and entry_index > final_entry_index
        )
        entry["after_discharge"] = after_final_discharge_row
        entry["skip_after_discharge"] = after_final_discharge_row
        entry["skip_holiday"] = (
            remove_holiday_rows
            and is_holiday_skip_date(day_value if isinstance(day_value, int) else None, row_month)
            and not is_final_row
            and not after_final_discharge_row
        )
