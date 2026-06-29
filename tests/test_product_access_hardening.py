from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from product_access import (
    PLAN_LIMITS,
    LicenseContractError,
    ProductAccessManager,
    apply_docx_footer_watermark,
    apply_watermark_to_files,
    machine_fingerprint,
    product_access_enforcement_enabled,
    sign_license_payload,
)

NOW = datetime(2026, 6, 27, tzinfo=timezone.utc)


def signed(plan: str = "doctor_pro", **overrides):
    payload = {
        "license_id": "LIC-TEST-1",
        "plan": plan,
        "owner_name": "Doctor",
        "seats": PLAN_LIMITS[plan].included_machines,
        "allowed_machines": [machine_fingerprint()],
        "valid_until": datetime(2027, 6, 27, tzinfo=timezone.utc).isoformat(),
        "issued_at": NOW.isoformat(),
    }
    payload.update(overrides)
    return sign_license_payload(payload, "test-secret")


def manager(tmp_path, monkeypatch, *, secret: bool = True, now: datetime = NOW):
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_DIR", str(tmp_path))
    if secret:
        monkeypatch.setenv("DOKKOMPLEKT_LICENSE_VERIFY_SECRET", "test-secret")
    return ProductAccessManager(now=now)


def test_trial_limits_are_total_and_local(tmp_path, monkeypatch):
    m = manager(tmp_path, monkeypatch, secret=False)
    state = m.current_state()
    assert state.plan == "trial"
    assert state.active is True
    assert state.watermark_required is True
    assert state.documents_limit_month == 30
    assert state.template_limit == 5
    assert state.profile_limit == 1
    m.record_created_documents(30)
    decision = m.check_document_creation(1)
    assert decision.allowed is False
    assert decision.code == "license_inactive"


def test_trial_blocks_batch_templates_and_profiles(tmp_path, monkeypatch):
    m = manager(tmp_path, monkeypatch, secret=False)
    assert m.check_document_creation(4).code == "per_run_limit"
    assert m.check_document_creation(1, template_count=6).code == "template_limit"
    assert m.check_document_creation(1, profile_count=2).code == "profile_limit"


def test_paid_license_uses_plan_limits_without_watermark(tmp_path, monkeypatch):
    m = manager(tmp_path, monkeypatch)
    m.install_license_text(json.dumps(signed(), ensure_ascii=False))
    state = m.current_state()
    assert state.plan == "doctor_pro"
    assert state.active is True
    assert state.watermark_required is False
    assert state.template_limit == PLAN_LIMITS["doctor_pro"].template_limit
    assert state.profile_limit == PLAN_LIMITS["doctor_pro"].profile_limit
    assert m.check_document_creation(50).allowed is True


def test_paid_license_rejects_tamper_and_wrong_machine(tmp_path, monkeypatch):
    m = manager(tmp_path, monkeypatch)
    tampered = signed()
    tampered["plan"] = "clinic"
    with pytest.raises(LicenseContractError):
        m.install_license_text(json.dumps(tampered, ensure_ascii=False))
    with pytest.raises(LicenseContractError):
        m.install_license_text(json.dumps(signed(allowed_machines=["wrong-machine"]), ensure_ascii=False))


def test_paid_license_rejects_future_unknown_bad_limits_and_bad_watermark(tmp_path, monkeypatch):
    m = manager(tmp_path, monkeypatch)
    with pytest.raises(LicenseContractError):
        m.install_license_text(json.dumps(signed(issued_at=(NOW + timedelta(days=1)).isoformat()), ensure_ascii=False))
    bad_plan = signed(); bad_plan["plan"] = "gold"; bad_plan["signature"] = "bad"
    with pytest.raises(LicenseContractError):
        m.install_license_text(json.dumps(bad_plan, ensure_ascii=False))
    with pytest.raises(LicenseContractError):
        m.install_license_text(json.dumps(signed(watermark_mode="unsafe"), ensure_ascii=False))
    with pytest.raises(LicenseContractError):
        m.install_license_text(json.dumps(signed("doctor_start", seats=2), ensure_ascii=False))
    with pytest.raises(LicenseContractError):
        m.install_license_text(json.dumps(signed(seats=2, allowed_machines=[machine_fingerprint(), "other", "third"]), ensure_ascii=False))


def test_paid_license_overage_grace_and_expiry(tmp_path, monkeypatch):
    m = manager(tmp_path, monkeypatch)
    m.install_license_text(json.dumps(signed("doctor_start", seats=1, generation_limit_month=10), ensure_ascii=False))
    m.record_created_documents(7)
    assert "80%" in m.check_document_creation(1).warning
    m.record_created_documents(3)
    assert "перерасход" in m.check_document_creation(1).warning
    m.record_created_documents(2)
    assert m.check_document_creation(1).code == "monthly_limit"

    m2 = manager(tmp_path / "expired", monkeypatch)
    m2.install_license_text(json.dumps(signed("doctor_start", seats=1, valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(), offline_grace_days=0), ensure_ascii=False))
    assert m2.current_state().plan == "blocked"
    assert m2.current_state().watermark_required is True


def test_unsigned_license_is_dev_only(tmp_path, monkeypatch):
    m = manager(tmp_path, monkeypatch, secret=False)
    payload = signed(); payload.pop("signature")
    with pytest.raises(LicenseContractError):
        m.install_license_text(json.dumps(payload, ensure_ascii=False))
    monkeypatch.setenv("DOKKOMPLEKT_ALLOW_UNSIGNED_LICENSES", "1")
    assert m.install_license_text(json.dumps(payload, ensure_ascii=False)).active is True


def test_state_schema_is_self_healing_and_non_private(tmp_path, monkeypatch):
    m = manager(tmp_path, monkeypatch, secret=False)
    m.state_path.write_text("not-json", "utf-8")
    assert m.current_state().plan == "trial"
    m.record_created_documents(2)
    payload = json.loads(m.state_path.read_text("utf-8"))
    assert payload["schema_version"] >= 2
    assert payload["contract_version"]
    assert "usage_by_month" in payload
    assert "trial_created_total" in payload
    as_text = json.dumps(payload).lower()
    assert "patient" not in as_text
    assert "diagnos" not in as_text


def test_zero_negative_records_and_env_switches(tmp_path, monkeypatch):
    m = manager(tmp_path, monkeypatch, secret=False)
    m.record_created_documents(0); m.record_created_documents(-10)
    assert m.current_state().documents_used_total_trial == 0
    monkeypatch.delenv("MEDICAL_AUTOFILL_DISABLE_PRODUCT_ACCESS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    assert product_access_enforcement_enabled() is True
    monkeypatch.setenv("CI", "1")
    assert product_access_enforcement_enabled() is False
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("MEDICAL_AUTOFILL_DISABLE_PRODUCT_ACCESS", "yes")
    assert product_access_enforcement_enabled() is False


def test_watermark_guards_and_idempotency(tmp_path):
    assert apply_docx_footer_watermark(tmp_path / "x.docx", "").error == ""
    assert "file not found" in apply_docx_footer_watermark(tmp_path / "missing.docx", "wm").error
    txt = tmp_path / "a.txt"; txt.write_text("x", "utf-8")
    assert "docx" in apply_docx_footer_watermark(txt, "wm").error
    from docx import Document
    docx = tmp_path / "a.docx"; doc = Document(); doc.add_paragraph("body"); doc.save(docx)
    assert apply_docx_footer_watermark(docx, "wm").changed is True
    assert apply_docx_footer_watermark(docx, "wm").changed is False
    assert len(apply_watermark_to_files([docx, docx], "wm2").results) == 1


class BaseCreator:
    def __init__(self):
        self.called = False
        self.custom_document_specs = {str(i): object() for i in range(6)}

    def _selected_outputs_or_warn(self):
        return [], False, ["1"]

    def _log(self, _message):
        pass

    def create_selected_outputs(self, *, print_after=False):
        self.called = True

    def _created_files_from_results(self, created_medical, created_custom, diary_result):
        return list(created_medical) + list(created_custom)


def test_mixin_checks_template_limit_before_super(tmp_path, monkeypatch):
    from product_access import ProductAccessMixin
    import tkinter.messagebox as messagebox
    monkeypatch.setattr(messagebox, "showwarning", lambda *args, **kwargs: None)
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_DIR", str(tmp_path)); monkeypatch.delenv("CI", raising=False)

    class Creator(ProductAccessMixin, BaseCreator):
        pass

    creator = Creator(); creator.create_selected_outputs()
    assert creator.called is False


def test_mixin_records_created_count_after_super(tmp_path, monkeypatch):
    from product_access import ProductAccessMixin
    monkeypatch.setenv("DOKKOMPLEKT_LICENSE_DIR", str(tmp_path)); monkeypatch.delenv("CI", raising=False)

    class Creator(ProductAccessMixin, BaseCreator):
        pass

    assert Creator()._created_files_from_results([tmp_path / "a.txt"], [], None)
    assert ProductAccessManager(storage_dir=tmp_path, now=NOW).current_state().documents_used_total_trial == 1
