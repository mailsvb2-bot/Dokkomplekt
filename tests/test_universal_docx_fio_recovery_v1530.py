from __future__ import annotations

from pathlib import Path

from docx import Document

from desktop_patient_folder import build_patient_folder_info, build_patient_folder_name
from medical_parser import MedicalTextParser


def test_invisible_word_separator_does_not_hide_unlabeled_fio():
    data = MedicalTextParser().parse_text(
        "15.04.2026 Направление на госпитализацию\n"
        "Иванов\ufffeИван Иванович, 04.01.2000, Нижний Новгород\n"
        "Диагноз: F20.00 Шизофрения"
    )
    assert data.fio == "Иванов Иван Иванович"
    assert build_patient_folder_name(
        fio=data.fio,
        settings={"parts": ["surname_initials"], "date_format": "short"},
        strict=True,
    ) == "Иванов И.И"


def test_invisible_word_formatting_is_removed_inside_labeled_fio():
    data = MedicalTextParser().parse_text(
        "15.04.2026 Первичный осмотр\n"
        "Ф.И.О.: Петрова\u200b Мария\ufeff Сергеевна\n"
        "Дата рождения: 04.01.2000"
    )
    assert data.fio == "Петрова Мария Сергеевна"


def test_table_header_row_recovers_any_patient_fio_for_strict_folder(tmp_path):
    primary = tmp_path / "primary.docx"
    doc = Document()
    doc.add_paragraph("15.04.2026 Направление на госпитализацию")
    table = doc.add_table(rows=2, cols=5)
    table.cell(0, 0).merge(table.cell(0, 2)).text = "Ф.И.О. больного"
    table.cell(0, 3).text = "Дата рождения"
    table.cell(0, 4).text = "Адрес регистрации"
    table.cell(1, 0).text = "Орлов"
    table.cell(1, 1).text = "Пётр"
    table.cell(1, 2).text = "Максимович"
    table.cell(1, 3).text = "04.01.2000"
    table.cell(1, 4).text = "Нижний Новгород"
    doc.add_paragraph("Диагноз: F20.00 Шизофрения")
    doc.save(primary)

    data = MedicalTextParser().parse_docx(primary)
    assert data.fio == "Орлов Пётр Максимович"
    assert build_patient_folder_info(primary).fio == "Орлов Пётр Максимович"
    assert build_patient_folder_name(
        fio=data.fio,
        settings={"parts": ["surname_initials"], "date_format": "short"},
        strict=True,
    ) == "Орлов П.М"


def test_table_geometry_never_promotes_clinician_fio_to_patient(tmp_path):
    primary = tmp_path / "clinician_only.docx"
    doc = Document()
    doc.add_paragraph("15.04.2026 Первичный осмотр")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Ф.И.О. лечащего врача"
    table.cell(0, 1).text = "Дата рождения"
    table.cell(1, 0).text = "Соколова Марина Андреевна"
    table.cell(1, 1).text = "04.01.2000"
    doc.add_paragraph("Диагноз: F20.00 Шизофрения")
    doc.save(primary)

    assert MedicalTextParser().parse_docx(primary).fio == ""


def test_content_control_flattening_recovers_patient_without_filename_help(tmp_path):
    from docx.oxml import OxmlElement

    primary = tmp_path / "primary.docx"
    doc = Document()
    doc.add_paragraph("15.04.2026 Направление на госпитализацию")
    sdt = OxmlElement("w:sdt")
    content = OxmlElement("w:sdtContent")
    for value in (
        "Ф.И.О. больного",
        "Кузнецова Анна Викторовна",
        "Дата рождения: 04.01.2000",
        "Адрес регистрации: Нижний Новгород",
    ):
        paragraph = OxmlElement("w:p")
        run = OxmlElement("w:r")
        text = OxmlElement("w:t")
        text.text = value
        run.append(text)
        paragraph.append(run)
        content.append(paragraph)
    sdt.append(content)
    body = doc._element.body
    body.insert(max(0, len(body) - 1), sdt)
    doc.add_paragraph("Диагноз: F20.00 Шизофрения")
    doc.save(primary)

    data = MedicalTextParser().parse_docx(primary)
    assert data.fio == "Кузнецова Анна Викторовна"
    assert data.output_fio == data.fio


def test_filename_initials_hint_is_output_identity_only(tmp_path):
    primary = tmp_path / "Смирнова А.В. Направление.docx"
    doc = Document()
    doc.add_paragraph("15.04.2026 Направление на госпитализацию")
    doc.add_paragraph("Дата рождения: 04.01.2000")
    doc.add_paragraph("Диагноз: F20.00 Шизофрения")
    doc.save(primary)

    data = MedicalTextParser().parse_docx(primary)
    assert data.fio == ""
    assert data.output_fio == "Смирнова А.В."
    assert build_patient_folder_name(
        fio=data.output_fio,
        settings={"parts": ["surname_initials"], "date_format": "short"},
        strict=True,
    ) == "Смирнова А.В"


def test_output_hint_contract_is_ui_only_not_document_fio():
    medical_flow = Path("actions_medical_flow.py").read_text(encoding="utf-8")
    navigation = Path("actions_navigation.py").read_text(encoding="utf-8")

    assert 'if not data.fio and manual_patient_name and bool(getattr(self, "_manual_patient_name", False)):' in medical_flow
    assert 'data.output_fio = manual_patient_name or data.output_fio or data.fio' in medical_flow
    assert 'display_fio = str(data.fio or data.output_fio or "").strip()' in navigation
