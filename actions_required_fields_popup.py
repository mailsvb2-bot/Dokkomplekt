from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox
from typing import Any

from app_config import ACCENT_2, DEEP, FIELD, PANEL, PANEL_3, TEXT, WARN
from diagnostic_logging import record_soft_exception
from icd10_f_search import normalize_required_diagnosis_with_icd10
from medical_formatting import parse_date
from medical_text_utils import sanitize_case_number_candidate
from dialog_fields_popup import DialogDiagnosisPopup
from universal_fields import normalize_field_id


LAB_FIELD_KEYS = {"labs", "labs.results", "laboratory", "analysis", "analyses"}
NO_LABS_VALUES = {"нет анализов", "анализов нет", "без анализов", "не требуется", "не требуются"}

SEMANTIC_DATE_STORE_KEYS = {
    "admission.date": "admission_date",
    "discharge.date": "discharge_date",
    "labs.date": "labs_explicit_date",
    "commission.date": "commission_date",
    "vk_mse.date": "vk_date",
    "vk_mse.protocol_date": "vk_protocol_date",
    "sick_leave_vk.date": "sick_leave_vk_date",
    "sick_leave_vk.protocol_date": "sick_leave_vk_protocol_date",
    "sick_leave_vk.commission_date": "sick_leave_vk_commission_date",
    "expert.sick_leave_from": "expert_sick_leave_from",
}


DIAGNOSIS_FIELD_HINTS = {
    "diagnosis",
    "diagnosis.main",
    "diagnosis.primary",
    "primary.diagnosis",
    "patient.diagnosis",
    "main.diagnosis",
    "clinical.diagnosis",
}
DIAGNOSIS_TEXT_HINTS = ("diagnos", "диагноз", "мкб", "mkb", "icd", "icd-10")
CASE_TEXT_HINTS = (
    "case.number", "case_number", "case.no", "case.num", "history.number", "history_number",
    "medical.record", "medical_record", "medical.card", "record.number", "record_no", "ib.number",
    "номер истории", "история болезни", "№ истории", "истории №", "иб №", "иб n",
    "номер карты", "медицинская карта",
)
ADMISSION_TEXT_HINTS = (
    "admission.date", "admission_date", "admission.dt", "date.of.admission", "date_admission",
    "hospitalization.date", "hospitalization_date", "hospital.admission", "admitted.at", "admitted_at",
    "дата поступ", "дата госпитал", "госпитализац", "поступил", "поступила", "принят", "принята",
)
DISCHARGE_TEXT_HINTS = (
    "discharge.date", "discharge_date", "discharge.dt", "date.of.discharge", "date_discharge",
    "hospital.discharge", "discharged.at", "discharged_at",
    "дата выписк", "выписан", "выписана", "выписывается",
)
TREATMENT_TEXT_HINTS = (
    "treatment.plan", "treatment_plan", "assigned_treatment", "assigned.treatment",
    "prescribed_treatment", "therapy.plan", "therapy_plan",
    "лечение", "назначенное лечение", "план лечения", "терапия", "назначения",
)
LABS_TEXT_HINTS = (
    "labs.results", "lab.results", "lab_results", "analysis.results", "analysis_results",
    "analyses.results", "laboratory.results", "instrumental.results",
    "анализ", "лаборатор", "обследован", "исследован", "оак", "оам", "бак",
)

LEGACY_STORE_KEYS = {
    "patient.fio": "fio",
    "patient.work": "patient_work",
    "patient.position": "patient_position",
    "case.number": "case_number",
    "admission.date": "admission_date",
    "discharge.date": "discharge_date",
    "diagnosis.main": "diagnosis",
    "diagnosis.icd10": "diagnosis",
    "treatment.plan": "treatment",
    "labs.results": "labs",
    "labs.date": "labs_explicit_date",
    "instrumental.results": "labs",
    "expert.work_status": "expert_work_status",
    "expert.work_org": "expert_work_org",
    "expert.position": "expert_position",
    "expert.sick_leave_needed": "expert_sick_leave_needed",
    "expert.sick_leave_from": "expert_sick_leave_from",
    "expert.sick_leave_number": "expert_sick_leave_number",
    "commission.date": "commission_date",
    "commission.number": "commission_number",
    "rvk.act_number": "rvk_act_number",
    "rvk.military_commissariat": "rvk_military_commissariat",
    "rvk.work_position": "rvk_work_position",
    "vk_mse.date": "vk_date",
    "vk_mse.protocol_number": "vk_protocol_number",
    "vk_mse.protocol_date": "vk_protocol_date",
    "vk_mse.work": "vk_mse_work_org",
    "vk_mse.position": "vk_mse_position",
    "vk_mse.work_position": "vk_mse_work_position",
    "sick_leave_vk.date": "sick_leave_vk_date",
    "sick_leave_vk.protocol_number": "sick_leave_vk_protocol_number",
    "sick_leave_vk.protocol_date": "sick_leave_vk_protocol_date",
    "sick_leave_vk.commission_date": "sick_leave_vk_commission_date",
    "sick_leave_vk.work": "sick_leave_vk_work_org",
    "sick_leave_vk.position": "sick_leave_vk_position",
    "sick_leave_vk.work_position": "sick_leave_vk_work_position",
}


def _raw_field_id(field: Any) -> str:
    return str(getattr(field, "key", "") or getattr(field, "field_id", "") or "").strip()


def _safe_normalized_field_id(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return normalize_field_id(raw)
    except Exception as exc:
        record_soft_exception("actions_required_fields_popup.normalize_field_id", exc, detail=raw[:120])
        return raw.casefold().replace("ё", "е").replace("-", "_").replace(" ", "_").replace("_", ".")


def _field_id(field: Any) -> str:
    return _safe_normalized_field_id(_raw_field_id(field))


def _normalized_field_signature(field: Any) -> str:
    parts = (
        getattr(field, "key", ""),
        getattr(field, "field_id", ""),
        getattr(field, "label", ""),
        getattr(field, "placeholder", ""),
        getattr(field, "reason", ""),
    )
    return " ".join(str(part or "") for part in parts).casefold().replace("ё", "е").replace("_", ".")


def _matches_any(field: Any, exact_ids: set[str], text_hints: tuple[str, ...]) -> bool:
    normalized = _field_id(field)
    signature = _normalized_field_signature(field)
    return normalized in exact_ids or any(hint in signature for hint in text_hints)


def _store_key_for_field(field: Any) -> str:
    """Map universal/custom field ids to the legacy UI state keys.

    The preflight popup stores values through the same canonical UI/data
    setters that fixed-document generation uses.  This keeps custom doctor
    templates from creating a second, invisible state for case number,
    diagnosis, dates, treatment or labs.
    """
    normalized = _field_id(field)
    if normalized in LEGACY_STORE_KEYS:
        return LEGACY_STORE_KEYS[normalized]
    if _is_diagnosis_field(field):
        return "diagnosis"
    if _is_case_number_field(field):
        return "case_number"
    if _is_admission_date_field(field):
        return "admission_date"
    if _is_discharge_date_field(field):
        return "discharge_date"
    if _is_treatment_field(field):
        return "treatment"
    if _is_labs_field(field):
        return "labs"
    return _raw_field_id(field)



def _semantic_date_store_key_for_field(field: Any) -> str:
    normalized = _field_id(field)
    if normalized in SEMANTIC_DATE_STORE_KEYS:
        return SEMANTIC_DATE_STORE_KEYS[normalized]
    if _is_admission_date_field(field):
        return "admission_date"
    if _is_discharge_date_field(field):
        return "discharge_date"
    return ""


def _is_semantic_date_field(field: Any) -> bool:
    return bool(_semantic_date_store_key_for_field(field))


def _is_diagnosis_field(field: Any) -> bool:
    """Return True for both legacy and dynamic diagnosis fields.

    The required-fields popup may receive universal-profile fields such as
    ``patient.diagnosis`` or ``diagnosis.primary``.  ICD-10 autocomplete and
    validation must not depend on one exact legacy key, otherwise custom doctor
    templates silently lose diagnosis normalization.
    """
    normalized = _field_id(field)
    signature = _normalized_field_signature(field)
    return normalized in DIAGNOSIS_FIELD_HINTS or normalized.startswith("diagnosis.") or any(hint in signature for hint in DIAGNOSIS_TEXT_HINTS)


def _is_case_number_field(field: Any) -> bool:
    return _matches_any(field, {"case.number"}, CASE_TEXT_HINTS)


def _is_discharge_date_field(field: Any) -> bool:
    normalized = _field_id(field)
    signature = _normalized_field_signature(field)
    return (
        normalized in {"discharge.date", "discharge.date.actual"}
        or any(hint in signature for hint in DISCHARGE_TEXT_HINTS)
        or (("date" in normalized or "дата" in signature) and ("discharge" in normalized or "выписк" in signature))
    )


def _is_admission_date_field(field: Any) -> bool:
    normalized = _field_id(field)
    signature = _normalized_field_signature(field)
    return (
        normalized in {"admission.date", "hospitalization.date"}
        or any(hint in signature for hint in ADMISSION_TEXT_HINTS)
        or (("date" in normalized or "дата" in signature) and ("admission" in normalized or "hospitalization" in normalized or "поступ" in signature or "госпитал" in signature))
    )


def _is_treatment_field(field: Any) -> bool:
    return _matches_any(field, {"treatment.plan"}, TREATMENT_TEXT_HINTS)


def _is_labs_field(field: Any) -> bool:
    normalized = _field_id(field)
    if normalized in {"labs.results", "labs", "laboratory", "analysis", "analyses"}:
        return True
    signature = _normalized_field_signature(field)
    return any(hint in signature for hint in LABS_TEXT_HINTS)


def prompt_missing_required_fields_or_continue(app: Any, review: Any) -> bool:
    """Open a strict, scrollable correction dialog for missing critical fields."""
    missing = review.critical_missing()
    if not missing:
        app._allow_missing_required_creation = False
        return True
    if os.environ.get("CI"):
        app._allow_missing_required_creation = False
        return False
    try:
        return _RequiredFieldsDialog(app, review, missing).show()
    except Exception as exc:
        record_soft_exception("actions_required_fields_popup.open", exc)
        messagebox.showwarning(
            "Не заполнено обязательное поле",
            review.as_text(include_sources=False) + "\n\nСоздание документов остановлено. Заполните обязательные поля и повторите.",
        )
        app._allow_missing_required_creation = False
        return False


class _RequiredFieldsDialog:
    def __init__(self, app: Any, review: Any, missing: list[Any]) -> None:
        self.app = app
        self.review = review
        self.missing = missing
        self.result = {"action": "cancel"}
        self.variables: dict[str, tk.StringVar] = {}
        self.entries: dict[str, object] = {}
        self.text_widgets: dict[str, tk.Text] = {}
        self.win: tk.Toplevel | None = None
        self.canvas: tk.Canvas | None = None
        self.form: tk.Frame | None = None
        self.form_id: int | None = None
        self.diagnosis_popup: DialogDiagnosisPopup | None = None

    def show(self) -> bool:
        self._create_window()
        self._build_header()
        self._build_scroll_area()
        self._build_rows()
        self._build_buttons()
        self._bind_window()
        self._focus_first()
        self.app.root.wait_window(self.win)
        return self.result["action"] == "save"

    def _window(self) -> tk.Toplevel:
        if self.win is None:
            raise RuntimeError("required fields dialog window is not initialized")
        return self.win

    def _form(self) -> tk.Frame:
        if self.form is None:
            raise RuntimeError("required fields dialog form is not initialized")
        return self.form

    def _create_window(self) -> None:
        title = "Не заполнены обязательные поля" if len(self.missing) > 1 else "Не заполнено обязательное поле"
        self.win = tk.Toplevel(self.app.root)
        self.win.title(title)
        self.win.configure(bg=DEEP)
        self.win.geometry("780x560")
        self.win.minsize(700, 420)
        self.win.grid_columnconfigure(0, weight=1)
        self.win.grid_rowconfigure(1, weight=1)

    def _build_header(self) -> None:
        win = self._window()
        text = (
            "Перед созданием документов нужно заполнить обязательные поля. "
            "Окно останется открытым, пока значение не будет исправлено, поэтому данные можно спокойно поправить здесь."
        )
        tk.Label(
            win,
            text=text,
            bg=DEEP,
            fg=WARN,
            font=self.app._font(12, "bold"),
            padx=14,
            pady=10,
            wraplength=730,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")

    def _build_scroll_area(self) -> None:
        win = self._window()
        shell = tk.Frame(win, bg=PANEL, padx=0, pady=0)
        shell.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(shell, bg=PANEL, highlightthickness=0, borderwidth=0)
        scrollbar = tk.Scrollbar(shell, orient="vertical", command=self.canvas.yview)
        self.form = tk.Frame(self.canvas, bg=PANEL, padx=12, pady=12)
        self.form_id = self.canvas.create_window((0, 0), window=self.form, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.form.grid_columnconfigure(1, weight=1)
        self.form.bind("<Configure>", self._sync_scroll_region)
        self.canvas.bind("<Configure>", self._sync_form_width)

    def _build_rows(self) -> None:
        self._form()
        win = self._window()
        self.diagnosis_popup = DialogDiagnosisPopup(win, self.app.root, language_id=self.app._diagnosis_language() if hasattr(self.app, "_diagnosis_language") else "ru")
        for row, field in enumerate(self.missing):
            self._build_label(row, field)
            if _is_labs_field(field):
                self._build_labs_row(row, field)
            else:
                self._build_entry_row(row, field)

    def _build_label(self, row: int, field: Any) -> None:
        form = self._form()
        tk.Label(
            form,
            text=field.label,
            bg=PANEL,
            fg=TEXT,
            font=self.app._font(9, "bold"),
            anchor="w",
            justify="left",
            wraplength=220,
        ).grid(row=row, column=0, sticky="nw", padx=(0, 10), pady=(0, 10))

    def _build_entry_row(self, row: int, field: Any) -> None:
        form = self._form()
        var = tk.StringVar(value=field.value or "")
        self.variables[field.key] = var
        entry = tk.Entry(form, textvariable=var, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat", font=self.app._font(10))
        entry.grid(row=row, column=1, sticky="ew", ipady=5, pady=(0, 10))
        self.entries[field.key] = entry
        if _is_diagnosis_field(field) and self.diagnosis_popup is not None:
            self.diagnosis_popup.attach(entry, var)

    def _build_labs_row(self, row: int, field: Any) -> None:
        form = self._form()
        box_frame = tk.Frame(form, bg=PANEL)
        box_frame.grid(row=row, column=1, sticky="ew", pady=(0, 10))
        box_frame.grid_columnconfigure(0, weight=1)
        widget = tk.Text(box_frame, height=7, wrap="word", bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat", font=self.app._font(10), padx=8, pady=8)
        if field.value:
            widget.insert("1.0", str(field.value))
        widget.grid(row=0, column=0, sticky="ew")
        self.text_widgets[field.key] = widget
        self.entries[field.key] = widget
        tools = tk.Frame(box_frame, bg=PANEL)
        tools.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        tk.Button(tools, text="Нет анализов", command=lambda target=widget: self._mark_no_labs(target), bg=PANEL_3, fg=TEXT, relief="flat", padx=10, pady=5, font=self.app._font(9, "bold")).pack(side="left")

    def _build_buttons(self) -> None:
        win = self._window()
        buttons = tk.Frame(win, bg=DEEP)
        buttons.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)
        tk.Button(buttons, text="Сохранить и продолжить", command=self._save, bg=ACCENT_2, fg="#03101f", relief="flat", padx=10, pady=8, font=self.app._font(9, "bold")).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        tk.Button(buttons, text="Отмена", command=self._cancel, bg=PANEL_3, fg=TEXT, relief="flat", padx=10, pady=8, font=self.app._font(9, "bold")).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def _bind_window(self) -> None:
        win = self._window()
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            win.bind(sequence, self._on_mousewheel)
        win.bind("<Escape>", lambda _event: self._cancel())
        win.protocol("WM_DELETE_WINDOW", self._cancel)
        win.transient(self.app.root)
        win.grab_set()

    def _save(self) -> None:
        values: dict[str, str] = {}
        for field in self.missing:
            normalized = self._validate_field(field)
            if normalized is None:
                return
            values[field.key] = normalized
        for key, value in values.items():
            if not self._store_value(key, value):
                return
        self.app._allow_missing_required_creation = False
        self.result["action"] = "save"
        self._close()

    def _validate_field(self, field: Any) -> str | None:
        raw = self._value_for(field.key)
        if not raw:
            self._warn_and_focus(field.key, "Не заполнено поле", f"Заполните поле: {field.label}")
            return None
        if _is_semantic_date_field(field):
            return self._validate_date(field, raw)
        if _is_diagnosis_field(field):
            return self._validate_diagnosis(field, raw)
        if _is_case_number_field(field):
            return self._validate_case_number(field, raw)
        return raw

    def _validate_date(self, field: Any, raw: str) -> str | None:
        normalized = self.app._normalize_date_for_ui(raw) if hasattr(self.app, "_normalize_date_for_ui") else raw
        if not parse_date(normalized):
            self._warn_and_focus(field.key, "Некорректная дата", f"Проверьте поле: {field.label}")
            return None
        if _is_discharge_date_field(field) and hasattr(self.app, "_date_is_not_before_admission"):
            if not self.app._date_is_not_before_admission(normalized):
                self._warn_and_focus(field.key, "Некорректная дата", "Дата выписки не может быть раньше даты поступления.")
                return None
        self._set_value_for(field.key, normalized)
        return normalized

    def _validate_diagnosis(self, field: Any, raw: str) -> str | None:
        normalized = normalize_required_diagnosis_with_icd10(raw, language_id=self.app._diagnosis_language() if hasattr(self.app, "_diagnosis_language") else "ru")
        if not normalized:
            self._warn_and_focus(field.key, "Некорректный диагноз", "Выберите диагноз из МКБ-10 или укажите шифр с буквой класса, например K35 или I10.")
            return None
        self._set_value_for(field.key, normalized)
        return normalized

    def _validate_case_number(self, field: Any, raw: str) -> str | None:
        sanitized = sanitize_case_number_candidate(raw, patient_name=self._patient_name_for_guard())
        if not sanitized:
            self._warn_and_focus(field.key, "Некорректный номер", "Проверьте поле: Номер истории болезни")
            return None
        self._set_value_for(field.key, sanitized)
        return sanitized

    def _store_value(self, field_key: str, value: str) -> bool:
        field_ref = next((item for item in self.missing if item.key == field_key), None)
        store_key = _store_key_for_field(field_ref) if field_ref is not None else field_key
        if field_ref is not None and _is_labs_field(field_ref) and self._is_without_labs_text(value):
            self._store_no_labs_value()
            return True
        if field_ref is not None and _is_semantic_date_field(field_ref):
            date_key = _semantic_date_store_key_for_field(field_ref) or store_key
            if date_key == "discharge_date" and hasattr(self.app, "_store_discharge_date_value"):
                if not self.app._store_discharge_date_value(value, parent=self._window(), source_label="popup обязательных полей"):
                    self._warn_and_focus(field_key, "Уточнить дату", "Дата выписки отличается от уже сохранённой. Подтвердите замену или исправьте поле.")
                    return False
                return True
            if hasattr(self.app, "_store_popup_date_value"):
                label = str(getattr(field_ref, "label", "") or date_key)
                if not self.app._store_popup_date_value(date_key, value, parent=self._window(), source_label=f"popup обязательных полей: {label}"):
                    self._warn_and_focus(field_key, "Уточнить дату", "Проверьте дату или подтвердите замену уже сохранённого значения.")
                    return False
                return True
            store_key = date_key
        self.app._store_required_review_value(store_key, value)
        return True

    def _store_no_labs_value(self) -> None:
        try:
            if hasattr(self.app, "labs_without_var"):
                self.app.labs_without_var.set(True)
            if hasattr(self.app, "labs_text_var"):
                self.app.labs_text_var.set("")
            if hasattr(self.app, "labs_source_path_var"):
                self.app.labs_source_path_var.set("")
            if hasattr(self.app, "_labs_date_policy"):
                self.app._labs_date_policy = "without_labs"
            self.app._store_required_review_value("labs", "Нет анализов")
        except Exception as exc:
            record_soft_exception("actions_required_fields_popup.store_no_labs", exc)

    def _warn_and_focus(self, key: str, title: str, text: str) -> None:
        win = self._window()
        messagebox.showwarning(title, text, parent=win)
        self._focus(key)

    def _focus(self, field_key: str) -> None:
        try:
            widget = self.entries[field_key]
            widget.focus_set()
            if isinstance(widget, tk.Entry):
                widget.selection_range(0, "end")
        except Exception as exc:
            record_soft_exception("actions_required_fields_popup.focus", exc, detail=field_key)

    def _focus_first(self) -> None:
        try:
            if self.missing:
                self.entries[self.missing[0].key].focus_set()
        except Exception as exc:
            record_soft_exception("actions_required_fields_popup.initial_focus", exc)

    def _value_for(self, field_key: str) -> str:
        widget = self.text_widgets.get(field_key)
        if widget is not None:
            return widget.get("1.0", "end").strip()
        var = self.variables.get(field_key)
        return var.get().strip() if var is not None else ""

    def _set_value_for(self, field_key: str, value: str) -> None:
        widget = self.text_widgets.get(field_key)
        if widget is not None:
            widget.delete("1.0", "end")
            widget.insert("1.0", value)
            return
        var = self.variables.get(field_key)
        if var is not None:
            var.set(value)

    def _patient_name_for_guard(self) -> str:
        try:
            if hasattr(self.app, "_patient_name_for_case_number_guard"):
                return str(self.app._patient_name_for_case_number_guard())
        except Exception as exc:
            record_soft_exception("actions_required_fields_popup.patient_name_guard", exc)
        try:
            return self.app.patient_name_var.get().strip() if hasattr(self.app, "patient_name_var") else ""
        except Exception as exc:
            record_soft_exception("actions_required_fields_popup.patient_name_var", exc)
            return ""

    def _close(self) -> None:
        if self.win is None:
            return
        try:
            self.win.grab_release()
        except Exception as exc:
            record_soft_exception("actions_required_fields_popup.grab_release", exc)
        try:
            if self.diagnosis_popup is not None:
                self.diagnosis_popup.hide()
        except Exception as exc:
            record_soft_exception("actions_required_fields_popup.diagnosis_hide", exc)
        try:
            self.win.withdraw()
        except Exception as exc:
            record_soft_exception("actions_required_fields_popup.withdraw", exc)
        self.win.destroy()

    def _cancel(self) -> None:
        self.app._allow_missing_required_creation = False
        self.result["action"] = "cancel"
        self._close()

    def _sync_scroll_region(self, _event=None) -> None:
        try:
            if self.canvas is not None:
                self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except Exception as exc:
            record_soft_exception("actions_required_fields_popup.scroll_region", exc)

    def _sync_form_width(self, event) -> None:
        try:
            if self.canvas is not None and self.form_id is not None:
                self.canvas.itemconfigure(self.form_id, width=max(event.width, 1))
        except Exception as exc:
            record_soft_exception("actions_required_fields_popup.form_width", exc)

    def _on_mousewheel(self, event) -> None:
        try:
            delta = -1 if getattr(event, "delta", 0) > 0 else 1
            if getattr(event, "num", None) == 4:
                delta = -1
            elif getattr(event, "num", None) == 5:
                delta = 1
            if self.canvas is not None:
                self.canvas.yview_scroll(delta, "units")
        except Exception as exc:
            record_soft_exception("actions_required_fields_popup.mousewheel", exc)

    def _mark_no_labs(self, target: tk.Text) -> None:
        target.delete("1.0", "end")
        target.insert("1.0", "Нет анализов")
        try:
            target.focus_set()
        except Exception as exc:
            record_soft_exception("actions_required_fields_popup.labs_focus", exc)

    @staticmethod
    def _is_without_labs_text(value: str) -> bool:
        normalized = " ".join((value or "").replace("ё", "е").lower().split())
        return normalized in NO_LABS_VALUES
