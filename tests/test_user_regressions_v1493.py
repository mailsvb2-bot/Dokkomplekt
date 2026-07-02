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


def test_discharge_custom_template_receives_primary_case_fields(tmp_path: Path) -> None:
    from docx import Document
    from medical_models import PatientData
    from universal_case_adapter import patient_data_to_case
    from universal_generation import render_documents_from_pack
    from universal_profiles import DocumentPack
    from universal_template_engine import attach_template_to_pack

    template = tmp_path / "discharge.docx"
    document = Document()
    document.add_paragraph("Пациент {{patient.fio}} | ИБ {{case.number}}")
    document.add_paragraph("Даты {{admission.date}} — {{discharge.date}} | Возраст {{patient.age}}")
    document.add_paragraph("Жалобы {{complaints}}")
    document.add_paragraph("Анамнез {{anamnesis.disease}}")
    document.add_paragraph("Статус {{status.objective}}")
    document.add_paragraph("Состояние {{condition.discharge}}")
    document.add_paragraph("Диагноз {{diagnosis.main}}")
    document.add_paragraph("Лечение {{treatment.plan}}")
    document.add_paragraph("Итог {{treatment.result}}")
    document.save(template)

    data = PatientData(
        fio="Петров Пётр Петрович",
        birth="45 лет",
        case_number="777",
        admission_date="01.06.2026",
        discharge_date="10.06.2026",
        complaints="головная боль",
        disease_anamnesis="заболел остро",
        somatic_status="соматически стабилен",
        mental_status="профильный статус без отрицательной динамики",
        diagnosis="J20 Острый бронхит",
        treatment_plan="режим, терапия",
        epi_text="выписывается в стабильном состоянии",
    )
    case = patient_data_to_case(data, source_document="primary.docx")
    pack = DocumentPack(pack_id="doctor.discharge", name="Профиль врача")
    spec, _copied = attach_template_to_pack(pack, template, tmp_path / "profile", button_label="Выписной эпикриз", role_id="dischargeEpicrisis")

    result = render_documents_from_pack(pack=pack, case=case, document_ids=[spec.id], output_dir=tmp_path / "out", base_dir=tmp_path / "profile", strict=True)

    assert result.ok
    text = "\n".join(paragraph.text for paragraph in Document(result.created_files[0]).paragraphs)
    assert "Петров Пётр Петрович" in text
    assert "ИБ 777" in text
    assert "01.06.2026 — 10.06.2026" in text
    assert "Возраст 45 лет" in text
    assert "головная боль" in text
    assert "заболел остро" in text
    assert "соматически стабилен" in text
    assert "выписывается в стабильном состоянии" in text
    assert "J20 Острый бронхит" in text
    assert "режим, терапия" in text


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
