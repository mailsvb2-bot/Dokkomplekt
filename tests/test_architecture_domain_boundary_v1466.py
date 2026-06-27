from __future__ import annotations

from pathlib import Path

import architecture_contracts as contracts

ROOT = Path(__file__).resolve().parents[1]


def _source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_domain_modules_do_not_import_app_config() -> None:
    contracts.assert_domain_modules_do_not_import_app_config()
    assert "from app_config" not in _source("diary_template_discovery.py")
    assert "from app_config" not in _source("diary_template_selection.py")


def test_folder_memory_keys_live_in_domain_constants() -> None:
    diary = _source("diary_constants.py")
    medical = _source("medical_constants.py")
    config = _source("app_config.py")
    assert 'DIR_DIARY_TEXTS = "diary_texts_dir"' in diary
    assert 'DIR_NUMBERED_DIARY_TEMPLATES = "numbered_diary_templates_dir"' in diary
    assert 'DIR_PRIMARY_DOCUMENTS = "primary_documents_dir"' in medical
    assert 'DIR_OUTPUT = "output_dir"' in medical
    assert "from diary_constants import (" in config
    assert "from medical_constants import DIR_EPI, DIR_OUTPUT, DIR_PRIMARY_DOCUMENTS" in config


def test_creation_and_dialogs_use_primary_document_resolver() -> None:
    contracts.assert_primary_path_resolver_contract()
    for name in ("dialog_document_details.py", "dialog_expert.py", "actions_selection.py", "diary_template_discovery.py"):
        source = _source(name)
        assert "navigation_path_var.get" not in source
    assert "selected_primary_document_path_text" in _source("dialog_document_details.py")
    assert "selected_primary_document_path_text" in _source("dialog_expert.py")


def test_primary_document_state_exposes_text_resolver() -> None:
    source = _source("medical_primary_document_state.py")
    assert "def selected_primary_document_path_text" in source
    assert "selected_primary_document_path(app)" in source


def test_architecture_contract_lock_v16() -> None:
    assert contracts.ARCHITECTURE_CONTRACT_LOCK_VERSION == "v2.4"
    contracts.assert_architecture_contracts()
