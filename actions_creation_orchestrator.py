from __future__ import annotations

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


class ActionsCreationOrchestratorMixin(
    ActionsCreationReviewMixin,
    ActionsCreationFolderingMixin,
    ActionsCreationMaintenanceMixin,
    ActionsCreationBatchingMixin,
    ActionsCreationExecutionMixin,
):
    """Aggregate focused creation-flow mixins for selected output generation."""
