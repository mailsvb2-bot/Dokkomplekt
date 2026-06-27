from __future__ import annotations

import ast
from pathlib import Path

import architecture_contracts as contracts

ROOT = Path(__file__).resolve().parents[1]


def test_no_app_config_wildcard_imports_in_implementation_modules() -> None:
    offenders: list[str] = []
    for path in ROOT.glob("*.py"):
        if path.name in contracts.WILDCARD_IMPORT_ALLOWED_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "app_config":
                if any(alias.name == "*" for alias in node.names):
                    offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []


def test_only_public_facades_use_wildcard_imports() -> None:
    offenders: list[str] = []
    allowed = contracts.WILDCARD_IMPORT_ALLOWED_FILES
    for path in ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
                if path.name not in allowed:
                    offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []
    assert allowed == {"medical_documents.py", "diary_filler.py"}


def test_ui_action_layers_have_no_subprocess_imports() -> None:
    offenders: list[str] = []
    for path in ROOT.glob("*.py"):
        name = path.name
        if name in contracts.CENTRAL_DESKTOP_OPEN_BOUNDARY_ALLOWED_FILES:
            continue
        is_ui = name.startswith(contracts.UI_SHELL_IMPORT_FORBIDDEN_PREFIXES) or name in contracts.UI_SHELL_IMPORT_FORBIDDEN_FILES
        if not is_ui:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(alias.name.split(".", 1)[0] == "subprocess" for alias in node.names):
                offenders.append(f"{name}:{node.lineno}")
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".", 1)[0] == "subprocess":
                offenders.append(f"{name}:{node.lineno}")
    assert offenders == []


def test_architecture_contract_lock_v16() -> None:
    assert contracts.ARCHITECTURE_CONTRACT_LOCK_VERSION == "v2.4"
    contracts.assert_architecture_contracts()
