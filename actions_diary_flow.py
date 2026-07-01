from __future__ import annotations

from diary_constants import DIARY_KIND
from diagnostic_logging import record_soft_exception
from medical_constants import DOCUMENT_ORDER
from medical_date_state import current_semantic_date
from medical_primary_document_state import selected_primary_document_path


class ActionsDiaryFlowMixin:
    def _create_diaries_impl(self):
        """Create the doctor-selected diary output for the current patient case.

        The production diary contract is ``Тексты + Даты``.  Doctor-owned text
        files provide the diary wording and doctor-owned date/table templates
        provide the document shape and date principle.  Plain text diary output is
        kept only as a fallback when no date/table template is available.
        """
        primary_path = selected_primary_document_path(self)
        title_admission_value = self._sync_admission_date_from_title(force=False)
        diary_admission_value = current_semantic_date(self, "admission_date") or title_admission_value
        if not self.status_files:
            self._auto_select_diary_text_by_diagnosis(ask_folder=False)
        if not self.status_files:
            self.choose_status_files()
        if not self.status_files:
            raise ValueError("Выберите файл(ы) с текстами дневников. Тексты можно выбирать из DOCX/DOCM/DOC.")
        self._auto_select_numbered_diary_template(ask_folder=False)
        text_output = not bool(getattr(self, "diary_files", None))
        self._diary_text_output_enabled = bool(text_output)
        try:
            from diary_creation_wizard import confirm_diary_creation
            if not confirm_diary_creation(self):
                raise ValueError("Создание дневников остановлено мастером дневников: проверьте дату госпитализации, тексты и шаблон дат дневников.")
        except ValueError:
            raise
        except Exception as exc:
            record_soft_exception("actions_diary_flow.diary_wizard", exc)

        diary_patient_name = self.patient_name_var.get().strip()
        source_patient_fio = ""
        parsed_for_name = None
        if primary_path is not None:
            try:
                parsed_for_name = self._parse_primary_document(str(primary_path))
                source_patient_fio = parsed_for_name.fio.strip()
                if not diary_patient_name and source_patient_fio:
                    diary_patient_name = source_patient_fio
                    self._set_ui_var(self.patient_name_var, diary_patient_name)
            except Exception as exc:
                record_soft_exception("actions_diary_flow.parse_source_patient_fio", exc)
                source_patient_fio = ""
        if not diary_patient_name:
            raise ValueError("Введите ФИО для названия файлов или выберите первичный документ с ФИО пациента.")
        if not diary_admission_value:
            diary_admission_value = current_semantic_date(self, "admission_date")
        if not diary_admission_value:
            raise ValueError("Не удалось найти дату поступления в первичном документе или popup/UI.")

        from diary_batch import fill_diary_batch
        diary_schedule = self._selected_profile_diary_schedule()
        sick_leave_yes = self._normalize_yes_no(getattr(self, "expert_sick_leave_needed_var", None).get() if getattr(self, "expert_sick_leave_needed_var", None) else "") == "да"
        treatment_correction = str(getattr(getattr(self, "diary_treatment_correction_var", None), "get", lambda: "")() or "").strip()
        result = fill_diary_batch(
            status_files=self.status_files,
            diary_files=self.diary_files,
            output_dir=str(self._result_output_dir()),
            patient_name=diary_patient_name,
            admission_value=diary_admission_value,
            gender_source_name=source_patient_fio or diary_patient_name,
            discharge_value=current_semantic_date(self, "discharge_date"),
            repeat_statuses=self.repeat_statuses_var.get(),
            reset_each_file=self.reset_each_file_var.get(),
            keep_signature=self.keep_signature_var.get(),
            fill_months=self.fill_months_var.get(),
            force_final_diary=self.force_final_diary_var.get(),
            remove_holiday_rows=self.remove_holiday_rows_var.get(),
            open_result_folder=False,
            write_report=self._diagnostic_reports_enabled(),
            diary_day_offsets=diary_schedule.day_offsets if diary_schedule else (),
            diary_hour_offsets=diary_schedule.hour_offsets if diary_schedule and getattr(self, "diary_frequency_mode_var", None) and self.diary_frequency_mode_var.get() == "hourly" else (),
            diary_frequency_mode=getattr(self, "diary_frequency_mode_var", None).get() if getattr(self, "diary_frequency_mode_var", None) else "daily",
            text_output=text_output,
            sick_leave_dynamic_epicrisis=sick_leave_yes,
            treatment_correction=treatment_correction,
            birth_date=str(getattr(parsed_for_name, "birth", "") or getattr(getattr(self, "data", None), "birth", "") or ""),
            complaints=str(getattr(parsed_for_name, "complaints", "") or getattr(getattr(self, "data", None), "complaints", "") or ""),
            treatment=str(getattr(parsed_for_name, "treatment_plan", "") or getattr(getattr(self, "data", None), "treatment_plan", "") or getattr(getattr(self, "assigned_treatment_var", None), "get", lambda: "")() or ""),
            profile_status=str(getattr(parsed_for_name, "mental_status", "") or getattr(getattr(self, "data", None), "mental_status", "") or ""),
            sick_leave_from=current_semantic_date(self, "expert_sick_leave_from"),
        )
        self._log("\n✅ Дневники заполнены:\n")
        for path in result.created_files:
            self._log(f"- {path}\n")
        if result.report_path is not None:
            self._log(f"Отчёт: {result.report_path}\n")
        else:
            self._log("Отчёт дневников не создавался: диагностические отчёты выключены.\n")
        self._log(f"Итого: файлов {result.processed_files}, дневников {result.filled_rows}, динамических записей {result.final_rows_filled}.\n")
        return result

    def _selected_profile_diary_schedule(self):
        try:
            from diary_schedule import DiaryScheduleSpec
            pack = self._load_or_create_universal_pack()
            frequency = getattr(self, "diary_frequency_mode_var", None).get() if getattr(self, "diary_frequency_mode_var", None) else "daily"
            for document in pack.documents:
                if getattr(document, "category", "") != "diaries":
                    continue
                spec = DiaryScheduleSpec.from_dict(getattr(document, "diary_schedule", None))
                if frequency == "hourly" and spec.has_hourly:
                    return spec.with_mode("hourly")
                if frequency == "daily" and spec.has_daily:
                    return spec.with_mode("daily")
        except Exception as exc:
            record_soft_exception("actions_diary_flow:selected_profile_diary_schedule", exc)
            return None
        return None

    def create_diaries(self) -> None:
        self.output_vars[DIARY_KIND].set(True)
        for kind in DOCUMENT_ORDER:
            self.output_vars[kind].set(False)
        self.create_selected_outputs()
