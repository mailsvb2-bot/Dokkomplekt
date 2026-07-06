from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_DOCUMENT_SHAPES = ("blank_form", "table_form", "free_text", "letter", "mixed")


@dataclass(frozen=True)
class DocumentSource:
    path: str
    source_type: str = "template"
    user_label: str = ""
    profession_hint: str = "auto"


@dataclass(frozen=True)
class FieldSpec:
    field_id: str
    label: str
    value_kind: str = "text"
    required: bool = True
    source: str = "inferred"
    confidence: float = 0.75


@dataclass(frozen=True)
class SignatureSpec:
    label: str
    role: str = "custom"
    anchor: str = "document_end"
    frequency: str = "end_only"
    confidence: float = 0.70


@dataclass(frozen=True)
class SectionSpec:
    kind: str
    title: str = ""
    confidence: float = 0.60


@dataclass(frozen=True)
class PopupField:
    field_id: str
    label: str
    value_kind: str = "text"
    required: bool = True
    reason: str = "Шаблон документа требует уточнения"
    placeholder: str = ""


@dataclass(frozen=True)
class DocumentBlueprint:
    title: str
    domain: str
    shape: str
    source: str
    fields: tuple[FieldSpec, ...] = ()
    signatures: tuple[SignatureSpec, ...] = ()
    sections: tuple[SectionSpec, ...] = ()
    confidence: float = 0.75

    @property
    def required_field_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(field.field_id for field in self.fields if field.required))
