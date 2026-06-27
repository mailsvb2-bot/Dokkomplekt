"""Deterministic project auditor CLI.

This scans the project itself: syntax, imports, dependencies, architecture
boundaries, god modules, dust artifacts and deterministic AST rules.  It is a
quality gate, not a proof engine.  It deliberately uses only the standard
library and never imports application UI or heavy DOCX runtime modules.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import time

from project_auditor_dependencies import assert_project_auditor_dependencies_lock, dependency_findings
from project_auditor_files import assert_project_auditor_files_lock, build_file_index, file_hygiene_findings, syntax_findings
from project_auditor_imports import assert_project_auditor_imports_lock, import_findings
from project_auditor_models import ProjectAuditReport, assert_project_auditor_models_lock, merge_findings
from project_auditor_reports import assert_project_auditor_reports_lock, write_json_report, write_text_report
from project_auditor_rules import assert_project_auditor_rules_lock, ast_rule_findings

PROJECT_AUDITOR_LOCK_VERSION = "v1.0"
PROJECT_AUDITOR_IS_PROJECT_SCANNER = True
PROJECT_AUDITOR_HAS_NO_UI_DEPENDENCY = True
PROJECT_AUDITOR_CI_FAILS_ON_ERRORS_ONLY = True


def audit_project(root: str | Path = ".") -> ProjectAuditReport:
    started = time.perf_counter()
    index = build_file_index(root)
    findings = merge_findings(
        (
            file_hygiene_findings(index),
            syntax_findings(index),
            import_findings(index),
            ast_rule_findings(index),
            dependency_findings(index),
        )
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return ProjectAuditReport(
        title="Аудит проекта MedicalDiaryAutofill",
        target=str(index.root),
        findings=findings,
        scanned_files=len(index.all_files),
        scanned_python_files=len(index.python_files),
        duration_ms=elapsed_ms,
    )


def assert_project_auditor_lock() -> None:
    if PROJECT_AUDITOR_LOCK_VERSION != "v1.0":
        raise AssertionError("Project auditor lock changed unexpectedly")
    if not PROJECT_AUDITOR_IS_PROJECT_SCANNER:
        raise AssertionError("Project auditor must scan the project itself")
    if not PROJECT_AUDITOR_HAS_NO_UI_DEPENDENCY:
        raise AssertionError("Project auditor must stay UI-free")
    if not PROJECT_AUDITOR_CI_FAILS_ON_ERRORS_ONLY:
        raise AssertionError("Project auditor CI policy must stay explicit")
    assert_project_auditor_models_lock()
    assert_project_auditor_files_lock()
    assert_project_auditor_imports_lock()
    assert_project_auditor_rules_lock()
    assert_project_auditor_dependencies_lock()
    assert_project_auditor_reports_lock()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan this project for syntax, import, dependency and architecture risks.")
    parser.add_argument("root", nargs="?", default=".", help="Project root to scan")
    parser.add_argument("--ci", action="store_true", help="Exit non-zero when blocking errors are found")
    parser.add_argument("--json", dest="json_report", default="", help="Write JSON report to this path")
    parser.add_argument("--text", dest="text_report", default="", help="Write human-readable report to this path")
    parser.add_argument("--quiet", action="store_true", help="Print only a compact status line")
    args = parser.parse_args(argv)

    assert_project_auditor_lock()
    report = audit_project(args.root)
    if args.json_report:
        write_json_report(report, args.json_report)
    if args.text_report:
        write_text_report(report, args.text_report)
    if args.quiet:
        print(f"PROJECT AUDITOR {'OK' if report.ok else 'FAILED'} score={report.score} errors={len(report.errors)} files={report.scanned_python_files}")
    else:
        print(report.human_report())
    if args.ci and not report.ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
