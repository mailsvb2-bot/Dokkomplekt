"""Main-screen bridge for dynamic medpack documents.

This module gives Tkinter block 03 a safe namespace for doctor-owned
profile documents:

``custom_profile:<document_id>``

The commercial product is a constructor: the doctor loads DOCX/DOCM templates,
the program reads the top title of each template, and block 03 shows buttons
created from those doctor-owned names.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Mapping

from diary_constants import DIARY_KIND
from medical_constants import DOCUMENT_ORDER
from universal_fields import normalize_field_id, normalize_field_id_for_context
from diagnostic_logging import record_soft_exception
from universal_profiles import DocumentPack, DocumentTemplateSpec

CUSTOM_DOCUMENT_KIND_PREFIX = "custom_profile:"
DYNAMIC_MEDPACK_BUTTON_LOCK_VERSION = "v1.1"
PROFILE_BUTTON_LABELS_ARE_PERSISTED = True


@dataclass(frozen=True)
class MainScreenCustomDocument:
    """A profile document that can be safely shown in block 03."""

    kind: str
    document_id: str
    label: str
    template: str
    description: str = ""
    role_id: str = ""
    button_language: str = "auto"

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "document_id": self.document_id,
            "label": self.label,
            "template": self.template,
            "description": self.description,
            "role_id": self.role_id,
            "button_language": self.button_language,
        }


def custom_kind(document_id: str) -> str:
    document_id = str(document_id or "").strip()
    if not document_id:
        raise ValueError("Пустой id custom-документа")
    return CUSTOM_DOCUMENT_KIND_PREFIX + document_id


def is_custom_kind(kind: str) -> bool:
    return str(kind or "").startswith(CUSTOM_DOCUMENT_KIND_PREFIX)


def custom_document_id_from_kind(kind: str) -> str:
    text = str(kind or "").strip()
    if not is_custom_kind(text):
        raise ValueError(f"Это не custom kind: {kind}")
    document_id = text[len(CUSTOM_DOCUMENT_KIND_PREFIX):].strip()
    if not document_id:
        raise ValueError("Пустой id custom-документа")
    return document_id


def is_builtin_document_id(document_id: str) -> bool:
    normalized = str(document_id or "").strip()
    return normalized in set(DOCUMENT_ORDER) or normalized == DIARY_KIND


def custom_documents_for_main_ui(pack: DocumentPack, *, base_dir: str | Path | None = None) -> tuple[MainScreenCustomDocument, ...]:
    """Return only doctor-added profile DOCX documents for block 03.

    Only doctor-added templates are shown.  Legacy fixed ids are filtered out
    so block 03 cannot silently resurrect an old bundled medical set.
    """

    base = Path(base_dir).expanduser() if base_dir else None
    result: list[MainScreenCustomDocument] = []
    seen: set[str] = set()
    for document in pack.documents:
        if is_builtin_document_id(document.id):
            continue
        template_text = str(document.template or "").replace("\\", "/").strip()
        if not template_text.lower().endswith((".docx", ".docm")):
            continue
        if not (template_text.startswith("templates/") or Path(template_text).is_absolute()):
            continue
        if base is not None:
            candidate = Path(template_text).expanduser()
            if not candidate.is_absolute():
                candidate = base / candidate
            if not candidate.exists():
                continue
        kind = custom_kind(document.id)
        if kind in seen:
            continue
        seen.add(kind)
        result.append(MainScreenCustomDocument(
            kind=kind,
            document_id=document.id,
            label=document.button_label or document.id,
            template=template_text,
            description=document.description,
            role_id=getattr(document, "role_id", ""),
            button_language=getattr(document, "button_language", "auto"),
        ))
    return tuple(result)


def selected_custom_document_ids(output_vars: Mapping[str, object]) -> tuple[str, ...]:
    """Extract selected profile document ids from Tk BooleanVar-like objects."""

    ids: list[str] = []
    for kind, var in output_vars.items():
        if not is_custom_kind(kind):
            continue
        try:
            selected = bool(var.get())  # type: ignore[attr-defined]
        except Exception as exc:
            record_soft_exception("universal_main_documents.selected_custom_document_ids", exc, detail=str(kind))
            selected = False
        if selected:
            ids.append(custom_document_id_from_kind(kind))
    return tuple(dict.fromkeys(ids))



def empty_custom_requirement_flags() -> dict[str, bool]:
    return {
        "diary": False,
        "regular": False,
        "discharge": False,
        "rvk": False,
        "commission": False,
        "vk_mse": False,
        "sick_leave_vk": False,
        "requires_case_number": False,
        "requires_diagnosis": False,
        "requires_treatment": False,
        "requires_discharge_date": False,
        "requires_labs": False,
    }


_CASE_FIELDS = {"case.number", "case_number", "history.number", "history.case", "patient.case_number"}
_DIAGNOSIS_FIELDS = {"diagnosis", "diagnosis.main", "diagnosis.icd10", "diagnosis.code", "diagnosis.text"}
_TREATMENT_FIELDS = {"treatment", "treatment.plan", "treatment.summary", "treatment.result", "treatment.assigned"}
_DISCHARGE_FIELDS = {"discharge.date", "discharge_date", "condition.discharge"}
_LABS_FIELDS = {"labs.results", "labs.block", "analysis.results", "analysis.date", "labs.date", "labs.types", "instrumental.results"}

# Behavioral compatibility with the early production implementation.  These are
# role aliases only: no bundled templates or specialty-specific text are
# restored.  Doctor-owned DOCX templates keep their own names and content, while
# the UI restores the correct popup chain for familiar document roles.
_LEGACY_ROLE_ALIASES = {
    "primary": "primary_exam",
    "primary_exam": "primary_exam",
    "primary.exam": "primary_exam",
    "admission_doctor": "admission_doctor_exam",
    "admission.doctor": "admission_doctor_exam",
    "admission_doctor_exam": "admission_doctor_exam",
    "admission.doctor.exam": "admission_doctor_exam",
    "admission_doctor_referral": "admission_doctor_exam",
    "admission.doctor.referral": "admission_doctor_exam",
    "hospitalization_referral": "hospitalization_referral",
    "hospitalization.referral": "hospitalization_referral",
    "inpatient_record": "inpatient_record",
    "inpatient.record": "inpatient_record",
    "discharge": "discharge_epicrisis",
    "discharge_epicrisis": "discharge_epicrisis",
    "discharge.epicrisis": "discharge_epicrisis",
    "transfer_epicrisis": "transfer_epicrisis",
    "transfer.epicrisis": "transfer_epicrisis",
    "commission": "joint_medical_exam",
    "medical_commission": "medical_commission",
    "medical.commission": "medical_commission",
    "joint_medical_exam": "joint_medical_exam",
    "joint.medical.exam": "joint_medical_exam",
    "vk_mse": "vk_mse",
    "vk.mse": "vk_mse",
    "mse_referral": "mse_referral",
    "mse.referral": "mse_referral",
    "sick_leave_vk": "sick_leave_vk",
    "sick.leave.vk": "sick_leave_vk",
    "temporary_disability_commission": "temporary_disability_commission",
    "temporary.disability.commission": "temporary_disability_commission",
    "rvk": "military_commissariat_act",
    "rvk_act": "rvk_act",
    "rvk.act": "rvk_act",
    "military_commissariat_act": "military_commissariat_act",
    "military.commissariat.act": "military_commissariat_act",
}
_PRIMARY_ROLES = {"primary_exam", "admission_doctor_exam", "hospitalization_referral", "inpatient_record"}
_DISCHARGE_ROLES = {"discharge_epicrisis", "transfer_epicrisis"}
_COMMISSION_ROLES = {"medical_commission", "joint_medical_exam"}
_VK_MSE_ROLES = {"mse_referral", "vk_mse"}
_SICK_LEAVE_ROLES = {"sick_leave_vk", "temporary_disability_commission"}
_RVK_ROLES = {"military_commissariat_act", "rvk_act"}


def _normalize_role_token(value: object) -> str:
    """Normalize profile role ids from UI labels, JSON exports and camelCase ids."""

    text = str(value or "").strip()
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[\s\-]+", "_", text)
    text = re.sub(r"[\/\\:]+", ".", text)
    text = re.sub(r"_+", "_", text)
    text = re.sub(r"\.+", ".", text)
    return text.strip("._")


def _canonical_role_id(value: object) -> str:
    normalized = _normalize_role_token(value)
    return _LEGACY_ROLE_ALIASES.get(normalized, normalized)


def _field_set(document: object) -> set[str]:
    fields: set[str] = set()
    context = {
        "role_id": getattr(document, "role_id", "") or "",
        "category": getattr(document, "category", "") or "",
        "document_label": getattr(document, "button_label", "") or "",
    }
    for attr in ("required_fields", "optional_fields"):
        for item in tuple(getattr(document, attr, ()) or ()):  # type: ignore[arg-type]
            raw = str(item or "").strip()
            if not raw:
                continue
            try:
                fields.add(normalize_field_id_for_context(raw, **context))
            except ValueError:
                # Keep malformed doctor-owned ids visible to heuristics instead of
                # crashing the main screen; release gates still validate packs.
                fields.add(raw.lower().replace("-", "_").replace(" ", "_"))
    return fields


def _signature_for_document(document: object) -> str:
    parts = [
        getattr(document, "id", ""),
        getattr(document, "document_id", ""),
        getattr(document, "role_id", ""),
        getattr(document, "category", ""),
        getattr(document, "button_label", ""),
        getattr(document, "template", ""),
        getattr(document, "description", ""),
        " ".join(_field_set(document)),
    ]
    return " ".join(str(part or "") for part in parts).lower().replace("\\", "/").replace("ё", "е")


def _has_any(fields: set[str], aliases: set[str]) -> bool:
    return bool(fields & aliases)


def custom_requirement_flags_for_documents(documents: object) -> dict[str, bool]:
    """Infer popup requirements for doctor-owned block-03 documents.

    The contract is data-driven: role_id/category/button label/template path and
    semantic placeholders all participate.  A doctor may rename a button in the
    confirmation table, but the saved role/placeholders still restore the right
    popup chain.
    """

    flags = empty_custom_requirement_flags()
    for document in tuple(documents or ()):  # type: ignore[arg-type]
        fields = _field_set(document)
        signature = _signature_for_document(document)
        raw_role = getattr(document, "role_id", "") or ""
        raw_id = getattr(document, "id", "") or getattr(document, "document_id", "") or ""
        role = _canonical_role_id(raw_role) or _canonical_role_id(raw_id)
        if not role:
            role = _canonical_role_id(raw_id)
        category = _normalize_role_token(getattr(document, "category", "") or "")

        is_diary = category == "diaries" or role == "daily_diary" or any(token in signature for token in ("дневник", "дневники", "diary", "daily_diary"))
        is_primary = role in _PRIMARY_ROLES or any(token in signature for token in (
            "первичный осмотр", "первичный", "осмотр при поступлении",
            "осмотр врача приемного покоя", "осмотр врача приёмного покоя",
            "приемный покой", "приёмный покой", "admission_doctor",
        ))
        is_discharge = role in _DISCHARGE_ROLES or any(token in signature for token in (
            "выписной эпикриз", "выписка", "выпис", "эпикриз", "epicrisis", "discharge",
        ))
        is_rvk = role in _RVK_ROLES or any(token in signature for token in (
            "акт для рвк", "акт рвк", "рвк", "военком", "военно", "военный комиссариат",
            "military_commissariat", "military commissariat",
        ))
        is_commission = role in _COMMISSION_ROLES or any(token in signature for token in (
            "совместный осмотр", "комиссионный осмотр", "врачебная комиссия", "медицинская комиссия",
            "лкк", "комиссион",
        )) or ("врачебн" in signature and "комисс" in signature)
        is_vk_mse = role in _VK_MSE_ROLES or any(token in signature for token in (
            "вк на мсэ", "на мсэ", "мсэ", "мсек", "медико-социаль", "mse",
        ))
        is_sick_leave_vk = role in _SICK_LEAVE_ROLES or (
            ("больнич" in signature or "нетрудоспособ" in signature or "sick_leave" in signature)
            and ("вк" in signature or "комисс" in signature or "протокол" in signature)
        )
        requires_labs = _has_any(fields, _LABS_FIELDS) or any(token in signature for token in ("анализ", "лаборатор", "оак", "оам", "labs", "analysis.results"))

        flags["diary"] = flags["diary"] or is_diary
        flags["discharge"] = flags["discharge"] or is_discharge
        flags["rvk"] = flags["rvk"] or is_rvk
        flags["commission"] = flags["commission"] or is_commission
        flags["vk_mse"] = flags["vk_mse"] or is_vk_mse
        flags["sick_leave_vk"] = flags["sick_leave_vk"] or is_sick_leave_vk
        flags["regular"] = flags["regular"] or not is_diary
        flags["requires_case_number"] = flags["requires_case_number"] or (not is_diary) or _has_any(fields, _CASE_FIELDS)
        flags["requires_diagnosis"] = flags["requires_diagnosis"] or _has_any(fields, _DIAGNOSIS_FIELDS) or is_discharge or is_rvk or is_commission or is_vk_mse or is_sick_leave_vk
        flags["requires_treatment"] = flags["requires_treatment"] or _has_any(fields, _TREATMENT_FIELDS) or is_discharge or is_rvk or is_commission or is_vk_mse or is_sick_leave_vk
        flags["requires_discharge_date"] = flags["requires_discharge_date"] or _has_any(fields, _DISCHARGE_FIELDS) or is_diary or is_discharge or is_rvk
        flags["requires_labs"] = flags["requires_labs"] or requires_labs
    return flags

def assert_dynamic_medpack_button_lock() -> None:
    """Release-gate lock: doctor-owned buttons must stay in their own namespace."""

    for kind in DOCUMENT_ORDER:
        if is_custom_kind(kind):
            raise AssertionError("Legacy DOCUMENT_ORDER must not contain custom_profile namespace")
    if is_custom_kind(DIARY_KIND):
        raise AssertionError("DIARY_KIND must stay outside custom_profile namespace")
    if not PROFILE_BUTTON_LABELS_ARE_PERSISTED:
        raise AssertionError("Profile button labels must be persisted in medpack data")
