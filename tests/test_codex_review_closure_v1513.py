from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_pdf_overwrite_plan_includes_existing_pdf(monkeypatch, tmp_path: Path) -> None:
    from actions_creation_foldering import ActionsCreationFolderingMixin

    docx = tmp_path / "Иванов Справка.docx"
    pdf = docx.with_suffix(".pdf")
    docx.write_bytes(b"docx")
    pdf.write_bytes(b"pdf")
    app = SimpleNamespace(
        _planned_custom_output_format="pdf",
        _result_output_dir=lambda: tmp_path,
        _current_universal_patient_case=lambda: object(),
        _effective_output_language=lambda: "auto",
        spellcheck_enabled_var=None,
    )
    app._existing_medical_targets = lambda review, selected: []
    app._selected_custom_document_specs = lambda selected: [SimpleNamespace(category="medical")]
    monkeypatch.setattr("universal_generation.render_output_name", lambda *args, **kwargs: docx.name)

    existing = ActionsCreationFolderingMixin._existing_all_targets(app, SimpleNamespace(output_dir=str(tmp_path), patient_stem=lambda: "Иванов"), [], ["custom"], False)
    assert docx in existing
    assert pdf in existing



def test_custom_output_format_is_planned_once_before_collision_scan() -> None:
    from actions_document_intelligence_flow import ActionsDocumentIntelligenceFlowMixin

    class Fake(ActionsDocumentIntelligenceFlowMixin):
        def __init__(self) -> None:
            self.calls = 0
        def _load_or_create_universal_pack(self):
            return object()
        def _split_custom_diary_document_ids(self, current_pack, selected_custom_ids):
            return [], list(selected_custom_ids)
        def _ask_custom_document_output_format(self) -> str:
            self.calls += 1
            return "pdf"

    app = Fake()
    assert app._prepare_custom_document_output_format(["custom"]) == "pdf"
    assert app._planned_custom_output_format == "pdf"
    assert app.calls == 1

def test_batch_default_folder_naming_remains_non_strict_without_doctor_confirmation(tmp_path: Path) -> None:
    from medical_models import PatientData
    from medical_service import _batch_patient_dir_name

    patient = PatientData(fio="Иванов Иван Иванович", admission_date="")
    name = _batch_patient_dir_name(patient, tmp_path / "source.docx", None)
    assert name.startswith("Иванов")


def test_batch_confirmed_folder_rule_stays_strict(tmp_path: Path) -> None:
    from medical_models import PatientData
    from medical_service import _batch_patient_dir_name

    patient = PatientData(fio="Иванов Иван Иванович", admission_date="")
    settings = {"parts": ["surname_initials", "admission_month"], "doctor_confirmed": True}
    with pytest.raises(ValueError, match="не хватает данных"):
        _batch_patient_dir_name(patient, tmp_path / "source.docx", settings)


def test_gui_lock_rejects_reused_live_pid_with_different_process_identity(monkeypatch, tmp_path: Path) -> None:
    import desktop_intake_agent as agent

    lock = tmp_path / "gui.json"
    lock.write_text(json.dumps({"pid": 5151, "process_started": "win:old", "updated_at": 999990.0}), encoding="utf-8")
    monkeypatch.setattr(agent, "_gui_lock_path", lambda: lock)
    monkeypatch.setattr(agent, "_pid_is_running", lambda pid: pid == 5151)
    monkeypatch.setattr(agent, "_process_start_identity", lambda pid: "win:new" if pid == 5151 else "")
    assert agent.is_gui_runtime_active(now=1000000.0) is False
    assert not lock.exists()


def test_legacy_gui_lock_live_pid_has_bounded_stale_grace(monkeypatch, tmp_path: Path) -> None:
    import desktop_intake_agent as agent

    lock = tmp_path / "gui.json"
    lock.write_text(json.dumps({"pid": 5151, "updated_at": 1.0}), encoding="utf-8")
    monkeypatch.setattr(agent, "_gui_lock_path", lambda: lock)
    monkeypatch.setattr(agent, "_pid_is_running", lambda pid: pid == 5151)
    monkeypatch.setattr(agent, "_process_start_identity", lambda pid: "")
    now = 1.0 + agent.GUI_LEGACY_LIVE_PID_MAX_STALE_SECONDS + 1.0
    assert agent.is_gui_runtime_active(now=now) is False
