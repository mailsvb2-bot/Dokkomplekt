from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import architecture_contracts
from actions_reports import ActionsReportsMixin, technical_report_path
from desktop_patient_folder import (
    PrimaryPatientFolderInfo,
    build_patient_folder_name_from_info,
    folder_naming_option_labels,
    folder_naming_uses_discharge_date,
)


class _FakeReports(ActionsReportsMixin):
    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        self.logs: list[str] = []

    def _result_output_dir(self) -> Path:
        return self.out_dir

    def _selected_output_names(self, selected_medical, selected_diaries, selected_custom=None):
        return [*selected_medical]

    def _diagnostic_reports_enabled(self) -> bool:
        return True

    def _log(self, message: str) -> None:
        self.logs.append(message)


def test_desktop_intake_folder_name_uses_doctor_popup_rule() -> None:
    info = PrimaryPatientFolderInfo(
        fio="Иванов Иван Иванович",
        admission_date="05.05.2026",
        folder_name="Иванов И.И. май 2026",
    )
    settings = {
        "parts": ["full_fio", "admission_discharge_dates"],
        "date_format": "long",
        "doctor_confirmed": True,
    }

    assert folder_naming_uses_discharge_date(settings)
    assert build_patient_folder_name_from_info(
        info,
        settings=settings,
        discharge_date="06.06.2026",
    ) == "Иванов Иван Иванович 05.05.2026-06.06.2026"


def test_folder_naming_popup_label_is_human_clean() -> None:
    labels = dict(folder_naming_option_labels())
    assert labels["surname_initials"] == "Фамилия полностью, Имя и Отчество буквами"
    assert "- буквами" not in labels["surname_initials"]


def test_technical_report_path_is_outside_patient_folder(tmp_path: Path, monkeypatch) -> None:
    patient_dir = tmp_path / "Выписанные пациенты" / "Иванов И.И. июнь 2026"
    monkeypatch.setenv("MEDICAL_AUTOFILL_HISTORY_DIR", str(tmp_path / "appdata"))

    report_path = technical_report_path(patient_dir, "custom_profile_generation_report.txt")

    assert report_path.name == "custom_profile_generation_report.txt"
    assert patient_dir not in report_path.parents
    assert "MedicalDiaryAutofill" not in str(report_path) or "_medical_autofill_history" in str(report_path)


def test_creation_debug_report_does_not_pollute_patient_folder(tmp_path: Path, monkeypatch) -> None:
    patient_dir = tmp_path / "Выписанные пациенты" / "Петров П.П. июнь 2026"
    patient_dir.mkdir(parents=True)
    monkeypatch.setenv("MEDICAL_AUTOFILL_HISTORY_DIR", str(tmp_path / "appdata"))
    app = _FakeReports(patient_dir)

    report = app._write_creation_report(
        selected_medical=["custom"],
        selected_diaries=False,
        created_medical=[],
        created_custom=[],
        errors=["test"],
    )

    assert report is not None
    assert report.exists()
    assert patient_dir not in report.parents
    assert not (patient_dir / "ОТЧЁТ_создание_документов.txt").exists()


def test_custom_generation_report_is_routed_through_history() -> None:
    source = Path("actions_universal_flow.py").read_text(encoding="utf-8")
    assert "custom_profile_generation_report.txt" in source
    assert "technical_report_path(out_dir, \"custom_profile_generation_report.txt\")" in source
    assert 'Path(out_dir) / "custom_profile_generation_report.txt"' not in source


def test_architecture_lock_v1469() -> None:
    assert architecture_contracts.ARCHITECTURE_CONTRACT_LOCK_VERSION == "v2.4"
    architecture_contracts.assert_patient_folders_do_not_receive_technical_reports()
