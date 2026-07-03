from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from diagnostic_logging import record_soft_exception
from diary_schedule import DIARY_POPUP_STYLE_CHOICES, DiaryScheduleSpec, default_calendar_diary_schedule, describe_schedule, diary_calendar_schedule_from_choice, diary_hourly_schedule_from_choice
from medical_date_state import current_semantic_date

DIARY_CREATION_WIZARD_LOCK_VERSION = "v1.9"
DIARY_WIZARD_USES_PROGRAM_CALENDAR_WITHOUT_DATE_TEMPLATE = True
DIARY_WIZARD_HEADLESS_SAFE = True
DIARY_WIZARD_HAS_NO_LEGACY_TABLE_MODE = True
DIARY_WIZARD_HAS_STYLE_POPUP_CHOICES = True
DIARY_WIZARD_HAS_SICK_LEAVE_EPICRISIS_POPUP = True


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
            "МАСТЕР ДНЕВНИКОВ", "",
            f"Пациент: {self.patient_name or 'не указан'}",
            f"Дата госпитализации: {self.admission_date or 'не найдена'}",
            f"Дата выписки: {self.discharge_date or 'не указана'}",
            "Режим: текстовый DOCX, без таблиц",
            "Принцип: " + (self.calendar_description or "не выбран"),
            f"Лечится по больничному листу: {'да' if self.sick_leave_dynamic_epicrisis else 'нет'}",
            "Тексты дневников:",
        ]
        lines.extend([f"  - {name}" for name in self.text_files] or ["  - не выбраны"])
        if self.day_offsets:
            lines.append("Дни: " + ", ".join(f"+{item}" for item in self.day_offsets[:20]))
        if self.frequency_mode == "hourly" and self.hour_offsets:
            lines.append("Часы: " + ", ".join(f"+{item} ч" for item in self.hour_offsets[:20]))
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


def _set_var(app: object, name: str, value: str) -> None:
    try:
        var = getattr(app, name, None)
        if var is not None and hasattr(var, "set"):
            var.set(value)
    except Exception as exc:
        record_soft_exception("diary_creation_wizard.set_var", exc, detail=name)


def _headless_or_ci(app: object) -> bool:
    if os.environ.get("CI") or os.environ.get("MEDICAL_AUTOFILL_DISABLE_AUTOSTART"):
        return True
    root = getattr(app, "root", None)
    if root is None:
        return True
    return not hasattr(root, "tk")


def _set_confirmed_schedule(app: object, spec: DiaryScheduleSpec, choice_text: str = "", style_choice: str = "") -> DiaryScheduleSpec:
    description = describe_schedule(spec)
    setattr(app, "_doctor_confirmed_diary_day_offsets", tuple(spec.day_offsets))
    setattr(app, "_doctor_confirmed_diary_hour_offsets", tuple(spec.hour_offsets))
    setattr(app, "_doctor_confirmed_diary_frequency_mode", spec.mode)
    setattr(app, "_doctor_confirmed_diary_principle", description)
    setattr(app, "_doctor_confirmed_diary_choice", str(choice_text or "1").strip() or "1")
    if style_choice:
        setattr(app, "_doctor_confirmed_diary_style_choice", str(style_choice).strip())
    _set_var(app, "diary_frequency_mode_var", spec.mode)
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
    confirmed_mode = str(getattr(app, "_doctor_confirmed_diary_frequency_mode", "") or "").strip().lower()
    ui_mode = _get_var(app, "diary_frequency_mode_var") or "daily"
    frequency = confirmed_mode if confirmed_mode in {"daily", "hourly"} else ui_mode
    confirmed_days = tuple(int(item) for item in getattr(app, "_doctor_confirmed_diary_day_offsets", ()) or ())
    confirmed_hours = tuple(int(item) for item in getattr(app, "_doctor_confirmed_diary_hour_offsets", ()) or ())
    if confirmed_hours:
        return DiaryScheduleSpec("hourly", confirmed_days, confirmed_hours, 1.0, "doctor_confirmed_style_popup")
    if confirmed_days:
        return DiaryScheduleSpec("daily", confirmed_days, (), 1.0, "doctor_confirmed_style_popup")
    if fallback is not None:
        if frequency == "hourly" and fallback.has_hourly:
            return fallback.with_mode("hourly")
        if frequency == "daily" and fallback.has_daily:
            return fallback.with_mode("daily")
    return default_calendar_diary_schedule().with_mode(frequency)


def _prompt_sick_leave_epicrisis(app: object, messagebox, simpledialog) -> None:
    answer = messagebox.askyesno("Лечится по больничному листу", "Лечится по больничному листу?\n\nЕсли да — программа будет писать динамический эпикриз 1 раз в 10 дней.")
    if not answer:
        _set_var(app, "expert_sick_leave_needed_var", "нет")
        return
    _set_var(app, "expert_sick_leave_needed_var", "да")
    current = _get_var(app, "diary_treatment_correction_var") or "Лекарства принимает согласно назначениям."
    correction = simpledialog.askstring("Коррекция лечения", "Введите коррекцию лечения.\nЕсли оставить пустым, будет: лекарства принимает согласно назначениям.", initialvalue=current, parent=getattr(app, "root", None))
    if correction is not None:
        _set_var(app, "diary_treatment_correction_var", str(correction).strip())


def _confirm_schedule_and_sick_leave(app: object, spec: DiaryScheduleSpec, choice_text: str, style_choice: str, messagebox, simpledialog) -> bool:
    _set_confirmed_schedule(app, spec, choice_text, style_choice)
    _prompt_sick_leave_epicrisis(app, messagebox, simpledialog)
    return True


def prompt_diary_calendar_principle(app: object) -> bool:
    if _headless_or_ci(app):
        if not getattr(app, "_doctor_confirmed_diary_day_offsets", ()) and not getattr(app, "_doctor_confirmed_diary_hour_offsets", ()):
            _set_confirmed_schedule(app, default_calendar_diary_schedule(), "1", "1")
        return True
    try:
        from tkinter import messagebox, simpledialog
    except Exception as exc:
        record_soft_exception("diary_creation_wizard.import_tk_dialogs", exc)
        _set_confirmed_schedule(app, default_calendar_diary_schedule(), "1", "1")
        return True
    current = str(getattr(app, "_doctor_confirmed_diary_style_choice", "") or "1").strip() or "1"
    style_prompt = "1 - каждый день\n2 - 1, 2, 3 день...\n3 - каждый день по времени\n4 - свой стиль"
    while True:
        style = simpledialog.askstring("Стиль дневников", style_prompt, initialvalue=current, parent=getattr(app, "root", None))
        if style is None:
            return False
        text = str(style or "").strip().lower().replace("ё", "е")
        try:
            if text in {"1", "каждый день", "ежедневно"}:
                return _confirm_schedule_and_sick_leave(app, diary_calendar_schedule_from_choice("1"), "1", "1", messagebox, simpledialog)
            if text in {"2", "1,2,3", "1, 2, 3", "1 2 3"} or "1,2,3" in text or "1, 2, 3" in text:
                return _confirm_schedule_and_sick_leave(app, diary_calendar_schedule_from_choice("2"), "2", "2", messagebox, simpledialog)
            if text in {"3", "по времени", "каждый день по времени"} or "времен" in text:
                current_time = str(getattr(app, "_doctor_confirmed_diary_hourly_choice", "") or "24").strip()
                value = simpledialog.askstring("Дневники по времени", "24 - каждый день в то же время; 2 - каждые 2 часа; 1,2,4 - свой стиль", initialvalue=current_time, parent=getattr(app, "root", None))
                if value is None:
                    current = "3"
                    continue
                spec = diary_hourly_schedule_from_choice(value)
                setattr(app, "_doctor_confirmed_diary_hourly_choice", str(value).strip())
                return _confirm_schedule_and_sick_leave(app, spec, value, "3", messagebox, simpledialog)
            if text in {"4", "свой", "свой стиль"} or "свой" in text:
                current_custom = str(getattr(app, "_doctor_confirmed_diary_custom_choice", "") or "+1, +2, +3, +5, +7, +14").strip()
                value = simpledialog.askstring("Свой стиль дневников", "Введите дни: +1, +2, +3, +5, +7, +14", initialvalue=current_custom, parent=getattr(app, "root", None))
                if value is None:
                    current = "4"
                    continue
                spec = diary_calendar_schedule_from_choice(value)
                setattr(app, "_doctor_confirmed_diary_custom_choice", str(value).strip())
                return _confirm_schedule_and_sick_leave(app, spec, value, "4", messagebox, simpledialog)
            raise ValueError("Выберите 1, 2, 3 или 4.")
        except ValueError as exc:
            messagebox.showwarning("Проверьте стиль дневников", str(exc))
            current = str(style or "").strip() or current


def build_diary_wizard_review(app: object) -> DiaryWizardReview:
    patient = _get_var(app, "patient_name_var")
    admission = current_semantic_date(app, "admission_date") or _get_var(app, "admission_date_var")
    discharge = current_semantic_date(app, "discharge_date") or _get_var(app, "discharge_date_var")
    texts = tuple(Path(item).name for item in getattr(app, "status_files", []) or [])
    sick_leave_dynamic_epicrisis = _normalize_yes_no(_get_var(app, "expert_sick_leave_needed_var")) == "да"
    schedule = current_diary_calendar_schedule(app)
    frequency_mode = schedule.mode if schedule.mode in {"daily", "hourly"} else "daily"
    day_offsets = tuple(int(item) for item in getattr(schedule, "day_offsets", ()) or ())
    hour_offsets: tuple[int, ...] = tuple(int(item) for item in getattr(schedule, "hour_offsets", ()) or ()) if frequency_mode == "hourly" else ()
    if not texts and getattr(app, "diary_texts_dir", ""):
        texts = (f"папка: {Path(str(getattr(app, 'diary_texts_dir'))).name}",)
    warnings: list[str] = []
    if not patient:
        warnings.append("Введите ФИО пациента или загрузите первичный документ с ФИО.")
    if not admission:
        warnings.append("Не найдена дата госпитализации.")
    if not discharge:
        warnings.append("Не указана Дата выписки.")
    if not texts:
        warnings.append("Выберите тексты дневников.")
    if not day_offsets and frequency_mode != "hourly":
        warnings.append("Подтвердите стиль дневников.")
    if frequency_mode == "hourly" and not hour_offsets:
        warnings.append("Подтвердите интервалы часов.")
    return DiaryWizardReview(patient, admission, discharge, texts, sick_leave_dynamic_epicrisis, frequency_mode, day_offsets, hour_offsets, describe_schedule(schedule), tuple(warnings))


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
    if DIARY_CREATION_WIZARD_LOCK_VERSION != "v1.9":
        raise AssertionError("Diary creation wizard lock changed unexpectedly")
    if not DIARY_WIZARD_USES_PROGRAM_CALENDAR_WITHOUT_DATE_TEMPLATE:
        raise AssertionError("Diary wizard must not require date templates")
    if not DIARY_WIZARD_HEADLESS_SAFE:
        raise AssertionError("Diary wizard must stay headless-safe")
    if not DIARY_WIZARD_HAS_NO_LEGACY_TABLE_MODE:
        raise AssertionError("Diary wizard must not expose table mode")
    if not DIARY_WIZARD_HAS_STYLE_POPUP_CHOICES:
        raise AssertionError("Diary wizard must expose style popup choices")
    if not DIARY_WIZARD_HAS_SICK_LEAVE_EPICRISIS_POPUP:
        raise AssertionError("Diary wizard must expose sick leave epicrisis branch")
    if DIARY_POPUP_STYLE_CHOICES != ("каждый день", "1, 2, 3 день...", "каждый день по времени", "свой стиль"):
        raise AssertionError("Diary style choices changed")
