from __future__ import annotations

from pathlib import Path

import pytest

from actions_universal_flow import ActionsUniversalFlowMixin
from medical_models import PatientData
from universal_case_adapter import patient_data_to_case


class _CustomDiaryHarness(ActionsUniversalFlowMixin):
    def __init__(self, diary_texts_dir: str) -> None:
        self.status_files = []
        self.diary_texts_dir = diary_texts_dir
        self.auto_called = False
        self.choose_called = False

    def _auto_select_diary_text_by_diagnosis(self, *, ask_folder: bool = False) -> bool:
        assert ask_folder is False
        self.auto_called = True
        return False

    def choose_status_files(self) -> None:
        self.choose_called = True


class _Case:
    def get(self, key: str) -> str:
        return ""


def test_custom_diary_requires_actual_text_file_before_wizard(tmp_path: Path, monkeypatch) -> None:
    import diary_creation_wizard

    def forbidden_confirm(_app):
        raise AssertionError("wizard must not run without a concrete text file")

    monkeypatch.setattr(diary_creation_wizard, "confirm_diary_creation", forbidden_confirm)
    app = _CustomDiaryHarness(str(tmp_path))

    with pytest.raises(ValueError, match="DOC"):
        app._create_custom_diary_documents_impl(current_pack=None, case=_Case(), diary_ids=["daily_diary"], out_dir=tmp_path)

    assert app.auto_called
    assert app.choose_called


def test_patient_data_to_case_preserves_combined_vk_mse_work_position() -> None:
    data = PatientData(
        vk_mse_work_org="ACME",
        vk_mse_position="manager",
        vk_mse_work_position="ACME / manager",
    )

    case = patient_data_to_case(data)

    assert case.get("vk_mse.work_position") == "ACME / manager"
