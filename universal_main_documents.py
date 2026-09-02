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
    available: bool = True
    problem: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "document_id": self.document_id,
            "label": self.label,
            "template": self.template,
            "description": self.description,
            "role_id": self.role_id,
            "button_language": self.button_language,
            "available": self.available,
            "problem": self.problem,
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
    """Return every doctor-owned document, including damaged template links.

    A missing file is a repairable profile problem, not permission to erase a
    button from the doctor's UI.  Block 03 therefore keeps the stable document
    id/label visible and exposes availability explicitly.
    """

    base = Path(base_dir).expanduser() if base_dir else None
    result: list[MainScreenCustomDocument] = []
    seen: set[str] = set()
    for document in pack.documents:
        if is_builtin_document_id(document.id):
            continue
        kind = custom_kind(document.id)
        if kind in seen:
            continue
        seen.add(kind)
        template_text = str(document.template or "").replace("\\", "/").strip()
        candidate = Path(template_text).expanduser() if template_text else Path()
        if template_text and not candidate.is_absolute() and base is not None:
            candidate = base / candidate
        suffix_ok = bool(template_text.lower().endswith((".docx", ".docm")))
        location_ok = bool(template_text and (template_text.startswith("templates/") or Path(template_text).is_absolute()))
        exists = bool(template_text and suffix_ok and location_ok and (base is None or candidate.exists()))
        problem = ""
        if not template_text:
            problem = "В профиле не указан Word-шаблон."
        elif not suffix_ok:
            problem = f"Неподдерживаемый формат шаблона: {Path(template_text).suffix or 'без расширения'}."
        elif not location_ok:
            problem = "Ссылка на шаблон находится вне каталога templates профиля."
        elif base is not None and not candidate.exists():
            problem = f"Word-шаблон не найден: {template_text}"
        result.append(MainScreenCustomDocument(
            kind=kind,
            document_id=document.id,
            label=document.button_label or document.id,
            template=template_text,
            description=document.description,
            role_id=getattr(document, "role_id", ""),
            button_language=getattr(document, "button_language", "auto"),
            available=exists if base is not None else bool(template_text and suffix_ok and location_ok),
            problem=problem,
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
        "requires_fio": False,
        "requires_admission_date": False,
        "requires_case_number": False,
        "requires_diagnosis": False,
        "requires_treatment": False,
        "requires_discharge_date": False,
        "requires_labs": False,
    }


_FIO_FIELDS = {"patient.fio", "fio", "patient.name", "patient.full_name"}
_ADMISSION_FIELDS = {"admission.date", "admission_date", "hospitalization.date"}
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


def _field_set(document: object, *, required_only: bool = False) -> set[str]:
    """Canonical semantic fields independent of button label/path/description."""
    fields: set[str] = set()
    context = {
        "role_id": getattr(document, "role_id", "") or "",
        "category": getattr(document, "category", "") or "",
        "document_label": "",
    }
    attrs = ("required_fields",) if required_only else ("required_fields", "optional_fields")
    for attr in attrs:
        for item in tuple(getattr(document, attr, ()) or ()):  # type: ignore[arg-type]
            raw = str(item or "").strip()
            if not raw:
                continue
            try:
                fields.add(normalize_field_id_for_context(raw, **context))
            except ValueError:
                try:
                    fields.add(normalize_field_id(raw))
                except ValueError:
                    fields.add(raw.lower().replace("-", "_").replace(" ", "_"))
    return fields


def _has_any(fields: set[str], aliases: set[str]) -> bool:
    normalized_aliases: set[str] = set()
    for alias in aliases:
        try:
            normalized_aliases.add(normalize_field_id(alias))
        except ValueError:
            normalized_aliases.add(alias)
    return bool(fields & normalized_aliases)


_ROLE_REQUIREMENTS: dict[str, frozenset[str]] = {
    **{role: frozenset({"case"}) for role in _PRIMARY_ROLES},
    **{role: frozenset({"case", "diagnosis", "treatment", "discharge"}) for role in _DISCHARGE_ROLES},
    **{role: frozenset({"case", "diagnosis", "treatment", "discharge"}) for role in _RVK_ROLES},
    **{role: frozenset({"case", "diagnosis", "treatment"}) for role in _COMMISSION_ROLES},
    **{role: frozenset({"case", "diagnosis", "treatment"}) for role in _VK_MSE_ROLES},
    **{role: frozenset({"case", "diagnosis", "treatment"}) for role in _SICK_LEAVE_ROLES},
    "daily_diary": frozenset({"discharge"}),
}


def semantic_role_for_document(document: object) -> str:
    """Return persisted semantic role without guessing from human-facing text."""
    role = _canonical_role_id(getattr(document, "role_id", "") or "")
    if role and role != "unknown":
        return role
    # Exact historic ids may be migrated safely; substring/title/path guessing is
    # deliberately forbidden because rename/location must never change behavior.
    raw_id = _canonical_role_id(getattr(document, "id", "") or getattr(document, "document_id", "") or "")
    known = set(_ROLE_REQUIREMENTS) | _PRIMARY_ROLES | _DISCHARGE_ROLES | _COMMISSION_ROLES | _VK_MSE_ROLES | _SICK_LEAVE_ROLES | _RVK_ROLES
    return raw_id if raw_id in known else "unknown"


def document_role_matches_builtin_kind(document: object, kind: str) -> bool:
    role = semantic_role_for_document(document)
    mapping = {
        "discharge": _DISCHARGE_ROLES,
        "rvk": _RVK_ROLES,
        "commission": _COMMISSION_ROLES,
        "vk_mse": _VK_MSE_ROLES,
        "sick_leave_vk": _SICK_LEAVE_ROLES,
        "admission_doctor_referral": {"admission_doctor_exam", "hospitalization_referral"},
        "primary": {"primary_exam", "inpatient_record"},
    }
    return role in mapping.get(str(kind or "").strip(), set())


def custom_requirement_flags_for_documents(documents: object) -> dict[str, bool]:
    """Derive popup requirements only from persisted role + required fields.

    Human button labels, file paths and descriptions are presentation metadata.
    They are intentionally excluded so renaming/moving a template cannot mutate
    the clinical workflow.
    """

    flags = empty_custom_requirement_flags()
    for document in tuple(documents or ()):  # type: ignore[arg-type]
        fields = _field_set(document, required_only=True)
        role = semantic_role_for_document(document)
        category = _normalize_role_token(getattr(document, "category", "") or "")
        is_diary = category == "diaries" or role == "daily_diary"
        is_discharge = role in _DISCHARGE_ROLES
        is_rvk = role in _RVK_ROLES
        is_commission = role in _COMMISSION_ROLES
        is_vk_mse = role in _VK_MSE_ROLES
        is_sick_leave_vk = role in _SICK_LEAVE_ROLES
        requirements = _ROLE_REQUIREMENTS.get(role, frozenset())

        flags["diary"] = flags["diary"] or is_diary
        flags["discharge"] = flags["discharge"] or is_discharge
        flags["rvk"] = flags["rvk"] or is_rvk
        flags["commission"] = flags["commission"] or is_commission
        flags["vk_mse"] = flags["vk_mse"] or is_vk_mse
        flags["sick_leave_vk"] = flags["sick_leave_vk"] or is_sick_leave_vk
        flags["regular"] = flags["regular"] or not is_diary
        flags["requires_fio"] = flags["requires_fio"] or _has_any(fields, _FIO_FIELDS)
        flags["requires_admission_date"] = flags["requires_admission_date"] or _has_any(fields, _ADMISSION_FIELDS)
        flags["requires_case_number"] = flags["requires_case_number"] or "case" in requirements or _has_any(fields, _CASE_FIELDS)
        flags["requires_diagnosis"] = flags["requires_diagnosis"] or "diagnosis" in requirements or _has_any(fields, _DIAGNOSIS_FIELDS)
        flags["requires_treatment"] = flags["requires_treatment"] or "treatment" in requirements or _has_any(fields, _TREATMENT_FIELDS)
        flags["requires_discharge_date"] = flags["requires_discharge_date"] or "discharge" in requirements or _has_any(fields, _DISCHARGE_FIELDS)
        flags["requires_labs"] = flags["requires_labs"] or _has_any(fields, _LABS_FIELDS)
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
