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


def test_dynamic_required_field_semantics_are_detected_by_meaning():
    assert _is_case_number_field(_field("case.number", "Номер истории болезни"))
    assert _is_case_number_field(_field("patient.case_number", "История болезни №"))
    assert _is_admission_date_field(_field("admission.date", "Дата поступления"))
    assert _is_admission_date_field(_field("hospitalization.date", "Дата госпитализации"))
    assert _is_discharge_date_field(_field("discharge.date", "Дата выписки"))
    assert _is_discharge_date_field(_field("discharge_date", "Выписан"))
    assert _is_diagnosis_field(_field("diagnosis.main", "Клинический диагноз"))
    assert _is_treatment_field(_field("treatment.plan", "Назначенное лечение"))
    assert _is_labs_field(_field("analysis.results", "Лабораторные анализы"))


def test_dynamic_required_fields_store_into_canonical_ui_state_keys():
    assert _store_key_for_field(_field("case.number", "Номер истории болезни")) == "case_number"
    assert _store_key_for_field(_field("admission.date", "Дата поступления")) == "admission_date"
    assert _store_key_for_field(_field("discharge.date", "Дата выписки")) == "discharge_date"
    assert _store_key_for_field(_field("diagnosis.main", "Диагноз")) == "diagnosis"
    assert _store_key_for_field(_field("treatment.plan", "Лечение")) == "treatment"
    assert _store_key_for_field(_field("analysis.results", "Анализы")) == "labs"


def test_required_popup_stores_dynamic_case_treatment_and_labs_without_second_state():
    app = _App()
    fields = [
        _field("case.number", "Номер истории болезни"),
        _field("treatment.plan", "Назначенное лечение"),
        _field("analysis.results", "Анализы"),
    ]
    dialog = _RequiredFieldsDialog(app, SimpleNamespace(), fields)

    assert dialog._store_value("case.number", "ИБ-42")
    assert dialog._store_value("treatment.plan", "Терапия по плану")
    assert dialog._store_value("analysis.results", "Hb 140")

    assert app.stored == [
        ("case_number", "ИБ-42"),
        ("treatment", "Терапия по плану"),
        ("labs", "Hb 140"),
    ]


def test_required_popup_keeps_dynamic_discharge_confirmation_before_close():
    app = _App()
    field = _field("discharge.date", "Дата выписки")
    dialog = _RequiredFieldsDialog(app, SimpleNamespace(), [field])
    dialog.win = SimpleNamespace()  # parent placeholder; fake app method ignores it

    assert dialog._store_value("discharge.date", "12.06.2026")

    assert app.discharge_stored == ["12.06.2026"]
    assert app.stored == []
