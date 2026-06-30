from __future__ import annotations

from pathlib import Path

from docx import Document

from diary_batch import fill_diary_batch
from diary_text_parser import extract_statuses_from_docx


def _joined_table_text(path: Path) -> str:
    doc = Document(str(path))
    return "\n".join("\t".join(cell.text for cell in row.cells) for table in doc.tables for row in table.rows)


def test_diary_filler_donor_parity_preserves_signature_and_removes_after_discharge(tmp_path: Path) -> None:
    """Lock the useful diary-filler behavior that Dokkomplekt must keep.

    The donor repository mailsvb2-bot/diary-filler already had the correct diary
    mechanics: read unique statuses from DOCX, copy the doctor's diary table,
    preserve the signature paragraph, fill month/year, adapt grammar by patient
    gender, force the discharge/final diary row, and remove rows after discharge.
    Dokkomplekt is doctor-owned and must keep this behavior without restoring
    old bundled/narrow-profile document templates.
    """

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
