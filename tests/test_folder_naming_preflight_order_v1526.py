from pathlib import Path

import pytest

from actions_creation_foldering import ActionsCreationFolderingMixin
from actions_creation_preflight import ActionsCreationReviewMixin
from actions_folder_naming_preflight import ActionsFolderNamingPreflightMixin
from medical_models import PatientData


class _Var:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class _ConfirmStub:
    def _confirm_patient_case_before_creation(self, _review) -> bool:
        return True


class _Subject(
    ActionsFolderNamingPreflightMixin,
    _ConfirmStub,
    ActionsCreationReviewMixin,
    ActionsCreationFolderingMixin,
):
    def __init__(self, root: Path) -> None:
        self.root_dir = root
        self.data = PatientData(
            admission_date="10.10.2024",
            discharge_date="09.09.2026",
            diagnosis="F20.0",
        )
        self._settings = {
            "folder_naming": {
                "parts": ["surname_initials"],
                "date_format": "short",
                "doctor_confirmed": True,
            }
        }
        self.case_number_var = _Var()
        self.assigned_treatment_var = _Var()

    def _base_output_dir(self) -> Path:
        return self.root_dir


def test_missing_folder_identity_reaches_required_field_preflight(tmp_path: Path) -> None:
    app = _Subject(tmp_path)

    review = app._build_patient_case_review_for_selection([], True, [])

    missing = {field.key for field in review.critical_missing()}
    assert {"fio", "output_fio"} <= missing
    assert Path(review.output_dir).name == "Пациент"


def test_folder_naming_becomes_strict_after_preflight_confirmation(tmp_path: Path) -> None:
    app = _Subject(tmp_path)
    review = app._build_patient_case_review_for_selection([], True, [])
    assert app._confirm_patient_case_before_creation(review) is True

    with pytest.raises(ValueError, match="Фамилия полностью"):
        app._build_patient_case_review_for_selection([], True, [])

    app.data.fio = "Баннина Елена Геннадьевна"
    app.data.output_fio = "Баннина Елена Геннадьевна"
    final_review = app._build_patient_case_review_for_selection([], True, [])

    assert Path(final_review.output_dir).name == "Баннина Е.Г."
