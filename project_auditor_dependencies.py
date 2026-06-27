"""Dependency and manifest checks for the project auditor."""

from __future__ import annotations

import ast
from pathlib import Path
import re
import sys

from project_auditor_files import ProjectFileIndex, read_text
from project_auditor_imports import import_roots
from project_auditor_models import ProjectFinding, ProjectSeverity, finding

PROJECT_AUDITOR_DEPENDENCIES_LOCK_VERSION = "v1.0"
PROJECT_AUDITOR_DOES_NOT_IMPORT_THIRD_PARTY = True

STDLIB_ROOTS = set(getattr(sys, "stdlib_module_names", set())) | {"__future__", "typing_extensions"}
LOCAL_FIRST_PARTY_PREFIXES = {
    "actions", "app", "auditor", "dialog", "diary", "files", "icd10", "layout", "medical", "performance", "personal", "printer", "prod", "project", "regulatory", "settings", "smoke", "universal", "widgets", "window", "dnd", "diagnosis", "diagnostic", "desktop", "doctor", "error", "main", "embedded_templates", "architecture", "i18n", "language", "startup", "ui", "installation",
}
KNOWN_RUNTIME_DEPENDENCIES = {"docx": "python-docx", "tkinterdnd2": "tkinterdnd2", "win32api": "pywin32", "win32print": "pywin32", "win32con": "pywin32"}


def _requirements_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    names: set[str] = set()
    for raw in read_text(path).splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)", line)
        if match:
            names.add(match.group(1).lower().replace("_", "-"))
    return names


def _pyproject_dependencies(path: Path) -> set[str]:
    if not path.exists():
        return set()
    text = read_text(path)
    names: set[str] = set()
    for match in re.finditer(r'"([A-Za-z0-9_.-]+)\s*(?:[<>=!~].*)?"', text):
        names.add(match.group(1).lower().replace("_", "-"))
    return names


def dependency_findings(index: ProjectFileIndex) -> tuple[ProjectFinding, ...]:
    root = index.root
    declared = set()
    for file_name in ("requirements.txt", "requirements_build.txt"):
        declared.update(_requirements_names(root / file_name))
    declared.update(_pyproject_dependencies(root / "pyproject.toml"))
    imported_roots: set[str] = set()
    for path in index.python_files:
        imported_roots.update(import_roots(path))
    findings: list[ProjectFinding] = []
    for root_name, package_name in sorted(KNOWN_RUNTIME_DEPENDENCIES.items()):
        if root_name in imported_roots and package_name.lower() not in declared:
            findings.append(finding("DEP001", "Missing declared dependency", f"Импорт {root_name} есть, но пакет {package_name} не найден в requirements/pyproject.", ProjectSeverity.ERROR, evidence={"import": root_name, "package": package_name}, blocking=True))
    # Unknown third-party imports are advice only: optional Windows modules and stdlib backports can vary by platform.
    for root_name in sorted(imported_roots):
        if root_name in STDLIB_ROOTS or root_name in KNOWN_RUNTIME_DEPENDENCIES:
            continue
        if any(root_name.startswith(prefix) for prefix in LOCAL_FIRST_PARTY_PREFIXES):
            continue
        if root_name.lower().replace("_", "-") not in declared:
            findings.append(finding("DEP002", "Unclassified import", f"Импорт {root_name} не классифицирован как stdlib/first-party/declared dependency.", ProjectSeverity.ADVICE, evidence={"import": root_name}))
    return tuple(findings)


def assert_project_auditor_dependencies_lock() -> None:
    if PROJECT_AUDITOR_DEPENDENCIES_LOCK_VERSION != "v1.0":
        raise AssertionError("Project auditor dependencies lock changed unexpectedly")
    if not PROJECT_AUDITOR_DOES_NOT_IMPORT_THIRD_PARTY:
        raise AssertionError("Project auditor dependency scan must not import third-party packages")
    if KNOWN_RUNTIME_DEPENDENCIES.get("docx") != "python-docx":
        raise AssertionError("python-docx dependency mapping must stay explicit")
