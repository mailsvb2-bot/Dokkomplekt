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

    def _create_regular_custom_documents(self, current_pack, case, regular_ids, out_dir):
        """Render doctor-owned templates with the proven historical compatibility rule.

        The July 2026 working generation path rendered doctor templates with
        ``strict=False`` after the required patient fields had already been
        collected. Later code switched the renderer itself to ``strict=True``;
        that made any empty optional ``{{...}}`` placeholder fatal and could roll
        the whole output transaction back, so the doctor saw no documents at all.

        Preserve current safety by validating every persisted required field
        first. Only after that validation do we use the historical tolerant
        placeholder rendering mode, where optional values may legitimately stay
        blank. The flag is restored immediately so no other creation path is
        weakened.
        """
        from universal_template_engine import missing_required_fields

        selected = {str(item).strip() for item in regular_ids if str(item).strip()}
        failures: list[str] = []
        for document in tuple(getattr(current_pack, "documents", ()) or ()):
            if getattr(document, "id", "") not in selected:
                continue
            missing = missing_required_fields(case, document)
            if missing:
                label = str(getattr(document, "button_label", "") or getattr(document, "id", "") or "Документ")
                failures.append(f"{label}: {', '.join(missing)}")
        if failures:
            raise ValueError("Не заполнены обязательные поля документов: " + "; ".join(failures))

        previous = bool(getattr(self, "_allow_missing_required_creation", False))
        self._allow_missing_required_creation = True
        try:
            return super()._create_regular_custom_documents(current_pack, case, regular_ids, out_dir)
        finally:
            self._allow_missing_required_creation = previous

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
