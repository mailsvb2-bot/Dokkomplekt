"""Disabled legacy diary table entry discovery.

Diary generation is text-based.  This module remains only to keep old imports
from crashing during transition; it no longer discovers or prepares DOCX table
rows for diary filling.
"""

from __future__ import annotations

from datetime import date
from typing import Any

DiaryEntry = tuple[object, int, int | None, int | None, int | None]
DatedEntry = dict[str, object]

_DISABLED_MESSAGE = "Legacy diary table entry discovery is removed; use diary_batch.fill_diary_batch()."


def collect_data_entries(doc: Any) -> list[DiaryEntry]:
    _ = doc
    raise NotImplementedError(_DISABLED_MESSAGE)


def build_dated_entries(
    data_entries: list[DiaryEntry],
    *,
    start_month: int,
    start_year: int,
    admission_date_value: date | None,
    admission_datetime_value: object | None = None,
    diary_day_offsets: tuple[int, ...] = (),
    diary_hour_offsets: tuple[int, ...] = (),
    diary_frequency_mode: str = "daily",
) -> list[DatedEntry]:
    _ = (
        data_entries,
        start_month,
        start_year,
        admission_date_value,
        admission_datetime_value,
        diary_day_offsets,
        diary_hour_offsets,
        diary_frequency_mode,
    )
    raise NotImplementedError(_DISABLED_MESSAGE)


def find_final_entry_index(
    data_entries: list[DiaryEntry],
    dated_entries: list[DatedEntry],
    *,
    discharge_date: date | None,
    remove_holiday_rows: bool,
) -> int | None:
    _ = (data_entries, dated_entries, discharge_date, remove_holiday_rows)
    raise NotImplementedError(_DISABLED_MESSAGE)


def mark_skip_flags(
    dated_entries: list[DatedEntry],
    *,
    final_entry_index: int | None,
    discharge_date: date | None,
    remove_holiday_rows: bool,
) -> None:
    _ = (dated_entries, final_entry_index, discharge_date, remove_holiday_rows)
    raise NotImplementedError(_DISABLED_MESSAGE)
