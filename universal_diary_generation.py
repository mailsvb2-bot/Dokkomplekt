"""Render/fill custom diary documents stored in a medpack."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from typing import Sequence

from diagnostic_logging import record_soft_exception
from diary_batch import _day_offsets_from_date_templates, fill_diary_batch
from diary_dates import parse_full_datetime, parse_optional_discharge_date
from diary_paths import available_path
from diary_text_parser import extract_statuses_from_docx
from diary_schedule import DiaryScheduleSpec
from universal_fields import PatientCase
from universal_profiles import DocumentPack, DocumentTemplateSpec

UNIVERSAL_DIARY_GENERATION_LOCK_VERSION = "v1.5"
CUSTOM_DIARY_GENERATION_USES_SEMANTIC_TEXT_CALENDAR = True
CUSTOM_DIARY_CAN_USE_TEMPLATE_TEXTS_AS_STATUS_SOURCE = True
# The removed legacy GLOBAL table backend stays disabled. Every user-facing diary
# output is a text DOCX. Word tables may supply dates, but are never the result format.
CUSTOM_DIARY_TABLE_FILLING_IS_DISABLED = True
CUSTOM_DIARY_OUTPUT_IS_TEXT_ONLY = True
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
    date_files: Sequence[str | Path] = (),
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
    """Render selected custom diary buttons through the canonical text route.

    Block-02 ``Тексты`` are the observation source and block-02 ``Даты`` may
    supply the date plan.  A doctor-owned Word template can still provide
    fallback observation text when no external text source was selected, but
    table layout is never copied into the generated diary.  The selected set
    remains atomic: one failed diary invalidates the whole generated subset.
    """

    selected = {str(item).strip() for item in document_ids if str(item).strip()}
    created: list[Path] = []
    skipped: list[str] = []
    warnings: list[str] = []
    matched_ids: set[str] = set()
    rendered_signatures: dict[tuple[object, ...], str] = {}
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
        explicit_status_files = tuple(Path(item).expanduser() for item in status_files if str(item).strip())
        effective_status_files = explicit_status_files or _effective_status_files((), template)
        if not effective_status_files:
            skipped.append(f"{document.button_label}: не выбраны тексты дневников и в этом шаблоне не найдено текстов наблюдения")
            continue
        try:
            effective_date_files = tuple(Path(item).expanduser() for item in date_files if str(item).strip())
            effective_minute_offsets = effective.minute_offsets if effective.mode == "hourly" else ()
            if effective.mode == "hourly" and effective_date_files and not effective_minute_offsets and effective.hour_offsets:
                # A selected block-02 Dates file constrains the calendar. Convert
                # the hourly rhythm to intraday minutes so fill_diary_batch can
                # combine that rhythm with the dates parsed from the selected file.
                effective_minute_offsets = tuple(max(1, int(item)) * 60 for item in effective.hour_offsets)
            render_signature: tuple[object, ...] = (
                tuple(str(path.resolve()) for path in effective_status_files),
                tuple(str(path.resolve()) for path in effective_date_files),
                effective.mode,
                tuple(effective.day_offsets),
                tuple(effective.hour_offsets if effective.mode == "hourly" else ()),
                tuple(effective_minute_offsets),
            )
            existing_button = rendered_signatures.get(render_signature)
            if existing_button is not None:
                warnings.append(
                    f"{document.button_label}: совпадает по текстам, датам и ритму с «{existing_button}»; создан один общий дневник"
                )
                continue
            effective_admission = admission_value or case.get("admission.date")
            effective_discharge = discharge_value or case.get("discharge.date")
            if effective_date_files:
                try:
                    admission_date = parse_full_datetime(effective_admission).date()
                except ValueError:
                    admission_date = None
                discharge_date = parse_optional_discharge_date(effective_discharge)
                selected_offsets = _day_offsets_from_date_templates(
                    effective_date_files,
                    admission_date_value=admission_date,
                    discharge_date_value=discharge_date,
                )
                if not selected_offsets:
                    raise ValueError("в выбранном файле дат дневников не найдено подходящих дат в периоде госпитализации")

            final_output_dir = Path(output_dir).expanduser()
            final_output_dir.mkdir(parents=True, exist_ok=True)
            published_this_call: list[Path] = []
            try:
                with TemporaryDirectory(prefix=".dokkomplekt-diary-", dir=final_output_dir) as staging_dir:
                    result = fill_diary_batch(
                        status_files=effective_status_files,
                        diary_files=tuple(Path(item).expanduser() for item in date_files if str(item).strip()),
                        output_dir=staging_dir,
                        patient_name=patient_name or case.get("patient.fio") or "Пациент",
                        admission_value=effective_admission,
                        gender_source_name=gender_source_name or case.get("patient.fio") or patient_name,
                        discharge_value=effective_discharge,
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
                        diary_minute_offsets=effective_minute_offsets,
                        diary_frequency_mode=effective.mode,
                        text_output=True,
                        sick_leave_dynamic_epicrisis=sick_leave_dynamic_epicrisis,
                        treatment_correction=treatment_correction,
                        birth_date=birth_date,
                        complaints=complaints,
                        treatment=treatment,
                        profile_status=profile_status,
                        sick_leave_from=sick_leave_from,
                        treating_physician=case.get("doctor.name"),
                        department_head=case.get("head.name"),
                    )
                    if not result.created_files:
                        raise ValueError("текстовый дневник не был создан")
                    if effective.mode == "hourly":
                        from document_intelligence.diary_hourly_finalization import ensure_hourly_final_diary

                        ensure_hourly_final_diary(
                            result,
                            discharge_value=effective_discharge,
                            patient_name=case.get("patient.fio") or patient_name,
                            force_final_diary=force_final_diary,
                        )
                    for staged_path in result.created_files:
                        source = Path(staged_path)
                        destination = available_path(final_output_dir / source.name)
                        shutil.move(str(source), str(destination))
                        published_this_call.append(destination)
            except Exception:
                for published_path in published_this_call:
                    try:
                        published_path.unlink(missing_ok=True)
                    except OSError as cleanup_exc:
                        record_soft_exception("universal_diary_generation.rollback_current_call", cleanup_exc, detail=str(published_path))
                raise
            created.extend(published_this_call)
            rendered_signatures[render_signature] = document.button_label
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
    if UNIVERSAL_DIARY_GENERATION_LOCK_VERSION != "v1.5":
        raise AssertionError("Universal diary generation lock changed unexpectedly")
    if not CUSTOM_DIARY_GENERATION_USES_SEMANTIC_TEXT_CALENDAR:
        raise AssertionError("Custom diary generation must use the semantic text-calendar path")
    if not CUSTOM_DIARY_CAN_USE_TEMPLATE_TEXTS_AS_STATUS_SOURCE:
        raise AssertionError("Custom diary templates with embedded texts must remain supported as text sources")
    if not CUSTOM_DIARY_TABLE_FILLING_IS_DISABLED:
        raise AssertionError("Removed legacy global diary table filling must stay disabled")
    if not CUSTOM_DIARY_OUTPUT_IS_TEXT_ONLY:
        raise AssertionError("Every user-facing diary output must be a text DOCX")
    if not CUSTOM_DIARY_GENERATION_IS_ALL_OR_NOTHING:
        raise AssertionError("Selected custom diary set must be all-or-nothing")
    if not CUSTOM_DIARY_EMBEDDED_TEXT_SOURCE_IS_DOCUMENT_LOCAL:
        raise AssertionError("Each doctor-owned diary must preserve its own embedded text source")
    if not CUSTOM_DIARY_GENERATION_USES_DOCTOR_CONFIRMED_POPUP_SCHEDULE:
        raise AssertionError("Custom diary generation must preserve doctor-confirmed popup schedule")
    if not CUSTOM_DIARY_GENERATION_PROPAGATES_MINUTE_RHYTHM:
        raise AssertionError("Custom diary generation must preserve minute rhythm on both diary routes")
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

    The user-facing render path handles an explicitly selected block-02 ``Тексты``
    before calling this helper. Keeping this helper document-local preserves the
    established internal contract for embedded-template fallbacks.
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
