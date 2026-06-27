from __future__ import annotations

from types import SimpleNamespace

from actions_required_fields_popup import (
    _RequiredFieldsDialog,
    _is_admission_date_field,
    _is_case_number_field,
    _is_diagnosis_field,
    _is_discharge_date_field,
    _is_labs_field,
    _is_treatment_field,
    _store_key_for_field,
)
from universal_fields import PatientCase, normalize_field_id
from universal_main_documents import custom_requirement_flags_for_documents


class _App:
    def __init__(self) -> None:
        self.stored: list[tuple[str, str]] = []
        self.discharge_stored: list[str] = []

    def _store_required_review_value(self, key: str, value: str) -> None:
        self.stored.append((key, value))

    def _store_discharge_date_value(self, value: str, **_kwargs) -> bool:
        self.discharge_stored.append(value)
        return True


def _field(key: str, label: str = "", value: str = ""):
    return SimpleNamespace(key=key, field_id=key, label=label, placeholder="", reason="", value=value)


def _doc(*fields: str, label: str = "Custom"):
    return SimpleNamespace(
        id="custom_doc",
        document_id="custom_doc",
        role_id="",
        category="documents",
        button_label=label,
        template="custom.docx",
        description="",
        required_fields=tuple(fields),
        optional_fields=(),
    )


def test_universal_field_aliases_close_common_export_spellings():
    aliases = {
        "historyNumber": "case.number",
        "medical_record_number": "case.number",
        "case/no": "case.number",
        "admissionDate": "admission.date",
        "hospitalization_date": "admission.date",
        "dischargeDate": "discharge.date",
        "date/of/discharge": "discharge.date",
        "mainDiagnosis": "diagnosis.main",
        "icd_code": "diagnosis.icd10",
        "treatmentPlan": "treatment.plan",
        "prescribed_treatment": "treatment.plan",
        "labResults": "labs.results",
        "analysis_results": "labs.results",
    }
    for raw, expected in aliases.items():
        assert normalize_field_id(raw) == expected


def test_patient_case_uses_same_aliases_as_custom_renderer():
    case = PatientCase()
    case.set("historyNumber", "42")
    case.set("admissionDate", "01.06.2026")
    case.set("dischargeDate", "12.06.2026")
    case.set("mainDiagnosis", "I10 Гипертензия")
    case.set("treatmentPlan", "Терапия")
    case.set("analysis_results", "Hb 140")

    assert case.get("case.number") == "42"
    assert case.get("admission.date") == "01.06.2026"
    assert case.get("discharge.date") == "12.06.2026"
    assert case.get("diagnosis.main") == "I10 Гипертензия"
    assert case.get("treatment.plan") == "Терапия"
    assert case.get("labs.results") == "Hb 140"


def test_required_popup_semantics_cover_common_noncanonical_aliases():
    samples = [
        (_field("historyNumber", "History No"), _is_case_number_field, "case_number"),
        (_field("medical_record_number", "№ медицинской карты"), _is_case_number_field, "case_number"),
        (_field("admissionDate", "Поступил"), _is_admission_date_field, "admission_date"),
        (_field("dischargeDate", "Выписан"), _is_discharge_date_field, "discharge_date"),
        (_field("mainDiagnosis", "Клинический диагноз"), _is_diagnosis_field, "diagnosis"),
        (_field("treatmentPlan", "Назначения"), _is_treatment_field, "treatment"),
        (_field("labResults", "Лабораторные исследования"), _is_labs_field, "labs"),
    ]
    for field, detector, store_key in samples:
        assert detector(field), field
        assert _store_key_for_field(field) == store_key


def test_required_popup_stores_alias_values_into_canonical_state():
    app = _App()
    fields = [
        _field("historyNumber", "History No"),
        _field("admissionDate", "Поступил"),
        _field("treatmentPlan", "Назначения"),
        _field("analysis_results", "Анализы"),
    ]
    dialog = _RequiredFieldsDialog(app, SimpleNamespace(), fields)

    assert dialog._store_value("historyNumber", "ИБ-42")
    assert dialog._store_value("admissionDate", "01.06.2026")
    assert dialog._store_value("treatmentPlan", "Терапия")
    assert dialog._store_value("analysis_results", "Hb 140")

    assert app.stored == [
        ("case_number", "ИБ-42"),
        ("admission_date", "01.06.2026"),
        ("treatment", "Терапия"),
        ("labs", "Hb 140"),
    ]


def test_custom_requirement_flags_use_same_alias_registry():
    flags = custom_requirement_flags_for_documents([
        _doc("historyNumber", "mainDiagnosis", "treatmentPlan", "dischargeDate", "analysis_results")
    ])

    assert flags["requires_case_number"] is True
    assert flags["requires_diagnosis"] is True
    assert flags["requires_treatment"] is True
    assert flags["requires_discharge_date"] is True
    assert flags["requires_labs"] is True
