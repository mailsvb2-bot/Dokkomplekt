"""Adapters between the old production ``PatientData`` and universal ``PatientCase``.

The universal renderer should not import or depend on the old DOCX renderer.
This small adapter keeps the boundary explicit: old parser output in,
semantic field container out.
"""

from __future__ import annotations

import re
from typing import Mapping

from icd10_f_search import normalize_required_diagnosis_with_icd10
from medical_models import PatientData
from universal_fields import PatientCase


def _icd10_code_from_diagnosis(value: str) -> str:
    normalized = normalize_required_diagnosis_with_icd10(value)
    match = re.search(r"\b([A-Z][0-9]{2}(?:\.[0-9A-Z]+)?)\b", normalized)
    return match.group(1) if match else ""


def _labs_results_for_case(data: PatientData) -> str:
    if data.labs_without:
        return "Нет анализов"
    return data.labs_text or ""


def patient_data_to_case(data: PatientData, *, source_document: str = "") -> PatientCase:
    """Convert legacy PatientData, including popup requisites, into PatientCase."""
    case = PatientCase()
    pairs = {
        "patient.fio": data.output_fio or data.fio,
        "patient.birth_date": data.birth,
        "patient.address": data.registered,
        "patient.work": data.work_org,
        "patient.position": data.position,
        "case.number": data.case_number,
        "admission.date": data.admission_date,
        "discharge.date": data.discharge_date,
        "complaints": data.complaints,
        "anamnesis.life": data.life_anamnesis,
        "anamnesis.disease": data.disease_anamnesis,
        "anamnesis.expert": data.expert_work_status or data.sick_leave,
        "expert.work_status": data.expert_work_status,
        "expert.work_org": data.expert_work_org,
        "expert.position": data.expert_position,
        "expert.sick_leave_needed": data.expert_sick_leave_needed,
        "expert.sick_leave_from": data.expert_sick_leave_from,
        "expert.sick_leave_number": data.expert_sick_leave_number,
        "status.mental": data.mental_status,
        "status.somatic": data.somatic_status,
        "diagnosis.main": data.diagnosis,
        "diagnosis.icd10": _icd10_code_from_diagnosis(data.diagnosis),
        "treatment.plan": data.treatment_plan,
        "labs.results": _labs_results_for_case(data),
        "labs.source": data.labs_source,
        "labs.date_policy": data.labs_date_policy,
        "rvk.act_number": data.rvk_act_number,
        "rvk.military_commissariat": data.rvk_military_commissariat,
        "rvk.work_position": data.rvk_work_position,
        "commission.date": data.commission_date,
        "commission.number": data.commission_number,
        "vk_mse.date": data.vk_date,
        "vk_mse.protocol_number": data.vk_protocol_number,
        "vk_mse.protocol_date": data.vk_protocol_date,
        "vk_mse.work": data.vk_mse_work_org,
        "vk_mse.position": data.vk_mse_position,
        "vk_mse.work_position": ", ".join(part for part in (data.vk_mse_work_org, data.vk_mse_position) if part),
        "sick_leave_vk.date": data.sick_leave_vk_date,
        "sick_leave_vk.protocol_number": data.sick_leave_vk_protocol_number,
        "sick_leave_vk.protocol_date": data.sick_leave_vk_protocol_date,
        "sick_leave_vk.commission_date": data.sick_leave_vk_commission_date,
        "sick_leave_vk.work": data.sick_leave_vk_work_org,
        "sick_leave_vk.position": data.sick_leave_vk_position,
        "sick_leave_vk.work_position": data.sick_leave_vk_work_position,
        "recommendations": "",
        "doctor.name": data.doctor,
        "head.name": data.head,
    }
    case.update_from_pairs(pairs, confidence=0.90, source_document=source_document)
    return case


def merge_case_values(case: PatientCase, values: Mapping[str, str], *, source_document: str = "manual_completion") -> PatientCase:
    merged = PatientCase(values=dict(case.values))
    merged.update_from_pairs(values, confidence=1.0, source_document=source_document)
    return merged


def merge_patient_cases(base: PatientCase, overlay: PatientCase) -> PatientCase:
    """Merge two PatientCase objects, keeping the higher-confidence value."""

    merged = PatientCase(values=dict(base.values))
    for field_id, value in overlay.values.items():
        old = merged.values.get(field_id)
        if old is None or value.confidence >= old.confidence:
            merged.values[field_id] = value
    return merged
