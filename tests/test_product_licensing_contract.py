from __future__ import annotations

from datetime import datetime, timezone
import json

from product_licensing import PLAN_LIMITS, ProductAccessManager, machine_fingerprint, sign_license_payload


def test_trial_starts_locally_and_requires_watermark(tmp_path, monkeypatch):
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_DIR", str(tmp_path))
    manager = ProductAccessManager(now=datetime(2026, 6, 27, tzinfo=timezone.utc))

    state = manager.current_state()

    assert state.plan == "trial"
    assert state.active is True
    assert state.watermark_required is True
    assert state.documents_limit_month == 30
    assert state.template_limit == 5
    assert "ПРОБНАЯ ВЕРСИЯ" in state.watermark_text()


def test_trial_blocks_after_total_document_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_DIR", str(tmp_path))
    manager = ProductAccessManager(now=datetime(2026, 6, 27, tzinfo=timezone.utc))
    manager.record_created_documents(30)

    decision = manager.check_document_creation(1)

    assert decision.allowed is False
    assert decision.code == "license_inactive"
    assert decision.state.plan == "trial"
    assert decision.state.active is False


def test_paid_license_uses_plan_limits_without_watermark(tmp_path, monkeypatch):
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_DIR", str(tmp_path))
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_VERIFY_SECRET", "test-secret")
    payload = {
        "license_id": "LIC-DOCTOR-PRO-1",
        "plan": "doctor_pro",
        "owner_name": "Doctor",
        "seats": 2,
        "allowed_machines": [machine_fingerprint()],
        "valid_until": datetime(2027, 6, 27, tzinfo=timezone.utc).isoformat(),
        "issued_at": datetime(2026, 6, 27, tzinfo=timezone.utc).isoformat(),
    }
    signed = sign_license_payload(payload, "test-secret")
    manager = ProductAccessManager(now=datetime(2026, 6, 27, tzinfo=timezone.utc))
    manager.install_license_text(json.dumps(signed, ensure_ascii=False))

    state = manager.current_state()
    decision = manager.check_document_creation(50)

    assert state.plan == "doctor_pro"
    assert state.active is True
    assert state.watermark_required is False
    assert state.documents_limit_month == PLAN_LIMITS["doctor_pro"].document_limit_month
    assert state.template_limit == PLAN_LIMITS["doctor_pro"].template_limit
    assert decision.allowed is True


def test_paid_license_rejects_excess_per_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_DIR", str(tmp_path))
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_VERIFY_SECRET", "test-secret")
    payload = {
        "license_id": "LIC-START-1",
        "plan": "doctor_start",
        "allowed_machines": [machine_fingerprint()],
        "valid_until": datetime(2027, 6, 27, tzinfo=timezone.utc).isoformat(),
    }
    signed = sign_license_payload(payload, "test-secret")
    manager = ProductAccessManager(now=datetime(2026, 6, 27, tzinfo=timezone.utc))
    manager.install_license_text(json.dumps(signed, ensure_ascii=False))

    decision = manager.check_document_creation(11)

    assert decision.allowed is False
    assert decision.code == "per_run_limit"


def test_expired_paid_license_keeps_safe_blocked_state(tmp_path, monkeypatch):
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_DIR", str(tmp_path))
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_VERIFY_SECRET", "test-secret")
    payload = {
        "license_id": "LIC-OLD-1",
        "plan": "doctor_start",
        "allowed_machines": [machine_fingerprint()],
        "valid_until": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        "offline_grace_days": 0,
    }
    signed = sign_license_payload(payload, "test-secret")
    manager = ProductAccessManager(now=datetime(2026, 6, 27, tzinfo=timezone.utc))
    manager.install_license_text(json.dumps(signed, ensure_ascii=False))

    state = manager.current_state()
    decision = manager.check_document_creation(1)

    assert state.active is False
    assert state.plan == "blocked"
    assert state.watermark_required is True
    assert decision.allowed is False


def test_paid_license_grace_period_allows_temporary_creation(tmp_path, monkeypatch):
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_DIR", str(tmp_path))
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_VERIFY_SECRET", "test-secret")
    payload = {
        "license_id": "LIC-GRACE-1",
        "plan": "department",
        "allowed_machines": [machine_fingerprint()],
        "valid_until": datetime(2026, 6, 20, tzinfo=timezone.utc).isoformat(),
        "offline_grace_days": 14,
    }
    signed = sign_license_payload(payload, "test-secret")
    manager = ProductAccessManager(now=datetime(2026, 6, 27, tzinfo=timezone.utc))
    manager.install_license_text(json.dumps(signed, ensure_ascii=False))

    state = manager.current_state()
    decision = manager.check_document_creation(5)

    assert state.active is True
    assert state.reason == "active_grace"
    assert decision.allowed is True
    assert "льгот" in (state.warning + decision.warning).lower()
