from __future__ import annotations

from tkinter import messagebox

from diagnostic_logging import record_soft_exception
from error_taxonomy import ErrorCategory, record_classified_error


class ActionsCreationLiveGuardMixin:
    """Doctor-facing safety boundary for the main create buttons.

    Production runs without a console. An exception escaping a Tk callback
    otherwise looks exactly like a dead «Создать и сохранить» button. This
    mixin also removes the redundant second confirmation modal: the click on
    the main action is already explicit consent to create; only truly missing
    required fields may block generation. The full review remains available
    through the dedicated «Проверка» action in block 04.
    """

    def _confirm_patient_case_before_creation(self, review) -> bool:
        """Block only on truly missing required fields, then generate."""
        return bool(self._prompt_missing_required_fields_or_continue(review))

    def create_selected_outputs(self, *, print_after: bool = False) -> bool:
        """Run the complete create action and never fail invisibly in the EXE."""
        try:
            self._set_status("Проверяю данные перед созданием…")
        except Exception as exc:
            record_soft_exception("actions_creation_live_guard.set_start_status", exc)
        try:
            result = bool(super().create_selected_outputs(print_after=print_after))
        except Exception as exc:
            record_classified_error("create_selected_outputs_button", exc, category=ErrorCategory.DOCX_RENDER)
            try:
                self._set_status("Создание не выполнено: показана ошибка")
            except Exception as status_exc:
                record_soft_exception("actions_creation_live_guard.set_failure_status", status_exc)
            messagebox.showerror(
                "Документы не созданы",
                "Создание остановилось с ошибкой. Никакие частичные документы не считаются готовыми.\n\n"
                f"{exc}\n\n"
                "Подробности записаны в диагностику программы.",
            )
            return False
        if result:
            try:
                final_dir = getattr(self, "_active_patient_output_dir", None)
                suffix = f" — {final_dir}" if final_dir else ""
                self._set_status(f"Готово: файлы сохранены{suffix}")
            except Exception as exc:
                record_soft_exception("actions_creation_live_guard.set_success_status", exc)
        return result
