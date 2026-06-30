from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

from medical_constants import DIR_EPI, DIR_PRIMARY_DOCUMENTS
from medical_primary_document_state import clean_primary_document_path, clear_selected_primary_document_path, sync_selected_primary_document_path
from medical_word_format import SUPPORTED_WORD_SUFFIXES, supported_word_filetypes


class LegacyWordFileMixin:
    def choose_navigation(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите первичный документ",
            initialdir=self._dialog_initial_dir(DIR_PRIMARY_DOCUMENTS),
            filetypes=supported_word_filetypes(),
        )
        if path:
            self._apply_primary_document_path(path, prompt_for_referral=True)

    def choose_epi(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите файл ЭПИ",
            initialdir=self._dialog_initial_dir(DIR_EPI),
            filetypes=[*supported_word_filetypes(), ("Text", "*.txt")],
        )
        if path:
            self.epi_path_var.set(path)
            self._remember_dialog_directory(DIR_EPI, path)
            self.reparse_navigation(silent=True)

    def _apply_primary_document_path(self, path: str, *, prompt_for_referral: bool) -> None:
        path = clean_primary_document_path(path)
        candidate = Path(path).expanduser() if path else None
        if not candidate or not candidate.exists() or not candidate.is_file() or candidate.suffix.lower() not in SUPPORTED_WORD_SUFFIXES:
            clear_selected_primary_document_path(self)
            if path:
                messagebox.showwarning("Word file required", "Choose DOC, DOCX or DOCM.")
            return
        try:
            from files_mixin import PRIMARY_DOCUMENT_SUFFIXES
            PRIMARY_DOCUMENT_SUFFIXES.update(SUPPORTED_WORD_SUFFIXES)
        except Exception:
            pass
        path = sync_selected_primary_document_path(self, candidate)
        super()._apply_primary_document_path(path, prompt_for_referral=prompt_for_referral)
