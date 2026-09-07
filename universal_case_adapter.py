"""Adapters between the old production ``PatientData`` and universal ``PatientCase``."""

from __future__ import annotations

import re
from typing import Mapping

from icd10_f_search import normalize_required_diagnosis_with_icd10
from medical_formatting import parse_date
from medical_models import PatientData
from universal_fields import PatientCase


def _first_text(*values: str) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _icd10_code_from_diagnosis(value: str) -> str:
    normalized = normalize_required_diagnosis_with_icd10(value)
    match = re.search(r"\b([A-Z][0-9]{2}(?:\.[0-9A-Z]+)?)\b", normalized)
    return match.group(1) if match else ""


def _labs_results_for_case(data: PatientData) -> str:
    if data.labs_without:
        return "Нет анализов"
    return data.labs_text or ""


def _age_at_admission(birth_value: str, admission_value: str) -> str:
    """Return completed years only when both semantic dates are trustworthy.

    ``PatientData.birth`` historically also received values from an ``Возраст``
    label.  Treating an arbitrary birth/age string as ``patient.age`` produced
    dangerous output such as ``Возраст: 12.03.1981``.  Age is therefore derived
    only from two parseable dates and is otherwise left empty for preflight.
    """

    birth = parse_date(str(birth_value or "").strip())
    admission = parse_date(str(admission_value or "").strip())
    if not birth or not admission:
        return ""
    try:
        birth_date = birth.date() if hasattr(birth, "date") else birth
        admission_date = admission.date() if hasattr(admission, "date") else admission
        years = admission_date.year - birth_date.year - (
            (admission_date.month, admission_date.day) < (birth_date.month, birth_date.day)
        )
    except Exception:
        return ""
    return str(years) if 0 <= years <= 130 else ""


def patient_data_to_case(data: PatientData, *, source_document: str = "") -> PatientCase:
    """Convert legacy PatientData, including popup requisites, into PatientCase.

    The adapter is deliberately conservative: it never manufactures semantically
    different discharge/recommendation/expert fields from merely non-empty nearby
    sections.  Profile scanning or doctor-confirmed completion owns those fields.
    """

    case = PatientCase()
    objective_status = _first_text(data.somatic_status, data.profile_status)
    vk_mse_work_position = _first_text(
        data.vk_mse_work_position,
        ", ".join(part for part in (data.vk_mse_work_org, data.vk_mse_position) if part),
    )
    pairs = {
        "patient.fio": data.output_fio or data.fio,
        "patient.birth_date": data.birth,
        "patient.age": _age_at_admission(data.birth, data.admission_date),
        "patient.address": data.registered,
        "patient.work": data.work_org,
        "patient.position": data.position,
        "case.number": data.case_number,
        "admission.date": data.admission_date,
        "discharge.date": data.discharge_date,
        "complaints": data.complaints,
        "anamnesis.life": data.life_anamnesis,
        "anamnesis.disease": data.disease_anamnesis,
        "expert.work_status": data.expert_work_status,
        "expert.work_org": data.expert_work_org,
        "expert.position": data.expert_position,
        "expert.sick_leave_needed": data.expert_sick_leave_needed,
        "expert.sick_leave_from": data.expert_sick_leave_from,
        "expert.sick_leave_number": data.expert_sick_leave_number,
        "status.objective": objective_status,
        "status.specialty": data.profile_status,
        "status.somatic": data.somatic_status,
        "diagnosis.main": data.diagnosis,
        "diagnosis.icd10": _icd10_code_from_diagnosis(data.diagnosis),
        "treatment.plan": data.treatment_plan,
        "epicrisis.text": data.epi_text,
        "additional.info": data.additional_info_text,
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
        "vk_mse.work_position": vk_mse_work_position,
        "sick_leave_vk.date": data.sick_leave_vk_date,
        "sick_leave_vk.protocol_number": data.sick_leave_vk_protocol_number,
        "sick_leave_vk.protocol_date": data.sick_leave_vk_protocol_date,
        "sick_leave_vk.commission_date": data.sick_leave_vk_commission_date,
        "sick_leave_vk.work": data.sick_leave_vk_work_org,
        "sick_leave_vk.position": data.sick_leave_vk_position,
        "sick_leave_vk.work_position": data.sick_leave_vk_work_position,
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
