from __future__ import annotations

from pathlib import Path

import architecture_contracts

ROOT = Path(__file__).resolve().parents[1]


def _source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_desktop_open_boundary_is_centralized() -> None:
    architecture_contracts.assert_desktop_open_boundary_is_centralized()
    platform_source = _source("printer_platform.py")
    assert "def open_desktop_path" in platform_source
    assert "stdin=subprocess.DEVNULL" in platform_source
    assert "creationflags=_creationflags_no_window()" in platform_source


def test_ui_modules_use_open_desktop_path_instead_of_raw_subprocess() -> None:
    for name in ("actions_creation_batch.py", "diary_batch.py", "dialog_fields_core.py"):
        source = _source(name)
        assert "open_desktop_path" in source
        assert "subprocess.Popen" not in source
        assert "os.startfile" not in source


def test_diary_kind_is_domain_constant_not_app_config_dependency() -> None:
    universal_source = _source("universal_main_documents.py")
    config_source = _source("app_config.py")
    diary_source = _source("diary_constants.py")
    assert "from diary_constants import DIARY_KIND" in universal_source
    assert "from app_config import DIARY_KIND" not in universal_source
    assert "from diary_constants import (" in config_source
    assert "DIARY_KIND" in config_source and "DIARY_LABEL" in config_source
    assert 'DIARY_KIND = "diaries"' in diary_source


def test_generic_and_desktop_intake_popups_have_scrollable_bodies() -> None:
    fields_source = _source("dialog_fields_core.py")
    intake_source = _source("desktop_intake_mixin.py")
    assert "def _build_scrollable_prompt_body" in fields_source
    assert "ttk.Scrollbar" in fields_source
    assert "footer" in fields_source
    assert "def _build_desktop_intake_scroll_body" in intake_source
    assert "ttk.Scrollbar" in intake_source
    assert "Создать документы без печати" in intake_source


def test_primary_document_selection_rejects_non_word_inputs_up_front() -> None:
    source = _source("files_mixin.py")
    assert "PRIMARY_DOCUMENT_SUFFIXES" in source
    assert "clear_selected_primary_document_path" in source
    assert "Нужен Word-документ" in source
    assert "DOCX/DOCM" in source
