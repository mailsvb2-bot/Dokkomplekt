from __future__ import annotations

"""Runtime bridge from existing product access code to Rust native licensing.

This module keeps the existing Python product-access contract intact while
allowing signed Rust license documents to be trusted only after native proof
checking. If native checking is unavailable, paid Rust access fails closed.
"""

import json
import os
from typing import Any

from product_access import LicenseEntitlement, ProductAccessManager
from product_access_native import (
    NativeLicenseError,
    is_rust_license_document,
    load_verified_rust_entitlement_text,
)


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
            verified_payload = load_verified_rust_entitlement_text(text)
            return LicenseEntitlement.from_mapping(verified_payload)
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
