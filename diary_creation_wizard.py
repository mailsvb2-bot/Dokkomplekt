from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from diagnostic_logging import record_soft_exception
from diary_schedule import (
    DiaryScheduleSpec,
    default_calendar_diary_schedule,
    describe_schedule,
    diary_calendar_schedule_from_choice,
)
from medical_date_state import current_semantic_date

DIARY_CREATION_WIZARD_LOCK_VERSION = "v1.6"
DIARY_WIZARD_USES_PROGRAM_CALENDAR_WITHOUT_DATE_TEMPLATE = True
DIARY_WIZARD_HEADLESS_SAFE = True
DIARY_WIZARD_HAS_NO_LEGACY_TABLE_MODE = True


@dataclass(frozen=True)
class DiaryWizardReview:
    patient_name: str
    admission_date: str
    discharge_date: str
    text_files: tuple[str, ...]
    sick_leave_dynamic_epicrisis: bool = False
    frequency_mode: str = "daily"
    day_offsets: tuple[int, ...] = ()
    hour_offsets: tuple[int, ...] = ()
    calendar_description: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.warnings

    def as_text(self) -> str:
        lines = [
            "МАСТЕР ДНЕВНИКОВ",
            "",
            f"Пациент: {self.patient_name or 'не указан'}",
            f"Дата госпитализации: {self.admission_date or 'не найдена'}",
            f"Дата выписки: {self.discharge_date or 'не указана'}",
            "Режим: текстовый DOCX по календарю программы",
            f"Частота: {'по часам' if self.frequency_mode == 'hourly' else 'ежедневно'}",
            "Принцип дат: " + (self.calendar_description or "календарь программы: ежедневно с +1 дня"),
            f"Финальная запись выписки: {'да' if self.discharge_date else 'нет — нужна дата выписки'}",
            f"Динамический эпикриз по больничному: {'да' if self.sick_leave_dynamic_epicrisis else 'нет'}",
            "Тексты дневников:",
        ]
        lines.extend([f"  - {name}" for name in self.text_files] or ["  - не выбраны"])
        if self.day_offsets:
            lines.append("Дни дневников: " + ", ".join(f"+{item}" for item in self.day_offsets[:20]))
        if self.frequency_mode == "hourly" and self.hour_offsets:
            lines.append("Часы дневников: " + ", ".join(str(item) for item in self.hour_offsets))
        if self.warnings:
            lines.append("")
            lines.append("Что надо исправить:")
            lines.extend([f"  - {item}" for item in self.warnings])
        else:
            lines.append("")
            lines.append("Дневники готовы к созданию.")
        return "\n".join(lines)


def _normalize_yes_no(value: object) -> str:
    text = str(value or "").strip().lower().replace("ё", "е")
    if text in {"да", "yes", "true", "1", "+", "нужен", "нужна"}:
        return "да"
    if text in {"нет", "no", "false", "0", "-"}:
        return "нет"
    return ""


def _get_var(app: object, name: str) -> str:
    try:
        var = getattr(app, name)
        return str(var.get() or "").strip()
    except Exception as exc:
        record_soft_exception("diary_creation_wizard.get_var", exc, detail=name)
        return ""


def _headless_or_ci(app: object) -> bool:
    if os.environ.get("CI") or os.environ.get("MEDICAL_AUTOFILL_DISABLE_AUTOSTART"):
        return True
    root = getattr(app, "root", None)
    if root is None:
        return True
    return not hasattr(root, "tk")


def _set_confirmed_schedule(app: object, spec: DiaryScheduleSpec, choice_text: str = "") -> DiaryScheduleSpec:
    description = describe_schedule(spec)
    setattr(app, "_doctor_confirmed_diary_day_offsets", tuple(spec.day_offsets))
    setattr(app, "_doctor_confirmed_diary_hour_offsets", tuple(spec.hour_offsets))
    setattr(app, "_doctor_confirmed_diary_principle", description)
    setattr(app, "_doctor_confirmed_diary_choice", str(choice_text or "1").strip() or "1")
    try:
        var = getattr(app, "diary_calendar_principle_var", None)
        if var is not None:
            var.set(description)
    except Exception as exc:
        record_soft_exception("diary_creation_wizard.set_principle_var", exc)
    try:
        updater = getattr(app, "_update_diary_template_label", None)
        if callable(updater):
            updater(success=True)
    except Exception as exc:
        record_soft_exception("diary_creation_wizard.update_date_label", exc)
    return spec


def current_diary_calendar_schedule(app: object, fallback: DiaryScheduleSpec | None = None) -> DiaryScheduleSpec:
    frequency = _get_var(app, "diary_frequency_mode_var") or "daily"
    confirmed_days = tuple(int(item) for item in getattr(app, "_doctor_confirmed_diary_day_offsets", ()) or ())
    confirmed_hours = tuple(int(item) for item in getattr(app, "_doctor_confirmed_diary_hour_offsets", ()) or ())
    if confirmed_days or confirmed_hours:
        return DiaryScheduleSpec(
            "hourly" if frequency == "hourly" and confirmed_hours else "daily",
            confirmed_days or default_calendar_diary_schedule().day_offsets,
            confirmed_hours,
            1.0,
            "doctor_confirmed_calendar_popup",
        )
    if fallback is not None and fallback.has_daily:
        return fallback.with_mode(frequency)
    return default_calendar_diary_schedule().with_mode(frequency)


def prompt_diary_calendar_principle(app: object) -> bool:
    if _headless_or_ci(app):
        if not getattr(app, "_doctor_confirmed_diary_day_offsets", ()):
            _set_confirmed_schedule(app, default_calendar_diary_schedule(), "1")
        return True
    try:
        from tkinter import messagebox, simpledialog
    except Exception as exc:
        record_soft_exception("diary_creation_wizard.import_tk_dialogs", exc)
        _set_confirmed_schedule(app, default_calendar_diary_schedule(), "1")
        return True

    current = str(getattr(app, "_doctor_confirmed_diary_choice", "") or "").strip() or "1"
    prompt = (
        "Как составлять дневники?\n\n"
        "1 — ежедневно, начиная со следующего дня после госпитализации (+1, +2, +3...)\n"
        "2 — клиническая схема: +1, +2, +3, +7, +10, +14...\n"
        "Или напишите свои дни через запятую: +1, +2, +3, +5, +7, +14.\n\n"
        "Даты ставит календарь программы. Отдельный шаблон дат не используется."
    )
    while True:
        choice = simpledialog.askstring("Как составлять дневники", prompt, initialvalue=current, parent=getattr(app, "root", None))
        if choice is None:
            return False
        try:
            spec = diary_calendar_schedule_from_choice(choice)
        except ValueError as exc:
            messagebox.showwarning("Проверьте принцип дневников", str(exc))
            current = choice
            continue
        _set_confirmed_schedule(app, spec, choice)
        return True


def build_diary_wizard_review(app: object) -> DiaryWizardReview:
    patient = _get_var(app, "patient_name_var")
    admission = current_semantic_date(app, "admission_date") or _get_var(app, "admission_date_var")
    discharge = current_semantic_date(app, "discharge_date") or _get_var(app, "discharge_date_var")
    texts = tuple(Path(item).name for item in getattr(app, "status_files", []) or [])
    sick_leave_dynamic_epicrisis = _normalize_yes_no(_get_var(app, "expert_sick_leave_needed_var")) == "да"
    frequency_mode = _get_var(app, "diary_frequency_mode_var") or "daily"
    if frequency_mode not in {"daily", "hourly"}:
        frequency_mode = "daily"
    schedule = current_diary_calendar_schedule(app)
    day_offsets = tuple(int(item) for item in getattr(schedule, "day_offsets", ()) or ())
    hour_offsets: tuple[int, ...] = ()
    if frequency_mode == "hourly":
        hour_offsets = tuple(int(item) for item in getattr(schedule, "hour_offsets", ()) or ())
    if not texts and getattr(app, "diary_texts_dir", ""):
        texts = (f"папка: {Path(str(getattr(app, 'diary_texts_dir'))).name}",)
    warnings: list[str] = []
    if not patient:
        warnings.append("Введите ФИО пациента или загрузите первичный документ с ФИО.")
    if not admission:
        warnings.append("Не найдена дата госпитализации; календарь дневников не знает, с какой даты начать.")
    if not discharge:
        warnings.append("Не указана Дата выписки; программа не знает, где поставить финальную запись выписки.")
    if not texts:
        warnings.append("Выберите тексты дневников через кнопку Тексты или настройте автоподбор по диагнозу.")
    if not day_offsets and frequency_mode != "hourly":
        warnings.append("Подтвердите принцип составления дневников: ежедневно, клиническая схема или свои дни.")
    if frequency_mode == "hourly" and not hour_offsets:
        warnings.append("Для режима по часам в профиле дневников нет часового расписания.")
    return DiaryWizardReview(
        patient,
        admission,
        discharge,
        texts,
        sick_leave_dynamic_epicrisis,
        frequency_mode,
        day_offsets,
        hour_offsets,
        describe_schedule(schedule),
        tuple(warnings),
    )


def confirm_diary_creation(app: object) -> bool:
    if not prompt_diary_calendar_principle(app):
        return False
    review = build_diary_wizard_review(app)
    try:
        if hasattr(app, "_last_diary_wizard_review"):
            app._last_diary_wizard_review = review
    except Exception as exc:
        record_soft_exception("diary_creation_wizard.store_review", exc)
    if _headless_or_ci(app):
        return review.ok
    try:
        from tkinter import messagebox
        if not review.ok:
            messagebox.showwarning("Мастер дневников", review.as_text())
            return False
        return bool(messagebox.askyesno("Мастер дневников", review.as_text() + "\n\nСоздать дневники?"))
    except Exception as exc:
        record_soft_exception("diary_creation_wizard.confirm", exc)
        return review.ok


def assert_diary_creation_wizard_lock() -> None:
    if DIARY_CREATION_WIZARD_LOCK_VERSION != "v1.6":
        raise AssertionError("Diary creation wizard lock changed unexpectedly")
    if not DIARY_WIZARD_USES_PROGRAM_CALENDAR_WITHOUT_DATE_TEMPLATE:
        raise AssertionError("Diary wizard must not require a DOCX date template")
    if not DIARY_WIZARD_HEADLESS_SAFE:
        raise AssertionError("Diary wizard must auto-confirm safely in CI/headless tests")
    if not DIARY_WIZARD_HAS_NO_LEGACY_TABLE_MODE:
        raise AssertionError("Diary wizard must not expose legacy table mode")
    empty = type("Empty", (), {})()
    review = build_diary_wizard_review(empty)
    text = review.as_text()
    if review.ok or "МАСТЕР ДНЕВНИКОВ" not in text or "Принцип дат:" not in text:
        raise AssertionError("Diary wizard must block incomplete diary state and show calendar principle")
    if "таблица дневников" in text.lower() or "шаблоны дат" in text.lower():
        raise AssertionError("Diary wizard must not expose legacy table/date-template wording")
    if "текстовый DOCX по календарю программы" not in text:
        raise AssertionError("Diary wizard must present the single text-calendar route")
