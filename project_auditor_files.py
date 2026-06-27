"""Filesystem and syntax scan for the project auditor."""

from __future__ import annotations

import ast
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
import unicodedata

from project_auditor_models import ProjectFinding, ProjectSeverity, finding

PROJECT_AUDITOR_FILES_LOCK_VERSION = "v1.2"
PROJECT_AUDITOR_IGNORES_GENERATED_OUTPUTS = True
PROJECT_AUDITOR_DETECTS_TEXT_ENCODING_ERRORS = True
PROJECT_AUDITOR_REJECTS_SOURCE_SYMLINKS = True
PROJECT_AUDITOR_IGNORES_SMOKE_OUTPUTS = True

IGNORED_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "build",
    "dist",
    "release",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".idea",
    ".vscode",
}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".spec", ".bak", ".tmp"}
FORBIDDEN_FILENAMES = {".DS_Store", "Thumbs.db", "startup_error.log"}
MAX_TEXT_FILE_BYTES = 2_000_000
CRITICAL_EMPTY_SUFFIXES = {".py", ".md", ".txt", ".json", ".toml", ".yml", ".yaml"}


@dataclass(frozen=True)
class ProjectFileIndex:
    root: Path
    all_files: tuple[Path, ...]
    python_files: tuple[Path, ...]

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()


def build_file_index(root: str | Path) -> ProjectFileIndex:
    base = Path(root).expanduser().resolve()
    if not base.exists():
        raise FileNotFoundError(f"Project root does not exist: {base}")
    if not base.is_dir():
        raise NotADirectoryError(f"Project root must be a directory: {base}")
    files: list[Path] = []
    for path in base.rglob("*"):
        rel_parts = path.relative_to(base).parts
        if any(_is_ignored_part(part) for part in rel_parts):
            continue
        if path.is_file():
            files.append(path)
    all_files = tuple(sorted(files, key=lambda item: item.relative_to(base).as_posix().lower()))
    python_files = tuple(path for path in all_files if path.suffix.lower() == ".py")
    return ProjectFileIndex(base, all_files, python_files)




def _is_ignored_part(part: str) -> bool:
    """Return True for directories/files that are generated, not source.

    Smoke/regression suites deliberately create ``test_run_*`` folders with
    CP1251 fixtures and generated DOCX outputs.  They are valuable runtime
    artifacts, but they must never become project-auditor source input;
    otherwise running ``smoke_test.py`` before ``project_auditor.py`` produces
    false UTF-8/source hygiene failures.
    """

    return part in IGNORED_DIR_NAMES or part.startswith("test_run") or part.endswith("_run")

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def read_text_strict(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_python(path: Path) -> ast.AST | None:
    try:
        return ast.parse(read_text(path), filename=str(path))
    except SyntaxError:
        return None


def file_hygiene_findings(index: ProjectFileIndex) -> tuple[ProjectFinding, ...]:
    findings: list[ProjectFinding] = []
    normalized_names: dict[str, str] = {}
    for path in index.all_files:
        rel = index.relative(path)
        suffix = path.suffix.lower()
        if path.is_symlink():
            findings.append(finding("FS005", "Source symlink", "В исходном архиве не должно быть symlink-файлов: они ломают переносимость и аудит путей.", ProjectSeverity.ERROR, path=rel, blocking=True))
        if suffix in CRITICAL_EMPTY_SUFFIXES:
            try:
                read_text_strict(path)
            except UnicodeDecodeError as exc:
                findings.append(finding("FS006", "Text encoding error", "Текстовый файл не читается как UTF-8 без потерь.", ProjectSeverity.ERROR, path=rel, line=exc.start + 1, evidence={"encoding_error": str(exc)}, blocking=True))
        if suffix in FORBIDDEN_SUFFIXES or path.name in FORBIDDEN_FILENAMES:
            findings.append(finding("FS001", "Generated or forbidden artifact", "В архиве найден служебный/мусорный файл.", ProjectSeverity.ERROR, path=rel, blocking=True))
        if path.stat().st_size == 0 and suffix in CRITICAL_EMPTY_SUFFIXES:
            findings.append(finding("FS002", "Empty critical file", "Критичный текстовый файл пустой.", ProjectSeverity.ERROR, path=rel, blocking=True))
        if path.stat().st_size > MAX_TEXT_FILE_BYTES and suffix in CRITICAL_EMPTY_SUFFIXES:
            findings.append(finding("FS003", "Oversized text file", "Текстовый файл слишком большой для обычного исходника проекта.", ProjectSeverity.WARNING, path=rel, evidence={"bytes": path.stat().st_size}))
        normalized = unicodedata.normalize("NFC", rel).casefold().replace("\\", "/")
        previous = normalized_names.get(normalized)
        if previous and previous != rel:
            findings.append(finding("FS004", "Case/Unicode path collision", "Пути отличаются только регистром или Unicode-нормализацией.", ProjectSeverity.ERROR, path=rel, evidence={"other": previous}, blocking=True))
        normalized_names[normalized] = rel
    return tuple(findings)


def syntax_findings(index: ProjectFileIndex) -> tuple[ProjectFinding, ...]:
    findings: list[ProjectFinding] = []
    for path in index.python_files:
        try:
            ast.parse(read_text(path), filename=str(path))
        except SyntaxError as exc:
            findings.append(
                finding(
                    "PY000",
                    "Python syntax error",
                    f"Синтаксическая ошибка Python: {exc.msg}",
                    ProjectSeverity.CRITICAL,
                    path=index.relative(path),
                    line=exc.lineno,
                    evidence={"offset": exc.offset or 0},
                    blocking=True,
                )
            )
    return tuple(findings)


def assert_project_auditor_files_lock() -> None:
    if PROJECT_AUDITOR_FILES_LOCK_VERSION != "v1.2":
        raise AssertionError("Project auditor file lock changed unexpectedly")
    if not PROJECT_AUDITOR_IGNORES_GENERATED_OUTPUTS:
        raise AssertionError("Project auditor must ignore generated output directories")
    if not PROJECT_AUDITOR_DETECTS_TEXT_ENCODING_ERRORS:
        raise AssertionError("Project auditor must detect UTF-8 text encoding errors")
    if not PROJECT_AUDITOR_REJECTS_SOURCE_SYMLINKS:
        raise AssertionError("Project auditor must reject source symlinks")
    if not PROJECT_AUDITOR_IGNORES_SMOKE_OUTPUTS:
        raise AssertionError("Project auditor must ignore generated smoke/test_run outputs")
    if not _is_ignored_part("test_run_combined") or not _is_ignored_part("stress_run"):
        raise AssertionError("Generated smoke/run directory patterns must stay ignored")
    if not hasattr(read_text, "__call__") or not hasattr(parse_python, "__call__"):
        raise AssertionError("Project auditor text/AST cache wrappers must stay callable")
    if "__pycache__" not in IGNORED_DIR_NAMES or ".pyc" not in FORBIDDEN_SUFFIXES:
        raise AssertionError("Generated Python artifacts must stay protected")
