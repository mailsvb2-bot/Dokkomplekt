"""Profile builder/orchestrator for universal medical document packs.

This module turns the lower-level scanner/template/generation primitives into a
commercial setup flow: choose a specialty preset, scan several source examples,
attach the doctor's templates, then return a concrete checklist of what is ready
and what still needs manual mapping.
"""

from __future__ import annotations

from diagnostic_logging import record_soft_exception
from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
from typing import Mapping, Sequence

from universal_fields import FieldDefinition, PatientCase, default_field_registry, normalize_field_id
from universal_generation import PackReadinessReport, analyze_pack_readiness, save_readiness_report
from universal_profiles import DocumentPack, DocumentTemplateSpec, default_document_pack, save_document_pack
from universal_scanner import DocumentScanResult, merge_scan_results, scan_docx, scan_many_docx
from universal_template_engine import (
    PackValidationResult,
    attach_template_to_pack,
    export_document_pack_zip,
    validate_document_pack,
)


@dataclass(frozen=True)
class SpecialtyDocumentPreset:
    """A planned document button for a specialty profile before a DOCX exists."""

    id: str
    label: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()
    category: str = "medical"
    description: str = ""

    def to_spec(self) -> DocumentTemplateSpec:
        return DocumentTemplateSpec(
            id=self.id,
            button_label=self.label,
            template=f"templates/{self.id}.docx",
            output_name="{{patient.fio}} " + self.label + ".docx",
            required_fields=tuple(dict.fromkeys(normalize_field_id(item) for item in self.required_fields)),
            optional_fields=tuple(dict.fromkeys(normalize_field_id(item) for item in self.optional_fields)),
            category=self.category,
            description=self.description or "Запланированный документ из пресета специальности. Добавьте DOCX-шаблон с placeholders, чтобы кнопка стала рабочей.",
        )


@dataclass(frozen=True)
class SpecialtyPreset:
    """Reusable starting point for a doctor specialty/department profile."""

    id: str
    label: str
    specialty: str
    documents: tuple[SpecialtyDocumentPreset, ...]
    custom_fields: tuple[FieldDefinition, ...] = ()
    notes: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["documents"] = [asdict(item) for item in self.documents]
        data["custom_fields"] = [item.to_dict() for item in self.custom_fields]
        return data




@dataclass(frozen=True)
class TemplateButtonRecognition:
    """One Word template recognized during 10-second doctor setup."""

    path: str
    label: str
    document_id: str
    role_id: str = "unknown"
    source: str = "fallback"
    confidence: float = 0.0

    def human_line(self) -> str:
        percent = int(round(max(0.0, min(1.0, self.confidence)) * 100))
        return f"{self.label} — {Path(self.path).name} ({percent}%)"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TemplateIngestionResult:
    """Result of batch-adding DOCX templates into a profile."""

    added_document_ids: tuple[str, ...]
    copied_templates: tuple[str, ...]
    skipped_templates: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return bool(self.added_document_ids) and not self.skipped_templates

    def human_report(self) -> str:
        lines = ["Подключение пользовательских шаблонов", f"Добавлено документов: {len(self.added_document_ids)}"]
        if self.added_document_ids:
            lines.append("")
            lines.append("Документы:")
            lines.extend("• " + item for item in self.added_document_ids)
        if self.copied_templates:
            lines.append("")
            lines.append("Скопированные шаблоны:")
            lines.extend("• " + Path(item).name for item in self.copied_templates)
        if self.skipped_templates:
            lines.append("")
            lines.append("Пропущено:")
            lines.extend("• " + item for item in self.skipped_templates)
        if self.warnings:
            lines.append("")
            lines.append("Предупреждения:")
            lines.extend("• " + item for item in self.warnings)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProfileBuildReport:
    """End-to-end result of building a doctor profile."""

    pack_id: str
    pack_name: str
    specialty: str
    source_documents: tuple[str, ...]
    template_documents: tuple[str, ...]
    detected_fields: tuple[str, ...]
    missing_core_fields: tuple[str, ...]
    ingestion: TemplateIngestionResult
    validation_ok: bool
    readiness_ready_count: int
    readiness_blocked_count: int
    warnings: tuple[str, ...] = ()

    def human_report(self) -> str:
        lines = [
            f"Мастер профиля: {self.pack_name}",
            f"Специальность: {self.specialty or 'не указана'}",
            f"Исходных документов изучено: {len(self.source_documents)}",
            f"DOCX-шаблонов подключено: {len(self.template_documents)}",
            f"Найдено смысловых полей: {len(self.detected_fields)}",
            f"Профиль проверен: {'OK' if self.validation_ok else 'есть замечания'}",
            f"Готовых кнопок: {self.readiness_ready_count}",
            f"Заблокированных кнопок: {self.readiness_blocked_count}",
        ]
        if self.detected_fields:
            lines.append("")
            lines.append("Найденные поля:")
            lines.extend("• " + item for item in self.detected_fields)
        if self.missing_core_fields:
            lines.append("")
            lines.append("Не найдены базовые поля, их нужно разметить вручную:")
            lines.extend("• " + item for item in self.missing_core_fields)
        if self.warnings:
            lines.append("")
            lines.append("Предупреждения:")
            lines.extend("• " + item for item in self.warnings)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProfileBuildResult:
    """Concrete build artifacts for a profile setup session."""

    pack: DocumentPack
    scan: DocumentScanResult | None
    ingestion: TemplateIngestionResult
    validation: PackValidationResult
    readiness: PackReadinessReport
    report: ProfileBuildReport
    saved_pack_path: str = ""
    readiness_report_path: str = ""

    @property
    def ok(self) -> bool:
        return self.validation.ok and self.readiness.ready_count > 0

    def human_report(self) -> str:
        return self.report.human_report()


def specialty_presets() -> tuple[SpecialtyPreset, ...]:
    """Return optional field presets only; never ship filled medical templates."""

    generic_common = ("patient.fio", "case.number", "diagnosis.main")
    common = ("patient.fio", "case.number", "admission.date", "diagnosis.main")
    discharge = (*common, "discharge.date", "treatment.result", "recommendations")
    therapy_vitals = ("vitals.blood_pressure", "vitals.pulse", "vitals.temperature")
    return (
        SpecialtyPreset(
            id="generic_base",
            label="Любая специальность — пустой медицинский конструктор",
            specialty="generic",
            documents=(
                SpecialtyDocumentPreset("generic_document", "Документ врача", generic_common, description="Нейтральная кнопка-заготовка: замените её своим DOCX-шаблоном и обязательными полями."),
            ),
            notes="Нейтральный режим: программа не привязана к одной специальности; врач сам задаёт названия документов и обязательные поля через свои шаблоны.",
        ),
        SpecialtyPreset(
            id="therapy_base",
            label="Терапия — базовый стационар",
            specialty="therapy",
            documents=(
                SpecialtyDocumentPreset("therapy_primary_exam", "Первичный осмотр терапевта", (*common, *therapy_vitals, "complaints", "anamnesis.disease")),
                SpecialtyDocumentPreset("therapy_daily_diary", "Терапевтический дневник", (*common, *therapy_vitals, "treatment.plan"), category="diaries"),
                SpecialtyDocumentPreset("therapy_discharge", "Выписной эпикриз терапевта", discharge),
                SpecialtyDocumentPreset("therapy_mse", "ВК / МСЭ терапевта", (*common, "discharge.date", "recommendations")),
            ),
            notes="Подходит для общей логики терапевтического отделения: жалобы, объективный статус, витальные показатели, лечение, рекомендации.",
        ),
        SpecialtyPreset(
            id="surgery_base",
            label="Хирургия — базовый стационар",
            specialty="surgery",
            documents=(
                SpecialtyDocumentPreset("surgery_primary_exam", "Первичный осмотр хирурга", (*common, "complaints", "status.objective")),
                SpecialtyDocumentPreset("operation_protocol", "Протокол операции", (*common, "procedure.name", "procedure.date", "procedure.anesthesia")),
                SpecialtyDocumentPreset("postoperative_diary", "Послеоперационный дневник", (*common, "procedure.date", "postoperative.status"), category="diaries"),
                SpecialtyDocumentPreset("surgery_discharge", "Выписной эпикриз хирурга", (*discharge, "procedure.name", "procedure.complications")),
                SpecialtyDocumentPreset("informed_consent", "Информированное согласие", ("patient.fio", "procedure.name", "consent.informed")),
            ),
            notes="Подходит для операций, анестезии, послеоперационных дневников и согласий.",
        ),
        SpecialtyPreset(
            id="neurology_base",
            label="Неврология — базовый стационар",
            specialty="neurology",
            documents=(
                SpecialtyDocumentPreset("neurology_primary_exam", "Первичный осмотр невролога", (*common, "complaints", "anamnesis.disease", "status.neurological")),
                SpecialtyDocumentPreset("neurology_diary", "Неврологический дневник", (*common, "status.neurological", "treatment.plan"), category="diaries"),
                SpecialtyDocumentPreset("neurology_discharge", "Выписной эпикриз невролога", (*discharge, "status.neurological")),
            ),
            custom_fields=(FieldDefinition("status.neurological", "Неврологический статус", "clinical", ("Неврологический статус", "Невростатус"), "block"),),
            notes="Добавляет пользовательское поле status.neurological как пример расширения под специальность.",
        ),
    )


def get_specialty_preset(preset_id: str) -> SpecialtyPreset:
    needle = _normalize_preset_id(preset_id)
    for preset in specialty_presets():
        if preset.id == needle or preset.specialty == needle:
            return preset
    available = ", ".join(preset.id for preset in specialty_presets())
    raise KeyError(f"Неизвестный пресет специальности: {preset_id}. Доступно: {available}")


def create_pack_from_preset(preset_id: str, *, pack_id: str | None = None, name: str | None = None) -> DocumentPack:
    """Create a profile with planned dynamic documents from a specialty preset."""

    preset = get_specialty_preset(preset_id)
    return DocumentPack(
        pack_id=pack_id or f"custom.{preset.id}",
        name=name or preset.label,
        specialty=preset.specialty,
        documents=tuple(document.to_spec() for document in preset.documents),
        custom_fields=preset.custom_fields,
        notes=preset.notes,
    )




def recognize_template_buttons(
    template_paths: Sequence[str | Path],
    *,
    preferred_language: str | None = "ru",
    ui_language: str | None = "ru",
    specialty: str = "",
) -> tuple[TemplateButtonRecognition, ...]:
    """Recognize user-visible button names from the top of several DOCX templates.

    This powers the fast onboarding flow: select a bunch of doctor's Word
    templates, show "Распознаны документы …", then create block-03 buttons in
    one confirmation.  It does not mutate the pack.
    """

    from personal_document_buttons import suggest_button_label_for_template

    results: list[TemplateButtonRecognition] = []
    seen_paths: set[Path] = set()
    for raw_path in template_paths:
        path = Path(raw_path).expanduser()
        try:
            resolved = path.resolve()
        except Exception as exc:
            record_soft_exception("universal_profile_builder.resolve", exc, detail=str(path))
            resolved = path.absolute()
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        suggestion = suggest_button_label_for_template(
            path,
            preferred_language=preferred_language,
            ui_language=ui_language,
            explicit_specialty=specialty,
        )
        if not suggestion.label:
            suggestion = suggest_button_label_for_template(
                path,
                preferred_language=preferred_language,
                ui_language=ui_language,
                explicit_specialty=specialty,
                fallback_label=path.stem,
            )
        results.append(
            TemplateButtonRecognition(
                path=str(path),
                label=suggestion.label,
                document_id=suggestion.document_id,
                role_id=suggestion.role_id,
                source=suggestion.source,
                confidence=suggestion.confidence,
            )
        )
    return tuple(results)


def ingest_templates_into_pack(
    pack: DocumentPack,
    template_paths: Sequence[str | Path],
    profile_dir: str | Path,
    *,
    category: str = "medical",
) -> TemplateIngestionResult:
    """Copy several user templates into the profile and attach document specs."""

    registry = pack.registry()
    added: list[str] = []
    copied: list[str] = []
    skipped: list[str] = []
    warnings: list[str] = []
    seen_paths: set[Path] = set()
    for raw_path in template_paths:
        try:
            path = Path(raw_path).expanduser()
            resolved = path.resolve()
            if resolved in seen_paths:
                warnings.append(f"Повторный шаблон пропущен: {path.name}")
                continue
            seen_paths.add(resolved)
            spec, copied_to = attach_template_to_pack(pack, path, profile_dir, category=category, registry=registry)
            added.append(spec.id)
            copied.append(str(copied_to))
        except Exception as exc:
            skipped.append(f"{Path(str(raw_path)).name}: {exc}")
    return TemplateIngestionResult(tuple(added), tuple(copied), tuple(skipped), tuple(warnings))


def build_profile_from_sources_and_templates(
    *,
    source_paths: Sequence[str | Path],
    template_paths: Sequence[str | Path],
    profile_dir: str | Path,
    preset_id: str = "generic_base",
    pack_id: str | None = None,
    name: str | None = None,
) -> ProfileBuildResult:
    """Run the full first setup pass for a doctor profile."""

    profile_root = Path(profile_dir).expanduser()
    profile_root.mkdir(parents=True, exist_ok=True)
    pack = create_pack_from_preset(preset_id, pack_id=pack_id, name=name)
    pack.workflow_principles = {**getattr(pack, "workflow_principles", {}), "profile_scope": "specialty_neutral_medical"}
    scan = scan_many_docx(source_paths, registry=pack.registry(), rules=pack.extraction_rules) if source_paths else None
    case = scan.patient_case() if scan else PatientCase()
    ingestion = ingest_templates_into_pack(pack, template_paths, profile_root)
    validation = validate_document_pack(pack, base_dir=profile_root)
    readiness = analyze_pack_readiness(pack, case, base_dir=profile_root)
    pack_path = save_document_pack(pack, profile_root / "pack.json")
    readiness_path = save_readiness_report(readiness, profile_root / "profile_readiness_report.txt")
    missing_core = scan.missing_field_ids(pack.registry()) if scan else tuple(field_id for field_id in pack.required_field_ids() if field_id in {"patient.fio", "case.number", "admission.date", "diagnosis.main"})
    warnings = list(ingestion.warnings)
    if ingestion.skipped_templates:
        warnings.append("Часть шаблонов не подключена — см. список пропущенных.")
    if not source_paths:
        warnings.append("Исходные документы не загружены: профиль создан только по шаблонам/пресету.")
    if readiness.ready_count == 0:
        warnings.append("Нет готовых custom-кнопок: нужны значения обязательных полей или DOCX-шаблоны.")
    report = ProfileBuildReport(
        pack_id=pack.pack_id,
        pack_name=pack.name,
        specialty=pack.specialty,
        source_documents=tuple(str(Path(item).expanduser()) for item in source_paths),
        template_documents=tuple(ingestion.copied_templates),
        detected_fields=tuple(sorted((scan.best_matches() if scan else {}).keys())),
        missing_core_fields=tuple(missing_core),
        ingestion=ingestion,
        validation_ok=validation.ok,
        readiness_ready_count=readiness.ready_count,
        readiness_blocked_count=readiness.blocked_count,
        warnings=tuple(dict.fromkeys(warnings)),
    )
    (profile_root / "profile_build_report.txt").write_text(report.human_report() + "\n", encoding="utf-8")
    return ProfileBuildResult(pack, scan, ingestion, validation, readiness, report, str(pack_path), str(readiness_path))


def profile_setup_checklist(pack: DocumentPack, *, base_dir: str | Path | None = None) -> str:
    """Return a practical support checklist for finishing a profile."""

    validation = validate_document_pack(pack, base_dir=base_dir)
    lines = [
        f"Профиль: {pack.name}",
        f"Документов в профиле: {len(pack.documents)}",
        f"Обязательных смысловых полей: {len(pack.required_field_ids())}",
        "",
        "Что нужно проверить перед продажей/передачей врачу:",
        "1. Все нужные кнопки есть в профиле.",
        "2. Каждый пользовательский DOCX содержит placeholders вида {{patient.fio}}.",
        "3. Разметчик находит ФИО, номер истории, дату поступления и диагноз на 3–5 примерах.",
        "4. Поля со средней/низкой уверенностью подтверждаются врачом.",
        "5. Профиль экспортируется в .medpack.zip и импортируется на чистом компьютере.",
        "6. Генерация custom DOCX проходит без пропущенных обязательных полей.",
    ]
    if validation.errors:
        lines.append("")
        lines.append("Ошибки профиля:")
        lines.extend("• " + item for item in validation.errors)
    if validation.warnings:
        lines.append("")
        lines.append("Предупреждения профиля:")
        lines.extend("• " + item for item in validation.warnings)
    return "\n".join(lines)


def export_profile_with_summary(pack: DocumentPack, target_zip: str | Path, *, profile_dir: str | Path) -> Path:
    """Export a medpack and write a nearby human-readable setup checklist."""

    exported = export_document_pack_zip(pack, target_zip, template_base_dir=profile_dir)
    checklist_path = Path(target_zip).expanduser().with_suffix(".checklist.txt")
    checklist_path.write_text(profile_setup_checklist(pack, base_dir=profile_dir) + "\n", encoding="utf-8")
    return exported


def _normalize_preset_id(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
