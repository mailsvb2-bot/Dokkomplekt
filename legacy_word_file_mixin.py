from __future__ import annotations

from pathlib import Path
from tkinter import messagebox

from medical_primary_document_state import clean_primary_document_path, clear_selected_primary_document_path, sync_selected_primary_document_path
from medical_word_format import SUPPORTED_WORD_SUFFIXES


class LegacyWordFileMixin:
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
