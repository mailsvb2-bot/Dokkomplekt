"""Import graph and layer checks for the project auditor."""

from __future__ import annotations

import ast
from pathlib import Path

from project_auditor_files import ProjectFileIndex, parse_python
from project_auditor_models import ProjectFinding, ProjectSeverity, finding

PROJECT_AUDITOR_IMPORTS_LOCK_VERSION = "v1.0"
PROJECT_AUDITOR_DETECTS_CYCLES = True
PROJECT_AUDITOR_CORE_IS_UI_FREE = True

CORE_PREFIXES = (
    "universal_",
    "regulatory_",
    "medical_language_",
    "medical_orthography",
    "personal_document_buttons",
    "auditor_",
    "project_auditor",
)
UI_OR_ACTION_PREFIXES = ("window_", "layout_", "dialog_", "actions_", "widgets_", "settings_", "dnd_", "files_mixin")
FORBIDDEN_CORE_IMPORT_ROOTS = {"tkinter", "customtkinter", "PyQt5", "PySide6", "window_mixin", "layout_mixin", "dialogs_mixin", "actions_mixin"}


def import_roots(path: Path) -> set[str]:
    tree = parse_python(path)
    if tree is None:
        return set()
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def local_import_graph(index: ProjectFileIndex) -> dict[str, set[str]]:
    local_modules = {path.stem for path in index.python_files}
    graph: dict[str, set[str]] = {path.stem: set() for path in index.python_files}
    for path in index.python_files:
        graph[path.stem].update(root for root in import_roots(path) if root in local_modules)
    return graph


def _cycles(graph: dict[str, set[str]]) -> tuple[tuple[str, ...], ...]:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []
    result: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()

    def normalize(cycle: list[str]) -> tuple[str, ...]:
        body = cycle[:-1]
        rotations = [tuple(body[i:] + body[:i]) for i in range(len(body))]
        best = min(rotations)
        return (*best, best[0])

    def dfs(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            if node in stack:
                start = stack.index(node)
                normalized = normalize([*stack[start:], node])
                if normalized not in seen:
                    seen.add(normalized)
                    result.append(normalized)
            return
        visiting.add(node)
        stack.append(node)
        for child in sorted(graph.get(node, ())):
            dfs(child)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        dfs(node)
    return tuple(result)


def import_findings(index: ProjectFileIndex) -> tuple[ProjectFinding, ...]:
    findings: list[ProjectFinding] = []
    graph = local_import_graph(index)
    for cycle in _cycles(graph):
        findings.append(finding("IMP001", "Local import cycle", "Найдена циклическая зависимость: " + " -> ".join(cycle), ProjectSeverity.ERROR, evidence={"cycle": cycle}, blocking=True))
    for path in index.python_files:
        stem = path.stem
        if not stem.startswith(CORE_PREFIXES):
            continue
        roots = import_roots(path)
        forbidden = sorted(root for root in roots if root in FORBIDDEN_CORE_IMPORT_ROOTS or root.startswith(UI_OR_ACTION_PREFIXES))
        if forbidden:
            findings.append(
                finding(
                    "IMP002",
                    "Core imports UI/action layer",
                    "Core/universal/regulatory/auditor слой импортирует UI/action зависимость.",
                    ProjectSeverity.ERROR,
                    path=index.relative(path),
                    evidence={"forbidden_imports": forbidden},
                    blocking=True,
                )
            )
    return tuple(findings)


def assert_project_auditor_imports_lock() -> None:
    if PROJECT_AUDITOR_IMPORTS_LOCK_VERSION != "v1.0":
        raise AssertionError("Project auditor imports lock changed unexpectedly")
    if not PROJECT_AUDITOR_DETECTS_CYCLES:
        raise AssertionError("Project auditor must detect local import cycles")
    if not PROJECT_AUDITOR_CORE_IS_UI_FREE:
        raise AssertionError("Project auditor core checks must stay UI-free")
