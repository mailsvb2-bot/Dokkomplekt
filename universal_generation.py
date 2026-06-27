"""Universal document-pack generation and readiness layer.

This module is the bridge between the profile/configuration world and the
future dynamic block-03 UI.  It never touches the old hard-coded production
flow directly; instead it answers three safe questions:

* which buttons should a configurable DocumentPack show?
* which required fields are already available in the current PatientCase?
* which custom DOCX templates can be rendered right now?

The implementation is deterministic, local-only and intentionally strict for
required medical fields.  It is suitable for a setup wizard, support QA and a
future fully dynamic document checklist.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from medical_formatting import redact_technical_text, technical_ref
from universal_fields import PatientCase, normalize_field_id
from universal_profiles import DocumentPack, DocumentTemplateSpec
from universal_template_engine import RenderResult, build_render_context, missing_required_fields, render_output_name, render_template_to_docx


@dataclass(frozen=True)
class DynamicDocumentButton:
    """UI-ready representation of one dynamic document button."""

    document_id: str
    label: str
    category: str
    ready: bool
    template_exists: bool
    missing_fields: tuple[str, ...] = ()
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FieldCoverageItem:
    """Coverage of one semantic field across the current case and pack."""

    field_id: str
    label: str
    required_by: tuple[str, ...]
    value: str = ""
    confidence: float = 0.0

    @property
    def present(self) -> bool:
        return bool(self.value.strip())

    def to_dict(self) -> dict:
        data = asdict(self)
        data["present"] = self.present
        return data


@dataclass(frozen=True)
class PackReadinessReport:
    """Can this profile generate documents from this patient case?"""

    pack_id: str
    ready_document_ids: tuple[str, ...]
    blocked_document_ids: tuple[str, ...]
    buttons: tuple[DynamicDocumentButton, ...]
    field_coverage: tuple[FieldCoverageItem, ...]
    warnings: tuple[str, ...] = ()

    @property
    def ready_count(self) -> int:
        return len(self.ready_document_ids)

    @property
    def blocked_count(self) -> int:
        return len(self.blocked_document_ids)

    def human_report(self) -> str:
        lines = [
            f"Готовность профиля: {self.pack_id}",
            f"Готово документов: {self.ready_count}",
            f"Заблокировано документов: {self.blocked_count}",
        ]
        if self.warnings:
            lines.append("")
            lines.append("Предупреждения:")
            lines.extend("• " + warning for warning in self.warnings)
        if self.buttons:
            lines.append("")
            lines.append("Кнопки документов:")
            for button in self.buttons:
                state = "готов" if button.ready else "нужны поля: " + ", ".join(button.missing_fields)
                template = "шаблон найден" if button.template_exists else "шаблон не найден/локальный"
                lines.append(f"• {button.label}: {state}; {template}")
        if self.field_coverage:
            lines.append("")
            lines.append("Покрытие обязательных полей:")
            for item in self.field_coverage:
                state = "OK" if item.present else "нет значения"
                confidence = f", {int(round(item.confidence * 100))}%" if item.confidence else ""
                lines.append(f"• {item.label} ({item.field_id}): {state}{confidence}; нужно для: {', '.join(item.required_by)}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "pack_id": self.pack_id,
            "ready_document_ids": list(self.ready_document_ids),
            "blocked_document_ids": list(self.blocked_document_ids),
            "buttons": [button.to_dict() for button in self.buttons],
            "field_coverage": [item.to_dict() for item in self.field_coverage],
            "warnings": list(self.warnings),
            "ready_count": self.ready_count,
            "blocked_count": self.blocked_count,
        }


@dataclass(frozen=True)
class PackGenerationResult:
    """Result of rendering several custom documents from a pack."""

    created_files: tuple[str, ...]
    render_results: tuple[RenderResult, ...]
    skipped_documents: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.skipped_documents and all(result.ok for result in self.render_results)

    def human_report(self) -> str:
        lines = ["Генерация custom-документов", f"Создано файлов: {len(self.created_files)}"]
        if self.created_files:
            lines.append("")
            lines.append("Файлы:")
            lines.extend("• " + str(path) for path in self.created_files)
        if self.skipped_documents:
            lines.append("")
            lines.append("Пропущено:")
            lines.extend("• " + item for item in self.skipped_documents)
        if self.warnings:
            lines.append("")
            lines.append("Предупреждения:")
            lines.extend("• " + warning for warning in self.warnings)
        return "\n".join(lines)

    def technical_report(self) -> str:
        lines = ["Генерация custom-документов — технический обезличенный отчёт", f"Создано файлов: {len(self.created_files)}"]
        if self.created_files:
            lines.append("Пакет файлов: " + technical_ref(*self.created_files))
        if self.skipped_documents:
            lines.append("")
            lines.append("Пропущено:")
            lines.extend("• " + redact_technical_text(item) for item in self.skipped_documents)
        if self.warnings:
            lines.append("")
            lines.append("Предупреждения:")
            lines.extend("• " + redact_technical_text(warning) for warning in self.warnings)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "created_files": list(self.created_files),
            "render_results": [result.to_dict() for result in self.render_results],
            "skipped_documents": list(self.skipped_documents),
            "warnings": list(self.warnings),
        }


def document_buttons_for_pack(pack: DocumentPack, *, case: PatientCase | None = None, base_dir: str | Path | None = None) -> tuple[DynamicDocumentButton, ...]:
    """Return dynamic block-03 button descriptors for a pack."""

    case = case or PatientCase()
    buttons: list[DynamicDocumentButton] = []
    for document in pack.documents:
        missing = missing_required_fields(case, document)
        template_exists = _resolve_template_path(document, base_dir).exists()
        buttons.append(
            DynamicDocumentButton(
                document_id=document.id,
                label=document.button_label,
                category=document.category,
                ready=not missing and template_exists,
                template_exists=template_exists,
                missing_fields=missing,
                description=document.description,
            )
        )
    return tuple(buttons)


def analyze_pack_readiness(pack: DocumentPack, case: PatientCase, *, base_dir: str | Path | None = None) -> PackReadinessReport:
    """Build a doctor/support friendly readiness report for one case."""

    registry = pack.registry()
    buttons = document_buttons_for_pack(pack, case=case, base_dir=base_dir)
    ready_ids = tuple(button.document_id for button in buttons if button.ready)
    blocked_ids = tuple(button.document_id for button in buttons if not button.ready)
    required_by_field: dict[str, list[str]] = {}
    for document in pack.documents:
        for field_id in document.required_fields:
            normalized = normalize_field_id(field_id)
            required_by_field.setdefault(normalized, []).append(document.button_label)
    coverage: list[FieldCoverageItem] = []
    for field_id in sorted(required_by_field):
        value = case.values.get(field_id)
        try:
            label = registry.require(field_id).label
        except KeyError:
            label = field_id
        coverage.append(
            FieldCoverageItem(
                field_id=field_id,
                label=label,
                required_by=tuple(dict.fromkeys(required_by_field[field_id])),
                value=value.value if value else "",
                confidence=value.confidence if value else 0.0,
            )
        )
    warnings = []
    if not pack.documents:
        warnings.append("В профиле нет документов.")
    if buttons and not any(button.template_exists for button in buttons):
        warnings.append(
            "Для пользовательских документов рядом с профилем не найдено ни одного DOCX/DOCM-шаблона. "
            "Production-сценарий не подставляет встроенные медицинские шаблоны: загрузите шаблоны врача в конструкторе."
        )
    return PackReadinessReport(pack.pack_id, ready_ids, blocked_ids, buttons, tuple(coverage), tuple(warnings))


def render_documents_from_pack(
    *,
    pack: DocumentPack,
    case: PatientCase,
    document_ids: Sequence[str],
    output_dir: str | Path,
    base_dir: str | Path | None = None,
    strict: bool = True,
    output_language: str = "auto",
    spellcheck_enabled: bool = True,
) -> PackGenerationResult:
    """Render selected custom DOCX documents from a DocumentPack."""

    output_root = Path(output_dir).expanduser()
    if output_root.exists() and not output_root.is_dir():
        raise ValueError(f"Папка результата указывает на файл, а не на папку: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    selected = {str(item).strip() for item in document_ids if str(item).strip()}
    known_ids = {document.id for document in pack.documents}
    created: list[str] = []
    renders: list[RenderResult] = []
    skipped: list[str] = []
    warnings: list[str] = []
    reserved_output_names: dict[str, int] = {}
    reserved_output_paths: set[str] = set()
    for unknown_id in sorted(selected - known_ids):
        skipped.append(f"Неизвестный документ профиля: {unknown_id}")
    for document in pack.documents:
        if selected and document.id not in selected:
            continue
        template_path = _resolve_template_path(document, base_dir)
        if not template_path.exists():
            skipped.append(f"{document.button_label}: шаблон не найден ({document.template})")
            continue
        missing = missing_required_fields(case, document)
        if strict and missing:
            skipped.append(f"{document.button_label}: не заполнены поля {', '.join(missing)}")
            continue
        rendered_name = render_output_name(document, case, output_language=output_language, spellcheck_enabled=spellcheck_enabled)
        out_path = _available_batch_path(output_root / rendered_name, reserved_output_names, reserved_output_paths)
        result = render_template_to_docx(
            template_path=template_path,
            output_path=out_path,
            case=case,
            document=document,
            strict=strict,
            output_language=output_language,
            spellcheck_enabled=spellcheck_enabled,
        )
        renders.append(result)
        created.append(result.output_path)
        if result.missing_fields:
            warnings.append(f"{document.button_label}: placeholders без значения: {', '.join(result.missing_fields)}")
    return PackGenerationResult(tuple(created), tuple(renders), tuple(skipped), tuple(dict.fromkeys(warnings)))


def save_readiness_report(report: PackReadinessReport, path: str | Path) -> Path:
    target = _available_path(Path(path).expanduser())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report.human_report() + "\n", encoding="utf-8")
    return target


def save_generation_report(result: PackGenerationResult, path: str | Path) -> Path:
    target = _available_path(Path(path).expanduser())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(result.technical_report() + "\n", encoding="utf-8")
    return target


def _resolve_template_path(document: DocumentTemplateSpec, base_dir: str | Path | None) -> Path:
    template = Path(document.template).expanduser()
    if template.is_absolute():
        return template
    if base_dir:
        base = Path(base_dir).expanduser()
        direct = base / template
        if direct.exists():
            return direct
        in_templates = base / "templates" / template.name
        if in_templates.exists():
            return in_templates
        return direct
    return template


def _available_path(path: Path) -> Path:
    return _available_batch_path(path, {}, set())


def _available_batch_path(path: Path, reserved_names: dict[str, int], reserved_paths: set[str]) -> Path:
    """Return a free output path without O(N²) disk probing in batch renders.

    Earlier batch generation called ``_available_path`` for every document and
    linearly probed existing files up to ``(999)``.  A stress pack with many
    documents sharing the same output name became extremely slow and could fail
    at the 1000th duplicate.  The batch allocator keeps per-directory/name
    counters in memory, probes only the next candidate, and has no artificial
    999-file ceiling.
    """

    parent = path.parent
    stem = path.stem
    suffix = path.suffix
    key = str(parent.resolve()) + "|" + path.name.casefold()
    next_index = reserved_names.get(key, 1)
    while True:
        candidate = path if next_index <= 1 else parent / f"{stem} ({next_index}){suffix}"
        candidate_key = str(candidate.resolve()).casefold()
        reserved_names[key] = next_index + 1
        if candidate_key not in reserved_paths and not candidate.exists():
            reserved_paths.add(candidate_key)
            return candidate
        next_index = reserved_names[key]
