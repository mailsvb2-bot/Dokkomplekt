from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_build_checks_are_wired_into_ci_and_release_gate():
    workflow = _read(".github/workflows/windows-build.yml")
    release = _read("release_check.py")
    runner = _read("tools/run_regression_contour.py")

    for snippet in (
        "python -m ruff check .",
        "python -m mypy --config-file pyproject.toml",
        "python -m pytest tests",
        "python tools/run_regression_contour.py",
        "python prod_audit.py",
        "python release_check.py",
        "build_exe_windows.bat",
        "--cov-fail-under",
    ):
        assert snippet in workflow

    for snippet in (
        "_assert_architecture_contracts()",
        "quality_modernization_smoke_main()",
        "full_patient_replay_smoke_main()",
    ):
        assert snippet in release

    for snippet in (
        "test_user_reported_regressions_v1492.py",
        "test_regression_state_overlay_v1491.py",
    ):
        assert snippet in runner
