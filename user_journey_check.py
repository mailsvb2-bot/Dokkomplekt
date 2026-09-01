"""GUI-free end-to-end verifier for the packaged doctor workflow."""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import replace
from pathlib import Path


def run_user_journey_check() -> dict[str, object]:
    result: dict[str, object] = {"check": "user_journey", "ok": False, "checks": {}, "error": None}
    checks: dict[str, bool] = result["checks"]  # type: ignore[assignment]
    try:
        from docx import Document
        from desktop_intake import prepare_patient_work_folder, scan_primary_candidates
        from diary_schedule import DiaryScheduleSpec
        from medical_docx_reader import extract_docx_text
        from medical_service import MedicalDocumentService
        from universal_case_adapter import patient_data_to_case
        from universal_diary_generation import render_diary_documents_from_pack
        from universal_generation import render_documents_from_pack
        from universal_profiles import default_document_pack
        from universal_template_engine import attach_template_to_pack

        def write_docx(path: Path, paragraphs: list[str]) -> Path:
            document = Document()
            for text in paragraphs:
                document.add_paragraph(text)
            document.save(path)
            return path

        with tempfile.TemporaryDirectory(prefix="dokkomplekt-user-journey-") as raw:
            root = Path(raw)
            intake = root / "Выписанные пациенты"
            intake.mkdir()
            source = write_docx(intake / "01.09.2026 Первичный осмотр.docx", [
                "01.09.2026 Первичный осмотр",
                "Ф.И.О.: ИВАНОВ ИВАН ИВАНОВИЧ",
                "Дата поступления: 01.09.2026",
                "Жалобы: тревога",
                "Диагноз: K35.8 Острый аппендицит",
            ])
            old = time.time() - 5
            os.utime(source, (old, old))
            candidates = scan_primary_candidates(intake, set())
            checks["desktop_intake_detects_primary"] = len(candidates) == 1 and candidates[0].path == source

            patient_dir, primary = prepare_patient_work_folder(intake, source)
            checks["patient_folder_created"] = patient_dir.name == "ИВАНОВ И.И. сентябрь 2026"
            checks["primary_moved_into_patient_folder"] = primary.exists() and primary.parent == patient_dir and not source.exists()

            data = MedicalDocumentService().parse_primary_document(primary)
            checks["primary_parsed"] = (
                data.fio == "ИВАНОВ ИВАН ИВАНОВИЧ"
                and data.admission_date == "01.09.2026"
                and "K35.8" in data.diagnosis
            )
            # These are the values the application-level popup writes before rendering.
            data.case_number = "К-777"
            data.treatment_plan = "терапия из пользовательского popup"
            data.discharge_date = "05.09.2026"
            case = patient_data_to_case(data, source_document=str(primary))
            checks["popup_values_reach_case"] = (
                case.get("case.number") == "К-777"
                and case.get("treatment.plan") == "терапия из пользовательского popup"
                and case.get("discharge.date") == "05.09.2026"
            )

            profile_dir = root / "profile"
            profile_dir.mkdir()
            pack = default_document_pack()
            primary_template = write_docx(root / "Первичный шаблон.docx", [
                "Пациент {{patient.fio}}",
                "История болезни № {{case.number}}",
                "Диагноз {{diagnosis.main}}",
                "План лечения {{treatment.plan}}",
            ])
            attach_template_to_pack(
                pack, primary_template, profile_dir,
                button_label="Первичный осмотр", document_id="doctor_primary",
                category="medical", role_id="primary_exam",
            )
            discharge_template = write_docx(root / "Выписной шаблон.docx", [
                "Выписной эпикриз {{patient.fio}}",
                "История болезни № {{case.number}}",
                "Диагноз {{diagnosis.main}}",
                "Лечение {{treatment.plan}}",
                "Дата выписки {{discharge.date}}",
            ])
            attach_template_to_pack(
                pack, discharge_template, profile_dir,
                button_label="Выписной эпикриз", document_id="doctor_discharge",
                category="medical", role_id="discharge",
            )
            diary_template = write_docx(root / "Дневники шаблон.docx", [
                "Состояние стабильное, жалоб активно не предъявляет.",
                "Контактен, ориентирован, назначения выполняет.",
            ])
            diary_spec, _ = attach_template_to_pack(
                pack, diary_template, profile_dir,
                button_label="Дневники наблюдения", document_id="doctor_diary",
                category="diaries", role_id="daily_diary",
            )
            diary_spec = replace(
                diary_spec,
                category="diaries",
                role_id="daily_diary",
                diary_schedule=DiaryScheduleSpec("daily", (1, 2, 3, 4), (), 1.0, "packaged_user_journey").to_dict(),
            )
            pack.add_document(diary_spec)
            checks["doctor_owned_buttons_ready"] = {doc.id for doc in pack.documents} == {
                "doctor_primary", "doctor_discharge", "doctor_diary"
            }

            regular = render_documents_from_pack(
                pack=pack,
                case=case,
                document_ids=["doctor_primary", "doctor_discharge"],
                output_dir=patient_dir,
                base_dir=profile_dir,
                strict=True,
            )
            diaries = render_diary_documents_from_pack(
                pack=pack,
                case=case,
                document_ids=["doctor_diary"],
                output_dir=patient_dir,
                base_dir=profile_dir,
                status_files=[],
                patient_name=case.get("patient.fio"),
                admission_value=case.get("admission.date"),
                discharge_value=case.get("discharge.date"),
                diary_day_offsets=(1, 2, 3, 4),
                remove_holiday_rows=False,
                force_final_diary=False,
            )
            checks["regular_documents_created"] = regular.ok and len(regular.created_files) == 2
            checks["diaries_created"] = not diaries.skipped and len(diaries.created_files) == 1

            regular_texts = [extract_docx_text(path) for path in regular.created_files]
            diary_text = extract_docx_text(diaries.created_files[0]) if diaries.created_files else ""
            checks["regular_content_correct"] = (
                all("К-777" in text and "K35.8" in text for text in regular_texts)
                and any("терапия из пользовательского popup" in text for text in regular_texts)
                and any("05.09.2026" in text for text in regular_texts)
            )
            checks["diary_calendar_correct"] = (
                "02.09.26" in diary_text
                and "05.09.26" in diary_text
                and "01.09.26" not in diary_text
                and "06.09.26" not in diary_text
            )
            checks["diary_signatures_present"] = "Лечащий врач" in diary_text and "Зав. отделением" in diary_text
            checks["outputs_stay_in_patient_folder"] = all(
                Path(path).parent == patient_dir for path in [*regular.created_files, *diaries.created_files]
            )
            checks["intake_does_not_retrigger"] = scan_primary_candidates(intake, set()) == ()

        result["ok"] = bool(checks) and all(checks.values())
    except Exception as exc:  # pragma: no cover - packaged verifier reports the error as JSON
        result["error"] = repr(exc)
    return result
