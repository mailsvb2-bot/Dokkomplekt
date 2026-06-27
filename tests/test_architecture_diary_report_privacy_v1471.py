from __future__ import annotations

from pathlib import Path

from medical_formatting import technical_report_path
from architecture_contracts import (
    ARCHITECTURE_CONTRACT_LOCK_VERSION,
    assert_diary_reports_are_technical_and_redacted,
    assert_patient_folders_do_not_receive_technical_reports,
)


def test_diary_report_path_is_outside_patient_folder(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDICAL_AUTOFILL_HISTORY_DIR", str(tmp_path / "appdata"))
    patient_dir = tmp_path / "Выписанные пациенты" / "Иванов Иван Иванович"
    patient_dir.mkdir(parents=True)

    report_path = technical_report_path(patient_dir, "ОТЧЁТ_дневники.txt")

    assert report_path.name == "ОТЧЁТ_дневники.txt"
    assert patient_dir not in report_path.parents
    assert report_path.parent != patient_dir
    assert "_medical_autofill_history" in str(report_path)


def test_diary_batch_report_contract_is_redacted_and_centralized() -> None:
    source = Path("diary_batch.py").read_text(encoding="utf-8")

    assert 'technical_report_path(result_dir, "ОТЧЁТ_дневники.txt")' in source
    assert 'result_dir / "ОТЧЁТ_дневники.txt"' not in source
    assert "Пациент / имя файлов" not in source
    assert "ФИО для определения рода" not in source
    assert "technical_ref(patient_filename" in source
    assert "redact_technical_text" in source


def test_architecture_lock_covers_diary_reports() -> None:
    assert ARCHITECTURE_CONTRACT_LOCK_VERSION == "v2.4"
    assert_patient_folders_do_not_receive_technical_reports()
    assert_diary_reports_are_technical_and_redacted()
