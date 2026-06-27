from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app_config import (
    ACCENT,
    ACCENT_2,
    BG_2,
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

class WindowHeaderMixin:
    def _status_shield_icon(self, parent) -> tk.Canvas:
        c = tk.Canvas(parent, width=23, height=23, bg=DEEP, highlightthickness=0, bd=0)
        c.create_polygon(11, 2, 19, 5, 18, 14, 11, 21, 4, 14, 3, 5, fill="", outline=ACCENT, width=1.2)
        c.create_line(7, 11, 10, 14, 16, 7, fill=ACCENT, width=1.4, capstyle="round", joinstyle="round")
        return c

    def _build_header(self, parent: tk.Frame) -> None:
        """Шапка без зачёркнутых элементов: убраны логотип слева и service-icons справа."""
        header = tk.Frame(parent, bg=DEEP, padx=self._px(7, 4), pady=self._px(4, 2))
        header.grid(row=0, column=0, sticky="ew", pady=(0, self._px(10 if self._compact_ui else 13, 6)))
        header.grid_columnconfigure(0, weight=1)
        self._bind_window_drag(header)

        title_box = tk.Frame(header, bg=DEEP)
        title_box.grid(row=0, column=0, sticky="ew", pady=(self._px(2, 0), 0), padx=(self._px(8, 4), 0))
        self._bind_window_drag(title_box)

        title = tk.Label(
            title_box,
            text=self._ui_text("app.title"),
            bg=DEEP,
            fg=TEXT,
            font=self._font(21 if self._compact_ui else 23, "bold"),
        )
        title.grid(row=0, column=0, sticky="w")

        subtitle = tk.Label(
            title_box,
            text=self._ui_text("app.subtitle"),
            bg=DEEP,
            fg=MUTED,
            font=self._font(11 if self._compact_ui else 12),
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(self._px(2, 0), 0))
        self._bind_window_drag(title)
        self._bind_window_drag(subtitle)

        # Оставляем только системные кнопки окна. Зачёркнутые иконки настроек/справки убраны.
        controls = tk.Frame(header, bg=DEEP)
        controls.grid(row=0, column=1, sticky="ne", pady=(0, self._px(18 if self._compact_ui else 22, 7)))
        self._language_settings_button(controls).grid(row=0, column=0, padx=(0, self._px(8, 4)))
        self._profile_mapper_button(controls).grid(row=0, column=1, padx=(0, self._px(8, 4)))
        self._window_control_button(controls, "−", self._minimize_window).grid(row=0, column=2)
        self._window_control_button(controls, "□", self._toggle_maximize).grid(row=0, column=3)
        self._window_control_button(controls, "×", self.root.destroy, danger=True).grid(row=0, column=4)

    def _profile_mapper_button(self, parent) -> tk.Button:
        """Small entrypoint to the new universal document mapper.

        The current production workflow stays untouched.  This button opens a
        safe setup/prototype surface where a doctor can inspect what the program
        understood in an arbitrary DOCX and save manual field rules into a
        profile file for future universal packs. It can also import/export portable medpacks and render a first custom DOCX output from the currently scanned case.
        """
        return tk.Button(
            parent,
            text=self._ui_text("button.profiles"),
            command=self._open_universal_document_mapper,
            bg=FIELD,
            fg=ACCENT,
            activebackground=PANEL_3,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=self._px(12, 8),
            pady=self._px(3, 2),
            font=self._font(9, "bold"),
            cursor="hand2",
        )

    def _ui_text(self, key: str) -> str:
        try:
            language = self.ui_language_var.get()
        except Exception as exc:
            record_soft_exception("window_header.ui_language", exc)
            language = "ru"
        return tr(key, language)

    def _language_settings_button(self, parent) -> tk.Button:
        return tk.Button(
            parent,
            text=self._ui_text("button.language"),
            command=self._open_language_settings,
            bg=FIELD,
            fg=ACCENT,
            activebackground=PANEL_3,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=self._px(12, 8),
            pady=self._px(3, 2),
            font=self._font(9, "bold"),
            cursor="hand2",
        )

    def _open_language_settings(self) -> None:
        """Implement the _open_language_settings workflow with validation, UI state updates and diagnostics."""
        popup = tk.Toplevel(self.root)
        popup.title(self._ui_text("language.dialog.title"))
        popup.configure(bg=DEEP)
        popup.geometry("520x360")
        popup.grid_columnconfigure(0, weight=1)
        popup.grid_rowconfigure(0, weight=1)
        body = tk.Frame(popup, bg=PANEL, padx=self._px(14, 10), pady=self._px(14, 10))
        body.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        body.grid_columnconfigure(1, weight=1)
        choices = language_choices()

        def label_for(lang_id: str) -> str:
            return language_profile(lang_id).choice_label()

        ui_choice = tk.StringVar(value=label_for(self.ui_language_var.get()))
        doc_choice = tk.StringVar(value=label_for(self.document_language_var.get()))
        output_current = self.output_language_var.get()
        output_choice = tk.StringVar(value="same_as_source" if output_current == "same_as_source" else label_for(output_current))

        rows = [
            (self._ui_text("language.ui"), ui_choice, choices),
            (self._ui_text("language.document"), doc_choice, choices),
            (self._ui_text("language.output"), output_choice, ("same_as_source", *choices)),
        ]
        for row, (caption, var, values) in enumerate(rows):
            tk.Label(body, text=caption, bg=PANEL, fg=TEXT, font=self._font(10, "bold")).grid(row=row, column=0, sticky="w", pady=(0, 8), padx=(0, 10))
            ttk.Combobox(body, textvariable=var, values=values, state="readonly", font=self._font(10)).grid(row=row, column=1, sticky="ew", pady=(0, 8))
        spell = tk.Checkbutton(
            body,
            text=self._ui_text("language.spellcheck"),
            variable=self.spellcheck_enabled_var,
            bg=PANEL,
            fg=TEXT,
            activebackground=PANEL,
            activeforeground=TEXT,
            selectcolor=FIELD,
            font=self._font(10),
        )
        spell.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 12))
        note = tk.Label(
            body,
            text="Орфография применяется безопасно: коды МКБ, даты, номера, подписи и {{placeholders}} не изменяются.",
            bg=PANEL,
            fg=MUTED,
            wraplength=self._px(470, 320),
            justify="left",
            font=self._font(9),
        )
        note.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        buttons = tk.Frame(body, bg=PANEL)
        buttons.grid(row=5, column=0, columnspan=2, sticky="ew")
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)

        def save_language() -> None:
            ui_lang = language_id_from_choice(ui_choice.get())
            doc_lang = language_id_from_choice(doc_choice.get())
            out_raw = output_choice.get()
            out_lang = "same_as_source" if out_raw == "same_as_source" else language_id_from_choice(out_raw)
            self.ui_language_var.set(ui_lang)
            self.document_language_var.set(doc_lang)
            self.output_language_var.set(out_lang)
            self._settings["language"] = {
                "ui_language": ui_lang,
                "document_language": doc_lang,
                "output_language": out_lang,
                "spellcheck_enabled": bool(self.spellcheck_enabled_var.get()),
            }
            self._save_settings()
            self.root.title(self._ui_text("app.title"))
            self._set_status(self._ui_text("language.saved"))
            popup.destroy()

        tk.Button(buttons, text=self._ui_text("button.save"), command=save_language, bg=ACCENT_2, fg="#03101f", relief="flat", font=self._font(9, "bold"), padx=10, pady=8).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        tk.Button(buttons, text=self._ui_text("button.cancel"), command=popup.destroy, bg=FIELD, fg=TEXT, relief="flat", font=self._font(9, "bold"), padx=10, pady=8).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        popup.transient(self.root)
        popup.grab_set()
        popup.focus_set()

    def _effective_output_language(self) -> str:
        out = self.output_language_var.get().strip() if hasattr(self, "output_language_var") else "same_as_source"
        if out and out != "same_as_source":
            return out
        doc_lang = self.document_language_var.get().strip() if hasattr(self, "document_language_var") else "auto"
        if doc_lang and doc_lang != "auto":
            return doc_lang
        # Fall back to the last scanned document language when the mapper has it.
        detected = getattr(self, "_last_detected_document_language", "auto")
        return detected or "auto"

    def _universal_profile_path(self):
        from pathlib import Path
        try:
            configured = str(self._settings.get("active_universal_profile", "") or "").strip()
        except Exception as exc:
            record_soft_exception("window_header.profile_setting", exc)
            configured = ""
        if configured:
            return Path(configured).expanduser()
        try:
            base = self._settings_path.parent
        except Exception as exc:
            record_soft_exception("window_header.profile_base", exc)
            base = Path.home() / "MedicalDiaryAutofill"
        return base / "profiles" / "default_custom.medpack.json"

    def _set_universal_profile_path(self, path) -> None:
        from pathlib import Path
        candidate = Path(path).expanduser()
        candidate.parent.mkdir(parents=True, exist_ok=True)
        self._settings["active_universal_profile"] = str(candidate)
        self._save_settings()
        try:
            self._refresh_custom_profile_tiles()
        except Exception as exc:
            record_soft_exception("window_header_mixin.refresh_custom_profile_tiles", exc)

    def _load_or_create_universal_pack(self):
        from universal_profiles import ensure_default_pack
        return ensure_default_pack(self._universal_profile_path())

    def _header_icon_button(self, parent, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=DEEP,
            fg=MUTED,
            activebackground=BG_2,
            activeforeground=ACCENT,
            relief="flat",
            bd=0,
            width=2,
            height=1,
            font=("Segoe UI", 14, "bold"),
            cursor="hand2",
        )

    def _build_patient_card(self, parent: tk.Frame) -> None:
        section, body = self._section(parent, "01", "patient", "Источник\nданных")
        section.grid(row=1, column=0, sticky="ew", pady=(0, 3))

        body.grid_rowconfigure(0, weight=0)
        body.grid_rowconfigure(1, weight=1)
        body.grid_columnconfigure(0, weight=1)

        top = tk.Frame(body, bg=PANEL)
        top.grid(row=0, column=0, sticky="ew", pady=(0, self._px(10, 5)))
        top.grid_columnconfigure(0, weight=1)
        self._source_drop_row(top, 0)

        card = tk.Frame(body, bg=PANEL)
        card.grid(row=1, column=0, sticky="new", pady=(0, self._px(2, 1)))
        card.grid_columnconfigure(0, weight=5)
        card.grid_columnconfigure(1, weight=3)
        card.grid_columnconfigure(2, weight=3)
        card.grid_columnconfigure(3, weight=4)
        card.grid_columnconfigure(4, weight=4)
        card.grid_columnconfigure(5, weight=3)
        card.grid_columnconfigure(6, weight=3)
        card.grid_columnconfigure(7, weight=3)
        card.grid_columnconfigure(8, weight=3)
        card.grid_columnconfigure(9, weight=3)
        card.grid_columnconfigure(10, weight=3)
        card.grid_columnconfigure(11, weight=3)

        self._field(card, "ФИО или название файла", self.patient_name_var, row=0, col=0, colspan=5)
        self._field(card, "Дата поступления", self.admission_date_var, row=0, col=5, colspan=3)
        self._field(card, "Дата выписки", self.discharge_date_var, row=0, col=8, colspan=4)
        self._diagnosis_field(card, row=1, col=0, colspan=8)
        self._sick_leave_need_field(card, row=1, col=8, colspan=4)
