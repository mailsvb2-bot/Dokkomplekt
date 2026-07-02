from __future__ import annotations

import tkinter as tk

from settings_mixin import SettingsMixin
from window_mixin import WindowMixin
from layout_mixin import LayoutMixin
from dialogs_mixin import DialogsMixin
from files_mixin import FilesMixin
from dnd_mixin import DragDropMixin
from actions_mixin import ActionsMixin
from app_initialization import AppInitializationMixin
from desktop_intake_mixin import DesktopIntakeMixin
from ui_cards import UiCardsMixin
from ui_icons import UiIconsMixin
from ui_buttons import UiButtonsMixin
from ui_fields import UiFieldsMixin
from diagnosis_widget import DiagnosisWidgetMixin
from ui_file_rows import UiFileRowsMixin
from diary_template_discovery import DiaryTemplateDiscoveryMixin
from diary_template_selection import DiaryTemplateSelectionMixin
from product_access import ProductAccessMixin, ProductLicenseMixin
from product_access_native import NativeProductAccessMixin
from diagnostic_logging import record_soft_exception
from medical_date_state import current_semantic_date
from medical_formatting import parse_date


def _not_working_value(value: str) -> bool:
    normalized = " ".join(str(value or "").strip().lower().replace("ё", "е").split())
    return normalized in {"", "нет", "не работает", "безработный", "безработная", "неработающий", "неработающая"}


class RegressionStateOverlayMixin:
    def _auto_select_numbered_diary_template(self, *, ask_folder: bool = False) -> bool:
        """Do not auto-pick legacy 01-31 date DOCX files for the new diary flow."""
        if not ask_folder:
            return False
        return super()._auto_select_numbered_diary_template(ask_folder=ask_folder)  # type: ignore[misc]

    def choose_diary_files(self) -> None:
        """The Dates button now confirms the program calendar principle.

        Old date-template DOCX files remain supported through lower-level
        compatibility paths, but the visible production flow no longer requires a
        date template: the doctor confirms how to compose diary dates in a popup.
        """
        try:
            from diary_constants import DIARY_KIND
            from diary_creation_wizard import prompt_diary_calendar_principle
            if not prompt_diary_calendar_principle(self):
                return None
            try:
                self.output_vars[DIARY_KIND].set(True)
            except Exception as exc:
                record_soft_exception("app.diary_calendar_select_output", exc)
            try:
                self._update_diary_template_label(success=True)
                self._redraw_selection_controls()
            except Exception as exc:
                record_soft_exception("app.diary_calendar_refresh_ui", exc)
            try:
                if hasattr(self, "_update_selected_outputs_status"):
                    self._update_selected_outputs_status()
            except Exception as exc:
                record_soft_exception("app.diary_calendar_status", exc)
            try:
                self._log("\n✅ Принцип дат дневников подтверждён: календарь программы, без обязательного шаблона дат.\n")
            except Exception as exc:
                record_soft_exception("app.diary_calendar_log", exc)
            return None
        except Exception as exc:
            record_soft_exception("app.choose_diary_calendar_principle", exc)
            return super().choose_diary_files()  # type: ignore[misc]

    def _diary_template_label_text(self) -> str:
        if not getattr(self, "diary_files", None) and not getattr(self, "diary_template_dir", ""):
            principle = str(getattr(self, "_doctor_confirmed_diary_principle", "") or "календарь программы: +1 день")
            text = "Даты: " + principle
            try:
                return self._truncate_label_text(text, max_chars=42 if getattr(self, "_compact_ui", False) else 78)
            except Exception as exc:
                record_soft_exception("app.diary_calendar_label", exc)
                return text
        return super()._diary_template_label_text()  # type: ignore[misc]

    def _vk_mse_work_position_value(self) -> str:
        if hasattr(self, "vk_mse_work_position_var"):
            return self.vk_mse_work_position_var.get().strip()
        return str(getattr(self, "_vk_mse_work_position_value_cache", "") or "").strip()

    def _set_vk_mse_work_position_value(self, value: str) -> None:
        value = str(value or "").strip()
        if hasattr(self, "vk_mse_work_position_var"):
            self.vk_mse_work_position_var.set(value)
        self._vk_mse_work_position_value_cache = value

    def _clear_required_review_value(self, key: str) -> None:
        if key == "admission_date":
            try:
                if hasattr(self, "_clear_semantic_date_value"):
                    self._clear_semantic_date_value("admission_date")
                else:
                    self._set_ui_var(self.admission_date_var, "")
                    self._manual_admission_date = False
                    data = getattr(self, "data", None)
                    if data is not None:
                        data.admission_date = ""
                return
            except Exception as exc:
                record_soft_exception("regression_state_overlay.clear_admission_date", exc)
        if key == "vk_mse_work_position":
            try:
                self._set_vk_mse_work_position_value("")
                data = getattr(self, "data", None)
                if data is not None:
                    setattr(data, "vk_mse_work_position", "")
                return
            except Exception as exc:
                record_soft_exception("regression_state_overlay.clear_vk_mse_work_position", exc)
        return super()._clear_required_review_value(key)  # type: ignore[misc]

    def _store_required_review_value(self, key: str, value: str) -> None:
        value = str(value or "").strip()
        if key == "admission_date":
            if not value:
                self._clear_required_review_value(key)
                return
            try:
                normalized = self._normalize_date_for_ui(value) if hasattr(self, "_normalize_date_for_ui") else value
                parsed = parse_date(normalized)
                if parsed:
                    normalized = parsed.strftime("%d.%m.%Y")
                stored = False
                if hasattr(self, "_store_popup_date_value"):
                    stored = bool(self._store_popup_date_value("admission_date", normalized, source_label="doctor-confirmed admission date", confirm_conflict=False))
                if not stored:
                    self._set_ui_var(self.admission_date_var, normalized)
                    self._manual_admission_date = True
                    data = getattr(self, "data", None)
                    if data is not None:
                        data.admission_date = normalized
                return
            except Exception as exc:
                record_soft_exception("regression_state_overlay.store_admission_date", exc, detail=value[:120])
        if key == "vk_mse_work_position":
            if not value:
                self._clear_required_review_value(key)
                return
            try:
                self._set_vk_mse_work_position_value(value)
                data = getattr(self, "data", None)
                if data is not None:
                    setattr(data, "vk_mse_work_position", value)
                return
            except Exception as exc:
                record_soft_exception("regression_state_overlay.store_vk_mse_work_position", exc, detail=value[:120])
        return super()._store_required_review_value(key, value)  # type: ignore[misc]

    def _reset_primary_document_runtime_state(self) -> None:
        result = super()._reset_primary_document_runtime_state()  # type: ignore[misc]
        try:
            self._set_vk_mse_work_position_value("")
        except Exception as exc:
            record_soft_exception("regression_state_overlay.reset_vk_mse_work_position", exc)
        try:
            self._doctor_confirmed_diary_day_offsets = ()
            self._doctor_confirmed_diary_hour_offsets = ()
            self._doctor_confirmed_diary_principle = ""
            if hasattr(self, "diary_calendar_principle_var"):
                self.diary_calendar_principle_var.set("")
        except Exception as exc:
            record_soft_exception("regression_state_overlay.reset_diary_calendar", exc)
        return result

    def _vk_mse_details_complete(self) -> bool:
        dates = (current_semantic_date(self, "vk_date"), current_semantic_date(self, "vk_protocol_date"))
        try:
            work_org = self.vk_mse_work_org_var.get().strip()
            position = self.vk_mse_position_var.get().strip()
            combined = self._vk_mse_work_position_value()
            if not all([*dates, self.vk_protocol_number_var.get().strip(), work_org]):
                return False
            if not _not_working_value(work_org) and not (position or combined):
                return False
            return all(self._popup_date_value_is_valid_and_in_episode(value) for value in dates)
        except Exception as exc:
            record_soft_exception("regression_state_overlay.vk_mse_details_complete", exc)
            return False

    def _confirmed_universal_overlay_values(self) -> dict[str, str]:
        values: dict[str, str] = dict(super()._confirmed_universal_overlay_values())  # type: ignore[misc]
        try:
            combined = self._vk_mse_work_position_value()
            if not combined:
                work = values.get("vk_mse.work", "").strip()
                position = values.get("vk_mse.position", "").strip()
                combined = ", ".join(part for part in (work, position) if part)
            if combined:
                values["vk_mse.work_position"] = combined
        except Exception as exc:
            record_soft_exception("regression_state_overlay.universal_vk_mse_work_position", exc)
        return values

    def _custom_requirement_flags(self, selected_custom_ids: list[str]) -> dict[str, bool]:
        flags: dict[str, bool] = dict(super()._custom_requirement_flags(selected_custom_ids))  # type: ignore[misc]
        try:
            pack = self._load_or_create_universal_pack()
            selected = {str(item).strip() for item in selected_custom_ids if str(item).strip()}
            for document in tuple(getattr(pack, "documents", ()) or ()):
                if selected and getattr(document, "id", "") not in selected:
                    continue
                required = " ".join(str(item or "") for item in tuple(getattr(document, "required_fields", ()) or ()))
                optional = " ".join(str(item or "") for item in tuple(getattr(document, "optional_fields", ()) or ()))
                signature = (required + " " + optional).lower().replace("_", ".")
                if "vk.mse.work.position" in signature or "vk_mse.work_position" in signature:
                    flags["vk_mse"] = True
                    flags["requires_case_number"] = True
            return flags
        except Exception as exc:
            record_soft_exception("regression_state_overlay.custom_requirement_flags", exc)
            return flags


class WidgetsMixin(UiCardsMixin, UiIconsMixin, UiButtonsMixin, UiFieldsMixin, DiagnosisWidgetMixin, UiFileRowsMixin):
    pass


class DiaryTemplateMixin(DiaryTemplateDiscoveryMixin, DiaryTemplateSelectionMixin):
    pass


class CombinedMedicalDiaryApp(
    RegressionStateOverlayMixin,
    NativeProductAccessMixin,
    ProductAccessMixin,
    ProductLicenseMixin,
    AppInitializationMixin,
    SettingsMixin,
    DesktopIntakeMixin,
    WindowMixin,
    LayoutMixin,
    DialogsMixin,
    WidgetsMixin,
    FilesMixin,
    DiaryTemplateMixin,
    DragDropMixin,
    ActionsMixin,
):
    def __init__(self, root: tk.Tk):
        self._initialize_app(root)
        try:
            self._product_license_button = tk.Label(root, text="License", cursor="hand2")
            self._product_license_button.bind("<Button-1>", lambda _event: self.show_product_license_dialog())
            self._product_license_button.place(relx=1.0, rely=1.0, x=-14, y=-14, anchor="se")
        except Exception as exc:
            record_soft_exception("app.license_button", exc)
