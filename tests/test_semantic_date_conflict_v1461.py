from __future__ import annotations

from types import SimpleNamespace

from medical_date_state import apply_semantic_date, current_semantic_date, date_conflict
from dialog_dates import DialogDatesMixin
from dialog_expert import DialogExpertMixin


class _Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _DateHarness(DialogDatesMixin, DialogExpertMixin):
    def __init__(self):
        self._semantic_date_state = {}
        self._popup_discharge_date_override = ""
        self.discharge_date_var = _Var("")
        self.admission_date_var = _Var("10.06.2026")
        self.data = SimpleNamespace(discharge_date="", admission_date="10.06.2026")
        self._manual_discharge_date = False
        self.confirmed = []

    def _set_ui_var(self, var, value):
        var.set(value)

    def _confirm_semantic_date_conflict(self, conflict, *, parent=None):
        self.confirmed.append((conflict.existing, conflict.candidate, conflict.source_label))
        return False


def test_semantic_discharge_date_is_single_source_for_ui_data_and_state():
    app = _DateHarness()

    assert app._store_discharge_date_value("11062026", source_label="first popup") is True

    assert current_semantic_date(app, "discharge.date") == "11.06.2026"
    assert app.discharge_date_var.get() == "11.06.2026"
    assert app.data.discharge_date == "11.06.2026"


def test_conflicting_discharge_date_is_not_silently_overwritten():
    app = _DateHarness()
    apply_semantic_date(app, "discharge_date", "11.06.2026")

    assert date_conflict(app, "discharge_date", "12.06.2026") is not None
    assert app._store_discharge_date_value("12.06.2026", source_label="second popup") is False

    assert app._current_discharge_date_value() == "11.06.2026"
    assert app.discharge_date_var.get() == "11.06.2026"
    assert app.data.discharge_date == "11.06.2026"
    assert app.confirmed == [("11.06.2026", "12.06.2026", "second popup")]


def test_confirmed_conflicting_discharge_date_replaces_everywhere():
    class _AcceptingHarness(_DateHarness):
        def _confirm_semantic_date_conflict(self, conflict, *, parent=None):
            self.confirmed.append((conflict.existing, conflict.candidate, conflict.source_label))
            return True

    app = _AcceptingHarness()
    apply_semantic_date(app, "discharge_date", "11.06.2026")

    assert app._store_discharge_date_value("12.06.2026", source_label="doctor corrected popup") is True

    assert app._current_discharge_date_value() == "12.06.2026"
    assert app.discharge_date_var.get() == "12.06.2026"
    assert app.data.discharge_date == "12.06.2026"
    assert app.confirmed == [("11.06.2026", "12.06.2026", "doctor corrected popup")]
