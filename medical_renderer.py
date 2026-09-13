"""Facade рендера медицинских документов.

Документ-специфичные render_* методы вынесены в отдельные mixin-модули,
а публичный класс MedicalDocumentRenderer сохранён.
"""

from __future__ import annotations

from pathlib import Path

from medical_gender import adapt_patient_data_to_gender
from medical_models import PatientData
from medical_renderer_commission import MedicalRendererCommissionMixin
from medical_renderer_labs import MedicalRendererLabsMixin
from medical_renderer_primary import MedicalRendererPrimaryMixin
from medical_renderer_special import MedicalRendererSpecialMixin


def _append_additional_info_to_docx(output_path: str | Path, data: PatientData) -> None:
    text = str(getattr(data, "additional_info_text", "") or "").strip()
    if not text:
        return
    from docx import Document
    doc = Document(str(output_path))
    doc.add_paragraph("")
    doc.add_paragraph("Дополнительная информация:")
    for line in text.splitlines():
        line = line.strip()
        if line:
            doc.add_paragraph(line)
    doc.save(str(output_path))


class MedicalDocumentRenderer(
    MedicalRendererPrimaryMixin,
    MedicalRendererCommissionMixin,
    MedicalRendererSpecialMixin,
    MedicalRendererLabsMixin,
):
    def render(self, kind: str, template_path: str | Path, output_path: str | Path, data: PatientData) -> None:
        methods = {
            "primary": self.render_primary,
            "discharge": self.render_discharge,
            "commission": self.render_commission,
            "vk_mse": self.render_vk_mse,
            "admission_doctor_referral": self.render_admission_doctor_referral,
            "sick_leave_vk": self.render_sick_leave_vk,
            "rvk": self.render_rvk,
        }
        method = methods.get(kind)
        if method is None:
            raise ValueError(f"Неизвестный тип медицинского документа: {kind}")
        gender_adapted_data = adapt_patient_data_to_gender(data)
        method(template_path, output_path, gender_adapted_data)
        _append_additional_info_to_docx(output_path, gender_adapted_data)

        # A Word template is layout + fixed boilerplate, never a donor patient.
        # Strip any patient/sample payload that survived the role renderer
        # unchanged and is not supported by the canonical current case.
        from document_intelligence.form_fill import remove_unchanged_medical_template_payloads
        from universal_case_adapter import patient_data_to_case

        role_by_kind = {
            "primary": "primary_exam",
            "discharge": "discharge_epicrisis",
            "commission": "joint_medical_exam",
            "vk_mse": "vk_mse",
            "admission_doctor_referral": "admission_doctor_exam",
            "sick_leave_vk": "sick_leave_vk",
            "rvk": "military_commissariat_act",
        }
        case = patient_data_to_case(gender_adapted_data, source_document=str(template_path))
        remove_unchanged_medical_template_payloads(
            template_path,
            output_path,
            {field_id: value.value for field_id, value in case.values.items()},
            role_id=role_by_kind[kind],
            category="medical",
            button_label=kind,
        )


def apply_role_owned_medical_postprocessing(output: str | Path, case, document) -> None:
    """Enforce role-owned medical wording after generic DOCX field filling."""
    from diagnostic_logging import record_soft_exception
    from docx import Document
    from docx.shared import RGBColor
    from medical_admission_resolver import admission_to_department_phrase, normalize_admission_mode
    from medical_constants import DISCHARGE_RECOMMENDATION_TEXT
    from medical_docx_editor_utils import iter_all_paragraphs, set_paragraph_text
    from medical_gender import adapt_role_owned_patient_phrase
    from medical_text_utils import normalize_match
    from universal_main_documents import document_role_matches_builtin_kind, semantic_role_for_document

    path = Path(output)
    try:
        is_discharge = document_role_matches_builtin_kind(document, "discharge")
        is_rvk = document_role_matches_builtin_kind(document, "rvk")
        is_joint_exam = semantic_role_for_document(document) == "joint_medical_exam"
        if not (is_discharge or is_rvk or is_joint_exam):
            return

        doc = Document(str(path))
        changed = False
        recommendation_found = False
        admission_mode = normalize_admission_mode(case.get("admission.mode"))

        for paragraph in list(iter_all_paragraphs(doc)):
            original = paragraph.text or ""
            normalized = normalize_match(original)
            if is_discharge and normalized.startswith(("рекомендовано", "рекомендации")):
                set_paragraph_text(paragraph, DISCHARGE_RECOMMENDATION_TEXT)
                recommendation_found = True
                changed = True
                continue
            if admission_mode and normalized.startswith("в 3 отделение кдп поступает"):
                set_paragraph_text(paragraph, admission_to_department_phrase(admission_mode))
                changed = True
                continue
            if is_discharge and normalized.startswith(("находился на лечении", "находилась на лечении")):
                gendered = adapt_role_owned_patient_phrase(original, case.get("patient.fio"))
                if gendered != original:
                    set_paragraph_text(paragraph, gendered)
                for run in paragraph.runs:
                    run.font.color.rgb = RGBColor(0, 0, 0)
                changed = True
                continue
            if is_rvk and normalized.startswith(("находился на обследовании", "находилась на обследовании")):
                gendered = adapt_role_owned_patient_phrase(original, case.get("patient.fio"))
                if gendered != original:
                    set_paragraph_text(paragraph, gendered)
                    changed = True

        if is_discharge and not recommendation_found:
            for paragraph in iter_all_paragraphs(doc):
                normalized = normalize_match(paragraph.text or "")
                if normalized.startswith(("зав. отд", "зав. отделением", "врач")):
                    paragraph.insert_paragraph_before(DISCHARGE_RECOMMENDATION_TEXT)
                    changed = True
                    break
            else:
                doc.add_paragraph(DISCHARGE_RECOMMENDATION_TEXT)
                changed = True

        if changed:
            doc.save(str(path))
    except Exception as exc:
        record_soft_exception("medical_renderer.role_owned_postprocessing", exc, detail=str(path))
        raise
