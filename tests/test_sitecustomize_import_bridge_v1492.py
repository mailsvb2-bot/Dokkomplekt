from __future__ import annotations

import builtins
import importlib


def test_medical_calendar_does_not_pollute_python_builtins() -> None:
    if hasattr(builtins, "is_non_working_day"):
        delattr(builtins, "is_non_working_day")
    import medical_calendar
    importlib.reload(medical_calendar)
    assert not hasattr(builtins, "is_non_working_day")
    assert callable(medical_calendar.is_non_working_day)
