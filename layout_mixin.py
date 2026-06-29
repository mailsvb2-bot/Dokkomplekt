from __future__ import annotations

import tkinter as tk

from app_config import ACCENT, BORDER_SOFT, DEEP, FIELD, MUTED, PANEL, PANEL_3, TEXT
from layout_sources import LayoutSourcesMixin
from layout_checklist import LayoutChecklistMixin
from layout_action_bar import LayoutActionBarMixin


class LayoutWizardSurfaceMixin:
    def _build_wizard_surface(self, parent: tk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)
        self._build_header(parent)

        workspace = tk.Frame(parent, bg=DEEP)
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.grid_columnconfigure(0, minsize=self._px(170, 132))
        workspace.grid_columnconfigure(1, weight=1)
        workspace.grid_rowconfigure(0, weight=1)

        self._build_wizard_rail(workspace)
        pages = tk.Frame(workspace, bg=DEEP)
        pages.grid(row=0, column=1, sticky="nsew", padx=(self._px(16, 8), 0))
        pages.grid_columnconfigure(0, weight=1)
        for row in range(6):
            pages.grid_rowconfigure(row, weight=0)

        self._wizard_shell_active = True
        try:
            self._build_wizard_context_banner(pages)
            self._build_patient_card(pages)
            self._build_input_files_card(pages)
            self._build_create_checklist_card(pages)
            self._build_action_bar(pages)
        finally:
            self._wizard_shell_active = False

    def _build_wizard_rail(self, parent: tk.Frame) -> None:
        rail = tk.Frame(parent, bg=DEEP)
        rail.grid(row=0, column=0, sticky="nsw", padx=(0, self._px(6, 2)))
        steps = (
            ("01", "Документ", "Загрузите первичный DOCX/DOCM"),
            ("02", "Данные", "Проверьте найденные поля"),
            ("03", "Создать", "Выберите документы врача"),
            ("04", "Готово", "Сохранить или распечатать"),
        )
        for idx, (number, title, hint) in enumerate(steps):
            item = tk.Frame(rail, bg=DEEP)
            item.grid(row=idx, column=0, sticky="ew", pady=(0, self._px(18 if idx < 3 else 0, 8)))
            item.grid_columnconfigure(1, weight=1)
            active = idx == 0
            tk.Label(
                item,
                text=number,
                bg=("#eef5ff" if active else "#f8fbff"),
                fg=(ACCENT if active else MUTED),
                highlightbackground=(ACCENT if active else BORDER_SOFT),
                highlightthickness=2 if active else 1,
                font=self._font(15 if active else 13, "bold"),
                width=4,
                padx=self._px(5, 3),
                pady=self._px(10, 6),
            ).grid(row=0, column=0, sticky="n", padx=(0, self._px(10, 5)))
            box = tk.Frame(item, bg=DEEP)
            box.grid(row=0, column=1, sticky="ew")
            tk.Label(box, text=title, bg=DEEP, fg=(ACCENT if active else MUTED), anchor="w", font=self._font(12 if active else 11, "bold" if active else None)).grid(row=0, column=0, sticky="ew")
            tk.Label(box, text=hint, bg=DEEP, fg=MUTED, anchor="w", wraplength=self._px(115, 92), justify="left", font=self._font(8)).grid(row=1, column=0, sticky="ew", pady=(self._px(3, 1), 0))

    def _build_wizard_context_banner(self, parent: tk.Frame) -> None:
        banner = tk.Frame(parent, bg=PANEL, highlightbackground=BORDER_SOFT, highlightthickness=1, padx=self._px(14, 8), pady=self._px(10, 6))
        banner.grid(row=0, column=0, sticky="ew", pady=(0, self._px(10, 5)))
        banner.grid_columnconfigure(0, weight=1)
        for col in range(1, 4):
            banner.grid_columnconfigure(col, weight=0)
        tk.Label(banner, text="Простой путь: документ → данные → какие документы создать → сохранить / распечатать", bg=PANEL, fg=TEXT, anchor="w", font=self._font(10, "bold")).grid(row=0, column=0, sticky="ew")
        tk.Label(banner, text="Скрытые проверки, popup-и, дубликаты, лицензия, папки и принтер остаются под капотом.", bg=PANEL, fg=MUTED, anchor="w", font=self._font(9)).grid(row=1, column=0, sticky="ew", pady=(self._px(2, 1), 0))
        self._wizard_top_button(banner, text="Создать кнопки", command=lambda: self._safe_call_ui("_open_first_run_create_buttons_popup")).grid(row=0, column=1, rowspan=2, sticky="e", padx=(self._px(10, 5), 0))
        self._wizard_top_button(banner, text="Папка пациента", command=lambda: self._safe_call_ui("configure_patient_folder_naming_dialog")).grid(row=0, column=2, rowspan=2, sticky="e", padx=(self._px(8, 4), 0))
        self._wizard_top_button(banner, text="Лицензия", command=lambda: self._safe_call_ui("show_product_license_dialog")).grid(row=0, column=3, rowspan=2, sticky="e", padx=(self._px(8, 4), 0))

    def _wizard_top_button(self, parent: tk.Frame, *, text: str, command) -> tk.Button:
        return tk.Button(parent, text=text, command=command, bg=FIELD, fg=ACCENT, activebackground=PANEL_3, activeforeground=ACCENT, relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER_SOFT, padx=self._px(12, 8), pady=self._px(6, 4), font=self._font(9, "bold"), cursor="hand2")

    def _safe_call_ui(self, method_name: str) -> None:
        method = getattr(self, method_name, None)
        if callable(method):
            method()


class LayoutMixin(LayoutWizardSurfaceMixin, LayoutSourcesMixin, LayoutChecklistMixin, LayoutActionBarMixin):
    pass
