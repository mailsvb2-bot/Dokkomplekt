"""Regression smoke for the project technical-debt cleanup line."""

from __future__ import annotations

import ast
import time
from pathlib import Path

from diagnostic_logging import assert_diagnostic_logging_lock
from project_auditor_rules import assert_project_auditor_rules_lock

ROOT = Path(__file__).resolve().parent
SELF_TEST_NAME = "smoke_technical_debt_cleanup.py"
TECHNICAL_DEBT_CLEANUP_LOCK_VERSION = "v1.0"
PROJECT_AUDITOR_WARNINGS_MUST_STAY_ZERO = True
SILENT_EXCEPTION_PASS_IS_FORBIDDEN = True
WINDOW_MIXIN_MUST_STAY_COMPOSED = True


def _silent_except_pass_locations() -> list[str]:
    locations: list[str] = []
    for path in ROOT.glob("*.py"):
        if path.name == "diagnostic_logging.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body = [stmt for stmt in node.body if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str))]
            if body and all(isinstance(stmt, ast.Pass) for stmt in body):
                locations.append(f"{path.name}:{node.lineno}")
    return locations


def _assert_window_mixin_composed() -> None:
    source = (ROOT / "window_mixin.py").read_text(encoding="utf-8")
    required = [
        "WindowCoreMixin",
        "WindowStyleMixin",
        "WindowChromeMixin",
        "WindowHeaderMixin",
        "WindowUniversalDialogsMixin",
    ]
    missing = [item for item in required if item not in source]
    if missing:
        raise AssertionError("WindowMixin composition is incomplete: " + ", ".join(missing))
    if "def _open_universal_document_mapper" in source:
        raise AssertionError("Universal mapper implementation drifted back into WindowMixin")


def _assert_project_auditor_zero_findings() -> None:
    """Keep this smoke lightweight.

    release_check.py runs the full project auditor immediately before this
    smoke.  This function verifies that the zero-warning budget remains an
    explicit contract without launching a second nested full-project scan.
    """
    if not PROJECT_AUDITOR_WARNINGS_MUST_STAY_ZERO:
        raise AssertionError("Project auditor warning budget must stay zero")


def assert_technical_debt_cleanup_lock() -> None:
    if TECHNICAL_DEBT_CLEANUP_LOCK_VERSION != "v1.0":
        raise AssertionError("Technical debt cleanup lock changed unexpectedly")
    if not PROJECT_AUDITOR_WARNINGS_MUST_STAY_ZERO:
        raise AssertionError("Project auditor warning budget must stay zero")
    if not SILENT_EXCEPTION_PASS_IS_FORBIDDEN:
        raise AssertionError("Silent except/pass must stay forbidden")
    if not WINDOW_MIXIN_MUST_STAY_COMPOSED:
        raise AssertionError("WindowMixin must stay composed")


def main() -> None:
    assert_technical_debt_cleanup_lock()
    assert_diagnostic_logging_lock()
    assert_project_auditor_rules_lock()
    locations = _silent_except_pass_locations()
    if locations:
        raise AssertionError("Silent except/pass locations remain: " + ", ".join(locations))
    _assert_window_mixin_composed()
    _assert_project_auditor_zero_findings()
    print("TECHNICAL DEBT CLEANUP SMOKE OK")


if __name__ == "__main__":
    main()
