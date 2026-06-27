from __future__ import annotations

from pathlib import Path
from typing import List

from universal_case_adapter import merge_case_values, merge_patient_cases, patient_data_to_case
from medical_primary_document_state import selected_primary_document_path
from medical_date_state import current_semantic_date


_SEMANTIC_DATE_CASE_FIELDS = {
    "admission_date": "admission.date",
    "discharge_date": "discharge.date",
    "commission_date": "commission.date",
    "vk_date": "vk_mse.date",
    "vk_protocol_date": "vk_mse.protocol_date",
    "sick_leave_vk_date": "sick_leave_vk.date",
    "sick_leave_vk_protocol_date": "sick_leave_vk.protocol_date",
    "sick_leave_vk_commission_date": "sick_leave_vk.commission_date",
    "expert_sick_leave_from": "expert.sick_leave_from",
    "labs_explicit_date": "labs.date",
}


class ActionsUniversalFlowMixin:
    """Creation flow for dynamic medpack documents selected in block 03."""

    def _current_universal_patient_case(self):
        primary_path = selected_primary_document_path(self)
        if primary_path is None:
            stale = str(getattr(self, "_last_missing_primary_document_path", "") or "")
            hint = f"\nПоследний путь: {stale}" if stale else ""
            raise ValueError("Первичный документ не найден. Загрузите первичный осмотр или направление на госпитализацию заново." + hint)
        navigation = str(primary_path)
        data = self._medical_override_data(navigation)
        case = patient_data_to_case(data, source_document=navigation)
        try:
            current_pack = self._load_or_create_universal_pack()
            from universal_scanner import scan_docx

            scan = scan_docx(navigation, registry=current_pack.registry(), rules=current_pack.extraction_rules)
            case = merge_patient_cases(case, scan.patient_case())
        except Exception as exc:
            from diagnostic_logging import record_soft_exception
            record_soft_exception("actions_universal_flow.current_patient_case_scan", exc, detail=navigation)
            self._log(f"\n⚠ Не удалось применить правила профиля к исходному документу: {exc}\n")
        confirmed_values = self._confirmed_universal_overlay_values()
        if confirmed_values:
            # The profile scanner is helpful, but it must never win over the
            # current UI/popup state.  Some regex matches intentionally carry
            # high confidence (for example a case number found in the source
            # DOCX), and without this final overlay a doctor-corrected value in
            # the UI could be overwritten only for custom medpack documents.
            case = merge_case_values(case, confirmed_values, source_document="doctor_confirmed_ui_state")
        return case

    def _confirmed_universal_overlay_values(self) -> dict[str, str]:
        """Return current UI/popup values that must outrank source scanning.

        Fixed-document generation already renders from ``_medical_override_data``.
        Dynamic doctor-owned templates additionally rescan the source document
        with profile rules; this helper reapplies the values visible in the UI
        afterwards so custom documents preserve the same doctor-approved state.
        """

        values: dict[str, str] = {}

        def var_text(name: str) -> str:
            try:
                var = getattr(self, name, None)
                return str(var.get() if var is not None and hasattr(var, "get") else "").strip()
            except Exception as exc:
                from diagnostic_logging import record_soft_exception
                record_soft_exception("actions_universal_flow.read_ui_var", exc, detail=name)
                return ""

        def add(field_id: str, value: object) -> None:
            text = str(value or "").strip()
            if text:
                values[field_id] = text

        add("patient.fio", var_text("patient_name_var"))
        try:
            from medical_text_utils import sanitize_case_number_candidate
            case_number = sanitize_case_number_candidate(var_text("case_number_var"), patient_name=var_text("patient_name_var"))
        except Exception as exc:
            from diagnostic_logging import record_soft_exception
            record_soft_exception("actions_universal_flow.sanitize_case_number", exc)
            case_number = var_text("case_number_var")
        add("case.number", case_number)
        add("diagnosis.main", str(getattr(self, "_popup_diagnosis_override", "") or "").strip() or var_text("diagnosis_var"))
        add("treatment.plan", var_text("assigned_treatment_var"))

        for semantic_key, field_id in _SEMANTIC_DATE_CASE_FIELDS.items():
            add(field_id, current_semantic_date(self, semantic_key))

        labs_without = False
        try:
            labs_without_var = getattr(self, "labs_without_var", None)
            labs_without = bool(labs_without_var.get()) if labs_without_var is not None and hasattr(labs_without_var, "get") else False
        except Exception as exc:
            from diagnostic_logging import record_soft_exception
            record_soft_exception("actions_universal_flow.read_labs_without", exc)
        if labs_without:
            add("labs.results", "Нет анализов")
        else:
            add("labs.results", var_text("labs_text_var"))
        add("labs.source", var_text("labs_source_path_var"))
        add("labs.date_policy", var_text("labs_date_policy_var"))

        yes_no = getattr(self, "_normalize_yes_no", None)
        def normalized_yes_no(value: str) -> str:
            try:
                return str(yes_no(value) if callable(yes_no) else value).strip()
            except Exception as exc:
                from diagnostic_logging import record_soft_exception
                record_soft_exception("actions_universal_flow.normalize_yes_no", exc)
                return value

        expert_work_status = normalized_yes_no(var_text("expert_work_status_var"))
        expert_org = var_text("expert_work_org_var")
        expert_position = var_text("expert_position_var")
        add("expert.work_status", expert_work_status)
        add("expert.work_org", expert_org)
        add("expert.position", expert_position)
        if expert_work_status == "да":
            add("patient.work", expert_org)
            add("patient.position", expert_position)
        elif expert_work_status == "нет":
            add("patient.work", "не работает")
        add("expert.sick_leave_needed", normalized_yes_no(var_text("expert_sick_leave_needed_var")))
        add("expert.sick_leave_number", var_text("expert_sick_leave_number_var"))

        add("rvk.act_number", var_text("rvk_act_number_var"))
        add("rvk.military_commissariat", var_text("rvk_military_commissariat_var"))
        add("rvk.work_position", var_text("rvk_work_position_var"))
        add("commission.number", var_text("commission_number_var"))
        add("vk_mse.protocol_number", var_text("vk_protocol_number_var"))
        vk_mse_work = var_text("vk_mse_work_org_var")
        vk_mse_position = var_text("vk_mse_position_var")
        add("vk_mse.work", vk_mse_work)
        add("vk_mse.position", vk_mse_position)
        add("vk_mse.work_position", ", ".join(part for part in (vk_mse_work, vk_mse_position) if part))
        add("sick_leave_vk.protocol_number", var_text("sick_leave_vk_protocol_number_var"))
        add("sick_leave_vk.work", var_text("sick_leave_vk_work_org_var"))
        add("sick_leave_vk.position", var_text("sick_leave_vk_position_var"))
        add("sick_leave_vk.work_position", var_text("sick_leave_vk_work_position_var"))
        return values

    def _missing_custom_completion_inputs(self, current_pack, case, selected_custom_ids: List[str]):
        missing: list[str] = []
        selected = {str(item).strip() for item in selected_custom_ids if str(item).strip()}
        for document in current_pack.documents:
            if selected and document.id not in selected:
                continue
            from universal_template_engine import missing_required_fields

            missing.extend(missing_required_fields(case, document))
        if not missing:
            return ()
        from regulatory_completion_blocks import completion_inputs_for_missing_fields

        return completion_inputs_for_missing_fields(
            tuple(dict.fromkeys(missing)),
            registry=current_pack.registry(),
            existing_case=case,
            reason_prefix="Не заполнено обязательное поле",
        )

    def _completion_inputs_are_required(self, inputs) -> bool:
        return any("обязатель" in str(getattr(item, "reason", "")).lower() for item in inputs or ())

    def _offer_custom_completion_values(self, current_pack, case, selected_custom_ids: List[str]):
        inputs = self._missing_custom_completion_inputs(current_pack, case, selected_custom_ids)
        if not inputs:
            return case
        required_mode = self._completion_inputs_are_required(inputs)
        try:
            raw_values = self._prompt_regulatory_completion_values(inputs, parent=self.root)
            from regulatory_completion_blocks import apply_completion_values, completion_values_from_raw

            values = completion_values_from_raw(inputs, raw_values)
            if values:
                return apply_completion_values(case, values, source_document="custom_document_completion_popup")
            if required_mode:
                labels = ", ".join(str(getattr(item, "label", item.field_id)) for item in inputs[:6])
                raise ValueError("Не заполнены обязательные поля custom-документа: " + labels)
            self._log("\nℹ Врач выбрал создание custom-документов как есть, без дополнительных полей.\n")
        except Exception as exc:
            if required_mode:
                raise
            self._log(f"\n⚠ Не удалось открыть popup дополнения custom-документа; создаю как есть: {exc}\n")
        return case

    def _create_custom_documents_impl(self, selected_custom_ids: List[str]) -> List[Path]:
        if not selected_custom_ids:
            return []
        current_pack = self._load_or_create_universal_pack()
        out_dir = self._result_output_dir()
        case = self._current_universal_patient_case()
        case = self._offer_custom_completion_values(current_pack, case, selected_custom_ids)
        diary_ids, regular_ids = self._split_custom_diary_document_ids(current_pack, selected_custom_ids)
        created_paths: list[Path] = []
        if regular_ids:
            created_paths.extend(self._create_regular_custom_documents(current_pack, case, regular_ids, out_dir))
        if diary_ids:
            created_paths.extend(self._create_custom_diary_documents_impl(current_pack, case, diary_ids, out_dir))
        self._set_status("Custom-документы профиля обработаны")
        return created_paths

    def _create_regular_custom_documents(self, current_pack, case, regular_ids: List[str], out_dir) -> List[Path]:
        from universal_generation import render_documents_from_pack, save_generation_report
        from medical_formatting import technical_report_path

        result = render_documents_from_pack(
            pack=current_pack,
            case=case,
            document_ids=regular_ids,
            output_dir=out_dir,
            base_dir=self._universal_profile_path().parent,
            strict=False,
            output_language=self._effective_output_language(),
            spellcheck_enabled=bool(getattr(self, "spellcheck_enabled_var", None) and self.spellcheck_enabled_var.get()),
        )
        report_path = save_generation_report(result, technical_report_path(out_dir, "custom_profile_generation_report.txt"))
        if result.skipped_documents:
            self._log("\n⚠ Custom-документы профиля пропущены:\n")
            for item in result.skipped_documents:
                self._log(f"- {item}\n")
        if result.warnings:
            self._log("\n⚠ Custom-документы профиля созданы с предупреждениями:\n")
            for warning in result.warnings:
                self._log(f"- {warning}\n")
        if result.created_files:
            self._log("\n✅ Созданы custom-документы профиля:\n")
            for path in result.created_files:
                self._log(f"- {path}\n")
        elif result.skipped_documents:
            raise ValueError("Custom-документы профиля не созданы: " + "; ".join(str(item) for item in result.skipped_documents[:5]))
        if self._diagnostic_reports_enabled():
            self._log(f"Технический отчёт custom-профиля: {report_path}\n")
        return [Path(item) for item in result.created_files]

    def _split_custom_diary_document_ids(self, current_pack, selected_custom_ids: List[str]) -> tuple[list[str], list[str]]:
        diary_ids: list[str] = []
        regular_ids: list[str] = []
        for document_id in selected_custom_ids:
            document = current_pack.document_by_id(document_id)
            if document is not None and getattr(document, "category", "") == "diaries":
                diary_ids.append(document_id)
            else:
                regular_ids.append(document_id)
        return diary_ids, regular_ids

    def _create_custom_diary_documents_impl(self, current_pack, case, diary_ids: List[str], out_dir) -> List[Path]:
        if not self.status_files:
            self._auto_select_diary_text_by_diagnosis(ask_folder=False)
        # Custom diary templates may contain the observation texts themselves.
        # The generation layer will use the template as a fallback status source
        # when no separate diary-text file is selected.
        patient_name = self.patient_name_var.get().strip() or case.get("patient.fio")
        admission_value = current_semantic_date(self, "admission_date") or case.get("admission.date")
        if not patient_name:
            raise ValueError("Введите ФИО пациента или выберите первичный документ с ФИО.")
        if not admission_value:
            raise ValueError("Не указана дата поступления для дневников.")
        discharge_value = current_semantic_date(self, "discharge_date") or case.get("discharge.date")
        if not discharge_value:
            raise ValueError("Не указана дата выписки для дневников. Она нужна, чтобы правильно закончить таблицу.")
        from universal_diary_generation import render_diary_documents_from_pack

        result = render_diary_documents_from_pack(
            pack=current_pack,
            case=case,
            document_ids=diary_ids,
            output_dir=out_dir,
            base_dir=self._universal_profile_path().parent,
            status_files=self.status_files,
            patient_name=patient_name,
            admission_value=admission_value,
            discharge_value=discharge_value,
            gender_source_name=case.get("patient.fio") or patient_name,
            frequency_mode=getattr(self, "diary_frequency_mode_var", None).get() if getattr(self, "diary_frequency_mode_var", None) else "daily",
            repeat_statuses=self.repeat_statuses_var.get(),
            reset_each_file=self.reset_each_file_var.get(),
            keep_signature=self.keep_signature_var.get(),
            fill_months=self.fill_months_var.get(),
            force_final_diary=self.force_final_diary_var.get(),
            remove_holiday_rows=self.remove_holiday_rows_var.get(),
            write_report=self._diagnostic_reports_enabled(),
        )
        if result.skipped:
            self._log("\n⚠ Custom-дневники профиля пропущены:\n")
            for item in result.skipped:
                self._log(f"- {item}\n")
        if result.created_files:
            self._log("\n✅ Созданы custom-дневники профиля:\n")
            for path in result.created_files:
                self._log(f"- {path}\n")
        elif result.skipped:
            raise ValueError("Custom-дневники не созданы: " + "; ".join(str(item) for item in result.skipped[:5]))
        return list(result.created_files)
