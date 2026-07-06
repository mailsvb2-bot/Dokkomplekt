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
        "tests/test_diary_filler_donor_parity_v1490.py",
        "tests/test_regression_state_overlay_v1491.py",
        "tests/test_build_check_wiring_v1495.py",
        "tests/test_user_regressions_v1493.py",
        "tests/test_diary_manual_date_priority_v1496.py",
        "tests/test_diary_user_emulation_matrix_v1497.py",
        "tests/test_native_license_security_v1499.py",
        "tests/test_desktop_intake_patient_chain_v1502.py",
        "tests/test_text_diary_signature_lock_v1503.py",
        "tests/test_discharge_profile_routing_lock_v1504.py",
        "tests/test_anonymized_constructor_contract_v1507.py",
        "tests/test_pdf_document_io_v1508.py",
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
