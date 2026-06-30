from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk

from layout_sources import LayoutSourcesMixin
from layout_checklist import (
    FIRST_RUN_CREATE_BUTTON_LABEL,
    LayoutChecklistMixin,
    _doctor_buttons_setup_completed,
)
from layout_action_bar import LayoutActionBarMixin
from diagnostic_logging import record_soft_exception

L_BG = "#f3f6fb"
L_PANEL = "#ffffff"
L_SOFT = "#f7faff"
L_LINE = "#d8e2ef"
L_TEXT = "#172033"
L_MUTED = "#667085"
L_ACCENT = "#2f73e8"
L_ACCENT_DARK = "#1f5fd0"
L_SUCCESS = "#14804a"


class LayoutWizardSurfaceMixin:
    def _build_wizard_surface(self, parent: tk.Frame) -> None:
        """Build the real Dokkomplekt wizard, not a wrapper around old blocks."""
        parent.configure(bg=L_BG)
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)
        self._rw_header(parent)
        workspace = tk.Frame(parent, bg=L_BG)
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.grid_columnconfigure(0, minsize=self._px(178, 132))
        workspace.grid_columnconfigure(1, weight=1)
        workspace.grid_rowconfigure(0, weight=1)
        self._rw_step_rail(workspace)
        pages = tk.Frame(workspace, bg=L_BG)
        pages.grid(row=0, column=1, sticky="nsew", padx=(self._px(18, 10), 0))
        pages.grid_columnconfigure(0, weight=1)
        pages.grid_rowconfigure(2, weight=1)
        self._rw_setup_card(pages, row=0)
        self._rw_document_card(pages, row=1)
        mid = tk.Frame(pages, bg=L_BG)
        mid.grid(row=2, column=0, sticky="nsew", pady=(self._px(12, 6), 0))
        mid.grid_columnconfigure(0, weight=1)
        mid.grid_columnconfigure(1, weight=1)
        mid.grid_rowconfigure(0, weight=1)
        self._rw_data_card(mid, row=0, column=0)
        self._rw_create_card(mid, row=0, column=1)
        self._rw_done_card(pages, row=3)

    def _rw_header(self, parent: tk.Frame) -> None:
        header = tk.Frame(parent, bg=L_BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, self._px(14, 8)))
        header.grid_columnconfigure(0, weight=1)
        self._bind_window_drag(header)
        left = tk.Frame(header, bg=L_BG)
        left.grid(row=0, column=0, sticky="w")
        self._bind_window_drag(left)
        logo = tk.Canvas(left, width=self._px(34, 28), height=self._px(34, 28), bg=L_BG, highlightthickness=0)
        logo.grid(row=0, column=0, rowspan=2, padx=(0, self._px(11, 7)))
        self._rw_logo(logo)
        tk.Label(left, text="Dokkomplekt", bg=L_BG, fg=L_TEXT, font=self._font(21, "bold")).grid(row=0, column=1, sticky="w")
        tk.Label(left, text="Документы врача без лишних шагов", bg=L_BG, fg=L_MUTED, font=self._font(10)).grid(row=1, column=1, sticky="w")
        right = tk.Frame(header, bg=L_BG)
        right.grid(row=0, column=1, sticky="e")
        self._rw_small_button(right, "Лицензия", lambda: self._rw_call("show_product_license_dialog")).grid(row=0, column=0, padx=(0, 7))
        self._rw_small_button(right, "Профиль", lambda: self._rw_call("_open_universal_document_mapper")).grid(row=0, column=1, padx=(0, 7))
        self._rw_small_button(right, "Папка вывода", self.choose_output_dir).grid(row=0, column=2, padx=(0, 7))
        self._rw_small_button(right, "Язык", lambda: self._rw_call("_open_language_settings")).grid(row=0, column=3, padx=(0, 10))
        self._window_control_button(right, "−", self._minimize_window).grid(row=0, column=4)
        self._window_control_button(right, "□", self._toggle_maximize).grid(row=0, column=5)
        self._window_control_button(right, "×", self.root.destroy, danger=True).grid(row=0, column=6)

    def _rw_step_rail(self, parent: tk.Frame) -> None:
        rail = tk.Frame(parent, bg=L_BG)
        rail.grid(row=0, column=0, sticky="nsw")
        steps = (("01", "Документ"), ("02", "Данные"), ("03", "Создать"), ("04", "Готово"))
        for idx, (num, title) in enumerate(steps):
            item = tk.Frame(rail, bg=L_BG)
            item.grid(row=idx, column=0, sticky="ew", pady=(0, self._px(22 if idx < 3 else 0, 10)))
            badge_bg = "#eef5ff" if idx == 0 else "#ffffff"
            tk.Label(item, text=num, width=4, bg=badge_bg, fg=L_ACCENT, highlightbackground=L_LINE, highlightthickness=1, font=self._font(15, "bold"), pady=self._px(10, 6)).grid(row=0, column=0, sticky="n", padx=(0, 10))
            tk.Label(item, text=title, bg=L_BG, fg=L_TEXT if idx == 0 else L_MUTED, font=self._font(11, "bold"), anchor="w").grid(row=0, column=1, sticky="w")

    def _rw_setup_card(self, parent: tk.Frame, *, row: int) -> None:
        card = self._rw_card(parent)
        card.grid(row=row, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        tk.Label(card, text="Первый запуск: создайте кнопки документов", bg=L_PANEL, fg=L_TEXT, font=self._font(12, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        tk.Label(card, text="Загрузите свои Word-шаблоны. Программа сделает из них кнопки: Выписка, Справка, Акт и любые ваши документы.", bg=L_PANEL, fg=L_MUTED, font=self._font(9), anchor="w", wraplength=self._px(760, 520), justify="left").grid(row=1, column=0, sticky="ew", pady=(2, 0))
        actions = tk.Frame(card, bg=L_PANEL)
        actions.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))
        self._rw_primary_button(actions, "Создать кнопки", self._open_first_run_create_buttons_popup).grid(row=0, column=0, padx=(0, 7))
        self._rw_small_button(actions, "Выписанные пациенты", lambda: self._rw_call("_ask_create_desktop_intake_folder")).grid(row=0, column=1, padx=(0, 7))
        self._rw_small_button(actions, "Подпапки", self.configure_patient_folder_naming_dialog).grid(row=0, column=2)

    def _rw_document_card(self, parent: tk.Frame, *, row: int) -> None:
        card = self._rw_card(parent)
        card.grid(row=row, column=0, sticky="ew", pady=(self._px(12, 6), 0))
        card.grid_columnconfigure(0, weight=1)
        tk.Label(card, text="Загрузите первичный документ", bg=L_PANEL, fg=L_TEXT, font=self._font(17, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        tk.Label(card, text="Перетащите DOCX/DOCM или нажмите кнопку. После выбора программа очистит данные прошлого пациента и распознает текущий случай.", bg=L_PANEL, fg=L_MUTED, font=self._font(9), anchor="w", wraplength=self._px(760, 520), justify="left").grid(row=1, column=0, sticky="ew", pady=(3, 8))
        upload = tk.Frame(card, bg=L_PANEL)
        upload.grid(row=2, column=0, sticky="ew")
        upload.grid_columnconfigure(0, weight=1)
        self._rw_upload_zone(upload, 0)
        type_row = tk.Frame(card, bg=L_PANEL)
        type_row.grid(row=3, column=0, sticky="ew", pady=(self._px(8, 4), 0))
        type_row.grid_columnconfigure(1, weight=1)
        tk.Label(type_row, text="Тип документа", bg=L_PANEL, fg=L_MUTED, font=self._font(9, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 10))
        tk.Label(type_row, textvariable=self.primary_document_type_display_var, bg=L_SOFT, fg=L_TEXT, highlightbackground=L_LINE, highlightthickness=1, font=self._font(10), padx=12, pady=7, anchor="w").grid(row=0, column=1, sticky="ew")
        self._rw_small_button(type_row, "Изменить", self._toggle_primary_document_type).grid(row=0, column=2, sticky="e", padx=(10, 0))
        self._rw_primary_button(card, "Выбрать файл", self.choose_navigation).grid(row=2, column=1, sticky="e", padx=(self._px(16, 8), 0))

    def _rw_upload_zone(self, parent: tk.Frame, row: int) -> None:
        drop = tk.Frame(parent, bg=L_SOFT, highlightbackground=L_LINE, highlightthickness=1, cursor="hand2", height=self._px(94, 70))
        drop.grid(row=row, column=0, sticky="ew")
        drop.grid_propagate(False)
        drop.grid_columnconfigure(0, weight=1)
        title = tk.Label(drop, text="Перетащите сюда первичный документ", bg=L_SOFT, fg=L_TEXT, font=self._font(12, "bold"), anchor="center")
        title.grid(row=0, column=0, sticky="ew", pady=(self._px(16, 8), 0))
        hint = tk.Label(drop, text="PDF пока не обрабатываем здесь: нужен DOCX/DOCM", bg=L_SOFT, fg=L_MUTED, font=self._font(9), anchor="center")
        hint.grid(row=1, column=0, sticky="ew", pady=(self._px(4, 2), 0))
        self.primary_drop_hint_label = hint
        self.primary_selected_status_var = tk.StringVar(value=" ")
        status = tk.Label(drop, textvariable=self.primary_selected_status_var, bg=L_SOFT, fg=L_SUCCESS, font=self._font(9, "bold"), anchor="center", wraplength=self._px(650, 460))
        status.grid(row=2, column=0, sticky="ew", pady=(self._px(4, 2), 0))
        for widget in (drop, title, hint, status):
            widget.bind("<Button-1>", lambda _event: self.choose_navigation())
        self.drop_zone = drop
        self.primary_selected_status_label = status
        self._drop_widgets = [drop, title, hint, status]

    def _rw_data_card(self, parent: tk.Frame, *, row: int, column: int) -> None:
        card = self._rw_card(parent)
        card.grid(row=row, column=column, sticky="nsew", padx=(0, self._px(6, 3)))
        card.grid_columnconfigure(0, weight=1)
        tk.Label(card, text="Проверьте данные", bg=L_PANEL, fg=L_TEXT, font=self._font(14, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        fields = tk.Frame(card, bg=L_PANEL)
        fields.grid(row=1, column=0, sticky="ew", pady=(self._px(8, 4), 0))
        fields.grid_columnconfigure(1, weight=1)
        rows = (("ФИО / файл", self.patient_name_var), ("История болезни", self.case_number_var), ("Поступление", self.admission_date_var), ("Выписка", self.discharge_date_var), ("Диагноз", self.diagnosis_var), ("Больничный", self.expert_sick_leave_display_var))
        for i, (label, var) in enumerate(rows):
            tk.Label(fields, text=label, bg=L_PANEL, fg=L_MUTED, font=self._font(9), anchor="w").grid(row=i, column=0, sticky="w", pady=3, padx=(0, 8))
            tk.Label(fields, textvariable=var, bg=L_SOFT, fg=L_TEXT, highlightbackground=L_LINE, highlightthickness=1, font=self._font(9), padx=9, pady=5, anchor="w").grid(row=i, column=1, sticky="ew", pady=3)
        buttons = tk.Frame(card, bg=L_PANEL)
        buttons.grid(row=2, column=0, sticky="ew", pady=(self._px(10, 5), 0))
        self._rw_small_button(buttons, "Проверка", self.show_found_patient_data).grid(row=0, column=0, sticky="w", padx=(0, 7))
        self._rw_small_button(buttons, "Папка пациента", self.configure_patient_folder_naming_dialog).grid(row=0, column=1, sticky="w")

    def _rw_create_card(self, parent: tk.Frame, *, row: int, column: int) -> None:
        card = self._rw_card(parent)
        card.grid(row=row, column=column, sticky="nsew", padx=(self._px(6, 3), 0))
        card.grid_columnconfigure(0, weight=1)
        tk.Label(card, text="Какие документы создать?", bg=L_PANEL, fg=L_TEXT, font=self._font(14, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        toolbar = tk.Frame(card, bg=L_PANEL)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(self._px(7, 3), self._px(7, 3)))
        self.selected_outputs_count_var = tk.StringVar(value="Выбрано: 0")
        tk.Label(toolbar, textvariable=self.selected_outputs_count_var, bg=L_PANEL, fg=L_MUTED, font=self._font(9, "bold")).grid(row=0, column=0, sticky="w")
        toolbar.grid_columnconfigure(1, weight=1)
        self._rw_small_button(toolbar, "Выбрать всё", self._rw_select_all_outputs).grid(row=0, column=2, padx=(0, 6))
        self._rw_small_button(toolbar, "Снять всё", self._rw_clear_outputs).grid(row=0, column=3)
        self._custom_profile_tiles_container = tk.Frame(card, bg=L_PANEL)
        self._custom_profile_tiles_container.grid(row=2, column=0, sticky="nsew")
        self._diary_frequency_container = tk.Frame(card, bg=L_PANEL)
        self._diary_frequency_container.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self._rw_refresh_doctor_document_list()
        inputs = tk.LabelFrame(card, text="Дополнительные входные файлы", bg=L_PANEL, fg=L_MUTED, font=self._font(9, "bold"), padx=8, pady=6, labelanchor="nw")
        inputs.grid(row=4, column=0, sticky="ew", pady=(self._px(10, 5), 0))
        inputs.grid_columnconfigure(1, weight=1)
        self._rw_input_row(inputs, 0, "Файл ЭПИ", self.epi_path_var, self.choose_epi, "Добавить")
        self.status_files_label = self._rw_input_row(inputs, 1, "Дневники: тексты", None, self.choose_status_files, "Тексты")
        self.diary_files_label = self._rw_input_row(inputs, 2, "Дневники: даты", None, self.choose_diary_files, "Даты")
        self._refresh_diary_labels()

    def _rw_refresh_doctor_document_list(self) -> None:
        """Render doctor-owned document buttons as a clean list, not old tiles."""
        container = self._custom_profile_tiles_container
        for child in container.winfo_children():
            child.destroy()
        try:
            from universal_main_documents import custom_documents_for_main_ui
            pack = self._load_or_create_universal_pack()
            docs = list(custom_documents_for_main_ui(pack, base_dir=self._universal_profile_path().parent)) if _doctor_buttons_setup_completed(pack) else []
        except Exception as exc:
            record_soft_exception("layout_mixin.real_wizard_docs", exc)
            docs = []
        self._custom_profile_documents = docs
        visible = {doc.kind for doc in docs}
        for kind in list(getattr(self, "custom_output_vars", {})):
            if kind not in visible:
                self.custom_output_vars.pop(kind, None)
                self.output_vars.pop(kind, None)
        if not docs:
            empty = tk.Frame(container, bg=L_SOFT, highlightbackground=L_LINE, highlightthickness=1, padx=12, pady=12)
            empty.grid(row=0, column=0, sticky="ew")
            empty.grid_columnconfigure(0, weight=1)
            tk.Label(empty, text="Пока нет кнопок документов", bg=L_SOFT, fg=L_TEXT, font=self._font(11, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
            tk.Label(empty, text="Сначала загрузите свои Word-шаблоны. Встроенных медицинских шаблонов здесь нет.", bg=L_SOFT, fg=L_MUTED, font=self._font(9), anchor="w", wraplength=self._px(460, 320), justify="left").grid(row=1, column=0, sticky="ew", pady=(2, 8))
            self._rw_primary_button(empty, FIRST_RUN_CREATE_BUTTON_LABEL, self._open_first_run_create_buttons_popup).grid(row=2, column=0, sticky="w")
            self._rw_update_selected_count()
            return
        container.grid_columnconfigure(0, weight=1)
        for i, doc in enumerate(docs):
            var = self.custom_output_vars.get(doc.kind)
            if var is None:
                var = tk.BooleanVar(value=False)
                self.custom_output_vars[doc.kind] = var
            self.output_vars[doc.kind] = var
            row = tk.Frame(container, bg=L_SOFT, highlightbackground=L_LINE, highlightthickness=1, padx=9, pady=6)
            row.grid(row=i, column=0, sticky="ew", pady=(0, 6))
            row.grid_columnconfigure(1, weight=1)
            tk.Checkbutton(row, variable=var, bg=L_SOFT, activebackground=L_SOFT, selectcolor="#ffffff", command=self._rw_update_selected_count).grid(row=0, column=0, sticky="w")
            tk.Label(row, text=doc.label, bg=L_SOFT, fg=L_TEXT, font=self._font(10, "bold"), anchor="w").grid(row=0, column=1, sticky="ew")
        self._refresh_diary_frequency_controls()
        self._rw_update_selected_count()

    def _rw_done_card(self, parent: tk.Frame, *, row: int) -> None:
        card = self._rw_card(parent)
        card.grid(row=row, column=0, sticky="ew", pady=(self._px(12, 6), 0))
        card.grid_columnconfigure(0, weight=1)
        tk.Label(card, text="Всё готово к созданию", bg=L_PANEL, fg=L_TEXT, font=self._font(14, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        settings = tk.Frame(card, bg=L_PANEL)
        settings.grid(row=1, column=0, sticky="ew", pady=(self._px(9, 4), 0))
        settings.grid_columnconfigure(1, weight=1)
        tk.Label(settings, text="Папка", bg=L_PANEL, fg=L_MUTED, font=self._font(9)).grid(row=0, column=0, sticky="w", padx=(0, 8))
        tk.Entry(settings, textvariable=self.output_dir_var, bg=L_SOFT, fg=L_TEXT, relief="flat", highlightthickness=1, highlightbackground=L_LINE, font=self._font(9)).grid(row=0, column=1, sticky="ew")
        self._rw_small_button(settings, "Выбрать", self.choose_output_dir).grid(row=0, column=2, padx=(8, 0))
        tk.Label(settings, text="Принтер", bg=L_PANEL, fg=L_MUTED, font=self._font(9)).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(7, 0))
        self.printer_combo = ttk.Combobox(settings, textvariable=self.printer_var, values=[], state="readonly", font=self._font(9))
        self.printer_combo.grid(row=1, column=1, sticky="ew", pady=(7, 0))
        self.printer_combo.bind("<<ComboboxSelected>>", self._on_printer_selected)
        self._rw_small_button(settings, "Обновить", self.refresh_printers).grid(row=1, column=2, padx=(8, 0), pady=(7, 0))
        buttons = tk.Frame(card, bg=L_PANEL)
        buttons.grid(row=0, column=1, rowspan=2, sticky="e", padx=(self._px(18, 10), 0))
        self._rw_primary_button(buttons, "Создать и сохранить", lambda: self.create_selected_outputs(print_after=False), wide=True).grid(row=0, column=0, sticky="ew", pady=(0, 7))
        self._rw_primary_button(buttons, "Создать, сохранить, распечатать", lambda: self.create_selected_outputs(print_after=True), wide=True).grid(row=1, column=0, sticky="ew")
        more = tk.Frame(card, bg=L_PANEL)
        more.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(self._px(10, 5), 0))
        for col, (text, cmd) in enumerate((("Проверка", self.show_found_patient_data), ("Диагн.", self.show_installation_diagnostics_dialog), ("Пакет", self.batch_generate_documents_dialog), ("Версия", self.check_updates_dialog), ("Сброс", self.reset_settings_dialog))):
            self._rw_small_button(more, text, cmd).grid(row=0, column=col, sticky="w", padx=(0, 6))
        self.progress = ttk.Progressbar(card, mode="indeterminate", length=180)
        self.status_label = self._status_bar_label

    def _rw_input_row(self, parent: tk.Frame, row: int, label: str, var, command, button: str):
        tk.Label(parent, text=label, bg=L_PANEL, fg=L_MUTED, font=self._font(9), anchor="w").grid(row=row, column=0, sticky="w", pady=3, padx=(0, 8))
        value = tk.Label(parent, textvariable=var if var is not None else None, text="не выбрано" if var is None else "", bg=L_SOFT, fg=L_TEXT, highlightbackground=L_LINE, highlightthickness=1, font=self._font(8), padx=8, pady=5, anchor="w")
        value.grid(row=row, column=1, sticky="ew", pady=3)
        self._rw_small_button(parent, button, command).grid(row=row, column=2, padx=(8, 0), pady=3)
        return value

    def _rw_card(self, parent: tk.Frame) -> tk.Frame:
        return tk.Frame(parent, bg=L_PANEL, highlightbackground=L_LINE, highlightthickness=1, padx=self._px(18, 10), pady=self._px(14, 8))

    def _rw_primary_button(self, parent, text: str, command, *, wide: bool = False) -> tk.Button:
        return tk.Button(parent, text=text, command=command, bg=L_ACCENT, fg="#ffffff", activebackground=L_ACCENT_DARK, activeforeground="#ffffff", relief="flat", bd=0, padx=self._px(18 if wide else 14, 9), pady=self._px(9, 6), font=self._font(10, "bold"), cursor="hand2")

    def _rw_small_button(self, parent, text: str, command) -> tk.Button:
        return tk.Button(parent, text=text, command=command, bg=L_SOFT, fg=L_ACCENT, activebackground="#eef5ff", activeforeground=L_ACCENT_DARK, relief="flat", bd=0, highlightthickness=1, highlightbackground=L_LINE, padx=self._px(11, 7), pady=self._px(6, 4), font=self._font(9, "bold"), cursor="hand2")

    def _rw_logo(self, canvas: tk.Canvas) -> None:
        w = int(canvas["width"])
        h = int(canvas["height"])
        canvas.create_rectangle(5, 8, w - 5, h - 4, outline=L_ACCENT, width=2)
        canvas.create_line(10, 5, 10, 11, fill=L_ACCENT, width=2)
        canvas.create_line(w - 10, 5, w - 10, 11, fill=L_ACCENT, width=2)
        canvas.create_line(w // 2, 13, w // 2, h - 9, fill=L_ACCENT, width=2)
        canvas.create_line(w // 2 - 5, h // 2 + 2, w // 2 + 5, h // 2 + 2, fill=L_ACCENT, width=2)

    def _rw_update_selected_count(self) -> None:
        count = sum(1 for var in getattr(self, "output_vars", {}).values() if var.get())
        if hasattr(self, "selected_outputs_count_var"):
            self.selected_outputs_count_var.set(f"Выбрано: {count}")

    def _rw_select_all_outputs(self) -> None:
        for kind, var in getattr(self, "output_vars", {}).items():
            try:
                var.set(True)
            except Exception as exc:
                record_soft_exception("layout_mixin.select_all", exc, detail=str(kind))
        self._rw_update_selected_count()

    def _rw_clear_outputs(self) -> None:
        for kind, var in getattr(self, "output_vars", {}).items():
            try:
                var.set(False)
            except Exception as exc:
                record_soft_exception("layout_mixin.clear_outputs", exc, detail=str(kind))
        self._rw_update_selected_count()

    def _rw_call(self, method_name: str) -> None:
        method = getattr(self, method_name, None)
        if callable(method):
            method()


class LayoutMixin(LayoutWizardSurfaceMixin, LayoutSourcesMixin, LayoutChecklistMixin, LayoutActionBarMixin):
    pass
