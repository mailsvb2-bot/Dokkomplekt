from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dialog_expert import DialogExpertMixin


class _Var:
    def __init__(self, value="") -> None:
        self._value = value

    def get(self):
        return self._value

    def set(self, value) -> None:
        self._value = value


class _PopupFake(DialogExpertMixin):
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.labs_text_var = _Var("")
        self.labs_without_var = _Var(False)
        self.diagnosis_var = _Var("")
        self.assigned_treatment_var = _Var("")
        self.case_number_var = _Var("")
        self.expert_sick_leave_number_var = _Var("")
        self.data = None

    def _hospitalization_details_missing(self) -> bool:
        return False

    def _manual_treatment_missing(self) -> bool:
        return False

    def _selected_outputs_require_discharge_date(self) -> bool:
        return False

    def _discharge_date_missing_or_invalid(self) -> bool:
        return False

    def _case_number_missing(self) -> bool:
        return False

    def _should_prompt_discharge_sick_leave_number(self) -> bool:
        return False

    def _prompt_fields(self, **kwargs):
        self.calls.append(kwargs)
        self.labs_without_var.set(True)
        return []


def test_required_labs_popup_opens_even_when_no_text_rows_are_missing() -> None:
    fake = _PopupFake()
    assert fake._prompt_common_output_requirements(
        include_discharge_date=False,
        include_case_number=True,
        include_medical_details=True,
        include_labs_block=True,
    ) is True
    assert fake.calls, "required analyses must still show a popup when ordinary rows are complete"
    assert fake.calls[-1]["rows"] == []
    assert fake.calls[-1]["include_labs_block"] is True


def test_required_labs_popup_is_skipped_after_explicit_without_labs_choice() -> None:
    fake = _PopupFake()
    fake.labs_without_var.set(True)
    assert fake._prompt_common_output_requirements(
        include_discharge_date=False,
        include_case_number=True,
        include_medical_details=True,
        include_labs_block=True,
    ) is True
    assert fake.calls == []


def test_discharge_required_labs_popup_opens_without_duplicate_windows() -> None:
    fake = _PopupFake()
    assert fake._prompt_discharge_output_requirements(include_labs_block=True) is True
    assert len(fake.calls) == 1
    assert fake.calls[0]["title"] == "Данные для выписного эпикриза"
    assert fake.calls[0]["include_labs_block"] is True


def test_labs_scanner_checks_empty_doc_before_opening_child_window() -> None:
    source = (ROOT / "dialog_fields_core.py").read_text(encoding="utf-8")
    fn = source.split("def open_labs_selection_scanner", 1)[1].split("def _prompt_manual_labs", 1)[0]
    assert fn.index("if not scan.blocks:") < fn.index("win = tk.Toplevel(parent)")


def test_preflight_inline_editor_validates_diagnosis_case_number_and_episode_dates() -> None:
    source = (ROOT / "actions_creation_preflight.py").read_text(encoding="utf-8")
    editor = source.split("def _edit_patient_case_inside_preflight", 1)[1].split("def _confirm_patient_case_before_creation", 1)[0]
    assert "normalize_required_diagnosis_with_icd10" in editor
    assert "sanitize_case_number_candidate" in editor
    assert "Дата выписки не может быть раньше даты поступления" in editor
    assert "_focus_editor_field" in editor


def test_required_labs_without_labs_choice_satisfies_preflight_review() -> None:
    from medical_models import PatientData, augment_patient_case_review_with_custom_flags, build_patient_case_review

    review = build_patient_case_review(
        PatientData(
            fio="Иванов Иван Иванович",
            output_fio="Иванов Иван Иванович",
            case_number="123",
            admission_date="01.01.2026",
            diagnosis="K35 Острый аппендицит",
            treatment_plan="оперативное лечение",
        ),
        selected_custom=("Шаблон с анализами",),
    )
    review = augment_patient_case_review_with_custom_flags(
        review,
        {"requires_labs": True},
        labs="",
        labs_without=True,
    )
    assert review.value("labs") == "Нет анализов"
    assert "labs" not in [field.key for field in review.critical_missing()]


def test_required_invalid_episode_dates_are_critical_not_soft_warnings() -> None:
    from medical_models import PatientData, build_patient_case_review

    review = build_patient_case_review(
        PatientData(
            fio="Иванов Иван Иванович",
            output_fio="Иванов Иван Иванович",
            case_number="123",
            admission_date="не дата",
            diagnosis="K35 Острый аппендицит",
            treatment_plan="оперативное лечение",
        ),
        selected_medical=("primary",),
    )
    assert "admission_date" in [field.key for field in review.critical_missing()]

    discharge_review = build_patient_case_review(
        PatientData(
            fio="Иванов Иван Иванович",
            output_fio="Иванов Иван Иванович",
            case_number="123",
            admission_date="01.01.2026",
            discharge_date="не дата",
            diagnosis="K35 Острый аппендицит",
            treatment_plan="оперативное лечение",
        ),
        selected_medical=("discharge",),
    )
    assert "discharge_date" in [field.key for field in discharge_review.critical_missing()]


def test_custom_rvk_labs_get_standalone_labs_popup_when_no_discharge_popup_will_cover_it() -> None:
    from actions_creation_batch import ActionsCreationBatchingMixin

    class _Var:
        def __init__(self, value="") -> None:
            self._value = value
        def get(self):
            return self._value
        def set(self, value) -> None:
            self._value = value

    class _App(ActionsCreationBatchingMixin):
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []
            self.labs_text_var = _Var("")
            self.labs_without_var = _Var(False)
            self.commission_date_var = _Var("01.01.2026")
            self.commission_number_var = _Var("1")
            self.vk_date_var = _Var("01.01.2026")
            self.vk_protocol_number_var = _Var("1")
            self.vk_protocol_date_var = _Var("01.01.2026")
            self.vk_mse_work_org_var = _Var("ООО")
            self.sick_leave_vk_date_var = _Var("01.01.2026")
            self.sick_leave_vk_protocol_number_var = _Var("1")
            self.sick_leave_vk_protocol_date_var = _Var("01.01.2026")
            self.sick_leave_vk_commission_date_var = _Var("01.01.2026")
            self.sick_leave_vk_work_org_var = _Var("ООО")
            self.sick_leave_vk_position_var = _Var("должность")

        def _custom_requirement_flags(self, _selected_custom):
            return {
                "diary": False,
                "regular": True,
                "discharge": False,
                "rvk": True,
                "commission": False,
                "vk_mse": False,
                "sick_leave_vk": False,
                "requires_case_number": True,
                "requires_diagnosis": True,
                "requires_treatment": True,
                "requires_discharge_date": True,
                "requires_labs": True,
            }

        def _prompt_common_output_requirements(self, **kwargs):
            self.calls.append(("common", kwargs))
            self.labs_without_var.set(True)
            return True

        def _labs_required_missing(self):
            return not bool(self.labs_without_var.get()) and not bool(self.labs_text_var.get().strip())

        def _rvk_needs_popup(self):
            return True

        def _prompt_rvk_details(self):
            self.calls.append(("rvk", {}))
            return True

        def _vk_mse_details_complete(self):
            return True

        def _sick_leave_vk_details_complete(self):
            return True

        def _expert_anamnesis_needed_for_selection(self, selected_medical, custom=None):
            return False

        def _prompt_assigned_treatment_if_needed(self, **kwargs):
            self.calls.append(("treatment", kwargs))
            return True

    app = _App()
    assert app._collect_creation_requirements([], False, ["custom_rvk_labs"]) is True
    assert app.calls[0] == ("common", {
        "include_discharge_date": False,
        "include_case_number": False,
        "include_medical_details": False,
        "include_labs_block": True,
    })
    assert any(call[0] == "rvk" for call in app.calls)
