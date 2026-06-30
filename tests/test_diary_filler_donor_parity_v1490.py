from __future__ import annotations

from datetime import date
from pathlib import Path

from docx import Document

from diary_batch import (
    DynamicEpicrisisInput,
    build_dynamic_epicrisis_text,
    default_observation_diary_dates,
    fill_diary_batch,
    is_non_working_day,
)
from diary_text_parser import extract_statuses_from_docx
from medical_word_format import SUPPORTED_WORD_SUFFIXES, is_supported_word_file


def _joined_table_text(path: Path) -> str:
    doc = Document(str(path))
    return "\n".join("\t".join(cell.text for cell in row.cells) for table in doc.tables for row in table.rows)


def _read_docx_paragraphs(path: Path) -> list[str]:
    return [paragraph.text for paragraph in Document(str(path)).paragraphs if paragraph.text.strip()]


def test_diary_filler_donor_parity_preserves_signature_and_removes_after_discharge(tmp_path: Path) -> None:
    """Lock the useful diary-filler behavior that Dokkomplekt must keep."""

    status_docx = tmp_path / "texts.docx"
    source = Document()
    source.add_paragraph("01.06.2026 Пациент был спокоен, жалоб активно не предъявлял, в беседе доступен, инструкции выполнял.")
    source.add_paragraph("02.06.2026 Пациент сообщил об улучшении сна, фон настроения ровный, поведение упорядоченное.")
    source.add_paragraph("02.06.2026 Пациент сообщил об улучшении сна, фон настроения ровный, поведение упорядоченное.")
    source.save(status_docx)
    assert len(extract_statuses_from_docx(status_docx)) == 2

    table_docx = tmp_path / "diary_table.docx"
    template = Document()
    table = template.add_table(rows=1, cols=4)
    for index, header in enumerate(["№", "Число", "Месяц/год", "Дневник наблюдения"]):
        table.rows[0].cells[index].text = header
    for day in [10, 11, 12, 13, 14, 15]:
        row = table.add_row()
        row.cells[0].text = str(day)
        row.cells[1].text = str(day)
        row.cells[2].text = ""
        row.cells[3].text = "Лечащий врач Иванов И.И."
    template.save(table_docx)

    result = fill_diary_batch(
        status_files=[status_docx],
        diary_files=[table_docx],
        output_dir=tmp_path / "out",
        patient_name="Иванова Ирина Ивановна",
        admission_value="10.06.2026",
        discharge_value="12.06.2026",
        repeat_statuses=True,
        reset_each_file=True,
        keep_signature=True,
        fill_months=True,
        force_final_diary=True,
        remove_holiday_rows=True,
    )

    assert result.processed_files == 1
    assert result.filled_rows >= 2
    assert result.final_rows_filled == 1
    assert result.removed_after_discharge_rows == 3
    assert result.month_cells_filled >= 3
    assert result.report_path is None

    text = _joined_table_text(Path(result.created_files[0]))
    assert "Пациентка была спокойна" in text
    assert "не предъявляла" in text
    assert "Лечащий врач Иванов И.И." in text
    assert "13\t13" not in text


def test_diary_filler_donor_parity_supports_merged_status_cells_once(tmp_path: Path) -> None:
    """Merged Word cells must not duplicate one diary text into several rows."""

    merged_status = tmp_path / "merged_status.docx"
    doc = Document()
    table = doc.add_table(rows=1, cols=2)
    merged_cell = table.cell(0, 0).merge(table.cell(0, 1))
    merged_cell.text = "Пациент был спокоен, жалоб активно не предъявлял, в беседе доступен, инструкции выполнял."
    doc.save(merged_status)

    assert extract_statuses_from_docx(merged_status) == [
        "Пациент был спокоен, жалоб активно не предъявлял, в беседе доступен, инструкции выполнял."
    ]


def test_word_format_contract_accepts_doc_docx_docm() -> None:
    assert {".doc", ".docx", ".docm"}.issubset(SUPPORTED_WORD_SUFFIXES)
    assert is_supported_word_file("source.doc")
    assert is_supported_word_file("source.docx")
    assert is_supported_word_file("source.docm")
    assert not is_supported_word_file("source.pdf")


def test_default_diary_calendar_skips_weekends_and_fixed_holidays() -> None:
    dates = default_observation_diary_dates(date(2026, 1, 1), limit=8)
    assert len(dates) == 8
    assert dates == tuple(dict.fromkeys(dates))
    assert all(not is_non_working_day(item) for item in dates)
    assert dates[0] >= date(2026, 1, 12)


def test_text_diary_output_uses_selected_texts_gender_and_periodic_summary(tmp_path: Path) -> None:
    texts = tmp_path / "texts.docx"
    source = Document()
    source.add_paragraph("Пациент был спокоен, жалоб активно не предъявлял, инструкции выполнял.")
    source.add_paragraph("Пациент сообщил об улучшении сна, фон настроения ровный, поведение упорядоченное.")
    source.save(texts)

    result = fill_diary_batch(
        status_files=[texts],
        diary_files=[],
        output_dir=tmp_path / "out",
        patient_name="Иванова Ирина Ивановна",
        gender_source_name="Иванова Ирина Ивановна",
        admission_value="10.06.2026",
        discharge_value="30.06.2026",
        repeat_statuses=True,
        text_output=True,
        sick_leave_dynamic_epicrisis=True,
        sick_leave_from="10.06.2026",
        birth_date="01.01.1980",
        complaints="жалобы уменьшились",
        treatment="терапия по назначению",
        profile_status="контакт доступен",
        treatment_correction="Коррекция терапии не требуется.",
    )

    assert result.processed_files == 1
    assert result.created_files[0].exists()
    joined = "\n".join(_read_docx_paragraphs(Path(result.created_files[0])))
    assert "Пациентка была спокойна" in joined
    assert "не предъявляла" in joined
    assert "Динамический эпикриз" in joined
    assert "Продолжение лечения" in joined
    assert "Заведующий отделением" in joined
    assert "Лечащий врач" in joined


def test_dynamic_summary_fallback_correction_text() -> None:
    text = build_dynamic_epicrisis_text(DynamicEpicrisisInput(patient_name="Петров Пётр", sick_leave_from="01.06.2026"))
    assert "Лекарства принимает согласно назначениям." in text
    assert "Продолжение лечения" in text
