from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app_config import (
    ACCENT,
    ACCENT_2,
    DEEP,
    FIELD,
    FIELD_BORDER,
    MUTED,
    PANEL,
    PANEL_3,
    TEXT,
)
from diagnostic_logging import record_soft_exception
from i18n_strings import tr
from medical_language_catalog import language_choices, language_id_from_choice, language_profile
from medical_formatting import parse_date
from icd10_f_search import normalize_required_diagnosis_with_icd10
from medical_text_utils import sanitize_case_number_candidate
from dialog_fields_popup import DialogDiagnosisPopup


def _completion_input_signature(item) -> str:
    return f"{getattr(item, 'field_id', '')} {getattr(item, 'label', '')}".lower().replace("ё", "е")


def _attach_completion_diagnosis_popup(app, item, popup, parent, entry, var, bucket: list[DialogDiagnosisPopup]) -> None:
    signature = _completion_input_signature(item)
    if "diagnosis" not in signature and "диагноз" not in signature:
        return
    helper = DialogDiagnosisPopup(
        popup,
        parent,
        language_id=app._diagnosis_language() if hasattr(app, "_diagnosis_language") else "ru",
    )
    helper.attach(entry, var)
    bucket.append(helper)


def _close_completion_popup(popup, helpers: list[DialogDiagnosisPopup]) -> None:
    for helper in helpers:
        try:
            helper.hide()
        except Exception as exc:
            record_soft_exception("window_completion_dialog.diagnosis_hide", exc)
    try:
        popup.grab_release()
    except Exception as exc:
        record_soft_exception("window_completion_dialog.grab_release", exc)
    popup.destroy()


def _completion_field_problem_and_normalized(app, item, raw: str, *, required_mode: bool) -> tuple[str, str]:
    value = str(raw or "").strip()
    label = str(getattr(item, "label", item.field_id) or item.field_id)
    signature = f"{item.field_id} {label}".lower().replace("ё", "е")
    if not value:
        return (f"Заполните поле: {label}" if required_mode else ""), ""
    if "date" in signature or "дата" in signature:
        parsed = parse_date(value)
        if not parsed:
            return f"Проверьте формат даты: {label}", ""
        return "", parsed.strftime("%d.%m.%Y")
    if "diagnosis" in signature or "диагноз" in signature:
        normalized = normalize_required_diagnosis_with_icd10(
            value,
            language_id=app._diagnosis_language() if hasattr(app, "_diagnosis_language") else "ru",
        )
        if not normalized:
            return "Выберите диагноз из МКБ-10 или укажите шифр с буквой класса, например K35 или I10.", ""
        return "", normalized
    if "case_number" in signature or "номер истории" in signature or ("истори" in signature and "болез" in signature):
        patient_name = ""
        try:
            if hasattr(app, "_patient_name_for_case_number_guard"):
                patient_name = str(app._patient_name_for_case_number_guard())
            elif hasattr(app, "patient_name_var"):
                patient_name = app.patient_name_var.get().strip()
        except Exception as exc:
            record_soft_exception("window_completion_dialog.case_patient_guard", exc)
        normalized_case = sanitize_case_number_candidate(value, patient_name=patient_name)
        if not normalized_case:
            return f"Проверьте поле: {label}", ""
        return "", normalized_case
    return "", value


def _store_completion_semantic_dates(app, inputs, values, *, popup, entries) -> bool:
    """Persist doctor-entered semantic dates before the completion popup closes."""
    for item in inputs:
        field_id = item.field_id
        normalized = values.get(field_id, "")
        if not normalized:
            continue
        signature = _completion_input_signature(item)
        is_discharge = field_id in {"discharge.date", "discharge_date"} or ("дата" in signature and "выписк" in signature)
        if is_discharge and hasattr(app, "_store_discharge_date_value"):
            if app._store_discharge_date_value(normalized, parent=popup, source_label="popup дополнения custom-документа"):
                continue
            messagebox.showwarning(
                "Уточнить дату",
                "Дата выписки отличается от уже сохранённой. Подтвердите замену или исправьте поле.",
                parent=popup,
            )
            entry = entries.get(field_id)
            if entry is not None:
                entry.focus_set()
            return False
    return True

def prompt_regulatory_completion_values(app, inputs, *, parent) -> dict[str, str]:
    """Implement the prompt_regulatory_completion_values workflow with validation, UI state updates and diagnostics."""
    self = app
    """Popup with optional fields after doctor clicks «Буду дополнять».

    This window is intentionally gentle: every field is optional, and the
    doctor can close it or save only the values they want. Generation is not
    blocked when values are blank.
    """
    from regulatory_advisory_policy import DECLINE_LABEL
    from regulatory_completion_blocks import COMPLETION_POPUP_TITLE

    if not inputs:
        messagebox.showinfo("Дополнения", "Дополнительных пунктов для заполнения нет.", parent=parent)
        return {}
    required_mode = any("обязатель" in str(getattr(item, "reason", "")).lower() for item in inputs)
    popup = tk.Toplevel(parent)
    popup.title("Не заполнено обязательное поле" if required_mode else COMPLETION_POPUP_TITLE)
    popup.configure(bg=DEEP)
    popup.geometry("760x560")
    popup.grid_columnconfigure(0, weight=1)
    popup.grid_rowconfigure(1, weight=1)
    tk.Label(
        popup,
        text=("Заполните недостающие обязательные поля. Пустыми их оставлять нельзя." if required_mode else "Можно дополнить только то, что действительно нужно. Пустые поля будут проигнорированы."),
        bg=DEEP,
        fg=TEXT,
        font=self._font(12, "bold"),
        padx=self._px(12, 8),
        pady=self._px(10, 6),
        wraplength=self._px(720, 520),
        justify="left",
    ).grid(row=0, column=0, sticky="ew")

    holder = tk.Frame(popup, bg=PANEL, padx=10, pady=10)
    holder.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
    holder.grid_columnconfigure(0, weight=1)
    holder.grid_rowconfigure(0, weight=1)
    canvas = tk.Canvas(holder, bg=PANEL, highlightthickness=0, bd=0)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(holder, command=canvas.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    canvas.configure(yscrollcommand=scrollbar.set)
    form = tk.Frame(canvas, bg=PANEL)
    canvas_window = canvas.create_window((0, 0), window=form, anchor="nw")
    form.grid_columnconfigure(0, weight=1)

    def _resize_form(_event=None):
        try:
            canvas.itemconfigure(canvas_window, width=canvas.winfo_width())
        except Exception as exc:
            record_soft_exception("window_mixin:1059", exc)

    canvas.bind("<Configure>", _resize_form)
    form.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))

    def _on_mousewheel(event) -> None:
        try:
            delta = -1 if getattr(event, "delta", 0) > 0 else 1
            if getattr(event, "num", None) == 4:
                delta = -1
            elif getattr(event, "num", None) == 5:
                delta = 1
            canvas.yview_scroll(delta, "units")
        except Exception as exc:
            record_soft_exception("window_completion_dialog.mousewheel", exc)

    for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        popup.bind(sequence, _on_mousewheel)

    variables: dict[str, tk.StringVar] = {}
    entries: dict[str, tk.Entry] = {}
    diagnosis_popups: list[DialogDiagnosisPopup] = []
    for row, item in enumerate(inputs):
        card = tk.Frame(form, bg=FIELD, padx=9, pady=7, highlightbackground=FIELD_BORDER, highlightthickness=1)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        card.grid_columnconfigure(0, weight=1)
        label_text = f"{item.label}  {item.placeholder}"
        tk.Label(card, text=label_text, bg=FIELD, fg=ACCENT, font=self._font(9, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        if item.reason:
            tk.Label(card, text=item.reason, bg=FIELD, fg=MUTED, font=self._font(8), anchor="w", wraplength=self._px(660, 460), justify="left").grid(row=1, column=0, sticky="ew", pady=(2, 5))
        var = tk.StringVar(value=item.initial_value)
        variables[item.field_id] = var
        entry = tk.Entry(card, textvariable=var, bg=DEEP, fg=TEXT, insertbackground=ACCENT, relief="flat", font=self._font(10))
        entry.grid(row=2, column=0, sticky="ew", ipady=4)
        entries[item.field_id] = entry
        _attach_completion_diagnosis_popup(self, item, popup, parent, entry, var, diagnosis_popups)

    result: dict[str, str] = {}

    def close_popup() -> None:
        _close_completion_popup(popup, diagnosis_popups)

    buttons = tk.Frame(popup, bg=DEEP)
    buttons.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
    buttons.grid_columnconfigure(0, weight=1)
    buttons.grid_columnconfigure(1, weight=1)

    def save_values() -> None:
        values: dict[str, str] = {}
        problems: list[str] = []
        first_problem_field = ""
        for item in inputs:
            field_id = item.field_id
            raw = variables[field_id].get().strip() if field_id in variables else ""
            problem, normalized = _completion_field_problem_and_normalized(self, item, raw, required_mode=required_mode)
            if problem:
                problems.append(problem)
                first_problem_field = first_problem_field or field_id
            elif normalized:
                values[field_id] = normalized
        if problems:
            messagebox.showwarning(
                "Не заполнено обязательное поле" if required_mode else "Проверьте поле",
                "\n".join("- " + item for item in problems[:8]) + ("" if len(problems) <= 8 else "\n…"),
                parent=popup,
            )
            entry = entries.get(first_problem_field)
            if entry is not None:
                entry.focus_set()
                try:
                    entry.selection_range(0, tk.END)
                except tk.TclError as exc:
                    record_soft_exception("window_completion_dialog.selection", exc)
            return
        if not _store_completion_semantic_dates(self, inputs, values, popup=popup, entries=entries):
            return
        result.update(values)
        close_popup()

    def decline_values() -> None:
        result.clear()
        close_popup()

    tk.Button(
        buttons,
        text="Сохранить введённые дополнения",
        command=save_values,
        bg=ACCENT_2,
        fg="#03101f",
        activebackground="#18a8dd",
        activeforeground="#03101f",
        relief="flat",
        font=self._font(9, "bold"),
        cursor="hand2",
        padx=10,
        pady=8,
    ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    tk.Button(
        buttons,
        text=("Отмена" if required_mode else DECLINE_LABEL),
        command=decline_values,
        bg=FIELD,
        fg=TEXT,
        activebackground=PANEL_3,
        activeforeground=TEXT,
        relief="flat",
        font=self._font(9, "bold"),
        cursor="hand2",
        padx=10,
        pady=8,
    ).grid(row=0, column=1, sticky="ew", padx=(6, 0))
    popup.protocol("WM_DELETE_WINDOW", close_popup)
    popup.transient(parent)
    popup.grab_set()
    parent.wait_window(popup)
    return result
