from __future__ import annotations

import inspect
import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app_config import ACCENT, ACCENT_2, ERROR, FIELD, FIELD_BORDER, MUTED, PANEL, PANEL_3, TEXT
from dialog_fields_linking import attach_linked_field_mirroring
from diagnostic_logging import record_soft_exception
from medical_formatting import parse_date
from medical_date_state import current_semantic_date, semantic_date_key_from_prompt
from medical_text_utils import sanitize_case_number_candidate
from medical_parser_sanitize import sanitize_diagnosis
from icd10_f_search import normalize_required_diagnosis_with_icd10
from dialog_fields_popup import DialogDiagnosisPopup



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
    """Call ``owner._prompt_fields`` without letting optional UI kwargs break old fakes.

    Runtime uses :class:`DialogFieldsMixin`, which supports all parameters.
    A lot of smoke/acceptance objects intentionally monkeypatch ``_prompt_fields``
    with tiny lambdas that only accept the fields they check.  New popup features
    must not break those harnesses, and old external overrides should continue to
    work: unsupported optional parameters are dropped by signature, not by fragile
    one-off ``try/except TypeError`` blocks in each dialog.
    """

    prompt = getattr(owner, "_prompt_fields")
    kwargs = {
        "title": title,
        "rows": rows,
        "width": width,
        "linked_groups": linked_groups,
        "include_labs_block": include_labs_block,
        "date_field_keys": date_field_keys,
    }
    supported = _filter_prompt_fields_kwargs(prompt, kwargs)
    return prompt(**supported)


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
    result = {key: value for key, value in kwargs.items() if key in required or key in accepted}
    # ``title`` and ``rows`` are the stable prompt contract.  If an override is
    # so old that it does not advertise them, let Python raise a clear error
    # rather than silently opening a wrong popup.
    return result


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
    """Implement the prompt_fields_dialog workflow with validation, UI state updates and diagnostics."""
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
    diagnosis_popup = DialogDiagnosisPopup(win, self.root, language_id=(self.ui_language_var.get() if hasattr(self, "ui_language_var") else "ru"))

    body, footer, _wheel = _build_scrollable_prompt_body(win, title)

    for idx, (label, initial) in enumerate(rows, start=1):
        entry, var = _build_field_row(self, body, idx, label, initial, width)
        if diagnosis_popup.is_diagnosis_label(label):
            diagnosis_popup.attach(entry, var)
        entry.bind("<MouseWheel>", _wheel, add="+")
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

    def _validate_and_normalize(label: str, value: str) -> tuple[str | None, str]:
        label_l = (label or "").strip().lower().replace("ё", "е")
        value = (value or "").strip()
        if not value:
            return None, f"Заполните поле: {label}"
        if "дата" in label_l:
            parsed = parse_date(value)
            if not parsed:
                return None, f"Проверьте формат даты: {label}"
            normalized_date = parsed.strftime("%d.%m.%Y")
            if hasattr(self, "_date_is_not_before_admission"):
                try:
                    if not self._date_is_not_before_admission(normalized_date):
                        return None, f"{label} не может быть раньше даты поступления."
                except Exception as exc:
                    record_soft_exception("dialog_fields_core.date_episode_validation", exc, detail=f"{label}: {value}")
            return normalized_date, ""
        if "диагноз" in label_l:
            sanitized = sanitize_diagnosis(value)
            compact = re.sub(r"\s+", "", sanitized.replace(",", "."))
            if re.fullmatch(r"\d{1,4}(?:\.\d+)?", compact):
                return None, "Укажите диагноз текстом или полный шифр МКБ-10 с буквой класса, например K35 или I10."
            normalized = normalize_required_diagnosis_with_icd10(sanitized, language_id=getattr(self, "_diagnosis_language", lambda: "ru")())
            return (normalized or None), "" if normalized else "Выберите диагноз из МКБ-10 или укажите шифр с буквой класса, например K35 или I10."
        if "номер истории" in label_l or "истори" in label_l and "болез" in label_l:
            patient_name = ""
            try:
                if hasattr(self, "_patient_name_for_case_number_guard"):
                    patient_name = str(self._patient_name_for_case_number_guard())
                elif hasattr(self, "patient_name_var"):
                    patient_name = self.patient_name_var.get().strip()
            except Exception as exc:
                record_soft_exception("dialog_fields_core.case_patient_name", exc)
                patient_name = ""
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
            raw = entry.get().strip()
            normalized, problem = _validate_and_normalize(label, raw)
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
        # Popup dates are patient-level semantic values. Store them before
        # closing so conflicting values are clarified inside the same window.
        for idx, ((label, _initial), normalized_value) in enumerate(zip(rows, values)):
            explicit_key = None
            if date_field_keys is not None and idx < len(date_field_keys):
                explicit_key = date_field_keys[idx]
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

    def cancel() -> None:
        close_dialog()

    _build_action_buttons(buttons, ok, cancel)
    if entries:
        entries[0].focus_set()
    win.bind("<Return>", lambda _event: ok())
    win.bind("<Escape>", lambda _event: cancel())
    win.protocol("WM_DELETE_WINDOW", cancel)
    self.root.wait_window(win)
    return result


def _prompt_geometry(row_count: int, *, include_labs_block: bool = False) -> str:
    """Choose a safe popup size so buttons remain visible on small screens."""
    height = 220 + max(0, row_count) * 48 + (150 if include_labs_block else 0)
    height = max(360, min(760, height))
    width = 780 if row_count >= 4 or include_labs_block else 640
    return f"{width}x{height}"


def _build_scrollable_prompt_body(win: tk.Toplevel, title: str) -> tuple[tk.Frame, tk.Frame, object]:
    """Build a popup body whose fields scroll while errors/buttons stay visible."""

    outer = tk.Frame(win, bg=PANEL, padx=18, pady=16)
    outer.pack(fill="both", expand=True)
    outer.grid_columnconfigure(0, weight=1)
    outer.grid_rowconfigure(1, weight=1)
    tk.Label(outer, text=title, bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
    )
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


def _build_field_row(
    app,
    body: tk.Frame,
    idx: int,
    label: str,
    initial: str,
    width: int,
) -> tuple[tk.Entry, tk.StringVar]:
    tk.Label(body, text=label, bg=PANEL, fg=TEXT, font=("Segoe UI", 8)).grid(
        row=idx, column=0, sticky="w", pady=6
    )
    var = tk.StringVar(value=initial)
    entry = tk.Entry(
        body,
        textvariable=var,
        bg=FIELD,
        fg=TEXT,
        insertbackground=TEXT,
        relief="flat",
        width=width,
        font=("Segoe UI", 8),
        highlightbackground=FIELD_BORDER,
        highlightcolor=ACCENT,
        highlightthickness=1,
    )
    entry.grid(row=idx, column=1, sticky="ew", padx=(12, 0), ipady=6, pady=6)
    entry.bind("<Control-KeyPress>", app._entry_control_shortcut, add="+")
    return entry, var


def _build_buttons_frame(body: tk.Frame, row: int) -> tk.Frame:
    buttons = tk.Frame(body, bg=PANEL)
    buttons.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(14, 0))
    buttons.grid_columnconfigure(0, weight=1)
    return buttons


def _build_action_buttons(buttons: tk.Frame, ok, cancel) -> None:
    tk.Button(
        buttons,
        text="ОК",
        command=ok,
        bg=ACCENT_2,
        fg="#03101f",
        relief="flat",
        padx=18,
        pady=8,
        font=("Segoe UI", 10, "bold"),
    ).grid(row=0, column=0, sticky="e", padx=(0, 8))
    tk.Button(
        buttons,
        text="Отмена",
        command=cancel,
        bg=PANEL_3,
        fg=TEXT,
        relief="flat",
        padx=18,
        pady=8,
        font=("Segoe UI", 8),
    ).grid(row=0, column=1, sticky="e")


def build_labs_popup_block(app, body: tk.Frame, *, row: int, columnspan: int, parent: tk.Toplevel) -> int:
    """Add a deliberately simple analyses panel to creation popups.

    The old panel offered five different actions at once and confused doctors.
    The production path stays idiot-proof: choose «нет анализов», paste/type,
    load a file, or use one clearly named mouse scanner button.
    """

    if not all(hasattr(app, name) for name in ("labs_text_var", "labs_without_var", "labs_date_policy_var")):
        return 0

    frame = tk.Frame(body, bg=PANEL_3, padx=10, pady=8)
    frame.grid(row=row, column=0, columnspan=columnspan, sticky="ew", pady=(10, 4))
    for col in range(5):
        frame.grid_columnconfigure(col, weight=1)

    tk.Label(frame, text="Анализы — просто выберите один вариант", bg=PANEL_3, fg=TEXT, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", columnspan=5)

    summary_var = tk.StringVar(value=_labs_summary(app))
    summary = tk.Label(frame, textvariable=summary_var, bg=PANEL_3, fg=MUTED, justify="left", wraplength=640, font=("Segoe UI", 8))
    summary.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(2, 8))

    def refresh() -> None:
        summary_var.set(_labs_summary(app))

    def without_labs() -> None:
        app.labs_without_var.set(True)
        app.labs_text_var.set("")
        app.labs_source_path_var.set("")
        try:
            app.labs_explicit_date_var.set("")
            app.labs_date_policy_var.set("without_labs")
        except Exception as exc:
            record_soft_exception("dialog_fields_core.labs_without_clear_date", exc)
        refresh()

    def manual_labs() -> None:
        _prompt_manual_labs(app, parent=parent, refresh=refresh)

    def load_labs() -> None:
        path = filedialog.askopenfilename(
            title="Выберите файл с анализами",
            filetypes=[("Файл анализов", "*.docx *.docm *.txt *.csv"), ("All files", "*.*")],
            parent=parent,
        )
        if not path:
            return
        try:
            from medical_renderer_labs import extract_labs_from_file
            app.labs_date_policy_var.set("auto_from_source_or_document")
            block = extract_labs_from_file(path, date_policy=app.labs_date_policy_var.get(), default_date=_default_labs_date(app))
            app.labs_text_var.set(block.text)
            app.labs_source_path_var.set(block.source)
            app.labs_without_var.set(False)
            refresh()
        except Exception as exc:
            record_soft_exception("dialog_fields_core.load_labs_file", exc, detail=path)
            messagebox.showerror("Файл с анализами", str(exc), parent=parent)

    def scan_labs() -> None:
        open_labs_selection_scanner(app, parent=parent, refresh=refresh)

    def scan_labs_word() -> None:
        try:
            open_external_word_selection_scanner_dialog(
                app,
                default_field_id="labs.results",
                parent=parent,
            )
            refresh()
        except Exception as exc:
            record_soft_exception("dialog_fields_core.labs_word_scanner", exc)
            messagebox.showerror("Сканер Word", str(exc), parent=parent)

    _button(frame, "Нет анализов", without_labs).grid(row=2, column=0, sticky="ew", padx=(0, 4))
    _button(frame, "Вставить / ввести", manual_labs, primary=True).grid(row=2, column=1, sticky="ew", padx=4)
    _button(frame, "Сканер мышкой", scan_labs).grid(row=2, column=2, sticky="ew", padx=4)
    _button(frame, "Сканер Word", scan_labs_word).grid(row=2, column=3, sticky="ew", padx=4)
    _button(frame, "Загрузить файл", load_labs).grid(row=2, column=4, sticky="ew", padx=(4, 0))
    return 1

def open_labs_selection_scanner(app, *, parent: tk.Toplevel, refresh=None) -> None:
    """Implement the open_labs_selection_scanner workflow with validation, UI state updates and diagnostics."""
    path = filedialog.askopenfilename(
        title="Выберите документ, где нужно выделить анализы",
        filetypes=[("Word DOC/DOCX/DOCM", "*.doc *.docx *.docm"), ("All files", "*.*")],
        parent=parent,
    )
    if not path:
        return
    try:
        pack = app._load_or_create_universal_pack()
        from universal_scanner import learn_rule_from_selection, scan_docx
        scan = scan_docx(path, registry=pack.registry(), rules=pack.extraction_rules)
    except Exception as exc:
        messagebox.showerror("Сканер анализов", f"Не удалось разобрать документ:\n\n{exc}", parent=parent)
        return

    if not scan.blocks:
        messagebox.showwarning("Сканер анализов", "В документе не найден текст для выделения. Откройте другой файл или используйте ввод вручную.", parent=parent)
        return

    win = tk.Toplevel(parent)
    win.title("Сканер анализов — выделите нужный блок")
    win.configure(bg=PANEL)
    win.geometry("860x560")
    win.grid_columnconfigure(0, weight=1)
    win.grid_rowconfigure(1, weight=1)

    tk.Label(
        win,
        text="Выделите мышкой блок с анализами. Программа сохранит текст для текущего документа и правило для будущих документов профиля.",
        bg=PANEL,
        fg=TEXT,
        font=("Segoe UI", 10, "bold"),
        justify="left",
        wraplength=820,
        padx=12,
        pady=10,
    ).grid(row=0, column=0, sticky="ew")

    text = tk.Text(win, bg=FIELD, fg=TEXT, selectbackground=ACCENT, selectforeground="#03101f", wrap="word", relief="flat", padx=10, pady=10)
    text.grid(row=1, column=0, sticky="nsew", padx=12)
    scroll = tk.Scrollbar(win, command=text.yview)
    scroll.grid(row=1, column=1, sticky="ns")
    text.configure(yscrollcommand=scroll.set)
    for block in scan.blocks:
        text.insert("end", f"[{block.index:03d}] {block.path_hint}\n", ("header",))
        text.insert("end", block.text + "\n\n")
    text.tag_configure("header", foreground=ACCENT)

    status_var = tk.StringVar(value="Выделите фрагмент и нажмите «Сохранить анализы». Если даты нет, используйте кнопку автодаты в popup.")
    tk.Label(win, textvariable=status_var, bg=PANEL, fg=MUTED, justify="left", wraplength=820).grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 0))

    buttons = tk.Frame(win, bg=PANEL)
    buttons.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=12)
    buttons.grid_columnconfigure(0, weight=1)
    buttons.grid_columnconfigure(1, weight=1)

    def save_selection() -> None:
        try:
            selected = text.get("sel.first", "sel.last").strip()
        except tk.TclError:
            messagebox.showwarning("Нет выделения", "Выделите мышкой блок анализов.", parent=win)
            return
        if not selected:
            messagebox.showwarning("Нет выделения", "Выделите мышкой блок анализов.", parent=win)
            return
        try:
            from medical_renderer_labs import normalize_labs_block
            selected = re.sub(r"(?m)^\[\d{3}\]\s+.*$", "", selected).strip()
            normalized = normalize_labs_block(selected, default_date=_default_labs_date(app), date_policy=app.labs_date_policy_var.get())
            app.labs_text_var.set(normalized)
            app.labs_source_path_var.set(str(Path(path).expanduser()))
            app.labs_without_var.set(False)
            rule = learn_rule_from_selection(scan.blocks, field_id="labs.results", selected_text=selected, registry=pack.registry())
            pack.add_rule(rule)
            from universal_profiles import save_document_pack
            save_document_pack(pack, app._universal_profile_path())
            status_var.set(f"Сохранено: labs.results / {rule.strategy}. Правило записано в профиль врача.")
            if refresh:
                refresh()
            close_scanner()
        except Exception as exc:
            messagebox.showerror("Сканер анализов", str(exc), parent=win)

    def close_scanner() -> None:
        try:
            win.grab_release()
        except tk.TclError as exc:
            record_soft_exception("dialog_fields_core.labs_scanner_grab_release", exc)
        win.destroy()

    _button(buttons, "Сохранить анализы", save_selection, primary=True).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    _button(buttons, "Отмена", close_scanner).grid(row=0, column=1, sticky="ew", padx=(6, 0))
    win.protocol("WM_DELETE_WINDOW", close_scanner)
    win.transient(parent)
    win.grab_set()
    win.focus_set()
    parent.wait_window(win)


def _prompt_manual_labs(app, *, parent: tk.Toplevel, refresh) -> None:
    """Implement the _prompt_manual_labs workflow with validation, UI state updates and diagnostics."""
    win = tk.Toplevel(parent)
    win.title("Ввести анализы")
    win.configure(bg=PANEL)
    win.geometry("760x520")
    win.grid_columnconfigure(0, weight=1)
    win.grid_rowconfigure(1, weight=1)
    tk.Label(
        win,
        text=(
            "1) Скопируйте анализы из Word/лабораторной системы и нажмите «Вставить из буфера».\n"
            "2) Или просто напечатайте/исправьте текст.\n"
            "3) Нажмите «Сохранить анализы». Дату можно оставить пустой — программа подставит дату выписки/сегодня."
        ),
        bg=PANEL,
        fg=TEXT,
        font=("Segoe UI", 10, "bold"),
        justify="left",
        wraplength=720,
        padx=12,
        pady=10,
    ).grid(row=0, column=0, sticky="ew")
    text = tk.Text(win, bg=FIELD, fg=TEXT, insertbackground=TEXT, wrap="word", relief="flat", padx=10, pady=10)
    text.grid(row=1, column=0, sticky="nsew", padx=12)
    text.insert("1.0", app.labs_text_var.get())
    date_row = tk.Frame(win, bg=PANEL)
    date_row.grid(row=2, column=0, sticky="ew", padx=12, pady=(8, 0))
    date_row.grid_columnconfigure(1, weight=1)
    tk.Label(date_row, text="Дата анализов, если нужна", bg=PANEL, fg=MUTED).grid(row=0, column=0, sticky="w", padx=(0, 8))
    date_entry = tk.Entry(date_row, textvariable=app.labs_explicit_date_var, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat")
    date_entry.grid(row=0, column=1, sticky="ew", ipady=5)
    buttons = tk.Frame(win, bg=PANEL)
    buttons.grid(row=3, column=0, sticky="ew", padx=12, pady=12)
    buttons.grid_columnconfigure(0, weight=1)
    buttons.grid_columnconfigure(1, weight=1)

    def paste_from_clipboard() -> None:
        try:
            value = win.clipboard_get().strip()
        except Exception as exc:
            record_soft_exception("dialog_fields_core.labs_clipboard", exc)
            value = ""
        if not value:
            messagebox.showwarning("Буфер пуст", "Сначала скопируйте анализы, затем нажмите «Вставить из буфера».", parent=win)
            return
        text.delete("1.0", "end")
        text.insert("1.0", value)

    def save() -> None:
        try:
            from medical_renderer_labs import normalize_labs_block
            app.labs_date_policy_var.set("auto_from_source_or_document")
            raw_labs = text.get("1.0", "end").strip()
            if not raw_labs:
                messagebox.showwarning("Нет анализов", "Введите текст анализов, вставьте из буфера или выберите «Нет анализов».", parent=win)
                text.focus_set()
                return
            app.labs_text_var.set(
                normalize_labs_block(
                    raw_labs,
                    default_date=_default_labs_date(app),
                    date_policy=app.labs_date_policy_var.get(),
                    explicit_date=current_semantic_date(app, "labs_explicit_date"),
                )
            )
            app.labs_source_path_var.set("ручной ввод")
            app.labs_without_var.set(False)
            refresh()
            close_manual_labs()
        except Exception as exc:
            messagebox.showerror("Ввести анализы", str(exc), parent=win)

    def close_manual_labs() -> None:
        try:
            win.grab_release()
        except tk.TclError as exc:
            record_soft_exception("dialog_fields_core.manual_labs_grab_release", exc)
        try:
            win.withdraw()
        except tk.TclError as exc:
            record_soft_exception("dialog_fields_core.manual_labs_withdraw", exc)
        win.destroy()

    buttons.grid_columnconfigure(2, weight=1)
    _button(buttons, "Вставить из буфера", paste_from_clipboard).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    _button(buttons, "Сохранить анализы", save, primary=True).grid(row=0, column=1, sticky="ew", padx=6)
    _button(buttons, "Отмена", close_manual_labs).grid(row=0, column=2, sticky="ew", padx=(6, 0))
    win.protocol("WM_DELETE_WINDOW", close_manual_labs)
    win.bind("<Escape>", lambda _event: close_manual_labs())
    win.transient(parent)
    win.grab_set()
    text.focus_set()
    parent.wait_window(win)


def _button(parent: tk.Misc, text: str, command, *, primary: bool = False) -> tk.Button:
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg=ACCENT_2 if primary else FIELD,
        fg="#03101f" if primary else TEXT,
        activebackground=ACCENT if primary else PANEL_3,
        activeforeground="#03101f" if primary else TEXT,
        relief="flat",
        font=("Segoe UI", 8 if not primary else 9, "bold"),
        cursor="hand2",
        padx=8,
        pady=6,
        wraplength=180,
    )


def _labs_summary(app) -> str:
    if bool(app.labs_without_var.get()):
        return "Выбрано: без анализов. В документы блок анализов не вставляется."
    text = app.labs_text_var.get().strip()
    if not text:
        return "Анализы не добавлены. Выберите: нет анализов, вставить/ввести, сканер мышкой, сканер Word или загрузить файл."
    source = app.labs_source_path_var.get().strip()
    first = " ".join(text.split())[:140]
    source_text = f" Источник: {Path(source).name if source and source != 'ручной ввод' else source}." if source else ""
    return f"Добавлено: {first}{'…' if len(text) > 140 else ''}.{source_text}"


def _default_labs_date(app) -> str:
    return (
        current_semantic_date(app, "labs_explicit_date")
        or current_semantic_date(app, "discharge_date")
        or current_semantic_date(app, "admission_date")
    )

# --- Generic visual P2 scanner: mouse selection + color marks ---

_VISUAL_COLOR_CHOICES: tuple[tuple[str, str], ...] = (
    ("Голубой", "#1e5a7a"),
    ("Зелёный", "#245b42"),
    ("Жёлтый", "#6a4f1d"),
    ("Фиолетовый", "#59375f"),
    ("Розовый", "#5d3540"),
    ("Синий", "#314d7a"),
    ("Оливковый", "#4d5d30"),
)



def _open_document_in_default_app(path: str | Path) -> None:
    """Open a DOCX in the doctor's normal desktop application.

    This intentionally avoids global mouse/keyboard hooks and Word automation:
    those are exactly the techniques Windows Defender and corporate policies are
    likely to distrust.  The safe bridge is: open the document, let the doctor
    select text with the mouse, copy it, then read the clipboard.
    """

    from printer_platform import open_desktop_path
    open_desktop_path(Path(path).expanduser(), require_file=True)


def open_external_word_selection_scanner_dialog(
    app,
    *,
    parent: tk.Toplevel | tk.Tk | None = None,
    refresh=None,
    default_field_id: str = "diagnosis.main",
) -> None:
    """Scanner bridge for the real doctor workflow: Word window + mouse selection.

    The doctor chooses a DOCX, the program opens it in Word/LibreOffice/default
    editor, then the doctor selects the needed fragment with the mouse and copies
    it.  The program reads the clipboard and saves an extraction rule into the
    active profile.  This gives the requested external-document UX without unsafe
    system hooks that Windows can block.
    """

    owner = parent or getattr(app, "root", None)
    path = filedialog.askopenfilename(
        title="Выберите DOC/DOCX/DOCM, который нужно показать сканеру",
        filetypes=[("Word DOC/DOCX/DOCM", "*.doc *.docx *.docm"), ("All files", "*.*")],
        parent=owner,
    )
    if not path:
        return
    try:
        pack = app._load_or_create_universal_pack()
        from universal_scanner import scan_docx
        scan = scan_docx(path, registry=pack.registry(), rules=pack.extraction_rules)
        _open_document_in_default_app(path)
    except Exception as exc:
        messagebox.showerror("Сканер Word", f"Не удалось открыть/разобрать документ:\n\n{exc}", parent=owner)
        return

    win = tk.Toplevel(owner)
    win.title("Сканер Word — выделить мышкой в документе")
    win.configure(bg=PANEL)
    win.geometry("760x560")
    win.minsize(660, 460)
    win.grid_columnconfigure(0, weight=1)
    win.grid_rowconfigure(3, weight=1)

    tk.Label(
        win,
        text="Документ открыт во внешнем окне. Выделите нужный текст мышкой, нажмите Ctrl+C, затем здесь выберите смысл поля и нажмите «Запомнить из буфера».",
        bg=PANEL,
        fg=TEXT,
        font=("Segoe UI", 11, "bold"),
        justify="left",
        wraplength=720,
        padx=14,
        pady=12,
    ).grid(row=0, column=0, sticky="ew")

    form = tk.Frame(win, bg=PANEL_3, padx=12, pady=12)
    form.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
    form.grid_columnconfigure(1, weight=1)
    tk.Label(form, text="Что означает выделение", bg=PANEL_3, fg=TEXT, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 10))
    choices = pack.registry().choices()
    prefix = str(default_field_id or "") + " — "
    initial_choice = next((choice for choice in choices if choice.startswith(prefix)), choices[0] if choices else "diagnosis.main — Диагноз")
    field_var = tk.StringVar(value=initial_choice)
    ttk.Combobox(form, textvariable=field_var, values=choices, state="readonly").grid(row=0, column=1, sticky="ew")

    status_var = tk.StringVar(value=f"Открыт файл: {Path(path).name}")
    tk.Label(win, textvariable=status_var, bg=PANEL, fg=MUTED, justify="left", wraplength=720, font=("Segoe UI", 9)).grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 8))

    preview = tk.Text(win, bg=FIELD, fg=TEXT, wrap="word", relief="flat", height=12, padx=10, pady=10, font=("Segoe UI", 9))
    preview.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 10))
    preview.insert("1.0", scan.human_report())
    preview.configure(state="disabled")

    def clipboard_text() -> str:
        try:
            return str(win.clipboard_get() or "").strip()
        except tk.TclError:
            return ""

    def remember_from_clipboard() -> None:
        selected = clipboard_text()
        if not selected:
            messagebox.showwarning("Буфер пуст", "В открытом документе выделите фрагмент мышкой, нажмите Ctrl+C и повторите.", parent=win)
            return
        field_id = field_var.get().split(" — ", 1)[0].strip()
        try:
            current_pack = app._load_or_create_universal_pack()
            from universal_scanner import learn_rule_from_selection
            rule = learn_rule_from_selection(scan.blocks, field_id=field_id, selected_text=selected, registry=current_pack.registry())
            # External selection is doctor-confirmed, so keep it above automatic
            # guesses but below direct placeholder mapping.
            rule = type(rule)(rule.field_id, rule.strategy, rule.label, rule.regex, rule.block_hint, rule.selected_text, max(rule.confidence, 0.9), "external_word_clipboard_selection")
            current_pack.add_rule(rule)
            marks = [dict(item) for item in (current_pack.workflow_principles or {}).get("external_word_scanner_marks", []) if isinstance(item, dict)]
            marks.append({
                "field_id": field_id,
                "source": str(Path(path).expanduser()),
                "selected_preview": " ".join(selected.split())[:240],
                "strategy": rule.strategy,
            })
            current_pack.workflow_principles = {**dict(current_pack.workflow_principles or {}), "external_word_scanner_enabled": True, "external_word_scanner_marks": marks[-200:]}
            from universal_profiles import save_document_pack
            save_document_pack(current_pack, app._universal_profile_path())
            if field_id == "labs.results" and hasattr(app, "labs_text_var"):
                try:
                    from medical_renderer_labs import normalize_labs_block
                    app.labs_text_var.set(normalize_labs_block(selected, default_date=_default_labs_date(app), date_policy=getattr(app, "labs_date_policy_var").get()))
                    app.labs_source_path_var.set(str(Path(path).expanduser()))
                    app.labs_without_var.set(False)
                except Exception as exc:
                    record_soft_exception("dialog_fields_core.external_word_labs_apply", exc)
            if refresh:
                refresh()
            status_var.set(f"Запомнено: {field_id} / {rule.strategy}. Профиль сохранён. Выделение: {' '.join(selected.split())[:90]}")
            try:
                app._set_status("Сканер Word сохранил правило профиля")
            except Exception as exc:
                record_soft_exception("dialog_fields_core.external_word_status", exc)
        except Exception as exc:
            messagebox.showerror("Сканер Word", str(exc), parent=win)

    buttons = tk.Frame(win, bg=PANEL)
    buttons.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 14))
    buttons.grid_columnconfigure(0, weight=1)
    buttons.grid_columnconfigure(1, weight=1)
    buttons.grid_columnconfigure(2, weight=1)
    def close_word_scanner() -> None:
        try:
            win.grab_release()
        except tk.TclError as exc:
            record_soft_exception("dialog_fields_core.external_word_grab_release", exc)
        try:
            win.withdraw()
        except tk.TclError as exc:
            record_soft_exception("dialog_fields_core.external_word_withdraw", exc)
        win.destroy()

    _button(buttons, "Открыть документ снова", lambda: _open_document_in_default_app(path)).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    _button(buttons, "Запомнить из буфера", remember_from_clipboard, primary=True).grid(row=0, column=1, sticky="ew", padx=6)
    _button(buttons, "Закрыть", close_word_scanner).grid(row=0, column=2, sticky="ew", padx=(6, 0))
    win.protocol("WM_DELETE_WINDOW", close_word_scanner)
    win.bind("<Escape>", lambda _event: close_word_scanner())
    win.transient(owner)
    win.grab_set()
    win.focus_set()
    if owner is not None:
        owner.wait_window(win)

def open_visual_scanner_dialog(
    app,
    *,
    parent: tk.Toplevel | tk.Tk | None = None,
    refresh=None,
    default_field_id: str = "labs.results",
    default_mode: str = "source_extraction",
    selection_callback=None,
) -> None:
    """Open the production-safe color scanner."""

    owner = parent or getattr(app, "root", None)
    path = filedialog.askopenfilename(
        title="Выберите DOCX/DOCM для цветной разметки",
        filetypes=[("Word DOC/DOCX/DOCM", "*.doc *.docx *.docm"), ("All files", "*.*")],
        parent=owner,
    )
    if not path:
        return
    try:
        pack = app._load_or_create_universal_pack()
        from universal_scanner import scan_docx
        scan = scan_docx(path, registry=pack.registry(), rules=pack.extraction_rules)
    except Exception as exc:
        messagebox.showerror("Цветной сканер", f"Не удалось разобрать документ:\n\n{exc}", parent=owner)
        return
    _create_visual_scanner_dialog(app, owner, path, pack, scan, refresh, default_field_id, default_mode, selection_callback)


def _create_visual_scanner_dialog(app, owner, path: str, pack, scan, refresh, default_field_id: str, default_mode: str, selection_callback) -> None:
    win = tk.Toplevel(owner)
    win.title("Цветной сканер — показать программе мышкой")
    win.configure(bg=PANEL)
    win.geometry("1080x700")
    win.minsize(900, 560)
    win.grid_columnconfigure(0, weight=3)
    win.grid_columnconfigure(1, weight=2)
    win.grid_rowconfigure(1, weight=1)
    tk.Label(win, text="Цветной сканер: выделите фрагмент, выберите смысл поля и режим запоминания", bg=PANEL, fg=TEXT, font=("Segoe UI", 12, "bold"), justify="left", padx=12, pady=10).grid(row=0, column=0, columnspan=2, sticky="ew")
    text = _build_visual_scanner_text_column(win, scan)
    controls = _build_visual_scanner_controls(win, pack, default_field_id, default_mode, path)
    ctx = {
        "app": app,
        "win": win,
        "path": path,
        "scan": scan,
        "refresh": refresh,
        "selection_callback": selection_callback,
        "text": text,
        **controls,
    }
    _build_visual_scanner_buttons(ctx)
    win.transient(owner)
    win.focus_set()


def _build_visual_scanner_text_column(win: tk.Toplevel, scan) -> tk.Text:
    left = tk.Frame(win, bg=PANEL, padx=12, pady=0)
    left.grid(row=1, column=0, sticky="nsew")
    left.grid_columnconfigure(0, weight=1)
    left.grid_rowconfigure(0, weight=1)
    text = tk.Text(left, bg=FIELD, fg=TEXT, selectbackground=ACCENT, selectforeground="#03101f", wrap="word", relief="flat", padx=12, pady=12, font=("Segoe UI", 10))
    text.grid(row=0, column=0, sticky="nsew")
    scroll = tk.Scrollbar(left, command=text.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    text.configure(yscrollcommand=scroll.set)
    for block in scan.blocks:
        text.insert("end", f"[{block.index:03d}] {block.kind}: {block.path_hint}\n", ("block_header",))
        text.insert("end", block.text + "\n\n")
    text.tag_configure("block_header", foreground=ACCENT, spacing1=4, spacing3=2)
    return text


def _build_visual_scanner_controls(win: tk.Toplevel, pack, default_field_id: str, default_mode: str, path: str) -> dict:
    right = tk.Frame(win, bg=PANEL_3, padx=12, pady=12)
    right.grid(row=1, column=1, sticky="nsew", padx=(0, 12), pady=(0, 12))
    right.grid_columnconfigure(0, weight=1)
    right.grid_rowconfigure(8, weight=1)
    tk.Label(right, text="Что означает выделение", bg=PANEL_3, fg=TEXT, font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
    choices = pack.registry().choices()
    prefix = str(default_field_id or "") + " — "
    initial_choice = next((choice for choice in choices if choice.startswith(prefix)), choices[0] if choices else "labs.results — Анализы")
    field_var = tk.StringVar(value=initial_choice)
    ttk.Combobox(right, textvariable=field_var, values=choices, state="readonly").grid(row=1, column=0, sticky="ew", pady=(6, 12))
    tk.Label(right, text="Цвет метки", bg=PANEL_3, fg=TEXT, font=("Segoe UI", 10, "bold")).grid(row=2, column=0, sticky="w")
    color_var = tk.StringVar(value=_VISUAL_COLOR_CHOICES[0][0])
    ttk.Combobox(right, textvariable=color_var, values=tuple(name for name, _hex in _VISUAL_COLOR_CHOICES), state="readonly").grid(row=3, column=0, sticky="ew", pady=(6, 12))
    tk.Label(right, text="Режим", bg=PANEL_3, fg=TEXT, font=("Segoe UI", 10, "bold")).grid(row=4, column=0, sticky="w")
    mode_var = tk.StringVar(value=default_mode if default_mode in {"source_extraction", "template_replace", "template_insert_after"} else "source_extraction")
    _visual_radio(right, "Исходный документ: научить извлекать это поле", "source_extraction", mode_var).grid(row=5, column=0, sticky="w", pady=(6, 2))
    _visual_radio(right, "Шаблон: заменить выделение на {{поле}}", "template_replace", mode_var).grid(row=6, column=0, sticky="w", pady=2)
    _visual_radio(right, "Шаблон: вставлять {{поле}} после выбранной строки", "template_insert_after", mode_var).grid(row=7, column=0, sticky="w", pady=(2, 12))
    _build_visual_help(right)
    status_var = tk.StringVar(value=f"Файл: {Path(path).name}. Выделите фрагмент слева.")
    tk.Label(right, textvariable=status_var, bg=PANEL_3, fg=MUTED, justify="left", wraplength=360, font=("Segoe UI", 8)).grid(row=9, column=0, sticky="ew", pady=(0, 10))
    return {"right": right, "field_var": field_var, "color_var": color_var, "mode_var": mode_var, "status_var": status_var}


def _build_visual_help(parent: tk.Frame) -> None:
    help_text = tk.Text(parent, bg=FIELD, fg=MUTED, wrap="word", relief="flat", height=10, padx=8, pady=8, font=("Segoe UI", 8))
    help_text.grid(row=8, column=0, sticky="nsew", pady=(0, 10))
    help_text.insert(
        "1.0",
        "Как пользоваться:\n"
        "1) Выделите мышкой строку/блок слева.\n"
        "2) Выберите смысл поля: анализы, диагноз, лечение, дата и т.д.\n"
        "3) Для исходников программа сохранит правило чтения в профиль.\n"
        "4) Для шаблонов программа поставит реальную метку {{field.id}}, которую потом заполнит генератор.\n\n"
        "Это безопасный режим: он не перехватывает мышь/клавиатуру Windows. Для настоящего Word-окна используйте кнопку «Сканер Word»."
    )
    help_text.configure(state="disabled")


def _visual_selected_text(ctx: dict) -> str:
    try:
        return ctx["text"].get("sel.first", "sel.last").strip()
    except tk.TclError:
        return ""


def _visual_color_hex(name: str) -> str:
    return dict(_VISUAL_COLOR_CHOICES).get(name, _VISUAL_COLOR_CHOICES[0][1])


def _visual_mark_only(ctx: dict) -> None:
    selected = _visual_selected_text(ctx)
    if not selected:
        messagebox.showwarning("Нет выделения", "Выделите мышкой фрагмент документа слева.", parent=ctx["win"])
        return
    tag = "visual_mark_" + str(abs(hash((selected, ctx["color_var"].get()))) % 1000000)
    ctx["text"].tag_configure(tag, background=_visual_color_hex(ctx["color_var"].get()), foreground=TEXT)
    try:
        ctx["text"].tag_add(tag, "sel.first", "sel.last")
    except tk.TclError as exc:
        record_soft_exception("dialog_fields_core.visual_mark_selection", exc)
        return
    ctx["status_var"].set(f"Помечено цветом: {ctx['color_var'].get()}. Чтобы правило сохранилось, нажмите «Запомнить».")


def _visual_append_mark(ctx: dict, current_pack, *, field_id: str, selected: str, mode: str, strategy: str) -> None:
    marks = [dict(item) for item in (current_pack.workflow_principles or {}).get("visual_color_marks", []) if isinstance(item, dict)]
    marks.append({"field_id": field_id, "mode": mode, "strategy": strategy, "color": ctx["color_var"].get(), "source": str(Path(ctx["path"]).expanduser()), "selected_preview": " ".join(selected.split())[:240]})
    current_pack.workflow_principles = {**dict(current_pack.workflow_principles or {}), "visual_color_marks": marks[-200:], "visual_scanner_enabled": True}


def _visual_remember(ctx: dict) -> None:
    selected = _visual_selected_text(ctx)
    if not selected:
        messagebox.showwarning("Нет выделения", "Выделите мышкой фрагмент документа слева.", parent=ctx["win"])
        return
    field_id = ctx["field_var"].get().split(" — ", 1)[0].strip()
    mode = ctx["mode_var"].get()
    _visual_mark_only(ctx)
    try:
        _visual_save_selection(ctx, selected=selected, field_id=field_id, mode=mode)
    except Exception as exc:
        messagebox.showerror("Цветной сканер", str(exc), parent=ctx["win"])


def _visual_save_selection(ctx: dict, *, selected: str, field_id: str, mode: str) -> None:
    app = ctx["app"]
    current_pack = app._load_or_create_universal_pack()
    if mode == "source_extraction":
        from universal_scanner import learn_rule_from_selection
        rule = learn_rule_from_selection(ctx["scan"].blocks, field_id=field_id, selected_text=selected, registry=current_pack.registry())
        rule = type(rule)(rule.field_id, rule.strategy, rule.label, rule.regex, rule.block_hint, rule.selected_text, max(rule.confidence, 0.82), f"visual_color_selection:{ctx['color_var'].get()}")
        current_pack.add_rule(rule)
        _visual_append_mark(ctx, current_pack, field_id=field_id, selected=selected, mode=mode, strategy=rule.strategy)
        status = f"Запомнено правило чтения: {field_id} / {rule.strategy}. Профиль сохранён."
    else:
        from universal_template_engine import insert_placeholder_after_selection, replace_selection_with_placeholder
        result = insert_placeholder_after_selection(ctx["path"], selected, field_id) if mode == "template_insert_after" else replace_selection_with_placeholder(ctx["path"], selected, field_id)
        if not result.ok:
            raise ValueError("Не удалось найти выделенный фрагмент внутри DOCX. Попробуйте выделить одну точную строку без лишних переносов.")
        _visual_append_mark(ctx, current_pack, field_id=field_id, selected=selected, mode=mode, strategy=result.strategy)
        status = f"В шаблон поставлена метка {result.placeholder}. Резервная копия: {Path(result.backup_path).name if result.backup_path else 'нет'}."
    from universal_profiles import save_document_pack
    save_document_pack(current_pack, app._universal_profile_path())
    if mode == "source_extraction" and ctx.get("selection_callback"):
        ctx["selection_callback"](selected, str(Path(ctx["path"]).expanduser()))
    if ctx.get("refresh"):
        ctx["refresh"]()
    ctx["status_var"].set(status)
    try:
        app._set_status("Цветной сканер сохранил правило профиля")
    except Exception as exc:
        record_soft_exception("dialog_fields_core.visual_scanner_status", exc)


def _build_visual_scanner_buttons(ctx: dict) -> None:
    right = ctx["right"]
    buttons = tk.Frame(right, bg=PANEL_3)
    buttons.grid(row=10, column=0, sticky="ew")
    buttons.grid_columnconfigure(0, weight=1)
    buttons.grid_columnconfigure(1, weight=1)
    _button(buttons, "Пометить цветом", lambda: _visual_mark_only(ctx)).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    _button(buttons, "Запомнить", lambda: _visual_remember(ctx), primary=True).grid(row=0, column=1, sticky="ew", padx=(6, 0))
    _button(right, "Закрыть", ctx["win"].destroy).grid(row=11, column=0, sticky="ew", pady=(10, 0))

def _visual_radio(parent, text: str, value: str, variable: tk.StringVar) -> tk.Radiobutton:
    return tk.Radiobutton(
        parent,
        text=text,
        value=value,
        variable=variable,
        bg=PANEL_3,
        fg=TEXT,
        activebackground=PANEL_3,
        selectcolor=FIELD,
        justify="left",
        wraplength=360,
        font=("Segoe UI", 8),
    )


# --- Additional information popup helpers; inlined to preserve architecture file budget. ---


def ensure_additional_info_state(app):
    if not hasattr(app, "additional_info_text_var"):
        app.additional_info_text_var = tk.StringVar()
    if not hasattr(app, "additional_info_source_path_var"):
        app.additional_info_source_path_var = tk.StringVar()

def _read_text_file_for_additional_info(path):
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return raw.decode(enc).strip()
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace").strip()

def read_additional_info_file(path):
    candidate = Path(path).expanduser()
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(f"Не найден файл дополнительной информации: {candidate}")
    suffix = candidate.suffix.lower()
    if suffix in {".txt", ".csv"}:
        return _read_text_file_for_additional_info(candidate)
    if suffix in {".docx", ".docm", ".doc"}:
        from medical_docx_reader import extract_docx_text
        word_path = candidate
        if suffix == ".doc":
            try:
                from medical_docx_xml_fragments import ensure_docx_compatible
                word_path = ensure_docx_compatible(candidate)
            except Exception:
                word_path = candidate
        return extract_docx_text(word_path).strip()
    raise ValueError(f"Неверный формат файла дополнительной информации: {suffix or 'без расширения'}")

def choose_additional_info_file(app, parent=None, title="Выберите файл дополнительной информации"):
    ensure_additional_info_state(app)
    owner = parent or getattr(app, "root", None)
    path = filedialog.askopenfilename(title=title, filetypes=[("Word/Text", "*.doc *.docx *.docm *.txt *.csv"), ("All files", "*.*")], parent=owner)
    if not path:
        return False
    try:
        text = read_additional_info_file(path)
    except Exception as exc:
        record_soft_exception("dialog_fields_core.additional_info_file", exc, detail=path)
        messagebox.showerror("Дополнительная информация", str(exc), parent=owner)
        return False
    if not text:
        messagebox.showwarning("Дополнительная информация", "Выбранный файл пуст.", parent=owner)
        return False
    app.additional_info_text_var.set(text)
    app.additional_info_source_path_var.set(str(Path(path).expanduser()))
    return True

def choose_epi_file_for_app(app, parent=None):
    owner = parent or getattr(app, "root", None)
    path = filedialog.askopenfilename(title="Добавить ЭПИ в акт РВК", filetypes=[("ЭПИ Word/Text", "*.doc *.docx *.docm *.txt"), ("All files", "*.*")], parent=owner)
    if not path:
        return False
    try:
        if hasattr(app, "service"):
            app.service.load_epi_text(path)
        else:
            read_additional_info_file(path)
    except Exception as exc:
        record_soft_exception("dialog_fields_core.choose_epi", exc, detail=path)
        messagebox.showerror("ЭПИ", str(exc), parent=owner)
        return False
    app.epi_path_var.set(str(Path(path).expanduser()))
    return True

def _additional_info_summary(app):
    ensure_additional_info_state(app)
    text = app.additional_info_text_var.get().strip()
    source = app.additional_info_source_path_var.get().strip()
    if not text:
        return "Дополнительная информация не добавлена."
    words = " ".join(text.split())
    suffix = "..." if words[140:] else ""
    source_text = f" Источник: {Path(source).name}." if source else ""
    return "Добавлено: " + words[:140] + suffix + "." + source_text

def open_additional_info(app, parent=None):
    ensure_additional_info_state(app)
    owner = parent or getattr(app, "root", None)
    text = app.additional_info_text_var.get().strip()
    if not text:
        messagebox.showinfo("Дополнительная информация", "Дополнительная информация ещё не добавлена.", parent=owner)
        return
    win = tk.Toplevel(owner)
    win.title("Дополнительная информация")
    win.configure(bg=PANEL)
    win.geometry("760x520")
    win.grid_columnconfigure(0, weight=1)
    win.grid_rowconfigure(0, weight=1)
    box = tk.Text(win, bg=FIELD, fg=TEXT, insertbackground=TEXT, wrap="word", relief="flat", padx=10, pady=10)
    box.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
    box.insert("1.0", text)
    box.configure(state="disabled")
    tk.Button(win, text="Закрыть", command=win.destroy, bg=ACCENT_2, fg="#03101f", relief="flat", padx=18, pady=8).grid(row=1, column=0, sticky="e", padx=12, pady=(0, 12))
    win.transient(owner)

def attach_additional_info_buttons(app, parent, container, row, columnspan=2):
    ensure_additional_info_state(app)
    frame = tk.Frame(container, bg=PANEL_3, padx=10, pady=8)
    frame.grid(row=row, column=0, columnspan=columnspan, sticky="ew", pady=(8, 8))
    frame.grid_columnconfigure(0, weight=1)
    frame.grid_columnconfigure(1, weight=1)
    summary_var = tk.StringVar(value=_additional_info_summary(app))
    tk.Label(frame, text="Дополнительная информация", bg=PANEL_3, fg=TEXT, font=("Segoe UI", 9, "bold"), anchor="w").grid(row=0, column=0, columnspan=2, sticky="ew")
    tk.Label(frame, textvariable=summary_var, bg=PANEL_3, fg=MUTED, wraplength=620, justify="left", anchor="w", font=("Segoe UI", 8)).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 8))
    def refresh():
        summary_var.set(_additional_info_summary(app))
    def add_file():
        if choose_additional_info_file(app, parent=parent):
            refresh()
    def open_file():
        open_additional_info(app, parent=parent)
        refresh()
    tk.Button(frame, text="Добавить дополнительную информацию", command=add_file, bg=ACCENT_2, fg="#03101f", activebackground=ACCENT, activeforeground="#03101f", relief="flat", padx=8, pady=6, cursor="hand2", font=("Segoe UI", 8, "bold"), wraplength=220).grid(row=2, column=0, sticky="ew", padx=(0, 6))
    tk.Button(frame, text="Открыть", command=open_file, bg=FIELD, fg=TEXT, activebackground=PANEL_3, activeforeground=TEXT, relief="flat", padx=8, pady=6, cursor="hand2", font=("Segoe UI", 8, "bold")).grid(row=2, column=1, sticky="ew", padx=(6, 0))
    return 1

