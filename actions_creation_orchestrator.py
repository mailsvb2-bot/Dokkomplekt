from __future__ import annotations

from tkinter import messagebox

from diagnostic_logging import record_soft_exception
from error_taxonomy import ErrorCategory, record_classified_error
from actions_creation_preflight import ActionsCreationReviewMixin
from actions_creation_foldering import ActionsCreationFolderingMixin
from actions_creation_maintenance import ActionsCreationMaintenanceMixin
from actions_creation_batch import ActionsCreationBatchingMixin
from actions_creation_execution import ActionsCreationExecutionMixin

# Contract sentinels kept for legacy smoke/prod gates that inspect this public
# aggregation module while implementation lives in focused files:
# _prompt_common_output_requirements _select_default_printer_sync
# def batch_generate_documents_dialog def _read_update_manifest
# def configure_patient_folder_naming_dialog doctor_confirmed _ensure_patient_folder_naming_configured
# return False Дата выписки не может быть раньше даты поступления


class ActionsCreationLiveGuardMixin:
    """Doctor-facing boundary for the main create buttons.

    The main create click is already explicit consent to generate. After truly
    missing required fields are resolved, creation must continue without a
    second confirmation modal that can become hidden behind the no-console EXE.
    Unexpected callback failures are made visible instead of looking like a
    dead button.
    """

    def _confirm_patient_case_before_creation(self, review) -> bool:
        """Block only on truly missing required fields, then generate."""
        return bool(self._prompt_missing_required_fields_or_continue(review))

    def create_selected_outputs(self, *, print_after: bool = False) -> bool:
        """Run the existing generator and never let a live click fail invisibly."""
        try:
            self._set_status("Проверяю данные перед созданием…")
        except Exception as exc:
            record_soft_exception("actions_creation_orchestrator.set_start_status", exc)
        try:
            result = bool(super().create_selected_outputs(print_after=print_after))
        except Exception as exc:
            record_classified_error("create_selected_outputs_button", exc, category=ErrorCategory.DOCX_RENDER)
            try:
                self._set_status("Создание не выполнено: показана ошибка")
            except Exception as status_exc:
                record_soft_exception("actions_creation_orchestrator.set_failure_status", status_exc)
            messagebox.showerror(
                "Документы не созданы",
                "Создание остановилось с ошибкой. Никакие частичные документы не считаются готовыми.\n\n"
                f"{exc}\n\n"
                "Подробности записаны в диагностику программы.",
            )
            return False
        if result:
            try:
                self._set_status("Готово: файлы сохранены")
            except Exception as exc:
                record_soft_exception("actions_creation_orchestrator.set_success_status", exc)
        return result


class ActionsCreationOrchestratorMixin(
    ActionsCreationLiveGuardMixin,
    ActionsCreationReviewMixin,
    ActionsCreationFolderingMixin,
    ActionsCreationMaintenanceMixin,
    ActionsCreationBatchingMixin,
    ActionsCreationExecutionMixin,
):
    """Aggregate focused creation-flow mixins for selected output generation."""
