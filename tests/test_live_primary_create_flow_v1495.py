from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document

from icd10_f_search import normalize_required_diagnosis_with_icd10
from medical_current_episode_dates import (
    extract_current_admission_date_from_primary_docx,
    extract_current_discharge_date_from_primary_docx,
)
from medical_parser import MedicalTextParser


SCREENSHOT_DIAGNOSIS = "F20.00 Шизофрения параноидная галлюцинаторно-бредовый синдром"


def _write_docx(path: Path, lines: list[str]) -> None:
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    doc.save(path)


def test_visible_f2000_diagnosis_is_accepted_by_creation_popup_validator() -> None:
    normalized = normalize_required_diagnosis_with_icd10(SCREENSHOT_DIAGNOSIS)
    assert normalized == SCREENSHOT_DIAGNOSIS


def test_word_unicode_lookalikes_in_icd_code_do_not_false_reject() -> None:
    samples = (
        "Ｆ２０．００ Шизофрения параноидная",
        "F20․00 Шизофрения параноидная",
        "F 20 . 00 Шизофрения параноидная",
        "F20\u200b.00 Шизофрения параноидная",
    )
    for value in samples:
        normalized = normalize_required_diagnosis_with_icd10(value)
        assert normalized.startswith("F20.00"), (value, normalized)


def test_referral_historical_episode_cannot_become_current_discharge() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "referral.docx"
        _write_docx(
            path,
            [
                "30.09.2025 Направление на госпитализацию",
                "История болезни № 234",
                "ФИО: Иванов Иван Иванович",
                "Дата поступления: 30.09.2025",
                "Лечение: Галоперидол 5 мг 2 раза в день",
                f"Диагноз: {SCREENSHOT_DIAGNOSIS}",
                "Анамнез заболевания: в 2023 году госпитализирован 01.02.2023, выписан 07.02.2023.",
            ],
        )

        assert extract_current_admission_date_from_primary_docx(path) == "30.09.2025"
        assert extract_current_discharge_date_from_primary_docx(path) == ""
        data = MedicalTextParser().parse_docx(path)
        assert data.admission_date == "30.09.2025"
        assert data.discharge_date == ""


def test_referral_title_date_outranks_historical_hospitalization_without_label() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "referral-title-only.docx"
        _write_docx(
            path,
            [
                "30.09.2025 Направление на госпитализацию",
                "История болезни № 234",
                "ФИО: Иванов Иван Иванович",
                "Анамнез заболевания: в 2023 году госпитализирован 01.02.2023, выписан 07.02.2023.",
                f"Диагноз: {SCREENSHOT_DIAGNOSIS}",
            ],
        )

        assert extract_current_admission_date_from_primary_docx(path) == "30.09.2025"
        assert extract_current_discharge_date_from_primary_docx(path) == ""
        data = MedicalTextParser().parse_docx(path)
        assert data.admission_date == "30.09.2025"
        assert data.discharge_date == ""


def test_primary_docx_prefills_current_patient_fields_end_to_end() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "primary.docx"
        _write_docx(
            path,
            [
                "30.09.2025 Первичный осмотр",
                "История болезни № 234",
                "ФИО: Иванов Иван Иванович",
                "Дата рождения: 01.01.1980",
                "Дата поступления: 30.09.2025",
                "Дата выписки: 10.10.2025",
                "Место работы: ООО Пример",
                "Должность: инженер",
                "Лечение: Галоперидол 5 мг 2 раза в день",
                f"Диагноз: {SCREENSHOT_DIAGNOSIS}",
            ],
        )

        data = MedicalTextParser().parse_docx(path)
        assert data.case_number == "234"
        assert data.fio == "Иванов Иван Иванович"
        assert data.birth == "01.01.1980"
        assert data.admission_date == "30.09.2025"
        assert data.discharge_date == "10.10.2025"
        assert data.work_org == "ООО Пример"
        assert data.position == "инженер"
        assert data.treatment_plan == "Галоперидол 5 мг 2 раза в день"
        assert data.diagnosis == SCREENSHOT_DIAGNOSIS
