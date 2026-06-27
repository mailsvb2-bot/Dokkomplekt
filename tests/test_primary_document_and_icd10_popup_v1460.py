from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from actions_required_fields_popup import _is_diagnosis_field
from medical_primary_document_state import clean_primary_document_path, selected_primary_document_path, sync_selected_primary_document_path


class _Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _App:
    def __init__(self):
        self.navigation_path_var = _Var("")
        self.selected_status = ""

    def _set_primary_drop_selected(self, path: str) -> None:
        self.selected_status = Path(path).name


def test_selected_primary_path_recovers_from_last_runtime_path(tmp_path):
    doc = tmp_path / "первичный пациент.docx"
    doc.write_bytes(b"placeholder")
    app = _App()
    app._last_primary_document_path = str(doc)

    resolved = selected_primary_document_path(app)

    assert resolved == doc
    assert app.navigation_path_var.get() == str(doc.resolve())
    assert app.selected_status == doc.name


def test_sync_selected_primary_path_normalizes_braced_dnd_value(tmp_path):
    doc = tmp_path / "file with spaces.docx"
    doc.write_bytes(b"placeholder")
    app = _App()

    value = sync_selected_primary_document_path(app, "{" + str(doc) + "}")

    assert value == str(doc.resolve())
    assert app.navigation_path_var.get() == str(doc.resolve())
    assert app._active_primary_document_path == str(doc.resolve())


def test_required_fields_popup_has_icd10_autocomplete_contract():
    source = Path("actions_required_fields_popup.py").read_text(encoding="utf-8")

    assert "DialogDiagnosisPopup" in source
    assert "self.diagnosis_popup.attach(entry, var)" in source
    assert "_is_diagnosis_field(field)" in source
    assert 'field.key == "diagnosis"' not in source


def test_required_fields_popup_detects_dynamic_diagnosis_keys():
    assert _is_diagnosis_field(SimpleNamespace(key="diagnosis", label="Диагноз"))
    assert _is_diagnosis_field(SimpleNamespace(key="patient.diagnosis", label="Клинический диагноз"))
    assert _is_diagnosis_field(SimpleNamespace(key="diagnosis.primary", label="Основной диагноз"))
    assert _is_diagnosis_field(SimpleNamespace(key="custom_field", label="Диагноз по МКБ-10"))
    assert not _is_diagnosis_field(SimpleNamespace(key="case_number", label="Номер истории болезни"))


def test_clean_primary_document_path_handles_file_uri_and_tk_wrappers():
    assert clean_primary_document_path("{C:/Users/Doctor/My Patient.docx}") == "C:/Users/Doctor/My Patient.docx"
    assert clean_primary_document_path("file:///C:/Users/Doctor/My%20Patient.docx") == "C:/Users/Doctor/My Patient.docx"
    assert clean_primary_document_path("'file:///tmp/primary%20doc.docx'") == "/tmp/primary doc.docx"


def test_completion_popup_has_icd10_autocomplete_contract():
    source = Path("window_completion_dialog.py").read_text(encoding="utf-8")

    assert "DialogDiagnosisPopup" in source
    assert "_attach_completion_diagnosis_popup" in source
    assert "helper.attach(entry, var)" in source


def test_diary_text_autodiscovery_uses_clean_primary_path_from_dnd_wrappers(tmp_path):
    from files_mixin import FilesMixin

    patient_dir = tmp_path / "patient folder"
    texts_dir = patient_dir / "дневники тексты"
    texts_dir.mkdir(parents=True)
    (texts_dir / "дневник тестовый.docx").write_bytes(b"placeholder")
    primary = patient_dir / "первичный документ.docx"
    primary.write_bytes(b"placeholder")

    class App(FilesMixin):
        navigation_path_var = _Var("{" + str(primary) + "}")
        output_dir_var = _Var("")
        diary_texts_dir = ""

        def _get_saved_directory(self, _key):
            return ""

    found = App()._candidate_diary_text_dirs()

    assert texts_dir in found


def test_primary_selected_status_text_shows_clean_filename_for_wrapped_uri():
    from layout_sources import LayoutSourcesMixin

    class TypeVar:
        def get(self):
            return "primary_exam"

    class App(LayoutSourcesMixin):
        _compact_ui = False
        navigation_path_var = _Var("file:///C:/Users/Doctor/My%20Patient.docx")
        primary_document_type_var = TypeVar()

    text = App()._primary_selected_status_text()

    assert "My Patient.docx" in text
    assert "file:///" not in text
    assert "%20" not in text
