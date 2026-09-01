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

UNIVERSAL_DIARY_GENERATION_LOCK_VERSION = "v1.3"
CUSTOM_DIARY_GENERATION_USES_SEMANTIC_TEXT_CALENDAR = True
CUSTOM_DIARY_CAN_USE_TEMPLATE_TEXTS_AS_STATUS_SOURCE = True
CUSTOM_DIARY_TABLE_FILLING_IS_DISABLED = True
CUSTOM_DIARY_GENERATION_USES_DOCTOR_CONFIRMED_POPUP_SCHEDULE = True
CUSTOM_DIARY_GENERATION_PROPAGATES_MINUTE_RHYTHM = True
CUSTOM_DIARY_GENERATION_PROPAGATES_SICK_LEAVE_EPICRISIS = True


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
    diary_day_offsets: Sequence[int] = (),
    diary_hour_offsets: Sequence[int] = (),
    diary_minute_offsets: Sequence[int] = (),
    repeat_statuses: bool = True,
    reset_each_file: bool = True,
    keep_signature: bool = True,
    fill_months: bool = True,
    force_final_diary: bool = True,
    remove_holiday_rows: bool = True,
    write_report: bool = False,
    sick_leave_dynamic_epicrisis: bool = False,
    treatment_correction: str = "",
    birth_date: str = "",
    complaints: str = "",
    treatment: str = "",
    profile_status: str = "",
    sick_leave_from: str = "",
) -> CustomDiaryGenerationResult:
    """Render selected custom diary buttons through the text-calendar diary engine."""
    selected = {str(item).strip() for item in document_ids if str(item).strip()}
    created: list[Path] = []
    skipped: list[str] = []
    warnings: list[str] = []
    doctor_schedule = _doctor_confirmed_schedule_from_offsets(
        frequency_mode=frequency_mode,
        day_offsets=diary_day_offsets,
        hour_offsets=diary_hour_offsets,
        minute_offsets=diary_minute_offsets,
    )
    for document in pack.documents:
        if document.category != "diaries" or (selected and document.id not in selected):
            continue
        template = _resolve_template(document, base_dir)
        if not template.exists():
            skipped.append(f"{document.button_label}: источник текстов дневников не найден ({document.template})")
            continue
        effective = doctor_schedule or _schedule_from_profile(document, frequency_mode)
        effective_status_files = _effective_status_files(status_files, template)
        if not effective_status_files:
            skipped.append(f"{document.button_label}: не выбраны тексты дневников и в файле профиля не найдено текстов наблюдения")
            continue
        try:
            result = fill_diary_batch(
                status_files=effective_status_files,
                diary_files=[],
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
                diary_minute_offsets=effective.minute_offsets if effective.mode == "hourly" else (),
                diary_frequency_mode=effective.mode,
                text_output=True,
                sick_leave_dynamic_epicrisis=sick_leave_dynamic_epicrisis,
                treatment_correction=treatment_correction,
                birth_date=birth_date,
                complaints=complaints,
                treatment=treatment,
                profile_status=profile_status,
                sick_leave_from=sick_leave_from,
            )
            created.extend(result.created_files)
        except Exception as exc:
            skipped.append(f"{document.button_label}: {exc}")
    return CustomDiaryGenerationResult(tuple(created), tuple(skipped), tuple(dict.fromkeys(warnings)))


def _doctor_confirmed_schedule_from_offsets(
    *,
    frequency_mode: str,
    day_offsets: Sequence[int],
    hour_offsets: Sequence[int],
    minute_offsets: Sequence[int],
) -> DiaryScheduleSpec | None:
    days = _positive_int_tuple(day_offsets, allow_zero=True)
    hours = _positive_int_tuple(hour_offsets)
    minutes = _positive_int_tuple(minute_offsets)
    mode = str(frequency_mode or "daily").strip().lower()
    if minutes:
        return DiaryScheduleSpec("hourly", days, (), 1.0, "doctor_confirmed_custom_diary_popup", minutes)
    if mode == "hourly" and hours:
        return DiaryScheduleSpec("hourly", days, hours, 1.0, "doctor_confirmed_custom_diary_popup")
    if days:
        return DiaryScheduleSpec("daily", days, (), 1.0, "doctor_confirmed_custom_diary_popup")
    return None


def _schedule_from_profile(document: DocumentTemplateSpec, frequency_mode: str) -> DiaryScheduleSpec:
    schedule = DiaryScheduleSpec.from_dict(getattr(document, "diary_schedule", None))
    if str(frequency_mode or "daily").strip().lower() == "hourly" and schedule.has_hourly:
        return schedule.with_mode("hourly")
    return schedule.with_mode("daily")


def _positive_int_tuple(values: Sequence[int], *, allow_zero: bool = False) -> tuple[int, ...]:
    result: list[int] = []
    seen: set[int] = set()
    for raw in values or ():
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value < 0 or (value == 0 and not allow_zero):
            continue
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def assert_universal_diary_generation_lock() -> None:
    if UNIVERSAL_DIARY_GENERATION_LOCK_VERSION != "v1.3":
        raise AssertionError("Universal diary generation lock changed unexpectedly")
    if not CUSTOM_DIARY_GENERATION_USES_SEMANTIC_TEXT_CALENDAR:
        raise AssertionError("Custom diary generation must use the semantic text-calendar path")
    if not CUSTOM_DIARY_CAN_USE_TEMPLATE_TEXTS_AS_STATUS_SOURCE:
        raise AssertionError("Custom diary templates with embedded texts must remain supported as text sources")
    if not CUSTOM_DIARY_TABLE_FILLING_IS_DISABLED:
        raise AssertionError("Custom diary generation must not re-enable legacy table filling")
    if not CUSTOM_DIARY_GENERATION_USES_DOCTOR_CONFIRMED_POPUP_SCHEDULE:
        raise AssertionError("Custom diary generation must preserve doctor-confirmed popup schedule")
    if not CUSTOM_DIARY_GENERATION_PROPAGATES_MINUTE_RHYTHM:
        raise AssertionError("Custom diary generation must pass minute rhythm into fill_diary_batch")
    if not CUSTOM_DIARY_GENERATION_PROPAGATES_SICK_LEAVE_EPICRISIS:
        raise AssertionError("Custom diary generation must pass sick-leave dynamic epicrisis fields")


def diary_documents_have_embedded_status_texts(
    *,
    pack: DocumentPack,
    document_ids: Sequence[str],
    base_dir: str | Path | None,
) -> bool:
    """Return True when every selected custom diary can supply its own status texts.

    The application must not force a second text-file chooser when the doctor's
    diary template already contains the observation texts consumed by this engine.
    """

    selected = {str(item).strip() for item in document_ids if str(item).strip()}
    matched = 0
    for document in pack.documents:
        if document.category != "diaries" or (selected and document.id not in selected):
            continue
        matched += 1
        template = _resolve_template(document, base_dir)
        if not template.exists():
            return False
        try:
            if not extract_statuses_from_docx(template):
                return False
        except Exception as exc:
            record_soft_exception("universal_diary_generation.embedded_status_probe", exc, detail=str(template))
            return False
    return matched > 0


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
