from __future__ import annotations

from diagnostic_logging import record_soft_exception
from pathlib import Path
from typing import List

from diary_constants import DIARY_KIND, DIARY_LABEL
from medical_constants import DOCUMENT_LABELS, DOCUMENT_ORDER
from medical_primary_document_state import selected_primary_document_path


class ActionsSelectionMixin:
    def selected_medical_docs(self) -> List[str]:
        return [kind for kind in DOCUMENT_ORDER if self.output_vars[kind].get()]

    def diaries_selected(self) -> bool:
        return bool(self.output_vars[DIARY_KIND].get())

    def selected_custom_docs(self) -> List[str]:
        from universal_main_documents import selected_custom_document_ids
        return list(selected_custom_document_ids(self.output_vars))

    def _custom_output_name_by_id(self, document_id: str) -> str:
        try:
            from universal_main_documents import custom_documents_for_main_ui
            pack = self._load_or_create_universal_pack()
            for doc in custom_documents_for_main_ui(pack, base_dir=self._universal_profile_path().parent):
                if doc.document_id == document_id:
                    return doc.label
        except Exception as exc:
            record_soft_exception("actions_selection:28", exc)
        return document_id

    def _selected_output_names(self, selected_medical: List[str], selected_diaries: bool, selected_custom: List[str] | None = None) -> List[str]:
        names = [DOCUMENT_LABELS.get(kind, kind) for kind in selected_medical]
        if selected_diaries:
            names.append(DIARY_LABEL)
        for document_id in selected_custom or []:
            names.append(self._custom_output_name_by_id(document_id))
        return names

    def _update_selected_outputs_status(self) -> None:
        names = self._selected_output_names(self.selected_medical_docs(), self.diaries_selected(), self.selected_custom_docs())
        if names:
            self._set_status("Выбрано: " + ", ".join(names))
        else:
            self._set_status("Документы для создания не выбраны")
        self._redraw_selection_controls()

    def _base_output_dir(self) -> Path:
        explicit = self.output_dir_var.get().strip()
        primary_path = selected_primary_document_path(self)
        navigation = str(primary_path) if primary_path is not None else ""
        if primary_path is not None and not self._manual_output_dir:
            return primary_path.parent
        if explicit:
            return Path(explicit)
        if navigation:
            return Path(navigation).parent
        if self.diary_files:
            return Path(self.diary_files[0]).parent
        return Path.cwd()

    def _result_output_dir(self) -> Path:
        override = getattr(self, "_active_patient_output_dir", None)
        if override:
            return Path(override)
        return self._base_output_dir()
