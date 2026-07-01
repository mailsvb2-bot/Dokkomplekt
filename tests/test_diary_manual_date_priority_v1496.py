from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from docx import Document

from actions_diary_flow import ActionsDiaryFlowMixin
from diary_creation_wizard import build_diary_wizard_review
from diary_template_selection import DiaryTemplateSelectionMixin
from medical_date_state import apply_semantic_date
from medical_models import PatientData


class FakeVar:
    def __init__(self, value="") -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


class FakeDiaryApp(ActionsDiaryFlowMixin, DiaryTemplateSelectionMixin):
    def __init__(self, primary_path: Path) -> None:
        self.navigation_path_var = FakeVar(str(primary_path))
        self.admission_date_var = FakeVar("")
        self.discharge_date_var = FakeVar("")
        self.patient_name_var = FakeVar("Patient Example")
        self.repeat_statuses_var = FakeVar(True)
        self.reset_each_file_var = FakeVar(True)
        self.keep_signature_var = FakeVar(True)
        self.fill_months_var = FakeVar(True)
        self.force_final_diary_var = FakeVar(True)
        self.remove_holiday_rows_var = FakeVar(False)
        self.expert_sick_leave_needed_var = FakeVar("no")
        self.diary_frequency_mode_var = FakeVar("daily")
        self.status_files = ["status.docx"]
        self.diary_files = []
        self.diary_template_dir = ""
        self.diary_texts_dir = ""
        self.data = PatientData(fio="Patient Example")
        self._manual_admission_date = False
        self._manual_discharge_date = False
        self._popup_discharge_date_override = ""
        self._diary_files_auto_selected = False
        self.logged: list[str] = []

    def _set_ui_var(self, var, value):
        var.set(value)

    def _auto_select_diary_text_by_diagnosis(self, ask_folder=False):
        return False

    def choose_status_files(self):
        return None

    def _auto_select_numbered_diary_template(self, ask_folder=False):
        return False

    def _selected_profile_diary_schedule(self):
        return None

    def _normalize_yes_no(self, value):
        return str(value or "").strip().lower()

    def _diagnostic_reports_enabled(self):
        return False

    def _result_output_dir(self):
        return Path.cwd()

    def _parse_primary_document(self, _path: str):
        return PatientData(fio="Patient Example", admission_date="")

    def _log(self, text: str):
        self.logged.append(text)


def _make_docx(path: Path, text: str = "primary document without title date") -> Path:
    doc = Document()
    doc.add_paragraph(text)
    doc.save(path)
    return path


def test_diary_creation_uses_confirmed_semantic_admission_when_primary_has_no_title_date(tmp_path, monkeypatch):
    primary = _make_docx(tmp_path / "primary.docx")
    app = FakeDiaryApp(primary)
    apply_semantic_date(app, "admission_date", "02.06.2026")
    apply_semantic_date(app, "discharge_date", "10.06.2026")

    captured: dict[str, str] = {}

    def fake_fill_diary_batch(**kwargs):
        captured.update({"admission_value": kwargs["admission_value"], "discharge_value": kwargs["discharge_value"]})
        return SimpleNamespace(created_files=[], report_path=None, processed_files=0, filled_rows=0, final_rows_filled=0)

    monkeypatch.setattr("diary_batch.fill_diary_batch", fake_fill_diary_batch)

    app._create_diaries_impl()

    assert captured["admission_value"] == "02.06.2026"
    assert captured["discharge_value"] == "10.06.2026"


def test_diary_template_selection_keeps_doctor_confirmed_admission_date(tmp_path, monkeypatch):
    primary = _make_docx(tmp_path / "01.06.2026 primary.docx")
    app = FakeDiaryApp(primary)
    apply_semantic_date(app, "admission_date", "02.06.2026")

    monkeypatch.setattr("medical_admission_resolver.extract_admission_date_from_primary_docx", lambda _path: "01.06.2026")

    parsed = app._admission_datetime_for_diary_template()

    assert parsed is not None
    assert parsed.strftime("%d.%m.%Y") == "02.06.2026"
    assert app.admission_date_var.get() == "02.06.2026"


def test_diary_wizard_reads_semantic_dates_when_legacy_vars_are_empty():
    app = SimpleNamespace(
        patient_name_var=FakeVar("Patient Example"),
        admission_date_var=FakeVar(""),
        discharge_date_var=FakeVar(""),
        expert_sick_leave_needed_var=FakeVar("no"),
        diary_frequency_mode_var=FakeVar("daily"),
        diary_files=[],
        status_files=["texts.docx"],
        _diary_text_output_enabled=True,
    )
    apply_semantic_date(app, "admission_date", "02.06.2026")
    apply_semantic_date(app, "discharge_date", "10.06.2026")

    review = build_diary_wizard_review(app)

    assert review.ok
    assert review.admission_date == "02.06.2026"
    assert review.discharge_date == "10.06.2026"
