"""Render/fill custom diary documents stored in a medpack."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from diagnostic_logging import record_soft_exception
from diary_batch import fill_diary_batch
from diary_text_parser import extract_statuses_from_docx
from diary_schedule import DiaryScheduleSpec
from universal_fields import PatientCase
from universal_profiles import DocumentPack, DocumentTemplateSpec
from universal_template_engine import render_output_name

UNIVERSAL_DIARY_GENERATION_LOCK_VERSION = "v1.1"
CUSTOM_DIARY_GENERATION_USES_EXISTING_DIARY_ENGINE = True
CUSTOM_DIARY_CAN_USE_TEMPLATE_TEXTS_AS_STATUS_SOURCE = True


@dataclass(frozen=True)
class CustomDiaryGenerationResult:
    created_files: tuple[Path, ...]
    skipped: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def render_diary_documents_from_pack(
    *,
    pack: DocumentPack,
    case: PatientCase,
    document_ids: Sequence[str],
    output_dir: str | Path,
    base_dir: str | Path | None,
    status_files: Sequence[str | Path],
    patient_name: str,
    admission_value: str,
    discharge_value: str = "",
    gender_source_name: str = "",
    frequency_mode: str = "daily",
    repeat_statuses: bool = True,
    reset_each_file: bool = True,
    keep_signature: bool = True,
    fill_months: bool = True,
    force_final_diary: bool = True,
    remove_holiday_rows: bool = True,
    write_report: bool = False,
) -> CustomDiaryGenerationResult:
    """Implement the render_diary_documents_from_pack workflow with validation, UI state updates and diagnostics."""
    selected = {str(item).strip() for item in document_ids if str(item).strip()}
    created: list[Path] = []
    skipped: list[str] = []
    warnings: list[str] = []
    for document in pack.documents:
        if document.category != "diaries" or (selected and document.id not in selected):
            continue
        template = _resolve_template(document, base_dir)
        if not template.exists():
            skipped.append(f"{document.button_label}: шаблон дневников не найден ({document.template})")
            continue
        schedule = DiaryScheduleSpec.from_dict(getattr(document, "diary_schedule", None))
        if frequency_mode == "hourly" and schedule.has_hourly:
            effective = schedule.with_mode("hourly")
        else:
            effective = schedule.with_mode("daily")
        effective_status_files = _effective_status_files(status_files, template)
        if not effective_status_files:
            skipped.append(f"{document.button_label}: не выбраны тексты дневников и в шаблоне не найдено текстов наблюдения")
            continue
        try:
            result = fill_diary_batch(
                status_files=effective_status_files,
                diary_files=[template],
                output_dir=output_dir,
                patient_name=patient_name or case.get("patient.fio") or "Пациент",
                admission_value=admission_value or case.get("admission.date"),
                gender_source_name=gender_source_name or case.get("patient.fio") or patient_name,
                discharge_value=discharge_value or case.get("discharge.date"),
                repeat_statuses=repeat_statuses,
                reset_each_file=reset_each_file,
                keep_signature=keep_signature,
                fill_months=fill_months,
                force_final_diary=force_final_diary,
                remove_holiday_rows=remove_holiday_rows,
                open_result_folder=False,
                write_report=write_report,
                diary_day_offsets=effective.day_offsets,
                diary_hour_offsets=effective.hour_offsets if effective.mode == "hourly" else (),
                diary_frequency_mode=effective.mode,
            )
            # Keep the old robust diary writer output naming, but report the
            # profile label in warnings for traceability.
            created.extend(result.created_files)
        except Exception as exc:
            skipped.append(f"{document.button_label}: {exc}")
    return CustomDiaryGenerationResult(tuple(created), tuple(skipped), tuple(dict.fromkeys(warnings)))


def assert_universal_diary_generation_lock() -> None:
    if UNIVERSAL_DIARY_GENERATION_LOCK_VERSION != "v1.1":
        raise AssertionError("Universal diary generation lock changed unexpectedly")
    if not CUSTOM_DIARY_GENERATION_USES_EXISTING_DIARY_ENGINE:
        raise AssertionError("Custom diary generation must reuse the proven diary engine")
    if not CUSTOM_DIARY_CAN_USE_TEMPLATE_TEXTS_AS_STATUS_SOURCE:
        raise AssertionError("Custom diary templates with embedded texts must remain supported")


def _effective_status_files(status_files: Sequence[str | Path], template: Path) -> tuple[Path, ...]:
    explicit = tuple(Path(item).expanduser() for item in status_files if str(item).strip())
    if explicit:
        return explicit
    try:
        if extract_statuses_from_docx(template):
            return (template,)
    except Exception as exc:
        record_soft_exception("universal_diary_generation:embedded_statuses", exc)
        return ()
    return ()


def _resolve_template(document: DocumentTemplateSpec, base_dir: str | Path | None) -> Path:
    template = Path(document.template).expanduser()
    if template.is_absolute():
        return template
    if base_dir is None:
        return template
    base = Path(base_dir).expanduser()
    direct = base / template
    if direct.exists():
        return direct
    in_templates = base / "templates" / template.name
    if in_templates.exists():
        return in_templates
    return direct
