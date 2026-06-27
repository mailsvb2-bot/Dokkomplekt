"""Focused diary creation wizard/preflight.

Diaries are the most fragile output: they depend on admission date, discharge
date, a numbered 01-31 table and separate text files.  This module keeps that
preflight visible and testable instead of hiding it in the generic creation flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from diagnostic_logging import record_soft_exception

DIARY_CREATION_WIZARD_LOCK_VERSION = "v1.0"


@dataclass(frozen=True)
class DiaryWizardReview:
    patient_name: str
    admission_date: str
    discharge_date: str
    template_files: tuple[str, ...]
    text_files: tuple[str, ...]
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
            "Шаблоны дат:",
        ]
        lines.extend([f"  • {name}" for name in self.template_files] or ["  ⚠ не выбраны"])
        lines.append("Тексты дневников:")
        lines.extend([f"  • {name}" for name in self.text_files] or ["  ⚠ не выбраны"])
        if self.warnings:
            lines.append("")
            lines.append("Что надо исправить:")
            lines.extend([f"  ⚠ {item}" for item in self.warnings])
        else:
            lines.append("")
            lines.append("✅ Дневники готовы к созданию.")
        return "\n".join(lines)


def build_diary_wizard_review(app: object) -> DiaryWizardReview:
    """Build a deterministic review from the current UI/app state."""

    def _get_var(name: str) -> str:
        try:
            var = getattr(app, name)
            return str(var.get() or "").strip()
        except Exception as exc:
            record_soft_exception("diary_creation_wizard.get_var", exc, detail=name)
            return ""

    patient = _get_var("patient_name_var")
    admission = _get_var("admission_date_var")
    discharge = _get_var("discharge_date_var")
    templates = tuple(Path(item).name for item in getattr(app, "diary_files", []) or [])
    texts = tuple(Path(item).name for item in getattr(app, "status_files", []) or [])
    if not templates and getattr(app, "diary_template_dir", ""):
        templates = (f"папка: {Path(str(getattr(app, 'diary_template_dir'))).name}",)
    if not texts and getattr(app, "diary_texts_dir", ""):
        texts = (f"папка: {Path(str(getattr(app, 'diary_texts_dir'))).name}",)
    warnings: list[str] = []
    if not patient:
        warnings.append("Введите ФИО пациента или загрузите первичный документ с ФИО.")
    if not admission:
        warnings.append("Не найдена дата госпитализации; дневники не знают, с какой даты начать таблицу.")
    if not discharge:
        warnings.append("Не указана дата выписки; программа не знает, на какой строке закончить дневники.")
    if not templates:
        warnings.append("Выберите папку/шаблон дат дневников через кнопку «Даты».")
    if not texts:
        warnings.append("Выберите тексты дневников через кнопку «Тексты» или настройте автоподбор по диагнозу.")
    return DiaryWizardReview(patient, admission, discharge, templates, texts, tuple(warnings))


def confirm_diary_creation(app: object) -> bool:
    """Show a diary-only confirmation window; return True when creation may continue."""

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
    if DIARY_CREATION_WIZARD_LOCK_VERSION != "v1.0":
        raise AssertionError("Diary creation wizard lock changed unexpectedly")
    empty = type("Empty", (), {})()
    review = build_diary_wizard_review(empty)
    if review.ok or "МАСТЕР ДНЕВНИКОВ" not in review.as_text():
        raise AssertionError("Diary wizard must block incomplete diary state")
