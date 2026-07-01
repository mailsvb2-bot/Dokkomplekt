from __future__ import annotations

"""Cross-layer regression guards for doctor-confirmed UI/popup state.

The project intentionally has several layers that can all carry patient data:
Tk variables, PatientData, semantic date state and the universal medpack case.
This mixin keeps the doctor-confirmed overlay as the final source of truth for
known high-risk regressions without restoring bundled templates or narrow
medical defaults.
"""

from typing import Any

from diagnostic_logging import record_soft_exception
from medical_date_state import current_semantic_date
from medical_formatting import parse_date


def _not_working_value(value: str) -> bool:
    normalized = " ".join(str(value or "").strip().lower().replace("ё", "е").split())
    return normalized in {
        "",
        "нет",
        "не работает",
        "безработный",
        "безработная",
        "неработающий",
        "неработающая",
    }


class RegressionStateOverlayMixin:
    """Protect popup/UI values from scanner/profile overwrites."""

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
                if hasattr(self, "vk_mse_work_position_var"):
                    self.vk_mse_work_position_var.set("")
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
                    stored = bool(self._store_popup_date_value(
                        "admission_date",
                        normalized,
                        source_label="doctor-confirmed admission date",
                        confirm_conflict=False,
                    ))
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
                if hasattr(self, "vk_mse_work_position_var"):
                    self.vk_mse_work_position_var.set(value)
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
            if hasattr(self, "vk_mse_work_position_var"):
                self.vk_mse_work_position_var.set("")
        except Exception as exc:
            record_soft_exception("regression_state_overlay.reset_vk_mse_work_position", exc)
        return result

    def _vk_mse_details_complete(self) -> bool:
        dates = (
            current_semantic_date(self, "vk_date"),
            current_semantic_date(self, "vk_protocol_date"),
        )
        try:
            work_org = self.vk_mse_work_org_var.get().strip()
            position = self.vk_mse_position_var.get().strip()
            combined = self.vk_mse_work_position_var.get().strip() if hasattr(self, "vk_mse_work_position_var") else ""
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
            combined = ""
            if hasattr(self, "vk_mse_work_position_var"):
                combined = self.vk_mse_work_position_var.get().strip()
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
            # If a selected custom template explicitly needs combined VK/MSE work
            # position, keep the full VK/MSE popup chain active even when the
            # button name was edited by the doctor and no longer contains MSE words.
            pack = self._load_or_create_universal_pack()
            selected = {str(item).strip() for item in selected_custom_ids if str(item).strip()}
            for document in tuple(getattr(pack, "documents", ()) or ()):  # type: ignore[arg-type]
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
