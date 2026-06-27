"""Soft regulatory/document-role advisor for doctor templates.

The advisor compares a DOCX against broad medical document-role knowledge and
returns gentle suggestions.  It never mutates the template and never blocks
rendering; hard validation remains the job of the universal template engine.
"""

from __future__ import annotations

from diagnostic_logging import record_soft_exception
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from regulatory_advisory_policy import format_soft_advisory_prompt, make_completion_blocks
from regulatory_document_classifier import DocumentClassificationResult, classify_docx, text_from_docx
from regulatory_document_roles import DocumentRole, default_document_role_registry
from regulatory_section_registry import default_section_registry
from regulatory_specialty_overlays import default_specialty_overlay_registry
from universal_fields import FieldRegistry, default_field_registry
from universal_template_engine import extract_template_placeholders, validate_template


@dataclass(frozen=True)
class RegulatorySuggestion:
    field_id: str
    label: str
    reason: str
    section_id: str = ""
    severity: str = "soft"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RegulatoryTemplateAdvice:
    source_path: str
    classification: DocumentClassificationResult
    role_id: str
    role_label: str
    present_fields: tuple[str, ...]
    present_sections: tuple[str, ...]
    suggestions: tuple[RegulatorySuggestion, ...]
    warnings: tuple[str, ...] = ()

    @property
    def has_suggestions(self) -> bool:
        return bool(self.suggestions)

    @property
    def should_block_generation(self) -> bool:
        # Lock: regulatory advice is never a hard gate.
        return False

    def suggested_field_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.field_id for item in self.suggestions))

    def completion_blocks(self) -> tuple[str, ...]:
        return make_completion_blocks((item.label, item.field_id) for item in self.suggestions)

    def soft_prompt_text(self) -> str:
        items = [f"{item.label} — {item.field_id}" for item in self.suggestions]
        return format_soft_advisory_prompt(items, role_label=self.role_label or "документ")

    def human_report(self) -> str:
        lines = ["Мягкие подсказки по структуре документа", self.classification.human_report(), ""]
        lines.append("Статус: подсказки не блокируют генерацию. Врач может выбрать «Нет, не буду, делай как есть».")
        if self.present_fields:
            lines.append("\nУже есть смысловые поля/placeholders:")
            lines.extend("• " + item for item in self.present_fields)
        if self.present_sections:
            lines.append("\nПохожие разделы в документе:")
            lines.extend("• " + item for item in self.present_sections)
        if self.suggestions:
            lines.append("\nВозможно, здесь стоит указать ещё и:")
            for item in self.suggestions:
                lines.append(f"• {item.label}: {{{{{item.field_id}}}}} — {item.reason}")
            lines.append("\nБлоки для дополнения:")
            lines.extend("• " + item for item in self.completion_blocks())
        else:
            lines.append("\nДополнительных мягких подсказок по этой роли нет.")
        if self.warnings:
            lines.append("\nПредупреждения:")
            lines.extend("• " + item for item in self.warnings)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "source_path": self.source_path,
            "classification": self.classification.to_dict(),
            "role_id": self.role_id,
            "role_label": self.role_label,
            "present_fields": list(self.present_fields),
            "present_sections": list(self.present_sections),
            "suggestions": [item.to_dict() for item in self.suggestions],
            "warnings": list(self.warnings),
            "should_block_generation": self.should_block_generation,
        }


def advise_template(path: str | Path, *, registry: FieldRegistry | None = None, explicit_specialty: str = "") -> RegulatoryTemplateAdvice:
    """Advise a DOCX template using placeholders plus role/section detection."""

    registry = registry or default_field_registry()
    classification = classify_docx(path, explicit_specialty=explicit_specialty)
    placeholders = extract_template_placeholders(path)
    present_fields = tuple(dict.fromkeys(item.field_id for item in placeholders if not item.field_id.startswith("document.")))
    validation = validate_template(path, registry=registry)
    text = text_from_docx(path)
    return _build_advice(path, classification, present_fields, text, validation.warnings, registry=registry, explicit_specialty=explicit_specialty)


def advise_document(path: str | Path, *, registry: FieldRegistry | None = None, explicit_specialty: str = "") -> RegulatoryTemplateAdvice:
    """Advise a source DOCX without requiring placeholders."""

    registry = registry or default_field_registry()
    classification = classify_docx(path, explicit_specialty=explicit_specialty)
    text = text_from_docx(path)
    present_fields = _present_fields_from_text(text, registry)
    return _build_advice(path, classification, present_fields, text, (), registry=registry, explicit_specialty=explicit_specialty)


def save_advice_report(advice: RegulatoryTemplateAdvice, path: str | Path) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(advice.human_report() + "\n", encoding="utf-8")
    return target


def _build_advice(
    path: str | Path,
    classification: DocumentClassificationResult,
    present_fields: Sequence[str],
    text: str,
    warnings: Sequence[str],
    *,
    registry: FieldRegistry,
    explicit_specialty: str = "",
) -> RegulatoryTemplateAdvice:
    """Implement the _build_advice workflow with validation, UI state updates and diagnostics."""
    role = default_document_role_registry().get(classification.role_id) if classification.role_id != "unknown" else None
    section_registry = default_section_registry()
    present_sections = section_registry.detect_sections(text)
    overlay = default_specialty_overlay_registry().detect(text, explicit_specialty=explicit_specialty)
    suggested_field_ids: list[str] = []
    reasons: dict[str, str] = {}
    section_by_field: dict[str, str] = {}
    if role:
        for field_id in role.all_advisory_fields():
            suggested_field_ids.append(field_id)
            reasons.setdefault(field_id, f"часто встречается в роли «{role.label}»")
        for section_id in role.typical_sections:
            section = section_registry.get(section_id)
            if not section:
                continue
            for field_id in section.field_ids:
                suggested_field_ids.append(field_id)
                reasons.setdefault(field_id, f"часто относится к разделу «{section.label}»")
                section_by_field.setdefault(field_id, section.id)
    if overlay:
        for field_id in overlay.recommended_fields:
            suggested_field_ids.append(field_id)
            reasons.setdefault(field_id, f"мягкая подсказка для профиля «{overlay.label}»")
    present = {item for item in present_fields}
    suggestions: list[RegulatorySuggestion] = []
    for field_id in dict.fromkeys(suggested_field_ids):
        if field_id in present or field_id.startswith("document."):
            continue
        try:
            definition = registry.get(field_id)
            label = definition.label if definition else field_id
        except Exception as exc:
            record_soft_exception("regulatory_template_advisor.field_label", exc, detail=field_id)
            label = field_id
        suggestions.append(RegulatorySuggestion(field_id, label, reasons.get(field_id, "может быть полезно для этого типа документа"), section_by_field.get(field_id, "")))
    return RegulatoryTemplateAdvice(
        source_path=str(Path(path).expanduser()),
        classification=classification,
        role_id=role.id if role else "unknown",
        role_label=role.label if role else "неопределённый документ",
        present_fields=tuple(dict.fromkeys(present_fields)),
        present_sections=present_sections,
        suggestions=tuple(suggestions),
        warnings=tuple(warnings),
    )


def _present_fields_from_text(text: str, registry: FieldRegistry) -> tuple[str, ...]:
    haystack = " ".join(str(text or "").lower().replace("ё", "е").split())
    found: list[str] = []
    for definition in registry.definitions():
        if any(alias.lower().replace("ё", "е") in haystack for alias in definition.aliases):
            found.append(definition.id)
    return tuple(dict.fromkeys(found))
