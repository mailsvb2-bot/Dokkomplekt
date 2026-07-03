"""Hourly diary wizard regression tests.

The «ежечасно» toggle used to be a dead end in the UI: the calendar-principle
popup collected only DAY offsets, no popup ever asked for hour intervals, so
hourly creation always aborted with «Для режима по часам в профиле дневников
нет часового расписания». The v1.7 wizard asks an hourly question symmetric to
the daily one and confirms hour offsets.
"""
from __future__ import annotations

import pytest

from diary_creation_wizard import (
    build_diary_wizard_review,
    prompt_diary_calendar_principle,
)
from diary_schedule import diary_hourly_schedule_from_choice


class _Var:
    def __init__(self, value: str):
        self._value = value

    def get(self) -> str:
        return self._value


class _App:
    """Headless stub: no Tk root, so the wizard takes the auto-confirm path."""

    def __init__(self, frequency: str):
        self.diary_frequency_mode_var = _Var(frequency)
        self.patient_name_var = _Var("Иванов И.И.")
        self.admission_date_var = _Var("05.05.2026 14:00")
        self.discharge_date_var = _Var("07.05.2026")
        self.status_files = ["тексты.docx"]


def test_hourly_choice_single_interval_expands():
    spec = diary_hourly_schedule_from_choice("2")
    assert spec.mode == "hourly"
    assert spec.hour_offsets[:4] == (2, 4, 6, 8)
    assert not spec.day_offsets


def test_hourly_choice_explicit_hours():
    spec = diary_hourly_schedule_from_choice("1, 2, 4, 8")
    assert spec.hour_offsets == (1, 2, 4, 8)


def test_hourly_choice_rejects_garbage():
    with pytest.raises(ValueError):
        diary_hourly_schedule_from_choice("abc")


def test_hourly_prompt_confirms_hours_headless():
    app = _App("hourly")
    assert prompt_diary_calendar_principle(app) is True
    assert getattr(app, "_doctor_confirmed_diary_hour_offsets", ()), (
        "hourly mode must confirm hour offsets"
    )


def test_hourly_review_passes_after_prompt():
    app = _App("hourly")
    assert prompt_diary_calendar_principle(app) is True
    review = build_diary_wizard_review(app)
    assert review.frequency_mode == "hourly"
    assert review.hour_offsets, review.as_text()
    hourly_warning = "нет часового расписания"
    assert not any(hourly_warning in item for item in review.warnings), review.warnings


def test_daily_prompt_untouched():
    app = _App("daily")
    assert prompt_diary_calendar_principle(app) is True
    assert getattr(app, "_doctor_confirmed_diary_day_offsets", ())
    review = build_diary_wizard_review(app)
    assert review.frequency_mode == "daily"
    assert review.ok, review.warnings
