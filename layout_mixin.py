from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from diagnostic_logging import record_soft_exception
from layout_action_bar import LayoutActionBarMixin
from layout_checklist import FIRST_RUN_CREATE_BUTTON_LABEL, LayoutChecklistMixin, _doctor_buttons_setup_completed
from layout_sources import LayoutSourcesMixin

L_BG, L_PANEL, L_SOFT, L_SOFT_2, L_LINE = "#f3f6fb", "#ffffff", "#f7faff", "#eef5ff", "#d8e2ef"
L_TEXT, L_MUTED, L_ACCENT, L_ACCENT_DARK = "#172033", "#667085", "#2f73e8", "#1f5fd0"
L_SUCCESS, L_ERROR = "#14804a", "#c2415d"
MARKERS = {"user": L_SUCCESS, "program": "#61a878", "choice": "#f59e0b", "info": "#5b5fc7", "error": L_ERROR, "hidden": "#5b5fc7"}

BOARD_TEXT = """
I. ЗАПУСК И ПЕРВИЧНАЯ НАСТРОЙКА|1|Запуск программы|Версия и старт окна|program|ready
I. ЗАПУСК И ПЕРВИЧНАЯ НАСТРОЙКА|2|Мастер первого запуска|Рабочая папка и кнопки|user|tour
I. ЗАПУСК И ПЕРВИЧНАЯ НАСТРОЙКА|3|Выбор папки|Куда сохранять документы|choice|folder
I. ЗАПУСК И ПЕРВИЧНАЯ НАСТРОЙКА|4|Язык и тема|Интерфейс и язык документов|choice|language
I. ЗАПУСК И ПЕРВИЧНАЯ НАСТРОЙКА|5|Принтер по умолчанию|Проверить печать|choice|printer_setup
I. ЗАПУСК И ПЕРВИЧНАЯ НАСТРОЙКА|6|Главный экран|Начать работу|user|primary
I. ЗАПУСК И ПЕРВИЧНАЯ НАСТРОЙКА|7|Проверка обновлений|Версия актуальна|program|updates
I. ЗАПУСК И ПЕРВИЧНАЯ НАСТРОЙКА|8|Лицензия|Условия и доступ|choice|license
I. ЗАПУСК И ПЕРВИЧНАЯ НАСТРОЙКА|9|Профиль врача|ФИО, специальность, шаблоны|user|profile
I. ЗАПУСК И ПЕРВИЧНАЯ НАСТРОЙКА|10|Краткий тур|Показать подсказку|info|tour
II. ЗАГРУЗКА ПЕРВИЧНОГО ДОКУМЕНТА И АНАЛИЗ|11|Перетащить файл|Первичный DOCX/DOCM|user|primary
II. ЗАГРУЗКА ПЕРВИЧНОГО ДОКУМЕНТА И АНАЛИЗ|12|Файл загружен|Текущий путь|user|path
II. ЗАГРУЗКА ПЕРВИЧНОГО ДОКУМЕНТА И АНАЛИЗ|13|Анализ документа|Повторно распознать|program|reparse
II. ЗАГРУЗКА ПЕРВИЧНОГО ДОКУМЕНТА И АНАЛИЗ|14|Результаты анализа|ФИО, даты, диагноз, МКБ|program|ready
II. ЗАГРУЗКА ПЕРВИЧНОГО ДОКУМЕНТА И АНАЛИЗ|15|Предпросмотр текста|Показать найденные данные|info|preview
II. ЗАГРУЗКА ПЕРВИЧНОГО ДОКУМЕНТА И АНАЛИЗ|16|Найденные данные|ФИО пациента|program|patient
II. ЗАГРУЗКА ПЕРВИЧНОГО ДОКУМЕНТА И АНАЛИЗ|17|Проверка разделов|Жалобы, анамнез, лечение|program|ready
II. ЗАГРУЗКА ПЕРВИЧНОГО ДОКУМЕНТА И АНАЛИЗ|18|Ошибки анализа|Если раздел не найден|error|diagnostics
II. ЗАГРУЗКА ПЕРВИЧНОГО ДОКУМЕНТА И АНАЛИЗ|19|Подтверждение данных|Использовать найденные данные|user|preview
II. ЗАГРУЗКА ПЕРВИЧНОГО ДОКУМЕНТА И АНАЛИЗ|20|Сохранить результат|Папка результата|program|folder
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|21|Выбор документов|Кнопки из шаблонов врача|user|docs
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|22|Личные данные|ФИО / название файла|user|patient_edit
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|23|№ истории|Сквозное поле|user|case
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|24|Даты и период|Поступление / выписка|user|dates
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|25|Диагноз|Распознанный или введённый|user|diagnosis
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|26|Лечение|Popup при отсутствии лечения|user|treatment
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|27|Специальные поля|Открываются popup-и|choice|preview
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|28|Ошибка шаблона|Показать профиль|error|profile
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|29|Нет прав на папку|Выбрать другую|error|folder
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|30|Документ открыт|Закрыть Word и повторить|error|ready
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|31|Больничный|Да / нет|choice|sick
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|32|Дата протокола|Проверить данные|choice|preview
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|33|Проверка связей|Данные связаны|program|preview
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|34|Выбор формулировок|Из popup/шаблонов|choice|profile
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|35|Примечание|Добавить через popup|choice|preview
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|36|Копировать данные|Из другого документа|hidden|ready
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|37|Очистить ФИО|Сброс полей|choice|reset
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|38|Очистить поля|Сброс настроек|choice|reset
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|39|Проверка шаблона|Диагностика|program|diagnostics
III. ВЫБОР ДОКУМЕНТОВ И ЗАПОЛНЕНИЕ ДАННЫХ|40|Готово к созданию|Можно создавать|program|create
IV. СОЗДАНИЕ ДОКУМЕНТОВ И СОХРАНЕНИЕ|41|Создание документов|Выбранные кнопки|user|docs
IV. СОЗДАНИЕ ДОКУМЕНТОВ И СОХРАНЕНИЕ|42|Прогресс|Создание и проверки|program|ready
IV. СОЗДАНИЕ ДОКУМЕНТОВ И СОХРАНЕНИЕ|43|Папка сохранения|Куда попадут документы|choice|folder_value
IV. СОЗДАНИЕ ДОКУМЕНТОВ И СОХРАНЕНИЕ|44|Имя файлов|Дата / номер / подпапка|choice|folder_naming
IV. СОЗДАНИЕ ДОКУМЕНТОВ И СОХРАНЕНИЕ|45|Создать успешно|Preflight + popup-и|user|create
IV. СОЗДАНИЕ ДОКУМЕНТОВ И СОХРАНЕНИЕ|46|Кол-во файлов|Отчёт после создания|info|ready
IV. СОЗДАНИЕ ДОКУМЕНТОВ И СОХРАНЕНИЕ|47|Быстрый просмотр|Проверить данные|info|preview
IV. СОЗДАНИЕ ДОКУМЕНТОВ И СОХРАНЕНИЕ|48|Дубликаты|Перезаписать / копия|choice|folder_naming
IV. СОЗДАНИЕ ДОКУМЕНТОВ И СОХРАНЕНИЕ|49|Открыть папку|Выбрать/открыть результат|user|folder
IV. СОЗДАНИЕ ДОКУМЕНТОВ И СОХРАНЕНИЕ|50|Успешная работа|Документы созданы|program|ready
V. ПЕЧАТЬ, ЭКСПОРТ И ПЕРЕДАЧА|51|Печать документа|Создать + печать|user|print
V. ПЕЧАТЬ, ЭКСПОРТ И ПЕРЕДАЧА|52|Настройка печати|Выбор принтера|choice|printer_setup
V. ПЕЧАТЬ, ЭКСПОРТ И ПЕРЕДАЧА|53|Экспорт PDF|Зарезервировано|hidden|ready
V. ПЕЧАТЬ, ЭКСПОРТ И ПЕРЕДАЧА|54|Экспорт RTF|Зарезервировано|hidden|ready
V. ПЕЧАТЬ, ЭКСПОРТ И ПЕРЕДАЧА|55|Экспорт TXT|Зарезервировано|hidden|ready
V. ПЕЧАТЬ, ЭКСПОРТ И ПЕРЕДАЧА|56|Экспорт ODT|Зарезервировано|hidden|ready
V. ПЕЧАТЬ, ЭКСПОРТ И ПЕРЕДАЧА|57|Экспорт DOCX|Основной формат|program|ready
V. ПЕЧАТЬ, ЭКСПОРТ И ПЕРЕДАЧА|58|Подтверждение печати|Все данные проверены|user|ready
V. ПЕЧАТЬ, ЭКСПОРТ И ПЕРЕДАЧА|59|Создать архив|Пакетное создание|hidden|batch
V. ПЕЧАТЬ, ЭКСПОРТ И ПЕРЕДАЧА|60|Передать в систему|Зарезервировано|hidden|ready
VI. ШАБЛОНЫ, ПРОФИЛИ И НАПОМИНАНИЯ|61|Редактор шаблонов|Профиль врача|user|profile
VI. ШАБЛОНЫ, ПРОФИЛИ И НАПОМИНАНИЯ|62|Добавить поле|Через мастер профиля|user|profile
VI. ШАБЛОНЫ, ПРОФИЛИ И НАПОМИНАНИЯ|63|Настройка папки|Подпапки пациента|choice|folder_naming
VI. ШАБЛОНЫ, ПРОФИЛИ И НАПОМИНАНИЯ|64|Условные поля|Проверка программы|program|diagnostics
VI. ШАБЛОНЫ, ПРОФИЛИ И НАПОМИНАНИЯ|65|Проверка полей|Диагностика|program|diagnostics
VI. ШАБЛОНЫ, ПРОФИЛИ И НАПОМИНАНИЯ|66|Просмотр шаблона|Открыть профиль|info|profile
VI. ШАБЛОНЫ, ПРОФИЛИ И НАПОМИНАНИЯ|67|Деталь шаблона|Поля и правила|info|ready
VI. ШАБЛОНЫ, ПРОФИЛИ И НАПОМИНАНИЯ|68|Восстановить|Через профиль|hidden|ready
VI. ШАБЛОНЫ, ПРОФИЛИ И НАПОМИНАНИЯ|69|Напоминания|Зарезервировано|hidden|ready
VI. ШАБЛОНЫ, ПРОФИЛИ И НАПОМИНАНИЯ|70|Проверка шаблонов|Запустить аудит|program|diagnostics
VII. ЖУРНАЛ ДЕЙСТВИЙ И ЛОГИ|71|Открыть журнал|Диагностика|info|diagnostics
VII. ЖУРНАЛ ДЕЙСТВИЙ И ЛОГИ|72|Фильтр|Даты и действия|info|ready
VII. ЖУРНАЛ ДЕЙСТВИЙ И ЛОГИ|73|Оценка действий|Служебный отчёт|program|ready
VII. ЖУРНАЛ ДЕЙСТВИЙ И ЛОГИ|74|Экспорт лога|Зарезервировано|hidden|ready
VII. ЖУРНАЛ ДЕЙСТВИЙ И ЛОГИ|75|Детали события|Ошибки и действия|info|ready
VII. ЖУРНАЛ ДЕЙСТВИЙ И ЛОГИ|76|Печать журнала|Зарезервировано|hidden|ready
VII. ЖУРНАЛ ДЕЙСТВИЙ И ЛОГИ|77|Очистить журнал|Зарезервировано|hidden|ready
VII. ЖУРНАЛ ДЕЙСТВИЙ И ЛОГИ|78|Проверка|Диагностика установки|program|diagnostics
VII. ЖУРНАЛ ДЕЙСТВИЙ И ЛОГИ|79|Журнал ошибок|Служебно|info|ready
VII. ЖУРНАЛ ДЕЙСТВИЙ И ЛОГИ|80|Настройки журнала|Зарезервировано|hidden|ready
VIII. НАСТРОЙКИ И ПРОГРАММА|81|Общие настройки|Папки, язык, печать|choice|folder_naming
VIII. НАСТРОЙКИ И ПРОГРАММА|82|История печати|Принтер|choice|printer_setup
VIII. НАСТРОЙКИ И ПРОГРАММА|83|Путь к данным|Папка вывода|choice|folder_value
VIII. НАСТРОЙКИ И ПРОГРАММА|84|Резервное копирование|Зарезервировано|hidden|ready
VIII. НАСТРОЙКИ И ПРОГРАММА|85|Восстановление|Зарезервировано|hidden|ready
VIII. НАСТРОЙКИ И ПРОГРАММА|86|Язык интерфейса|Русский / English|choice|language
VIII. НАСТРОЙКИ И ПРОГРАММА|87|Тема|Светлая рабочая|choice|theme
VIII. НАСТРОЙКИ И ПРОГРАММА|88|Горячие клавиши|F5 / F8 / F9|info|ready
VIII. НАСТРОЙКИ И ПРОГРАММА|89|О программе|Локальное приложение|info|ready
VIII. НАСТРОЙКИ И ПРОГРАММА|90|Выход|Закрыть программу|choice|exit
IX. ИСКЛЮЧИТЕЛЬНЫЕ СИТУАЦИИ И ОШИБКИ|91|Ошибка анализа|Не удалось распознать файл|error|diagnostics
IX. ИСКЛЮЧИТЕЛЬНЫЕ СИТУАЦИИ И ОШИБКИ|92|Ошибка шаблона|Шаблон повреждён|error|profile
IX. ИСКЛЮЧИТЕЛЬНЫЕ СИТУАЦИИ И ОШИБКИ|93|Ошибка печати|Принтер недоступен|error|printer_setup
IX. ИСКЛЮЧИТЕЛЬНЫЕ СИТУАЦИИ И ОШИБКИ|94|Нет доступа|Выбрать другую папку|error|folder
IX. ИСКЛЮЧИТЕЛЬНЫЕ СИТУАЦИИ И ОШИБКИ|95|Сбой программы|Диагностика|error|diagnostics
X. СКРЫТЫЕ СЦЕНАРИИ И ДОПОЛНИТЕЛЬНЫЕ ВОЗМОЖНОСТИ|96|Быстрое создание|Drag & Drop файла|hidden|primary
X. СКРЫТЫЕ СЦЕНАРИИ И ДОПОЛНИТЕЛЬНЫЕ ВОЗМОЖНОСТИ|97|Автозаполнение|Из предыдущих данных|hidden|ready
X. СКРЫТЫЕ СЦЕНАРИИ И ДОПОЛНИТЕЛЬНЫЕ ВОЗМОЖНОСТИ|98|Макросы и скрипты|Не выполняются|hidden|ready
X. СКРЫТЫЕ СЦЕНАРИИ И ДОПОЛНИТЕЛЬНЫЕ ВОЗМОЖНОСТИ|99|Интеграция|Зарезервировано|hidden|ready
X. СКРЫТЫЕ СЦЕНАРИИ И ДОПОЛНИТЕЛЬНЫЕ ВОЗМОЖНОСТИ|100|Многопользовательский режим|Локальные профили|hidden|ready
"""


class LayoutWizardSurfaceMixin:
    def _build_wizard_surface(self, parent: tk.Frame) -> None:
        """Render the board-style Dokkomplekt workflow while calling existing production methods."""
        self._real_wizard_ui_active = True
        parent.configure(bg=L_BG)
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)
        self._rw_header(parent)
        self._rw_board(parent)

    def _rw_header(self, parent: tk.Frame) -> None:
        header = tk.Frame(parent, bg=L_BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, self._px(8, 4)))
        header.grid_columnconfigure(0, weight=1)
        self._bind_window_drag(header)
        left = tk.Frame(header, bg=L_BG)
        left.grid(row=0, column=0, sticky="w")
        self._bind_window_drag(left)
        tk.Label(left, text="DOKKOMPLEKT — 100 ГЛУБОКИХ ПРОГОНОВ ПОЛЬЗОВАТЕЛЬСКИХ ДЕЙСТВИЙ", bg=L_BG, fg="#111f70", font=self._font(16, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(left, text="полный путь: запуск → анализ → выбор → popup-и → создание → печать → ошибки → скрытые сценарии", bg=L_BG, fg="#111f70", font=self._font(8, "bold")).grid(row=1, column=0, sticky="w")
        right = tk.Frame(header, bg=L_BG)
        right.grid(row=0, column=1, sticky="e")
        for col, (text, command) in enumerate((("Лицензия", lambda: self._rw_call("show_product_license_dialog")), ("Профиль", self._open_universal_document_mapper), ("Папка вывода", self.choose_output_dir), ("Язык", lambda: self._rw_call("_open_language_settings")))):
            self._rw_small_button(right, text, command).grid(row=0, column=col, padx=(0, self._px(5, 3)))
        self._window_control_button(right, "−", self._minimize_window).grid(row=0, column=4)
        self._window_control_button(right, "□", self._toggle_maximize).grid(row=0, column=5)
        self._window_control_button(right, "×", self.root.destroy, danger=True).grid(row=0, column=6)

    def _rw_board(self, parent: tk.Frame) -> None:
        shell = tk.Frame(parent, bg=L_BG)
        shell.grid(row=1, column=0, sticky="nsew")
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(0, weight=1)
        canvas = tk.Canvas(shell, bg=L_BG, highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        board = tk.Frame(canvas, bg=L_BG)
        window_id = canvas.create_window((0, 0), window=board, anchor="nw")
        board.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"), add="+")
        board.grid_columnconfigure(0, weight=1)
        self._rw_legend(board, 0)
        for row, (title, cards) in enumerate(self._rw_sections().items(), start=1):
            self._rw_section(board, row, title, cards)
        self._rw_success_footer(board, len(self._rw_sections()) + 1)
        self.status_label = self._status_bar_label
        self.progress = ttk.Progressbar(board, mode="indeterminate", length=180)

    def _rw_sections(self) -> dict[str, list[dict[str, str]]]:
        """Parse the static 100-card board description into sections."""
        sections: dict[str, list[dict[str, str]]] = {}
        for raw in BOARD_TEXT.strip().splitlines():
            section, number, title, note, marker, action = raw.split("|")
            sections.setdefault(section, []).append({"n": number, "title": title, "note": note, "marker": marker, "action": action})
        return sections

    def _rw_legend(self, parent: tk.Frame, row: int) -> None:
        legend = tk.Frame(parent, bg=L_PANEL, highlightbackground=L_LINE, highlightthickness=1, padx=self._px(9, 5), pady=self._px(6, 3))
        legend.grid(row=row, column=0, sticky="ew", pady=(0, self._px(7, 4)))
        legend.grid_columnconfigure(0, weight=1)
        tk.Label(legend, text="Обозначения:", bg=L_PANEL, fg=L_TEXT, font=self._font(8, "bold")).grid(row=0, column=0, sticky="w")
        for idx, (marker, text) in enumerate((("user", "действие пользователя"), ("program", "действие программы"), ("choice", "выбор / опция"), ("info", "информация / результат"), ("error", "ошибка / предупреждение")), start=1):
            dot = tk.Canvas(legend, width=12, height=12, bg=L_PANEL, highlightthickness=0)
            dot.grid(row=0, column=idx * 2 - 1, padx=(self._px(12, 6), self._px(3, 2)))
            dot.create_oval(2, 2, 10, 10, fill=MARKERS[marker], outline=MARKERS[marker])
            tk.Label(legend, text=text, bg=L_PANEL, fg=L_MUTED, font=self._font(7, "bold")).grid(row=0, column=idx * 2, sticky="w")

    def _rw_section(self, parent: tk.Frame, row: int, title: str, cards: list[dict[str, str]]) -> None:
        section = tk.Frame(parent, bg=L_BG, highlightbackground=L_LINE, highlightthickness=1, padx=self._px(6, 4), pady=self._px(5, 3))
        section.grid(row=row, column=0, sticky="ew", pady=(0, self._px(7, 4)))
        section.grid_columnconfigure(0, weight=1)
        tk.Label(section, text=title, bg=L_BG, fg="#111f70", font=self._font(9, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        grid = tk.Frame(section, bg=L_BG)
        grid.grid(row=1, column=0, sticky="ew", pady=(self._px(4, 2), 0))
        cols = 10 if not getattr(self, "_compact_ui", False) else 5
        for col in range(cols):
            grid.grid_columnconfigure(col, weight=1, uniform=f"section-{row}")
        for idx, spec in enumerate(cards):
            card = tk.Frame(grid, bg=L_PANEL, highlightbackground=L_LINE, highlightthickness=1, padx=self._px(6, 4), pady=self._px(5, 3))
            card.grid(row=idx // cols, column=idx % cols, sticky="nsew", padx=self._px(2, 1), pady=self._px(2, 1))
            card.grid_columnconfigure(0, weight=1)
            self._rw_render_card(card, spec)

    def _rw_render_card(self, card: tk.Frame, spec: dict[str, str]) -> None:
        marker, action = spec["marker"], spec["action"]
        self._rw_title(card, int(spec["n"]), spec["title"], marker)
        self._rw_note(card, spec["note"])
        if action == "docs":
            self._rw_docs_panel(card)
        elif action in {"patient_edit", "case", "diagnosis", "treatment", "sick"}:
            self._rw_entry(card, {"patient_edit": self.patient_name_var, "case": self.case_number_var, "diagnosis": self.diagnosis_var, "treatment": self.assigned_treatment_var, "sick": self.expert_sick_leave_display_var}[action])
        elif action == "dates":
            self._rw_entry(card, self.admission_date_var)
            self._rw_entry(card, self.discharge_date_var, row=3)
        elif action in {"path", "patient", "folder_value", "printer_setup", "printer"}:
            self._rw_value(card, {"path": self.navigation_path_var, "patient": self.patient_name_var, "folder_value": self.output_dir_var, "printer_setup": self.printer_var, "printer": self.printer_var}[action])
            self._rw_action_for(card, action, row=3)
        else:
            command = self._rw_command(action)
            if command is None:
                self._rw_value(card, text="скрыто" if marker == "hidden" else "готово")
            else:
                self._rw_action_for(card, action, row=2)

    def _rw_title(self, card: tk.Frame, number: int, title: str, marker: str) -> None:
        top = tk.Frame(card, bg=L_PANEL)
        top.grid(row=0, column=0, sticky="ew")
        dot = tk.Canvas(top, width=12, height=12, bg=L_PANEL, highlightthickness=0)
        dot.grid(row=0, column=0, sticky="w", padx=(0, 4))
        color = MARKERS.get(marker, MARKERS["info"])
        dot.create_oval(2, 2, 10, 10, fill=color, outline=color)
        tk.Label(top, text=f"{number}. {title}", bg=L_PANEL, fg="#111f70", font=self._font(7, "bold"), anchor="w", justify="left", wraplength=self._px(145, 92)).grid(row=0, column=1, sticky="ew")
        top.grid_columnconfigure(1, weight=1)

    def _rw_note(self, card: tk.Frame, text: str) -> None:
        tk.Label(card, text=text, bg=L_PANEL, fg=L_MUTED, font=self._font(7), anchor="w", justify="left", wraplength=self._px(150, 95)).grid(row=1, column=0, sticky="ew", pady=(self._px(3, 2), 0))

    def _rw_value(self, card: tk.Frame, variable: tk.Variable | None = None, text: str = "", row: int = 2) -> tk.Label:
        label = tk.Label(card, textvariable=variable, text=text if variable is None else "", bg=L_SOFT, fg=L_TEXT, highlightbackground=L_LINE, highlightthickness=1, font=self._font(7), anchor="w", justify="left", padx=self._px(5, 3), pady=self._px(3, 2), wraplength=self._px(135, 88))
        label.grid(row=row, column=0, sticky="ew", pady=(self._px(4, 2), 0))
        return label

    def _rw_entry(self, card: tk.Frame, variable: tk.StringVar, row: int = 2) -> None:
        tk.Entry(card, textvariable=variable, bg=L_SOFT, fg=L_TEXT, relief="flat", highlightbackground=L_LINE, highlightthickness=1, font=self._font(7)).grid(row=row, column=0, sticky="ew", pady=(self._px(4, 2), 0), ipady=self._px(2, 1))

    def _rw_command(self, action: str):
        return {
            "tour": self._rw_show_tour,
            "folder": self.choose_output_dir,
            "language": lambda: self._rw_call("_open_language_settings"),
            "license": lambda: self._rw_call("show_product_license_dialog"),
            "profile": self._open_universal_document_mapper,
            "primary": self.choose_navigation,
            "reparse": lambda: self.reparse_navigation(silent=False),
            "preview": self.show_found_patient_data,
            "diagnostics": self.show_installation_diagnostics_dialog,
            "reset": self.reset_settings_dialog,
            "folder_naming": self.configure_patient_folder_naming_dialog,
            "create": lambda: self.create_selected_outputs(print_after=False),
            "print": lambda: self.create_selected_outputs(print_after=True),
            "printer": lambda: self.create_selected_outputs(print_after=True),
            "printer_setup": self.refresh_printers,
            "updates": self.check_updates_dialog,
            "batch": self.batch_generate_documents_dialog,
            "theme": lambda: self._rw_notice("Тема", "Светлая рабочая схема закреплена."),
            "exit": self.root.destroy,
        }.get(action)

    def _rw_action_for(self, card: tk.Frame, action: str, row: int) -> None:
        command = self._rw_command(action)
        if command is None:
            return
        text = {"primary": "Выбрать", "create": "Создать", "print": "Печать", "printer": "Печать", "tour": "Да", "folder": "Изменить"}.get(action, "Открыть")
        self._rw_button(card, text, command, row, action in {"primary", "create", "print", "printer"})

    def _rw_button(self, card: tk.Frame, text: str, command, row: int, primary: bool = False) -> None:
        button = self._rw_primary_button(card, text, command) if primary else self._rw_small_button(card, text, command)
        button.grid(row=row, column=0, sticky="ew", pady=(self._px(5, 2), 0))

    def _rw_docs_panel(self, card: tk.Frame) -> None:
        self._custom_profile_tiles_container = tk.Frame(card, bg=L_PANEL)
        self._custom_profile_tiles_container.grid(row=2, column=0, sticky="ew", pady=(self._px(4, 2), 0))
        self._diary_frequency_container = tk.Frame(card, bg=L_PANEL)
        self._diary_frequency_container.grid(row=3, column=0, sticky="ew")
        self.selected_outputs_count_var = tk.StringVar(value="Выбрано: 0")
        self._rw_refresh_doctor_document_list()
        buttons = tk.Frame(card, bg=L_PANEL)
        buttons.grid(row=4, column=0, sticky="ew", pady=(self._px(4, 2), 0))
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)
        self._rw_small_button(buttons, "Все", self._rw_select_all_outputs).grid(row=0, column=0, sticky="ew", padx=(0, 2))
        self._rw_small_button(buttons, "Снять", self._rw_clear_outputs).grid(row=0, column=1, sticky="ew", padx=(2, 0))

    def _rw_success_footer(self, parent: tk.Frame, row: int) -> None:
        footer = tk.Frame(parent, bg=L_PANEL, highlightbackground=L_LINE, highlightthickness=1, padx=self._px(10, 6), pady=self._px(8, 5))
        footer.grid(row=row, column=0, sticky="ew", pady=(0, self._px(10, 6)))
        footer.grid_columnconfigure(1, weight=1)
        tk.Label(footer, text="УСПЕШНАЯ РАБОТА!", bg=L_PANEL, fg=L_SUCCESS, font=self._font(12, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(footer, text="Документы созданы · данные сохранены · можно продолжать", bg=L_PANEL, fg=L_MUTED, font=self._font(9)).grid(row=0, column=1, sticky="ew", padx=(self._px(12, 8), 0))
        self._rw_primary_button(footer, "Создать, сохранить, распечатать", lambda: self.create_selected_outputs(print_after=True), wide=True).grid(row=0, column=2, sticky="e")

    def _rw_refresh_doctor_document_list(self) -> None:
        """Refresh doctor-owned document checkboxes without falling back to the legacy dark tile grid."""
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
            tk.Label(container, text="Кнопки ещё не созданы", bg=L_SOFT, fg=L_TEXT, font=self._font(8, "bold"), padx=5, pady=4).grid(row=0, column=0, sticky="ew")
            self._rw_primary_button(container, FIRST_RUN_CREATE_BUTTON_LABEL, self._open_first_run_create_buttons_popup).grid(row=1, column=0, sticky="ew", pady=(3, 0))
            self._rw_update_selected_count()
            return
        container.grid_columnconfigure(0, weight=1)
        for row, doc in enumerate(docs[:5]):
            var = self.custom_output_vars.get(doc.kind)
            if var is None:
                var = tk.BooleanVar(value=False)
                self.custom_output_vars[doc.kind] = var
            self.output_vars[doc.kind] = var
            tk.Checkbutton(container, text=doc.label, variable=var, command=self._rw_update_selected_count, bg=L_PANEL, fg=L_TEXT, activebackground=L_PANEL, selectcolor=L_SOFT, anchor="w", justify="left", font=self._font(7, "bold"), wraplength=self._px(130, 90)).grid(row=row, column=0, sticky="ew")
        if len(docs) > 5:
            tk.Label(container, text=f"+ ещё {len(docs) - 5}", bg=L_PANEL, fg=L_MUTED, font=self._font(7)).grid(row=5, column=0, sticky="w")
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
        self._rw_small_button(container, "день", lambda: self._rw_set_diary_frequency("daily")).grid(row=0, column=1, padx=(4, 2))
        self._rw_small_button(container, "час", lambda: self._rw_set_diary_frequency("hourly")).grid(row=0, column=2, padx=(2, 0))

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
        return tk.Button(parent, text=text, command=command, bg=L_ACCENT, fg="#ffffff", activebackground=L_ACCENT_DARK, activeforeground="#ffffff", relief="flat", bd=0, padx=self._px(11 if wide else 8, 5), pady=self._px(4, 2), font=self._font(7, "bold"), cursor="hand2")

    def _rw_small_button(self, parent, text: str, command) -> tk.Button:
        return tk.Button(parent, text=text, command=command, bg=L_SOFT_2, fg=L_ACCENT, activebackground="#dfeaff", activeforeground=L_ACCENT_DARK, relief="flat", bd=0, highlightthickness=1, highlightbackground=L_LINE, padx=self._px(7, 4), pady=self._px(3, 2), font=self._font(7, "bold"), cursor="hand2")

    def _rw_show_tour(self) -> None:
        messagebox.showinfo("Краткий тур", "1. Создайте кнопки из своих Word-шаблонов.\n2. Загрузите первичный документ.\n3. Проверьте данные.\n4. Выберите документы.\n5. Создайте, сохраните и распечатайте.")

    def _rw_notice(self, title: str, text: str) -> None:
        messagebox.showinfo(title, text)

    def _rw_call(self, method_name: str) -> None:
        method = getattr(self, method_name, None)
        if callable(method):
            method()


class LayoutMixin(LayoutWizardSurfaceMixin, LayoutSourcesMixin, LayoutChecklistMixin, LayoutActionBarMixin):
    pass
