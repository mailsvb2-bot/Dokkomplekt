"""Runner for the split combined smoke regression suite.

The split files are intentionally executable both through ``smoke_test.py`` and
as individual scripts.  Several regressions were previously hidden because
part02+ depended on globals created by part01 and therefore crashed with
``NameError`` when a developer ran a single part directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

PARTS = (
    "smoke_combined_part01_setup_contracts.py",
    "smoke_combined_part02_ui_parser_regressions.py",
    "smoke_combined_part03_medical_parser_manual.py",
    "smoke_combined_part04_medical_generation.py",
    "smoke_combined_part05_diary_basic_templates.py",
    "smoke_combined_part06_diary_columns_settings.py",
)


def _root() -> Path:
    return Path(__file__).resolve().parent


def _base_namespace(entry_file: str = "smoke_test_combined.py") -> dict[str, object]:
    root = _root()
    return {
        "__name__": "__smoke_combined__",
        "__file__": str(root / entry_file),
        "_SMOKE_COMBINED_RUNNER_ACTIVE": True,
    }


def _exec_part(part_name: str, namespace: dict[str, object]) -> None:
    root = _root()
    part_path = root / part_name
    code = compile(part_path.read_text(encoding="utf-8"), str(part_path), "exec")
    namespace["__file__"] = str(part_path)
    exec(code, namespace, namespace)


def build_namespace_before(part_name: str) -> dict[str, object]:
    """Execute all split-smoke dependencies before ``part_name``.

    Used by direct execution of ``smoke_combined_part02+``.  The returned
    namespace contains exactly the globals that the combined runner would have
    produced before reaching that part.
    """

    normalized = Path(part_name).name
    if normalized not in PARTS:
        raise ValueError(f"Unknown combined smoke part: {part_name}")
    namespace = _base_namespace(entry_file=normalized)
    for dependency in PARTS:
        if dependency == normalized:
            break
        _exec_part(dependency, namespace)
    namespace.pop("_SMOKE_COMBINED_RUNNER_ACTIVE", None)
    namespace["__file__"] = str(_root() / normalized)
    return namespace


def run(parts: Iterable[str] | None = None) -> None:
    selected = tuple(Path(part).name for part in (parts or PARTS))
    unknown = [part for part in selected if part not in PARTS]
    if unknown:
        raise ValueError("Unknown combined smoke parts: " + ", ".join(unknown))
    namespace = _base_namespace()
    executed: set[str] = set()
    # Keep partial runs safe too: if a later split file is requested, execute
    # its dependencies first so ``run(["part03"])`` behaves like direct script
    # execution instead of failing with missing globals.
    for part_name in PARTS:
        if part_name in selected or any(PARTS.index(part_name) < PARTS.index(target) for target in selected):
            _exec_part(part_name, namespace)
            executed.add(part_name)
        if set(selected).issubset(executed):
            break
