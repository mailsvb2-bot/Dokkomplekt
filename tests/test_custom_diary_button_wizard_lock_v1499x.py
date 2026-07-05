from __future__ import annotations

from pathlib import Path


def test_custom_diary_button_uses_same_wizard_as_diary_checkbox():
    source = Path("actions_universal_flow.py").read_text(encoding="utf-8")
    section = source.split("def _create_custom_diary_documents_impl", 1)[1]
    assert "confirm_diary_creation(self)" in section
    assert "current_diary_calendar_schedule" in section
    assert "diary_day_offsets=" in section
    assert "diary_hour_offsets=" in section
    assert "diary_minute_offsets=" in section
