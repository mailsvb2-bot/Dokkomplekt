from __future__ import annotations

import pytest

from medical_models import PatientData
from medical_service import MedicalDocumentService, legacy_fixed_template_backend_enabled


def _base_patient() -> PatientData:
    return PatientData(
        fio="Иванов Иван Иванович",
        birth="1980",
        admission_date="01.06.2026",
        case_number="123",
        diagnosis="I10 Гипертензивная болезнь",
        treatment_plan="Назначенное лечение",
        vk_date="02.06.2026",
        vk_protocol_number="7",
        vk_protocol_date="02.06.2026",
    )


def test_patient_data_has_vk_mse_combined_work_position_field() -> None:
    patient = PatientData()
    patient.vk_mse_work_position = "ООО Ромашка, инженер"
    assert patient.vk_mse_work_position == "ООО Ромашка, инженер"


def test_vk_mse_service_boundary_requires_position_for_working_patient() -> None:
    patient = _base_patient()
    patient.vk_mse_work_org = "ООО Ромашка"
    patient.vk_mse_position = ""
    patient.vk_mse_work_position = ""

    with pytest.raises(ValueError, match="должность"):
        MedicalDocumentService()._validate_and_normalize_selected_data(patient, ["vk_mse"])


def test_vk_mse_service_boundary_accepts_combined_work_position() -> None:
    patient = _base_patient()
    patient.vk_mse_work_org = "ООО Ромашка"
    patient.vk_mse_position = ""
    patient.vk_mse_work_position = "ООО Ромашка, инженер"

    MedicalDocumentService()._validate_and_normalize_selected_data(patient, ["vk_mse"])

    assert patient.vk_mse_work_position == "ООО Ромашка, инженер"


def test_legacy_fixed_template_backend_is_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOKKOMPLEKT_ENABLE_LEGACY_FIXED_TEMPLATES", raising=False)
    assert legacy_fixed_template_backend_enabled() is False

    monkeypatch.setenv("DOKKOMPLEKT_ENABLE_LEGACY_FIXED_TEMPLATES", "1")
    assert legacy_fixed_template_backend_enabled() is True
