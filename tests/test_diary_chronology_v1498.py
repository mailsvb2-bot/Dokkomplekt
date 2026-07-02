from __future__ import annotations

from datetime import date

from diary_batch import _dynamic_epicrisis_base_date, dynamic_epicrisis_dates


def test_dynamic_summary_calendar_uses_confirmed_later_start_date() -> None:
    base = _dynamic_epicrisis_base_date(date(2026, 6, 1), "10.06.2026")
    assert base == date(2026, 6, 10)
    assert dynamic_epicrisis_dates(base, discharge_date=date(2026, 6, 30), limit=2) == (date(2026, 6, 22),)


def test_dynamic_summary_calendar_never_moves_before_admission() -> None:
    assert _dynamic_epicrisis_base_date(date(2026, 6, 10), "01.06.2026") == date(2026, 6, 10)
