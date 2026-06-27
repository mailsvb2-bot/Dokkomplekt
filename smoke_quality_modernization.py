from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _missing_large_docstrings() -> list[str]:
    missing: list[str] = []
    for path in sorted(ROOT.glob("*.py")):
        if path.name.startswith(("smoke", "test_", "release_check", "prod_audit", "project_auditor", "architecture_contracts")):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not getattr(node, "end_lineno", None):
                continue
            if node.end_lineno - node.lineno + 1 > 50 and ast.get_docstring(node) is None:
                missing.append(f"{path.name}:{node.lineno}:{node.name}")
    return missing


def main() -> None:
    from architecture_contracts import TOTAL_PYTHON_FILE_BUDGET, LAYER_FILE_BUDGETS

    assert TOTAL_PYTHON_FILE_BUDGET == 200
    assert LAYER_FILE_BUDGETS["ui_actions"] >= 50
    assert LAYER_FILE_BUDGETS["release_quality"] >= 40

    assert len(_read("window_mapper_dialog.py").splitlines()) <= 40
    assert "from window_setup_center import open_template_setup_center" in _read("window_mapper_dialog.py")
    assert "from window_document_mapper import open_universal_document_mapper" in _read("window_mapper_dialog.py")
    assert "from actions_creation_batch import ActionsCreationBatchingMixin" in _read("actions_creation_orchestrator.py")
    assert "from actions_creation_preflight import ActionsCreationReviewMixin" in _read("actions_creation_orchestrator.py")

    diary_discovery = _read("diary_template_discovery.py")
    assert "except Exception:\n" not in diary_discovery
    assert diary_discovery.count("record_soft_exception") >= 12

    assert not _missing_large_docstrings()

    app_init = _read("app_initialization.py")
    for snippet in ("<F5>", "<F8>", "<F9>", "_undo_last_key_field", "_field_undo_stack"):
        assert snippet in app_init

    assert "_show_created_document_preview" in _read("actions_creation_execution.py")
    assert "_backup_existing_output_file" in _read("actions_creation_foldering.py")
    assert "RotatingFileHandler" in _read("desktop_intake_agent.py")

    workflow = _read(".github/workflows/windows-build.yml")
    assert "headless-tests" in workflow
    assert "python -m pytest tests" in workflow
    assert "--cov=medical_parser" in workflow
    assert "Upload coverage artifact" in workflow

    dev = _read("requirements_dev.txt")
    for package in ("pytest", "pytest-cov", "mypy", "ruff"):
        assert package in dev
    assert (ROOT / "tests" / "test_parser_scanner_logic.py").exists()
    assert (ROOT / "tests" / "test_diary_discovery_logic.py").exists()
    assert "[tool.mypy]" in _read("pyproject.toml")
    print("QUALITY MODERNIZATION SMOKE OK")


if __name__ == "__main__":
    main()
