from __future__ import annotations

import os
from tkinter import messagebox

from app_config import ACCENT_2, DEEP, FIELD, PANEL, PANEL_3, TEXT
from diagnostic_logging import record_soft_exception
from icd10_f_search import normalize_diagnosis_with_icd10, normalize_required_diagnosis_with_icd10
from medical_formatting import parse_date
from medical_date_state import current_semantic_date
from medical_models import build_patient_case_review, augment_patient_case_review_with_custom_flags
from medical_primary_document_state import selected_primary_document_path


REQUIRED_REVIEW_TEXT_TARGETS = {
    "patient_work": ("expert_work_org_var", "work_org"),
    "patient_position": ("expert_position_var", "position"),
    "expert_work_status": ("expert_work_status_var", "expert_work_status"),
    "expert_work_org": ("expert_work_org_var", "expert_work_org"),
    "expert_position": ("expert_position_var", "expert_position"),
    "expert_sick_leave_needed": ("expert_sick_leave_needed_var", "expert_sick_leave_needed"),
    "expert_sick_leave_number": ("expert_sick_leave_number_var", "expert_sick_leave_number"),
    "commission_number": ("commission_number_var", "commission_number"),
    "rvk_act_number": ("rvk_act_number_var", "rvk_act_number"),
    "rvk_military_commissariat": ("rvk_military_commissariat_var", "rvk_military_commissariat"),
    "rvk_work_position": ("rvk_work_position_var", "rvk_work_position"),
    "vk_protocol_number": ("vk_protocol_number_var", "vk_protocol_number"),
    "vk_mse_work_org": ("vk_mse_work_org_var", "vk_mse_work_org"),
    "vk_mse_position": ("vk_mse_position_var", "vk_mse_position"),
    "sick_leave_vk_protocol_number": ("sick_leave_vk_protocol_number_var", "sick_leave_vk_protocol_number"),
    "sick_leave_vk_work_org": ("sick_leave_vk_work_org_var", "sick_leave_vk_work_org"),
    "sick_leave_vk_position": ("sick_leave_vk_position_var", "sick_leave_vk_position"),
    "sick_leave_vk_work_position": ("sick_leave_vk_work_position_var", "sick_leave_vk_work_position"),
}

REQUIRED_REVIEW_DATE_KEYS = {
    "admission_date",
    "discharge_date",
    "labs_explicit_date",
    "commission_date",
    "vk_date",
    "vk_protocol_date",
    "sick_leave_vk_date",
    "sick_leave_vk_protocol_date",
    "sick_leave_vk_commission_date",
    "expert_sick_leave_from",
}

class ActionsCreationReviewMixin:
    def _build_patient_case_review_for_selection(
        self,
        selected_medical: list[str],
        selected_diaries: bool,
        selected_custom: list[str] | None = None,
    ):
        """Create one checked patient card from the same data that renderers use."""
        primary_path = selected_primary_document_path(self)
        navigation = str(primary_path) if primary_path is not None else ""
        data = None
        if navigation:
            try:
                data = self._medical_override_data(navigation)
            except Exception as exc:
                record_soft_exception("actions_creation_orchestrator.build_patient_case_review", exc, detail=navigation)
        if data is None:
            data = getattr(self, "data", None)
        if data is None:
            from medical_models import PatientData
            data = PatientData()
        output_dir = self._patient_output_dir_for_data(data, base_dir=self._base_output_dir())
        selected_custom_labels = [self._custom_output_name_by_id(doc_id) for doc_id in (selected_custom or [])]
        review = build_patient_case_review(
            data,
            selected_medical=selected_medical,
            selected_diaries=selected_diaries,
            selected_custom=selected_custom_labels,
            output_dir=str(output_dir),
            primary_path=navigation,
            manual_patient_name=bool(getattr(self, "_manual_patient_name", False)),
            manual_admission_date=bool(getattr(self, "_manual_admission_date", False)),
            manual_discharge_date=bool(getattr(self, "_manual_discharge_date", False)),
            manual_diagnosis=bool(getattr(self, "_manual_diagnosis", False)),
            manual_case_number=bool(self.case_number_var.get().strip()),
            manual_treatment=bool(self.assigned_treatment_var.get().strip()),
        )
        if selected_custom:
            custom_flags = self._custom_requirement_flags(selected_custom)
            self._active_custom_requirement_flags = custom_flags
            data_for_custom = getattr(self, "data", None)
            review = augment_patient_case_review_with_custom_flags(
                review,
                custom_flags,
                case_number=(self._case_number_popup_default() if hasattr(self, "_case_number_popup_default") else self.case_number_var.get().strip()),
                diagnosis=(self.diagnosis_var.get().strip() or str(getattr(data_for_custom, "diagnosis", "") or "").strip()),
                treatment=(self.assigned_treatment_var.get().strip() or str(getattr(data_for_custom, "treatment_plan", "") or "").strip()),
                discharge_date=current_semantic_date(self, "discharge_date"),
                labs=(self.labs_text_var.get().strip() if hasattr(self, "labs_text_var") else ""),
                labs_without=bool(self.labs_without_var.get()) if hasattr(self, "labs_without_var") else False,
                manual_case_number=bool(self.case_number_var.get().strip()),
                manual_diagnosis=bool(getattr(self, "_manual_diagnosis", False)),
                manual_treatment=bool(self.assigned_treatment_var.get().strip()),
                manual_discharge_date=bool(getattr(self, "_manual_discharge_date", False)),
            )
        self._last_patient_case_review = review
        return review
    def _show_found_data_dialog(self, review=None, *, title: str = "Что найдено в первичном документе") -> None:
        """Implement the _show_found_data_dialog workflow with validation, UI state updates and diagnostics."""
        review = review or self._build_patient_case_review_for_selection(
            self.selected_medical_docs(),
            self.diaries_selected(),
            self.selected_custom_docs(),
        )
        if os.environ.get("CI"):
            self._log("\n" + review.as_text() + "\n")
            return
        try:
            import tkinter as tk
            from tkinter import ttk
            from app_config import PANEL, FIELD, TEXT, MUTED, SUCCESS, WARN, ERROR, ACCENT_2, DEEP
            win = tk.Toplevel(self.root)
            win.title(title)
            win.configure(bg=DEEP)
            win.geometry("760x560")
            win.grid_columnconfigure(0, weight=1)
            win.grid_rowconfigure(1, weight=1)
            tk.Label(
                win,
                text=title,
                bg=DEEP,
                fg=TEXT,
                font=self._font(13, "bold"),
                padx=14,
                pady=10,
                anchor="w",
            ).grid(row=0, column=0, sticky="ew")
            frame = tk.Frame(win, bg=PANEL, padx=10, pady=10)
            frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(0, weight=1)
            text = tk.Text(frame, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word", font=self._font(10), padx=10, pady=10)
            text.grid(row=0, column=0, sticky="nsew")
            scroll = ttk.Scrollbar(frame, command=text.yview)
            scroll.grid(row=0, column=1, sticky="ns")
            text.configure(yscrollcommand=scroll.set)
            for line in review.as_text().splitlines():
                text.insert("end", line + "\n")
            text.configure(state="disabled")
            buttons = tk.Frame(win, bg=DEEP)
            buttons.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
            buttons.grid_columnconfigure(0, weight=1)
            tk.Button(buttons, text="Закрыть", command=win.destroy, bg=ACCENT_2, fg="#03101f", relief="flat", padx=18, pady=8, font=self._font(10, "bold")).grid(row=0, column=0, sticky="e")
            win.transient(self.root)
            win.grab_set()
            self.root.wait_window(win)
        except Exception as exc:
            record_soft_exception("actions_creation_orchestrator.show_found_data_dialog", exc)
            messagebox.showinfo(title, review.as_text())
    def show_found_patient_data(self) -> None:
        self._show_found_data_dialog(title="Что программа нашла")
    def _clear_required_review_value(self, key: str) -> None:
        """Clear a patient/preflight field when the doctor intentionally erases it."""
        data = getattr(self, "data", None)
        if key in {"fio", "output_fio"}:
            self._set_ui_var(self.patient_name_var, "")
            self._manual_patient_name = False
            if data is not None:
                data.output_fio = ""
                data.fio = ""
        elif key == "case_number":
            self.case_number_var.set("")
            if data is not None:
                data.case_number = ""
        elif key == "admission_date":
            self._set_ui_var(self.admission_date_var, "")
            self._manual_admission_date = False
            if data is not None:
                data.admission_date = ""
        elif key == "discharge_date":
            if hasattr(self, "_clear_semantic_date_value"):
                self._clear_semantic_date_value("discharge_date")
            else:
                self._popup_discharge_date_override = ""
                self._set_ui_var(self.discharge_date_var, "")
                self._manual_discharge_date = False
                if data is not None:
                    data.discharge_date = ""
        elif key == "diagnosis":
            self._set_ui_var(self.diagnosis_var, "")
            self._popup_diagnosis_override = ""
            self._manual_diagnosis = False
            if data is not None:
                data.diagnosis = ""
        elif key == "treatment":
            self._set_ui_var(self.assigned_treatment_var, "")
            if data is not None:
                data.treatment_plan = ""
        elif key in {"labs", "labs.results"}:
            try:
                self.labs_text_var.set("")
                self.labs_source_path_var.set("")
                self.labs_without_var.set(False)
                if hasattr(self, "labs_explicit_date_var"):
                    self.labs_explicit_date_var.set("")
                if hasattr(self, "labs_date_policy_var"):
                    self.labs_date_policy_var.set("preserve_found_dates")
            except Exception as exc:
                record_soft_exception("actions_creation_preflight.clear_labs", exc)
        elif key in REQUIRED_REVIEW_DATE_KEYS:
            try:
                if hasattr(self, "_clear_semantic_date_value"):
                    self._clear_semantic_date_value(key)
                var_name = {
                    "labs_explicit_date": "labs_explicit_date_var",
                    "commission_date": "commission_date_var",
                    "vk_date": "vk_date_var",
                    "vk_protocol_date": "vk_protocol_date_var",
                    "sick_leave_vk_date": "sick_leave_vk_date_var",
                    "sick_leave_vk_protocol_date": "sick_leave_vk_protocol_date_var",
                    "sick_leave_vk_commission_date": "sick_leave_vk_commission_date_var",
                    "expert_sick_leave_from": "expert_sick_leave_from_var",
                }.get(key, "")
                if var_name and hasattr(self, var_name):
                    getattr(self, var_name).set("")
            except Exception as exc:
                record_soft_exception("actions_creation_preflight.clear_semantic_date", exc, detail=key)
        elif key in REQUIRED_REVIEW_TEXT_TARGETS:
            try:
                var_name, data_attr = REQUIRED_REVIEW_TEXT_TARGETS[key]
                if hasattr(self, var_name):
                    getattr(self, var_name).set("")
                if data is not None and data_attr:
                    setattr(data, data_attr, "")
                if key.startswith("expert_sick_leave") and hasattr(self, "_update_expert_sick_leave_display"):
                    self._update_expert_sick_leave_display()
            except Exception as exc:
                record_soft_exception("actions_creation_preflight.clear_text_target", exc, detail=key)

    def _store_required_review_value(self, key: str, value: str) -> None:
        """Persist corrected preflight values into canonical UI and data state."""
        value = str(value or "").strip()
        if not value:
            self._clear_required_review_value(key)
            return
        data = getattr(self, "data", None)
        if key in {"fio", "output_fio"}:
            self._set_ui_var(self.patient_name_var, value)
            self._manual_patient_name = True
            if data is not None:
                data.output_fio = value
                if not getattr(data, "fio", ""):
                    data.fio = value
        elif key == "case_number":
            self._store_case_number_value(value)
        elif key == "admission_date":
            normalized = self._normalize_date_for_ui(value) or value
            self._set_ui_var(self.admission_date_var, normalized)
            self._manual_admission_date = True
            if data is not None:
                data.admission_date = normalized
        elif key == "discharge_date":
            self._store_discharge_date_value(value)
        elif key == "diagnosis":
            try:
                value = normalize_diagnosis_with_icd10(self._normalize_popup_diagnosis_value(value), language_id=self._diagnosis_language() if hasattr(self, "_diagnosis_language") else "ru")
            except Exception as exc:
                record_soft_exception("actions_creation_orchestrator.normalize_required_diagnosis", exc)
            self._set_ui_var(self.diagnosis_var, value)
            self._popup_diagnosis_override = value
            self._manual_diagnosis = True
            if data is not None:
                data.diagnosis = value
        elif key == "treatment":
            self._set_ui_var(self.assigned_treatment_var, value)
            if data is not None:
                data.treatment_plan = value
        elif key in {"labs", "labs.results"}:
            try:
                normalized_labs = " ".join(value.replace("ё", "е").lower().split())
                if normalized_labs in {"нет анализов", "анализов нет", "без анализов", "не требуется", "не требуются"}:
                    self.labs_text_var.set("")
                    self.labs_source_path_var.set("")
                    self.labs_without_var.set(True)
                    if hasattr(self, "labs_date_policy_var"):
                        self.labs_date_policy_var.set("without_labs")
                    return
                self.labs_text_var.set(value)
                self.labs_source_path_var.set("preflight")
                self.labs_without_var.set(False)
                if hasattr(self, "labs_date_policy_var") and self.labs_date_policy_var.get() == "without_labs":
                    self.labs_date_policy_var.set("preserve_found_dates")
            except Exception as exc:
                record_soft_exception("actions_creation_preflight.store_labs", exc)
        elif key in REQUIRED_REVIEW_DATE_KEYS:
            try:
                if hasattr(self, "_store_popup_date_value"):
                    self._store_popup_date_value(key, value, source_label="popup обязательных полей")
                else:
                    var_name = {
                        "labs_explicit_date": "labs_explicit_date_var",
                        "commission_date": "commission_date_var",
                        "vk_date": "vk_date_var",
                        "vk_protocol_date": "vk_protocol_date_var",
                        "sick_leave_vk_date": "sick_leave_vk_date_var",
                        "sick_leave_vk_protocol_date": "sick_leave_vk_protocol_date_var",
                        "sick_leave_vk_commission_date": "sick_leave_vk_commission_date_var",
                        "expert_sick_leave_from": "expert_sick_leave_from_var",
                    }.get(key, "")
                    if var_name and hasattr(self, var_name):
                        getattr(self, var_name).set(value)
                if data is not None:
                    data_attr = {
                        "commission_date": "commission_date",
                        "vk_date": "vk_date",
                        "vk_protocol_date": "vk_protocol_date",
                        "sick_leave_vk_date": "sick_leave_vk_date",
                        "sick_leave_vk_protocol_date": "sick_leave_vk_protocol_date",
                        "sick_leave_vk_commission_date": "sick_leave_vk_commission_date",
                        "expert_sick_leave_from": "expert_sick_leave_from",
                    }.get(key, "")
                    if data_attr:
                        setattr(data, data_attr, value)
            except Exception as exc:
                record_soft_exception("actions_creation_preflight.store_semantic_date", exc, detail=key)
        elif key in REQUIRED_REVIEW_TEXT_TARGETS:
            try:
                var_name, data_attr = REQUIRED_REVIEW_TEXT_TARGETS[key]
                if key in {"expert_work_status", "expert_sick_leave_needed"} and hasattr(self, "_normalize_yes_no"):
                    value = self._normalize_yes_no(value) or value
                if hasattr(self, var_name):
                    getattr(self, var_name).set(value)
                if data is not None and data_attr:
                    setattr(data, data_attr, value)
                if key in {"patient_work", "expert_work_org"} and data is not None:
                    data.work_org = value
                if key in {"patient_position", "expert_position"} and data is not None:
                    data.position = value
                if key.startswith("expert_sick_leave") and hasattr(self, "_update_expert_sick_leave_display"):
                    self._update_expert_sick_leave_display()
            except Exception as exc:
                record_soft_exception("actions_creation_preflight.store_text_target", exc, detail=key)

    def _prompt_missing_required_fields_or_continue(self, review) -> bool:
        # close_required_popup contract is implemented inside actions_required_fields_popup._RequiredFieldsDialog._close.
        from actions_required_fields_popup import prompt_missing_required_fields_or_continue

        return prompt_missing_required_fields_or_continue(self, review)

    def _edit_patient_case_inside_preflight(self, parent) -> bool:
        """Let the doctor correct key patient fields without closing preflight."""
        try:
            import tkinter as tk
            from app_config import PANEL, FIELD, TEXT, ACCENT_2, PANEL_3
            from dialog_fields_popup import DialogDiagnosisPopup
            win = tk.Toplevel(parent)
            win.title("Исправить данные пациента")
            win.configure(bg=PANEL)
            win.geometry("760x560")
            win.minsize(680, 460)
            win.grid_columnconfigure(0, weight=1)
            win.grid_rowconfigure(0, weight=1)
            diagnosis_popup = DialogDiagnosisPopup(win, self.root, language_id=self._diagnosis_language() if hasattr(self, "_diagnosis_language") else "ru")
            form = tk.Frame(win, bg=PANEL, padx=12, pady=12)
            form.grid(row=0, column=0, sticky="nsew")
            form.grid_columnconfigure(1, weight=1)
            fields = [
                ("fio", "ФИО пациента", self.patient_name_var),
                ("case_number", "Номер истории болезни", self.case_number_var),
                ("admission_date", "Дата поступления", self.admission_date_var),
                ("discharge_date", "Дата выписки", self.discharge_date_var),
                ("diagnosis", "Диагноз с МКБ-10", self.diagnosis_var),
                ("treatment", "Лечение", self.assigned_treatment_var),
            ]
            variables: dict[str, tk.StringVar] = {}
            entries: dict[str, tk.Entry] = {}
            for row, (key, label, source_var) in enumerate(fields):
                tk.Label(form, text=label, bg=PANEL, fg=TEXT, font=self._font(9, "bold"), anchor="w").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
                value = ""
                try:
                    value = source_var.get().strip()
                except Exception as exc:
                    record_soft_exception("actions_creation_preflight.edit_read_var", exc, detail=key)
                var = tk.StringVar(value=value)
                variables[key] = var
                entry = tk.Entry(form, textvariable=var, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat", font=self._font(10))
                entry.grid(row=row, column=1, sticky="ew", ipady=5, pady=(0, 8))
                entries[key] = entry
                if key == "diagnosis":
                    diagnosis_popup.attach(entry, var)
            result = {"saved": False}

            def close_editor() -> None:
                try:
                    win.grab_release()
                except Exception as exc:
                    record_soft_exception("actions_creation_preflight.edit_grab_release", exc)
                try:
                    diagnosis_popup.hide()
                except Exception as exc:
                    record_soft_exception("actions_creation_preflight.edit_diagnosis_hide", exc)
                try:
                    win.withdraw()
                except Exception as exc:
                    record_soft_exception("actions_creation_preflight.edit_withdraw", exc)
                win.destroy()

            buttons = tk.Frame(win, bg=PANEL)
            buttons.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
            buttons.grid_columnconfigure(0, weight=1)
            buttons.grid_columnconfigure(1, weight=1)

            def _focus_editor_field(field_key: str) -> None:
                try:
                    entry = entries.get(field_key)
                    if entry is not None:
                        entry.focus_set()
                        entry.selection_range(0, "end")
                except Exception as exc:
                    record_soft_exception("actions_creation_preflight.edit_focus", exc, detail=field_key)

            def save() -> None:
                normalized_values: dict[str, str] = {}
                for key, var in variables.items():
                    raw = var.get().strip()
                    if key in {"admission_date", "discharge_date"} and raw:
                        parsed = parse_date(raw)
                        if not parsed:
                            messagebox.showwarning("Некорректная дата", "Введите дату в формате ДД.ММ.ГГГГ.", parent=win)
                            _focus_editor_field(key)
                            return
                        raw = parsed.strftime("%d.%m.%Y")
                        var.set(raw)
                    if key == "diagnosis" and raw:
                        try:
                            normalized = normalize_required_diagnosis_with_icd10(raw, language_id=self._diagnosis_language() if hasattr(self, "_diagnosis_language") else "ru")
                        except Exception as exc:
                            record_soft_exception("actions_creation_preflight.edit_normalize_diagnosis", exc)
                            normalized = ""
                        if not normalized:
                            messagebox.showwarning("Некорректный диагноз", "Выберите диагноз из МКБ-10 или укажите шифр с буквой класса, например K35 или I10.", parent=win)
                            _focus_editor_field(key)
                            return
                        raw = normalized
                        var.set(raw)
                    if key == "case_number" and raw:
                        from medical_text_utils import sanitize_case_number_candidate
                        patient_name = variables.get("fio").get().strip() if variables.get("fio") is not None else ""
                        sanitized = sanitize_case_number_candidate(raw, patient_name=patient_name)
                        if not sanitized:
                            messagebox.showwarning("Некорректный номер", "Проверьте поле: Номер истории болезни", parent=win)
                            _focus_editor_field(key)
                            return
                        raw = sanitized
                        var.set(raw)
                    normalized_values[key] = raw
                admission = parse_date(normalized_values.get("admission_date", ""))
                discharge = parse_date(normalized_values.get("discharge_date", ""))
                if admission and discharge and discharge.date() < admission.date():
                    messagebox.showwarning("Некорректная дата", "Дата выписки не может быть раньше даты поступления.", parent=win)
                    _focus_editor_field("discharge_date")
                    return
                for key, raw in normalized_values.items():
                    if key == "discharge_date" and raw and hasattr(self, "_store_discharge_date_value"):
                        if not self._store_discharge_date_value(raw, parent=win, source_label="редактор данных пациента"):
                            _focus_editor_field("discharge_date")
                            return
                        continue
                    self._store_required_review_value(key, raw)
                result["saved"] = True
                close_editor()

            def cancel() -> None:
                close_editor()

            tk.Button(buttons, text="Сохранить исправления", command=save, bg=ACCENT_2, fg="#03101f", relief="flat", padx=18, pady=8, font=self._font(10, "bold")).grid(row=0, column=0, sticky="ew", padx=(0, 6))
            tk.Button(buttons, text="Вернуться без изменений", command=cancel, bg=PANEL_3, fg=TEXT, relief="flat", padx=18, pady=8, font=self._font(9)).grid(row=0, column=1, sticky="ew", padx=(6, 0))
            win.bind("<Escape>", lambda _event: cancel())
            win.protocol("WM_DELETE_WINDOW", cancel)
            win.transient(parent)
            win.grab_set()
            try:
                form.winfo_children()[1].focus_set()
            except Exception as exc:
                record_soft_exception("actions_creation_preflight.edit_initial_focus", exc)
            self.root.wait_window(win)
            return bool(result["saved"])
        except Exception as exc:
            record_soft_exception("actions_creation_preflight.edit_patient_case", exc)
            messagebox.showwarning("Исправить данные", "Не удалось открыть редактор данных. Исправьте поля в главном окне и повторите.", parent=parent)
            return False

    def _confirm_patient_case_before_creation(self, review) -> bool:
        """Implement the _confirm_patient_case_before_creation workflow with validation, UI state updates and diagnostics."""
        if not self._prompt_missing_required_fields_or_continue(review):
            return False
        if os.environ.get("CI"):
            return True
        try:
            import tkinter as tk
            from tkinter import ttk
            from app_config import PANEL, FIELD, TEXT, MUTED, WARN, ERROR, SUCCESS, ACCENT_2, PANEL_3, DEEP
            win = tk.Toplevel(self.root)
            win.title("Проверка перед созданием документов")
            win.configure(bg=DEEP)
            win.geometry("820x620")
            win.grid_columnconfigure(0, weight=1)
            win.grid_rowconfigure(1, weight=1)
            header = tk.Label(
                win,
                text="Проверьте данные перед созданием документов",
                bg=DEEP,
                fg=TEXT,
                font=self._font(14, "bold"),
                padx=14,
                pady=10,
                anchor="w",
            )
            header.grid(row=0, column=0, sticky="ew")
            frame = tk.Frame(win, bg=PANEL, padx=10, pady=10)
            frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(0, weight=1)
            text = tk.Text(frame, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word", font=self._font(10), padx=10, pady=10)
            text.grid(row=0, column=0, sticky="nsew")
            scroll = ttk.Scrollbar(frame, command=text.yview)
            scroll.grid(row=0, column=1, sticky="ns")
            text.configure(yscrollcommand=scroll.set)
            text.insert("end", review.as_text())
            text.configure(state="disabled")
            result = {"ok": False}

            def close_preflight() -> None:
                try:
                    win.grab_release()
                except Exception as exc:
                    record_soft_exception("actions_creation_preflight.preflight_grab_release", exc)
                try:
                    win.withdraw()
                except Exception as exc:
                    record_soft_exception("actions_creation_preflight.preflight_withdraw", exc)
                win.destroy()

            buttons = tk.Frame(win, bg=DEEP)
            buttons.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
            buttons.grid_columnconfigure(0, weight=1)
            def ok():
                result["ok"] = True
                close_preflight()
            def cancel():
                result["ok"] = False
                close_preflight()
            def refresh_review_text() -> None:
                try:
                    refreshed = self._build_patient_case_review_for_selection(
                        self.selected_medical_docs(),
                        self.diaries_selected(),
                        self.selected_custom_docs(),
                    )
                    text.configure(state="normal")
                    text.delete("1.0", "end")
                    text.insert("end", refreshed.as_text())
                    text.configure(state="disabled")
                except Exception as exc:
                    record_soft_exception("actions_creation_preflight.refresh_review_after_edit", exc)

            def edit_fields():
                if self._edit_patient_case_inside_preflight(win):
                    refresh_review_text()
                    self._set_status("Данные исправлены. Проверьте окно ещё раз и нажмите «Создать документы».")
                else:
                    self._set_status("Исправление отменено. Окно проверки осталось открытым.")
            tk.Button(buttons, text="Создать документы", command=ok, bg=ACCENT_2, fg="#03101f", relief="flat", padx=18, pady=8, font=self._font(10, "bold")).grid(row=0, column=0, sticky="e", padx=(0, 8))
            tk.Button(buttons, text="Исправить данные", command=edit_fields, bg=PANEL_3, fg=TEXT, relief="flat", padx=18, pady=8, font=self._font(9, "bold")).grid(row=0, column=1, sticky="e", padx=(0, 8))
            tk.Button(buttons, text="Отмена", command=cancel, bg=FIELD, fg=TEXT, relief="flat", padx=18, pady=8, font=self._font(9)).grid(row=0, column=2, sticky="e")
            win.bind("<Return>", lambda _event: ok())
            win.bind("<Escape>", lambda _event: cancel())
            win.protocol("WM_DELETE_WINDOW", cancel)
            win.minsize(680, 360)
            win.transient(self.root)
            win.grab_set()
            self.root.wait_window(win)
            return bool(result["ok"])
        except Exception as exc:
            record_soft_exception("actions_creation_orchestrator.confirm_patient_case", exc)
            return messagebox.askyesno("Проверка перед созданием", review.as_text() + "\nСоздать документы?")
