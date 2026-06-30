from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from diagnostic_logging import record_soft_exception
from layout_action_bar import LayoutActionBarMixin
from layout_checklist import FIRST_RUN_CREATE_BUTTON_LABEL, LayoutChecklistMixin, _doctor_buttons_setup_completed
from layout_sources import LayoutSourcesMixin

L_BG = "#f3f6fb"
L_PANEL = "#ffffff"
L_SOFT = "#f7faff"
L_SOFT_2 = "#eef5ff"
L_LINE = "#d8e2ef"
L_TEXT = "#172033"
L_MUTED = "#667085"
L_MUTED_2 = "#8a94a6"
L_ACCENT = "#2f73e8"
L_ACCENT_DARK = "#1f5fd0"
L_SUCCESS = "#14804a"
L_WARN = "#b7791f"
L_ERROR = "#c2415d"


class LayoutWizardSurfaceMixin:
    def _build_wizard_surface(self, parent: tk.Frame) -> None:
        """Build the real Dokkomplekt action board.

        The previous attempt only wrapped the old 01/02/03/04 grid.  This surface is a standalone
        workflow board that exposes the full doctor path while still calling the existing production
        callbacks for document parsing, profile/template setup, popups, saving and printing.
        """
        self._real_wizard_ui_active = True
        parent.configure(bg=L_BG)
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)
        self._rw_header(parent)
        self._rw_scrollable_board(parent)

    def _rw_header(self, parent: tk.Frame) -> None:
        header = tk.Frame(parent, bg=L_BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, self._px(8, 4)))
        header.grid_columnconfigure(0, weight=1)
        self._bind_window_drag(header)

        left = tk.Frame(header, bg=L_BG)
        left.grid(row=0, column=0, sticky="w")
        self._bind_window_drag(left)
        tk.Label(left, text="DOKKOMPLEKT — ПОЛНЫЙ ПУТЬ ДОКУМЕНТОВ", bg=L_BG, fg="#111f70", font=self._font(18, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        tk.Label(
            left,
            text="от первого запуска и шаблонов врача до создания, сохранения, печати, экспорта и ошибок",
            bg=L_BG,
            fg="#111f70",
            font=self._font(9, "bold"),
        ).grid(row=1, column=0, sticky="w")

        right = tk.Frame(header, bg=L_BG)
        right.grid(row=0, column=1, sticky="e")
        for col, (text, command) in enumerate(
            (
                ("Лицензия", lambda: self._rw_call("show_product_license_dialog")),
                ("Профиль", lambda: self._rw_call("_open_universal_document_mapper")),
                ("Папка вывода", self.choose_output_dir),
                ("Язык", lambda: self._rw_call("_open_language_settings")),
            )
        ):
            self._rw_small_button(right, text, command).grid(row=0, column=col, padx=(0, self._px(6, 3)))
        self._window_control_button(right, "−", self._minimize_window).grid(row=0, column=4)
        self._window_control_button(right, "□", self._toggle_maximize).grid(row=0, column=5)
        self._window_control_button(right, "×", self.root.destroy, danger=True).grid(row=0, column=6)

    def _rw_scrollable_board(self, parent: tk.Frame) -> None:
        shell = tk.Frame(parent, bg=L_BG)
        shell.grid(row=1, column=0, sticky="nsew")
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(0, weight=1)

        canvas = tk.Canvas(shell, bg=L_BG, highlightthickness=0, bd=0)
        vbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")

        board = tk.Frame(canvas, bg=L_BG)
        window_id = canvas.create_window((0, 0), window=board, anchor="nw")
        board.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"), add="+")

        board.grid_columnconfigure(0, weight=1)
        self._rw_legend(board, row=0)
        self._rw_build_sections(board, start_row=1)
        self.status_label = self._status_bar_label
        self.progress = ttk.Progressbar(board, mode="indeterminate", length=180)

    def _rw_legend(self, parent: tk.Frame, *, row: int) -> None:
        legend = tk.Frame(parent, bg=L_PANEL, highlightbackground=L_LINE, highlightthickness=1, padx=self._px(10, 6), pady=self._px(7, 4))
        legend.grid(row=row, column=0, sticky="ew", pady=(0, self._px(8, 4)))
        legend.grid_columnconfigure(0, weight=1)
        tk.Label(legend, text="Обозначения:", bg=L_PANEL, fg=L_TEXT, font=self._font(8, "bold")).grid(row=0, column=0, sticky="w")
        items = (
            (L_SUCCESS, "действие пользователя"),
            ("#61a878", "действие программы"),
            ("#f59e0b", "выбор / опция"),
            ("#5b5fc7", "информация / результат"),
            (L_ERROR, "ошибка / предупреждение"),
        )
        for idx, (color, text) in enumerate(items, start=1):
            dot = tk.Canvas(legend, width=self._px(14, 10), height=self._px(14, 10), bg=L_PANEL, highlightthickness=0)
            dot.grid(row=0, column=idx * 2 - 1, sticky="e", padx=(self._px(14, 7), self._px(4, 2)))
            dot.create_oval(3, 3, 11, 11, fill=color, outline=color)
            tk.Label(legend, text=text, bg=L_PANEL, fg=L_MUTED, font=self._font(8, "bold")).grid(row=0, column=idx * 2, sticky="w")

    def _rw_build_sections(self, parent: tk.Frame, *, start_row: int) -> None:
        self._rw_section(parent, start_row + 0, "I. ЗАПУСК И ПЕРВИЧНАЯ НАСТРОЙКА", self._rw_startup_cards())
        self._rw_section(parent, start_row + 1, "II. ЗАГРУЗКА ПЕРВИЧНОГО ДОКУМЕНТА И АНАЛИЗ", self._rw_primary_cards())
        self._rw_section(parent, start_row + 2, "III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ", self._rw_data_and_choice_cards())
        self._rw_section(parent, start_row + 3, "IV. СОЗДАНИЕ ДОКУМЕНТОВ И СОХРАНЕНИЕ", self._rw_creation_cards())
        self._rw_section(parent, start_row + 4, "V. ПЕЧАТЬ, ЭКСПОРТ И ПЕРЕДАЧА", self._rw_export_cards())
        self._rw_section(parent, start_row + 5, "VI. ШАБЛОНЫ, ПРОФИЛИ И НАПОМИНАНИЯ", self._rw_template_cards())
        self._rw_section(parent, start_row + 6, "VII. ЖУРНАЛ ДЕЙСТВИЙ И ЛОГИ", self._rw_log_cards())
        self._rw_section(parent, start_row + 7, "VIII. НАСТРОЙКИ И ПРОГРАММА", self._rw_settings_cards())
        self._rw_section(parent, start_row + 8, "IX. ИСКЛЮЧИТЕЛЬНЫЕ СИТУАЦИИ И ОШИБКИ", self._rw_error_cards())
        self._rw_section(parent, start_row + 9, "X. СКРЫТЫЕ СЦЕНАРИИ И ДОПОЛНИТЕЛЬНЫЕ ВОЗМОЖНОСТИ", self._rw_hidden_cards())
        self._rw_success_footer(parent, row=start_row + 10)

    def _rw_section(self, parent: tk.Frame, row: int, title: str, builders: tuple) -> None:
        section = tk.Frame(parent, bg=L_BG, highlightbackground=L_LINE, highlightthickness=1, padx=self._px(7, 4), pady=self._px(5, 3))
        section.grid(row=row, column=0, sticky="ew", pady=(0, self._px(8, 4)))
        section.grid_columnconfigure(0, weight=1)
        tk.Label(section, text=title, bg=L_BG, fg="#111f70", font=self._font(10, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        grid = tk.Frame(section, bg=L_BG)
        grid.grid(row=1, column=0, sticky="ew", pady=(self._px(5, 3), 0))
        cols = 10 if not getattr(self, "_compact_ui", False) else 5
        for col in range(cols):
            grid.grid_columnconfigure(col, weight=1, uniform=f"{title}-cards")
        for idx, builder in enumerate(builders):
            card = tk.Frame(grid, bg=L_PANEL, highlightbackground=L_LINE, highlightthickness=1, padx=self._px(7, 4), pady=self._px(6, 3))
            card.grid(row=idx // cols, column=idx % cols, sticky="nsew", padx=self._px(3, 2), pady=self._px(3, 2))
            card.grid_columnconfigure(0, weight=1)
            builder(card)

    def _rw_card_title(self, card: tk.Frame, number: int, title: str, marker: str = "info") -> None:
        color = {"user": L_SUCCESS, "program": "#61a878", "choice": "#f59e0b", "error": L_ERROR, "hidden": "#5b5fc7"}.get(marker, "#5b5fc7")
        top = tk.Frame(card, bg=L_PANEL)
        top.grid(row=0, column=0, sticky="ew")
        dot = tk.Canvas(top, width=12, height=12, bg=L_PANEL, highlightthickness=0)
        dot.grid(row=0, column=0, sticky="w", padx=(0, 4))
        dot.create_oval(2, 2, 10, 10, fill=color, outline=color)
        tk.Label(top, text=f"{number}. {title}", bg=L_PANEL, fg="#111f70", font=self._font(8, "bold"), anchor="w", justify="left", wraplength=self._px(160, 110)).grid(
            row=0, column=1, sticky="ew"
        )
        top.grid_columnconfigure(1, weight=1)

    def _rw_note(self, card: tk.Frame, text: str, row: int = 1) -> None:
        tk.Label(card, text=text, bg=L_PANEL, fg=L_MUTED, font=self._font(7), anchor="w", justify="left", wraplength=self._px(170, 110)).grid(
            row=row, column=0, sticky="ew", pady=(self._px(4, 2), 0)
        )

    def _rw_action_button(self, card: tk.Frame, text: str, command, row: int = 2, primary: bool = False) -> None:
        button = self._rw_primary_button(card, text, command) if primary else self._rw_small_button(card, text, command)
        button.grid(row=row, column=0, sticky="ew", pady=(self._px(6, 3), 0))

    def _rw_value_label(self, card: tk.Frame, variable: tk.Variable | None = None, text: str = "", row: int = 2) -> tk.Label:
        label = tk.Label(
            card,
            textvariable=variable,
            text=text if variable is None else "",
            bg=L_SOFT,
            fg=L_TEXT,
            highlightbackground=L_LINE,
            highlightthickness=1,
            font=self._font(7),
            anchor="w",
            justify="left",
            padx=self._px(5, 3),
            pady=self._px(4, 2),
            wraplength=self._px(150, 100),
        )
        label.grid(row=row, column=0, sticky="ew", pady=(self._px(5, 2), 0))
        return label

    def _rw_entry(self, card: tk.Frame, variable: tk.StringVar, row: int = 2) -> None:
        tk.Entry(
            card,
            textvariable=variable,
            bg=L_SOFT,
            fg=L_TEXT,
            relief="flat",
            highlightbackground=L_LINE,
            highlightthickness=1,
            font=self._font(7),
        ).grid(row=row, column=0, sticky="ew", pady=(self._px(5, 2), 0), ipady=self._px(2, 1))

    def _rw_startup_cards(self) -> tuple:
        return (
            lambda c: self._rw_status_card(c, 1, "Запуск программы", "Версия и старт окна", "program"),
            lambda c: self._rw_simple_action(c, 2, "Мастер первого запуска", "Создать рабочую папку и кнопки", self._rw_show_tour, "user"),
            lambda c: self._rw_simple_action(c, 3, "Выбор папки", "Куда сохранять документы", self.choose_output_dir, "choice"),
            lambda c: self._rw_simple_action(c, 4, "Язык и тема", "Интерфейс и язык документов", lambda: self._rw_call("_open_language_settings"), "choice"),
            lambda c: self._rw_simple_action(c, 5, "Принтер", "Проверить печать", self.refresh_printers, "choice"),
            lambda c: self._rw_start_button_card(c, 6),
            lambda c: self._rw_simple_action(c, 7, "Проверка обновлений", "Версия программы", self.check_updates_dialog, "program"),
            lambda c: self._rw_simple_action(c, 8, "Лицензия", "Доступ и оплата", lambda: self._rw_call("show_product_license_dialog"), "choice"),
            lambda c: self._rw_simple_action(c, 9, "Профиль врача", "Шаблоны, кнопки, правила", self._open_universal_document_mapper, "user"),
            lambda c: self._rw_simple_action(c, 10, "Краткий тур", "Показать подсказку", self._rw_show_tour, "info"),
        )

    def _rw_primary_cards(self) -> tuple:
        return (
            lambda c: self._rw_simple_action(c, 11, "Перетащить файл", "Первичный DOCX/DOCM", self.choose_navigation, "user", primary=True),
            lambda c: self._rw_primary_path_card(c, 12),
            lambda c: self._rw_simple_action(c, 13, "Анализ документа", "Распознать поля повторно", lambda: self.reparse_navigation(silent=False), "program"),
            lambda c: self._rw_status_card(c, 14, "Результаты анализа", "ФИО, даты, диагноз, МКБ", "program"),
            lambda c: self._rw_simple_action(c, 15, "Предпросмотр", "Показать найденные данные", self.show_found_patient_data, "info"),
            lambda c: self._rw_found_data_summary(c, 16),
            lambda c: self._rw_status_card(c, 17, "Проверка разделов", "Жалобы, анамнез, лечение", "program"),
            lambda c: self._rw_warning_card(c, 18, "Ошибки анализа", "Если раздел не найден — popup спросит"),
            lambda c: self._rw_status_card(c, 19, "Подтверждение", "Врач подтверждает данные", "user"),
            lambda c: self._rw_simple_action(c, 20, "Сохранить результат", "Открыть папку вывода", self.choose_output_dir, "choice"),
        )

    def _rw_data_and_choice_cards(self) -> tuple:
        return (
            lambda c: self._rw_document_choice_card(c, 21),
            lambda c: self._rw_field_card(c, 22, "Личные данные", self.patient_name_var),
            lambda c: self._rw_field_card(c, 23, "№ истории", self.case_number_var),
            lambda c: self._rw_dates_card(c, 24),
            lambda c: self._rw_field_card(c, 25, "Диагноз", self.diagnosis_var),
            lambda c: self._rw_field_card(c, 26, "Лечение", self.assigned_treatment_var),
            lambda c: self._rw_simple_action(c, 27, "Специальные поля", "Откроются popup-и документов", self.show_found_patient_data, "choice"),
            lambda c: self._rw_simple_action(c, 28, "Ошибка шаблона", "Показать профили/шаблоны", self._open_universal_document_mapper, "error"),
            lambda c: self._rw_simple_action(c, 29, "Нет права на папку", "Выбрать другую папку", self.choose_output_dir, "error"),
            lambda c: self._rw_status_card(c, 30, "Документ открыт", "Повторить после закрытия Word", "error"),
            lambda c: self._rw_field_card(c, 31, "Больничный", self.expert_sick_leave_display_var),
            lambda c: self._rw_simple_action(c, 32, "Дата протокола", "Проверить данные случая", self.show_found_patient_data, "choice"),
            lambda c: self._rw_simple_action(c, 33, "Проверка связей", "Данные связаны", self.show_found_patient_data, "program"),
            lambda c: self._rw_simple_action(c, 34, "Выбор формулировок", "Через popup/шаблон", self._open_universal_document_mapper, "choice"),
            lambda c: self._rw_simple_action(c, 35, "Примечание", "Добавляется popup-ом", self.show_found_patient_data, "choice"),
            lambda c: self._rw_simple_action(c, 36, "Копировать данные", "Из другого документа", self.show_found_patient_data, "hidden"),
            lambda c: self._rw_simple_action(c, 37, "Очистить ФИО", "Сброс настроек/полей", self.reset_settings_dialog, "choice"),
            lambda c: self._rw_simple_action(c, 38, "Очистить поля", "Сбросить настройки", self.reset_settings_dialog, "choice"),
            lambda c: self._rw_simple_action(c, 39, "Проверка шаблона", "Ошибки и диагностика", self.show_installation_diagnostics_dialog, "program"),
            lambda c: self._rw_ready_card(c, 40),
        )

    def _rw_creation_cards(self) -> tuple:
        return (
            lambda c: self._rw_selected_docs_panel(c, 41),
            lambda c: self._rw_status_card(c, 42, "Прогресс", "Создание и проверки", "program"),
            lambda c: self._rw_output_folder_card(c, 43),
            lambda c: self._rw_simple_action(c, 44, "Имя файлов", "Добавить дату / номер", self.configure_patient_folder_naming_dialog, "choice"),
            lambda c: self._rw_create_button_card(c, 45, False),
            lambda c: self._rw_status_card(c, 46, "Кол-во файлов", "Отчёт после создания", "info"),
            lambda c: self._rw_simple_action(c, 47, "Быстрый просмотр", "Показать созданные", self.show_found_patient_data, "info"),
            lambda c: self._rw_simple_action(c, 48, "Дубликаты", "Перезаписать или копия", self.configure_patient_folder_naming_dialog, "choice"),
            lambda c: self._rw_simple_action(c, 49, "Открыть папку", "Папка результата", self.choose_output_dir, "user"),
            lambda c: self._rw_success_card(c, 50),
        )

    def _rw_export_cards(self) -> tuple:
        return (
            lambda c: self._rw_print_card(c, 51),
            lambda c: self._rw_simple_action(c, 52, "Настройка печати", "Выбор принтера", self.refresh_printers, "choice"),
            lambda c: self._rw_status_card(c, 53, "Экспорт PDF", "Зарезервировано", "hidden"),
            lambda c: self._rw_status_card(c, 54, "Экспорт RTF", "Зарезервировано", "hidden"),
            lambda c: self._rw_status_card(c, 55, "Экспорт TXT", "Зарезервировано", "hidden"),
            lambda c: self._rw_status_card(c, 56, "Экспорт ODT", "Зарезервировано", "hidden"),
            lambda c: self._rw_status_card(c, 57, "Экспорт docx", "Основной формат", "program"),
            lambda c: self._rw_status_card(c, 58, "Подтверждение", "Все данные проверены", "user"),
            lambda c: self._rw_simple_action(c, 59, "Архив", "Пакетная генерация", self.batch_generate_documents_dialog, "hidden"),
            lambda c: self._rw_status_card(c, 60, "Передать в систему", "Зарезервировано", "hidden"),
        )

    def _rw_template_cards(self) -> tuple:
        return (
            lambda c: self._rw_simple_action(c, 61, "Редактор шаблонов", "Профиль врача", self._open_universal_document_mapper, "user"),
            lambda c: self._rw_simple_action(c, 62, "Добавить поле", "Через мастер профиля", self._open_universal_document_mapper, "user"),
            lambda c: self._rw_simple_action(c, 63, "Настройка папки", "Подпапки пациента", self.configure_patient_folder_naming_dialog, "choice"),
            lambda c: self._rw_simple_action(c, 64, "Условные поля", "Проверка программы", self.show_installation_diagnostics_dialog, "program"),
            lambda c: self._rw_simple_action(c, 65, "Проверка полей", "Диагностика", self.show_installation_diagnostics_dialog, "program"),
            lambda c: self._rw_simple_action(c, 66, "Просмотр шаблона", "Открыть профиль", self._open_universal_document_mapper, "info"),
            lambda c: self._rw_status_card(c, 67, "Деталь шаблона", "Поля и правила", "info"),
            lambda c: self._rw_status_card(c, 68, "Восстановить", "Через профиль", "hidden"),
            lambda c: self._rw_status_card(c, 69, "Настройка напоминаний", "Зарезервировано", "hidden"),
            lambda c: self._rw_simple_action(c, 70, "Проверка шаблонов", "Запустить аудит", self.show_installation_diagnostics_dialog, "program"),
        )

    def _rw_log_cards(self) -> tuple:
        return (
            lambda c: self._rw_simple_action(c, 71, "Открыть журнал", "Диагностика", self.show_installation_diagnostics_dialog, "info"),
            lambda c: self._rw_status_card(c, 72, "Фильтр", "Даты и действия", "info"),
            lambda c: self._rw_status_card(c, 73, "Оценка действий", "Служебный отчёт", "program"),
            lambda c: self._rw_status_card(c, 74, "Экспорт лога", "Зарезервировано", "hidden"),
            lambda c: self._rw_status_card(c, 75, "Детали события", "Ошибки и действия", "info"),
            lambda c: self._rw_status_card(c, 76, "Печать журнала", "Зарезервировано", "hidden"),
            lambda c: self._rw_status_card(c, 77, "Очистить журнал", "Зарезервировано", "hidden"),
            lambda c: self._rw_simple_action(c, 78, "Проверка", "Диагностика установки", self.show_installation_diagnostics_dialog, "program"),
            lambda c: self._rw_status_card(c, 79, "Журнал ошибок", "Служебно", "info"),
            lambda c: self._rw_status_card(c, 80, "Настройки журнала", "Зарезервировано", "hidden"),
        )

    def _rw_settings_cards(self) -> tuple:
        return (
            lambda c: self._rw_simple_action(c, 81, "Общие настройки", "Папки, язык, печать", self.configure_patient_folder_naming_dialog, "choice"),
            lambda c: self._rw_simple_action(c, 82, "История печати", "Принтер", self.refresh_printers, "choice"),
            lambda c: self._rw_output_folder_card(c, 83),
            lambda c: self._rw_status_card(c, 84, "Резервное копирование", "Зарезервировано", "hidden"),
            lambda c: self._rw_status_card(c, 85, "Восстановление", "Зарезервировано", "hidden"),
            lambda c: self._rw_simple_action(c, 86, "Язык интерфейса", "Русский / English", lambda: self._rw_call("_open_language_settings"), "choice"),
            lambda c: self._rw_simple_action(c, 87, "Тема", "Светлая рабочая", lambda: self._rw_notice("Тема", "В этой ветке закреплена светлая схема DOKKOMPLEKT."), "choice"),
            lambda c: self._rw_status_card(c, 88, "Горячие клавиши", "F5 / F8 / F9", "info"),
            lambda c: self._rw_status_card(c, 89, "О программе", "Локальное приложение", "info"),
            lambda c: self._rw_simple_action(c, 90, "Выход", "Закрыть программу", self.root.destroy, "choice"),
        )

    def _rw_error_cards(self) -> tuple:
        return (
            lambda c: self._rw_warning_card(c, 91, "Ошибка анализа", "Не удалось распознать файл"),
            lambda c: self._rw_warning_card(c, 92, "Ошибка шаблона", "Шаблон повреждён"),
            lambda c: self._rw_warning_card(c, 93, "Ошибка печати", "Принтер недоступен"),
            lambda c: self._rw_warning_card(c, 94, "Нет доступа", "Выберите другую папку"),
            lambda c: self._rw_warning_card(c, 95, "Сбой программы", "Отправить отчёт"),
        )

    def _rw_hidden_cards(self) -> tuple:
        return (
            lambda c: self._rw_simple_action(c, 96, "Быстрое создание", "Drag & Drop файла", self.choose_navigation, "hidden"),
            lambda c: self._rw_status_card(c, 97, "Автозаполнение", "Из предыдущих данных", "hidden"),
            lambda c: self._rw_status_card(c, 98, "Макросы и скрипты", "Не выполняются", "hidden"),
            lambda c: self._rw_status_card(c, 99, "Интеграция", "Зарезервировано", "hidden"),
            lambda c: self._rw_status_card(c, 100, "Многопользовательский режим", "Локальные профили", "hidden"),
        )

    def _rw_simple_action(self, card: tk.Frame, number: int, title: str, note: str, command, marker: str, primary: bool = False) -> None:
        self._rw_card_title(card, number, title, marker)
        self._rw_note(card, note)
        self._rw_action_button(card, "Открыть" if not primary else "Начать", command, primary=primary)

    def _rw_status_card(self, card: tk.Frame, number: int, title: str, note: str, marker: str) -> None:
        self._rw_card_title(card, number, title, marker)
        self._rw_note(card, note)
        self._rw_value_label(card, text="Готово" if marker != "hidden" else "скрытый сценарий")

    def _rw_warning_card(self, card: tk.Frame, number: int, title: str, note: str) -> None:
        self._rw_card_title(card, number, title, "error")
        self._rw_note(card, note)
        self._rw_action_button(card, "Проверить", self.show_installation_diagnostics_dialog)

    def _rw_primary_path_card(self, card: tk.Frame, number: int) -> None:
        self._rw_card_title(card, number, "Файл загружен", "user")
        self._rw_note(card, "Текущий первичный документ")
        self._rw_value_label(card, self.navigation_path_var)
        self._rw_action_button(card, "Выбрать", self.choose_navigation, row=3)

    def _rw_found_data_summary(self, card: tk.Frame, number: int) -> None:
        self._rw_card_title(card, number, "Найденные данные", "program")
        self._rw_note(card, "ФИО, даты, диагноз")
        self._rw_value_label(card, self.patient_name_var)
        self._rw_action_button(card, "Подробнее", self.show_found_patient_data, row=3)

    def _rw_document_choice_card(self, card: tk.Frame, number: int) -> None:
        self._rw_card_title(card, number, "Выбор документов", "user")
        self._rw_note(card, "Кнопки из шаблонов врача")
        self._rw_value_label(card, getattr(self, "selected_outputs_count_var", None), "Выбрано: 0")
        self._rw_action_button(card, "Создать кнопки", self._open_first_run_create_buttons_popup, row=3, primary=True)

    def _rw_field_card(self, card: tk.Frame, number: int, title: str, variable: tk.StringVar) -> None:
        self._rw_card_title(card, number, title, "user")
        self._rw_note(card, "Можно проверить/исправить")
        self._rw_entry(card, variable)

    def _rw_dates_card(self, card: tk.Frame, number: int) -> None:
        self._rw_card_title(card, number, "Даты и период", "user")
        self._rw_note(card, "Поступление / выписка")
        self._rw_entry(card, self.admission_date_var, row=2)
        self._rw_entry(card, self.discharge_date_var, row=3)

    def _rw_ready_card(self, card: tk.Frame, number: int) -> None:
        self._rw_card_title(card, number, "Готово к созданию", "program")
        self._rw_note(card, "Проверьте документы и папку")
        self._rw_action_button(card, "Создать", lambda: self.create_selected_outputs(print_after=False), primary=True)

    def _rw_selected_docs_panel(self, card: tk.Frame, number: int) -> None:
        self._rw_card_title(card, number, "Создать документы", "user")
        self._custom_profile_tiles_container = tk.Frame(card, bg=L_PANEL)
        self._custom_profile_tiles_container.grid(row=1, column=0, sticky="ew", pady=(self._px(5, 2), 0))
        self._diary_frequency_container = tk.Frame(card, bg=L_PANEL)
        self._diary_frequency_container.grid(row=2, column=0, sticky="ew")
        self.selected_outputs_count_var = tk.StringVar(value="Выбрано: 0")
        self._rw_refresh_doctor_document_list()
        buttons = tk.Frame(card, bg=L_PANEL)
        buttons.grid(row=3, column=0, sticky="ew", pady=(self._px(5, 2), 0))
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)
        self._rw_small_button(buttons, "Все", self._rw_select_all_outputs).grid(row=0, column=0, sticky="ew", padx=(0, 2))
        self._rw_small_button(buttons, "Снять", self._rw_clear_outputs).grid(row=0, column=1, sticky="ew", padx=(2, 0))

    def _rw_output_folder_card(self, card: tk.Frame, number: int) -> None:
        self._rw_card_title(card, number, "Папка сохранения", "choice")
        self._rw_note(card, "Куда попадут документы")
        self._rw_value_label(card, self.output_dir_var)
        self._rw_action_button(card, "Изменить", self.choose_output_dir, row=3)

    def _rw_create_button_card(self, card: tk.Frame, number: int, print_after: bool) -> None:
        self._rw_card_title(card, number, "Создать успешно" if not print_after else "Создать и печатать", "user")
        self._rw_note(card, "Запускает все preflight popup-и")
        self._rw_action_button(card, "Создать", lambda: self.create_selected_outputs(print_after=print_after), primary=True)

    def _rw_print_card(self, card: tk.Frame, number: int) -> None:
        self._rw_card_title(card, number, "Печать документов", "user")
        self._rw_note(card, "Создать, сохранить, распечатать")
        self._rw_value_label(card, self.printer_var)
        self._rw_action_button(card, "Печать", lambda: self.create_selected_outputs(print_after=True), row=3, primary=True)

    def _rw_success_card(self, card: tk.Frame, number: int) -> None:
        self._rw_card_title(card, number, "Успешная работа", "program")
        self._rw_note(card, "Документы созданы и сохранены")
        self._rw_value_label(card, text="Можно продолжать")

    def _rw_start_button_card(self, card: tk.Frame, number: int) -> None:
        self._rw_card_title(card, number, "Главный экран", "user")
        self._rw_note(card, "Загрузить файл и начать работу")
        self._rw_action_button(card, "НАЧАТЬ РАБОТУ", self.choose_navigation, primary=True)

    def _rw_success_footer(self, parent: tk.Frame, *, row: int) -> None:
        footer = tk.Frame(parent, bg=L_PANEL, highlightbackground=L_LINE, highlightthickness=1, padx=self._px(12, 8), pady=self._px(9, 6))
        footer.grid(row=row, column=0, sticky="ew", pady=(0, self._px(10, 6)))
        footer.grid_columnconfigure(1, weight=1)
        tk.Label(footer, text="УСПЕШНАЯ РАБОТА!", bg=L_PANEL, fg=L_SUCCESS, font=self._font(12, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(
            footer,
            text="Документы созданы · данные сохранены · можно открыть папку, печатать или начать нового пациента",
            bg=L_PANEL,
            fg=L_MUTED,
            font=self._font(9),
        ).grid(row=0, column=1, sticky="ew", padx=(self._px(14, 8), 0))
        self._rw_primary_button(footer, "Создать, сохранить, распечатать", lambda: self.create_selected_outputs(print_after=True), wide=True).grid(
            row=0, column=2, sticky="e", padx=(self._px(12, 8), 0)
        )

    def _rw_refresh_doctor_document_list(self) -> None:
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
            record_soft_exception("layout_mixin.real_wizard_docs", exc)
            docs = []
        self._custom_profile_documents = docs
        visible = {doc.kind for doc in docs}
        for kind in list(getattr(self, "custom_output_vars", {})):
            if kind not in visible:
                self.custom_output_vars.pop(kind, None)
                self.output_vars.pop(kind, None)
        if not docs:
            tk.Label(container, text="Кнопки ещё не созданы", bg=L_SOFT, fg=L_TEXT, font=self._font(8, "bold"), padx=5, pady=4).grid(
                row=0, column=0, sticky="ew"
            )
            self._rw_update_selected_count()
            return
        container.grid_columnconfigure(0, weight=1)
        max_visible = 5
        for i, doc in enumerate(docs[:max_visible]):
            var = self.custom_output_vars.get(doc.kind)
            if var is None:
                var = tk.BooleanVar(value=False)
                self.custom_output_vars[doc.kind] = var
            self.output_vars[doc.kind] = var
            chk = tk.Checkbutton(
                container,
                text=doc.label,
                variable=var,
                command=self._rw_update_selected_count,
                bg=L_PANEL,
                fg=L_TEXT,
                activebackground=L_PANEL,
                selectcolor=L_SOFT,
                anchor="w",
                justify="left",
                font=self._font(7, "bold"),
                wraplength=self._px(130, 90),
            )
            chk.grid(row=i, column=0, sticky="ew")
        if len(docs) > max_visible:
            tk.Label(container, text=f"+ ещё {len(docs) - max_visible}", bg=L_PANEL, fg=L_MUTED, font=self._font(7)).grid(row=max_visible, column=0, sticky="w")
        self._rw_update_selected_count()

    def _refresh_custom_profile_tiles(self) -> None:
        if getattr(self, "_real_wizard_ui_active", False) and hasattr(self, "_custom_profile_tiles_container"):
            self._rw_refresh_doctor_document_list()
            return
        super()._refresh_custom_profile_tiles()

    def _refresh_diary_frequency_controls(self) -> None:
        container = getattr(self, "_diary_frequency_container", None)
        if container is None:
            return
        for child in container.winfo_children():
            child.destroy()
        try:
            enabled = bool(self._diary_hourly_enabled())
        except Exception as exc:
            record_soft_exception("layout_mixin.diary_frequency", exc)
            enabled = False
        if not enabled:
            if getattr(self, "diary_frequency_mode_var", None):
                self.diary_frequency_mode_var.set("daily")
            return
        tk.Label(container, text="Дневники:", bg=L_PANEL, fg=L_MUTED, font=self._font(7, "bold")).grid(row=0, column=0, sticky="w")
        self._rw_small_button(container, "ежедневно", lambda: self._rw_set_diary_frequency("daily")).grid(row=0, column=1, padx=(4, 2))
        self._rw_small_button(container, "ежечасно", lambda: self._rw_set_diary_frequency("hourly")).grid(row=0, column=2, padx=(2, 0))

    def _rw_set_diary_frequency(self, mode: str) -> None:
        self.diary_frequency_mode_var.set(mode)
        self._refresh_diary_frequency_controls()

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

    def _rw_update_selected_count(self) -> None:
        count = sum(1 for var in getattr(self, "output_vars", {}).values() if var.get())
        if hasattr(self, "selected_outputs_count_var"):
            self.selected_outputs_count_var.set(f"Выбрано: {count}")

    def _rw_primary_button(self, parent, text: str, command, *, wide: bool = False) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=L_ACCENT,
            fg="#ffffff",
            activebackground=L_ACCENT_DARK,
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=self._px(12 if wide else 8, 6),
            pady=self._px(5, 3),
            font=self._font(8, "bold"),
            cursor="hand2",
        )

    def _rw_small_button(self, parent, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=L_SOFT_2,
            fg=L_ACCENT,
            activebackground="#dfeaff",
            activeforeground=L_ACCENT_DARK,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=L_LINE,
            padx=self._px(8, 5),
            pady=self._px(4, 2),
            font=self._font(7, "bold"),
            cursor="hand2",
        )

    def _rw_show_tour(self) -> None:
        messagebox.showinfo(
            "Краткий тур",
            "1. Создайте кнопки из своих Word-шаблонов.\n"
            "2. Загрузите первичный документ пациента.\n"
            "3. Проверьте найденные данные.\n"
            "4. Выберите документы для создания.\n"
            "5. Нажмите: создать, сохранить, распечатать.",
        )

    def _rw_notice(self, title: str, text: str) -> None:
        messagebox.showinfo(title, text)

    def _rw_call(self, method_name: str) -> None:
        method = getattr(self, method_name, None)
        if callable(method):
            method()


class LayoutMixin(LayoutWizardSurfaceMixin, LayoutSourcesMixin, LayoutChecklistMixin, LayoutActionBarMixin):
    pass
