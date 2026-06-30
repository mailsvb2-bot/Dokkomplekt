"""Calendar helpers for diary planning.

The diary plan must not blindly write entries on weekends or fixed holiday
periods.  This layer stays deterministic and local; it does not call online
calendars or store patient data.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

DIARY_CALENDAR_LOCK_VERSION = "v1.0"
DIARY_CALENDAR_SKIPS_WEEKENDS = True
DIARY_CALENDAR_SKIPS_FIXED_HOLIDAYS = True

# Conservative fixed non-working periods used by the existing diary rules too.
# The exact official transfer days may differ by year, but these ranges protect
# the doctor's main requirement: no diary dates on obvious holidays.
_FIXED_HOLIDAY_RANGES: tuple[tuple[int, int, int], ...] = (
    (1, 1, 9),
    (5, 1, 9),
)


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
    raise RuntimeError("Не удалось подобрать рабочую дату дневника в пределах года.")


def default_observation_diary_dates(admission: date, *, limit: int = 20, discharge_date: date | None = None) -> tuple[date, ...]:
    """Return the requested diary rhythm as working calendar dates.

    Rule: first three days from admission, then day 7, then twice per week.  If a
    planned date falls on a weekend or fixed holiday period, move it to the next
    available working day without duplicating an already selected date.
    """

    if limit <= 0:
        return ()
    offsets: list[int] = [0, 1, 2, 7]
    # After day 7: two times per week.  3/4-day alternation gives a stable
    # twice-weekly rhythm without depending on the weekday of admission.
    next_offset = 10
    step_toggle = 0
    while len(offsets) < max(limit * 3, 12):
        offsets.append(next_offset)
        next_offset += 3 if step_toggle % 2 == 0 else 4
        step_toggle += 1

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


def day_offsets_from_dates(admission: date, dates: Iterable[date]) -> tuple[int, ...]:
    return tuple(max(0, (item - admission).days) for item in dates)


def assert_diary_calendar_lock() -> None:
    if DIARY_CALENDAR_LOCK_VERSION != "v1.0":
        raise AssertionError("Diary calendar lock changed unexpectedly")
    if not DIARY_CALENDAR_SKIPS_WEEKENDS or not DIARY_CALENDAR_SKIPS_FIXED_HOLIDAYS:
        raise AssertionError("Diary calendar must skip weekends and fixed holidays")
    sample = default_observation_diary_dates(date(2026, 1, 1), limit=5)
    if any(is_non_working_day(item) for item in sample):
        raise AssertionError("Default diary schedule produced a non-working day")
    if sample != tuple(dict.fromkeys(sample)):
        raise AssertionError("Default diary schedule produced duplicate dates")
