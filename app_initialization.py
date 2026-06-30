from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tkinter as tk
from typing import Dict, List

from app_config import DEEP
from diary_constants import DIARY_KIND
from diagnostic_logging import record_soft_exception
from medical_constants import DOCUMENT_ORDER
from medical_models import PatientData
from medical_word_format import ensure_docx_compatible


class _LazyMedicalDocumentService:
    __slots__ = ("_service",)

    def __init__(self) -> None:
        self._service = None

    def _get(self):
        if self._service is None:
            from medical_service import MedicalDocumentService
            self._service = MedicalDocumentService()
        return self._service

    def __getattr__(self, name: str):
        return getattr(self._get(), name)


class AppInitializationMixin:
    def _initialize_app(self, root: tk.Tk) -> None:
        self._init_core_state(root)
        self._init_primary_and_expert_state()
        self._init_document_detail_state()
        self._init_key_field_undo_state()
        self._init_medical_output_state()
        self._init_diary_state()
        self._init_desktop_intake_state()
        self._init_runtime_visual_state()
        self._configure_root_window()
        self._bootstrap_ui()

    def _primary_document_cache_signature(self, path: Path) -> tuple[int, int, str]:
        try:
            stat = path.stat()
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() and path.is_file() else ""
            return (int(stat.st_mtime_ns), int(stat.st_size), digest)
        except Exception as exc:
            record_soft_exception("app_initialization.primary_signature", exc, detail=str(path))
            return (0, -1, "")

    def _parse_primary_document(self, path: str | Path) -> PatientData:
        p = Path(path)
        key = str(p.resolve()) if p.exists() else str(p)
        signature = self._primary_document_cache_signature(p)
        cached = self._primary_parse_cache.get(key)
        if cached and cached[0] == signature:
            return copy.deepcopy(cached[1])
        parse_path = ensure_docx_compatible(p, label="primary document")
        data = self.service.parse_primary_document(parse_path)
        self._primary_parse_cache[key] = (signature, copy.deepcopy(data))
        if len(self._primary_parse_cache) > 3:
            for old_key in list(self._primary_parse_cache)[:-3]:
                self._primary_parse_cache.pop(old_key, None)
        return data

    def _init_core_state(self, root: tk.Tk) -> None:
        self.root = root
        self.service = _LazyMedicalDocumentService()
        self._primary_parse_cache: dict[str, tuple[tuple[int, int, str], PatientData]] = {}
        self._diary_template_files_cache: dict[tuple[str, int], list[Path]] = {}
        self._diary_template_day_cache: dict[tuple[str, int, int], int | None] = {}
        self._diary_template_folder_contains_cache: dict[tuple[str, int], bool] = {}
        self.data = PatientData()
        self._last_patient_case_review = None
        self._hotkey_print_after = False
        self.patient_name_var = tk.StringVar()
        self.admission_date_var = tk.StringVar()
        self.discharge_date_var = tk.StringVar()
        self.diagnosis_var = tk.StringVar()
        self._popup_diagnosis_override = ""
        self._popup_discharge_date_override = ""
        self._semantic_date_state: dict[str, str] = {}
        self.output_dir_var = tk.StringVar()
        self._suspend_output_dir_tracking = False
        self._manual_output_dir = False
        self._output_dir_auto_locked_to_patient = False
        self.output_dir_var.trace_add("write", lambda *_: self._mark_manual_output_dir())
        self.printer_var = tk.StringVar()
        self.available_printers: list[str] = []
        self._printer_refresh_in_progress = False
        self._settings_path = self._get_settings_path()
        self._settings = self._load_settings()
        from language_preferences import LanguagePreferences
        self._language_preferences = LanguagePreferences.from_settings(self._settings.get("language"))
        self.ui_language_var = tk.StringVar(value=self._language_preferences.ui_language)
        self.document_language_var = tk.StringVar(value=self._language_preferences.document_language)
        self.output_language_var = tk.StringVar(value=self._language_preferences.output_language)
        self.spellcheck_enabled_var = tk.BooleanVar(value=self._language_preferences.spellcheck_enabled)

    def _init_primary_and_expert_state(self) -> None:
        self.primary_document_type_var = tk.StringVar(value="primary_exam")
        self.primary_document_type_display_var = tk.StringVar(value="Первичный осмотр")
        self.assigned_treatment_var = tk.StringVar()
        self.case_number_var = tk.StringVar()
        self.expert_work_status_var = tk.StringVar()
        self.expert_work_org_var = tk.StringVar()
        self.expert_position_var = tk.StringVar()
        self.expert_sick_leave_needed_var = tk.StringVar(value="нет")
        self.expert_sick_leave_from_var = tk.StringVar()
        self.expert_sick_leave_number_var = tk.StringVar()
        self.expert_sick_leave_display_var = tk.StringVar(value="нет")
        self._primary_work_org_default = ""
        self._primary_work_position_default = ""
        self._work_details_manually_edited = False
        self._suspend_user_edit_tracking = False
        self._manual_patient_name = False
        self._manual_admission_date = False
        self._manual_discharge_date = False
        self._manual_diagnosis = False
        self.patient_name_var.trace_add("write", lambda *_: self._mark_manual_field("patient_name"))
        self.admission_date_var.trace_add("write", lambda *_: self._mark_manual_field("admission_date"))
        self.discharge_date_var.trace_add("write", self._on_discharge_date_var_changed)
        self.diagnosis_var.trace_add("write", lambda *_: self._mark_manual_field("diagnosis"))

    def _init_document_detail_state(self) -> None:
        self.rvk_act_number_var = tk.StringVar()
        default_rvk = ""
        try:
            defaults_raw = self._settings.get("defaults") if isinstance(getattr(self, "_settings", None), dict) else {}
            if isinstance(defaults_raw, dict):
                default_rvk = str(defaults_raw.get("rvk_military_commissariat", "") or "").strip()
        except Exception as exc:
            record_soft_exception("app_initialization.default_rvk", exc)
        self.rvk_military_commissariat_var = tk.StringVar(value=default_rvk)
        self.rvk_work_position_var = tk.StringVar()
        self.vk_date_var = tk.StringVar()
        self.vk_protocol_number_var = tk.StringVar()
        self.vk_protocol_date_var = tk.StringVar()
        self.vk_mse_work_org_var = tk.StringVar()
        self.vk_mse_position_var = tk.StringVar()
        self.sick_leave_vk_date_var = tk.StringVar()
        self.sick_leave_vk_protocol_number_var = tk.StringVar()
        self.sick_leave_vk_protocol_date_var = tk.StringVar()
        self.sick_leave_vk_commission_date_var = tk.StringVar()
        self.sick_leave_vk_work_org_var = tk.StringVar()
        self.sick_leave_vk_position_var = tk.StringVar()
        self.sick_leave_vk_work_position_var = tk.StringVar()
        self.labs_without_var = tk.BooleanVar(value=False)
        self.labs_text_var = tk.StringVar()
        self.labs_source_path_var = tk.StringVar()
        self.labs_explicit_date_var = tk.StringVar()
        self.labs_date_policy_var = tk.StringVar(value="preserve_found_dates")
        self.diary_treatment_correction_var = tk.StringVar()
        self._auto_fill_default_work_targets()

    def _init_key_field_undo_state(self) -> None:
        self._key_field_history: dict[str, list[str]] = {}
        self._key_field_future: dict[str, list[str]] = {}

    def _init_medical_output_state(self) -> None:
        self.output_vars: Dict[str, tk.BooleanVar] = {kind: tk.BooleanVar(value=False) for kind in DOCUMENT_ORDER}
        self.output_vars[DIARY_KIND] = tk.BooleanVar(value=False)

    def _init_diary_state(self) -> None:
        self.status_files: List[str] = []
        self.diary_files: List[str] = []
        self._diary_files_auto_selected = False
        self._diary_text_files_auto_selected = False
        self._diary_text_output_enabled = False
        self.diary_texts_dir = ""
        self.diary_template_dir = ""
        self.repeat_statuses_var = tk.BooleanVar(value=True)
        self.reset_each_file_var = tk.BooleanVar(value=True)
        self.keep_signature_var = tk.BooleanVar(value=True)
        self.fill_months_var = tk.BooleanVar(value=True)
        self.force_final_diary_var = tk.BooleanVar(value=True)
        self.remove_holiday_rows_var = tk.BooleanVar(value=True)
        self.diary_frequency_mode_var = tk.StringVar(value="daily")

    def _init_desktop_intake_state(self) -> None:
        self._desktop_intake_seen: set[str] = set()
        self._desktop_intake_poll_after_id: str | None = None
        self._desktop_intake_last_prompt_signature = ""
        self._desktop_intake_agent_installed = False
        self._desktop_intake_agent_started = False

    def _init_runtime_visual_state(self) -> None:
        self._log_lines: list[str] = []
        self._is_dark = False
        self._current_theme = DEEP
        self._creation_in_progress = False
        self._allow_missing_required_creation = False
        self._active_patient_output_dir: Path | None = None
        self._preview_after_id: str | None = None
        self._preview_cache_key: str = ""
        self._manual_preview_text: str = ""
        self._setup_mode = "primary"
