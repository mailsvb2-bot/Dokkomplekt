from __future__ import annotations

from pathlib import Path
from typing import List
from tkinter import messagebox

from diary_constants import DIARY_KIND
from medical_formatting import parse_date
from medical_text_utils import sanitize_case_number_candidate
from medical_parser_sanitize import sanitize_diagnosis
from icd10_f_search import normalize_diagnosis_with_icd10
from diagnostic_logging import record_soft_exception
from medical_primary_document_state import selected_primary_document_path
from medical_date_state import current_semantic_date, normalize_date_value


def _format_preview_lazy(data) -> str:
    from medical_preview import format_preview
    return format_preview(data)
from medical_models import PatientData


def _not_working_value(value: str) -> bool:
    normalized = " ".join(str(value or "").strip().lower().replace("ё", "е").split())
    return normalized in {"", "нет", "не работает", "безработный", "безработная", "неработающий", "неработающая"}


def _combined_vk_mse_work_position(app, work_org: str, position: str) -> str:
    if hasattr(app, "_vk_mse_work_position_value"):
        value = app._vk_mse_work_position_value()
    elif hasattr(app, "vk_mse_work_position_var"):
        value = app.vk_mse_work_position_var.get().strip()
    else:
        value = str(getattr(app, "_vk_mse_work_position_value_cache", "") or "").strip()
    return value or ", ".join(part for part in [work_org, position] if part)


class ActionsMedicalFlowMixin:
    def _confirmed_admission_date_override(self) -> str:
        """Return a doctor-confirmed admission date that may outrank rescanning."""
        try:
            state = getattr(self, "_semantic_date_state", {})
            if isinstance(state, dict):
                stored = normalize_date_value(state.get("admission_date", ""))
                if stored:
                    return stored
        except Exception as exc:
            record_soft_exception("actions_medical_flow.confirmed_admission_state", exc)
        try:
            if bool(getattr(self, "_manual_admission_date", False)):
                value = normalize_date_value(current_semantic_date(self, "admission_date"))
                if value:
                    return value
        except Exception as exc:
            record_soft_exception("actions_medical_flow.confirmed_admission_ui", exc)
        return ""

    def _medical_override_data(self, navigation: str) -> PatientData:
        """Implement the _medical_override_data workflow with validation, UI state updates and diagnostics."""
        data = self._parse_primary_document(navigation)
        selected_source_type = self.primary_document_type_var.get()
        if selected_source_type == "hospitalization_referral":
            data.input_document_kind = "направление на госпитализацию"
            if self.assigned_treatment_var.get().strip():
                data.treatment_plan = self.assigned_treatment_var.get().strip()
        elif selected_source_type == "primary_exam":
            data.input_document_kind = "первичный осмотр"
            if self.assigned_treatment_var.get().strip():
                data.treatment_plan = self.assigned_treatment_var.get().strip()
            case_value = sanitize_case_number_candidate(self.case_number_var.get(), patient_name=self.patient_name_var.get().strip() or data.fio)
            if case_value:
                data.case_number = case_value
        case_value = sanitize_case_number_candidate(self.case_number_var.get(), patient_name=self.patient_name_var.get().strip() or data.fio)
        if case_value:
            data.case_number = case_value
        elif self.case_number_var.get().strip():
            self.case_number_var.set("")
        manual_patient_name = self.patient_name_var.get().strip()
        if not data.fio and manual_patient_name:
            data.fio = manual_patient_name
        data.output_fio = manual_patient_name or data.fio
        confirmed_admission = self._confirmed_admission_date_override()
        if confirmed_admission:
            data.admission_date = confirmed_admission
        else:
            from medical_admission_resolver import extract_admission_date_from_primary_docx
            safe_admission_date = extract_admission_date_from_primary_docx(navigation)
            if safe_admission_date:
                data.admission_date = safe_admission_date
            else:
                value = current_semantic_date(self, "admission_date")
                if value:
                    data.admission_date = value
        def _semantic_date(key: str) -> str:
            return current_semantic_date(self, key)

        shared_discharge = current_semantic_date(self, "discharge_date")
        if shared_discharge:
            data.discharge_date = shared_discharge
        popup_diag = self._popup_diagnosis_override.strip()
        ui_diag = self.diagnosis_var.get().strip()
        if popup_diag:
            data.diagnosis = sanitize_diagnosis(popup_diag)
        elif ui_diag:
            data.diagnosis = sanitize_diagnosis(ui_diag)
        if data.diagnosis:
            try:
                normalized_diagnosis = normalize_diagnosis_with_icd10(
                    data.diagnosis,
                    language_id=self._diagnosis_language() if hasattr(self, "_diagnosis_language") else "ru",
                )
                if normalized_diagnosis:
                    data.diagnosis = normalized_diagnosis
                    self._set_ui_var(self.diagnosis_var, normalized_diagnosis)
            except Exception as exc:
                record_soft_exception("actions_medical_flow.normalize_diagnosis", exc, detail=str(data.diagnosis)[:200])
                data.diagnosis = sanitize_diagnosis(data.diagnosis)
        if self.epi_path_var.get().strip():
            data.epi_text = self.service.load_epi_text(self.epi_path_var.get().strip())
        else:
            data.epi_text = ""
        try:
            data.additional_info_text = self.additional_info_text_var.get().strip()
            data.additional_info_source = self.additional_info_source_path_var.get().strip()
        except Exception as exc:
            record_soft_exception("actions_medical_flow.additional_info", exc)
            data.additional_info_text = ""
            data.additional_info_source = ""

        try:
            from medical_renderer_labs import labs_block_from_values

            default_labs_date = data.discharge_date or data.admission_date
            labs_block = labs_block_from_values(
                text=self.labs_text_var.get(),
                source=self.labs_source_path_var.get(),
                date_policy=self.labs_date_policy_var.get(),
                default_date=default_labs_date,
                explicit_date=current_semantic_date(self, "labs_explicit_date"),
                without_labs=bool(self.labs_without_var.get()),
            )
            data.labs_text = labs_block.text
            data.labs_source = labs_block.source
            data.labs_date_policy = labs_block.date_policy
            data.labs_without = labs_block.without_labs
        except Exception as exc:
            record_soft_exception("actions_medical_flow.labs_override", exc, detail=str(navigation))
            data.labs_text = ""
            data.labs_source = ""
            data.labs_date_policy = "preserve_found_dates"
            data.labs_without = False

        shared_org, shared_position = self._shared_work_defaults()
        data.expert_work_status = self._normalize_yes_no(self.expert_work_status_var.get())
        data.expert_work_org = self.expert_work_org_var.get().strip() or shared_org
        data.expert_position = self.expert_position_var.get().strip() or shared_position
        if not data.expert_work_status and (data.expert_work_org or data.expert_position):
            data.expert_work_status = "да"
        data.expert_sick_leave_needed = self._normalize_yes_no(self.expert_sick_leave_needed_var.get())
        data.expert_sick_leave_from = _semantic_date("expert_sick_leave_from")
        data.expert_sick_leave_number = self.expert_sick_leave_number_var.get().strip()
        if data.expert_work_status == "да":
            data.work_org = data.expert_work_org
            data.position = data.expert_position
        elif data.expert_work_status == "нет":
            data.work_org = "не работает"
            data.position = ""
        if data.expert_sick_leave_needed == "да":
            data.sick_leave = f"нужен с {data.expert_sick_leave_from}" if data.expert_sick_leave_from else "нужен"
        elif data.expert_sick_leave_needed == "нет":
            data.sick_leave = "не нужен"

        data.rvk_act_number = self.rvk_act_number_var.get().strip()
        data.rvk_military_commissariat = self.rvk_military_commissariat_var.get().strip()
        data.rvk_work_position = self.rvk_work_position_var.get().strip()
        data.vk_date = _semantic_date("vk_date")
        data.vk_protocol_number = self.vk_protocol_number_var.get().strip()
        data.vk_protocol_date = _semantic_date("vk_protocol_date")
        data.vk_mse_work_org = self.vk_mse_work_org_var.get().strip() or shared_org
        data.vk_mse_position = self.vk_mse_position_var.get().strip() or shared_position
        data.vk_mse_work_position = _combined_vk_mse_work_position(self, data.vk_mse_work_org, data.vk_mse_position)
        data.sick_leave_vk_date = _semantic_date("sick_leave_vk_date")
        data.sick_leave_vk_protocol_number = self.sick_leave_vk_protocol_number_var.get().strip()
        data.sick_leave_vk_protocol_date = _semantic_date("sick_leave_vk_protocol_date")
        data.sick_leave_vk_commission_date = _semantic_date("sick_leave_vk_commission_date")
        data.sick_leave_vk_work_org = self.sick_leave_vk_work_org_var.get().strip() or shared_org
        data.sick_leave_vk_position = self.sick_leave_vk_position_var.get().strip() or shared_position
        data.sick_leave_vk_work_position = self.sick_leave_vk_work_position_var.get().strip() or ", ".join(
            part for part in [data.sick_leave_vk_work_org, data.sick_leave_vk_position] if part
        )
        data.commission_date = _semantic_date("commission_date")
        data.commission_number = self.commission_number_var.get().strip()
        return data

    def _create_medical_documents_impl(self, selected_docs: List[str]) -> List[Path]:
        primary_path = selected_primary_document_path(self)
        if primary_path is None:
            stale = str(getattr(self, "_last_missing_primary_document_path", "") or "")
            hint = f"\nПоследний путь: {stale}" if stale else ""
            raise ValueError("Первичный документ не найден. Загрузите первичный осмотр или направление на госпитализацию заново." + hint)
        navigation = str(primary_path)
        discharge = current_semantic_date(self, "discharge_date")
        if discharge and not parse_date(discharge):
            raise ValueError("Дата выписки должна быть в формате ДД.ММ.ГГГГ, ДД.ММ.ГГ, ДДММГГГГ, ДДММГГ или коротко ДМГГ.")
        if discharge:
            discharge = self._normalize_date_for_ui(discharge)
            if not self._date_is_not_before_admission(discharge):
                raise ValueError("Дата выписки не может быть раньше даты госпитализации.")
            if hasattr(self, "_store_discharge_date_value"):
                self._store_discharge_date_value(discharge, source_label="создание медицинских документов")
            else:
                self._set_ui_var(self.discharge_date_var, discharge)
        out_dir = str(self._result_output_dir())
        data = self._medical_override_data(navigation)
        if "vk_mse" in selected_docs and not _not_working_value(data.vk_mse_work_org) and not (data.vk_mse_position or data.vk_mse_work_position):
            raise ValueError("Для ВК на МСЭ укажите должность или общее поле места работы/должности.")
        missing = data.missing_critical_fields()
        allow_missing_required = bool(getattr(self, "_allow_missing_required_creation", False))
        if missing and not allow_missing_required:
            msg = "Не найдены критические поля: " + ", ".join(missing)
            if self.strict_mode_var.get():
                raise ValueError(msg + ". Проверьте, что выбран заполненный файл пациента, а не пустой шаблон.")
            if not messagebox.askyesno("Есть пропуски", msg + "\n\nПродолжить медицинские документы всё равно?"):
                raise RuntimeError("Создание медицинских документов отменено пользователем.")
        created, used_data = self.service.create_documents(
            navigation_path=navigation,
            output_dir=out_dir,
            discharge_date=discharge,
            epi_path=self.epi_path_var.get().strip() or None,
            selected_docs=selected_docs,
            override_data=data,
            allow_missing_required=allow_missing_required,
        )
        self._set_preview(_format_preview_lazy(used_data))
        self._log("\n✅ Созданы медицинские документы:\n")
        for path in created:
            self._log(f"- {path}\n")
        return list(created)

    def create_medical_documents(self) -> None:
        selected = self.selected_medical_docs()
        if not selected:
            messagebox.showwarning("Нет документов", "Отметьте хотя бы один медицинский документ.")
            return
        self.output_vars[DIARY_KIND].set(False)
        self.create_selected_outputs()
