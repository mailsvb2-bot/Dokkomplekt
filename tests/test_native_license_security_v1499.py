from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from product_access import machine_fingerprint
from product_access.native import NativeProductAccessManager


def _flat_rust_marker_payload() -> dict[str, object]:
    return {
        "license_id": "LIC-FLAT-RUST-MARKER",
        "plan": "doctor_pro",
        "allowed_machines": [machine_fingerprint()],
        "valid_until": datetime(2027, 6, 27, tzinfo=timezone.utc).isoformat(),
        "signature": "rust-ed25519",
    }


def test_flat_json_cannot_impersonate_native_rust_license(tmp_path, monkeypatch):
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_DIR", str(tmp_path))
    manager = NativeProductAccessManager(now=datetime(2026, 6, 27, tzinfo=timezone.utc))
    manager.license_path.write_text(json.dumps(_flat_rust_marker_payload()), encoding="utf-8")

    state = manager.current_state()

    assert state.active is False
    assert state.plan == "blocked"
    assert "Flat JSON license" in state.warning or "Rust license marker" in state.warning


def test_flat_json_rust_marker_is_rejected_on_install(tmp_path, monkeypatch):
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_DIR", str(tmp_path))
    manager = NativeProductAccessManager(now=datetime(2026, 6, 27, tzinfo=timezone.utc))

    with pytest.raises(Exception):
        manager.install_license_text(json.dumps(_flat_rust_marker_payload()))
