from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from product_access import machine_fingerprint, sign_license_payload
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


def test_owner_enterprise_license_is_unlimited_in_native_app_path(tmp_path, monkeypatch):
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_DIR", str(tmp_path))
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_VERIFY_SECRET", "test-secret")
    payload = {
        "license_id": "LIC-OWNER-UNLIMITED-1",
        "plan": "enterprise",
        "owner_name": "Owner",
        "organization_name": "Dokkomplekt Owner",
        "seats": 9999,
        "allowed_machines": [],
        "valid_until": datetime(2099, 12, 31, tzinfo=timezone.utc).isoformat(),
        "issued_at": datetime(2026, 7, 6, tzinfo=timezone.utc).isoformat(),
        "generation_limit_month": 2147483647,
        "template_limit": 999999,
        "profile_limit": 999999,
        "watermark_mode": "none",
        "offline_grace_days": 36500,
        "features": ["owner_license"],
    }
    signed = sign_license_payload(payload, "test-secret")
    manager = NativeProductAccessManager(now=datetime(2026, 7, 6, tzinfo=timezone.utc))
    manager.install_license_text(json.dumps(signed, ensure_ascii=False))

    state = manager.current_state()
    decision = manager.check_document_creation(100000, template_count=100000, profile_count=100000)

    assert state.plan == "enterprise"
    assert state.active is True
    assert state.watermark_required is False
    assert state.documents_limit_month == 2147483647
    assert state.remaining_documents_month == 2147483647
    assert decision.allowed is True
    assert decision.code == "ok_owner_unlimited"
