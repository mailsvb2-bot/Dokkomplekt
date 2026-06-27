from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tkinter as tk
from typing import Dict, List

from app_config import APP_TITLE, DEEP
from diary_constants import DIARY_KIND
from medical_constants import DOCUMENT_ORDER
from medical_models import PatientData
from diagnostic_logging import record_soft_exception


class _LazyMedicalDocumentService:
    """Create the DOCX service only when a file operation really needs it.

    Startup should paint the UI quickly. Importing python-docx/renderers/templates
    is deferred until the first primary-document parse or document generation.
    """
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
        """Return a cache signature that survives coarse Windows timestamps.

        The UI cache must be fast, but it must never reuse a parsed patient case
        after the doctor or Word has rewritten the primary DOCX.  Some Windows /
        cloud-synced folders round ``st_mtime_ns`` aggressively, and a same-size
        rewrite can therefore look unchanged if the cache only keys by
        modification time and file size.  A tiny full-file SHA-256 is still much
        cheaper than reparsing DOCX repeatedly and closes that live regression.
        """
        try:
            stat = path.stat()
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() and path.is_file() else ""
            return (int(stat.st_mtime_ns), int(stat.st_size), digest)
        except Exception as exc:
            record_soft_exception("app_initialization.primary_signature", exc, detail=str(path))
            return (0, -1, "")

    def _parse_primary_document(self, path: str | Path) -> PatientData:
        """Parse a primary DOCX with a small content-aware cache for UI responsiveness.

        Selecting a file, updating the preview, opening dialogs and creating files
        can ask for the same primary document several times. Re-reading DOCX each
        time makes the interface feel sticky. The cache is invalidated by
        modification time, size and content digest, then returns a deep copy so
        callers may safely mutate the PatientData for their own document flow.
        """
        p = Path(path)
        key = str(p.resolve()) if p.exists() else str(p)
        signature = self._primary_document_cache_signature(p)
        cached = self._primary_parse_cache.get(key)
        if cached and cached[0] == signature:
            return copy.deepcopy(cached[1])
        data = self.service.parse_primary_document(p)
        self._primary_parse_cache[key] = (signature, copy.deepcopy(data))
        # Keep cache tiny: the UI works with one current patient document.
        if len(self._primary_parse_cache) > 3:
            for old_key in list(self._primary_parse_cache)[:-3]:
                self._primary_parse_cache.pop(old_key, None)
        return data

    def _init_core_state(self, root: tk.Tk) -> None:
        """Implement the _init_core_state workflow with validation, UI state updates and diagnostics."""
        self.root = root
        self.service = _LazyMedicalDocumentService()
        self._primary_parse_cache: dict[str, tuple[tuple[int, int, str], PatientData]] = {}
        self._diary_template_files_cache: dict[tuple[str, int], list[Path]] = {}
        self._diary_template_day_cache: dict[tuple[str, int, int], int | None] = {}
        self._diary_template_folder_contains_cache: dict[tuple[str, int], bool] = {}
        self.data = PatientData()
        self._last_patient_case_review = None
        self._hotkey_print_after = False

        # Общая карточка пациента. ФИО в UI используется для названия файлов.
        # ФИО внутри документов всегда берётся из выбранного первичного документа.
        # На старте интерфейс всегда открывается «с чистого листа».
        # Никакие данные пациента, даты, диагноз, папка результата или принтер
        # не подставляются из прошлых запусков: пользователь явно выбирает файлы
        # и вводит/подтверждает значения для текущего пациента.
        self.patient_name_var = tk.StringVar()
        self.admission_date_var = tk.StringVar()
        self.discharge_date_var = tk.StringVar()
        self.diagnosis_var = tk.StringVar()
        # Диагноз и дата выписки, выбранные/введённые врачом в popup
        # направления, имеют абсолютный приоритет над данными, распознанными
        # из первичного DOCX. Особенно важно не дать повторному reparse_navigation()
        # заменить дату выписки датой поступления.
        self._popup_diagnosis_override = ""
        self._popup_discharge_date_override = ""
        # Accepted patient-level dates shared by every popup and renderer.
        # Prevents one dialog from silently using a different discharge date than another.
        self._semantic_date_state: dict[str, str] = {}
        self.output_dir_var = tk.StringVar()
        # Папка результата по умолчанию должна следовать за первичным
        # документом пациента. Ручной выбор через кнопку/ручной ввод
        # сохраняется и не перетирается автоматикой.
        self._suspend_output_dir_tracking = False
        self._manual_output_dir = False
        # True only for a folder that was chosen automatically for one detected
        # desktop-intake patient.  It prevents generation for that patient from
        # escaping the patient subfolder, but must be released when the next
        # primary document is selected so a new patient is not saved into the
        # previous patient's folder.
        self._output_dir_auto_locked_to_patient = False
        self.output_dir_var.trace_add("write", lambda *_: self._mark_manual_output_dir())

        # Печать: выбор принтера и сценарий "создать + сохранить + распечатать".
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
        # Тип входного первичного документа.
        # - направление на госпитализацию: номер истории болезни, лечение и
        #   диагноз подтверждаются вручную в popup;
        # - первичный осмотр: popup не открывается, данные берутся из DOCX.
        self.primary_document_type_var = tk.StringVar(value="primary_exam")
        self.primary_document_type_display_var = tk.StringVar(value="Первичный осмотр")
        self.assigned_treatment_var = tk.StringVar()
        self.case_number_var = tk.StringVar()

        # Экспертный анамнез / больничный лист.
        # Видимый старт всегда пустой: значения задаются врачом для текущего случая
        # через popup и затем идут в первичный осмотр, выписной эпикриз и комиссионный осмотр.
        self.expert_work_status_var = tk.StringVar()  # да/нет: работает ли пациент
        self.expert_work_org_var = tk.StringVar()
        self.expert_position_var = tk.StringVar()
        self.expert_sick_leave_needed_var = tk.StringVar(value="нет")  # да/нет
        self.expert_sick_leave_from_var = tk.StringVar()
        self.expert_sick_leave_number_var = tk.StringVar()
        self.expert_sick_leave_display_var = tk.StringVar(value="нет")
        self._primary_work_org_default = ""
        self._primary_work_position_default = ""
        self._work_details_manually_edited = False

        # Защита ручного ввода UI. Некоторые файлы умеют подтягивать ФИО/дату/диагноз
        # автоматически, но уже набранные врачом значения нельзя перетирать при выборе
        # направления, ЭПИ или таблиц дневников.
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
        # Ручные реквизиты для отдельных документов. В UI они не занимают место:
        # появляются маленькие окна при включении соответствующих галочек.
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
        # Старое объединённое поле оставлено как внутренний fallback/совместимость.
        self.sick_leave_vk_work_position_var = tk.StringVar()
        self.commission_date_var = tk.StringVar()
        self.commission_number_var = tk.StringVar()

        # Универсальный блок анализов для всех специальностей. Значения
        # живут в UI/профиле текущего случая и попадают как в старые встроенные
        # DOCX, так и в doctor-owned шаблоны через {{labs.results}}.
        self.labs_text_var = tk.StringVar()
        self.labs_source_path_var = tk.StringVar()
        self.labs_date_policy_var = tk.StringVar(value="preserve_found_dates")
        self.labs_explicit_date_var = tk.StringVar()
        self.labs_without_var = tk.BooleanVar(value=False)

        # Даты popup-окон ВК/комиссий не должны переноситься между разными
        # документами. Например, дата комиссионного осмотра и дата Акта/ВК
        # могут быть разными, поэтому каждое popup-окно хранит только своё
        # собственное значение. Эти поля оставлены пустыми как совместимость,
        # но больше не используются для межоконного автодублирования.
        self._last_committee_date = ""
        self._last_protocol_date = ""


    def _init_key_field_undo_state(self) -> None:
        """Keep a short Ctrl+Z history for patient fields that doctors edit manually."""
        self._field_undo_stack: dict[str, list[str]] = {}
        self._field_undo_last: dict[str, str] = {}
        self._field_undo_vars: dict[str, tk.StringVar] = {}
        self._field_undo_suspended = False
        for key, var in (
            ("patient_name", self.patient_name_var),
            ("admission_date", self.admission_date_var),
            ("discharge_date", self.discharge_date_var),
            ("diagnosis", self.diagnosis_var),
            ("case_number", self.case_number_var),
            ("treatment", self.assigned_treatment_var),
        ):
            self._register_undo_var(key, var)
        self.root.bind_all("<Control-z>", self._undo_last_key_field, add="+")
        self.root.bind_all("<Control-Z>", self._undo_last_key_field, add="+")

    def _register_undo_var(self, key: str, var: tk.StringVar) -> None:
        """Register one StringVar in the lightweight key-field undo stack."""
        self._field_undo_vars[key] = var
        self._field_undo_stack.setdefault(key, [])
        self._field_undo_last[key] = var.get()

        def _remember_previous(*_args) -> None:
            if getattr(self, "_field_undo_suspended", False):
                self._field_undo_last[key] = var.get()
                return
            previous = self._field_undo_last.get(key, "")
            current = var.get()
            if previous != current:
                stack = self._field_undo_stack.setdefault(key, [])
                if not stack or stack[-1] != previous:
                    stack.append(previous)
                    del stack[:-20]
                self._field_undo_last[key] = current

        var.trace_add("write", _remember_previous)

    def _undo_last_key_field(self, event=None) -> str | None:
        """Restore the previous value of the focused key input field."""
        focus = None
        try:
            focus = self.root.focus_get()
        except Exception as exc:
            record_soft_exception("app_initialization.undo_focus", exc)
        textvariable = ""
        try:
            textvariable = str(focus.cget("textvariable")) if focus is not None else ""
        except Exception as exc:
            record_soft_exception("app_initialization.undo_textvariable", exc)
            textvariable = ""
        candidates = list(self._field_undo_vars.items())
        if textvariable:
            matched = [(key, var) for key, var in candidates if str(var) == textvariable]
            if not matched:
                return None
            candidates = matched
        elif focus is not None and str(getattr(focus, "winfo_class", lambda: "")()).lower() in {"entry", "text", "spinbox", "combobox"}:
            return None
        for key, var in reversed(candidates):
            stack = self._field_undo_stack.get(key) or []
            if not stack:
                continue
            previous = stack.pop()
            self._field_undo_suspended = True
            try:
                var.set(previous)
                self._field_undo_last[key] = previous
            finally:
                self._field_undo_suspended = False
            return "break"
        return None

    def _init_medical_output_state(self) -> None:
        # Медицинские документы.
        self.navigation_path_var = tk.StringVar()
        self.epi_path_var = tk.StringVar()
        self.strict_mode_var = tk.BooleanVar(value=True)

        # Общий список создаваемых сущностей: медицинские документы + дневники.
        # В продовом UI ничего не включаем по умолчанию: врач явно выбирает
        # нужные документы, чтобы случайно не создать лишний выписной эпикриз
        # или дневники наблюдения.
        self.output_vars: Dict[str, tk.BooleanVar] = {
            kind: tk.BooleanVar(value=False) for kind in DOCUMENT_ORDER
        }
        self.output_vars[DIARY_KIND] = tk.BooleanVar(value=False)
        # Doctor-owned medpack buttons live in visual block 03 under the
        # reserved namespace custom_profile:<document_id>. Legacy fixed ids stay
        # false and hidden from the production UI.
        self.custom_output_vars: Dict[str, tk.BooleanVar] = {}
        self._custom_profile_documents: list[object] = []
        self._custom_profile_tiles_container = None
        # Mapper-local completion values are kept inside the mapper window.
        # This legacy attribute remains only for backward compatibility with old sessions.
        self._regulatory_completion_values: dict[str, str] = {}

    def _init_diary_state(self) -> None:
        # Дневники.
        self.status_files: List[str] = []
        # Папка с текстами дневников. В новом сценарии файлы внутри названы
        # диагнозами, поэтому после чтения первичного документа программа
        # может автоматически выбрать нужный DOCX по diagnosis_var.
        self.diary_texts_dir: str = ""
        self._diary_text_files_auto_selected = False
        self.diary_files: List[str] = []
        # Папка, выбранная кнопкой «Шаблоны дневников». Сама кнопка теперь
        # выбирает именно папку 01–31, а не отдельный DOCX-файл. Конкретный
        # шаблон затем автоматически подставляется в прежний fill_diary_batch.
        self.diary_template_dir: str = ""
        # True only when the numbered 01–31 template was selected by the program.
        # Manual template selection by the doctor is still respected.
        self._diary_files_auto_selected = False
        self.repeat_statuses_var = tk.BooleanVar(value=True)
        self.reset_each_file_var = tk.BooleanVar(value=True)
        self.keep_signature_var = tk.BooleanVar(value=True)
        self.fill_months_var = tk.BooleanVar(value=True)
        self.force_final_diary_var = tk.BooleanVar(value=True)
        self.remove_holiday_rows_var = tk.BooleanVar(value=True)
        self.open_result_folder_var = tk.BooleanVar(value=True)
        self.diary_frequency_mode_var = tk.StringVar(value="daily")

    def _init_runtime_visual_state(self) -> None:
        # Скрытые служебные данные вместо прежних видимых блоков "Предпросмотр" и "Журнал".
        # Функционал остаётся: данные пациента хранятся, ошибки показываются в messagebox,
        # а короткий статус выводится в нижней панели.
        self._last_preview_text = ""
        self._log_buffer: List[str] = []

        # Визуальные состояния выбранных кнопок/плиток. Пользователь должен сразу
        # видеть, какие документы, тексты и даты уже включены, а не искать
        # маленькую галочку внутри тёмной карточки.
        self._check_tile_redrawers: Dict[str, object] = {}
        self._state_button_redrawers: List[object] = []

        # Собственный быстрый список диагноза, встроенный прямо в карточку пациента.
        # Не используется плавающее окно: оно могло сбивать фокус и положение UI.
        self._diagnosis_popup: tk.Frame | None = None
        self._diagnosis_listbox: tk.Listbox | None = None
        self._diagnosis_popup_matches: list[str] = []

    def _configure_root_window(self) -> None:
        self.root.title(APP_TITLE)
        # Стартовый размер окна — примерно 1/3 площади экрана.
        # Берём коэффициент sqrt(1/3) ≈ 0.577 по ширине и высоте,
        # чтобы сохранить внешний вид референса, но не открывать окно слишком большим.
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        target_w = max(900, int(screen_w * 0.577))
        target_h = max(700, int(screen_h * 0.63))
        start_x = max(0, (screen_w - target_w) // 2)
        start_y = max(0, (screen_h - target_h) // 2)
        self.root.geometry(f"{target_w}x{target_h}+{start_x}+{start_y}")
        self.root.minsize(980, 700)
        # Масштабируем не только окно, но и сам UI. Иначе при 1/3 экрана
        # карточки 03/04 уезжали вниз, а часть полей визуально обрезалась.
        self._ui_scale = max(0.57, min(1.0, target_w / 1408, target_h / 1056))
        self._font_scale = max(0.72, self._ui_scale)
        self._compact_ui = self._ui_scale < 0.82
        self.root.configure(bg=DEEP)
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._normal_geometry = f"{target_w}x{target_h}+{start_x}+{start_y}"
        self._is_maximized = False
        self._custom_chrome_restore_pending = False
        self._custom_chrome_restore_job = None
        self.root.bind("<Map>", self._on_root_mapped, add="+")

    def _global_hotkey_allowed(self) -> bool:
        """Do not trigger creation shortcuts while a modal dialog owns the grab."""

        try:
            grabbed = self.root.grab_current()
            return grabbed is None or grabbed == self.root
        except Exception as exc:
            record_soft_exception("app_initialization.hotkey_grab", exc)
            return True


    def _install_global_hotkeys(self) -> None:
        """Bind production workflow shortcuts: F5 primary, F8 print mode, F9 create."""
        self.root.bind_all("<F5>", lambda event: self._hotkey_choose_primary(), add="+")
        self.root.bind_all("<F8>", lambda event: self._toggle_hotkey_print_mode(), add="+")
        self.root.bind_all("<F9>", lambda event: self._hotkey_create_outputs(), add="+")

    def _hotkey_choose_primary(self) -> str:
        """Open primary DOCX chooser from the global F5 shortcut."""
        if not self._global_hotkey_allowed():
            return "break"
        self.choose_navigation()
        return "break"

    def _toggle_hotkey_print_mode(self) -> str:
        """Toggle whether F9 creates with printing enabled."""
        if not self._global_hotkey_allowed():
            return "break"
        self._hotkey_print_after = not bool(getattr(self, "_hotkey_print_after", False))
        mode = "с печатью" if self._hotkey_print_after else "без печати"
        self._set_status(f"F9: создание {mode}")
        return "break"

    def _hotkey_create_outputs(self) -> str:
        """Run selected document creation from the global F9 shortcut."""
        if not self._global_hotkey_allowed():
            return "break"
        self.create_selected_outputs(print_after=bool(getattr(self, "_hotkey_print_after", False)))
        return "break"

    def _bootstrap_printer_field_without_shell_scan(self) -> None:
        """Fill the printer field from settings without probing Windows printers.

        Startup can happen automatically after a doctor drops a DOCX into
        «Выписанные пациенты».  Printer discovery is intentionally explicit only
        (the «Выбрать/Проверить принтер» UI button or print flow), because old
        Windows/source environments may try shell-based fallbacks and briefly
        show a PowerShell window.
        """
        try:
            saved = str(self._settings.get("printer", "") or "").strip()
            if saved and hasattr(self, "printer_var"):
                self.printer_var.set(saved)
        except Exception as exc:
            record_soft_exception("app_initialization.bootstrap_printer_field", exc)

    def _bootstrap_ui(self) -> None:
        self._apply_custom_window_chrome()
        self._install_text_shortcuts()
        self._install_global_hotkeys()
        self._build_ui()
        # Drag-and-drop включается только через безопасный TkDND-путь.
        # Нативная подмена Windows WndProc была рискованной: на некоторых ПК
        # приложение могло не стартовать или закрываться сразу после запуска.
        self.root.after(150, self._install_file_drop_support)
        self._check_templates()
        self._set_status("Готов к работе")
        self._bootstrap_printer_field_without_shell_scan()
        self.root.after(700, self._bootstrap_desktop_intake_watcher)
