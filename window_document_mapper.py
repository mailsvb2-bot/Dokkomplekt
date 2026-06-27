from __future__ import annotations
import tkinter as tk
from pathlib import Path
from medical_constants import DIR_PRIMARY_DOCUMENTS
from tkinter import filedialog, messagebox, ttk
from app_config import (
    ACCENT,
    ACCENT_2,
    DEEP,
    FIELD,
    MUTED,
    PANEL,
    PANEL_3,
    TEXT,
)
from diagnostic_logging import record_soft_exception
from i18n_strings import tr
from medical_language_catalog import language_choices, language_id_from_choice, language_profile
from personal_document_buttons import available_profile_path, safe_profile_filename, safe_profile_pack_id, unique_button_label
from layout_checklist import BLOCK03_DOCTOR_SETUP_FLAG, BLOCK03_LEGACY_SETUP_FLAGS
from universal_profiles import DOCTOR_BUTTON_REVIEW_CONTRACT_VERSION

def open_universal_document_mapper(app) -> None:
    """Implement the open_universal_document_mapper workflow with validation, UI state updates and diagnostics."""
    self = app
    path = filedialog.askopenfilename(
        title="Выберите DOCX для разметки профиля",
        initialdir=self._dialog_initial_dir(DIR_PRIMARY_DOCUMENTS),
        filetypes=[("Word DOCX/DOCM", "*.docx *.docm"), ("All files", "*.*")],
    )
    if not path:
        return
    try:
        pack = self._load_or_create_universal_pack()
        from universal_scanner import learn_rule_from_selection, scan_docx
        scan = scan_docx(path, registry=pack.registry(), rules=pack.extraction_rules)
        self._last_detected_document_language = scan.detected_language
    except Exception as exc:
        messagebox.showerror("Разметчик документов", f"Не удалось разобрать документ:\n\n{exc}")
        return

    dialog = tk.Toplevel(self.root)
    dialog.title("Разметчик документов — профиль")
    dialog.configure(bg=DEEP)
    dialog.geometry("1040x680")
    dialog.minsize(860, 540)
    dialog.grid_columnconfigure(0, weight=3)
    dialog.grid_columnconfigure(1, weight=2)
    dialog.grid_rowconfigure(1, weight=1)

    title = tk.Label(
        dialog,
        text="Разметчик документа: проверьте найденные поля или выделите фрагмент мышкой",
        bg=DEEP,
        fg=TEXT,
        font=self._font(13, "bold"),
        padx=self._px(14, 8),
        pady=self._px(10, 6),
    )
    title.grid(row=0, column=0, columnspan=2, sticky="ew")

    left = tk.Frame(dialog, bg=PANEL, padx=self._px(10, 6), pady=self._px(10, 6))
    left.grid(row=1, column=0, sticky="nsew", padx=(self._px(12, 7), self._px(6, 4)), pady=(0, self._px(12, 7)))
    left.grid_rowconfigure(0, weight=1)
    left.grid_columnconfigure(0, weight=1)

    text = tk.Text(
        left,
        bg=FIELD,
        fg=TEXT,
        insertbackground=ACCENT,
        selectbackground=PANEL_3,
        selectforeground=TEXT,
        wrap="word",
        relief="flat",
        padx=self._px(10, 6),
        pady=self._px(10, 6),
        font=self._font(10),
    )
    text.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(left, command=text.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    text.configure(yscrollcommand=scroll.set)

    index_by_block: dict[int, tuple[str, str, int]] = {}
    for block in scan.blocks:
        start = text.index("end-1c")
        header = f"[{block.index:03d}] {block.path_hint}\n"
        text.insert("end", header, ("block_header",))
        text.insert("end", block.text + "\n\n")
        end_index = text.index("end-1c")
        index_by_block[block.index] = (start, end_index, len(header))
    text.tag_configure("block_header", foreground=ACCENT, spacing1=4, spacing3=2)

    palette = ["#1e5a7a", "#245b42", "#6a4f1d", "#59375f", "#5d3540", "#314d7a", "#4d5d30"]
    for n, match in enumerate(scan.best_matches().values()):
        block_info = index_by_block.get(match.block_index)
        if not block_info or match.start < 0 or match.end <= match.start:
            continue
        tag = "field_" + match.field_id.replace(".", "_")
        text.tag_configure(tag, background=palette[n % len(palette)], foreground=TEXT)
        block_start_index, _block_end_index, header_len = block_info
        try:
            start_index = f"{block_start_index}+{header_len + match.start}c"
            end_index = f"{block_start_index}+{header_len + match.end}c"
            text.tag_add(tag, start_index, end_index)
        except Exception as exc:
            record_soft_exception("window_mixin:530", exc)

    right = tk.Frame(dialog, bg=PANEL, padx=self._px(10, 6), pady=self._px(10, 6))
    right.grid(row=1, column=1, sticky="nsew", padx=(self._px(6, 4), self._px(12, 7)), pady=(0, self._px(12, 7)))
    right.grid_rowconfigure(1, weight=1)
    right.grid_columnconfigure(0, weight=1)

    tk.Label(right, text="Что программа поняла", bg=PANEL, fg=TEXT, font=self._font(12, "bold")).grid(row=0, column=0, sticky="w")
    report = tk.Text(right, bg=FIELD, fg=TEXT, wrap="word", relief="flat", height=14, padx=8, pady=8, font=self._font(9))
    report.grid(row=1, column=0, sticky="nsew", pady=(self._px(8, 4), self._px(10, 6)))
    report.insert("1.0", scan.human_report())
    report.configure(state="disabled")

    tk.Label(
        right,
        text="Выделите фрагмент слева, выберите смысл поля и нажмите «Запомнить». Правило сохранится в профиль, а не в данные пациента.",
        bg=PANEL,
        fg=MUTED,
        wraplength=self._px(360, 260),
        justify="left",
        font=self._font(9),
    ).grid(row=2, column=0, sticky="ew", pady=(0, self._px(6, 4)))

    field_var = tk.StringVar(value="patient.fio — ФИО пациента")
    combo = ttk.Combobox(right, textvariable=field_var, values=pack.registry().choices(), state="readonly")
    combo.grid(row=3, column=0, sticky="ew", pady=(0, self._px(8, 4)))

    status_var = tk.StringVar(value=f"Профиль: {self._universal_profile_path()}")
    completion_values_for_current_scan: dict[str, str] = {}
    status = tk.Label(right, textvariable=status_var, bg=PANEL, fg=MUTED, wraplength=self._px(360, 260), justify="left", font=self._font(8))
    status.grid(row=5, column=0, sticky="ew", pady=(self._px(8, 4), 0))

    def show_soft_regulatory_advice(advice, *, source_label: str) -> bool:
        """Show non-blocking regulatory suggestions and return doctor choice.

        Важный lock: даже если врач нажал «Нет, не буду, делай как есть»,
        программа не блокирует профиль, шаблон или генерацию документов.
        """
        if not getattr(advice, "has_suggestions", False):
            messagebox.showinfo("Подсказки по документу", advice.human_report(), parent=dialog)
            return False
        advice_dialog = tk.Toplevel(dialog)
        advice_dialog.title("Подсказки по документу")
        advice_dialog.configure(bg=DEEP)
        advice_dialog.geometry("760x520")
        advice_dialog.grid_columnconfigure(0, weight=1)
        advice_dialog.grid_rowconfigure(1, weight=1)
        tk.Label(
            advice_dialog,
            text=f"{source_label}: возможно, здесь стоит указать ещё и...",
            bg=DEEP,
            fg=TEXT,
            font=self._font(12, "bold"),
            padx=self._px(12, 8),
            pady=self._px(10, 6),
        ).grid(row=0, column=0, sticky="ew")
        body = tk.Text(advice_dialog, bg=FIELD, fg=TEXT, wrap="word", relief="flat", padx=10, pady=10, font=self._font(9))
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
        body.insert("1.0", advice.human_report() + "\n\n" + advice.soft_prompt_text())
        body.configure(state="disabled")
        choice = {"accepted": False}
        buttons = tk.Frame(advice_dialog, bg=DEEP)
        buttons.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)

        def accept_advice() -> None:
            try:
                from regulatory_completion_blocks import (
                    apply_completion_values,
                    completion_inputs_from_advice,
                    completion_values_from_raw,
                    save_completion_values,
                )
                from regulatory_template_advisor import save_advice_report

                report_path = save_advice_report(advice, self._universal_profile_path().with_name("regulatory_soft_advice.txt"))
                base_case = scan.patient_case()
                if completion_values_for_current_scan:
                    base_case = apply_completion_values(base_case, completion_values_for_current_scan)
                inputs = completion_inputs_from_advice(advice, existing_case=base_case)
                values = self._prompt_regulatory_completion_values(inputs, parent=advice_dialog)
                values = completion_values_from_raw(inputs, values)
                if values:
                    completion_values_for_current_scan.update(values)
                values_path = save_completion_values(completion_values_for_current_scan, self._universal_profile_path().with_name("regulatory_completion_values.txt"))
                status_var.set(
                    f"Дополнения сохранены: {report_path.name}. "
                    f"Дополнено полей: {len(values)}. Значения: {values_path.name}."
                )
            except Exception as exc:
                messagebox.showwarning("Подсказки по документу", f"Не удалось сохранить/открыть дополнения:\n\n{exc}", parent=advice_dialog)
            choice["accepted"] = True
            advice_dialog.destroy()

        def decline_advice() -> None:
            status_var.set("Врач выбрал: нет, не буду, делай как есть. Программа продолжит без давления и блокировок.")
            choice["accepted"] = False
            advice_dialog.destroy()

        tk.Button(
            buttons,
            text="Буду дополнять",
            command=accept_advice,
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
            text="Нет, не буду, делай как есть",
            command=decline_advice,
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
        advice_dialog.transient(dialog)
        advice_dialog.grab_set()
        dialog.wait_window(advice_dialog)
        return bool(choice["accepted"])

    def remember_selection() -> None:
        try:
            selected = text.get("sel.first", "sel.last").strip()
        except tk.TclError:
            messagebox.showwarning("Нет выделения", "Выделите мышкой фрагмент документа слева.", parent=dialog)
            return
        field_choice = field_var.get().split(" — ", 1)[0].strip()
        try:
            current_pack = self._load_or_create_universal_pack()
            rule = learn_rule_from_selection(scan.blocks, field_id=field_choice, selected_text=selected, registry=current_pack.registry())
            current_pack.add_rule(rule)
            from universal_profiles import save_document_pack
            save_document_pack(current_pack, self._universal_profile_path(), backup_reason="document_mapper_save")
            status_var.set(f"Запомнено правило: {rule.field_id} / {rule.strategy}. Профиль сохранён: {self._universal_profile_path()}")
            self._set_status("Профиль документов обновлён")
        except Exception as exc:
            messagebox.showerror("Не удалось сохранить правило", str(exc), parent=dialog)

    def _button_language_preference() -> str:
        try:
            out_lang = self.output_language_var.get().strip()
        except Exception as exc:
            record_soft_exception("window_document_mapper.output_language_preference", exc)
            out_lang = "same_as_source"
        if out_lang and out_lang not in {"same_as_source", "auto"}:
            return out_lang
        try:
            return self.document_language_var.get().strip()
        except Exception as exc:
            record_soft_exception("window_document_mapper.document_language_preference", exc)
            return "auto"

    def prompt_diary_schedule_for_template(template_path: str | Path):
        from diary_schedule import DiaryScheduleSpec, describe_schedule, infer_diary_schedule_from_docx, parse_day_offsets, parse_hour_offsets
        inferred = infer_diary_schedule_from_docx([template_path])
        use_inferred = False
        if inferred.day_offsets:
            use_inferred = messagebox.askyesno(
                "Принцип дневников",
                "Программа поняла, что дневники пишутся по принципу:\n\n"
                + describe_schedule(inferred)
                + "\n\nДа, по такому принципу?",
                parent=dialog,
            )
        if use_inferred:
            spec = inferred
        else:
            spec = ask_manual_day_schedule(inferred)
        if messagebox.askyesno(
            "Дневники по часам",
            "Пишите ли вы дневники по часам?",
            parent=dialog,
        ):
            hours = ask_manual_hour_schedule()
            spec = DiaryScheduleSpec("hourly", spec.day_offsets, hours, 1.0, "manual_hourly_confirmed")
        return spec

    def ask_manual_day_schedule(inferred):
        from diary_schedule import DiaryScheduleSpec, parse_day_offsets
        popup = tk.Toplevel(dialog)
        popup.title("Принцип дат дневников")
        popup.configure(bg=DEEP)
        popup.geometry("720x260")
        popup.grid_columnconfigure(0, weight=1)
        text_label = (
            "Введите просто цифры. Знак «+» подразумевается по умолчанию.\n"
            "Например: от даты поступления +1 день, +2 дня, +3 дня, +5 дней, +7 дней, +14 дней.\n"
            "Введите минимум 10 чисел — дальше программа будет понимать принцип заполнения."
        )
        tk.Label(popup, text=text_label, bg=DEEP, fg=TEXT, font=self._font(10, "bold"), justify="left", wraplength=680, padx=12, pady=12).grid(row=0, column=0, sticky="ew")
        value_var = tk.StringVar(value="+1, +2, +3, +5, +7, +14, +21, +28, +35, +42")
        entry = tk.Entry(popup, textvariable=value_var, bg=FIELD, fg=TEXT, insertbackground=ACCENT, relief="flat", font=self._font(11))
        entry.grid(row=1, column=0, sticky="ew", padx=12, ipady=8)
        result = {"spec": None}
        def save() -> None:
            try:
                offsets = parse_day_offsets(value_var.get(), require_minimum=True)
                result["spec"] = DiaryScheduleSpec("daily", offsets, (), 1.0, "manual_day_offsets")
                popup.destroy()
            except Exception as exc:
                messagebox.showwarning("Принцип дневников", str(exc), parent=popup)
        tk.Button(popup, text="Сохранить принцип", command=save, bg=ACCENT_2, fg="#03101f", relief="flat", font=self._font(10, "bold"), padx=10, pady=8).grid(row=2, column=0, sticky="ew", padx=12, pady=12)
        popup.transient(dialog)
        popup.grab_set()
        entry.focus_set()
        dialog.wait_window(popup)
        return result["spec"] or DiaryScheduleSpec("daily", inferred.day_offsets, (), inferred.confidence, inferred.source)

    def ask_manual_hour_schedule() -> tuple[int, ...]:
        from diary_schedule import parse_hour_offsets
        popup = tk.Toplevel(dialog)
        popup.title("Частота дневников по часам")
        popup.configure(bg=DEEP)
        popup.geometry("640x220")
        popup.grid_columnconfigure(0, weight=1)
        tk.Label(popup, text="Напишите интервалы: например 1 — каждый час; 2 — каждые 2 часа; 1, 2, 3 — через 1 час, затем через 2 часа, затем через 3 часа, с повторением этого принципа.", bg=DEEP, fg=TEXT, font=self._font(10, "bold"), justify="left", wraplength=600, padx=12, pady=12).grid(row=0, column=0, sticky="ew")
        value_var = tk.StringVar(value="1, 2, 3, 4, 6, 8, 12, 24")
        entry = tk.Entry(popup, textvariable=value_var, bg=FIELD, fg=TEXT, insertbackground=ACCENT, relief="flat", font=self._font(11))
        entry.grid(row=1, column=0, sticky="ew", padx=12, ipady=8)
        result = {"hours": ()}
        def save() -> None:
            try:
                result["hours"] = parse_hour_offsets(value_var.get())
                popup.destroy()
            except Exception as exc:
                messagebox.showwarning("Дневники по часам", str(exc), parent=popup)
        tk.Button(popup, text="Сохранить", command=save, bg=ACCENT_2, fg="#03101f", relief="flat", font=self._font(10, "bold"), padx=10, pady=8).grid(row=2, column=0, sticky="ew", padx=12, pady=12)
        popup.transient(dialog)
        popup.grab_set()
        entry.focus_set()
        dialog.wait_window(popup)
        return tuple(result["hours"])

    def _attach_regular_template_button(template_path: str, *, explicit_role_id: str = "", explicit_label: str = ""):
        current_pack = self._load_or_create_universal_pack()
        from personal_document_buttons import suggest_button_label_for_template
        suggestion = suggest_button_label_for_template(
            template_path,
            preferred_language=_button_language_preference(),
            ui_language=self.ui_language_var.get() if hasattr(self, "ui_language_var") else "ru",
            explicit_specialty=current_pack.specialty,
            explicit_role_id=explicit_role_id,
            fallback_label=explicit_label or None,
        )
        label = (explicit_label.strip() or suggestion.label or Path(template_path).stem).strip()
        existing_labels = {str(doc.button_label or "").casefold() for doc in current_pack.documents}
        label = unique_button_label(label, existing_labels)
        document_id = suggestion.document_id
        from universal_diary_templates import looks_like_diary_template
        is_diary_template = looks_like_diary_template(template_path)
        from universal_template_engine import attach_template_to_pack, validate_template
        spec, copied_to = attach_template_to_pack(
            current_pack,
            template_path,
            self._universal_profile_path().parent,
            button_label=label,
            document_id=document_id,
            category="diaries" if is_diary_template else "medical",
            registry=current_pack.registry(),
            role_id="daily_diary" if is_diary_template else (suggestion.role_id if suggestion.role_id != "unknown" else explicit_role_id),
            button_language=suggestion.language_id,
            source_language=suggestion.source_language,
            button_label_source="diary_template" if is_diary_template else suggestion.source,
        )
        validation = validate_template(copied_to, required_fields=spec.required_fields, registry=current_pack.registry())
        if is_diary_template:
            from dataclasses import replace
            schedule = prompt_diary_schedule_for_template(copied_to)
            spec = replace(spec, category="diaries", role_id="daily_diary", diary_schedule=schedule.to_dict())
            current_pack.add_document(spec)
        return current_pack, spec, copied_to, validation, suggestion

    def add_template_to_profile() -> None:
        template_path = filedialog.askopenfilename(
            title="Выберите пользовательский DOCX-шаблон",
            initialdir=self._dialog_initial_dir(DIR_PRIMARY_DOCUMENTS),
            filetypes=[("Word DOCX/DOCM", "*.docx *.docm"), ("All files", "*.*")],
            parent=dialog,
        )
        if not template_path:
            return
        try:
            current_pack, spec, copied_to, validation, suggestion = _attach_regular_template_button(template_path)
            if not validation.ok and spec.category != "diaries":
                details = validation.to_dict()
                raise ValueError("Шаблон не прошёл проверку. Проверьте placeholders вида {{patient.fio}}.\n\n" + str(details))
            from regulatory_template_advisor import advise_template
            advice = advise_template(copied_to, registry=current_pack.registry(), explicit_specialty=current_pack.specialty)
            from universal_profiles import save_document_pack
            save_document_pack(current_pack, self._universal_profile_path(), backup_reason="document_mapper_save")
            status_var.set(
                f"Добавлена кнопка: {spec.button_label}. Язык: {spec.button_language}. "
                f"Роль: {spec.role_id or 'не определена'}. Копия: {copied_to.name}. Полей: {len(validation.placeholders)}."
            )
            if advice.has_suggestions:
                show_soft_regulatory_advice(advice, source_label=spec.button_label)
            try:
                self._refresh_custom_profile_tiles()
            except Exception as exc:
                record_soft_exception("window_mixin:751", exc)
            self._set_status("Кнопка документа добавлена в профиль")
        except Exception as exc:
            messagebox.showerror("Не удалось добавить шаблон", str(exc), parent=dialog)

    def create_regular_document_button() -> None:
        """Implement the create_regular_document_button workflow with validation, UI state updates and diagnostics."""
        template_path = filedialog.askopenfilename(
            title="Выберите DOCX-шаблон для новой кнопки",
            initialdir=self._dialog_initial_dir(DIR_PRIMARY_DOCUMENTS),
            filetypes=[("Word DOCX/DOCM", "*.docx *.docm"), ("All files", "*.*")],
            parent=dialog,
        )
        if not template_path:
            return
        try:
            current_pack = self._load_or_create_universal_pack()
            from personal_document_buttons import (
                localized_role_label,
                regular_document_role_choices,
                role_id_from_choice,
                suggest_button_label_for_template,
            )
            language_id = _button_language_preference()
            suggestion = suggest_button_label_for_template(
                template_path,
                preferred_language=language_id,
                ui_language=self.ui_language_var.get() if hasattr(self, "ui_language_var") else "ru",
                explicit_specialty=current_pack.specialty,
            )
            popup = tk.Toplevel(dialog)
            popup.title("Создать кнопку документа")
            popup.configure(bg=DEEP)
            popup.geometry("640x360")
            popup.grid_columnconfigure(0, weight=1)
            tk.Label(
                popup,
                text="Выберите регулярный документ. Название кнопки можно оставить предложенным или исправить вручную.",
                bg=DEEP,
                fg=TEXT,
                font=self._font(11, "bold"),
                wraplength=600,
                justify="left",
                padx=12,
                pady=12,
            ).grid(row=0, column=0, sticky="ew")
            form = tk.Frame(popup, bg=PANEL, padx=12, pady=12)
            form.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
            form.grid_columnconfigure(1, weight=1)
            choices = regular_document_role_choices(suggestion.language_id)
            initial_choice = next((item for item in choices if item.endswith(f"[{suggestion.role_id}]")), choices[0] if choices else "")
            role_var = tk.StringVar(value=initial_choice)
            label_var = tk.StringVar(value=suggestion.label)
            tk.Label(form, text="Документ", bg=PANEL, fg=MUTED, font=self._font(9)).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
            role_box = ttk.Combobox(form, textvariable=role_var, values=choices, state="readonly")
            role_box.grid(row=0, column=1, sticky="ew", pady=(0, 8))
            tk.Label(form, text="Название кнопки", bg=PANEL, fg=MUTED, font=self._font(9)).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
            tk.Entry(form, textvariable=label_var, bg=FIELD, fg=TEXT, insertbackground=ACCENT, relief="flat", font=self._font(10)).grid(row=1, column=1, sticky="ew", ipady=5, pady=(0, 8))
            tk.Label(form, text=f"Файл: {Path(template_path).name}\nЯзык кнопки: {suggestion.language_id}; язык шаблона: {suggestion.source_language}", bg=PANEL, fg=MUTED, font=self._font(8), justify="left").grid(row=2, column=0, columnspan=2, sticky="ew")

            def sync_label(_event=None) -> None:
                role_id = role_id_from_choice(role_var.get())
                if role_id != "unknown":
                    label_var.set(localized_role_label(role_id, suggestion.language_id, fallback=label_var.get()))

            role_box.bind("<<ComboboxSelected>>", sync_label)
            buttons = tk.Frame(popup, bg=DEEP)
            buttons.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
            buttons.grid_columnconfigure(0, weight=1)
            buttons.grid_columnconfigure(1, weight=1)
            result = {"ok": False}

            def save_button() -> None:
                role_id = role_id_from_choice(role_var.get())
                label = label_var.get().strip()
                try:
                    pack, spec, copied_to, validation, _suggestion = _attach_regular_template_button(template_path, explicit_role_id=role_id, explicit_label=label)
                    if not validation.ok and spec.category != "diaries":
                        raise ValueError("Шаблон не прошёл проверку. Проверьте placeholders вида {{patient.fio}}.")
                    from regulatory_template_advisor import advise_template
                    from universal_profiles import save_document_pack
                    advice = advise_template(copied_to, registry=pack.registry(), explicit_specialty=pack.specialty)
                    save_document_pack(pack, self._universal_profile_path(), backup_reason="document_mapper_button")
                    if advice.has_suggestions:
                        show_soft_regulatory_advice(advice, source_label=spec.button_label)
                    self._refresh_custom_profile_tiles()
                    status_var.set(f"Создана постоянная кнопка: {spec.button_label}. Она появится в блоке 03 при следующем запуске.")
                    self._set_status("Постоянная кнопка документа создана")
                    result["ok"] = True
                    popup.destroy()
                except Exception as exc:
                    messagebox.showerror("Создать кнопку документа", str(exc), parent=popup)

            tk.Button(buttons, text="Создать кнопку", command=save_button, bg=ACCENT_2, fg="#03101f", relief="flat", font=self._font(9, "bold"), padx=10, pady=8).grid(row=0, column=0, sticky="ew", padx=(0, 6))
            tk.Button(buttons, text="Отмена", command=popup.destroy, bg=FIELD, fg=TEXT, relief="flat", font=self._font(9, "bold"), padx=10, pady=8).grid(row=0, column=1, sticky="ew", padx=(6, 0))
            popup.transient(dialog)
            popup.grab_set()
            dialog.wait_window(popup)
        except Exception as exc:
            messagebox.showerror("Создать кнопку документа", str(exc), parent=dialog)

    def validate_profile() -> None:
        try:
            current_pack = self._load_or_create_universal_pack()
            from universal_template_engine import save_pack_report, validate_document_pack
            report_obj = validate_document_pack(current_pack, base_dir=self._universal_profile_path().parent)
            report_path = save_pack_report(report_obj, self._universal_profile_path().with_name("profile_validation_report.txt"))
            status_var.set(report_obj.human_report() + f"\n\nОтчёт: {report_path}")
            self._set_status("Профиль документов проверен")
        except Exception as exc:
            messagebox.showerror("Проверка профиля", str(exc), parent=dialog)

    def export_profile() -> None:
        target = filedialog.asksaveasfilename(
            title="Экспорт профиля .medpack.zip",
            initialfile="MedicalDiaryAutofill_Profile.medpack.zip",
            defaultextension=".zip",
            filetypes=[("Medical profile", "*.zip *.medpack"), ("All files", "*.*")],
            parent=dialog,
        )
        if not target:
            return
        try:
            current_pack = self._load_or_create_universal_pack()
            from universal_template_engine import export_document_pack_zip
            exported = export_document_pack_zip(current_pack, target, template_base_dir=self._universal_profile_path().parent)
            status_var.set(f"Профиль экспортирован: {exported}")
            self._set_status("Профиль документов экспортирован")
        except Exception as exc:
            messagebox.showerror("Экспорт профиля", str(exc), parent=dialog)

    def import_profile() -> None:
        source = filedialog.askopenfilename(
            title="Импортировать medpack/profile",
            filetypes=[("Medical profile", "*.zip *.medpack *.json"), ("All files", "*.*")],
            parent=dialog,
        )
        if not source:
            return
        try:
            from universal_template_engine import import_document_pack_zip
            imported_pack, _imported_path = import_document_pack_zip(source, self._universal_profile_path().parent)
            from universal_profiles import save_document_pack
            save_document_pack(imported_pack, self._universal_profile_path(), backup_reason="document_mapper_import")
            try:
                self._refresh_custom_profile_tiles()
            except Exception as exc:
                record_soft_exception("window_mixin:898", exc)
            status_var.set(f"Профиль импортирован: {imported_pack.name}. Рабочий путь: {self._universal_profile_path()}")
            self._set_status("Профиль документов импортирован")
        except Exception as exc:
            messagebox.showerror("Импорт профиля", str(exc), parent=dialog)

    def readiness_report() -> None:
        try:
            current_pack = self._load_or_create_universal_pack()
            from universal_generation import analyze_pack_readiness, save_readiness_report
            report_obj = analyze_pack_readiness(current_pack, scan.patient_case(), base_dir=self._universal_profile_path().parent)
            report_path = save_readiness_report(report_obj, self._universal_profile_path().with_name("profile_readiness_report.txt"))
            messagebox.showinfo("Готовность профиля", report_obj.human_report(), parent=dialog)
            status_var.set(f"Готово: {report_obj.ready_count}; заблокировано: {report_obj.blocked_count}. Отчёт: {report_path.name}")
        except Exception as exc:
            messagebox.showerror("Готовность профиля", str(exc), parent=dialog)

    def audit_profile_layer() -> None:
        try:
            current_pack = self._load_or_create_universal_pack()
            from auditor_layer import audit_profile, save_audit_report
            report_obj = audit_profile(current_pack, base_dir=self._universal_profile_path().parent)
            report_path = save_audit_report(report_obj, self._universal_profile_path().with_name("profile_audit_report.txt"))
            messagebox.showinfo("Аудит профиля", report_obj.human_report(), parent=dialog)
            status_var.set(f"Аудит профиля: {report_obj.score}/100. Отчёт: {report_path.name}")
            self._set_status("Аудит профиля выполнен")
        except Exception as exc:
            messagebox.showerror("Аудит профиля", str(exc), parent=dialog)

    def render_custom_documents() -> None:
        out_dir = filedialog.askdirectory(title="Куда сохранить custom DOCX из профиля", parent=dialog)
        if not out_dir:
            return
        try:
            current_pack = self._load_or_create_universal_pack()
            from universal_generation import render_documents_from_pack, save_generation_report
            from medical_formatting import technical_report_path
            custom_ids = [
                doc.id for doc in current_pack.documents
                if str(doc.template).lower().endswith((".docx", ".docm"))
                and str(doc.template).replace("\\", "/").startswith("templates/")
            ]
            from regulatory_completion_blocks import apply_completion_values
            render_case = scan.patient_case()
            if completion_values_for_current_scan:
                render_case = apply_completion_values(render_case, completion_values_for_current_scan)
            result = render_documents_from_pack(
                pack=current_pack,
                case=render_case,
                document_ids=custom_ids,
                output_dir=out_dir,
                base_dir=self._universal_profile_path().parent,
                strict=True,
            )
            report_path = save_generation_report(result, technical_report_path(out_dir, "custom_generation_report.txt"))
            messagebox.showinfo("Custom DOCX", result.human_report(), parent=dialog)
            status_var.set(f"Создано custom-файлов: {len(result.created_files)}. Отчёт: {report_path}")
            self._set_status("Custom DOCX созданы из профиля")
        except Exception as exc:
            messagebox.showerror("Custom DOCX", str(exc), parent=dialog)

    def profile_builder_checklist() -> None:
        try:
            current_pack = self._load_or_create_universal_pack()
            from universal_profile_builder import profile_setup_checklist, specialty_presets
            presets_text = "\n".join("• " + preset.label for preset in specialty_presets())
            checklist = profile_setup_checklist(current_pack, base_dir=self._universal_profile_path().parent)
            messagebox.showinfo("Мастер профиля", checklist + "\n\nДоступные пресеты:\n" + presets_text, parent=dialog)
            status_var.set("Мастер профиля: checklist сформирован. Для нового врача используйте пресет, 3–5 исходных DOCX и его шаблоны.")
        except Exception as exc:
            messagebox.showerror("Мастер профиля", str(exc), parent=dialog)

    def regulatory_advice_for_loaded_document() -> None:
        try:
            current_pack = self._load_or_create_universal_pack()
            from regulatory_template_advisor import advise_document
            advice = advise_document(path, registry=current_pack.registry(), explicit_specialty=current_pack.specialty)
            show_soft_regulatory_advice(advice, source_label="Загруженный документ")
            self._set_status("Подсказки по документу по документу показаны")
        except Exception as exc:
            messagebox.showerror("Подсказки по документу", str(exc), parent=dialog)

    button_specs = [
        (4, "Запомнить выделение как правило", remember_selection, ACCENT_2, "#03101f"),
        (6, "Добавить DOCX-шаблон в профиль", add_template_to_profile, FIELD, TEXT),
        (7, "Создать кнопку документа", create_regular_document_button, FIELD, TEXT),
        (8, "Проверить профиль", validate_profile, FIELD, TEXT),
        (9, "Экспортировать medpack", export_profile, FIELD, TEXT),
        (10, "Импортировать medpack", import_profile, FIELD, TEXT),
        (11, "Отчёт готовности кнопок", readiness_report, FIELD, TEXT),
        (12, "Аудит профиля", audit_profile_layer, FIELD, TEXT),
        (13, "Создать custom DOCX", render_custom_documents, FIELD, TEXT),
        (14, "Мастер профиля / checklist", profile_builder_checklist, FIELD, TEXT),
        (15, "Подсказки по приказам", regulatory_advice_for_loaded_document, FIELD, TEXT),
    ]
    for row, label, command, bg, fg in button_specs:
        tk.Button(
            right,
            text=label,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=PANEL_3 if bg == FIELD else "#18a8dd",
            activeforeground=TEXT if bg == FIELD else "#03101f",
            relief="flat",
            font=self._font(9 if row != 4 else 10, "bold"),
            cursor="hand2",
            padx=self._px(10, 6),
            pady=self._px(6 if row != 4 else 8, 4),
        ).grid(row=row, column=0, sticky="ew", pady=(self._px(8 if row in {4, 6} else 6, 4), 0))
    dialog.transient(self.root)
    dialog.focus_set()
