from __future__ import annotations

import json
import sys
import types

from product_access import machine_fingerprint
from product_access_native import PUBLIC_KEY_ENV
from product_access_native_runtime import NativeProductAccessManager


def _rust_license_doc(plan: str = "doctor_pro") -> dict:
    return {
        "schema": "dokkomplekt.license.v1",
        "license": {
            "payload": {
                "license_id": "DKK-TEST-RUST-1",
                "order_id": "order-1",
                "plan": plan,
                "owner_name": "Doctor",
                "organization_name": "",
                "seats": 2,
                "allowed_machines": [machine_fingerprint()],
                "valid_from": "2026-01-01T00:00:00Z",
                "valid_until": "2027-01-01T00:00:00Z",
                "document_limit_month": 3000,
                "template_limit": 150,
                "profile_limit": 3,
                "features": ["batch_generation", "batch_print"],
                "grace_days": 7,
                "watermark_mode": "none",
                "issued_by": "test",
                "issued_at": "2026-06-27T00:00:00Z",
                "metadata": {},
            },
            "signature_alg": "ed25519",
            "signature": "test-proof",
        },
    }


def test_native_rust_license_document_installs_and_opens_paid_state(tmp_path, monkeypatch):
    fake_native = types.SimpleNamespace(proof_ok=lambda license_json, public_key: True)
    monkeypatch.setitem(sys.modules, "dokkomplekt_license_native", fake_native)
    monkeypatch.setenv(PUBLIC_KEY_ENV, "test-public-key")
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_DIR", str(tmp_path))

    manager = NativeProductAccessManager()
    manager.install_license_text(json.dumps(_rust_license_doc(), ensure_ascii=False))

    state = manager.current_state()

    assert state.active is True
    assert state.plan == "doctor_pro"
    assert state.watermark_required is False
    assert state.documents_limit_month == 3000


def test_native_rust_license_document_fails_closed_without_native_core(tmp_path, monkeypatch):
    monkeypatch.delenv(PUBLIC_KEY_ENV, raising=False)
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_DIR", str(tmp_path))
    manager = NativeProductAccessManager()
    manager.license_path.write_text(json.dumps(_rust_license_doc(), ensure_ascii=False), "utf-8")

    state = manager.current_state()

    assert state.active is False
    assert state.plan == "blocked"
    assert state.watermark_required is True
