from __future__ import annotations

from pathlib import Path

from universal_generation import PackGenerationResult, PackReadinessReport, save_generation_report, save_readiness_report


def test_generation_report_does_not_overwrite_previous_diagnostic_file(tmp_path: Path) -> None:
    first = save_generation_report(PackGenerationResult((), ()), tmp_path / "custom_profile_generation_report.txt")
    second = save_generation_report(PackGenerationResult((), ()), tmp_path / "custom_profile_generation_report.txt")

    assert first.exists()
    assert second.exists()
    assert first != second
    assert second.name == "custom_profile_generation_report (2).txt"


def test_readiness_report_does_not_overwrite_previous_diagnostic_file(tmp_path: Path) -> None:
    report = PackReadinessReport("doctor-pack", (), (), (), (), warnings=("Проверка",))
    first = save_readiness_report(report, tmp_path / "custom_profile_readiness_report.txt")
    second = save_readiness_report(report, tmp_path / "custom_profile_readiness_report.txt")

    assert first.exists()
    assert second.exists()
    assert first != second
    assert second.name == "custom_profile_readiness_report (2).txt"


def test_universal_generation_warning_does_not_recommend_builtin_old_templates() -> None:
    source = Path("universal_generation.py").read_text(encoding="utf-8")
    assert "Production-сценарий не подставляет встроенные медицинские шаблоны" in source
    assert "Встроенные старые шаблоны могут оставаться рабочими" not in source
