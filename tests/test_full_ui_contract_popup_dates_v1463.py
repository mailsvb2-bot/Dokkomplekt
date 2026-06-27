from __future__ import annotations

from types import SimpleNamespace

from dialog_dates import DialogDatesMixin
from medical_date_state import (
    apply_semantic_date,
    current_semantic_date,
    date_conflict,
    semantic_date_key_from_prompt,
)
from medical_models import PatientData
from universal_case_adapter import patient_data_to_case
from universal_fields import default_field_registry, normalize_field_id


class _Var:
    def __init__(self, value: str = ""):
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class _DateHarness(DialogDatesMixin):
    def __init__(self):
        self._semantic_date_state = {}
        self._popup_discharge_date_override = ""
        self.admission_date_var = _Var("10.06.2026")
        self.discharge_date_var = _Var("")
        self.commission_date_var = _Var("")
        self.vk_date_var = _Var("")
        self.vk_protocol_date_var = _Var("")
        self.sick_leave_vk_date_var = _Var("")
        self.sick_leave_vk_protocol_date_var = _Var("")
        self.sick_leave_vk_commission_date_var = _Var("")
        self.expert_sick_leave_from_var = _Var("")
        self.labs_explicit_date_var = _Var("")
        self.data = SimpleNamespace(
            admission_date="10.06.2026",
            discharge_date="",
            commission_date="",
            vk_date="",
            vk_protocol_date="",
            sick_leave_vk_date="",
            sick_leave_vk_protocol_date="",
            sick_leave_vk_commission_date="",
            expert_sick_leave_from="",
        )
        self.confirmed = []

    def _set_ui_var(self, var, value):
        var.set(value)

    def _confirm_semantic_date_conflict(self, conflict, *, parent=None):
        self.confirmed.append((conflict.key, conflict.existing, conflict.candidate, conflict.source_label))
        return False


def test_all_popup_dates_are_semantic_state_not_loose_vars():
    app = _DateHarness()
    mapping = {
        "commission_date": "11.06.2026",
        "vk_date": "12.06.2026",
        "vk_protocol_date": "12.06.2026",
        "sick_leave_vk_date": "13.06.2026",
        "sick_leave_vk_protocol_date": "13.06.2026",
        "sick_leave_vk_commission_date": "14.06.2026",
        "expert_sick_leave_from": "15.06.2026",
    }

    for key, value in mapping.items():
        assert app._store_popup_date_value(key, value, source_label="test popup") is True
        assert current_semantic_date(app, key) == value

    assert app.commission_date_var.get() == "11.06.2026"
    assert app.data.commission_date == "11.06.2026"
    assert app.vk_date_var.get() == "12.06.2026"
    assert app.data.vk_protocol_date == "12.06.2026"
    assert app.sick_leave_vk_commission_date_var.get() == "14.06.2026"
    assert app.data.expert_sick_leave_from == "15.06.2026"


def test_conflicting_popup_date_is_not_silently_overwritten():
    app = _DateHarness()
    apply_semantic_date(app, "commission.date", "11.06.2026")

    conflict = date_conflict(app, "commission_date", "12.06.2026", source_label="second commission popup")

    assert conflict is not None
    assert conflict.label == "Дата совместного осмотра"
    assert app._store_popup_date_value("commission_date", "12.06.2026", source_label="second commission popup") is False
    assert current_semantic_date(app, "commission_date") == "11.06.2026"
    assert app.commission_date_var.get() == "11.06.2026"
    assert app.confirmed == [("commission_date", "11.06.2026", "12.06.2026", "second commission popup")]


def test_prompt_date_key_inference_covers_real_doctor_popups():
    assert semantic_date_key_from_prompt("Совместный осмотр", "Дата / дата проведения комиссии") == "commission_date"
    assert semantic_date_key_from_prompt("ВК на МСЭ", "От / дата протокола / Дата протокола") == "vk_protocol_date"
    assert semantic_date_key_from_prompt("ВК больничный", "Дата проведения комиссии") == "sick_leave_vk_commission_date"
    assert semantic_date_key_from_prompt("Экспертный анамнез", "С какого числа больничный") == "expert_sick_leave_from"
    assert semantic_date_key_from_prompt("Анализы", "Дата анализов") == "labs_explicit_date"


def test_universal_case_receives_all_popup_fields_from_patient_data():
    data = PatientData(
        fio="Иванов Иван Иванович",
        case_number="123",
        admission_date="10.06.2026",
        discharge_date="20.06.2026",
        expert_work_status="да",
        expert_work_org="ООО Ромашка",
        expert_position="инженер",
        expert_sick_leave_needed="да",
        expert_sick_leave_from="11.06.2026",
        expert_sick_leave_number="ЛН-1",
        rvk_act_number="РВК-7",
        rvk_military_commissariat="районный военный комиссариат",
        commission_date="12.06.2026",
        commission_number="К-5",
        vk_date="13.06.2026",
        vk_protocol_number="ВК-9",
        vk_protocol_date="13.06.2026",
        vk_mse_work_org="ООО Ромашка",
        vk_mse_position="инженер",
        sick_leave_vk_date="14.06.2026",
        sick_leave_vk_protocol_number="Б-3",
        sick_leave_vk_protocol_date="14.06.2026",
        sick_leave_vk_commission_date="15.06.2026",
        sick_leave_vk_work_org="ООО Ромашка",
        sick_leave_vk_position="инженер",
    )

    case = patient_data_to_case(data)

    assert case.get("commission.date") == "12.06.2026"
    assert case.get("commission.number") == "К-5"
    assert case.get("vk_mse.date") == "13.06.2026"
    assert case.get("vk_mse.protocol_date") == "13.06.2026"
    assert case.get("sick_leave_vk.commission_date") == "15.06.2026"
    assert case.get("expert.sick_leave_from") == "11.06.2026"
    assert case.get("rvk.act_number") == "РВК-7"


def test_universal_registry_accepts_popup_aliases_and_definitions():
    registry = default_field_registry()

    for alias, expected in {
        "commission_date": "commission.date",
        "vk_protocol_date": "vk_mse.protocol_date",
        "sick_leave_vk_commission_date": "sick_leave_vk.commission_date",
        "expert_sick_leave_from": "expert.sick_leave_from",
        "rvk_act_number": "rvk.act_number",
    }.items():
        assert normalize_field_id(alias) == expected
        definition = registry.require(alias)
        assert definition.id == expected
