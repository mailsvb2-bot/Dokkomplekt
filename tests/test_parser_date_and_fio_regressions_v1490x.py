"""Regression tests for two silent primary-document parsing bugs.

1. Single-line date records ("Дата поступления: X. Дата выписки: Y.") made the
   discharge date bind to the admission marker because marker distance was
   measured in both directions. The discharge date silently became the
   admission date, corrupting every downstream diary/epicrisis date.
2. Demographic tails glued to the name ("Петрова Анна Сергеевна, 1975 г.р.")
   leaked the birth year into the parsed FIO, so document headers and the
   patient folder name contained ", 1975".

Both must stay fixed: a date binds to its nearest PRECEDING marker, and FIO is
cut at the first comma-or-digit boundary after the name words.
"""
from __future__ import annotations

from medical_admission_resolver import (
    extract_admission_date_from_primary_text,
    extract_discharge_date_from_primary_text,
)
from medical_parser import MedicalTextParser


def test_discharge_date_single_line_record_binds_to_its_own_marker():
    text = "Дата поступления: 10.02.2026. Дата выписки: 20.02.2026."
    assert extract_admission_date_from_primary_text(text) == "10.02.2026"
    assert extract_discharge_date_from_primary_text(text) == "20.02.2026"


def test_discharge_date_multiline_record_still_works():
    text = "Дата поступления: 10.02.2026.\nДата выписки: 20.02.2026."
    assert extract_admission_date_from_primary_text(text) == "10.02.2026"
    assert extract_discharge_date_from_primary_text(text) == "20.02.2026"


def test_discharge_date_verb_style_record():
    text = "Поступил 10.02.2026, выписан 20.02.2026."
    assert extract_admission_date_from_primary_text(text) == "10.02.2026"
    assert extract_discharge_date_from_primary_text(text) == "20.02.2026"


def test_admission_date_not_stolen_by_birth_marker_on_one_line():
    text = "Дата рождения: 05.05.1980. Дата поступления: 10.02.2026. Выписан: 20.02.2026."
    assert extract_admission_date_from_primary_text(text) == "10.02.2026"
    assert extract_discharge_date_from_primary_text(text) == "20.02.2026"


def test_fio_drops_birth_year_tail_with_comma():
    data = MedicalTextParser().parse_text("Пациентка: Петрова Анна Сергеевна, 1975 г.р.")
    assert data.fio == "Петрова Анна Сергеевна"


def test_fio_drops_full_demographics_tail():
    data = MedicalTextParser().parse_text(
        "Пациент: Иванов Иван Иванович, 1980 года рождения, пол мужской."
    )
    assert data.fio == "Иванов Иван Иванович"


def test_fio_drops_year_tail_without_comma():
    data = MedicalTextParser().parse_text(
        "Пациент: Кузнецова-Смирнова Ольга Викторовна 1990 г.р."
    )
    assert data.fio == "Кузнецова-Смирнова Ольга Викторовна"


def test_fio_with_initials_untouched():
    data = MedicalTextParser().parse_text("ФИО: Сидоров П.К.")
    assert data.fio == "Сидоров П.К."


def test_hourly_text_diary_route_restored():
    """diary_hour_offsets/diary_frequency_mode must not be silently ignored."""
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from docx import Document

    from diary_batch import fill_diary_batch
    from medical_docx_reader import extract_docx_text

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        texts = root / "тексты.docx"
        doc = Document()
        doc.add_paragraph("Состояние стабильное, жалоб активно не предъявляет.")
        doc.save(texts)
        result = fill_diary_batch(
            status_files=[texts],
            diary_files=[],
            output_dir=root / "out",
            patient_name="Иванов И.И.",
            admission_value="10.06.2026 14:00",
            gender_source_name="Иванов И.И.",
            diary_hour_offsets=(1,),
            diary_frequency_mode="hourly",
            force_final_diary=False,
        )
        text = extract_docx_text(result.created_files[0])
        assert "10.06.26 15:00" in text
        assert "10.06.26 16:00" in text
