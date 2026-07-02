from __future__ import annotations

import inspect
import re
import tkinter as tk
from pathlib import Path  # noqa: F401 - kept for historical external imports/gates
from types import SimpleNamespace
from tkinter import filedialog, messagebox, simpledialog, ttk

from app_config import ACCENT, ACCENT_2, ERROR, FIELD, FIELD_BORDER, MUTED, PANEL, PANEL_3, TEXT
from dialog_fields_linking import attach_linked_field_mirroring
from diagnostic_logging import record_soft_exception
from medical_formatting import parse_date
from medical_date_state import current_semantic_date, semantic_date_key_from_prompt  # noqa: F401 - current_semantic_date kept for compatibility gates
from medical_text_utils import sanitize_case_number_candidate
from medical_parser_sanitize import sanitize_diagnosis
from icd10_f_search import normalize_required_diagnosis_with_icd10
from dialog_fields_popup import DialogDiagnosisPopup
from printer_platform import open_desktop_path  # noqa: F401 - architecture contract: UI opens paths through platform helper



def call_prompt_fields_compatible(
    owner,
    *,
    title: str,
    rows: list[tuple[str, str]],
    width: int = 28,
    linked_groups: list[tuple[int, list[int]]] | None = None,
    include_labs_block: bool = False,
    date_field_keys: list[str | None] | None = None,
) -> list[str] | None:
    """Call ``owner._prompt_fields`` without letting optional UI kwargs break old fakes."""
    prompt = getattr(owner, "_prompt_fields")
    kwargs = {
        "title": title,
        "rows": rows,
        "width": width,
        "linked_groups": linked_groups,
        "include_labs_block": include_labs_block,
        "date_field_keys": date_field_keys,
    }
    return prompt(**_filter_prompt_fields_kwargs(prompt, kwargs))


def _filter_prompt_fields_kwargs(prompt, kwargs: dict) -> dict:
    try:
        signature = inspect.signature(prompt)
    except (TypeError, ValueError):
        return dict(kwargs)
    parameters = signature.parameters
    if any(param.kind is inspect.Parameter.VAR_KEYWORD for param in parameters.values()):
        return dict(kwargs)
    accepted = {
        name
        for name, param in parameters.items()
        if param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    required = {"title", "rows"}
    return {key: value for key, value in kwargs.items() if key in required or key in accepted}


def prompt_fields_dialog(
    self,
    *,
    title: str,
    rows: list[tuple[str, str]],
    width: int = 28,
    linked_groups: list[tuple[int, list[int]]] | None = None,
    include_labs_block: bool = False,
    date_field_keys: list[str | None] | None = None,
) -> list[str] | None:
    win = tk.Toplevel(self.root)
    win.title(title)
    win.configure(bg=PANEL)
    win.resizable(True, True)
    win.minsize(560, 320)
    win.geometry(_prompt_geometry(len(rows), include_labs_block=include_labs_block))
    win.transient(self.root)
    win.grab_set()

    result: list[str] | None = None
    entries: list[tk.Entry] = []
    entry_vars: list[tk.StringVar] = []
    entry_auto_values: list[str] = []
    diagnosis_popup = DialogDiagnosisPopup(
        win,
        self.root,
        language_id=str(getattr(self, "_diagnosis_language", lambda: self.ui_language_var.get() if hasattr(self, "ui_language_var") else "ru")()),
    )

    body, footer, wheel = _build_scrollable_prompt_body(win, title)
    for idx, (label, initial) in enumerate(rows, start=1):
        entry, var = _build_field_row(self, body, idx, label, initial, width)
        if diagnosis_popup.is_diagnosis_label(label):
            diagnosis_popup.attach(entry, var)
        entry.bind("<MouseWheel>", wheel, add="+")
        entries.append(entry)
        entry_vars.append(var)
        entry_auto_values.append(initial)
    body.grid_columnconfigure(1, weight=1)

    labs_rows = 0
    if include_labs_block:
        try:
            labs_rows = build_labs_popup_block(self, body, row=len(rows) + 1, columnspan=2, parent=win)
        except Exception as exc:
            record_soft_exception("dialog_fields_core.labs_popup_block", exc)
            labs_rows = 0

    try:
        attach_additional_info_buttons(self, win, body, row=len(rows) + 1 + labs_rows, columnspan=2)
    except Exception as exc:
        record_soft_exception("dialog_fields_core.additional_info_block", exc)

    attach_linked_field_mirroring(entry_vars, entry_auto_values, linked_groups)
    error_label = tk.Label(footer, text="", bg=PANEL, fg=ERROR, font=("Segoe UI", 8))
    error_label.grid(row=0, column=0, sticky="w", pady=(0, 4))
    buttons = _build_buttons_frame(footer, 1)

    def validate_and_normalize(label: str, value: str) -> tuple[str | None, str]:
        label_l = (label or "").strip().lower().replace("ё", "е")
        value = (value or "").strip()
        if not value:
            return None, f"Заполните поле: {label}"
        if any(marker in label_l for marker in ("дата", "data", "urodzenia", "przyjęcia", "przyjecia", "wypisu", "hospitalizacji")):
            parsed = parse_date(value)
            if not parsed:
                return None, f"Проверьте формат даты: {label}"
            normalized_date = parsed.strftime("%d.%m.%Y")
            semantic_key = semantic_date_key_from_prompt(title, label)
            if semantic_key != "admission_date" and hasattr(self, "_date_is_not_before_admission"):
                try:
                    if not self._date_is_not_before_admission(normalized_date):
                        return None, f"{label} не может быть раньше даты поступления."
                except Exception as exc:
                    record_soft_exception("dialog_fields_core.date_episode_validation", exc, detail=f"{label}: {value}")
            return normalized_date, ""
        if any(marker in label_l for marker in ("диагноз", "мкб", "icd", "mkb", "rozpoznanie", "diagnoza", "kod rozpoznania")):
            sanitized = sanitize_diagnosis(value)
            compact = re.sub(r"\s+", "", sanitized.replace(",", "."))
            if re.fullmatch(r"\d{1,4}(?:\.\d+)?", compact):
                return None, "Укажите диагноз текстом или полный шифр МКБ-10 с буквой класса, например K35 или I10."
            normalized = normalize_required_diagnosis_with_icd10(sanitized, language_id=getattr(self, "_diagnosis_language", lambda: "ru")())
            return (normalized or None), "" if normalized else "Выберите диагноз из МКБ-10 или укажите шифр с буквой класса, например K35 или I10."
        if (
            "номер истории" in label_l
            or ("истори" in label_l and "болез" in label_l)
            or ("histori" in label_l and "chorob" in label_l)
            or "nr dokumentacji" in label_l
            or "numer dokumentacji" in label_l
            or "nr karty" in label_l
        ):
            patient_name = ""
            try:
                patient_name = str(self._patient_name_for_case_number_guard()) if hasattr(self, "_patient_name_for_case_number_guard") else self.patient_name_var.get().strip()
            except Exception as exc:
                record_soft_exception("dialog_fields_core.case_patient_name", exc)
            normalized_case = sanitize_case_number_candidate(value, patient_name=patient_name)
            return (normalized_case or None), "" if normalized_case else f"Проверьте поле: {label}"
        return value, ""

    def close_dialog() -> None:
        try:
            win.grab_release()
        except tk.TclError as exc:
            record_soft_exception("dialog_fields_core.prompt_grab_release", exc)
        try:
            diagnosis_popup.hide()
        except Exception as exc:
            record_soft_exception("dialog_fields_core.prompt_diagnosis_hide", exc)
        try:
            win.withdraw()
        except tk.TclError as exc:
            record_soft_exception("dialog_fields_core.prompt_withdraw", exc)
        win.destroy()

    def ok() -> None:
        nonlocal result
        values: list[str] = []
        for entry, (label, _initial) in zip(entries, rows):
            normalized, problem = validate_and_normalize(label, entry.get().strip())
            if normalized is None:
                error_label.config(text=problem or f"Проверьте поле: {label}")
                entry.focus_set()
                try:
                    entry.selection_range(0, tk.END)
                except tk.TclError as exc:
                    record_soft_exception("dialog_fields_core.validation_selection", exc)
                return
            values.append(normalized)
        if include_labs_block and all(hasattr(self, name) for name in ("labs_text_var", "labs_without_var")):
            try:
                labs_ready = bool(self.labs_without_var.get()) or bool(self.labs_text_var.get().strip())
            except Exception as exc:
                record_soft_exception("dialog_fields_core.labs_required_state", exc)
                labs_ready = True
            if not labs_ready:
                error_label.config(text="Выберите вариант по анализам: нет анализов, вставить/ввести, сканер или загрузить файл.")
                return
        for idx, ((label, _initial), normalized_value) in enumerate(zip(rows, values)):
            explicit_key = date_field_keys[idx] if date_field_keys is not None and idx < len(date_field_keys) else None
            semantic_key = explicit_key or semantic_date_key_from_prompt(title, label)
            if semantic_key and hasattr(self, "_store_popup_date_value"):
                if not self._store_popup_date_value(semantic_key, normalized_value, parent=win, source_label=title):
                    error_label.config(text=f"{label}: дата отличается от уже сохранённой или выходит за период лечения. Подтвердите замену или исправьте поле.")
                    try:
                        entries[idx].focus_set()
                        entries[idx].selection_range(0, tk.END)
                    except tk.TclError as exc:
                        record_soft_exception("dialog_fields_core.semantic_date_conflict_focus", exc)
                    return
        result = values
        close_dialog()

    _build_action_buttons(buttons, ok, close_dialog)
    if entries:
        entries[0].focus_set()
    win.bind("<Return>", lambda _event: ok())
    win.bind("<Escape>", lambda _event: close_dialog())
    win.protocol("WM_DELETE_WINDOW", close_dialog)
    self.root.wait_window(win)
    return result


def _prompt_geometry(row_count: int, *, include_labs_block: bool = False) -> str:
    height = 220 + max(0, row_count) * 48 + (150 if include_labs_block else 0)
    height = max(360, min(760, height))
    width = 780 if row_count >= 4 or include_labs_block else 640
    return f"{width}x{height}"


def _build_scrollable_prompt_body(win: tk.Toplevel, title: str) -> tuple[tk.Frame, tk.Frame, object]:
    outer = tk.Frame(win, bg=PANEL, padx=18, pady=16)
    outer.pack(fill="both", expand=True)
    outer.grid_columnconfigure(0, weight=1)
    outer.grid_rowconfigure(1, weight=1)
    tk.Label(outer, text=title, bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
    canvas = tk.Canvas(outer, bg=PANEL, highlightthickness=0, borderwidth=0)
    scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=1, column=0, sticky="nsew")
    scrollbar.grid(row=1, column=1, sticky="ns")
    body = tk.Frame(canvas, bg=PANEL)
    body_id = canvas.create_window((0, 0), window=body, anchor="nw")

    def sync_scroll_region(_event=None) -> None:
        try:
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(body_id, width=canvas.winfo_width())
        except tk.TclError as exc:
            record_soft_exception("dialog_fields_core.scroll_region", exc)

    def wheel(event) -> None:
        try:
            delta = -1 if getattr(event, "delta", 0) > 0 else 1
            if getattr(event, "num", None) == 4:
                delta = -1
            elif getattr(event, "num", None) == 5:
                delta = 1
            canvas.yview_scroll(delta, "units")
        except tk.TclError as exc:
            record_soft_exception("dialog_fields_core.scroll_wheel", exc)

    body.bind("<Configure>", sync_scroll_region)
    canvas.bind("<Configure>", sync_scroll_region)
    canvas.bind("<MouseWheel>", wheel)
    body.bind("<MouseWheel>", wheel)
    footer = tk.Frame(outer, bg=PANEL)
    footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    footer.grid_columnconfigure(0, weight=1)
    return body, footer, wheel


def _build_field_row(app, body: tk.Frame, idx: int, label: str, initial: str, width: int) -> tuple[tk.Entry, tk.StringVar]:
    tk.Label(body, text=label, bg=PANEL, fg=TEXT, font=("Segoe UI", 8)).grid(row=idx, column=0, sticky="w", pady=6)
    var = tk.StringVar(value=initial)
    entry = tk.Entry(body, textvariable=var, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat", width=width, font=("Segoe UI", 8), highlightbackground=FIELD_BORDER, highlightcolor=ACCENT, highlightthickness=1)
    entry.grid(row=idx, column=1, sticky="ew", padx=(12, 0), ipady=6, pady=6)
    entry.bind("<Control-KeyPress>", app._entry_control_shortcut, add="+")
    return entry, var


def _build_buttons_frame(body: tk.Frame, row: int) -> tk.Frame:
    buttons = tk.Frame(body, bg=PANEL)
    buttons.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(14, 0))
    buttons.grid_columnconfigure(0, weight=1)
    return buttons


def _build_action_buttons(buttons: tk.Frame, ok, cancel) -> None:
    tk.Button(buttons, text="ОК", command=ok, bg=ACCENT_2, fg="#03101f", relief="flat", padx=18, pady=8, font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="e", padx=(0, 8))
    tk.Button(buttons, text="Отмена", command=cancel, bg=PANEL_3, fg=TEXT, relief="flat", padx=18, pady=8, font=("Segoe UI", 8)).grid(row=0, column=1, sticky="e")


def build_labs_popup_block(app, body: tk.Frame, *, row: int, columnspan: int, parent: tk.Toplevel) -> int:
    if not all(hasattr(app, name) for name in ("labs_text_var", "labs_without_var", "labs_date_policy_var")):
        return 0
    frame = tk.Frame(body, bg=PANEL_3, padx=10, pady=8)
    frame.grid(row=row, column=0, columnspan=columnspan, sticky="ew", pady=(10, 4))
    for col in range(5):
        frame.grid_columnconfigure(col, weight=1)
    tk.Label(frame, text="Анализы — просто выберите один вариант", bg=PANEL_3, fg=TEXT, font=("Segoe UI", 9, "bold"), anchor="w").grid(row=0, column=0, columnspan=5, sticky="ew", pady=(0, 6))

    def no_labs() -> None:
        app.labs_without_var.set(True)
        app.labs_text_var.set("")
        app.labs_source_path_var.set("")
        app.labs_date_policy_var.set("without_labs")

    def load_labs() -> None:
        path = filedialog.askopenfilename(title="Выберите файл с анализами", filetypes=[("Word/Text/PDF", "*.doc *.docx *.docm *.txt *.pdf"), ("All files", "*.*")], parent=parent)
        if not path:
            return
        try:
            from medical_labs_loader import load_labs_text
            loaded = load_labs_text(path)
            app.labs_text_var.set(loaded.text)
            app.labs_source_path_var.set(str(path))
            app.labs_without_var.set(False)
            app.labs_date_policy_var.set("preserve_found_dates")
        except Exception as exc:
            record_soft_exception("dialog_fields_core.load_labs", exc, detail=str(path))
            messagebox.showwarning("Анализы", f"Не удалось прочитать анализы:\n{exc}", parent=parent)

    tk.Button(frame, text="Нет анализов", command=no_labs, bg=FIELD, fg=TEXT, relief="flat", padx=8, pady=6).grid(row=1, column=0, sticky="ew", padx=(0, 6))
    tk.Button(frame, text="Вставить / ввести", command=lambda: _prompt_manual_labs(app, parent), bg=FIELD, fg=TEXT, relief="flat", padx=8, pady=6).grid(row=1, column=1, sticky="ew", padx=(0, 6))
    tk.Button(frame, text="Файл", command=load_labs, bg=FIELD, fg=TEXT, relief="flat", padx=8, pady=6).grid(row=1, column=2, sticky="ew", padx=(0, 6))
    tk.Button(frame, text="Сканер мышкой", command=lambda: open_labs_selection_scanner(app, parent), bg=FIELD, fg=TEXT, relief="flat", padx=8, pady=6).grid(row=1, column=3, sticky="ew", padx=(0, 6))
    tk.Label(frame, textvariable=app.labs_source_path_var, bg=PANEL_3, fg=MUTED, font=("Segoe UI", 8), anchor="w").grid(row=2, column=0, columnspan=5, sticky="ew", pady=(6, 0))
    return 3


def open_labs_selection_scanner(app, parent) -> None:
    try:
        from medical_mouse_scanner import capture_labs_with_mouse, capture_text_with_mouse
    except Exception as exc:
        record_soft_exception("dialog_fields_core.import_labs_scanner", exc)
        messagebox.showwarning("Сканер мышкой", f"Не удалось запустить сканер:\n{exc}", parent=parent)
        return
    try:
        scan = capture_labs_with_mouse(parent=parent)
    except Exception:
        try:
            text = capture_text_with_mouse(parent=parent)
            scan = SimpleNamespace(blocks=[text.strip()] if str(text or "").strip() else [])
        except Exception as exc:
            record_soft_exception("dialog_fields_core.scan_labs", exc)
            messagebox.showwarning("Сканер мышкой", f"Не удалось получить текст анализов:\n{exc}", parent=parent)
            return
    if not scan.blocks:
        messagebox.showwarning("Сканер мышкой", "Выделенный текст анализов не найден. Попробуйте ещё раз или вставьте текст вручную.", parent=parent)
        return
    win = tk.Toplevel(parent)
    win.withdraw()
    try:
        text = "\n".join(str(block).strip() for block in scan.blocks if str(block).strip()).strip()
        app.labs_text_var.set(text)
        app.labs_source_path_var.set("mouse_scanner")
        app.labs_without_var.set(False)
        app.labs_date_policy_var.set("preserve_found_dates")
    finally:
        win.destroy()


def _prompt_manual_labs(app, parent) -> None:
    value = simpledialog.askstring("Анализы", "Вставьте или введите текст анализов:", parent=parent)
    if value:
        app.labs_text_var.set(value.strip())
        app.labs_source_path_var.set("manual")
        app.labs_without_var.set(False)
        app.labs_date_policy_var.set("preserve_found_dates")


def attach_additional_info_buttons(app, parent, body: tk.Frame, *, row: int, columnspan: int = 2) -> int:
    if not hasattr(app, "additional_info_text_var"):
        return 0
    frame = tk.Frame(body, bg=PANEL_3, padx=10, pady=8)
    frame.grid(row=row, column=0, columnspan=columnspan, sticky="ew", pady=(10, 4))
    frame.grid_columnconfigure(1, weight=1)
    tk.Label(frame, text="Доп. информация / рекомендации", bg=PANEL_3, fg=TEXT, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

    def paste_info() -> None:
        value = simpledialog.askstring("Доп. информация", "Введите текст:", parent=parent)
        if value:
            app.additional_info_text_var.set(value.strip())
            app.additional_info_source_path_var.set("manual")

    def load_info() -> None:
        path = filedialog.askopenfilename(title="Выберите файл с дополнительной информацией", filetypes=[("Word/Text/PDF", "*.doc *.docx *.docm *.txt *.pdf"), ("All files", "*.*")], parent=parent)
        if not path:
            return
        try:
            from medical_labs_loader import load_labs_text
            loaded = load_labs_text(path)
            app.additional_info_text_var.set(loaded.text)
            app.additional_info_source_path_var.set(str(path))
        except Exception as exc:
            record_soft_exception("dialog_fields_core.load_additional_info", exc, detail=str(path))
            messagebox.showwarning("Доп. информация", f"Не удалось прочитать файл:\n{exc}", parent=parent)

    tk.Button(frame, text="Ввести", command=paste_info, bg=FIELD, fg=TEXT, relief="flat", padx=8, pady=6).grid(row=1, column=0, sticky="ew", padx=(0, 6))
    tk.Button(frame, text="Файл", command=load_info, bg=FIELD, fg=TEXT, relief="flat", padx=8, pady=6).grid(row=1, column=1, sticky="ew", padx=(0, 6))
    tk.Label(frame, textvariable=app.additional_info_source_path_var, bg=PANEL_3, fg=MUTED, font=("Segoe UI", 8), anchor="w").grid(row=2, column=0, columnspan=3, sticky="ew", pady=(6, 0))
    return 3


def choose_epi_file_for_app(app, *, parent=None) -> bool:
    path = filedialog.askopenfilename(title="Выберите файл ЭПИ", filetypes=[("Word DOC/DOCX/DOCM", "*.doc *.docx *.docm"), ("Text", "*.txt"), ("All files", "*.*")], parent=parent)
    if not path:
        return False
    try:
        app.epi_path_var.set(path)
        return True
    except Exception as exc:
        record_soft_exception("dialog_fields_core.choose_epi", exc, detail=str(path))
        return False
