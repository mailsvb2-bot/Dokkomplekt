from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app_config import (
    ACCENT,
    ACCENT_2,
    BG,
    BG_2,
    BORDER,
    DEEP,
    FIELD,
    FIELD_BORDER,
    MUTED,
    PANEL,
    PANEL_2,
    PANEL_3,
    TEXT,
)
from diagnostic_logging import record_soft_exception
from i18n_strings import tr
from medical_language_catalog import language_choices, language_id_from_choice, language_profile

class WindowStyleMixin:
    def _setup_style(self) -> None:
        """Implement the _setup_style workflow with validation, UI state updates and diagnostics."""
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError as exc:
            record_soft_exception("window_mixin:52", exc)

        default_font = self._font(10)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT, font=default_font)
        style.configure("Card.TLabel", background=PANEL, foreground=TEXT, font=self._font(11))
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=self._font(10))
        style.configure("Header.TLabel", background=DEEP, foreground=TEXT, font=self._font(23, "bold"))
        style.configure("Subheader.TLabel", background=DEEP, foreground=MUTED, font=self._font(12))
        style.configure("Accent.TButton", font=self._font(11, "bold"), foreground="#03101f", background=ACCENT)
        style.map("Accent.TButton", background=[("active", "#7ee3ff")])
        style.configure("Green.TButton", font=self._font(12, "bold"), foreground="#03101f", background=ACCENT_2)
        style.map("Green.TButton", background=[("active", "#8fffd5")])
        style.configure("Dark.TButton", font=self._font(10), foreground=TEXT, background=PANEL_3, borderwidth=0)
        style.map("Dark.TButton", background=[("active", BORDER)], foreground=[("active", TEXT)])
        style.configure("TCheckbutton", background=PANEL_2, foreground=TEXT, font=self._font(11))
        style.map("TCheckbutton", background=[("active", PANEL_2)], foreground=[("active", TEXT)])
        style.configure("TRadiobutton", background=FIELD, foreground=TEXT, font=self._font(11))
        style.map("TRadiobutton", background=[("active", FIELD)], foreground=[("active", TEXT)])

        # Combobox: тёмный стиль под референс, fieldbackground = FIELD
        for combo_style in ("TCombobox", "Printer.TCombobox"):
            style.configure(
                combo_style,
                fieldbackground=FIELD,
                background=FIELD,
                foreground=TEXT,
                arrowcolor=ACCENT,
                bordercolor=FIELD_BORDER,
                lightcolor=FIELD,
                darkcolor=FIELD,
                padding=6,
            )
            style.map(
                combo_style,
                fieldbackground=[("readonly", FIELD), ("!disabled", FIELD)],
                background=[("readonly", FIELD), ("active", PANEL_3), ("!disabled", FIELD)],
                foreground=[("readonly", TEXT), ("!disabled", TEXT)],
                selectbackground=[("readonly", FIELD), ("!disabled", FIELD)],
                selectforeground=[("readonly", TEXT), ("!disabled", TEXT)],
                arrowcolor=[("readonly", ACCENT), ("!disabled", ACCENT)],
            )
        self.root.option_add("*TCombobox*Listbox.background", FIELD)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", PANEL_3)
        self.root.option_add("*TCombobox*Listbox.selectForeground", TEXT)
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=BG_2,
            background=ACCENT_2,
            bordercolor=BG_2,
            lightcolor=ACCENT_2,
            darkcolor=ACCENT_2,
        )
