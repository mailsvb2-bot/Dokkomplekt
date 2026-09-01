"""Application-level replay of the doctor journey from intake to patient files."""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from docx import Document

import main as _main_module
from desktop_intake import prepare_patient_work_folder, scan_primary_candidates
from diary_constants import DIARY_KIND
from diary_schedule import DiaryScheduleSpec
from medical_constants import DOCUMENT_ORDER
from medical_docx_reader import extract_docx_text
from medical_service import MedicalDocumentService
from universal_main_documents import custom_kind
from universal_profiles import default_document_pack, save_document_pack
from universal_template_engine import attach_template_to_pack


class _Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Root:
    def configure(self, **_kwargs):
        return None

    def update_idletasks(self):
        return None


class _Status:
    def __init__(self):
        self.text = ""

    def config(self, **kwargs):
        if "text" in kwargs:
            self.text = kwargs["text"]


def _doc(path: Path, paragraphs: list[str]) -> Path:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    document.save(path)
    return path


def _build_profile(root: Path):
    profile_path = root / "profiles" / "journey.medpack.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    pack = default_document_pack()

    primary_template = _doc(root / "Первичный шаблон.docx", [
        "Пациент {{patient.fio}}",
        "История болезни № {{case.number}}",
        "Диагноз {{diagnosis.main}}",
        "План лечения {{treatment.plan}}",
    ])
    attach_template_to_pack(
        pack, primary_template, profile_path.parent,
        button_label="Первичный осмотр", document_id="doctor_primary",
        category="medical", role_id="primary_exam",
    )

    discharge_template = _doc(root / "Выписной шаблон.docx", [
        "Выписной эпикриз {{patient.fio}}",
        "История болезни № {{case.number}}",
        "Диагноз {{diagnosis.main}}",
        "Лечение {{treatment.plan}}",
        "Дата выписки {{discharge.date}}",
    ])
    attach_template_to_pack(
        pack, discharge_template, profile_path.parent,
        button_label="Выписной эпикриз", document_id="doctor_discharge",
        category="medical", role_id="discharge",
    )

    diary_template = _doc(root / "Дневники шаблон.docx", [
        "Состояние стабильное, жалоб активно не предъявляет.",
        "Контактен, ориентирован, назначения выполняет.",
    ])
    diary_spec, _ = attach_template_to_pack(
        pack, diary_template, profile_path.parent,
        button_label="Дневники наблюдения", document_id="doctor_diary",
        category="diaries", role_id="daily_diary",
    )
    diary_spec = replace(
        diary_spec,
        category="diaries",
        role_id="daily_diary",
        diary_schedule=DiaryScheduleSpec("daily", (1, 2, 3, 4), (), 1.0, "full_user_journey").to_dict(),
    )
    pack.add_document(diary_spec)
    save_document_pack(pack, profile_path)
    return profile_path, pack


def _build_app(primary_path: Path, patient_dir: Path, profile_path: Path, pack):
    app = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
    app.root = _Root()
    app.status_label = _Status()
    app.service = MedicalDocumentService()
    app._primary_parse_cache = {}
    app._diary_template_files_cache = {}
    app._diary_template_day_cache = {}
    app._diary_template_folder_contains_cache = {}
    app._log_buffer = []
    app._last_preview_text = ""
    app._suspend_user_edit_tracking = False
    app._manual_output_dir = False
    app._output_dir_auto_locked_to_patient = True
    app._manual_patient_name = False
    app._manual_admission_date = False
    app._manual_discharge_date = False
    app._manual_diagnosis = False
    app._popup_discharge_date_override = ""
    app._popup_diagnosis_override = ""
    app._work_details_manually_edited = False
    app._primary_work_org_default = ""
    app._primary_work_position_default = ""
    app._settings_path = profile_path.parent.parent / "settings.json"
    app._settings = {
        "active_universal_profile": str(profile_path),
        "folder_naming": {
            "parts": ["surname_initials", "admission_month"],
            "date_format": "short",
            "doctor_confirmed": True,
        },
    }

    app.navigation_path_var = _Var(str(primary_path))
    app.output_dir_var = _Var(str(patient_dir))
    app.primary_document_type_var = _Var("primary_exam")
    app.patient_name_var = _Var("")
    app.admission_date_var = _Var("")
    app.discharge_date_var = _Var("")
    app.diagnosis_var = _Var("")
    app.case_number_var = _Var("")
    app.assigned_treatment_var = _Var("")
    app.epi_path_var = _Var("")
    app.additional_info_text_var = _Var("")
    app.additional_info_source_path_var = _Var("")
    app.strict_mode_var = _Var(False)
    app.printer_var = _Var("")
    app.open_result_folder_var = _Var(False)
    app.document_language_var = _Var("auto")
    app.output_language_var = _Var("same_as_source")
    app.spellcheck_enabled_var = _Var(True)

    app.labs_text_var = _Var("")
    app.labs_without_var = _Var(False)
    app.labs_source_path_var = _Var("")
    app.labs_date_policy_var = _Var("preserve_found_dates")
    app.labs_explicit_date_var = _Var("")

    for name in (
        "expert_work_org_var", "expert_position_var", "expert_sick_leave_from_var",
        "expert_sick_leave_number_var", "commission_date_var", "commission_number_var",
        "rvk_act_number_var", "rvk_military_commissariat_var", "rvk_work_position_var",
        "vk_date_var", "vk_protocol_number_var", "vk_protocol_date_var",
        "vk_mse_work_org_var", "vk_mse_position_var", "vk_mse_work_position_var",
        "sick_leave_vk_date_var", "sick_leave_vk_protocol_number_var",
        "sick_leave_vk_protocol_date_var", "sick_leave_vk_commission_date_var",
        "sick_leave_vk_work_org_var", "sick_leave_vk_position_var",
        "sick_leave_vk_work_position_var", "diary_treatment_correction_var",
    ):
        setattr(app, name, _Var(""))
    app.expert_work_status_var = _Var("нет")
    app.expert_sick_leave_needed_var = _Var("нет")

    app.status_files = []
    app.diary_files = []
    app.diary_template_dir = ""
    app.diary_texts_dir = ""
    app.diary_frequency_mode_var = _Var("daily")
    app.repeat_statuses_var = _Var(True)
    app.reset_each_file_var = _Var(True)
    app.keep_signature_var = _Var(True)
    app.fill_months_var = _Var(True)
    app.force_final_diary_var = _Var(False)
    app.remove_holiday_rows_var = _Var(False)

    app.output_vars = {kind: _Var(False) for kind in DOCUMENT_ORDER}
    app.output_vars[DIARY_KIND] = _Var(False)
    app.custom_output_vars = {}
    for document_id in ("doctor_primary", "doctor_discharge", "doctor_diary"):
        kind = custom_kind(document_id)
        var = _Var(True)
        app.output_vars[kind] = var
        app.custom_output_vars[kind] = var

    app.data = app.service.parse_primary_document(primary_path)
    app._set_ui_var(app.patient_name_var, app.data.fio)
    app._set_ui_var(app.admission_date_var, app.data.admission_date)
    app._set_ui_var(app.diagnosis_var, app.data.diagnosis)

    app._load_or_create_universal_pack = lambda: pack
    app._universal_profile_path = lambda: profile_path
    app._ensure_patient_folder_naming_configured = lambda *args, **kwargs: True
    app._confirm_patient_case_before_creation = lambda review: True
    app._apply_duplicate_policy = lambda review, selected_medical: True
    app._write_creation_report = lambda **kwargs: None
    app._show_created_document_preview = lambda created_files: None
    app._open_output_folder_after_creation = lambda **kwargs: False
    app._start_progress = lambda: None
    app._stop_progress = lambda: None
    app._diagnostic_reports_enabled = lambda: False
    app._redraw_selection_controls = lambda: None
    app._update_expert_sick_leave_display = lambda: None
    app._save_settings = lambda: None
    app._log = lambda message: app._log_buffer.append(message)
    app._set_status = lambda message: app.status_label.config(text=message)
    return app


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="dokkomplekt-full-user-journey-") as raw:
        root = Path(raw)
        intake = root / "Выписанные пациенты"
        intake.mkdir()
        source = _doc(intake / "01.09.2026 Первичный осмотр.docx", [
            "01.09.2026 Первичный осмотр",
            "Ф.И.О.: ИВАНОВ ИВАН ИВАНОВИЧ",
            "Дата поступления: 01.09.2026",
            "Жалобы: тревога",
            "Диагноз: K35.8 Острый аппендицит",
        ])
        old = time.time() - 5
        os.utime(source, (old, old))
        candidates = scan_primary_candidates(intake, set())
        assert len(candidates) == 1 and candidates[0].path == source, candidates

        patient_dir, primary = prepare_patient_work_folder(intake, source)
        assert patient_dir.name == "ИВАНОВ И.И. сентябрь 2026", patient_dir
        assert primary.exists() and primary.parent == patient_dir and not source.exists()

        profile_path, pack = _build_profile(root)
        app = _build_app(primary, patient_dir, profile_path, pack)
        popup_calls: list[tuple[str, list[str]]] = []
        popup_values = {
            "Номер истории болезни": "К-777",
            "Лечение": "терапия из пользовательского popup",
            "Диагноз": "K35.8 Острый аппендицит",
            "Дата выписки": "05092026",
        }

        def prompt_fields(title, rows, **_kwargs):
            labels = [label for label, _default in rows]
            popup_calls.append((title, labels))
            return [popup_values[label] for label in labels]

        app._prompt_fields = prompt_fields
        from diary_schedule import DiaryScheduleSpec as _Schedule
        with (
            patch("diary_creation_wizard.confirm_diary_creation", return_value=True),
            patch(
                "diary_creation_wizard.current_diary_calendar_schedule",
                return_value=_Schedule("daily", (1, 2, 3, 4), (), 1.0, "full_user_journey"),
            ),
        ):
            app.create_selected_outputs(print_after=False)

        assert len(popup_calls) == 1, popup_calls
        assert popup_calls[0][0] == "Данные для выписного эпикриза", popup_calls
        assert "Номер истории болезни" in popup_calls[0][1], popup_calls
        assert "Лечение" in popup_calls[0][1], popup_calls
        assert "Дата выписки" in popup_calls[0][1], popup_calls

        created = sorted(path for path in patient_dir.glob("*.docx") if path != primary)
        assert len(created) == 3, [path.name for path in created]
        by_name = {path.name: extract_docx_text(path) for path in created}
        primary_out = next(text for name, text in by_name.items() if "Первичный осмотр" in name)
        discharge_out = next(text for name, text in by_name.items() if "Выписной эпикриз" in name)
        diary_out = next(text for name, text in by_name.items() if "дневники" in name.lower())

        assert "К-777" in primary_out and "терапия из пользовательского popup" in primary_out
        assert "K35.8 Острый аппендицит" in primary_out
        assert "К-777" in discharge_out and "05.09.2026" in discharge_out
        assert "терапия из пользовательского popup" in discharge_out
        assert "02.09.26" in diary_out and "05.09.26" in diary_out
        assert "01.09.26" not in diary_out and "06.09.26" not in diary_out
        assert "Лечащий врач" in diary_out and "Зав. отделением" in diary_out
        assert scan_primary_candidates(intake, set()) == ()
        assert app.status_label.text == "Готово: файлы сохранены", app.status_label.text

    print("FULL USER JOURNEY SMOKE OK")


if __name__ == "__main__":
    main()
