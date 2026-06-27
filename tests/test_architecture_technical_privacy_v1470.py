from __future__ import annotations

from pathlib import Path

import architecture_contracts
from medical_formatting import assert_technical_privacy_lock, redact_technical_text, technical_ref
from medical_service import BatchGenerationResult, BatchItemResult, save_batch_generation_report
from universal_generation import PackGenerationResult, save_generation_report


def test_technical_redaction_removes_paths_dates_and_case_numbers() -> None:
    assert_technical_privacy_lock()
    text = r"C:\Users\Doctor\Выписанные пациенты\Иванов И.И\doc.docx 11.06.2026 история болезни № 123"
    redacted = redact_technical_text(text)
    assert "Иванов" not in redacted
    assert "11.06.2026" not in redacted
    assert "123" not in redacted
    assert "Users" not in redacted
    assert technical_ref(text).startswith("ref-")


def test_batch_generation_report_is_redacted(tmp_path: Path) -> None:
    result = BatchGenerationResult(
        items=(
            BatchItemResult(
                source=r"C:\patients\Иванов И.И первичный.docx",
                patient_label="Иванов Иван Иванович",
                output_dir=r"C:\Users\Doctor\Выписанные пациенты\Иванов И.И",
                created_files=(r"C:\Users\Doctor\Выписанные пациенты\Иванов И.И\Иванов эпикриз.docx",),
            ),
        ),
        output_root=r"C:\Users\Doctor\Выписанные пациенты",
        selected_docs=("discharge",),
    )
    report = save_batch_generation_report(result, tmp_path / "batch_generation_report.txt")
    text = report.read_text(encoding="utf-8")
    assert "Иванов" not in text
    assert "Users" not in text
    assert "ref-" in text
    assert "создано файлов" in text


def test_universal_generation_report_is_redacted(tmp_path: Path) -> None:
    result = PackGenerationResult(
        created_files=(r"C:\Users\Doctor\Выписанные пациенты\Петров П.П\Петров custom.docx",),
        render_results=(),
        skipped_documents=(r"C:\шаблоны\Петров missing.docx 11.06.2026",),
        warnings=("история болезни № 77 не заполнена",),
    )
    report = save_generation_report(result, tmp_path / "custom_generation_report.txt")
    text = report.read_text(encoding="utf-8")
    assert "Петров" not in text
    assert "11.06.2026" not in text
    assert "77" not in text
    assert "ref-" in text


def test_architecture_lock_v20_includes_technical_privacy_gate() -> None:
    assert architecture_contracts.ARCHITECTURE_CONTRACT_LOCK_VERSION == "v2.4"
    architecture_contracts.assert_technical_reports_are_privacy_safe()
