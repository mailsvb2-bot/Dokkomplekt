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

def open_template_setup_center(app, *, first_run: bool = False) -> None:
    """Implement the open_template_setup_center workflow with validation, UI state updates and diagnostics."""
    self = app
    dialog = tk.Toplevel(self.root)
    dialog.title("Создать свои кнопки" if first_run else "Свои шаблоны врача")
    dialog.configure(bg=DEEP)
    dialog.geometry("860x640")
    dialog.minsize(760, 560)
    dialog.grid_columnconfigure(0, weight=1)
    dialog.grid_rowconfigure(2, weight=1)
    title = tk.Label(
        dialog,
        text="Создать свои кнопки" if first_run else "Свои шаблоны врача",
        bg=DEEP,
        fg=TEXT,
        font=self._font(17, "bold"),
        padx=14,
        pady=0,
    )
    title.grid(row=0, column=0, sticky="ew", pady=(14, 2))
    subtitle = tk.Label(
        dialog,
        text="Выберите Word-шаблоны врача. Программа прочитает название сверху каждого листа и создаст такие кнопки в блоке 03." if first_run else "Здесь врач загружает свои Word-шаблоны. Программа читает названия сверху листа и делает такие кнопки в блоке 03. Встроенных медицинских шаблонов нет.",
        bg=DEEP,
        fg=MUTED,
        font=self._font(10),
        wraplength=790,
        justify="center",
        padx=14,
        pady=0,
    )
    subtitle.grid(row=1, column=0, sticky="ew", pady=(0, 10))
    body = tk.Frame(dialog, bg=PANEL, padx=14, pady=14)
    body.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 14))
    body.grid_columnconfigure(0, weight=3)
    body.grid_columnconfigure(1, weight=2)
    body.grid_rowconfigure(1, weight=1)
    summary_var = tk.StringVar()
    status_var = tk.StringVar()
    summary = tk.Label(body, textvariable=summary_var, bg=PANEL, fg=TEXT, font=self._font(10, "bold"), justify="left", anchor="w", wraplength=500)
    summary.grid(row=0, column=0, sticky="ew", padx=(0, 12), pady=(0, 10))
    status = tk.Label(body, textvariable=status_var, bg=PANEL, fg=MUTED, font=self._font(9), justify="left", anchor="w", wraplength=500)
    status.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
    list_box = tk.Text(body, bg=FIELD, fg=TEXT, wrap="word", relief="flat", height=12, padx=10, pady=10, font=self._font(9))
    list_box.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
    buttons = tk.Frame(body, bg=PANEL)
    buttons.grid(row=0, column=1, rowspan=2, sticky="nsew")
    buttons.grid_columnconfigure(0, weight=1)
    def _active_profile_dir() -> Path:
        try:
            return self._settings_path.parent / "profiles"
        except Exception as exc:
            record_soft_exception("window_setup_center.active_profile_dir", exc)
            return Path.home() / "MedicalDiaryAutofill" / "profiles"
    def _mark_buttons_created(pack) -> None:
        principles = dict(getattr(pack, "workflow_principles", {}) or {})
        # Strict v2 marker; legacy flags alone must not unlock first launch.
        principles[BLOCK03_DOCTOR_SETUP_FLAG] = True
        principles["doctor_button_review_contract_version"] = DOCTOR_BUTTON_REVIEW_CONTRACT_VERSION
        for legacy_flag in BLOCK03_LEGACY_SETUP_FLAGS:
            principles[legacy_flag] = True
        pack.workflow_principles = principles
    def _save_pack(pack) -> None:
        from universal_profiles import save_document_pack
        save_document_pack(pack, self._universal_profile_path(), backup_reason="setup_center_save")
    def _refresh_main_tiles(context: str) -> None:
        try:
            self._refresh_custom_profile_tiles()
        except Exception as exc:
            record_soft_exception(f"window_mapper_dialog.refresh_main_tiles.{context}", exc)
    def _custom_documents(pack):
        from universal_main_documents import custom_documents_for_main_ui
        return custom_documents_for_main_ui(pack, base_dir=self._universal_profile_path().parent)
    def _prompt_folder_naming_after_buttons(message: str, *, log_key: str) -> None:
        try:
            from desktop_patient_folder import FOLDER_NAMING_SCHEMA_VERSION, normalize_folder_naming_settings
            raw = self._settings.get("folder_naming", {}) if isinstance(getattr(self, "_settings", None), dict) else {}
            current = normalize_folder_naming_settings(raw)
            confirmed = bool(current.get("doctor_confirmed")) and current.get("schema_version") == FOLDER_NAMING_SCHEMA_VERSION
            if not confirmed and messagebox.askyesno("Как называть сохранённую папку?", message, parent=dialog):
                self.configure_patient_folder_naming_dialog()
        except Exception as exc:
            record_soft_exception(log_key, exc)
    def refresh(message: str = "") -> None:
        try:
            pack = self._load_or_create_universal_pack()
            custom_docs = _custom_documents(pack)
            try:
                from universal_profiles import profile_scope_label
                scope = profile_scope_label(pack)
            except Exception as exc:
                record_soft_exception("window_setup_center.profile_scope", exc)
                scope = "Профиль врача"
            summary_var.set(
                "Настройка кнопок врача/отделения\n"
                + f"{scope}\n"
                + f"Выбрано шаблонов: {len(custom_docs)}"
            )
            list_box.configure(state="normal")
            list_box.delete("1.0", "end")
            if custom_docs:
                list_box.insert("end", "Созданные кнопки:\n\n")
                for idx, doc in enumerate(custom_docs, 1):
                    list_box.insert("end", f"{idx}. {doc.label}\n")
            else:
                list_box.insert(
                    "end",
                    "Выберите Word-шаблоны врача.\n\n"
                    "Перед созданием кнопок программа покажет таблицу проверки: файл, найденное название и название будущей кнопки. "
                    "Доктор сможет изменить названия и убрать лишние строки."
                )
            list_box.configure(state="disabled")
            status_var.set(message or "Готово. Выберите действие справа.")
        except Exception as exc:
            record_soft_exception("window_mapper_dialog.refresh_profile", exc)
            status_var.set(f"Не удалось прочитать профиль: {exc}")
    def show_tags_help() -> None:
        messagebox.showinfo(
            "Какие метки ставить в Word-шаблоне",
            "Откройте свой Word-шаблон и поставьте в нужные места такие метки:\n\n"
            "{{patient.fio}} — ФИО пациента\n"
            "{{case.number}} — номер истории болезни\n"
            "{{admission.date}} — дата поступления\n"
            "{{discharge.date}} — дата выписки\n"
            "{{diagnosis.main}} — диагноз\n"
            "{{treatment.plan}} — лечение\n"
            "{{patient.birth_date}} — дата рождения\n\n"
            "Пример в шаблоне:\n"
            "Пациент: {{patient.fio}}, история болезни № {{case.number}}.\n\n"
            "После этого добавьте этот DOCX через кнопку «Добавить шаблон и кнопку».",
            parent=dialog,
        )
    def new_profile() -> None:
        """Create either an individual doctor profile or a shared department profile."""
        popup = tk.Toplevel(dialog)
        popup.title("Новый профиль врача или отделения")
        popup.configure(bg=DEEP)
        popup.geometry("680x420")
        popup.grid_columnconfigure(0, weight=1)
        form = tk.Frame(popup, bg=PANEL, padx=12, pady=12)
        form.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        form.grid_columnconfigure(1, weight=1)
        name_var = tk.StringVar(value="Профиль врача")
        specialty_var = tk.StringVar(value="generic")
        kind_var = tk.StringVar(value="Профиль врача")
        department_var = tk.StringVar(value="")
        tk.Label(form, text="Тип профиля", bg=PANEL, fg=TEXT, font=self._font(10, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        ttk.Combobox(form, textvariable=kind_var, values=("Профиль врача", "Профиль отделения"), state="readonly", font=self._font(10)).grid(row=0, column=1, sticky="ew", pady=(0, 8))
        tk.Label(form, text="Название профиля", bg=PANEL, fg=TEXT, font=self._font(10, "bold")).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        tk.Entry(form, textvariable=name_var, bg=FIELD, fg=TEXT, insertbackground=ACCENT, relief="flat", font=self._font(10)).grid(row=1, column=1, sticky="ew", ipady=6, pady=(0, 8))
        tk.Label(form, text="Специальность", bg=PANEL, fg=TEXT, font=self._font(10, "bold")).grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        ttk.Combobox(form, textvariable=specialty_var, values=("generic", "therapy", "surgery", "neurology", "cardiology", "dentistry", "obstetrics", "intensive_care", "custom"), font=self._font(10)).grid(row=2, column=1, sticky="ew", pady=(0, 8))
        tk.Label(form, text="Отделение / кабинет", bg=PANEL, fg=TEXT, font=self._font(10, "bold")).grid(row=3, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        tk.Entry(form, textvariable=department_var, bg=FIELD, fg=TEXT, insertbackground=ACCENT, relief="flat", font=self._font(10)).grid(row=3, column=1, sticky="ew", ipady=6, pady=(0, 8))
        tk.Label(form, text="Профиль врача хранит личные кнопки. Профиль отделения можно перенести на несколько рабочих мест как общий набор шаблонов.", bg=PANEL, fg=MUTED, font=self._font(9), justify="left", wraplength=620).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 12))
        row = tk.Frame(form, bg=PANEL)
        row.grid(row=5, column=0, columnspan=2, sticky="ew")
        row.grid_columnconfigure(0, weight=1)
        row.grid_columnconfigure(1, weight=1)
        def save_new() -> None:
            try:
                from universal_profiles import default_document_pack, save_document_pack, mark_pack_as_department_profile, mark_pack_as_doctor_profile
                pack = default_document_pack()
                is_department = kind_var.get().strip() == "Профиль отделения"
                pack.name = name_var.get().strip() or ("Профиль отделения" if is_department else "Профиль врача")
                pack.specialty = specialty_var.get().strip() or "generic"
                pack.workflow_principles = {**getattr(pack, "workflow_principles", {}), "profile_scope": "specialty_neutral_medical", BLOCK03_DOCTOR_SETUP_FLAG: False, "block03_buttons_created_by_doctor": False, "first_run_create_buttons_completed": False}
                if is_department:
                    mark_pack_as_department_profile(pack, department_name=department_var.get().strip())
                else:
                    mark_pack_as_doctor_profile(pack, doctor_name=name_var.get().strip())
                target = available_profile_path(_active_profile_dir() / safe_profile_filename(pack.name))
                pack.pack_id = safe_profile_pack_id(pack.name, target)
                save_document_pack(pack, target, backup_reason="new_profile")
                self._set_universal_profile_path(target)
                _refresh_main_tiles("new_profile")
                popup.destroy()
                refresh("Создан новый профиль. Теперь добавьте его шаблоны.")
            except Exception as exc:
                messagebox.showerror("Новый профиль врача", str(exc), parent=popup)
        tk.Button(row, text="Создать профиль", command=save_new, bg=ACCENT_2, fg="#03101f", relief="flat", font=self._font(9, "bold"), padx=10, pady=8).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        tk.Button(row, text="Отмена", command=popup.destroy, bg=FIELD, fg=TEXT, relief="flat", font=self._font(9, "bold"), padx=10, pady=8).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        popup.transient(dialog)
        popup.grab_set()
        popup.focus_set()
    def open_profile() -> None:
        path = filedialog.askopenfilename(
            title="Открыть профиль врача",
            initialdir=_active_profile_dir(),
            filetypes=[("Профиль врача", "*.medpack.json *.json"), ("All files", "*.*")],
            parent=dialog,
        )
        if not path:
            return
        try:
            from universal_profiles import load_document_pack, save_document_pack
            opened_pack = load_document_pack(path)
            if getattr(opened_pack, "documents", ()): 
                _mark_buttons_created(opened_pack)
                save_document_pack(opened_pack, path, backup_reason="open_profile_mark")
            self._set_universal_profile_path(path)
            _refresh_main_tiles("open_profile")
            refresh("Профиль врача открыт. Кнопки блока 03 обновлены.")
        except Exception as exc:
            messagebox.showerror("Открыть профиль врача", str(exc), parent=dialog)
    def export_profile() -> None:
        target = filedialog.asksaveasfilename(
            title="Сохранить профиль врача для переноса",
            initialfile="MedicalDiaryAutofill_Profile.medpack.zip",
            defaultextension=".zip",
            filetypes=[("Medical profile", "*.zip *.medpack"), ("All files", "*.*")],
            parent=dialog,
        )
        if not target:
            return
        try:
            pack = self._load_or_create_universal_pack()
            from universal_template_engine import export_document_pack_zip
            exported = export_document_pack_zip(pack, target, template_base_dir=self._universal_profile_path().parent)
            refresh(f"Профиль экспортирован: {exported}")
        except Exception as exc:
            messagebox.showerror("Экспорт профиля", str(exc), parent=dialog)
    def import_profile() -> None:
        source = filedialog.askopenfilename(
            title="Импортировать профиль врача",
            filetypes=[("Medical profile", "*.zip *.medpack *.json"), ("All files", "*.*")],
            parent=dialog,
        )
        if not source:
            return
        try:
            source_path = Path(source).expanduser()
            profile_dir = _active_profile_dir()
            profile_dir.mkdir(parents=True, exist_ok=True)
            from universal_template_engine import import_document_pack_zip
            pack, _ = import_document_pack_zip(source_path, profile_dir)
            from universal_profiles import save_document_pack
            if getattr(pack, "documents", ()): 
                _mark_buttons_created(pack)
            target = available_profile_path(profile_dir / safe_profile_filename(pack.name or source_path.stem or "imported_profile"))
            save_document_pack(pack, target, backup_reason="import_profile")
            self._set_universal_profile_path(target)
            _refresh_main_tiles("import_profile")
            refresh("Профиль импортирован. Кнопки блока 03 обновлены.")
        except Exception as exc:
            messagebox.showerror("Импорт профиля", str(exc), parent=dialog)
    def check_profile() -> None:
        try:
            pack = self._load_or_create_universal_pack()
            from universal_template_engine import validate_document_pack
            from universal_generation import analyze_pack_readiness
            validation = validate_document_pack(pack, base_dir=self._universal_profile_path().parent)
            from universal_fields import PatientCase
            readiness = analyze_pack_readiness(pack, PatientCase(), base_dir=self._universal_profile_path().parent)
            messagebox.showinfo(
                "Проверка своих шаблонов",
                validation.human_report() + "\n\n" + readiness.human_report(),
                parent=dialog,
            )
            refresh("Проверка профиля выполнена.")
        except Exception as exc:
            messagebox.showerror("Проверка своих шаблонов", str(exc), parent=dialog)
    def teach_source_document() -> None:
        status_var.set("Сейчас откроется обучение чтению первичного документа: выберите пример DOCX, выделите нужный текст и нажмите «Запомнить».")
        open_universal_document_mapper(self)
        refresh("Если правило было сохранено, профиль уже обновлён.")
    def add_templates_fast() -> None:
        """Implement the add_templates_fast workflow with validation, UI state updates and diagnostics."""
        template_paths = filedialog.askopenfilenames(
            title="Выберите Word-шаблоны врача — можно сразу несколько",
            initialdir=self._dialog_initial_dir(DIR_PRIMARY_DOCUMENTS),
            filetypes=[("Word DOCX/DOCM", "*.docx *.docm"), ("All files", "*.*")],
            parent=dialog,
        )
        if not template_paths:
            return
        try:
            pack = self._load_or_create_universal_pack()
            language_id = self._effective_output_language() if hasattr(self, "_effective_output_language") else "ru"
            from universal_profile_builder import recognize_template_buttons
            recognitions = recognize_template_buttons(
                template_paths,
                preferred_language=language_id,
                ui_language="ru",
                specialty=pack.specialty,
            )
            if not recognitions:
                messagebox.showwarning("Свои шаблоны", "Не удалось распознать ни один Word-шаблон.", parent=dialog)
                return
            from layout_checklist import review_template_button_names
            from universal_main_documents import custom_documents_for_main_ui, is_builtin_document_id
            review = review_template_button_names(
                self,
                dialog,
                recognitions,
                first_run=first_run,
                existing_button_count=len(custom_documents_for_main_ui(pack, base_dir=self._universal_profile_path().parent)),
            )
            if not review:
                status_var.set("Кнопки не созданы. Доктор отменил таблицу проверки названий.")
                return
            current_pack = self._load_or_create_universal_pack()
            if review.replace_existing:
                current_pack.documents = tuple(doc for doc in current_pack.documents if is_builtin_document_id(doc.id))
            existing_labels = {str(doc.button_label or "").casefold() for doc in current_pack.documents}
            from personal_document_buttons import stable_document_id, unique_button_label
            from universal_template_engine import attach_template_to_pack, validate_template
            from universal_diary_templates import looks_like_diary_template
            from dataclasses import replace
            added_labels: list[str] = []
            warnings: list[str] = []
            for item in review.rows:
                requested_label = str(item.button_label or "Документ").strip() or Path(item.path).stem
                label = unique_button_label(requested_label, existing_labels)
                if label != requested_label:
                    warnings.append(f"«{requested_label}» уже есть в блоке 03 — новая кнопка названа «{label}», чтобы не потерять шаблон.")
                role_id = "" if str(item.role_id or "").strip().lower() == "unknown" else str(item.role_id or "").strip().lower()
                is_diary = looks_like_diary_template(item.path) or role_id == "daily_diary"
                document_id = stable_document_id(role_id or "unknown", label, item.path)
                spec, copied_to = attach_template_to_pack(
                    current_pack,
                    item.path,
                    self._universal_profile_path().parent,
                    button_label=label,
                    document_id=document_id,
                    category="diaries" if is_diary else "medical",
                    registry=current_pack.registry(),
                    role_id="daily_diary" if is_diary else role_id,
                    button_language=language_id,
                    source_language="auto",
                    button_label_source="doctor_review_table",
                )
                validation = validate_template(copied_to, required_fields=spec.required_fields, registry=current_pack.registry())
                if not validation.ok and not validation.placeholders:
                    warnings.append(f"«{label}»: кнопка создана, но в шаблоне пока нет меток {{patient.fio}}, {{case.number}} и т.п.; документ будет создан как копия шаблона, пока врач не добавит метки.")
                elif validation.warnings:
                    warnings.extend(f"«{label}»: {warning}" for warning in validation.warnings[:2])
                if is_diary:
                    from diary_schedule import DiaryScheduleSpec, infer_diary_schedule_from_docx
                    schedule = infer_diary_schedule_from_docx([copied_to])
                    if not schedule.day_offsets:
                        schedule = DiaryScheduleSpec("daily", (1, 2, 3, 5, 7, 14, 21, 28, 35, 42), (), 0.4, "doctor_review_table")
                    spec = replace(spec, category="diaries", role_id="daily_diary", diary_schedule=schedule.to_dict())
                    current_pack.add_document(spec)
                added_labels.append(label)
                existing_labels.add(label.casefold())
            if not added_labels:
                messagebox.showinfo("Свои шаблоны", "Новых кнопок не создано. В таблице не было подтверждённых строк.", parent=dialog)
                refresh("Новых кнопок не создано: врач не подтвердил строки.")
                return
            _mark_buttons_created(current_pack)
            _save_pack(current_pack)
            _refresh_main_tiles("doctor_review_table")
            # Doctor-facing result stays short; technical template warnings go to logs.
            if warnings:
                record_soft_exception(
                    "window_mapper_dialog.doctor_button_setup_warnings",
                    RuntimeError("; ".join(warnings[:12])),
                )
            result_text = f"Готово. Создано кнопок: {len(added_labels)}."
            if review.replace_existing:
                result_text += "\nСтарые кнопки заменены выбранными шаблонами."
            messagebox.showinfo("Готово", result_text, parent=dialog)
            _prompt_folder_naming_after_buttons(
                "Шаблоны добавлены. Теперь выберите, как программа будет называть папку пациента.\n\n"
                "Это настраивается один раз и потом применяется к обычному и пакетному созданию документов.",
                log_key="window_mapper_dialog.fast_folder_naming_prompt",
            )
            refresh(f"Созданы кнопки: {', '.join(added_labels)}")
        except Exception as exc:
            messagebox.showerror("Свои шаблоны", f"Не удалось быстро добавить шаблоны:\n\n{exc}", parent=dialog)
    def add_template_button() -> None:
        """Implement the add_template_button workflow with validation, UI state updates and diagnostics."""
        template_path = filedialog.askopenfilename(
            title="Выберите Word-шаблон, который должен стать кнопкой в блоке 03",
            initialdir=self._dialog_initial_dir(DIR_PRIMARY_DOCUMENTS),
            filetypes=[("Word DOCX/DOCM", "*.docx *.docm"), ("All files", "*.*")],
            parent=dialog,
        )
        if not template_path:
            return
        try:
            pack = self._load_or_create_universal_pack()
            from personal_document_buttons import localized_role_label, regular_document_role_choices, role_id_from_choice, suggest_button_label_for_template
            language_id = self._effective_output_language() if hasattr(self, "_effective_output_language") else "ru"
            suggestion = suggest_button_label_for_template(template_path, preferred_language=language_id, ui_language="ru", explicit_specialty=pack.specialty)
            popup = tk.Toplevel(dialog)
            popup.title("Новая кнопка в блоке 03")
            popup.configure(bg=DEEP)
            popup.geometry("700x420")
            popup.grid_columnconfigure(0, weight=1)
            tk.Label(
                popup,
                text="Проверьте название кнопки. Именно так она будет называться в блоке 03.",
                bg=DEEP,
                fg=TEXT,
                font=self._font(12, "bold"),
                wraplength=660,
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
            tk.Label(form, text="Что это за документ", bg=PANEL, fg=TEXT, font=self._font(9, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
            role_box = ttk.Combobox(form, textvariable=role_var, values=choices, state="readonly", font=self._font(10))
            role_box.grid(row=0, column=1, sticky="ew", pady=(0, 8))
            tk.Label(form, text="Название кнопки", bg=PANEL, fg=TEXT, font=self._font(9, "bold")).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
            tk.Entry(form, textvariable=label_var, bg=FIELD, fg=TEXT, insertbackground=ACCENT, relief="flat", font=self._font(11)).grid(row=1, column=1, sticky="ew", ipady=7, pady=(0, 8))
            tk.Label(
                form,
                text=f"Файл: {Path(template_path).name}\nЕсли название непонятное — просто напишите человечески: например «Осмотр невролога» или «Протокол операции».",
                bg=PANEL,
                fg=MUTED,
                font=self._font(9),
                justify="left",
                wraplength=640,
            ).grid(row=2, column=0, columnspan=2, sticky="ew")
            def sync_label(_event=None) -> None:
                role_id = role_id_from_choice(role_var.get())
                if role_id != "unknown":
                    label_var.set(localized_role_label(role_id, suggestion.language_id, fallback=label_var.get()))
            role_box.bind("<<ComboboxSelected>>", sync_label)
            row = tk.Frame(popup, bg=DEEP)
            row.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
            row.grid_columnconfigure(0, weight=1)
            row.grid_columnconfigure(1, weight=1)
            def save_button() -> None:
                """Implement the save_button workflow with validation, UI state updates and diagnostics."""
                try:
                    role_id = role_id_from_choice(role_var.get())
                    label = label_var.get().strip()
                    if not label:
                        raise ValueError("Введите понятное название кнопки.")
                    current_pack = self._load_or_create_universal_pack()
                    existing_labels = {str(doc.button_label or "").casefold() for doc in current_pack.documents}
                    label = unique_button_label(label, existing_labels)
                    from personal_document_buttons import suggest_button_label_for_template
                    final_suggestion = suggest_button_label_for_template(
                        template_path,
                        preferred_language=language_id,
                        ui_language="ru",
                        explicit_specialty=current_pack.specialty,
                        explicit_role_id=role_id,
                        fallback_label=label,
                    )
                    from universal_diary_templates import looks_like_diary_template
                    is_diary = looks_like_diary_template(template_path) or role_id == "daily_diary"
                    from universal_template_engine import attach_template_to_pack, validate_template
                    spec, copied_to = attach_template_to_pack(
                        current_pack,
                        template_path,
                        self._universal_profile_path().parent,
                        button_label=label,
                        document_id=final_suggestion.document_id,
                        category="diaries" if is_diary else "medical",
                        registry=current_pack.registry(),
                        role_id="daily_diary" if is_diary else role_id,
                        button_language=final_suggestion.language_id,
                        source_language=final_suggestion.source_language,
                        button_label_source="simple_ui_manual",
                    )
                    validation = validate_template(copied_to, required_fields=spec.required_fields, registry=current_pack.registry())
                    if not validation.ok and spec.category != "diaries":
                        raise ValueError(
                            "Шаблон добавлять рано: в нём нет понятных меток для заполнения.\n\n"
                            "Откройте Word-шаблон и поставьте метки вида {{patient.fio}}, {{case.number}}, {{diagnosis.main}}.\n"
                            "Нажмите «Какие метки ставить?» — там есть шпаргалка."
                        )
                    if is_diary:
                        from dataclasses import replace
                        from diary_schedule import DiaryScheduleSpec, infer_diary_schedule_from_docx
                        schedule = infer_diary_schedule_from_docx([copied_to])
                        if not schedule.day_offsets:
                            schedule = DiaryScheduleSpec("daily", (1, 2, 3, 5, 7, 14, 21, 28, 35, 42), (), 0.4, "simple_ui_default")
                        spec = replace(spec, category="diaries", role_id="daily_diary", diary_schedule=schedule.to_dict())
                        current_pack.add_document(spec)
                    _mark_buttons_created(current_pack)
                    _save_pack(current_pack)
                    _refresh_main_tiles("manual_add")
                    popup.destroy()
                    _prompt_folder_naming_after_buttons(
                        "Кнопка добавлена. Теперь выберите, как программа будет называть папку пациента.",
                        log_key="window_mapper_dialog.manual_folder_naming_prompt",
                    )
                    refresh(f"Кнопка «{label}» добавлена. Она уже должна быть видна в блоке 03.")
                except Exception as exc:
                    messagebox.showerror("Новая кнопка в блоке 03", str(exc), parent=popup)

            tk.Button(row, text="Добавить кнопку в блок 03", command=save_button, bg=ACCENT_2, fg="#03101f", relief="flat", font=self._font(10, "bold"), padx=10, pady=10).grid(row=0, column=0, sticky="ew", padx=(0, 6))
            tk.Button(row, text="Отмена", command=popup.destroy, bg=FIELD, fg=TEXT, relief="flat", font=self._font(9, "bold"), padx=10, pady=10).grid(row=0, column=1, sticky="ew", padx=(6, 0))
            popup.transient(dialog)
            popup.grab_set()
            popup.focus_set()
        except Exception as exc:
            messagebox.showerror("Добавить шаблон и кнопку", str(exc), parent=dialog)
    def open_color_mouse_scanner() -> None:
        from dialog_fields_core import open_visual_scanner_dialog
        open_visual_scanner_dialog(self, parent=dialog, refresh=refresh, default_field_id="labs.results")

    def open_external_word_scanner() -> None:
        from dialog_fields_core import open_external_word_selection_scanner_dialog
        open_external_word_selection_scanner_dialog(self, parent=dialog, refresh=refresh, default_field_id="diagnosis.main")

    def _editable_profile_documents(pack):
        try:
            from universal_main_documents import is_builtin_document_id
            return tuple(doc for doc in pack.documents if not is_builtin_document_id(getattr(doc, "id", "")))
        except Exception as exc:
            record_soft_exception("window_setup_center.editable_documents", exc)
            return tuple(pack.documents)

    def _document_choice_rows(pack):
        docs = _editable_profile_documents(pack)
        rows = []
        for index, doc in enumerate(docs, 1):
            label = str(getattr(doc, "button_label", "") or getattr(doc, "id", "") or "Документ").strip()
            role = str(getattr(doc, "role_id", "") or "").strip()
            suffix = f" [{role}]" if role else ""
            rows.append((f"{index}. {label}{suffix}", doc))
        return rows

    def _sync_button_created_flags(pack) -> None:
        docs = _editable_profile_documents(pack)
        principles = {**dict(getattr(pack, "workflow_principles", {}) or {})}
        has_docs = bool(docs)
        principles[BLOCK03_DOCTOR_SETUP_FLAG] = has_docs
        principles["block03_buttons_created_by_doctor"] = has_docs
        principles["first_run_create_buttons_completed"] = has_docs
        principles["doctor_button_review_contract_version"] = DOCTOR_BUTTON_REVIEW_CONTRACT_VERSION if has_docs else ""
        pack.workflow_principles = principles

    def rename_created_button() -> None:
        """Open a safe UI for renaming one doctor-created block-03 button.

        This edits only the profile-owned label.  It deliberately keeps the
        internal document id, DOCX template reference, role and required fields
        stable so saved generation behavior is not accidentally changed by a
        visual rename.
        """
        try:
            current_pack = self._load_or_create_universal_pack()
            rows = _document_choice_rows(current_pack)
            if not rows:
                messagebox.showinfo("Переименовать кнопку", "В профиле пока нет созданных кнопок.", parent=dialog)
                return
            popup = tk.Toplevel(dialog)
            popup.title("Переименовать созданную кнопку")
            popup.configure(bg=DEEP)
            popup.geometry("720x360")
            popup.grid_columnconfigure(0, weight=1)
            tk.Label(
                popup,
                text="Выберите созданную кнопку и напишите новое название. Шаблон DOCX, роль документа и заполнение не меняются.",
                bg=DEEP,
                fg=TEXT,
                font=self._font(12, "bold"),
                padx=12,
                pady=12,
                wraplength=680,
                justify="left",
            ).grid(row=0, column=0, sticky="ew")
            form = tk.Frame(popup, bg=PANEL, padx=12, pady=12)
            form.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
            form.grid_columnconfigure(1, weight=1)
            choices = [row[0] for row in rows]
            selected_var = tk.StringVar(value=choices[0])
            label_var = tk.StringVar(value=str(rows[0][1].button_label or ""))
            tk.Label(form, text="Кнопка", bg=PANEL, fg=TEXT, font=self._font(9, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
            combo = ttk.Combobox(form, textvariable=selected_var, values=choices, state="readonly", font=self._font(10))
            combo.grid(row=0, column=1, sticky="ew", pady=(0, 8))
            tk.Label(form, text="Новое название", bg=PANEL, fg=TEXT, font=self._font(9, "bold")).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
            entry = tk.Entry(form, textvariable=label_var, bg=FIELD, fg=TEXT, insertbackground=ACCENT, relief="flat", font=self._font(11))
            entry.grid(row=1, column=1, sticky="ew", ipady=7, pady=(0, 8))

            def selected_doc():
                index = choices.index(selected_var.get())
                return rows[index][1]

            def on_selected(_event=None) -> None:
                try:
                    label_var.set(str(selected_doc().button_label or ""))
                    entry.focus_set()
                    entry.selection_range(0, "end")
                except Exception as exc:
                    record_soft_exception("window_setup_center.rename_select", exc)

            combo.bind("<<ComboboxSelected>>", on_selected)
            buttons_row = tk.Frame(popup, bg=DEEP)
            buttons_row.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
            buttons_row.grid_columnconfigure(0, weight=1)
            buttons_row.grid_columnconfigure(1, weight=1)

            def save_rename() -> None:
                try:
                    doc = selected_doc()
                    from universal_profiles import rename_document_button

                    updated = rename_document_button(current_pack, doc.id, label_var.get())
                    current_pack.documents = tuple(updated if old.id == updated.id else old for old in current_pack.documents)
                    _sync_button_created_flags(current_pack)
                    _save_pack(current_pack)
                    _refresh_main_tiles("rename_button")
                    popup.destroy()
                    refresh(f"Кнопка переименована: {updated.button_label}")
                except Exception as exc:
                    messagebox.showerror("Переименовать кнопку", str(exc), parent=popup)

            tk.Button(buttons_row, text="Сохранить название", command=save_rename, bg=ACCENT_2, fg="#03101f", relief="flat", font=self._font(10, "bold"), padx=10, pady=9).grid(row=0, column=0, sticky="ew", padx=(0, 6))
            tk.Button(buttons_row, text="Отмена", command=popup.destroy, bg=FIELD, fg=TEXT, relief="flat", font=self._font(9, "bold"), padx=10, pady=9).grid(row=0, column=1, sticky="ew", padx=(6, 0))
            popup.transient(dialog)
            popup.grab_set()
            entry.focus_set()
            entry.selection_range(0, "end")
        except Exception as exc:
            messagebox.showerror("Переименовать созданную кнопку", str(exc), parent=dialog)

    def delete_created_button() -> None:
        """Open a safe UI for removing one doctor-created block-03 button.

        The operation removes the document spec from the active profile so the
        button disappears from block 03, but it does not delete the copied DOCX
        template file.  This avoids irreversible data loss and lets the doctor
        add the same template again later if needed.
        """
        try:
            current_pack = self._load_or_create_universal_pack()
            rows = _document_choice_rows(current_pack)
            if not rows:
                messagebox.showinfo("Удалить кнопку", "В профиле пока нет созданных кнопок.", parent=dialog)
                return
            popup = tk.Toplevel(dialog)
            popup.title("Удалить созданную кнопку")
            popup.configure(bg=DEEP)
            popup.geometry("720x340")
            popup.grid_columnconfigure(0, weight=1)
            tk.Label(
                popup,
                text="Выберите кнопку, которую нужно убрать из блока 03. DOCX-шаблон останется в папке профиля, чтобы его можно было добавить снова.",
                bg=DEEP,
                fg=TEXT,
                font=self._font(12, "bold"),
                padx=12,
                pady=12,
                wraplength=680,
                justify="left",
            ).grid(row=0, column=0, sticky="ew")
            form = tk.Frame(popup, bg=PANEL, padx=12, pady=12)
            form.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
            form.grid_columnconfigure(1, weight=1)
            choices = [row[0] for row in rows]
            selected_var = tk.StringVar(value=choices[0])
            tk.Label(form, text="Кнопка", bg=PANEL, fg=TEXT, font=self._font(9, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
            ttk.Combobox(form, textvariable=selected_var, values=choices, state="readonly", font=self._font(10)).grid(row=0, column=1, sticky="ew", pady=(0, 8))
            buttons_row = tk.Frame(popup, bg=DEEP)
            buttons_row.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
            buttons_row.grid_columnconfigure(0, weight=1)
            buttons_row.grid_columnconfigure(1, weight=1)

            def selected_doc():
                index = choices.index(selected_var.get())
                return rows[index][1]

            def delete_selected() -> None:
                try:
                    doc = selected_doc()
                    label = str(doc.button_label or doc.id)
                    if not messagebox.askyesno("Удалить кнопку", f"Убрать кнопку «{label}» из блока 03?", parent=popup):
                        return
                    from universal_profiles import remove_document_button

                    removed, kept = remove_document_button(current_pack, doc.id)
                    current_pack.documents = kept
                    _sync_button_created_flags(current_pack)
                    _save_pack(current_pack)
                    _refresh_main_tiles("delete_button")
                    popup.destroy()
                    refresh(f"Кнопка удалена: {removed.button_label}")
                except Exception as exc:
                    messagebox.showerror("Удалить кнопку", str(exc), parent=popup)

            tk.Button(buttons_row, text="Удалить кнопку", command=delete_selected, bg=PANEL_3, fg=TEXT, relief="flat", font=self._font(10, "bold"), padx=10, pady=9).grid(row=0, column=0, sticky="ew", padx=(0, 6))
            tk.Button(buttons_row, text="Отмена", command=popup.destroy, bg=FIELD, fg=TEXT, relief="flat", font=self._font(9, "bold"), padx=10, pady=9).grid(row=0, column=1, sticky="ew", padx=(6, 0))
            popup.transient(dialog)
            popup.grab_set()
            popup.focus_set()
        except Exception as exc:
            messagebox.showerror("Удалить созданную кнопку", str(exc), parent=dialog)

    def configure_required_popup_fields() -> None:
        from dialog_fields_popup import configure_required_popup_fields_dialog
        configure_required_popup_fields_dialog(self, dialog, save_pack=_save_pack, refresh_main_tiles=_refresh_main_tiles, refresh_view=refresh)

    def add_button(text: str, command, *, primary: bool = False, row: int = 0) -> None:
        tk.Button(
            buttons,
            text=text,
            command=command,
            bg=ACCENT_2 if primary else FIELD,
            fg="#03101f" if primary else TEXT,
            activebackground="#18a8dd" if primary else PANEL_3,
            activeforeground="#03101f" if primary else TEXT,
            relief="flat",
            font=self._font(10 if primary else 9, "bold"),
            cursor="hand2",
            padx=10,
            pady=9 if primary else 6,
            wraplength=260,
            justify="center",
        ).grid(row=row, column=0, sticky="ew", pady=(0, 6))

    if first_run:
        add_button("Выбрать Word-шаблоны и создать кнопки", add_templates_fast, primary=True, row=0)
        add_button("Переименовать созданную кнопку", rename_created_button, row=1)
        add_button("Удалить созданную кнопку", delete_created_button, row=2)
        add_button("Закрыть", dialog.destroy, row=3)
    else:
        add_button("Выбрать Word-шаблоны и создать кнопки", add_templates_fast, primary=True, row=0)
        add_button("Переименовать созданную кнопку", rename_created_button, row=1)
        add_button("Удалить созданную кнопку", delete_created_button, row=2)
        add_button("Как называть папку пациента", self.configure_patient_folder_naming_dialog, row=3)
        add_button("Добавить один шаблон вручную", add_template_button, row=4)
        add_button("Обязательные поля popup", configure_required_popup_fields, row=5)
        add_button("2. Научить читать первичный документ", teach_source_document, row=6)
        add_button("Сканер Word: открыть и взять выделение", open_external_word_scanner, row=7)
        add_button("Цветной сканер внутри программы", open_color_mouse_scanner, row=8)
        add_button("3. Какие метки ставить в Word?", show_tags_help, row=9)
        add_button("Новый профиль врача", new_profile, row=10)
        add_button("Открыть профиль врача", open_profile, row=11)
        add_button("Импорт профиля", import_profile, row=12)
        add_button("Экспорт профиля", export_profile, row=13)
        add_button("Проверить свои шаблоны", check_profile, row=14)
        add_button("Закрыть", dialog.destroy, row=15)

    refresh()
    dialog.transient(self.root)
    dialog.focus_set()
    if first_run:
        dialog.after(250, add_templates_fast)

