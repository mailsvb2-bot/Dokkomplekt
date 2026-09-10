from __future__ import annotations

from datetime import date
from pathlib import Path

from docx import Document

from diary_batch import default_observation_diary_dates, fill_diary_batch
from diary_text_parser import extract_statuses_from_docx
from medical_docx_xml_fragments import SUPPORTED_WORD_SUFFIXES, is_supported_word_file


def _paragraph_text(path: Path) -> str:
    return "\n".join(paragraph.text for paragraph in Document(str(path)).paragraphs if paragraph.text.strip())


def test_diary_single_route_ignores_calendar_table_file(tmp_path: Path) -> None:
    status_docx = tmp_path / "texts.docx"
    source = Document()
    source.add_paragraph("01.06.2026 First diary text is long enough for extraction and output.")
    source.add_paragraph("02.06.2026 Second diary text is long enough for extraction and output.")
    source.add_paragraph("02.06.2026 Second diary text is long enough for extraction and output.")
    source.save(status_docx)
    assert len(extract_statuses_from_docx(status_docx)) == 2

    table_docx = tmp_path / "calendar_table.docx"
    template = Document()
    table = template.add_table(rows=1, cols=4)
    for index, header in enumerate(["n", "day", "month", "text"]):
        table.rows[0].cells[index].text = header
    for day in [10, 11, 12, 13, 14, 15]:
        row = table.add_row()
        row.cells[0].text = str(day)
        row.cells[1].text = str(day)
        row.cells[2].text = ""
        row.cells[3].text = "OLD_TABLE_CONTENT_SHOULD_NOT_BE_USED"
    template.save(table_docx)

    result = fill_diary_batch(
        status_files=[status_docx],
        diary_files=[table_docx],
        output_dir=tmp_path / "out",
        patient_name="Ivanova Irina",
        gender_source_name="Ivanova Irina",
        admission_value="10.06.2026",
        discharge_value="12.06.2026",
        repeat_statuses=True,
        force_final_diary=True,
    )

    assert result.processed_files == 1
    assert result.final_rows_filled == 1
    assert result.removed_after_discharge_rows == 0
    assert result.month_cells_filled == 0
    text = _paragraph_text(Path(result.created_files[0]))
    assert "11.06.26 First diary text" in text
    assert "12.06.26 Состояние улучшилось" in text
    assert "OLD_TABLE_CONTENT_SHOULD_NOT_BE_USED" not in text
    assert "13.06.26" not in text


def test_diary_filler_supports_merged_status_cells_once(tmp_path: Path) -> None:
    merged_status = tmp_path / "merged_status.docx"
    doc = Document()
    table = doc.add_table(rows=1, cols=2)
    merged_cell = table.cell(0, 0).merge(table.cell(0, 1))
    merged_cell.text = "Merged diary text is long enough for strict extraction and appears once."
    doc.save(merged_status)
    assert extract_statuses_from_docx(merged_status) == ["Merged diary text is long enough for strict extraction and appears once."]


def test_word_format_contract_accepts_doc_docx_docm() -> None:
    assert {".doc", ".docx", ".docm"}.issubset(SUPPORTED_WORD_SUFFIXES)
    assert is_supported_word_file("source.doc")
    assert is_supported_word_file("source.docx")
    assert is_supported_word_file("source.docm")
    assert not is_supported_word_file("source.pdf")


def test_default_diary_calendar_preserves_program_offsets_without_workday_shift() -> None:
    dates = default_observation_diary_dates(date(2026, 1, 1), limit=8)
    assert len(dates) == 8
    assert dates == tuple(dict.fromkeys(dates))
    assert dates[:4] == (date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 8))


def test_custom_diary_button_uses_block02_dates_and_texts_and_outputs_text_docx(tmp_path: Path) -> None:
    from universal_diary_generation import render_diary_documents_from_pack
    from universal_fields import PatientCase
    from universal_profiles import DocumentPack, DocumentTemplateSpec

    button_template = tmp_path / "doctor_diary_button.docx"
    template_doc = Document()
    table = template_doc.add_table(rows=64, cols=4)
    for index, header in enumerate(("Число", "Месяц", "День госпитализации", "Дневник наблюдения")):
        table.rows[0].cells[index].text = header
    table.rows[1].cells[3].text = "EMBEDDED_TABLE_TEXT_MUST_NOT_APPEAR"
    template_doc.save(button_template)

    dates_file = tmp_path / "Даты.docx"
    dates_doc = Document()
    dates_doc.add_paragraph("07.11.2025")
    dates_doc.add_paragraph("08.11.2025")
    dates_doc.save(dates_file)

    texts_file = tmp_path / "Тексты.docx"
    texts_doc = Document()
    texts_doc.add_paragraph("01.01.2026 Состояние стабильное, контактен, назначения выполняет без замечаний.")
    texts_doc.save(texts_file)

    case = PatientCase()
    case.update_from_pairs(
        {
            "patient.fio": "Агафонов Артём Алексеевич",
            "admission.date": "31.10.2025",
            "discharge.date": "08.11.2025",
        },
        confidence=1.0,
        source_document="test",
    )
    pack = DocumentPack(
        pack_id="text.diary",
        name="Text diary",
        documents=(
            DocumentTemplateSpec(
                id="doctor_diary",
                button_label="Дневники",
                template=str(button_template),
                category="diaries",
                role_id="daily_diary",
            ),
        ),
    )

    result = render_diary_documents_from_pack(
        pack=pack,
        case=case,
        document_ids=("doctor_diary",),
        output_dir=tmp_path / "out",
        base_dir=None,
        status_files=(texts_file,),
        date_files=(dates_file,),
        patient_name="Агафонов Артём Алексеевич",
        admission_value="31.10.2025",
        discharge_value="08.11.2025",
        diary_day_offsets=(1, 2, 3, 4),
        force_final_diary=True,
    )

    assert not result.skipped
    assert len(result.created_files) == 1
    rendered = Document(str(result.created_files[0]))
    assert rendered.tables == []
    text = "\n".join(paragraph.text for paragraph in rendered.paragraphs)
    assert "07.11.25" in text
    assert "Состояние стабильное" in text
    assert "08.11.25 Состояние улучшилось" in text
    assert "01.11.25" not in text
    assert "EMBEDDED_TABLE_TEXT_MUST_NOT_APPEAR" not in text


def test_custom_diary_action_forwards_selected_block02_date_files() -> None:
    import inspect

    from actions_universal_flow import ActionsUniversalFlowMixin
    from universal_diary_generation import CUSTOM_DIARY_OUTPUT_IS_TEXT_ONLY

    source = inspect.getsource(ActionsUniversalFlowMixin._create_custom_diary_documents_impl)
    assert "date_files=list(self.diary_files)" in source
    assert CUSTOM_DIARY_OUTPUT_IS_TEXT_ONLY is True
