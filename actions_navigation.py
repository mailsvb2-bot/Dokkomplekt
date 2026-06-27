from __future__ import annotations

from pathlib import Path
from tkinter import messagebox


from medical_text_utils import sanitize_case_number_candidate
from medical_parser_sanitize import sanitize_diagnosis
from icd10_f_search import normalize_diagnosis_with_icd10
from medical_primary_document_state import selected_primary_document_path, clear_selected_primary_document_path
from medical_date_state import current_semantic_date


def _format_preview_lazy(data) -> str:
    from medical_preview import format_preview
    return format_preview(data)


class ActionsNavigationMixin:
    def reparse_navigation(self, *, silent: bool = False) -> None:
        """Implement the reparse_navigation workflow with validation, UI state updates and diagnostics."""
        primary_path = selected_primary_document_path(self)
        if primary_path is None:
            clear_selected_primary_document_path(self)
            if not silent:
                stale = str(getattr(self, "_last_missing_primary_document_path", "") or "")
                extra = f"\n\nПоследний путь: {stale}" if stale else ""
                messagebox.showwarning("Нет файла", "Первичный документ не найден. Выберите DOCX/DOCM заново." + extra)
            return
        path = str(primary_path)
        try:
            data = self._parse_primary_document(path)
            if self.primary_document_type_var.get() == "hospitalization_referral":
                data.input_document_kind = "направление на госпитализацию"
                if self.assigned_treatment_var.get().strip():
                    data.treatment_plan = self.assigned_treatment_var.get().strip()
            elif self.primary_document_type_var.get() == "primary_exam":
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
            if self.epi_path_var.get().strip() and Path(self.epi_path_var.get().strip()).exists():
                data.epi_text = self.service.load_epi_text(self.epi_path_var.get().strip())
            data.discharge_date = current_semantic_date(self, "discharge_date")
            popup_diag = self._popup_diagnosis_override.strip() or self.diagnosis_var.get().strip()
            if popup_diag and (self._popup_diagnosis_override.strip() or self._manual_diagnosis):
                data.diagnosis = normalize_diagnosis_with_icd10(popup_diag, language_id=self._diagnosis_language() if hasattr(self, "_diagnosis_language") else "ru")
            # Дата поступления берётся только из заголовка документа. Если
            # общий парсер где-то нашёл дату рождения, заголовочная дата
            # имеет приоритет.
            from medical_admission_resolver import extract_admission_date_from_primary_docx
            title_date = extract_admission_date_from_primary_docx(path)
            # Заголовочная дата имеет приоритет, но если её нет, сохраняем
            # строгий fallback из полного разбора первичного документа. Главное —
            # не подменять дату поступления датой рождения из демографического блока.
            if title_date:
                data.admission_date = title_date
            self.data = data
            self._apply_primary_work_defaults(data)
            # ФИО из первичного документа подтягивается в UI только как имя файлов.
            # Ручная правка этого UI-поля НЕ подменяет ФИО внутри документов.
            if data.fio and (not self._manual_patient_name or not self.patient_name_var.get().strip()):
                self._set_ui_var(self.patient_name_var, data.fio)
            if data.admission_date and (not self._manual_admission_date or not current_semantic_date(self, "admission_date")):
                self._set_ui_var(self.admission_date_var, data.admission_date)
            if data.case_number and not self.case_number_var.get().strip():
                case_value = sanitize_case_number_candidate(data.case_number, patient_name=self.patient_name_var.get().strip() or data.fio)
                if case_value:
                    self.case_number_var.set(case_value)
                    data.case_number = case_value
                else:
                    data.case_number = ""
            if data.diagnosis and (not self._manual_diagnosis or not self.diagnosis_var.get().strip()):
                self._set_ui_var(self.diagnosis_var, normalize_diagnosis_with_icd10(data.diagnosis, language_id=self._diagnosis_language() if hasattr(self, "_diagnosis_language") else "ru"))
            # Если папки уже известны, автоматически подставляем:
            # 1) текст дневников по названию диагноза;
            # 2) конкретный 01–31 DOCX-шаблон по дате госпитализации.
            self._auto_select_diary_text_by_diagnosis(ask_folder=False)
            self._auto_select_numbered_diary_template(ask_folder=False)
            self._set_preview(_format_preview_lazy(data))
            self._log(f"\n✅ Первичный документ прочитан ({data.input_document_kind or 'тип не определён'}). Данные подтянуты в общую карточку пациента.\n")
        except Exception as exc:
            self._show_error("Не удалось прочитать первичный документ", exc)
