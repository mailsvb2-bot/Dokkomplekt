from __future__ import annotations

from pathlib import Path

import architecture_contracts as contracts
from printer_jobs import print_files
from printer_models import PrintResult


def test_architecture_lock_v18_includes_constructible_contract_models() -> None:
    assert contracts.ARCHITECTURE_CONTRACT_LOCK_VERSION == "v2.4"
    contracts.assert_annotated_contract_models_are_constructible()


def test_printer_result_is_constructible_dataclass_contract() -> None:
    result = PrintResult([Path("one.docx")], ["printer offline"])
    assert result.printed_files == [Path("one.docx")]
    assert result.errors == ["printer offline"]
    assert result.error_count == 1
    assert not result.ok


def test_print_files_empty_path_returns_structured_result_not_typeerror() -> None:
    result = print_files([])
    assert isinstance(result, PrintResult)
    assert result.printed_files == []
    assert result.errors == []


def test_print_files_non_windows_returns_structured_warning(monkeypatch) -> None:
    monkeypatch.setattr("printer_jobs.is_windows", lambda: False)
    result = print_files([Path("created.docx")])
    assert isinstance(result, PrintResult)
    assert result.printed_files == []
    assert result.errors
    assert "Windows" in result.errors[0]
