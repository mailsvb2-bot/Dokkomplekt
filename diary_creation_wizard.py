from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from diagnostic_logging import record_soft_exception
from medical_date_state import current_semantic_date

DIARY_CREATION_WIZARD_LOCK_VERSION = "v1.3"


@dataclass(frozen=True)
class DiaryWizardReview:
    patient_name: str
    admission_date: str
    discharge_date: str
    template_files: tuple[str, ...]
    text_files: tuple[str, ...]
    text_output: bool = False
    sick_leave_dynamic_epicrisis: bool = False
    frequency_mode: str = "daily"
    day_offsets: tuple[int, ...] = ()
    hour_offsets: tuple[int, ...] = ()
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
            f"Режим: {'текстовый DOCX' if self.text_output else 'таблица дневников'}",
            f"Частота: {'по часам' if self.frequency_mode == 'hourly' else 'ежедневно'}",
            f"Динамический эпикриз по больничному: {'да' if self.sick_leave_dynamic_epicrisis else 'нет'}",
            "Шаблоны дат:",
        ]
        lines.extend([f"  - {name}" for name in self.template_files] or ["  - не требуются для текстового режима" if self.text_output else "  - не выбраны"])
        lines.append("Тексты дневников:")
        lines.extend([f"  - {name}" for name in self.text_files] or ["  - не выбраны"])
        if self.day_offsets:
            lines.append("Дни дневников: " + ", ".join(str(item) for item in self.day_offsets))
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


def build_diary_wizard_review(app: object) -> DiaryWizardReview:
    def _get_var(name: str) -> str:
        try:
            var = getattr(app, name)
            return str(var.get() or "").strip()
        except Exception as exc:
            record_soft_exception("diary_creation_wizard.get_var", exc, detail=name)
            return ""

    patient = _get_var("patient_name_var")
    admission = current_semantic_date(app, "admission_date") or _get_var("admission_date_var")
    discharge = current_semantic_date(app, "discharge_date") or _get_var("discharge_date_var")
    templates = tuple(Path(item).name for item in getattr(app, "diary_files", []) or [])
    texts = tuple(Path(item).name for item in getattr(app, "status_files", []) or [])
    text_output = bool(getattr(app, "_diary_text_output_enabled", False))
    sick_leave_dynamic_epicrisis = _normalize_yes_no(_get_var("expert_sick_leave_needed_var")) == "да"
    frequency_mode = _get_var("diary_frequency_mode_var") or "daily"
    if frequency_mode not in {"daily", "hourly"}:
        frequency_mode = "daily"
    day_offsets: tuple[int, ...] = ()
    hour_offsets: tuple[int, ...] = ()
    try:
        getter = getattr(app, "_selected_profile_diary_schedule", None)
        schedule = getter() if callable(getter) else None
        if schedule is not None:
            day_offsets = tuple(int(item) for item in getattr(schedule, "day_offsets", ()) or ())
            if frequency_mode == "hourly":
                hour_offsets = tuple(int(item) for item in getattr(schedule, "hour_offsets", ()) or ())
    except Exception as exc:
        record_soft_exception("diary_creation_wizard.schedule", exc)
    if not templates and getattr(app, "diary_template_dir", ""):
        templates = (f"папка: {Path(str(getattr(app, 'diary_template_dir'))).name}",)
    if not texts and getattr(app, "diary_texts_dir", ""):
        texts = (f"папка: {Path(str(getattr(app, 'diary_texts_dir'))).name}",)
    warnings: list[str] = []
    if not patient:
        warnings.append("Введите ФИО пациента или загрузите первичный документ с ФИО.")
    if not admission:
        warnings.append("Не найдена дата госпитализации; дневники не знают, с какой даты начать.")
    if not discharge:
        warnings.append("Не указана дата выписки; программа не знает, на какой строке закончить дневники.")
    if not templates and not text_output:
        warnings.append("Выберите папку/шаблон дат дневников через кнопку Даты или включите текстовый режим дневников.")
    if not texts:
        warnings.append("Выберите тексты дневников через кнопку Тексты или настройте автоподбор по диагнозу.")
    if frequency_mode == "hourly" and not hour_offsets:
        warnings.append("Для режима по часам в профиле дневников нет часового расписания.")
    return DiaryWizardReview(patient, admission, discharge, templates, texts, text_output, sick_leave_dynamic_epicrisis, frequency_mode, day_offsets, hour_offsets, tuple(warnings))


def confirm_diary_creation(app: object) -> bool:
    review = build_diary_wizard_review(app)
    try:
        if hasattr(app, "_last_diary_wizard_review"):
            app._last_diary_wizard_review = review
    except Exception as exc:
        record_soft_exception("diary_creation_wizard.store_review", exc)
    if os.environ.get("CI"):
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
    if DIARY_CREATION_WIZARD_LOCK_VERSION != "v1.3":
        raise AssertionError("Diary creation wizard lock changed unexpectedly")
    empty = type("Empty", (), {})()
    review = build_diary_wizard_review(empty)
    text = review.as_text()
    if review.ok or "МАСТЕР ДНЕВНИКОВ" not in text or "Частота:" not in text:
        raise AssertionError("Diary wizard must block incomplete diary state and show frequency")
