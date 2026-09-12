from __future__ import annotations

from pathlib import Path

from docx import Document

from diary_batch import TEXT_DIARY_SIGNATURE_LINES, fill_diary_batch


def _status_docx(path: Path) -> None:
    doc = Document()
    doc.add_paragraph("Состояние стабильное, жалоб активно не предъявляет, назначения выполняет.")
    doc.add_paragraph("Состояние спокойное, сон и аппетит без существенной отрицательной динамики.")
    doc.save(path)


def _paragraphs(path: Path) -> list[str]:
    return [paragraph.text.strip() for paragraph in Document(str(path)).paragraphs if paragraph.text.strip()]


def test_text_diary_has_doctor_and_head_signature_after_each_daily_entry(tmp_path):
    texts = tmp_path / "texts.docx"
    _status_docx(texts)

    result = fill_diary_batch(
        status_files=[texts],
        diary_files=[],
        output_dir=tmp_path / "out",
        patient_name="Иванов И.И.",
        admission_value="10.06.2026",
        discharge_value="12.06.2026",
        gender_source_name="Иванов И.И.",
        diary_day_offsets=(1, 2),
        force_final_diary=True,
    )

    lines = _paragraphs(result.created_files[0])
    diary_lines = [line for line in lines if line.startswith(("11.06.26", "12.06.26"))]
    assert len(diary_lines) == 2
    for diary_line in diary_lines:
        index = lines.index(diary_line)
        assert lines[index + 1:index + 3] == list(TEXT_DIARY_SIGNATURE_LINES)


def test_text_diary_has_doctor_and_head_signature_after_each_hourly_entry(tmp_path):
    texts = tmp_path / "texts.docx"
    _status_docx(texts)

    result = fill_diary_batch(
        status_files=[texts],
        diary_files=[],
        output_dir=tmp_path / "out",
        patient_name="Иванов И.И.",
        admission_value="10.06.2026 14:00",
        gender_source_name="Иванов И.И.",
        diary_hour_offsets=(1,),
        diary_frequency_mode="hourly",
        force_final_diary=False,
    )

    lines = _paragraphs(result.created_files[0])
    for prefix in ("10.06.26 15:00", "10.06.26 16:00"):
        index = next(index for index, line in enumerate(lines) if line.startswith(prefix))
        assert lines[index + 1:index + 3] == list(TEXT_DIARY_SIGNATURE_LINES)


def test_profile_diary_preserves_source_doctor_and_head_signatures(tmp_path):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from universal_diary_generation import render_diary_documents_from_pack
    from universal_fields import PatientCase
    from universal_profiles import DocumentPack, DocumentTemplateSpec

    texts = tmp_path / "texts-profile.docx"
    _status_docx(texts)
    template = tmp_path / "profile-diary.docx"
    Document().save(template)
    case = PatientCase()
    case.update_from_pairs(
        {
            "patient.fio": "Иванов Иван Иванович",
            "admission.date": "10.06.2026",
            "discharge.date": "12.06.2026",
            "doctor.name": "Балаганин С.В.",
            "head.name": "Можарова Е.А.",
        }
    )
    pack = DocumentPack(
        pack_id="signature-lock",
        name="signature-lock",
        documents=(
            DocumentTemplateSpec(
                id="doctor_diary",
                button_label="Дневники наблюдения",
                template=str(template),
                category="diaries",
                role_id="daily_diary",
            ),
        ),
    )
    result = render_diary_documents_from_pack(
        pack=pack,
        case=case,
        document_ids=("doctor_diary",),
        output_dir=tmp_path / "profile-out",
        base_dir=None,
        status_files=(texts,),
        patient_name="Иванов Иван Иванович",
        admission_value="10.06.2026",
        discharge_value="12.06.2026",
        diary_day_offsets=(1,),
        force_final_diary=False,
    )
    assert not result.skipped
    doc = Document(str(result.created_files[0]))
    signatures = [p for p in doc.paragraphs if p.text.startswith(("Лечащий врач", "Зав.отделением"))]
    assert signatures
    assert len(signatures) % 2 == 0
    assert [p.text for p in signatures] == [
        expected
        for _ in range(len(signatures) // 2)
        for expected in (
            "Лечащий врач Балаганин С.В.",
            "Зав.отделением Можарова Е.А.",
        )
    ]
    assert all(p.alignment == WD_ALIGN_PARAGRAPH.RIGHT for p in signatures)
