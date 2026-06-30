from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app_config import DEEP, MUTED, PANEL
from i18n_strings import tr
from medical_language_catalog import language_choices, language_id_from_choice, language_profile

class WindowCoreMixin:
    def _build_ui(self) -> None:
        self._setup_style()

        self._status_bar_label = tk.Label(self.root, text="", bg="#ffffff", fg=MUTED, font=self._font(11))

        shell = tk.Frame(self.root, bg="#ffffff", highlightthickness=1, highlightbackground="#d8e2ef")
        shell.pack(fill="both", expand=True, padx=0, pady=0)

        content = tk.Frame(shell, bg="#f3f6fb")
        content.pack(fill="both", expand=True, padx=self._px(12, 8), pady=(self._px(10, 6), self._px(8, 4)))
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(1, weight=1)

        if hasattr(self, "_build_wizard_surface"):
            self._build_wizard_surface(content)
            return

        for row in range(5):
            content.grid_rowconfigure(row, weight=0)
        self._build_header(content)
        self._build_patient_card(content)
        self._build_input_files_card(content)
        self._build_create_checklist_card(content)
        self._build_action_bar(content)

    def _px(self, value: int | float, minimum: int = 1) -> int:
        """Pixel helper: сохраняет пропорции референса на компактном окне 1/3 экрана."""
        return max(minimum, int(round(float(value) * getattr(self, "_ui_scale", 1.0))))

    def _font(self, size: int | float, weight: str | None = None) -> tuple:
        scaled = max(8, int(round(float(size) * getattr(self, "_font_scale", 1.0))))
        return ("Segoe UI", scaled, weight) if weight else ("Segoe UI", scaled)

    def _build_one_window_workspace(self, parent: tk.Frame) -> None:
        self._build_input_files_card(parent)
        self._build_create_checklist_card(parent)

    def _build_input_files_card(self, parent: tk.Frame) -> None:
        section, body = self._section(parent, "02", "folder", "Входные\nфайлы")
        section.grid(row=2, column=0, sticky="ew", pady=(0, 3))

        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        files = tk.Frame(body, bg=PANEL)
        files.grid(row=0, column=0, sticky="nsew", pady=(self._px(1, 0), 0))
        files.grid_columnconfigure(0, minsize=self._px(190, 128))
        files.grid_columnconfigure(1, weight=1)
        files.grid_columnconfigure(2, minsize=self._px(146, 104))

        self._file_row(files, 0, "Файл ЭПИ", self.epi_path_var, self.choose_epi, "Выбрать", optional=True)
        self._diary_compact_row(files, 1)
