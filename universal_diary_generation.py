"""Render/fill custom diary documents stored in a medpack."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from diagnostic_logging import record_soft_exception
from diary_batch import read_statuses_from_files
from diary_text_parser import extract_statuses_from_docx
from diary_schedule import DiaryScheduleSpec
from universal_fields import PatientCase
from universal_profiles import DocumentPack, DocumentTemplateSpec

UNIVERSAL_DIARY_GENERATION_LOCK_VERSION = "v1.4"
CUSTOM_DIARY_GENERATION_USES_SEMANTIC_TEXT_CALENDAR = True
CUSTOM_DIARY_CAN_USE_TEMPLATE_TEXTS_AS_STATUS_SOURCE = True
# The removed legacy GLOBAL table backend stays disabled. Doctor-owned block-03
# diaries now use their own isolated template-preserving renderer instead.
CUSTOM_DIARY_TABLE_FILLING_IS_DISABLED = True
CUSTOM_DIARY_USES_DOCTOR_TEMPLATE_RENDERER = True
CUSTOM_DIARY_GENERATION_IS_ALL_OR_NOTHING = True
CUSTOM_DIARY_EMBEDDED_TEXT_SOURCE_IS_DOCUMENT_LOCAL = True
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
    """Render selected custom diary buttons from the doctor's actual Word files.

    Unlike the generic Dates+Texts route, a doctor-owned custom diary is a
    template contract. Its DOCX is copied/rendered and remains the owner of
    layout/signatures. The selected set is atomic: one failed diary invalidates
    and removes the whole generated custom-diary subset.
    """

    _ = (reset_each_file, keep_signature, fill_months, remove_holiday_rows, write_report)
    selected = {str(item).strip() for item in document_ids if str(item).strip()}
    created: list[Path] = []
    skipped: list[str] = []
    warnings: list[str] = []
    matched_ids: set[str] = set()
    doctor_schedule = _doctor_confirmed_schedule_from_offsets(
        frequency_mode=frequency_mode,
        day_offsets=diary_day_offsets,
        hour_offsets=diary_hour_offsets,
        minute_offsets=diary_minute_offsets,
    )

    for document in pack.documents:
        if document.category != "diaries" or (selected and document.id not in selected):
            continue
        matched_ids.add(document.id)
        template = _resolve_template(document, base_dir)
        if not template.exists():
            skipped.append(f"{document.button_label}: шаблон дневников не найден ({document.template})")
            continue
        effective = doctor_schedule or _schedule_from_profile(document, frequency_mode)
        effective_status_files = _effective_status_files(status_files, template)
        if not effective_status_files:
            skipped.append(f"{document.button_label}: не выбраны тексты дневников и в этом шаблоне не найдено текстов наблюдения")
            continue
        try:
            statuses = read_statuses_from_files(effective_status_files)
            if not statuses:
                raise ValueError("в источнике не найдено подходящих текстов наблюдения")
            from custom_diary_template_renderer import render_custom_diary_template

            rendered = render_custom_diary_template(
                template_path=template,
                output_dir=output_dir,
                case=case,
                document=document,
                schedule=effective,
                statuses=statuses,
                patient_name=patient_name or case.get("patient.fio") or "Пациент",
                admission_value=admission_value or case.get("admission.date"),
                discharge_value=discharge_value or case.get("discharge.date"),
                repeat_statuses=repeat_statuses,
                force_final_diary=force_final_diary,
                sick_leave_dynamic_epicrisis=sick_leave_dynamic_epicrisis,
                treatment_correction=treatment_correction,
                birth_date=birth_date,
                complaints=complaints,
                treatment=treatment,
                profile_status=profile_status,
                sick_leave_from=sick_leave_from,
            )
            created.append(rendered.path)
        except Exception as exc:
            skipped.append(f"{document.button_label}: {exc}")

    for missing_id in sorted(selected - matched_ids):
        skipped.append(f"{missing_id}: выбранная кнопка дневников отсутствует в текущем профиле")

    if skipped:
        # Do not let the creation transaction publish a deceptively partial set.
        for path in created:
            try:
                Path(path).unlink()
            except OSError as exc:
                record_soft_exception("universal_diary_generation.rollback_partial", exc, detail=str(path))
        created = []

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
    if UNIVERSAL_DIARY_GENERATION_LOCK_VERSION != "v1.4":
        raise AssertionError("Universal diary generation lock changed unexpectedly")
    if not CUSTOM_DIARY_GENERATION_USES_SEMANTIC_TEXT_CALENDAR:
        raise AssertionError("Custom diary generation must use the semantic text-calendar path")
    if not CUSTOM_DIARY_CAN_USE_TEMPLATE_TEXTS_AS_STATUS_SOURCE:
        raise AssertionError("Custom diary templates with embedded texts must remain supported as text sources")
    if not CUSTOM_DIARY_TABLE_FILLING_IS_DISABLED:
        raise AssertionError("Removed legacy global diary table filling must stay disabled")
    if not CUSTOM_DIARY_USES_DOCTOR_TEMPLATE_RENDERER:
        raise AssertionError("Doctor-owned custom diaries must preserve their Word template")
    if not CUSTOM_DIARY_GENERATION_IS_ALL_OR_NOTHING:
        raise AssertionError("Selected custom diary set must be all-or-nothing")
    if not CUSTOM_DIARY_EMBEDDED_TEXT_SOURCE_IS_DOCUMENT_LOCAL:
        raise AssertionError("Each doctor-owned diary must prefer its own embedded texts")
    if not CUSTOM_DIARY_GENERATION_USES_DOCTOR_CONFIRMED_POPUP_SCHEDULE:
        raise AssertionError("Custom diary generation must preserve doctor-confirmed popup schedule")
    if not CUSTOM_DIARY_GENERATION_PROPAGATES_MINUTE_RHYTHM:
        raise AssertionError("Custom diary generation must pass minute rhythm into the template renderer")
    if not CUSTOM_DIARY_GENERATION_PROPAGATES_SICK_LEAVE_EPICRISIS:
        raise AssertionError("Custom diary generation must preserve sick-leave dynamic epicrisis fields")


def diary_documents_have_embedded_status_texts(
    *,
    pack: DocumentPack,
    document_ids: Sequence[str],
    base_dir: str | Path | None,
) -> bool:
    """Return True when every selected custom diary can supply its own statuses."""

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
    """Prefer this diary button's own embedded texts, then external fallback.

    External status files are shared patient-level input. They must never erase
    the distinct texts of another selected doctor-owned diary template.
    """

    try:
        if extract_statuses_from_docx(template):
            return (template,)
    except Exception as exc:
        record_soft_exception("universal_diary_generation.embedded_statuses", exc, detail=str(template))
    explicit = tuple(Path(item).expanduser() for item in status_files if str(item).strip())
    return explicit


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
