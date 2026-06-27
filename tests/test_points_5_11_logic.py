from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from doctor_action_journal import append_doctor_action, JOURNAL_JSONL_NAME, JOURNAL_TXT_NAME, _history_dir
from error_taxonomy import ErrorCategory, classify_error, doctor_message
from medical_models import PatientData, build_patient_case_review
from universal_profiles import default_document_pack, mark_pack_as_department_profile, profile_scope_label, save_document_pack


def test_doctor_action_journal_writes_txt_and_jsonl(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    review = build_patient_case_review(
        PatientData(fio="Иванов Иван", output_fio="Иванов", case_number="123", diagnosis="K35.8 Острый аппендицит", admission_date="10.02.2026", treatment_plan="Лечение"),
        selected_medical=("primary",),
        output_dir=str(tmp_path),
    )
    path = append_doctor_action(output_dir=tmp_path, action="Документы созданы", review=review, created_files=[tmp_path / "a.docx"])
    assert path is not None
    history = _history_dir(tmp_path)
    assert (history / JOURNAL_TXT_NAME).exists()
    assert history != tmp_path / "_medical_autofill_history"
    jsonl = history / JOURNAL_JSONL_NAME
    row = json.loads(jsonl.read_text(encoding="utf-8").splitlines()[-1])
    assert row["action"] == "Документы созданы"
    assert row["review"]["patient_ref"].startswith("ref-")
    assert row["review"]["diagnosis"] == "K35.8"
    assert row["created_file_count"] == "1"
    assert "case_number" not in row["review"]
    assert "created_files" not in row
    assert "123" not in json.dumps(row, ensure_ascii=False)
    assert "a.docx" not in json.dumps(row, ensure_ascii=False)


def test_error_taxonomy_classifies_template_and_printer() -> None:
    template_event = classify_error("template validation", ValueError("missing placeholder"))
    assert template_event.category is ErrorCategory.TEMPLATE
    printer_event = classify_error("print_created_files", RuntimeError("printer unavailable"))
    assert printer_event.category is ErrorCategory.PRINTER
    assert "печать" in doctor_message(printer_event).lower()


def test_department_profile_metadata_and_backup(tmp_path: Path) -> None:
    profile = default_document_pack()
    mark_pack_as_department_profile(profile, department_name="Приёмное отделение")
    assert "отделения" in profile_scope_label(profile).lower()
    target = tmp_path / "profile.medpack.json"
    save_document_pack(profile, target, backup_reason="initial")
    profile.notes = "changed"
    save_document_pack(profile, target, backup_reason="import_profile")
    backups = list((tmp_path / "_profile_backups").glob("*.json"))
    assert backups, "overwriting a profile must create timestamped backup"
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["workflow_principles"]["profile_kind"] == "department"


def test_error_taxonomy_invalid_category_is_safe() -> None:
    event = classify_error("bad category", RuntimeError("x"), category="typo_category")
    assert event.category is ErrorCategory.SYSTEM
    assert len(event.message) <= 220


def test_doctor_action_journal_keeps_icd10_not_full_diagnosis(tmp_path: Path) -> None:
    review = build_patient_case_review(
        PatientData(fio="Иванов Иван", output_fio="Иванов", case_number="123", diagnosis="K35.8 Острый аппендицит с длинным описанием"),
        selected_medical=("primary",),
        output_dir=str(tmp_path),
    )
    append_doctor_action(output_dir=tmp_path, action="Документы созданы", review=review)
    row = json.loads((_history_dir(tmp_path) / JOURNAL_JSONL_NAME).read_text(encoding="utf-8").splitlines()[-1])
    assert row["review"]["diagnosis"] == "K35.8"
    assert "Острый аппендицит" not in json.dumps(row, ensure_ascii=False)


def test_profile_backups_do_not_collide(tmp_path: Path) -> None:
    profile = default_document_pack()
    target = tmp_path / "profile.medpack.json"
    save_document_pack(profile, target, backup_reason="initial")
    profile.notes = "v2"
    save_document_pack(profile, target, backup_reason="fast")
    profile.notes = "v3"
    save_document_pack(profile, target, backup_reason="fast")
    backups = sorted((tmp_path / "_profile_backups").glob("*.json"))
    assert len(backups) >= 2
    assert len({item.name for item in backups}) == len(backups)
