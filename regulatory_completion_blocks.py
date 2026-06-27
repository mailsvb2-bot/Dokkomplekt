"""Doctor-friendly completion inputs for soft regulatory suggestions.

This is deliberately separate from Tkinter.  The UI can render these entries in
a popup, tests can verify the behavior headlessly, and the regulatory advisor
remains non-blocking.
"""

from __future__ import annotations

from diagnostic_logging import record_soft_exception
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

from regulatory_advisory_policy import DECLINE_LABEL
from universal_fields import PatientCase, normalize_field_id

COMPLETION_POPUP_LOCK_VERSION = "v1.0"
COMPLETION_POPUP_TITLE = "Дополнить документ"
COMPLETION_VALUES_ARE_OPTIONAL = True


@dataclass(frozen=True)
class CompletionInput:
    field_id: str
    label: str
    reason: str = ""
    placeholder: str = ""
    initial_value: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def completion_inputs_from_advice(advice, *, existing_case: PatientCase | None = None) -> tuple[CompletionInput, ...]:
    existing_case = existing_case or PatientCase()
    inputs: list[CompletionInput] = []
    for suggestion in getattr(advice, "suggestions", ()):
        field_id = normalize_field_id(getattr(suggestion, "field_id", ""))
        value = existing_case.get(field_id, "")
        inputs.append(
            CompletionInput(
                field_id=field_id,
                label=str(getattr(suggestion, "label", field_id) or field_id),
                reason=str(getattr(suggestion, "reason", "") or ""),
                placeholder="{{" + field_id + "}}",
                initial_value=value,
            )
        )
    return tuple(dict.fromkeys(inputs))


def completion_values_from_raw(inputs: Sequence[CompletionInput], raw_values: Mapping[str, str]) -> dict[str, str]:
    allowed = {item.field_id for item in inputs}
    result: dict[str, str] = {}
    for field_id, value in raw_values.items():
        normalized = normalize_field_id(field_id)
        if normalized not in allowed:
            continue
        text = str(value or "").strip()
        if text:
            result[normalized] = text
    return result


def completion_inputs_for_missing_fields(
    missing_field_ids: Sequence[str],
    *,
    registry=None,
    existing_case: PatientCase | None = None,
    reason_prefix: str = "Для выбранного документа не хватает поля",
) -> tuple[CompletionInput, ...]:
    """Build optional completion inputs from missing semantic fields.

    This is used when a doctor selected a profile document whose template needs
    values not found in the source DOCX.  It is intentionally non-blocking: the
    caller may still generate as-is if the doctor declines.
    """

    from universal_fields import default_field_registry

    existing_case = existing_case or PatientCase()
    registry = registry or default_field_registry()
    inputs: list[CompletionInput] = []
    for raw_id in missing_field_ids:
        field_id = normalize_field_id(raw_id)
        try:
            definition = registry.require(field_id)
            label = definition.label
        except Exception as exc:
            record_soft_exception("regulatory_completion_blocks.field_label", exc, detail=field_id)
            label = field_id
        inputs.append(
            CompletionInput(
                field_id=field_id,
                label=label,
                reason=f"{reason_prefix}: {label}",
                placeholder="{{" + field_id + "}}",
                initial_value=existing_case.get(field_id, ""),
            )
        )
    # Deduplicate by field_id while preserving order.
    result: dict[str, CompletionInput] = {}
    for item in inputs:
        result.setdefault(item.field_id, item)
    return tuple(result.values())


def apply_completion_values(case: PatientCase, values: Mapping[str, str], *, source_document: str = "regulatory_completion_popup") -> PatientCase:
    merged = PatientCase(values=dict(case.values))
    merged.update_from_pairs(values, confidence=1.0, source_document=source_document)
    return merged


def save_completion_values(values: Mapping[str, str], path: str | Path) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = ["Дополнения врача", ""]
    if values:
        for field_id, value in sorted(values.items()):
            lines.append(f"{field_id}: {value}")
    else:
        lines.append(f"Врач выбрал: {DECLINE_LABEL} / без дополнительных значений.")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def assert_completion_popup_lock() -> None:
    if not COMPLETION_VALUES_ARE_OPTIONAL:
        raise AssertionError("Soft completion popup fields must stay optional")
    if "делай как есть" not in DECLINE_LABEL:
        raise AssertionError("Doctor decline label must remain gentle and explicit")
    if "мягк" in COMPLETION_POPUP_TITLE.lower():
        raise AssertionError("Completion popup title must stay doctor-respectful: Дополнить документ")
