from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT_VERSION = "1.4.93"
CURRENT_VERSION_LABEL = "v1.4.93_generation_trial_hotfix"
CURRENT_VERSION_TUPLE = "(1, 4, 93, 0)"
HOTFIX_PHRASE = "discharge custom case propagation"


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

    assert "test_regression_state_overlay_v1491.py" in runner
    assert "smoke_user_reported" in runner
    assert "$PSNativeCommandUseErrorActionPreference = $true" in workflow
    assert "Smoke gate failed: $smoke" in workflow
    assert "if ($LASTEXITCODE -ne 0)" in workflow
    assert "contents: write" not in workflow
    assert "git push origin HEAD:main" not in workflow
    assert "apply-hotfix" not in workflow


def test_release_metadata_and_hotfix_notes_stay_synchronized():
    readme = _read("README.md")
    release_notes = _read("RELEASE_NOTES.md")
    app_config = _read("app_config.py")
    pyproject = _read("pyproject.toml")
    version_info = _read("version_info.txt")
    baseline = _read("BASELINE_VERSION.txt")

    assert f"Version: `{CURRENT_VERSION_LABEL}`" in readme.splitlines()[:8]
    assert release_notes.lstrip().startswith(f"# Release notes — {CURRENT_VERSION_LABEL}")
    assert f'APP_VERSION = "{CURRENT_VERSION_LABEL}"' in app_config
    assert f'version = "{CURRENT_VERSION}"' in pyproject
    assert f"filevers={CURRENT_VERSION_TUPLE}" in version_info
    assert f"prodvers={CURRENT_VERSION_TUPLE}" in version_info
    assert f"StringStruct('FileVersion', '{CURRENT_VERSION_LABEL}')" in version_info
    assert f"StringStruct('ProductVersion', '{CURRENT_VERSION_LABEL}')" in version_info
    assert CURRENT_VERSION_LABEL in baseline
    assert HOTFIX_PHRASE in readme
    assert HOTFIX_PHRASE in release_notes
