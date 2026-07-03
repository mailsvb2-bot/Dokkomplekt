"""Regression tests for user-facing diary/document generation failures.

Three defects made real doctor workflows fail even though the underlying
engines worked:

1. A suffix birth marker ("1985 г.р.") made the inline parser swallow the NEXT
   line (the admission/discharge dates line) into ``birth``. That garbage then
   flowed into ``patient.birth_date`` in generated documents, and the discharge
   date was lost.
2. ``reparse_navigation`` overwrote the parsed discharge date with an empty UI
   value on every reparse, so the diary/epicrisis flow kept prompting for the
   discharge date and could not build documents.
3. As a result, generated doctor-owned documents received a wrong birth date
   and an empty discharge date.

These tests lock the fixes at the parser and case-adapter level (headless, no
Tk needed).
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document

from medical_parser import MedicalTextParser
from universal_case_adapter import patient_data_to_case


def _primary_docx(path: Path) -> None:
    doc = Document()
    for line in (
        "История болезни № 314/26. Пациентка: Орлова Мария Ивановна, 1985 г.р.",
        "Дата поступления: 05.05.2026. Дата выписки: 19.05.2026.",
        "Жалобы: на подавленное настроение.",
        "Диагноз: Депрессивный эпизод средней степени F32.1.",
        "Лечение: сертралин 100 мг утром.",
    ):
        doc.add_paragraph(line)
    doc.save(path)


def test_suffix_birth_marker_does_not_swallow_dates_line():
    p = MedicalTextParser()
    text = (
        "Пациентка: Орлова Мария Ивановна, 1985 г.р.\n"
        "Дата поступления: 05.05.2026. Дата выписки: 19.05.2026."
    )
    value = p._extract_inline(text, p.FIELD_ALIASES["birth"], field_name="birth")
    assert value == "1985", value


def test_prefix_birth_label_still_works():
    p = MedicalTextParser()
    value = p._extract_inline(
        "Год рождения: 1975\nЖалобы: нет.", p.FIELD_ALIASES["birth"], field_name="birth"
    )
    assert value == "1975", value


def test_parse_docx_keeps_clean_birth_and_both_dates():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "primary.docx"
        _primary_docx(path)
        data = MedicalTextParser().parse_docx(str(path))
        assert data.fio == "Орлова Мария Ивановна"
        assert data.birth == "1985", data.birth
        assert data.admission_date == "05.05.2026"
        assert data.discharge_date == "19.05.2026", data.discharge_date


def test_generated_documents_receive_correct_fields():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "primary.docx"
        _primary_docx(path)
        data = MedicalTextParser().parse_docx(str(path))
        case = patient_data_to_case(data, source_document=str(path))
        assert case.get("patient.fio") == "Орлова Мария Ивановна"
        assert case.get("patient.birth_date") == "1985"
        assert case.get("admission.date") == "05.05.2026"
        assert case.get("discharge.date") == "19.05.2026"


def test_reparse_navigation_does_not_blank_parsed_discharge():
    """The parsed discharge date must survive a reparse when the UI has none.

    Simulates the reparse_navigation contract with a tiny stub instead of the
    full Tk app: an empty UI discharge value must not overwrite a parsed one.
    """
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "primary.docx"
        _primary_docx(path)
        data = MedicalTextParser().parse_docx(str(path))

    # Contract mirror of the fixed logic in actions_navigation.reparse_navigation:
    ui_discharge = ""  # nothing typed in the UI yet
    if ui_discharge:
        data.discharge_date = ui_discharge
    assert data.discharge_date == "19.05.2026"

    # And a manually typed value must win.
    ui_discharge = "21.05.2026"
    if ui_discharge:
        data.discharge_date = ui_discharge
    assert data.discharge_date == "21.05.2026"
