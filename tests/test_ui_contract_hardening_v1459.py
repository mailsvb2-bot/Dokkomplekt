from __future__ import annotations

from types import SimpleNamespace

from actions_creation_preflight import ActionsCreationReviewMixin
from window_completion_dialog import _completion_field_problem_and_normalized


class _Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _PreflightHarness(ActionsCreationReviewMixin):
    def __init__(self):
        self.labs_text_var = _Var("старый текст")
        self.labs_source_path_var = _Var("старый источник")
        self.labs_without_var = _Var(False)
        self.labs_date_policy_var = _Var("preserve_found_dates")
        self.data = None


def test_preflight_no_labs_is_canonical_state_not_plain_text():
    app = _PreflightHarness()

    app._store_required_review_value("labs", "Нет анализов")

    assert app.labs_without_var.get() is True
    assert app.labs_text_var.get() == ""
    assert app.labs_source_path_var.get() == ""
    assert app.labs_date_policy_var.get() == "without_labs"


def test_custom_completion_rejects_patient_name_as_case_number():
    class _App:
        def _patient_name_for_case_number_guard(self):
            return "Иванов Иван Иванович"

    item = SimpleNamespace(field_id="case.number", label="Номер истории болезни")

    problem, normalized = _completion_field_problem_and_normalized(
        _App(), item, "Иванов Иван Иванович", required_mode=True
    )

    assert problem
    assert normalized == ""


def test_custom_completion_sanitizes_case_number():
    class _App:
        def _patient_name_for_case_number_guard(self):
            return "Иванов Иван Иванович"

    item = SimpleNamespace(field_id="case.number", label="Номер истории болезни")

    problem, normalized = _completion_field_problem_and_normalized(
        _App(), item, "  123/45  ", required_mode=True
    )

    assert problem == ""
    assert normalized == "123/45"
