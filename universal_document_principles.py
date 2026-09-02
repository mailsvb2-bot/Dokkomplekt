from __future__ import annotations

from pathlib import Path
from typing import Sequence

from document_intelligence.analyzer import DocumentIntelligenceCore
from universal_fields import PatientCase

UNIVERSAL_DOCUMENT_PRINCIPLES_LOCK_VERSION = "v1.0"


def infer_document_principles(path: str | Path, **_kwargs):
    return DocumentIntelligenceCore().analyze_source(str(path))


def infer_document_principles_for_document(document: object, *, base_dir: str | Path | None = None):
    template = Path(str(getattr(document, "template", "") or "")).expanduser()
    if not template.is_absolute() and base_dir is not None:
        direct = Path(base_dir).expanduser() / template
        template = direct if direct.exists() else Path(base_dir).expanduser() / "templates" / template.name
    return infer_document_principles(template)


def missing_fields_from_principles(case: PatientCase, document: object, *, base_dir: str | Path | None = None):
    blueprint = infer_document_principles_for_document(document, base_dir=base_dir)
    result = []
    role_id = str(getattr(document, "role_id", "") or "")
    category = str(getattr(document, "category", "") or "")
    button_label = str(getattr(document, "button_label", "") or "")
    from dataclasses import replace
    from document_intelligence.form_fill import visible_field_id

    for field in blueprint.fields:
        field_id = str(getattr(field, "field_id", "") or "").strip()
        if getattr(field, "source", "") in {"visible_blank", "table_neighbor_blank"}:
            field_id = visible_field_id(
                str(getattr(field, "label", "") or ""),
                role_id=role_id,
                category=category,
                button_label=button_label,
            )
        if getattr(field, "required", True) and field_id and not case.get(field_id).strip():
            result.append(replace(field, field_id=field_id))
    return tuple(dict((field.field_id, field) for field in result).values())


def completion_inputs_from_inferred_fields(fields: Sequence[object], *, existing_case: PatientCase | None = None, reason_prefix: str = "Template requires field"):
    from regulatory_completion_blocks import CompletionInput

    existing_case = existing_case or PatientCase()
    result = {}
    for field in fields:
        field_id = str(getattr(field, "field_id", "") or "").strip()
        label = str(getattr(field, "label", "") or field_id).strip()
        if field_id:
            result.setdefault(field_id, CompletionInput(field_id, label, f"{reason_prefix}: {label}", "{{" + field_id + "}}", existing_case.get(field_id, "")))
    return tuple(result.values())


def assert_universal_document_principles_lock() -> None:
    if UNIVERSAL_DOCUMENT_PRINCIPLES_LOCK_VERSION != "v1.0":
        raise AssertionError("Universal document principles lock changed unexpectedly")
