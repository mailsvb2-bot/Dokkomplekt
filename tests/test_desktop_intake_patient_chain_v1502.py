from __future__ import annotations

from datetime import date
import inspect


def test_v1502_intake_diary_and_discharge_contracts():
    import desktop_intake
    import desktop_intake_agent
    from desktop_intake_mixin import DesktopIntakeMixin
    from diary_batch import _calendar_text_diary_dates, _split_regular_and_final_text_diary_dates

    assert desktop_intake.DESKTOP_INTAKE_SETUP_PROMPT_VERSION == "v4-intake-patient-folder-confirm"
    assert desktop_intake.DESKTOP_INTAKE_REASKS_AFTER_FOLDER_NAMING_REGRESSION is True
    assert desktop_intake_agent.AGENT_VERSION == "v1.9"
    assert desktop_intake_agent.DESKTOP_INTAKE_AGENT_REASKS_OLD_DISABLED_SETTINGS is True
    assert "_ensure_patient_folder_naming_configured(force=True)" in inspect.getsource(DesktopIntakeMixin._open_desktop_intake_popup)
    assert _calendar_text_diary_dates(date(2026, 7, 3), None, limit=3, day_offsets=(1, 2, 3)) == (date(2026, 7, 4), date(2026, 7, 5), date(2026, 7, 6))
    regular, final_date = _split_regular_and_final_text_diary_dates((date(2026, 7, 4), date(2026, 7, 5)), discharge_date_value=date(2026, 7, 5), force_final_diary=True)
    assert regular == (date(2026, 7, 4),)
    assert final_date == date(2026, 7, 5)


def test_v1502_discharge_button_route_exists():
    from actions_creation_execution import ActionsCreationExecutionMixin
    assert hasattr(ActionsCreationExecutionMixin, "_route_legacy_medical_selection_to_profile_docs")
