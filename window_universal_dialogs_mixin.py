from __future__ import annotations

from window_completion_dialog import prompt_regulatory_completion_values
from window_mapper_dialog import open_template_setup_center, open_universal_document_mapper


class WindowUniversalDialogsMixin:
    def _open_universal_document_mapper(self) -> None:
        return open_template_setup_center(self)

    def _open_first_run_create_buttons_popup(self) -> None:
        return open_template_setup_center(self, first_run=True)

    def _open_universal_document_mapper_advanced(self) -> None:
        return open_universal_document_mapper(self)

    def _prompt_regulatory_completion_values(self, inputs, *, parent) -> dict[str, str]:
        return prompt_regulatory_completion_values(self, inputs, parent=parent)
