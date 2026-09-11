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


def _explicit_age(value: str) -> str:
    """Return a doctor/source supplied age, but never a date/year of birth."""

    text = " ".join(str(value or "").strip().split())
    match = re.fullmatch(
        r"(?i)(\d{1,3})(?:\s*(?:лет|года?|год|years?|yrs?|y\.o\.|lat))?",
        text,
    )
    if not match:
        return ""
    years = int(match.group(1))
    return text if 0 <= years <= 130 else ""


def _age_at_admission(birth_or_age_value: str, admission_value: str) -> str:
    """Return an explicit age or derive completed years from two semantic dates.

    ``PatientData.birth`` is legacy storage and may contain either a birth value
    or an age extracted from a visible ``Возраст`` field. A birth date must never
    be copied verbatim into ``patient.age``.
    """

    explicit = _explicit_age(birth_or_age_value)
    if explicit:
        return explicit
    birth = parse_date(str(birth_or_age_value or "").strip())
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


def _birth_date_for_case(value: str) -> str:
    """Do not expose an explicit age as ``patient.birth_date``."""

    text = str(value or "").strip()
    return "" if _explicit_age(text) else text


def _is_negated_semantic_claim(value: str) -> bool:
    normalized = " ".join(str(value or "").casefold().replace("ё", "е").split())
    return any(
        marker in normalized
        for marker in (
            "не является",
            "не относится",
            "не считать",
            "не является результатом",
            "не является рекомендац",
        )
    )


def _discharge_summary(data: PatientData) -> str:
    """Use discharge-owned text, never unrelated somatic/profile status."""

    epi = str(data.epi_text or "").strip()
    if epi and not _is_negated_semantic_claim(epi):
        return epi
    additional = str(data.additional_info_text or "").strip()
    normalized = additional.casefold().replace("ё", "е")
    discharge_markers = (
        "выпис",
        "с улучш",
        "без улучш",
        "стабильн",
        "состояни",
        "wypis",
        "popraw",
        "stan przy wypisie",
    )
    if additional and not _is_negated_semantic_claim(additional) and any(marker in normalized for marker in discharge_markers):
        return additional
    return ""


def _recommendations(data: PatientData) -> str:
    text = str(data.additional_info_text or "").strip()
    normalized = text.casefold().replace("ё", "е")
    if not text or _is_negated_semantic_claim(text):
        return ""
    if any(marker in normalized for marker in ("рекоменд", "zalec")):
        return text
    return ""


def patient_data_to_case(data: PatientData, *, source_document: str = "") -> PatientCase:
    """Convert legacy PatientData, including popup requisites, into PatientCase.

    Semantically distinct fields are populated only from their owning source:
    treatment sections stay treatment plans; discharge/result fields come from
    epicrisis/discharge text; recommendations require recommendation semantics.
    """

    case = PatientCase()
    objective_status = data.somatic_status
    try:
        from medical_expert import build_expert_anamnesis
        expert_anamnesis = build_expert_anamnesis(data)
    except Exception:
        expert_anamnesis = ""
    discharge_summary = _discharge_summary(data)
    vk_mse_work_position = _first_text(
        data.vk_mse_work_position,
        ", ".join(part for part in (data.vk_mse_work_org, data.vk_mse_position) if part),
    )
    pairs = {
        # Medical identity is canonical and may never come from the filename/output hint.
        # ``output_fio`` exists only for filesystem naming when a full medical FIO is absent.
        "patient.fio": data.fio,
        "patient.birth_date": _birth_date_for_case(data.birth),
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
        "anamnesis.expert": expert_anamnesis,
        "expert.work_status": data.expert_work_status,
        "expert.work_org": data.expert_work_org,
        "expert.position": data.expert_position,
        "expert.sick_leave_needed": data.expert_sick_leave_needed,
        "expert.sick_leave_from": data.expert_sick_leave_from,
        "expert.sick_leave_number": data.expert_sick_leave_number,
        "status.objective": objective_status,
        # Keep the neutral specialty status as the universal canonical key.
        # Psychiatry templates may additionally address the same legacy PatientData
        # value through the narrower status.mental semantic field.
        "status.specialty": data.profile_status,
        "status.mental": data.profile_status,
        "status.somatic": data.somatic_status,
        "diagnosis.main": data.diagnosis,
        "diagnosis.icd10": _icd10_code_from_diagnosis(data.diagnosis),
        "examination.plan": data.examination_plan,
        "treatment.plan": data.treatment_plan,
        "epidemiology": data.epidemiology,
        "condition.discharge": discharge_summary,
        "treatment.result": discharge_summary,
        "epicrisis.text": data.epi_text,
        "additional.info": data.additional_info_text,
        "recommendations": _recommendations(data),
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


def _safe_overlay_values(values: Mapping[str, str]) -> dict[str, str]:
    safe = {str(key): str(value or "").strip() for key, value in values.items() if str(value or "").strip()}

    # The current UI has one generic "additional information" field. It must not
    # masquerade as Recommendations unless the value itself has recommendation
    # semantics. Source-parsed PatientData uses _recommendations() above.
    if safe.get("recommendations") and safe.get("recommendations") == safe.get("additional.info"):
        candidate = safe["recommendations"]
        if not _recommendations(PatientData(additional_info_text=candidate)):
            safe.pop("recommendations", None)

    work = safe.get("patient.work", "").casefold().replace("ё", "е")
    if work in {"не работает", "неработает", "нет", "безработный", "безработная"}:
        safe.pop("patient.position", None)
        safe.pop("expert.work_org", None)
        safe.pop("expert.position", None)
    return safe


def merge_case_values(case: PatientCase, values: Mapping[str, str], *, source_document: str = "manual_completion") -> PatientCase:
    safe_values = _safe_overlay_values(values)
    merged = PatientCase(values=dict(case.values))
    work = safe_values.get("patient.work", "").casefold().replace("ё", "е")
    if work in {"не работает", "неработает", "нет", "безработный", "безработная"}:
        for field_id in ("patient.position", "expert.work_org", "expert.position"):
            merged.values.pop(field_id, None)
    merged.update_from_pairs(safe_values, confidence=1.0, source_document=source_document)
    return merged


def merge_patient_cases(base: PatientCase, overlay: PatientCase) -> PatientCase:
    """Merge two PatientCase objects, keeping the higher-confidence value."""

    merged = PatientCase(values=dict(base.values))
    for field_id, value in overlay.values.items():
        old = merged.values.get(field_id)
        if old is None or value.confidence >= old.confidence:
            merged.values[field_id] = value
    return merged


def supplement_patient_case(base: PatientCase, supplement: PatientCase) -> PatientCase:
    """Fill only missing semantic fields without replacing canonical patient data.

    Profile/scanner extraction is allowed to enrich a case with specialty/custom
    fields, but it must never override patient identity, dates, diagnosis or any
    value already resolved from the selected primary document plus explicit
    doctor confirmations.
    """

    merged = PatientCase(values=dict(base.values))
    for field_id, value in supplement.values.items():
        old = merged.values.get(field_id)
        if old is None or not str(old.value or "").strip():
            merged.values[field_id] = value
    return merged
