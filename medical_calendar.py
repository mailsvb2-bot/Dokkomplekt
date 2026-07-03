from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

FIXED_HOLIDAY_RANGES: tuple[tuple[int, int, int], ...] = ((1, 1, 9), (5, 1, 9))


def is_fixed_holiday(day: date) -> bool:
    return any(month == day.month and start <= day.day <= end for month, start, end in FIXED_HOLIDAY_RANGES)


def is_non_working_day(day: date) -> bool:
    return day.weekday() >= 5 or is_fixed_holiday(day)


def next_working_day(day: date, *, used: Iterable[date] = ()) -> date:
    used_set = set(used)
    current = day
    for _ in range(370):
        if not is_non_working_day(current) and current not in used_set:
            return current
        current += timedelta(days=1)
    raise RuntimeError("Cannot find an available calendar day within one year.")
