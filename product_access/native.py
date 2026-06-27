from __future__ import annotations

import importlib
import json
import os
from typing import Any, Mapping

from product_access import LicenseEntitlement, ProductAccessManager

PUBLIC_KEY_ENV = "DOKKOMPLEKT_LICENSE_PUBLIC_KEY_B64"
RUST_LICENSE_SCHEMA = "dokkomplekt.license.v1"


class NativeLicenseError(ValueError):
    pass


def is_rust_license_document(payload: Mapping[str, Any]) -> bool:
    return payload.get("schema") == RUST_LICENSE_SCHEMA and isinstance(payload.get("license"), Mapping)


def _verify_text(text: str) -> None:
    key = os.getenv(PUBLIC_KEY_ENV, "").strip()
    if not key:
        raise NativeLicenseError("License public verification key is not configured.")
    try:
        native = importlib.import_module("dokkomplekt_license_native")
    except Exception as exc:
        raise NativeLicenseError("Rust native license core is unavailable.") from exc
    if native.proof_ok(text, key) is not True:
        raise NativeLicenseError("Rust license proof was rejected.")


def _entitlement_payload(text: str) -> dict[str, Any]:
    document = json.loads(text or "{}")
    if not isinstance(document, Mapping) or not is_rust_license_document(document):
        raise NativeLicenseError("Not a Dokkomplekt Rust license document.")
    _verify_text(text)
    license_block = document["license"]
    payload = license_block["payload"]
    return {
        "license_id": str(payload.get("license_id") or ""),
        "plan": str(payload.get("plan") or "").lower(),
        "owner_name": str(payload.get("owner_name") or ""),
        "organization_name": str(payload.get("organization_name") or ""),
        "seats": int(payload.get("seats") or 1),
        "allowed_machines": tuple(str(item).lower() for item in payload.get("allowed_machines", ()) if str(item).strip()),
        "valid_until": str(payload.get("valid_until") or ""),
        "issued_at": str(payload.get("issued_at") or ""),
        "generation_limit_month": payload.get("document_limit_month"),
        "template_limit": payload.get("template_limit"),
        "profile_limit": payload.get("profile_limit"),
        "watermark_mode": payload.get("watermark_mode"),
        "offline_grace_days": payload.get("grace_days"),
        "features": tuple(str(item) for item in payload.get("features", ()) if str(item).strip()),
        "signature": str(license_block.get("signature") or "rust-ed25519"),
    }


class NativeProductAccessManager(ProductAccessManager):
    def load_license(self) -> LicenseEntitlement | None:
        if not self.license_path.exists():
            return None
        text = self.license_path.read_text("utf-8")
        payload: Any = json.loads(text or "{}")
        if isinstance(payload, dict) and is_rust_license_document(payload):
            return LicenseEntitlement.from_mapping(_entitlement_payload(text))
        return LicenseEntitlement.from_mapping(payload) if isinstance(payload, dict) else None

    def install_license_text(self, text: str):
        payload: Any = json.loads(text or "{}")
        if isinstance(payload, dict) and is_rust_license_document(payload):
            _entitlement_payload(text)
            tmp_path = self.license_path.with_suffix(".tmp")
            tmp_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(text, "utf-8")
            os.replace(tmp_path, self.license_path)
            return self.current_state()
        return super().install_license_text(text)

    def _validate_license(self, entitlement: LicenseEntitlement, *, require_not_expired: bool = True) -> None:
        if entitlement.signature == "rust-ed25519":
            from product_access import PLAN_LIMITS, machine_fingerprint
            if not entitlement.license_id:
                raise ValueError("В лицензии нет license_id.")
            if entitlement.plan not in PLAN_LIMITS or entitlement.plan == "trial":
                raise ValueError(f"Неизвестный тариф лицензии: {entitlement.plan!r}.")
            if require_not_expired and entitlement.is_expired(self._now()):
                raise ValueError("Срок действия лицензии истёк.")
            if entitlement.allowed_machines and machine_fingerprint() not in entitlement.allowed_machines:
                raise ValueError("Лицензия не привязана к этому компьютеру.")
            return
        return super()._validate_license(entitlement, require_not_expired=require_not_expired)

    def current_state(self):
        try:
            return super().current_state()
        except (NativeLicenseError, ValueError, json.JSONDecodeError) as exc:
            payload = self._ensure_trial_started(self._load_state_payload())
            usage = payload.get("usage_by_month") if isinstance(payload.get("usage_by_month"), dict) else {}
            from product_access import month_key
            used = int(usage.get(month_key(self._now()), 0) or 0)
            trial_total = int(payload.get("trial_created_total", 0) or 0)
            return self._blocked_state(str(exc), used, trial_total)


class NativeProductAccessMixin:
    def _product_access_manager(self) -> NativeProductAccessManager:
        return NativeProductAccessManager()
