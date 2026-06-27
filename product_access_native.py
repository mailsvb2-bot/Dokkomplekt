from __future__ import annotations

"""Python boundary for the optional Rust native license core.

This module intentionally contains no patient data logic and no payment secrets.
It only bridges a signed Rust license document into the existing Python product
access model. If a paid Rust license cannot be checked by the native core, paid
access fails closed.
"""

import importlib
import json
import os
from typing import Any, Mapping

from product_access import LicenseEntitlement, ProductAccessManager

NATIVE_LICENSE_CORE_MODULE = "dokkomplekt_license_native"
PUBLIC_KEY_ENV = "DOKKOMPLEKT_LICENSE_PUBLIC_KEY_B64"
RUST_LICENSE_SCHEMA = "dokkomplekt.license.v1"


class NativeLicenseError(ValueError):
    """Raised when a Rust license document cannot be trusted locally."""


def is_rust_license_document(payload: Mapping[str, Any]) -> bool:
    return payload.get("schema") == RUST_LICENSE_SCHEMA and isinstance(payload.get("license"), Mapping)


def _native_module():
    try:
        return importlib.import_module(NATIVE_LICENSE_CORE_MODULE)
    except Exception as exc:
        raise NativeLicenseError("Rust native license core is unavailable.") from exc


def _public_key() -> str:
    value = os.getenv(PUBLIC_KEY_ENV, "").strip()
    if not value:
        raise NativeLicenseError("License public verification key is not configured.")
    return value


def verify_rust_license_document_text(text: str) -> None:
    native = _native_module()
    if not hasattr(native, "proof_ok"):
        raise NativeLicenseError("Rust native license core does not expose proof_ok().")
    ok = native.proof_ok(text, _public_key())
    if ok is not True:
        raise NativeLicenseError("Rust license proof was rejected.")


def rust_document_to_entitlement_payload(document: Mapping[str, Any]) -> dict[str, Any]:
    if not is_rust_license_document(document):
        raise NativeLicenseError("Not a Dokkomplekt Rust license document.")
    license_block = document.get("license")
    if not isinstance(license_block, Mapping):
        raise NativeLicenseError("License block is missing.")
    payload = license_block.get("payload")
    if not isinstance(payload, Mapping):
        raise NativeLicenseError("License payload is missing.")
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


def load_verified_rust_entitlement_text(text: str) -> dict[str, Any]:
    document = json.loads(text or "{}")
    if not isinstance(document, Mapping):
        raise NativeLicenseError("License document must be a JSON object.")
    verify_rust_license_document_text(text)
    return rust_document_to_entitlement_payload(document)


class NativeProductAccessManager(ProductAccessManager):
    def _read_license_text(self) -> str | None:
        if not self.license_path.exists():
            return None
        return self.license_path.read_text("utf-8")

    def load_license(self) -> LicenseEntitlement | None:
        text = self._read_license_text()
        if text is None:
            return None
        payload: Any = json.loads(text or "{}")
        if isinstance(payload, dict) and is_rust_license_document(payload):
            return LicenseEntitlement.from_mapping(load_verified_rust_entitlement_text(text))
        return LicenseEntitlement.from_mapping(payload) if isinstance(payload, dict) else None

    def install_license_text(self, text: str):
        payload: Any = json.loads(text or "{}")
        if isinstance(payload, dict) and is_rust_license_document(payload):
            load_verified_rust_entitlement_text(text)
            tmp_path = self.license_path.with_suffix(".tmp")
            tmp_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(text, "utf-8")
            os.replace(tmp_path, self.license_path)
            return self.current_state()
        return super().install_license_text(text)

    def _validate_license(self, entitlement: LicenseEntitlement, *, require_not_expired: bool = True) -> None:
        if entitlement.signature == "rust-ed25519":
            if not entitlement.license_id:
                raise ValueError("В лицензии нет license_id.")
            if entitlement.plan not in self.plan_ids() or entitlement.plan == "trial":
                raise ValueError(f"Неизвестный тариф лицензии: {entitlement.plan!r}.")
            if require_not_expired and entitlement.is_expired(self._now()):
                raise ValueError("Срок действия лицензии истёк.")
            from product_access import machine_fingerprint
            if entitlement.allowed_machines and machine_fingerprint() not in entitlement.allowed_machines:
                raise ValueError("Лицензия не привязана к этому компьютеру.")
            return
        return super()._validate_license(entitlement, require_not_expired=require_not_expired)

    @staticmethod
    def plan_ids() -> set[str]:
        from product_access import PLAN_LIMITS
        return set(PLAN_LIMITS)

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
