from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document

from document_intelligence.current_episode_dates import (
    extract_current_admission_date_from_primary_docx,
    extract_current_discharge_date_from_primary_docx,
)
from icd10_f_search import normalize_required_diagnosis_with_icd10
from medical_parser import MedicalTextParser


VALID_DIAGNOSIS = "F20.00 Тестовое описание"


def _write_docx(path: Path, lines: list[str]) -> None:
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    doc.save(path)


def test_visible_f2000_diagnosis_is_accepted_by_creation_preflight_normalizer() -> None:
    assert normalize_required_diagnosis_with_icd10(VALID_DIAGNOSIS) == VALID_DIAGNOSIS


def test_word_unicode_lookalikes_in_icd_code_do_not_false_reject() -> None:
    samples = (
        "Ｆ２０．００ Тестовое описание",
        "F20․00 Тестовое описание",
        "F 20 . 00 Тестовое описание",
        "F20\u200b.00 Тестовое описание",
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
                "ФИО: Тестов Тест Тестович",
                "Дата поступления: 30.09.2025",
                "Лечение: тестовый план",
                f"Диагноз: {VALID_DIAGNOSIS}",
                "Анамнез: ранее госпитализирован 01.02.2023, выписан 07.02.2023.",
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
                "ФИО: Тестов Тест Тестович",
                "Анамнез: ранее госпитализирован 01.02.2023, выписан 07.02.2023.",
                f"Диагноз: {VALID_DIAGNOSIS}",
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
                "ФИО: Тестов Тест Тестович",
                "Дата рождения: 01.01.1980",
                "Дата поступления: 30.09.2025",
                "Дата выписки: 10.10.2025",
                "Место работы: ООО Тест",
                "Должность: инженер",
                "Лечение: тестовый план",
                f"Диагноз: {VALID_DIAGNOSIS}",
            ],
        )

        data = MedicalTextParser().parse_docx(path)
        assert data.case_number == "234"
        assert data.fio == "Тестов Тест Тестович"
        assert data.birth == "01.01.1980"
        assert data.admission_date == "30.09.2025"
        assert data.discharge_date == "10.10.2025"
        assert data.work_org == "ООО Тест"
        assert data.position == "инженер"
        assert data.treatment_plan == "тестовый план"
        assert data.diagnosis == VALID_DIAGNOSIS
