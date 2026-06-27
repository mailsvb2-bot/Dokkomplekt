"""Regression tests for v1.4.10 universal/personal-buttons hardening."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

from docx import Document

from architecture_contracts import assert_architecture_contracts
from medical_language_detector import detect_text_language
from personal_document_buttons import stable_document_id, suggest_button_label_for_template
from regulatory_completion_blocks import completion_inputs_for_missing_fields
from universal_fields import PatientCase, default_field_registry
from universal_generation import render_documents_from_pack
from universal_main_documents import custom_requirement_flags_for_documents
from universal_profiles import DocumentPack, ExtractionRule
from universal_scanner import scan_docx
from universal_template_engine import attach_template_to_pack

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "test_run_universal_hardening"
OUT.mkdir(exist_ok=True)


def _docx(path: Path, paragraphs: list[str]) -> Path:
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    doc.save(path)
    return path


def run() -> None:
    assert_architecture_contracts()
    registry = default_field_registry()

    # Placeholders must not make a Russian/doctor-local template look English.
    detection = detect_text_language("Протокол операции {{patient.fio}} {{procedure.name}}")
    assert detection.language_id == "ru", detection.to_dict()

    op1 = _docx(OUT / "operation_primary.docx", [
        "Протокол операции",
        "Пациент: {{patient.fio}}",
        "Операция: {{procedure.name}}",
        "Анестезия: {{procedure.anesthesia}}",
        "Ход операции: {{procedure.description}}",
    ])
    op2 = _docx(OUT / "operation_repeat.docx", [
        "Протокол повторной операции",
        "Пациент: {{patient.fio}}",
        "Операция: {{procedure.name}}",
        "Ход операции: {{procedure.description}}",
    ])
    suggestion = suggest_button_label_for_template(op1, preferred_language="ru", explicit_role_id="operation_protocol")
    assert suggestion.label == "Протокол операции"
    assert suggestion.source_language == "ru"
    assert suggestion.document_id.startswith("operation_protocol_")

    generic_certificate = _docx(OUT / "generic_certificate.docx", [
        "Справка для бассейна",
        "Пациент: {{patient.fio}}",
        "Диагноз: {{diagnosis.main}}",
    ])
    generic_suggestion = suggest_button_label_for_template(generic_certificate, preferred_language="ru", explicit_specialty="generic")
    assert generic_suggestion.label == "Справка для бассейна"
    assert generic_suggestion.role_id == "unknown", generic_suggestion.to_dict()

    generic_endoscopy = _docx(OUT / "generic_endoscopy.docx", [
        "Протокол эндоскопического исследования",
        "Пациент: {{patient.fio}}",
        "Заключение: {{instrumental.results}}",
    ])
    endoscopy_suggestion = suggest_button_label_for_template(generic_endoscopy, preferred_language="ru", explicit_specialty="generic")
    assert endoscopy_suggestion.label == "Протокол эндоскопического исследования"
    assert endoscopy_suggestion.role_id == "unknown", endoscopy_suggestion.to_dict()

    def custom_doc(label: str, *, role_id: str = "", document_id: str = "custom", category: str = "medical"):
        return SimpleNamespace(
            id=document_id,
            document_id=document_id,
            role_id=role_id,
            category=category,
            button_label=label,
            template=f"templates/{label}.docx",
            description="",
            required_fields=(),
            optional_fields=(),
        )

    legacy_role_cases = (
        (custom_doc("Выписной эпикриз", document_id="discharge"), "discharge", "requires_discharge_date"),
        (custom_doc("Совместный осмотр", role_id="joint_medical_exam"), "commission", "requires_treatment"),
        (custom_doc("ВК на МСЭ", role_id="vk_mse"), "vk_mse", "requires_diagnosis"),
        (custom_doc("ВК больничный", role_id="sick_leave_vk"), "sick_leave_vk", "requires_case_number"),
        (custom_doc("Акт для РВК", role_id="military_commissariat_act"), "rvk", "requires_discharge_date"),
        (custom_doc("Дневник наблюдения", role_id="daily_diary", category="diaries"), "diary", "requires_discharge_date"),
    )
    for document, role_flag, requirement_flag in legacy_role_cases:
        flags = custom_requirement_flags_for_documents((document,))
        assert flags[role_flag], (document.button_label, role_flag, flags)
        assert flags[requirement_flag], (document.button_label, requirement_flag, flags)
    assert not custom_requirement_flags_for_documents((custom_doc("Дневник наблюдения", role_id="daily_diary", category="diaries"),))["regular"]

    assert stable_document_id("operation_protocol", "ოპერაციის პროტოკოლი", "ოპერაცია.docx") != stable_document_id("operation_protocol", "ოპერაციის პროტოკოლი", "მეორე.docx")
    assert DocumentPack.from_dict({"pack_id": "legacy", "name": "Legacy"}).source_document_types

    pack = DocumentPack(pack_id="hardening.pack", name="Hardening pack", documents=())
    spec1, _ = attach_template_to_pack(pack, op1, OUT / "profile", button_label="Протокол операции", document_id=suggestion.document_id, registry=registry, role_id="operation_protocol", button_language="ru", source_language="ru")
    spec2, _ = attach_template_to_pack(pack, op2, OUT / "profile", button_label="Протокол повторной операции", document_id=suggestion.document_id, registry=registry, role_id="operation_protocol", button_language="ru", source_language="ru")
    assert len(pack.documents) == 2
    assert spec1.id != spec2.id

    source = _docx(OUT / "source_with_rule.docx", [
        "Пациент: Иванов Иван Иванович",
        "История болезни № 123",
        "Дата поступления: 10.06.2026",
        "Диагноз: тестовый диагноз",
        "Анестезия: спинальная",
    ])
    rule = ExtractionRule(field_id="procedure.anesthesia", strategy="label_after", label="Анестезия", confidence=0.95)
    scanned = scan_docx(source, registry=registry, rules=(rule,))
    assert scanned.patient_case().get("procedure.anesthesia") == "спинальная"

    case = PatientCase()
    case.update_from_pairs({
        "patient.fio": "Иванов Иван Иванович",
        "procedure.name": "аппендэктомия",
        "procedure.anesthesia": "спинальная",
        "procedure.description": "доступ, обработка, гемостаз",
    }, confidence=1.0, source_document="test")
    result = render_documents_from_pack(
        pack=pack,
        case=case,
        document_ids=(spec1.id, spec2.id),
        output_dir=OUT / "rendered",
        base_dir=OUT / "profile",
        strict=False,
        output_language="ru",
        spellcheck_enabled=True,
    )
    assert len(result.created_files) == 2, result.human_report()
    assert not result.skipped_documents, result.human_report()

    missing_case = PatientCase()
    missing_case.update_from_pairs({"patient.fio": "Иванов Иван Иванович"}, confidence=1.0)
    inputs = completion_inputs_for_missing_fields(("procedure.name", "procedure.description"), registry=registry, existing_case=missing_case)
    assert [item.field_id for item in inputs] == ["procedure.name", "procedure.description"]
    assert all(item.placeholder.startswith("{{") for item in inputs)

    # Output directory pointing to a file must be rejected deterministically.
    file_as_dir = OUT / "not_a_dir.txt"
    file_as_dir.write_text("x", encoding="utf-8")
    try:
        render_documents_from_pack(pack=pack, case=case, document_ids=(spec1.id,), output_dir=file_as_dir, base_dir=OUT / "profile")
    except ValueError as exc:
        assert "указывает на файл" in str(exc)
    else:
        raise AssertionError("output_dir=file was not rejected")

    # Performance guard: small profile rendering must stay comfortably local/fast.
    start = time.perf_counter()
    render_documents_from_pack(pack=pack, case=case, document_ids=(spec1.id, spec2.id), output_dir=OUT / "rendered_perf", base_dir=OUT / "profile", strict=False)
    elapsed = time.perf_counter() - start
    assert elapsed < 3.0, f"Universal generation is too slow for a tiny pack: {elapsed:.3f}s"


if __name__ == "__main__":
    run()
    print("UNIVERSAL HARDENING SMOKE OK")
