"""Report writers for the project auditor."""

from __future__ import annotations

from pathlib import Path

from project_auditor_models import ProjectAuditReport

PROJECT_AUDITOR_REPORTS_LOCK_VERSION = "v1.0"
PROJECT_AUDITOR_REPORTS_ARE_LOCAL_ONLY = True


def write_json_report(report: ProjectAuditReport, path: str | Path) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report.to_json(), encoding="utf-8")
    return target


def write_text_report(report: ProjectAuditReport, path: str | Path) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report.human_report() + "\n", encoding="utf-8")
    return target


def assert_project_auditor_reports_lock() -> None:
    if PROJECT_AUDITOR_REPORTS_LOCK_VERSION != "v1.0":
        raise AssertionError("Project auditor reports lock changed unexpectedly")
    if not PROJECT_AUDITOR_REPORTS_ARE_LOCAL_ONLY:
        raise AssertionError("Project auditor reports must stay local-only")
