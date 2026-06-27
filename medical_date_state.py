"""Single source of truth for patient-level dates entered through UI/popups.

The application has many small dialogs.  Dates must not become different values
just because a doctor opened another popup.  This module is UI-neutral: it
normalizes values, finds already accepted semantic dates and applies the
approved value back to legacy Tk variables, ``PatientData`` and the universal
patient case bridge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from medical_constants import DATE_FMT
from medical_formatting import parse_date


SEMANTIC_DATE_ALIASES: dict[str, str] = {
    "admission": "admission_date",
    "admission.date": "admission_date",
    "admission_date": "admission_date",
    "hospitalization.date": "admission_date",
    "hospitalization_date": "admission_date",
    "discharge": "discharge_date",
    "discharge.date": "discharge_date",
    "discharge_date": "discharge_date",
    "condition.discharge_date": "discharge_date",
    "condition.discharge": "discharge_date",
    "commission": "commission_date",
    "commission.date": "commission_date",
    "commission_date": "commission_date",
    "committee": "commission_date",
    "committee.date": "commission_date",
    "committee_date": "commission_date",
    "vk": "vk_date",
    "vk.date": "vk_date",
    "vk_date": "vk_date",
    "vk_mse.date": "vk_date",
    "vk_mse_date": "vk_date",
    "vk.protocol_date": "vk_protocol_date",
    "vk_protocol_date": "vk_protocol_date",
    "vk_mse.protocol_date": "vk_protocol_date",
    "vk_mse_protocol_date": "vk_protocol_date",
    "sick_leave_vk": "sick_leave_vk_date",
    "sick_leave_vk.date": "sick_leave_vk_date",
    "sick_leave_vk_date": "sick_leave_vk_date",
    "sick_leave_vk.protocol_date": "sick_leave_vk_protocol_date",
    "sick_leave_vk_protocol_date": "sick_leave_vk_protocol_date",
    "sick_leave_vk.commission_date": "sick_leave_vk_commission_date",
    "sick_leave_vk_commission_date": "sick_leave_vk_commission_date",
    "expert.sick_leave_from": "expert_sick_leave_from",
    "expert_sick_leave_from": "expert_sick_leave_from",
    "sick_leave_from": "expert_sick_leave_from",
    "labs.date": "labs_explicit_date",
    "labs_date": "labs_explicit_date",
    "labs_explicit_date": "labs_explicit_date",
    "analysis.date": "labs_explicit_date",
}

SEMANTIC_DATE_LABELS: dict[str, str] = {
    "admission_date": "Дата поступления",
    "discharge_date": "Дата выписки",
    "commission_date": "Дата совместного осмотра",
    "vk_date": "Дата ВК на МСЭ",
    "vk_protocol_date": "Дата протокола ВК на МСЭ",
    "sick_leave_vk_date": "Дата ВК больничного",
    "sick_leave_vk_protocol_date": "Дата протокола ВК больничного",
    "sick_leave_vk_commission_date": "Дата комиссии ВК больничного",
    "expert_sick_leave_from": "Дата начала больничного",
    "labs_explicit_date": "Дата анализов",
}

# Canonical date key -> (Tk StringVar attribute, PatientData attribute).
SEMANTIC_DATE_TARGETS: dict[str, tuple[str, str]] = {
    "admission_date": ("admission_date_var", "admission_date"),
    "discharge_date": ("discharge_date_var", "discharge_date"),
    "commission_date": ("commission_date_var", "commission_date"),
    "vk_date": ("vk_date_var", "vk_date"),
    "vk_protocol_date": ("vk_protocol_date_var", "vk_protocol_date"),
    "sick_leave_vk_date": ("sick_leave_vk_date_var", "sick_leave_vk_date"),
    "sick_leave_vk_protocol_date": ("sick_leave_vk_protocol_date_var", "sick_leave_vk_protocol_date"),
    "sick_leave_vk_commission_date": ("sick_leave_vk_commission_date_var", "sick_leave_vk_commission_date"),
    "expert_sick_leave_from": ("expert_sick_leave_from_var", "expert_sick_leave_from"),
    "labs_explicit_date": ("labs_explicit_date_var", ""),
}


@dataclass(frozen=True)
class DateConflict:
    key: str
    label: str
    existing: str
    candidate: str
    source_label: str = ""


def canonical_date_key(key: str) -> str:
    raw = str(key or "").strip()
    return SEMANTIC_DATE_ALIASES.get(raw, raw)


def semantic_date_label(key: str) -> str:
    return SEMANTIC_DATE_LABELS.get(canonical_date_key(key), canonical_date_key(key))


def normalize_date_value(value: str) -> str:
    parsed = parse_date(str(value or "").strip())
    return parsed.strftime(DATE_FMT) if parsed else ""


def _var_get(obj: Any, name: str) -> str:
    var = getattr(obj, name, None)
    if var is None:
        return ""
    try:
        return str(var.get() or "").strip()
    except (AttributeError, TypeError, RuntimeError, ValueError):
        return ""


def _var_set(obj: Any, name: str, value: str) -> None:
    var = getattr(obj, name, None)
    if var is None:
        return
    setter = getattr(obj, "_set_ui_var", None)
    try:
        if callable(setter):
            setter(var, value)
        else:
            var.set(value)
    except (AttributeError, TypeError, RuntimeError, ValueError):
        return


def _state(app: Any) -> dict[str, str]:
    state = getattr(app, "_semantic_date_state", None)
    if isinstance(state, dict):
        return state
    state = {}
    setattr(app, "_semantic_date_state", state)
    return state


def _data_value(app: Any, attr: str) -> str:
    data = getattr(app, "data", None)
    if data is None or not attr:
        return ""
    return str(getattr(data, attr, "") or "").strip()


def current_semantic_date(app: Any, key: str) -> str:
    canonical = canonical_date_key(key)
    normalized = normalize_date_value(_state(app).get(canonical, ""))
    if normalized:
        return normalized

    candidates: list[str] = []
    if canonical == "discharge_date":
        candidates.append(str(getattr(app, "_popup_discharge_date_override", "") or "").strip())

    var_name, data_attr = SEMANTIC_DATE_TARGETS.get(canonical, ("", ""))
    if var_name:
        candidates.append(_var_get(app, var_name))
    if data_attr:
        candidates.append(_data_value(app, data_attr))

    for candidate in candidates:
        normalized = normalize_date_value(candidate)
        if normalized:
            return normalized
    return ""


def date_conflict(app: Any, key: str, candidate: str, *, source_label: str = "") -> DateConflict | None:
    canonical = canonical_date_key(key)
    normalized = normalize_date_value(candidate)
    if not normalized:
        return None
    existing = current_semantic_date(app, canonical)
    if existing and existing != normalized:
        return DateConflict(canonical, semantic_date_label(canonical), existing, normalized, source_label)
    return None


def apply_semantic_date(app: Any, key: str, value: str) -> str:
    canonical = canonical_date_key(key)
    normalized = normalize_date_value(value)
    if not normalized:
        return ""
    _state(app)[canonical] = normalized
    data = getattr(app, "data", None)
    var_name, data_attr = SEMANTIC_DATE_TARGETS.get(canonical, ("", ""))
    if var_name:
        _var_set(app, var_name, normalized)
    if data is not None and data_attr:
        setattr(data, data_attr, normalized)
    if canonical == "discharge_date":
        setattr(app, "_popup_discharge_date_override", normalized)
        setattr(app, "_manual_discharge_date", True)
    elif canonical == "admission_date":
        setattr(app, "_manual_admission_date", True)
    return normalized


def clear_semantic_date(app: Any, key: str) -> None:
    canonical = canonical_date_key(key)
    _state(app).pop(canonical, None)
    data = getattr(app, "data", None)
    var_name, data_attr = SEMANTIC_DATE_TARGETS.get(canonical, ("", ""))
    if var_name:
        _var_set(app, var_name, "")
    if data is not None and data_attr:
        setattr(data, data_attr, "")
    if canonical == "discharge_date":
        setattr(app, "_popup_discharge_date_override", "")
        setattr(app, "_manual_discharge_date", False)
    elif canonical == "admission_date":
        setattr(app, "_manual_admission_date", False)


def clear_all_semantic_dates(app: Any) -> None:
    _state(app).clear()


def semantic_date_key_from_prompt(title: str, label: str) -> str:
    """Infer a semantic date key from a popup title+label pair.

    The dedicated dialog code passes explicit keys, but this fallback protects
    old/new generic popups from silently accepting conflicting dates.
    """
    title_l = " ".join(str(title or "").lower().replace("ё", "е").split())
    label_l = " ".join(str(label or "").lower().replace("ё", "е").split())
    if "дата" not in label_l and "числ" not in label_l:
        return ""
    if "анализ" in label_l or "лаборатор" in label_l:
        return "labs_explicit_date"
    if "выписк" in label_l:
        return "discharge_date"
    if "поступ" in label_l or "госпитал" in label_l:
        return "admission_date"
    if "с какого" in label_l or ("больнич" in label_l and "числ" in label_l):
        return "expert_sick_leave_from"
    if "вк больнич" in title_l or ("больнич" in title_l and "вк" in title_l):
        if "протокол" in label_l or label_l.startswith("от"):
            return "sick_leave_vk_protocol_date"
        if "проведения комиссии" in label_l or "комисси" in label_l:
            return "sick_leave_vk_commission_date"
        return "sick_leave_vk_date"
    if "вк на мсэ" in title_l or "мсэ" in title_l:
        if "протокол" in label_l or label_l.startswith("от"):
            return "vk_protocol_date"
        return "vk_date"
    if "совмест" in title_l or "совмест" in label_l or "комисси" in label_l:
        return "commission_date"
    return ""
