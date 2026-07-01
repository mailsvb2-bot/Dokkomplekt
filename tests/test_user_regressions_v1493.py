from __future__ import annotations

import os
import time
from pathlib import Path


def test_primary_parser_understands_solid_text_core_fields():
    from medical_parser import MedicalTextParser

    text = (
        "Первичный осмотр 05.06.2026 История болезни № 12345 "
        "Ф.И.О.: Иванов Иван Иванович Возраст: 45 лет "
        "Место жительства: г. Нижний Новгород, ул. Пушкина, 1 "
        "Место работы: ООО Ромашка Должность: инженер "
        "Жалобы: головная боль "
        "Анамнез заболевания: заболел вчера "
        "Анамнез жизни: рос и развивался нормально "
        "Лечение: режим, терапия "
        "Диагноз: J20 Острый бронхит"
    )

    data = MedicalTextParser().parse_text(text)

    assert data.admission_date == "05.06.2026"
    assert data.case_number == "12345"
    assert data.fio == "Иванов Иван Иванович"
    assert "45" in data.birth
    assert "Нижний" in data.registered
    assert "Ромашка" in data.work_org
    assert "инженер" in data.position.lower()
    assert "головная" in data.complaints.lower()
    assert "заболел" in data.disease_anamnesis.lower()
    assert data.life_anamnesis
    assert "терап" in data.treatment_plan.lower()
    assert data.diagnosis


def test_desktop_intake_top_level_docx_is_launch_intent(tmp_path, monkeypatch):
    import desktop_intake

    primary = tmp_path / "primary.docx"
    primary.write_bytes(b"fake-docx-for-monkeypatched-reader")
    stable_time = time.time() - 10
    os.utime(primary, (stable_time, stable_time))
    monkeypatch.setattr(time, "time", lambda: stable_time + 10)
    monkeypatch.setattr(desktop_intake, "_read_intake_docx_text", lambda path, context: "Первичный осмотр ФИО: Иванов Иван История болезни № 123 Диагноз: J20")

    candidates = desktop_intake.scan_primary_candidates(tmp_path, set())

    assert candidates
    assert candidates[0].path == primary


def test_clean_profile_create_flow_has_folder_naming_guard():
    root = Path(__file__).resolve().parents[1]
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))

    assert "_ensure_patient_folder_naming_configured" in source
    assert "configure_patient_folder_naming_dialog" in source
    assert "doctor_confirmed" in source


def test_diary_creation_wizard_reports_table_text_and_frequency():
    assert "таблица дневников" in Path("diary_creation_wizard.py").read_text(encoding="utf-8")
    assert "текстовый DOCX" in Path("diary_creation_wizard.py").read_text(encoding="utf-8")
    actions = Path("actions_diary_flow.py").read_text(encoding="utf-8")
    assert "diary_frequency_mode_var" in actions
    assert "diary_hour_offsets" in actions
    assert "text_output=text_output" in actions


def test_visible_license_entrypoint_exists():
    product_source = Path("product_access/__init__.py").read_text(encoding="utf-8")
    app_source = Path("app.py").read_text(encoding="utf-8")

    assert "show_product_license_dialog" in product_source
    assert "<Control-l>" in product_source
    assert "show_product_license_dialog" in app_source
