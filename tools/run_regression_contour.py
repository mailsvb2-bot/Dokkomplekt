"""Run the strict baseline regression contour.

This command is intentionally separate from release_check.py.  It catches
user-facing regressions early, before packaging or EXE building starts.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COMMANDS: tuple[tuple[str, ...], ...] = (
    (sys.executable, "-m", "compileall", "-q", "."),
    (
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/test_regression_contour_baseline_v1486.py",
        "tests/test_button_management_popup_values_folder_v1484.py",
        "tests/test_contextual_role_disambiguation_v1482.py",
        "tests/test_docx_placeholder_camelcase_regression_v1483.py",
        "tests/test_production_interaction_matrix_v1487.py",
    ),
    (sys.executable, "smoke_user_reported_regressions.py"),
    (sys.executable, "smoke_followup_regressions.py"),
    (sys.executable, "smoke_full_patient_replay.py"),
    (sys.executable, "smoke_desktop_diary_workflow.py"),
    (sys.executable, "project_auditor.py", ".", "--ci", "--quiet"),
)


def _run(command: tuple[str, ...], *, timeout: int = 240) -> None:
    print("$ " + " ".join(command), flush=True)
    env = dict(os.environ)
    env.setdefault("CI", "1")
    env.setdefault("MEDICAL_AUTOFILL_DISABLE_AUTOSTART", "1")
    subprocess.run(command, cwd=ROOT, env=env, timeout=timeout, check=True)


def main() -> None:
    for command in COMMANDS:
        _run(command)
    print("STRICT REGRESSION CONTOUR OK")


if __name__ == "__main__":
    main()
