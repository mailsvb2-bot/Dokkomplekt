from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from diagnostic_logging import record_soft_exception
from layout_action_bar import LayoutActionBarMixin
from layout_checklist import FIRST_RUN_CREATE_BUTTON_LABEL, LayoutChecklistMixin, _doctor_buttons_setup_completed
from layout_sources import LayoutSourcesMixin

UI_BG = "#f3f6fb"
UI_PANEL = "#ffffff"
UI_SOFT = "#f7faff"
UI_BLUE_SOFT = "#eef5ff"
UI_LINE = "#d8e2ef"
UI_TEXT = "#172033"
UI_MUTED = "#667085"
UI_BLUE = "#2f73e8"
UI_BLUE_DARK = "#1f5fd0"
UI_GREEN = "#14804a"
UI_WARN = "#b7791f"
UI_RED = "#c2415d"


class LayoutWizardSurfaceMixin:
    def _build_wizard_surface(self, parent: tk.Frame) -> None:
        """Build a simple doctor-facing workflow UI over the existing backend callbacks."""
        self._simple_doctor_ui_active = True
        parent.configure(bg=UI_BG)
        parent.grid_columnconfigure(0, minsize=self._px(160, 122))
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(1, weight=1)
        self._doctor_header(parent)
        self._doctor_stepper(parent)
        self._doctor_main(parent)

    def _doctor_header(self, parent: tk.Frame) -> None:
        header = tk.Frame(parent, bg=UI_BG)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, self._px(12, 7)))
        header.grid_columnconfigure(0, weight=1)
        self._bind_window_drag(header)
        title_box = tk.Frame(header, bg=UI_BG)
        title_box.grid(row=0, column=0, sticky="w")
        self._bind_window_drag(title_box)
        logo = tk.Canvas(title_box, width=self._px(34, 26), height=self._px(34, 26), bg=UI_BG, highlightthickness=0)
        logo.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, self._px(11, 6)))
        self._draw_doctor_logo(logo)
        tk.Label(title_box, text="Dokkomplekt", bg=UI_BG, fg=UI_TEXT, font=self._font(21, "bold")).grid(row=0, column=1, sticky="w")
        tk.Label(title_box, text="Документы врача без лишних шагов", bg=UI_BG, fg=UI_MUTED, font=self._font(10)).grid(row=1, column=1, sticky="w")
        actions = tk.Frame(header, bg=UI_BG)
        actions.grid(row=0, column=1, sticky="e")
        for col, (text, command) in enumerate((("Лицензия", lambda: self._doctor_call("show_product_license_dialog")), ("Профиль", self._open_universal_document_mapper), ("Папка вывода", self.choose_output_dir), ("Язык", lambda: self._doctor_call("_open_language_settings")))):
            self._doctor_button(actions, text, command).grid(row=0, column=col, padx=(0, self._px(7, 4)))
        self._window_control_button(actions, "−", self._minimize_window).grid(row=0, column=4)
        self._window_control_button(actions, "□", self._toggle_maximize).grid(row=0, column=5)
        self._window_control_button(actions, "×", self.root.destroy, danger=True).grid(row=0, column=6)

    def _doctor_stepper(self, parent: tk.Frame) -> None:
        rail = tk.Frame(parent, bg=UI_BG)
        rail.grid(row=1, column=0, sticky="nsw", padx=(0, self._px(16, 9)))
        steps = (("01", "Документ", "Загрузите первичный файл"), ("02", "Данные", "Проверьте найденное"), ("03", "Создать", "Выберите документы"), ("04", "Готово", "Сохранить и печатать"))
        for idx, (num, title, hint) in enumerate(steps):
            item = tk.Frame(rail, bg=UI_BG)
            item.grid(row=idx, column=0, sticky="ew", pady=(0, self._px(20 if idx < 3 else 0, 10)))
            active = idx == 0
            tk.Label(item, text=num, width=4, bg=UI_BLUE_SOFT if active else UI_PANEL, fg=UI_BLUE if active else UI_MUTED, highlightbackground=UI_BLUE if active else UI_LINE, highlightthickness=2 if active else 1, font=self._font(15, "bold"), pady=self._px(10, 6)).grid(row=0, column=0, sticky="n", padx=(0, self._px(9, 5)))
            text = tk.Frame(item, bg=UI_BG)
            text.grid(row=0, column=1, sticky="w")
            tk.Label(text, text=title, bg=UI_BG, fg=UI_BLUE if active else UI_MUTED, font=self._font(11, "bold"), anchor="w").grid(row=0, column=0, sticky="w")
            tk.Label(text, text=hint, bg=UI_BG, fg=UI_MUTED, font=self._font(8), anchor="w", justify="left", wraplength=self._px(92, 72)).grid(row=1, column=0, sticky="w")

    def _doctor_main(self, parent: tk.Frame) -> None:
        main = tk.Frame(parent, bg=UI_BG)
        main.grid(row=1, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=3)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(1, weight=1)
        self._first_run_card(main)
        self._upload_card(main)
        self._patient_data_card(main)
        self._documents_card(main)
        self._final_card(main)
        self.status_label = self._status_bar_label
        self.progress = ttk.Progressbar(main, mode="indeterminate", length=180)

    def _first_run_card(self, parent: tk.Frame) -> None:
        card = self._panel(parent)
        card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, self._px(12, 7)))
        card.grid_columnconfigure(0, weight=1)
        tk.Label(card, text="Первый контакт с программой", bg=UI_PANEL, fg=UI_TEXT, font=self._font(13, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        tk.Label(card, text="Загрузите свои Word-шаблоны документов. Программа создаст из них кнопки, а потом будет сама заполнять выбранные документы по данным пациента.", bg=UI_PANEL, fg=UI_MUTED, font=self._font(9), anchor="w", justify="left", wraplength=self._px(760, 520)).grid(row=1, column=0, sticky="ew", pady=(2, 0))
        buttons = tk.Frame(card, bg=UI_PANEL)
        buttons.grid(row=0, column=1, rowspan=2, sticky="e", padx=(self._px(12, 8), 0))
        self._doctor_primary(buttons, "Создать кнопки", self._open_first_run_create_buttons_popup).grid(row=0, column=0, padx=(0, self._px(7, 4)))
        self._doctor_button(buttons, "Выписанные пациенты", lambda: self._doctor_call("_ask_create_desktop_intake_folder")).grid(row=0, column=1, padx=(0, self._px(7, 4)))
        self._doctor_button(buttons, "Подпапки", self.configure_patient_folder_naming_dialog).grid(row=0, column=2)

    def _upload_card(self, parent: tk.Frame) -> None:
        card = self._panel(parent)
        card.grid(row=1, column=0, sticky="nsew", padx=(0, self._px(8, 5)))
        card.grid_columnconfigure(0, weight=1)
        tk.Label(card, text="Загрузите документ", bg=UI_PANEL, fg=UI_TEXT, font=self._font(22, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        tk.Label(card, text="DOCX или DOCM. После выбора программа очистит данные прошлого пациента, распознает новый документ и подготовит поля для проверки.", bg=UI_PANEL, fg=UI_MUTED, font=self._font(10), anchor="w", justify="left", wraplength=self._px(620, 420)).grid(row=1, column=0, sticky="ew", pady=(self._px(4, 2), self._px(12, 6)))
        drop = tk.Frame(card, bg=UI_SOFT, highlightbackground=UI_LINE, highlightthickness=1, height=self._px(170, 118), cursor="hand2")
        drop.grid(row=2, column=0, sticky="ew")
        drop.grid_propagate(False)
        drop.grid_columnconfigure(0, weight=1)
        icon = tk.Canvas(drop, width=self._px(70, 48), height=self._px(50, 36), bg=UI_SOFT, highlightthickness=0)
        icon.grid(row=0, column=0, pady=(self._px(24, 14), self._px(4, 2)))
        self._draw_upload_icon(icon)
        tk.Label(drop, text="Перетащите сюда первичный документ", bg=UI_SOFT, fg=UI_TEXT, font=self._font(13, "bold")).grid(row=1, column=0, sticky="ew")
        self.primary_drop_hint_label = tk.Label(drop, text="или нажмите «Выбрать файл»", bg=UI_SOFT, fg=UI_MUTED, font=self._font(9))
        self.primary_drop_hint_label.grid(row=2, column=0, sticky="ew", pady=(2, 0))
        self.primary_selected_status_var = tk.StringVar(value="")
        self.primary_selected_status_label = tk.Label(drop, textvariable=self.primary_selected_status_var, bg=UI_SOFT, fg=UI_GREEN, font=self._font(9, "bold"), wraplength=self._px(560, 380))
        self.primary_selected_status_label.grid(row=3, column=0, sticky="ew", pady=(self._px(4, 2), 0))
        for widget in (drop, icon, self.primary_drop_hint_label, self.primary_selected_status_label):
            widget.bind("<Button-1>", lambda _event: self.choose_navigation())
        self.drop_zone = drop
        self._drop_widgets = [drop, icon, self.primary_drop_hint_label, self.primary_selected_status_label]
        actions = tk.Frame(card, bg=UI_PANEL)
        actions.grid(row=3, column=0, sticky="ew", pady=(self._px(14, 8), 0))
        self._doctor_primary(actions, "Выбрать файл", self.choose_navigation, wide=True).grid(row=0, column=0, sticky="w")
        self._doctor_button(actions, "Изменить тип", self._toggle_primary_document_type).grid(row=0, column=1, sticky="w", padx=(self._px(8, 5), 0))
        tk.Label(actions, textvariable=self.primary_document_type_display_var, bg=UI_BLUE_SOFT, fg=UI_TEXT, highlightbackground=UI_LINE, highlightthickness=1, font=self._font(9), padx=self._px(10, 6), pady=self._px(6, 3)).grid(row=0, column=2, sticky="w", padx=(self._px(8, 5), 0))
        next_box = tk.Frame(card, bg=UI_SOFT, highlightbackground=UI_LINE, highlightthickness=1, padx=self._px(12, 8), pady=self._px(9, 6))
        next_box.grid(row=4, column=0, sticky="ew", pady=(self._px(14, 8), 0))
        tk.Label(next_box, text="Что будет дальше", bg=UI_SOFT, fg=UI_TEXT, font=self._font(11, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        tk.Label(next_box, text="1. Проверим данные пациента\n2. Спросим только недостающие поля\n3. Создадим выбранные документы", bg=UI_SOFT, fg=UI_MUTED, font=self._font(9), justify="left", anchor="w").grid(row=1, column=0, sticky="ew", pady=(self._px(4, 2), 0))

    def _patient_data_card(self, parent: tk.Frame) -> None:
        card = self._panel(parent)
        card.grid(row=1, column=1, sticky="nsew")
        card.grid_columnconfigure(1, weight=1)
        tk.Label(card, text="Найденные данные", bg=UI_PANEL, fg=UI_TEXT, font=self._font(15, "bold"), anchor="w").grid(row=0, column=0, columnspan=2, sticky="ew")
        fields = (("ФИО / файл", self.patient_name_var), ("История болезни", self.case_number_var), ("Поступление", self.admission_date_var), ("Выписка", self.discharge_date_var), ("Диагноз", self.diagnosis_var), ("Больничный", self.expert_sick_leave_display_var))
        for row, (label, var) in enumerate(fields, start=1):
            tk.Label(card, text=label, bg=UI_PANEL, fg=UI_MUTED, font=self._font(9), anchor="w").grid(row=row, column=0, sticky="w", pady=self._px(4, 2), padx=(0, self._px(8, 4)))
            tk.Label(card, textvariable=var, bg=UI_SOFT, fg=UI_TEXT, highlightbackground=UI_LINE, highlightthickness=1, font=self._font(9), anchor="w", padx=self._px(8, 5), pady=self._px(5, 3), wraplength=self._px(330, 230)).grid(row=row, column=1, sticky="ew", pady=self._px(4, 2))
        controls = tk.Frame(card, bg=UI_PANEL)
        controls.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(self._px(12, 7), 0))
        self._doctor_button(controls, "Проверить / исправить", self.show_found_patient_data).grid(row=0, column=0, sticky="w", padx=(0, self._px(7, 4)))
        self._doctor_button(controls, "Папка пациента", self.configure_patient_folder_naming_dialog).grid(row=0, column=1, sticky="w")

    def _documents_card(self, parent: tk.Frame) -> None:
        card = self._panel(parent)
        card.grid(row=2, column=0, sticky="nsew", padx=(0, self._px(8, 5)), pady=(self._px(12, 7), 0))
        card.grid_columnconfigure(0, weight=1)
        top = tk.Frame(card, bg=UI_PANEL)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        tk.Label(top, text="Какие документы создать?", bg=UI_PANEL, fg=UI_TEXT, font=self._font(15, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        self.selected_outputs_count_var = tk.StringVar(value="Выбрано: 0")
        tk.Label(top, textvariable=self.selected_outputs_count_var, bg=UI_PANEL, fg=UI_MUTED, font=self._font(9, "bold")).grid(row=0, column=1, sticky="e", padx=(self._px(8, 4), 0))
        toolbar = tk.Frame(card, bg=UI_PANEL)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(self._px(8, 5), self._px(8, 5)))
        self._doctor_button(toolbar, "Выбрать всё", self._simple_select_all_outputs).grid(row=0, column=0, padx=(0, self._px(7, 4)))
        self._doctor_button(toolbar, "Снять всё", self._simple_clear_outputs).grid(row=0, column=1, padx=(0, self._px(7, 4)))
        self._doctor_button(toolbar, "Создать кнопки", self._open_first_run_create_buttons_popup).grid(row=0, column=2)
        self._custom_profile_tiles_container = tk.Frame(card, bg=UI_PANEL)
        self._custom_profile_tiles_container.grid(row=2, column=0, sticky="nsew")
        self._diary_frequency_container = tk.Frame(card, bg=UI_PANEL)
        self._diary_frequency_container.grid(row=3, column=0, sticky="ew", pady=(self._px(8, 5), 0))
        self._simple_refresh_doctor_documents()
        inputs = tk.Frame(card, bg=UI_SOFT, highlightbackground=UI_LINE, highlightthickness=1, padx=self._px(10, 6), pady=self._px(8, 5))
        inputs.grid(row=4, column=0, sticky="ew", pady=(self._px(12, 7), 0))
        inputs.grid_columnconfigure(1, weight=1)
        tk.Label(inputs, text="Дополнительные файлы", bg=UI_SOFT, fg=UI_TEXT, font=self._font(10, "bold"), anchor="w").grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, self._px(5, 3)))
        self._simple_file_row(inputs, 1, "Файл ЭПИ", self.epi_path_var, self.choose_epi, "ЭПИ")
        self.status_files_label = self._simple_file_row(inputs, 2, "Дневники: тексты", None, self.choose_status_files, "Тексты")
        self.diary_files_label = self._simple_file_row(inputs, 3, "Дневники: даты", None, self.choose_diary_files, "Даты")
        self._refresh_diary_labels()

    def _final_card(self, parent: tk.Frame) -> None:
        card = self._panel(parent)
        card.grid(row=2, column=1, sticky="nsew", pady=(self._px(12, 7), 0))
        card.grid_columnconfigure(1, weight=1)
        tk.Label(card, text="Создать документы", bg=UI_PANEL, fg=UI_TEXT, font=self._font(15, "bold"), anchor="w").grid(row=0, column=0, columnspan=3, sticky="ew")
        tk.Label(card, text="Папка", bg=UI_PANEL, fg=UI_MUTED, font=self._font(9)).grid(row=1, column=0, sticky="w", pady=(self._px(12, 7), 0), padx=(0, self._px(8, 5)))
        tk.Entry(card, textvariable=self.output_dir_var, bg=UI_SOFT, fg=UI_TEXT, relief="flat", highlightbackground=UI_LINE, highlightthickness=1, font=self._font(9)).grid(row=1, column=1, sticky="ew", pady=(self._px(12, 7), 0), ipady=self._px(4, 2))
        self._doctor_button(card, "Выбрать", self.choose_output_dir).grid(row=1, column=2, pady=(self._px(12, 7), 0), padx=(self._px(8, 5), 0))
        tk.Label(card, text="Принтер", bg=UI_PANEL, fg=UI_MUTED, font=self._font(9)).grid(row=2, column=0, sticky="w", pady=(self._px(8, 5), 0), padx=(0, self._px(8, 5)))
        self.printer_combo = ttk.Combobox(card, textvariable=self.printer_var, values=[], state="readonly", font=self._font(9))
        self.printer_combo.grid(row=2, column=1, sticky="ew", pady=(self._px(8, 5), 0), ipady=self._px(2, 1))
        self.printer_combo.bind("<<ComboboxSelected>>", self._on_printer_selected)
        self._doctor_button(card, "Обновить", self.refresh_printers).grid(row=2, column=2, pady=(self._px(8, 5), 0), padx=(self._px(8, 5), 0))
        self._doctor_primary(card, "Создать и сохранить", lambda: self.create_selected_outputs(print_after=False), wide=True).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(self._px(18, 10), self._px(8, 5)))
        self._doctor_primary(card, "Создать, сохранить, распечатать", lambda: self.create_selected_outputs(print_after=True), wide=True).grid(row=4, column=0, columnspan=3, sticky="ew")
        more = tk.Frame(card, bg=UI_PANEL)
        more.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(self._px(14, 8), 0))
        for col, (text, command) in enumerate((("Проверка", self.show_found_patient_data), ("Диагностика", self.show_installation_diagnostics_dialog), ("Пакет", self.batch_generate_documents_dialog), ("Версия", self.check_updates_dialog), ("Сброс", self.reset_settings_dialog))):
            self._doctor_button(more, text, command).grid(row=0, column=col, padx=(0, self._px(6, 3)))

    def _panel(self, parent: tk.Widget) -> tk.Frame:
        return tk.Frame(parent, bg=UI_PANEL, highlightbackground=UI_LINE, highlightthickness=1, padx=self._px(18, 10), pady=self._px(15, 9))

    def _doctor_primary(self, parent: tk.Widget, text: str, command, *, wide: bool = False) -> tk.Button:
        return tk.Button(parent, text=text, command=command, bg=UI_BLUE, fg="#ffffff", activebackground=UI_BLUE_DARK, activeforeground="#ffffff", relief="flat", bd=0, padx=self._px(18 if wide else 15, 10), pady=self._px(9, 6), font=self._font(10, "bold"), cursor="hand2")

    def _doctor_button(self, parent: tk.Widget, text: str, command) -> tk.Button:
        return tk.Button(parent, text=text, command=command, bg=UI_BLUE_SOFT, fg=UI_BLUE, activebackground="#dfeaff", activeforeground=UI_BLUE_DARK, relief="flat", bd=0, highlightthickness=1, highlightbackground=UI_LINE, padx=self._px(12, 8), pady=self._px(6, 4), font=self._font(9, "bold"), cursor="hand2")

    def _simple_file_row(self, parent: tk.Frame, row: int, label: str, variable, command, button: str) -> tk.Label:
        tk.Label(parent, text=label, bg=UI_SOFT, fg=UI_MUTED, font=self._font(9), anchor="w").grid(row=row, column=0, sticky="w", pady=self._px(4, 2), padx=(0, self._px(8, 5)))
        value = tk.Label(parent, textvariable=variable if variable is not None else None, text="не выбрано" if variable is None else "", bg=UI_PANEL, fg=UI_TEXT, highlightbackground=UI_LINE, highlightthickness=1, font=self._font(8), anchor="w", padx=self._px(8, 5), pady=self._px(5, 3))
        value.grid(row=row, column=1, sticky="ew", pady=self._px(4, 2))
        self._doctor_button(parent, button, command).grid(row=row, column=2, padx=(self._px(8, 5), 0), pady=self._px(4, 2))
        return value

    def _simple_refresh_doctor_documents(self) -> None:
        container = getattr(self, "_custom_profile_tiles_container", None)
        if container is None:
            return
        for child in container.winfo_children():
            child.destroy()
        try:
            from universal_main_documents import custom_documents_for_main_ui
            pack = self._load_or_create_universal_pack()
            docs = list(custom_documents_for_main_ui(pack, base_dir=self._universal_profile_path().parent)) if _doctor_buttons_setup_completed(pack) else []
        except Exception as exc:
            record_soft_exception("layout_mixin.simple_docs", exc)
            docs = []
        self._custom_profile_documents = docs
        visible = {doc.kind for doc in docs}
        for kind in list(getattr(self, "custom_output_vars", {})):
            if kind not in visible:
                self.custom_output_vars.pop(kind, None)
                self.output_vars.pop(kind, None)
        if not docs:
            empty = tk.Frame(container, bg=UI_SOFT, highlightbackground=UI_LINE, highlightthickness=1, padx=self._px(12, 8), pady=self._px(12, 8))
            empty.grid(row=0, column=0, sticky="ew")
            empty.grid_columnconfigure(0, weight=1)
            tk.Label(empty, text="Пока нет кнопок документов", bg=UI_SOFT, fg=UI_TEXT, font=self._font(11, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
            tk.Label(empty, text="Создайте кнопки из своих Word-шаблонов. Встроенных медицинских шаблонов нет.", bg=UI_SOFT, fg=UI_MUTED, font=self._font(9), anchor="w", justify="left", wraplength=self._px(520, 360)).grid(row=1, column=0, sticky="ew", pady=(self._px(3, 2), self._px(8, 5)))
            self._doctor_primary(empty, FIRST_RUN_CREATE_BUTTON_LABEL, self._open_first_run_create_buttons_popup).grid(row=2, column=0, sticky="w")
            self._simple_update_selected_count()
            return
        container.grid_columnconfigure(0, weight=1)
        for row, doc in enumerate(docs):
            var = self.custom_output_vars.get(doc.kind)
            if var is None:
                var = tk.BooleanVar(value=False)
                self.custom_output_vars[doc.kind] = var
            self.output_vars[doc.kind] = var
            item = tk.Frame(container, bg=UI_SOFT, highlightbackground=UI_LINE, highlightthickness=1, padx=self._px(9, 6), pady=self._px(6, 4))
            item.grid(row=row, column=0, sticky="ew", pady=(0, self._px(6, 3)))
            item.grid_columnconfigure(1, weight=1)
            tk.Checkbutton(item, variable=var, command=self._simple_update_selected_count, bg=UI_SOFT, activebackground=UI_SOFT, selectcolor=UI_PANEL).grid(row=0, column=0, sticky="w")
            tk.Label(item, text=doc.label, bg=UI_SOFT, fg=UI_TEXT, font=self._font(10, "bold"), anchor="w", wraplength=self._px(520, 360)).grid(row=0, column=1, sticky="ew")
        self._refresh_diary_frequency_controls()
        self._simple_update_selected_count()

    def _refresh_custom_profile_tiles(self) -> None:
        if getattr(self, "_simple_doctor_ui_active", False) and hasattr(self, "_custom_profile_tiles_container"):
            self._simple_refresh_doctor_documents()
            return
        super()._refresh_custom_profile_tiles()

    def _simple_update_selected_count(self) -> None:
        count = sum(1 for var in getattr(self, "output_vars", {}).values() if var.get())
        if hasattr(self, "selected_outputs_count_var"):
            self.selected_outputs_count_var.set(f"Выбрано: {count}")

    def _simple_select_all_outputs(self) -> None:
        for var in getattr(self, "output_vars", {}).values():
            try:
                var.set(True)
            except Exception as exc:
                record_soft_exception("layout_mixin.simple_select_all", exc)
        self._simple_update_selected_count()

    def _simple_clear_outputs(self) -> None:
        for var in getattr(self, "output_vars", {}).values():
            try:
                var.set(False)
            except Exception as exc:
                record_soft_exception("layout_mixin.simple_clear", exc)
        self._simple_update_selected_count()

    def _refresh_diary_frequency_controls(self) -> None:
        container = getattr(self, "_diary_frequency_container", None)
        if container is None:
            return
        for child in container.winfo_children():
            child.destroy()
        try:
            enabled = bool(self._diary_hourly_enabled())
        except Exception as exc:
            record_soft_exception("layout_mixin.simple_diary_frequency", exc)
            enabled = False
        if not enabled:
            if getattr(self, "diary_frequency_mode_var", None):
                self.diary_frequency_mode_var.set("daily")
            return
        tk.Label(container, text="Дневники:", bg=UI_PANEL, fg=UI_MUTED, font=self._font(9, "bold")).grid(row=0, column=0, sticky="w")
        self._doctor_button(container, "ежедневно", lambda: self._set_diary_frequency_mode("daily")).grid(row=0, column=1, padx=(self._px(6, 3), self._px(3, 2)))
        self._doctor_button(container, "ежечасно", lambda: self._set_diary_frequency_mode("hourly")).grid(row=0, column=2)

    def _set_diary_frequency_mode(self, mode: str) -> None:
        self.diary_frequency_mode_var.set(mode)
        self._refresh_diary_frequency_controls()

    def _doctor_call(self, method_name: str) -> None:
        method = getattr(self, method_name, None)
        if callable(method):
            method()

    def _draw_doctor_logo(self, canvas: tk.Canvas) -> None:
        w, h = int(canvas["width"]), int(canvas["height"])
        canvas.create_rectangle(5, 8, w - 5, h - 4, outline=UI_BLUE, width=2)
        canvas.create_line(10, 5, 10, 11, fill=UI_BLUE, width=2)
        canvas.create_line(w - 10, 5, w - 10, 11, fill=UI_BLUE, width=2)
        canvas.create_line(w // 2, 13, w // 2, h - 9, fill=UI_BLUE, width=2)
        canvas.create_line(w // 2 - 5, h // 2 + 2, w // 2 + 5, h // 2 + 2, fill=UI_BLUE, width=2)

    def _draw_upload_icon(self, canvas: tk.Canvas) -> None:
        w, h = int(canvas["width"]), int(canvas["height"])
        canvas.create_oval(9, 20, 34, 42, outline=UI_BLUE, width=2)
        canvas.create_oval(25, 10, 51, 40, outline=UI_BLUE, width=2)
        canvas.create_oval(44, 22, w - 8, 43, outline=UI_BLUE, width=2)
        canvas.create_line(w // 2, 38, w // 2, 17, fill=UI_BLUE, width=2)
        canvas.create_line(w // 2, 17, w // 2 - 8, 27, fill=UI_BLUE, width=2)
        canvas.create_line(w // 2, 17, w // 2 + 8, 27, fill=UI_BLUE, width=2)


class LayoutMixin(LayoutWizardSurfaceMixin, LayoutSourcesMixin, LayoutChecklistMixin, LayoutActionBarMixin):
    pass
