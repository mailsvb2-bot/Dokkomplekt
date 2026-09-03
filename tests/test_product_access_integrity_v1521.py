from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path

from product_access import ProductAccessManager, machine_fingerprint, stable_json


def _legacy_key() -> bytes:
    seed = f"dokkomplekt-product-access-v2|{machine_fingerprint()}"
    return hashlib.sha256(seed.encode("utf-8", errors="replace")).digest()


def test_v2_state_migrates_to_random_key_v3_without_resetting_usage(tmp_path: Path) -> None:
    payload = {
        "state_version": 2,
        "trial_started_at": "2026-09-01T00:00:00+00:00",
        "usage_by_month": {"2026-09": 12},
        "trial_created_total": 12,
    }
    payload["_state_mac"] = hmac.new(
        _legacy_key(), stable_json(payload).encode("utf-8"), hashlib.sha256
    ).hexdigest()
    (tmp_path / "product_access_state.json").write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "product_access_guard.json").write_text(json.dumps(payload), encoding="utf-8")

    manager = ProductAccessManager(tmp_path, now=datetime(2026, 9, 3, tzinfo=timezone.utc))
    state = manager.current_state()
    manager.record_created_documents(1)

    stored = json.loads(manager.state_path.read_text("utf-8"))
    assert state.documents_used_total_trial == 12
    assert stored["state_version"] == 3
    assert stored["trial_created_total"] == 13
    assert stored["usage_sequence"] >= 1
    assert manager.integrity_key_path.exists()
    assert manager.integrity_key_guard_path.exists()


def test_v3_state_rejects_mac_recomputed_from_machine_fingerprint(tmp_path: Path) -> None:
    manager = ProductAccessManager(tmp_path, now=datetime(2026, 9, 3, tzinfo=timezone.utc))
    manager.current_state()
    manager.record_created_documents(5)
    forged = json.loads(manager.state_path.read_text("utf-8"))
    forged["trial_created_total"] = 0
    forged["usage_by_month"] = {"2026-09": 0}
    unsigned = dict(forged)
    unsigned.pop("_state_mac", None)
    forged["_state_mac"] = hmac.new(
        _legacy_key(), stable_json(unsigned).encode("utf-8"), hashlib.sha256
    ).hexdigest()
    manager.state_path.write_text(json.dumps(forged), encoding="utf-8")
    manager.state_guard_path.write_text(json.dumps(forged), encoding="utf-8")

    state = ProductAccessManager(tmp_path, now=datetime(2026, 9, 3, tzinfo=timezone.utc)).current_state()

    assert state.active is False
    assert state.plan == "blocked"
    assert "повреждено" in state.warning.lower()
