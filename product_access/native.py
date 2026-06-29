from __future__ import annotations

"""Rust native license bridge for the Python product-access layer.

The bridge accepts only signed Dokkomplekt license documents. It verifies the
Ed25519 proof before converting the Rust payload into the local entitlement
shape. Patient data never crosses this boundary.
"""

import importlib
import json
import os
from typing import Any, Mapping

from product_access import LicenseEntitlement, ProductAccessManager, parse_dt

PUBLIC_KEY_ENV = "DOKKOMPLEKT_LICENSE_PUBLIC_KEY_B64"
RUST_LICENSE_SCHEMA = "dokkomplekt.license.v1"
RUST_SIGNATURE_SENTINEL = "rust-ed25519"


class NativeLicenseError(ValueError):
    pass


def is_rust_license_document(payload: Mapping[str, Any]) -> bool:
    return payload.get("schema") == RUST_LICENSE_SCHEMA and isinstance(payload.get("license"), Mapping)


def _native_module():
    try:
        return importlib.import_module("dokkomplekt_license_native")
    except Exception as exc:
        raise NativeLicenseError("Rust native license core is unavailable.") from exc


def _verify_text(text: str) -> None:
    key = os.getenv(PUBLIC_KEY_ENV, "").strip()
    if not key:
        raise NativeLicenseError("License public verification key is not configured.")
    native = _native_module()
    proof_ok = getattr(native, "proof_ok", None)
    if not callable(proof_ok) or proof_ok(text, key) is not True:
        raise NativeLicenseError("Rust license proof was rejected.")


def _license_mapping(document: Mapping[str, Any]) -> Mapping[str, Any]:
    block = document.get("license")
    if not isinstance(block, Mapping):
        raise NativeLicenseError("Rust license document has no license block.")
    payload = block.get("payload")
    if not isinstance(payload, Mapping):
        raise NativeLicenseError("Rust license document has no payload block.")
    return block


def _entitlement_payload(text: str) -> dict[str, Any]:
    try:
        document = json.loads(text or "{}")
    except json.JSONDecodeError as exc:
        raise NativeLicenseError("Rust license document is not valid JSON.") from exc
    if not isinstance(document, Mapping) or not is_rust_license_document(document):
        raise NativeLicenseError("Not a Dokkomplekt Rust license document.")
    _verify_text(text)
    block = _license_mapping(document)
    payload = block["payload"]
    return {
        "license_id": str(payload.get("license_id") or ""),
        "plan": str(payload.get("plan") or "").lower(),
        "owner_name": str(payload.get("owner_name") or ""),
        "organization_name": str(payload.get("organization_name") or ""),
        "seats": int(payload.get("seats") or payload.get("machine_limit") or 1),
        "allowed_machines": tuple(str(item).lower() for item in payload.get("allowed_machines", ()) if str(item).strip()),
        "valid_until": str(payload.get("valid_until") or ""),
        "issued_at": str(payload.get("issued_at") or ""),
        "generation_limit_month": payload.get("document_limit_month"),
        "template_limit": payload.get("template_limit"),
        "profile_limit": payload.get("profile_limit"),
        "watermark_mode": payload.get("watermark_mode"),
        "offline_grace_days": payload.get("grace_days"),
        "features": tuple(str(item) for item in payload.get("features", ()) if str(item).strip()),
        "signature": RUST_SIGNATURE_SENTINEL,
    }


class NativeProductAccessManager(ProductAccessManager):
    def load_license(self) -> LicenseEntitlement | None:
        try:
            if not self.license_path.exists():
                return None
            text = self.license_path.read_text("utf-8")
            payload: Any = json.loads(text or "{}")
            if isinstance(payload, Mapping) and is_rust_license_document(payload):
                return LicenseEntitlement.from_mapping(_entitlement_payload(text))
            return LicenseEntitlement.from_mapping(payload) if isinstance(payload, Mapping) else None
        except Exception:
            raise

    def install_license_text(self, text: str):
        try:
            payload: Any = json.loads(text or "{}")
        except json.JSONDecodeError:
            return super().install_license_text(text)
        if isinstance(payload, Mapping) and is_rust_license_document(payload):
            _entitlement_payload(text)
            self._save_json_file(self.license_path, payload)
            return self.current_state()
        return super().install_license_text(text)

    def _validate_license(self, entitlement: LicenseEntitlement, *, require_not_expired: bool = True) -> None:
        if entitlement.signature != RUST_SIGNATURE_SENTINEL:
            return super()._validate_license(entitlement, require_not_expired=require_not_expired)
        from product_access import PLAN_LIMITS, machine_fingerprint

        if not entitlement.license_id:
            raise ValueError("В лицензии нет license_id.")
        if entitlement.plan not in PLAN_LIMITS or entitlement.plan == "trial":
            raise ValueError(f"Неизвестный тариф лицензии: {entitlement.plan!r}.")
        if require_not_expired and entitlement.is_expired(self._now()):
            raise ValueError("Срок действия лицензии истёк.")
        issued_at = entitlement.issued_at_dt()
        if issued_at and issued_at > self._now():
            raise ValueError("Дата выдачи лицензии находится в будущем.")
        if parse_dt(entitlement.valid_until) is None:
            raise ValueError("В лицензии нет корректной даты окончания.")
        if entitlement.allowed_machines and machine_fingerprint() not in entitlement.allowed_machines:
            raise ValueError("Лицензия не привязана к этому компьютеру.")

    def current_state(self):
        try:
            return super().current_state()
        except (NativeLicenseError, ValueError, json.JSONDecodeError, OSError) as exc:
            payload = self._ensure_trial_started(self._load_state_payload())
            usage = payload.get("usage_by_month") if isinstance(payload.get("usage_by_month"), dict) else {}
            from product_access import month_key

            used = int(usage.get(month_key(self._now()), 0) or 0)
            trial_total = int(payload.get("trial_created_total", 0) or 0)
            return self._blocked_state(str(exc), used, trial_total)


class NativeProductAccessMixin:
    def _product_access_manager(self) -> NativeProductAccessManager:
        return NativeProductAccessManager()
