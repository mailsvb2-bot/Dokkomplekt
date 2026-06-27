from __future__ import annotations

from datetime import datetime
from tkinter import messagebox


from medical_constants import DATE_FMT
from medical_formatting import parse_date
from medical_date_state import (
    apply_semantic_date,
    clear_semantic_date,
    current_semantic_date,
    date_conflict,
    normalize_date_value,
    semantic_date_label,
    canonical_date_key,
)


class DialogDatesMixin:
    def _today_str(self) -> str:
        return datetime.now().strftime(DATE_FMT)

    def _normalize_date_for_ui(self, value: str) -> str:
        parsed = parse_date(value)
        return parsed.strftime(DATE_FMT) if parsed else (value or "").strip()



    def _normalize_required_date_for_ui(self, value: str, label: str) -> str | None:
        """Normalize a required user-entered date or warn and reject it.

        Several popup contracts store dates that later go directly into DOCX
        headers. A non-empty but invalid value must not pass as plain text.
        """
        raw = (value or "").strip()
        parsed = parse_date(raw)
        if not parsed:
            messagebox.showwarning(
                "Некорректная дата",
                f"{label} должна быть в формате ДД.ММ.ГГГГ, ДДММГГГГ, ДДММГГ или коротко ДМГГ.",
            )
            return None
        normalized = parsed.strftime(DATE_FMT)
        if not self._date_is_not_before_admission(normalized):
            messagebox.showwarning(
                "Некорректная дата",
                f"{label} не может быть раньше даты поступления.",
            )
            return None
        return normalized

    def _admission_date_for_validation(self) -> str:
        data = getattr(self, "data", None)
        data_value = getattr(data, "admission_date", "") if data is not None else ""
        ui_var = getattr(self, "admission_date_var", None)
        ui_value = ui_var.get().strip() if ui_var is not None else ""
        return (data_value or ui_value or "").strip()

    def _date_is_not_before_admission(self, value: str) -> bool:
        admission_value = self._admission_date_for_validation()
        if not admission_value or not value:
            return True
        admission = parse_date(admission_value)
        parsed = parse_date(value)
        if not admission or not parsed:
            return True
        return parsed.date() >= admission.date()


    def _current_semantic_date_value(self, key: str) -> str:
        """Return the accepted patient-level date for all UI/popups/renderers."""
        return current_semantic_date(self, key)

    def _clear_semantic_date_value(self, key: str) -> None:
        clear_semantic_date(self, key)

    def _confirm_semantic_date_conflict(self, conflict, *, parent=None) -> bool:
        """Ask the doctor before replacing a previously accepted patient date."""
        source = f"\nИсточник нового значения: {conflict.source_label}." if conflict.source_label else ""
        return bool(messagebox.askyesno(
            "Уточнить дату",
            (
                f"В программе уже сохранена {conflict.label.lower()}: {conflict.existing}.\n\n"
                f"В текущем popup введена другая дата: {conflict.candidate}.{source}\n\n"
                f"Считать правильной дату {conflict.candidate} и заменить её во всех создаваемых документах?\n\n"
                "Да — заменить общую дату.\n"
                "Нет — оставить прежнюю дату и вернуться к полю, чтобы исправить ввод."
            ),
            parent=parent,
        ))

    def _store_semantic_date_value(
        self,
        key: str,
        value: str,
        *,
        parent=None,
        source_label: str = "popup",
        confirm_conflict: bool = True,
    ) -> bool:
        """Normalize, conflict-check and store a patient-level date.

        This is the date contract between program and UI.  Dialogs may ask the
        same field several times, but they are no longer allowed to silently
        overwrite one another.
        """
        canonical = canonical_date_key(key)
        normalized = normalize_date_value(value)
        if not normalized:
            return False
        # Every patient-event date typed in a popup must live inside the current
        # hospitalization episode.  Admission itself is the lower boundary.
        if canonical != "admission_date" and not self._date_is_not_before_admission(normalized):
            return False
        if confirm_conflict:
            conflict = date_conflict(self, canonical, normalized, source_label=source_label)
            if conflict is not None and not self._confirm_semantic_date_conflict(conflict, parent=parent):
                return False
        applied = apply_semantic_date(self, canonical, normalized)
        if canonical == "discharge_date" and hasattr(self, "_refresh_discharge_date_visual"):
            try:
                self._refresh_discharge_date_visual()
            except Exception as exc:
                from diagnostic_logging import record_soft_exception
                record_soft_exception("dialog_dates.refresh_discharge_after_store", exc)
        return bool(applied)

    def _store_popup_date_value(
        self,
        key: str,
        value: str,
        *,
        parent=None,
        source_label: str = "popup",
        confirm_conflict: bool = True,
    ) -> bool:
        """Store any popup-owned date through the semantic date contract."""
        return self._store_semantic_date_value(
            key,
            value,
            parent=parent,
            source_label=source_label,
            confirm_conflict=confirm_conflict,
        )

    def _current_popup_date_value(self, key: str) -> str:
        return self._current_semantic_date_value(key)

    def _on_discharge_date_field_commit(self, _event=None) -> None:
        """Commit manual «Дата выписки» input as the global discharge date.

        A manually typed value such as ``1126`` is normalized to ``01.01.2026``
        on focus loss/Enter and then reused by both the discharge epicrisis and
        diary termination logic. Invalid partial input is left untouched until
        creation-time validation.
        """
        value = self.discharge_date_var.get().strip() if hasattr(self, "discharge_date_var") else ""
        if not value:
            self._clear_semantic_date_value("discharge_date")
            if hasattr(self, "_refresh_discharge_date_visual"):
                self._refresh_discharge_date_visual()
            return None
        if not self._store_semantic_date_value(
            "discharge_date",
            value,
            source_label="поле даты выписки в основном окне",
            confirm_conflict=False,
        ):
            return None
        return None

    def _default_committee_date(self) -> str:
        """Без межоконного копирования дат: новое popup-окно стартует с текущей даты."""
        return self._today_str()

    def _default_protocol_date(self, fallback: str | None = None) -> str:
        """Дата протокола может наследовать дату только внутри того же popup."""
        return (fallback or "").strip() or self._today_str()

    def _remember_committee_dates(self, *, committee_date: str | None = None, protocol_date: str | None = None) -> None:
        """Ничего не запоминаем между разными popup-окнами.

        Раньше дата, введённая в одном окне, подставлялась в другие окна
        комиссии/ВК. Это давало неверные документы, когда, например,
        совместный осмотр был 11.05.2026, а РВК/ВК — 12.05.2026.
        """
        return None
