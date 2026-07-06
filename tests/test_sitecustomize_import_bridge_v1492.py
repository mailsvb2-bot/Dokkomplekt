from __future__ import annotations

import builtins
import importlib


def test_medical_calendar_exports_non_working_day_helper_for_legacy_diary_batch() -> None:
    import medical_calendar

    if hasattr(builtins, "is_non_working_day"):
        delattr(builtins, "is_non_working_day")

    importlib.reload(medical_calendar)

    assert getattr(builtins, "is_non_working_day") is medical_calendar.is_non_working_day
