from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from app_config import ACCENT, FIELD, PANEL, TEXT
from medical_text_utils import sanitize_case_number_candidate
from medical_parser_sanitize import sanitize_diagnosis
from medical_primary_document_state import selected_primary_document_path_text
from medical_date_state import current_semantic_date
from diagnostic_logging import record_soft_exception
from dialog_fields_popup import DialogDiagnosisPopup
from dialog_fields_core import call_prompt_fields_compatible


class DialogDocumentDetailsMixin:
    def _prompt_commission_details(self) -> bool:
        date_default = self._current_popup_date_value("commission_date") or self._today_str()
        values = call_prompt_fields_compatible(self,
            title="Совместный осмотр",
            rows=[
                ("Номер истории болезни", self._case_number_popup_default()),
                ("Дата / дата проведения комиссии", date_default),
                ("Номер", self.commission_number_var.get().strip()),
            ],
            linked_groups=[],
            date_field_keys=[None, "commission_date", None],
        )
        if values is None:
            return False
        if not self._store_case_number_value(values[0].strip()):
            messagebox.showwarning("Не заполнено поле", "Укажите номер истории болезни.")
            return False
        commission_date = self._normalize_required_date_for_ui(values[1].strip(), "Дата комиссии")
        if commission_date is None:
            return False
        commission_number = values[2].strip()
        if not commission_number:
            messagebox.showwarning("Не заполнено поле", "Укажите номер совместного осмотра.")
            return False
        if not self._store_popup_date_value(
            "commission_date",
            commission_date,
            source_label="popup совместного осмотра",
            confirm_conflict=False,
        ):
            return False
        self.commission_number_var.set(commission_number)
        self._remember_committee_dates(committee_date=commission_date)
        return True

    def _prompt_rvk_details(self) -> bool:
        """Единый popup Акта РВК: лечение/диагноз, дата выписки, заключение и военкомат."""
        win = tk.Toplevel(self.root)
        win.title("Акт РВК")
        win.configure(bg=PANEL)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        result = {"ok": False}
        diagnosis_popup = DialogDiagnosisPopup(win, self.root, language_id=self._diagnosis_language() if hasattr(self, "_diagnosis_language") else "ru")
        case_var = tk.StringVar(value=self._case_number_popup_default())
        treatment_var = tk.StringVar(value=self.assigned_treatment_var.get().strip() or self._treatment_popup_default())
        diagnosis_var = tk.StringVar(value=self.diagnosis_var.get().strip() or sanitize_diagnosis(getattr(getattr(self, "data", None), "diagnosis", "")))
        discharge_var = tk.StringVar(value=self._discharge_popup_default())
        act_var = tk.StringVar(value=self.rvk_act_number_var.get().strip())
        default_military = self.rvk_military_commissariat_var.get().strip()
        if not default_military:
            try:
                defaults_raw = self._settings.get("defaults") if isinstance(getattr(self, "_settings", None), dict) else {}
                if isinstance(defaults_raw, dict):
                    default_military = str(defaults_raw.get("rvk_military_commissariat", "") or "").strip()
            except Exception as exc:
                record_soft_exception("dialog_document_details.rvk_default", exc)
        military_var = tk.StringVar(value=default_military)
        need_hospitalization_details = self._hospitalization_details_missing()
        need_manual_treatment = (not need_hospitalization_details) and self._manual_treatment_missing()
        need_discharge_date = self._selected_outputs_require_discharge_date() and self._discharge_date_missing_or_invalid()
        frame = tk.Frame(win, bg=PANEL, padx=18, pady=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        row = 0
        entries: list[tk.Entry] = []
        def add_entry(label_text: str, var: tk.StringVar, *, width: int = 44) -> tk.Entry:
            nonlocal row
            tk.Label(frame, text=label_text, bg=PANEL, fg=TEXT, font=self._font(10), anchor="w").grid(
                row=row, column=0, sticky="w", pady=(0, 4)
            )
            entry = tk.Entry(frame, textvariable=var, width=width, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat")
            entry.grid(row=row + 1, column=0, sticky="ew", pady=(0, 10))
            row += 2
            entries.append(entry)
            return entry
        add_entry("Номер истории болезни", case_var)
        if need_hospitalization_details:
            add_entry("Лечение", treatment_var, width=64)
            diagnosis_entry = add_entry("Диагноз", diagnosis_var, width=64)
            diagnosis_popup.attach(diagnosis_entry, diagnosis_var)
        elif need_manual_treatment:
            add_entry("Лечение", treatment_var, width=64)
        if need_discharge_date:
            add_entry("Дата выписки", discharge_var, width=28)
        number_entry = add_entry("Номер медицинского заключения", act_var, width=36)
        tk.Label(frame, text="Военкомат", bg=PANEL, fg=TEXT, font=self._font(10), anchor="w").grid(
            row=row, column=0, sticky="w", pady=(0, 6)
        )
        row += 1
        options_frame = tk.Frame(frame, bg=PANEL)
        options_frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1
        for idx, value in enumerate(("районный военный комиссариат", "городской военный комиссариат", "областной военный комиссариат")):
            options_frame.grid_columnconfigure(idx, weight=1)
            btn = tk.Button(
                options_frame,
                text=value,
                command=lambda v=value: military_var.set(v),
                bg=FIELD,
                fg=TEXT,
                activebackground=ACCENT,
                activeforeground="#03101f",
                relief="flat",
                padx=8,
                pady=6,
                cursor="hand2",
            )
            btn.grid(row=0, column=idx, sticky="ew", padx=(0 if idx == 0 else 6, 0))
        add_entry("Военкомат / организация направления", military_var, width=64)
        buttons = tk.Frame(frame, bg=PANEL)
        buttons.grid(row=row, column=0, sticky="e")
        def ok() -> None:
            """Implement the ok workflow with validation, UI state updates and diagnostics."""
            case_value = case_var.get().strip()
            if not self._store_case_number_value(case_value):
                messagebox.showwarning("Не заполнено поле", "Укажите номер истории болезни.", parent=win)
                return
            if need_hospitalization_details:
                treatment_value = treatment_var.get().strip()
                diagnosis_value = sanitize_diagnosis(self._normalize_popup_diagnosis_value(diagnosis_var.get().strip()))
                if not treatment_value:
                    messagebox.showwarning("Не заполнено поле", "Укажите лечение.", parent=win)
                    return
                if not diagnosis_value:
                    messagebox.showwarning("Не заполнено поле", "Укажите диагноз.", parent=win)
                    return
                self.assigned_treatment_var.set(treatment_value)
                self.diagnosis_var.set(diagnosis_value)
                self._popup_diagnosis_override = diagnosis_value
                self._manual_diagnosis = True
                if hasattr(self, "data"):
                    self.data.treatment_plan = treatment_value
                    self.data.diagnosis = diagnosis_value
            elif need_manual_treatment:
                treatment_value = treatment_var.get().strip()
                if not treatment_value:
                    messagebox.showwarning("Не заполнено поле", "Укажите лечение.", parent=win)
                    return
                self.assigned_treatment_var.set(treatment_value)
                if hasattr(self, "data"):
                    self.data.treatment_plan = treatment_value
            if need_discharge_date and not self._store_discharge_date_value(discharge_var.get().strip(), parent=win, source_label="popup Акта РВК"):
                messagebox.showwarning(
                    "Некорректная дата выписки",
                    "Дата выписки должна быть в формате ДД.ММ.ГГГГ, ДДММГГГГ, ДДММГГ или коротко ДМГГ, например 20.04.2026, 200426 или 1126.",
                    parent=win,
                )
                return
            if not act_var.get().strip():
                messagebox.showwarning("Не заполнено поле", "Укажите номер медицинского заключения.", parent=win)
                return
            if not military_var.get().strip():
                messagebox.showwarning("Не заполнено поле", "Укажите военкомат или организацию направления.", parent=win)
                return
            self.rvk_act_number_var.set(act_var.get().strip())
            military_value = military_var.get().strip()
            self.rvk_military_commissariat_var.set(military_value)
            try:
                defaults = self._settings.get("defaults") if isinstance(getattr(self, "_settings", None), dict) else None
                if not isinstance(defaults, dict):
                    defaults = {}
                    self._settings["defaults"] = defaults
                defaults["rvk_military_commissariat"] = military_value
                self._save_settings()
            except Exception as exc:
                record_soft_exception("dialog_document_details.remember_rvk", exc, detail=military_value)
            self.rvk_work_position_var.set("")
            result["ok"] = True
            close_dialog()
        def close_dialog() -> None:
            try:
                diagnosis_popup.hide()
            except Exception as exc:
                record_soft_exception("dialog_document_details.rvk_diagnosis_hide", exc)
            try:
                win.grab_release()
            except Exception as exc:
                record_soft_exception("dialog_document_details.rvk_grab_release", exc)
            try:
                win.withdraw()
            except Exception as exc:
                record_soft_exception("dialog_document_details.rvk_withdraw", exc)
            win.destroy()
        def cancel() -> None:
            close_dialog()
        tk.Button(buttons, text="OK", command=ok, bg=ACCENT, fg="#03101f", relief="flat", padx=16, pady=6).grid(row=0, column=0, padx=(0, 8))
        tk.Button(buttons, text="Отмена", command=cancel, bg=FIELD, fg=TEXT, relief="flat", padx=14, pady=6).grid(row=0, column=1)
        win.bind("<Return>", lambda _event: ok())
        win.bind("<Escape>", lambda _event: cancel())
        win.protocol("WM_DELETE_WINDOW", cancel)
        (entries[0] if entries else number_entry).focus_set()
        win.update_idletasks()
        self.root.wait_window(win)
        return bool(result["ok"])
    def _prompt_vk_mse_details(self) -> bool:
        date_default = self._current_popup_date_value("vk_date") or self._today_str()
        protocol_date_default = self._current_popup_date_value("vk_protocol_date") or date_default
        shared_org, shared_position = self._shared_work_defaults()
        values = call_prompt_fields_compatible(self,
            title="ВК на МСЭ",
            rows=[
                ("Номер истории болезни", self._case_number_popup_default()),
                ("Дата / дата проведения ВК / дата проведения комиссии", date_default),
                ("Протокол номер", self.vk_protocol_number_var.get().strip()),
                ("От / дата протокола / Дата протокола", protocol_date_default),
                ("Место работы", self.vk_mse_work_org_var.get().strip() or shared_org),
                ("Должность", self.vk_mse_position_var.get().strip() or shared_position),
            ],
            width=64,
            # Если врач меняет первую дату, поле «От / дата протокола»
            # автоматически получает ту же дату, пока врач сам его не изменил.
            linked_groups=[(1, [3])],
            date_field_keys=[None, "vk_date", None, "vk_protocol_date", None, None],
        )
        if values is None:
            return False
        if not self._store_case_number_value(values[0].strip()):
            messagebox.showwarning("Не заполнено поле", "Укажите номер истории болезни.")
            return False
        vk_date = self._normalize_required_date_for_ui(values[1].strip(), "Дата ВК")
        vk_protocol_date = self._normalize_required_date_for_ui(values[3].strip(), "Дата протокола ВК")
        if vk_date is None or vk_protocol_date is None:
            return False
        protocol_number = values[2].strip()
        work_org = values[4].strip()
        position = values[5].strip()
        if not protocol_number:
            messagebox.showwarning("Не заполнено поле", "Укажите номер протокола ВК.")
            return False
        if not work_org:
            messagebox.showwarning("Не заполнено поле", "Укажите место работы.")
            return False
        if not self._store_popup_date_value("vk_date", vk_date, source_label="popup ВК на МСЭ", confirm_conflict=False):
            return False
        self.vk_protocol_number_var.set(protocol_number)
        if not self._store_popup_date_value("vk_protocol_date", vk_protocol_date, source_label="popup ВК на МСЭ", confirm_conflict=False):
            return False
        self._sync_shared_work_details(work_org, position)
        self._remember_committee_dates(committee_date=vk_date, protocol_date=vk_protocol_date)
        return True

    def _prompt_sick_leave_vk_details(self) -> bool:
        """Collect and validate all ВК-больничный fields in one modal popup."""
        date_default = self._current_popup_date_value("sick_leave_vk_date") or self._today_str()
        protocol_date_default = self._current_popup_date_value("sick_leave_vk_protocol_date") or date_default
        commission_date_default = self._current_popup_date_value("sick_leave_vk_commission_date") or date_default
        shared_org, shared_position = self._shared_work_defaults()
        values = call_prompt_fields_compatible(self,
            title="ВК больничный",
            rows=[
                ("Номер истории болезни", self._case_number_popup_default()),
                ("Дата / дата проведения ВК", date_default),
                ("Номер протокола", self.sick_leave_vk_protocol_number_var.get().strip()),
                ("От / дата протокола / Дата протокола", protocol_date_default),
                ("Дата проведения комиссии", commission_date_default),
                ("Место работы", self.sick_leave_vk_work_org_var.get().strip() or shared_org),
                ("Должность", self.sick_leave_vk_position_var.get().strip() or shared_position),
            ],
            width=64,
            # Первая дата автоматически дублируется в «От» и в
            # «Дата проведения комиссии», но оба поля можно изменить вручную.
            linked_groups=[(1, [3, 4])],
            date_field_keys=[None, "sick_leave_vk_date", None, "sick_leave_vk_protocol_date", "sick_leave_vk_commission_date", None, None],
        )
        if values is None:
            return False
        if not self._store_case_number_value(values[0].strip()):
            messagebox.showwarning("Не заполнено поле", "Укажите номер истории болезни.")
            return False
        sick_vk_date = self._normalize_required_date_for_ui(values[1].strip(), "Дата ВК больничного")
        sick_vk_protocol_date = self._normalize_required_date_for_ui(values[3].strip(), "Дата протокола ВК больничного")
        sick_vk_commission_date = self._normalize_required_date_for_ui(values[4].strip(), "Дата проведения комиссии")
        if sick_vk_date is None or sick_vk_protocol_date is None or sick_vk_commission_date is None:
            return False
        protocol_number = values[2].strip()
        work_org = values[5].strip()
        position = values[6].strip()
        if not protocol_number:
            messagebox.showwarning("Не заполнено поле", "Укажите номер протокола ВК больничного.")
            return False
        if not work_org:
            messagebox.showwarning("Не заполнено поле", "Укажите место работы.")
            return False
        if not self._store_popup_date_value("sick_leave_vk_date", sick_vk_date, source_label="popup ВК больничного", confirm_conflict=False):
            return False
        self.sick_leave_vk_protocol_number_var.set(protocol_number)
        if not self._store_popup_date_value("sick_leave_vk_protocol_date", sick_vk_protocol_date, source_label="popup ВК больничного", confirm_conflict=False):
            return False
        if not self._store_popup_date_value("sick_leave_vk_commission_date", sick_vk_commission_date, source_label="popup ВК больничного", confirm_conflict=False):
            return False
        self._sync_shared_work_details(work_org, position)
        self._remember_committee_dates(committee_date=sick_vk_commission_date or sick_vk_date, protocol_date=sick_vk_protocol_date)
        return True

    def _on_primary_document_type_changed(self) -> None:
        """Реакция на выбор типа первичного документа."""
        selected_type = self.primary_document_type_var.get()
        desired_display = "Направление на госпитализацию" if selected_type == "hospitalization_referral" else "Первичный осмотр"
        if hasattr(self, "primary_document_type_display_var") and self.primary_document_type_display_var.get() != desired_display:
            self.primary_document_type_display_var.set(desired_display)
        self.assigned_treatment_var.set("")
        self.case_number_var.set("")
        if selected_primary_document_path_text(self):
            self.reparse_navigation(silent=True)
            if self.primary_document_type_var.get() == "hospitalization_referral":
                self._prompt_assigned_treatment_if_needed(force=True)
                self.reparse_navigation(silent=True)
            else:
                self._set_status("Тип изменён на первичный осмотр. Popup не требуется.")
        else:
            self.status_label.config(text="Готово")

    def _treatment_popup_default(self) -> str:
        """Текст по умолчанию для popup-окна лечения."""
        if self.assigned_treatment_var.get().strip():
            return self.assigned_treatment_var.get().strip()
        if self.data.treatment_plan.strip():
            return self.data.treatment_plan.strip()
        navigation = selected_primary_document_path_text(self)
        if navigation and Path(navigation).exists():
            try:
                return self._parse_primary_document(navigation).treatment_plan.strip()
            except Exception as exc:
                record_soft_exception("dialog_document_details.treatment_default_parse", exc, detail=navigation)
                return ""
        return ""

    def _patient_name_for_case_number_guard(self) -> str:
        values: list[str] = []
        if hasattr(self, "patient_name_var"):
            values.append(self.patient_name_var.get().strip())
        data = getattr(self, "data", None)
        if data is not None:
            values.append(getattr(data, "fio", "").strip())
            values.append(getattr(data, "output_fio", "").strip())
        return " ".join(value for value in values if value)

    def _case_number_popup_default(self) -> str:
        patient_name = self._patient_name_for_case_number_guard()
        if self.case_number_var.get().strip():
            value = sanitize_case_number_candidate(self.case_number_var.get(), patient_name=patient_name)
            if value:
                return value
            self.case_number_var.set("")
        data = getattr(self, "data", None)
        if data is not None and getattr(data, "case_number", "").strip():
            value = sanitize_case_number_candidate(data.case_number, patient_name=patient_name)
            if value:
                return value
            data.case_number = ""
        navigation = selected_primary_document_path_text(self)
        if navigation and Path(navigation).exists():
            try:
                parsed = self._parse_primary_document(navigation)
                value = sanitize_case_number_candidate(parsed.case_number, patient_name=patient_name or parsed.fio)
                return value
            except Exception as exc:
                record_soft_exception("dialog_document_details.case_number_default_parse", exc, detail=navigation)
                return ""
        return ""

    def _store_case_number_value(self, value: str) -> bool:
        """Save shared «номер истории болезни» for all popup windows and renderers."""
        value = sanitize_case_number_candidate(value, patient_name=self._patient_name_for_case_number_guard())
        if not value:
            return False
        self.case_number_var.set(value)
        if hasattr(self, "data"):
            self.data.case_number = value
        return True

    def _case_number_missing(self) -> bool:
        return not bool(self._case_number_popup_default())

    def _discharge_popup_default(self) -> str:
        value = current_semantic_date(self, "discharge_date")
        if value:
            return value
        data = getattr(self, "data", None)
        if data is not None and getattr(data, "discharge_date", "").strip():
            return data.discharge_date.strip()
        return ""

    def _primary_has_treatment_section(self) -> bool:
        """True if the uploaded primary DOCX itself has a treatment row.

        The parser scans the full DOCX text, including tables. We intentionally
        check the explicit section-row flag rather than any random occurrence of
        the word "лечение", so phrases like «за время лечения» do not suppress
        the doctor's popup.
        """
        data = getattr(self, "data", None)
        if data is not None and getattr(data, "has_treatment_section", False):
            return True
        navigation = selected_primary_document_path_text(self)
        if navigation and Path(navigation).exists():
            try:
                parsed = self._parse_primary_document(navigation)
                return bool(getattr(parsed, "has_treatment_section", False))
            except Exception as exc:
                record_soft_exception("dialog_document_details.primary_treatment_flag_parse", exc, detail=navigation)
                return False
        return False

    def _primary_treatment_missing_for_medical_docs(self) -> bool:
        """Need manual treatment when primary DOCX has no treatment section."""
        if self.assigned_treatment_var.get().strip():
            return False
        navigation = selected_primary_document_path_text(self)
        if not navigation or not Path(navigation).exists():
            return False
        return not self._primary_has_treatment_section()

    def _prompt_missing_primary_treatment_if_needed(self, *, prompt_if_needed: bool = True) -> bool:
        """Ask shared case number and missing «Лечение» for block-03 medical docs.

        Contract: if the uploaded primary document has no explicit row
        «Лечение» / «Назначенное лечение» / «План лечения», every medical
        output tile except «Дневники наблюдения» must request treatment.
        The shared case number is shown in the same popup and then reused by
        all subsequent popups and renderers.
        """
        treatment_missing = self._primary_treatment_missing_for_medical_docs()
        case_missing = self._case_number_missing()
        if not treatment_missing and not case_missing:
            default_treatment = self._treatment_popup_default()
            if default_treatment and not self.assigned_treatment_var.get().strip():
                self.assigned_treatment_var.set(default_treatment)
            return True
        if not prompt_if_needed:
            return False

        rows: list[tuple[str, str]] = []
        fields: list[str] = []
        if case_missing or treatment_missing:
            rows.append(("Номер истории болезни", self._case_number_popup_default()))
            fields.append("case_number")
        if treatment_missing:
            rows.append(("Лечение", self.assigned_treatment_var.get().strip() or self._treatment_popup_default()))
            fields.append("treatment")

        values = call_prompt_fields_compatible(self,
            title="Данные для выбранных документов",
            rows=rows,
            width=72,
        )
        if values is None:
            return False
        for field, raw_value in zip(fields, values):
            value = raw_value.strip()
            if field == "case_number":
                if not self._store_case_number_value(value):
                    messagebox.showwarning("Не заполнено поле", "Укажите номер истории болезни.")
                    return False
            elif field == "treatment":
                if not value:
                    messagebox.showwarning("Не заполнено поле", "Укажите лечение.")
                    return False
                self.assigned_treatment_var.set(value)
                if hasattr(self, "data"):
                    self.data.treatment_plan = value
        return True

    def _prompt_primary_exam_details_if_needed(self, *, force: bool = False) -> bool:
        """For primary exams, ask only for missing treatment when needed.

        If the primary DOCX already has an explicit treatment section, no popup
        is shown. If the section is absent and any medical document is selected,
        the doctor fills exactly one field: «Лечение».
        """
        default_treatment = self._treatment_popup_default()
        default_case_number = self._case_number_popup_default()
        if default_treatment and not self.assigned_treatment_var.get().strip() and self._primary_has_treatment_section():
            self.assigned_treatment_var.set(default_treatment)
        if default_case_number and not self.case_number_var.get().strip():
            self.case_number_var.set(default_case_number)
        return self._prompt_missing_primary_treatment_if_needed(prompt_if_needed=True)
