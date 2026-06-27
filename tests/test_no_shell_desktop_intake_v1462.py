from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _calls_function(source: str, function_name: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == function_name:
            return True
        if isinstance(func, ast.Attribute) and func.attr == function_name:
            return True
    return False


def test_desktop_intake_startup_does_not_auto_refresh_printers() -> None:
    source = _source("app_initialization.py")
    assert "refresh_printers(silent=True)" not in source
    assert "_bootstrap_printer_field_without_shell_scan" in source


def test_printer_runtime_has_no_shell_fallbacks() -> None:
    for name in ("printer_discovery.py", "printer_jobs.py"):
        lowered = _source(name).lower()
        assert "powershell" not in lowered
        assert "get-ciminstance" not in lowered
        assert "wscript.network" not in lowered


def test_printer_discovery_and_jobs_do_not_spawn_subprocesses() -> None:
    for name in ("printer_discovery.py", "printer_jobs.py"):
        source = _source(name)
        assert "import subprocess" not in source
        assert not _calls_function(source, "run")
        assert not _calls_function(source, "Popen")


def test_printer_field_bootstrap_preserves_saved_printer_without_scan() -> None:
    source = _source("app_initialization.py")
    assert "self.printer_var.set(saved)" in source
    assert "list_printers" not in source[source.index("def _bootstrap_printer_field_without_shell_scan"):source.index("def _bootstrap_ui")]
