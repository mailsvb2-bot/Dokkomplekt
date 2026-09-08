from __future__ import annotations

from pathlib import Path

from actions_creation_orchestrator import ActionsCreationOrchestratorMixin
from actions_diary_flow import ActionsDiaryFlowMixin
from actions_document_intelligence_flow import ActionsDocumentIntelligenceFlowMixin
from actions_medical_flow import ActionsMedicalFlowMixin
from actions_universal_flow import ActionsUniversalFlowMixin
from actions_navigation import ActionsNavigationMixin
from actions_template_checks import ActionsTemplateChecksMixin
from medical_date_state import current_semantic_date


class ActionsFolderNamingPreflightMixin:
    """Let required-field correction run before final strict folder naming."""

    _folder_naming_preflight_confirmed = False
    _folder_naming_review_tolerant = False

    def create_selected_outputs(self, *, print_after: bool = False) -> bool:
        previous = bool(getattr(self, "_folder_naming_preflight_confirmed", False))
        self._folder_naming_preflight_confirmed = False
        try:
            return bool(super().create_selected_outputs(print_after=print_after))
        finally:
            self._folder_naming_preflight_confirmed = previous

    def _confirm_patient_case_before_creation(self, review) -> bool:
        confirmed = bool(super()._confirm_patient_case_before_creation(review))
        if confirmed:
            self._folder_naming_preflight_confirmed = True
        return confirmed

    def _build_patient_case_review_for_selection(
        self,
        selected_medical: list[str],
        selected_diaries: bool,
        selected_custom: list[str] | None = None,
    ):
        previous = bool(getattr(self, "_folder_naming_review_tolerant", False))
        self._folder_naming_review_tolerant = not bool(
            getattr(self, "_folder_naming_preflight_confirmed", False)
        )
        try:
            return super()._build_patient_case_review_for_selection(
                selected_medical, selected_diaries, selected_custom
            )
        finally:
            self._folder_naming_review_tolerant = previous

    def _patient_output_dir_for_data(self, data, *, base_dir: Path | None = None) -> Path:
        if not bool(getattr(self, "_folder_naming_review_tolerant", False)):
            return super()._patient_output_dir_for_data(data, base_dir=base_dir)

        from desktop_patient_folder import build_patient_folder_name

        root = Path(base_dir or self._base_output_dir()).expanduser()
        if getattr(self, "_output_dir_auto_locked_to_patient", False):
            return root
        name = build_patient_folder_name(
            fio=getattr(data, "output_fio", "") or getattr(data, "fio", ""),
            admission_date=getattr(data, "admission_date", ""),
            discharge_date=getattr(data, "discharge_date", "")
            or current_semantic_date(self, "discharge_date"),
            settings=self._folder_naming_settings(),
            fallback=getattr(data, "output_fio", "") or getattr(data, "fio", "") or "Пациент",
            strict=False,
        )
        return root / (name or "Пациент")


class ActionsCreationMixin(
    ActionsFolderNamingPreflightMixin,
    ActionsCreationOrchestratorMixin,
    ActionsTemplateChecksMixin,
    ActionsNavigationMixin,
    ActionsMedicalFlowMixin,
    ActionsDocumentIntelligenceFlowMixin,
    ActionsUniversalFlowMixin,
    ActionsDiaryFlowMixin,
):
    pass
