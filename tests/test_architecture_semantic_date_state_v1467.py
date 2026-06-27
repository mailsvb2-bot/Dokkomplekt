from __future__ import annotations

import pathlib

import architecture_contracts as contracts

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_semantic_date_contract_gate_is_active() -> None:
    assert contracts.ARCHITECTURE_CONTRACT_LOCK_VERSION == "v2.4"
    contracts.assert_semantic_dates_use_central_resolver()


def test_patient_level_dates_are_not_read_directly_outside_dialog_dates_owner() -> None:
    allowed = set(contracts.SEMANTIC_DATE_DIRECT_READ_ALLOWED_FILES) | {
        "architecture_contracts.py",
        "prod_audit.py",
        "release_check.py",
    }
    offenders: list[str] = []
    for path in ROOT.glob("*.py"):
        if path.name.startswith("smoke") or path.name.startswith("test_") or path.name in allowed:
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        markers = [marker for marker in contracts.SEMANTIC_DATE_DIRECT_READ_MARKERS if marker in source]
        if markers:
            offenders.append(f"{path.name}: {', '.join(markers)}")
    assert offenders == []


def test_creation_flows_import_semantic_date_resolver() -> None:
    for name in (
        "actions_medical_flow.py",
        "actions_diary_flow.py",
        "actions_universal_flow.py",
        "actions_creation_batch.py",
        "actions_creation_preflight.py",
        "actions_creation_execution.py",
    ):
        source = (ROOT / name).read_text(encoding="utf-8", errors="replace")
        assert "current_semantic_date" in source
        assert "_current_discharge_date_value() if hasattr" not in source
