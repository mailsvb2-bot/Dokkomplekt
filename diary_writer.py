"""Removed legacy diary table writer facade.

The production diary workflow is text-based: doctor-owned diary texts are
combined with the calendar/popup schedule and written to a new DOCX document by
``diary_batch.fill_diary_batch``.  Filling diary templates as DOCX tables is not
part of the supported product contract.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Sequence

from diary_models import FillResult


_DISABLED_MESSAGE = (
    "Заполнение дневников через DOCX-таблицы удалено из проекта. "
    "Используйте текстовый маршрут дневников через diary_batch.fill_diary_batch()."
)


def fill_diary_file(
    path: str | Path,
    statuses: Sequence[str],
    *,
    start_idx: int = 0,
    repeat_statuses: bool = True,
    keep_signature: bool = True,
    fill_months: bool = True,
    start_month: int,
    start_year: int,
    admission_date_value: date | None = None,
    admission_datetime_value: datetime | None = None,
    discharge_date: date | None = None,
    force_final_diary: bool = True,
    remove_holiday_rows: bool = True,
    patient_gender: str | None = None,
    diary_day_offsets: tuple[int, ...] = (),
    diary_hour_offsets: tuple[int, ...] = (),
    diary_frequency_mode: str = "daily",
) -> FillResult:
    """Fail closed: diary table filling is intentionally unsupported."""
    _ = (
        path,
        statuses,
        start_idx,
        repeat_statuses,
        keep_signature,
        fill_months,
        start_month,
        start_year,
        admission_date_value,
        admission_datetime_value,
        discharge_date,
        force_final_diary,
        remove_holiday_rows,
        patient_gender,
        diary_day_offsets,
        diary_hour_offsets,
        diary_frequency_mode,
    )
    raise NotImplementedError(_DISABLED_MESSAGE)
