"""Role-owned medical wording applied after generic DOCX field filling.

The universal template engine owns placeholder mechanics. Medical phrases whose
meaning belongs to a specific document role live here so role rules cannot grow
inside the generic renderer.
"""

from __future__ import annotations

from pathlib import Path

from diagnostic_logging import record_soft_exception
from docx import Document
from docx.shared import RGBColor

from medical_admission_resolver import admission_to_department_phrase, normalize_admission_mode
from medical_constants import DISCHARGE_RECOMMENDATION_TEXT
from medical_docx_editor_utils import iter_all_paragraphs, set_paragraph_text
from medical_gender import adapt_role_owned_patient_phrase
from medical_text_utils import normalize_match
from universal_fields import PatientCase
from universal_main_documents import document_role_matches_builtin_kind, semantic_role_for_document
from universal_profiles import DocumentTemplateSpec


def apply_role_owned_medical_postprocessing(
    output: str | Path,
    case: PatientCase,
    document: DocumentTemplateSpec,
) -> None:
    """Enforce user-confirmed medical wording without polluting generic rendering."""
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
        record_soft_exception("medical_role_postprocessing.apply", exc, detail=str(path))
        raise
