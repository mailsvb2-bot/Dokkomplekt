from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping

from medical_paths import atomic_read_text, atomic_write_text
from product_access import AccessDecision, LicenseEntitlement, ProductAccessManager

try:
    import dokkomplekt_license_native as _native_license_core
except Exception:
    _native_license_core = None

PUBLIC_KEY_ENV = "DOKKOMPLEKT_LICENSE_PUBLIC_KEY_B64"
RUST_LICENSE_SCHEMA = "dokkomplekt.license.v1"
RUST_NATIVE_VERIFIED_FEATURE = "native:verified"
LICENSE_SERVER_URL_ENV = "DOKKOMPLEKT_LICENSE_SERVER_URL"
LICENSE_STATUS_SCHEMA = "dokkomplekt.license-status.v1"
LICENSE_STATUS_HTTP_TIMEOUT_SECONDS = 3.0


class NativeLicenseError(ValueError):
    pass


def is_rust_license_document(payload: Mapping[str, Any]) -> bool:
    return payload.get("schema") == RUST_LICENSE_SCHEMA and isinstance(payload.get("license"), Mapping)


def _native_module():
    if _native_license_core is not None:
        return _native_license_core
    try:
        return importlib.import_module("dokkomplekt_license_native")
    except Exception as exc:
        raise NativeLicenseError("Rust native license core is unavailable.") from exc


def _verification_key() -> str:
    """Load the pinned Ed25519 public key from source env or packaged resources."""

    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / "resources" / "license_public_key.b64")
    if not getattr(sys, "frozen", False):
        key = os.getenv(PUBLIC_KEY_ENV, "").strip()
        if key:
            return key
    candidates.append(Path(__file__).resolve().parent.parent / "resources" / "license_public_key.b64")
    for path in candidates:
        try:
            value = path.read_text("utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return ""


def _verify_text(text: str) -> None:
    key = _verification_key()
    if not key:
        raise NativeLicenseError(
            "License public verification key is not configured in this build. "
            "Rebuild with DOKKOMPLEKT_LICENSE_PUBLIC_KEY_B64."
        )
    native = _native_module()
    if native.proof_ok(text, key) is not True:
        raise NativeLicenseError("Rust license proof was rejected.")


def _entitlement_payload(text: str) -> dict[str, Any]:
    document = json.loads(text or "{}")
    if not isinstance(document, Mapping) or not is_rust_license_document(document):
        raise NativeLicenseError("Not a Dokkomplekt Rust license document.")
    _verify_text(text)
    license_block = document["license"]
    payload = license_block["payload"]
    features = tuple(str(item) for item in payload.get("features", ()) if str(item).strip())
    if RUST_NATIVE_VERIFIED_FEATURE not in features:
        features = (*features, RUST_NATIVE_VERIFIED_FEATURE)
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
        "features": features,
        "signature": str(license_block.get("signature") or "rust-ed25519"),
    }


class NativeProductAccessManager(ProductAccessManager):
    def load_license(self) -> LicenseEntitlement | None:
        try:
            text = atomic_read_text(self.license_path, encoding="utf-8")
        except FileNotFoundError:
            return None
        payload: Any = json.loads(text or "{}")
        if isinstance(payload, dict) and is_rust_license_document(payload):
            return LicenseEntitlement.from_mapping(_entitlement_payload(text))
        entitlement = LicenseEntitlement.from_mapping(payload) if isinstance(payload, dict) else None
        if entitlement and entitlement.signature == "rust-ed25519":
            raise NativeLicenseError("Flat JSON license cannot use the Rust native signature marker.")
        return entitlement

    def install_license_text(self, text: str):
        payload: Any = json.loads(text or "{}")
        if isinstance(payload, dict) and is_rust_license_document(payload):
            _entitlement_payload(text)
            atomic_write_text(self.license_path, text)
            return self.current_state()
        entitlement = LicenseEntitlement.from_mapping(payload) if isinstance(payload, dict) else None
        if entitlement and entitlement.signature == "rust-ed25519":
            raise NativeLicenseError("Flat JSON license cannot use the Rust native signature marker.")
        if entitlement and getattr(sys, "frozen", False):
            raise NativeLicenseError("Packaged Dokkomplekt accepts only native Ed25519 license documents.")
        return super().install_license_text(text)

    def _validate_license(self, entitlement: LicenseEntitlement, *, require_not_expired: bool = True) -> None:
        if entitlement.signature == "rust-ed25519":
            if RUST_NATIVE_VERIFIED_FEATURE not in entitlement.features:
                raise ValueError("Rust license marker is accepted only after native proof verification.")
            from product_access import PLAN_LIMITS, machine_fingerprint
            if not entitlement.license_id:
                raise ValueError("В лицензии нет license_id.")
            if entitlement.plan not in PLAN_LIMITS or entitlement.plan == "trial":
                raise ValueError(f"Неизвестный тариф лицензии: {entitlement.plan!r}.")
            if require_not_expired and entitlement.is_expired(self._now()):
                raise ValueError("Срок действия лицензии истёк.")
            if entitlement.allowed_machines and machine_fingerprint() not in entitlement.allowed_machines:
                raise ValueError("Лицензия не привязана к этому компьютеру.")
            self._validate_revocation_status(entitlement)
            return
        if getattr(sys, "frozen", False):
            raise ValueError("Packaged Dokkomplekt accepts only native Ed25519 licenses.")
        return super()._validate_license(entitlement, require_not_expired=require_not_expired)

    @property
    def _license_status_cache_path(self) -> Path:
        return self.storage_dir / "license_status_cache.json"

    @staticmethod
    def _license_server_url() -> str:
        return os.getenv(LICENSE_SERVER_URL_ENV, "").strip().rstrip("/")

    def _read_license_status_cache(self, license_id: str) -> dict[str, Any] | None:
        path = self._license_status_cache_path
        if not path.exists():
            return None
        try:
            payload = json.loads(atomic_read_text(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("schema") != LICENSE_STATUS_SCHEMA:
            return None
        if str(payload.get("license_id") or "") != license_id:
            return None
        return payload

    def _write_license_status_cache(self, payload: Mapping[str, Any]) -> None:
        atomic_write_text(
            self._license_status_cache_path,
            json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )

    def _cached_status_is_fresh(self, payload: Mapping[str, Any]) -> bool:
        from product_access import parse_dt

        checked_at = parse_dt(str(payload.get("checked_at") or ""))
        if checked_at is None:
            return False
        try:
            ttl_seconds = max(1, int(payload.get("cache_ttl_seconds") or 0))
        except (TypeError, ValueError):
            return False
        return (self._now() - checked_at).total_seconds() <= ttl_seconds

    def _cached_status_within_offline_grace(
        self, payload: Mapping[str, Any], entitlement: LicenseEntitlement
    ) -> bool:
        from product_access import parse_dt

        checked_at = parse_dt(str(payload.get("checked_at") or ""))
        if checked_at is None or str(payload.get("status") or "") != "active":
            return False
        try:
            ttl_seconds = max(0, int(payload.get("cache_ttl_seconds") or 0))
        except (TypeError, ValueError):
            return False
        grace_days = entitlement.offline_grace_days
        if grace_days is None:
            grace_days = entitlement.plan_limits().grace_days
        allowed_seconds = ttl_seconds + max(0, int(grace_days)) * 86400
        return (self._now() - checked_at).total_seconds() <= allowed_seconds

    def _fetch_license_status(self, entitlement: LicenseEntitlement) -> dict[str, Any]:
        base_url = self._license_server_url()
        if not base_url:
            raise NativeLicenseError("License status server is not configured.")
        license_id = urllib.parse.quote(entitlement.license_id, safe="")
        request = urllib.request.Request(
            f"{base_url}/api/licenses/{license_id}/status",
            headers={"Accept": "application/json", "User-Agent": "Dokkomplekt-LicenseStatus/1"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=LICENSE_STATUS_HTTP_TIMEOUT_SECONDS) as response:
                body = response.read(64 * 1024)
        except (OSError, urllib.error.URLError) as exc:
            raise NativeLicenseError("License status server is temporarily unavailable.") from exc
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NativeLicenseError("License status server returned invalid JSON.") from exc
        if not isinstance(payload, dict) or payload.get("schema") != LICENSE_STATUS_SCHEMA:
            raise NativeLicenseError("License status server returned an unsupported schema.")
        if str(payload.get("license_id") or "") != entitlement.license_id:
            raise NativeLicenseError("License status response does not match this license.")
        status = str(payload.get("status") or "").strip().lower()
        if status not in {"active", "revoked"}:
            raise NativeLicenseError("License status server returned an invalid status.")
        if not str(payload.get("checked_at") or "").strip():
            raise NativeLicenseError("License status response has no checked_at timestamp.")
        try:
            if int(payload.get("cache_ttl_seconds") or 0) <= 0:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise NativeLicenseError("License status response has an invalid cache TTL.") from exc
        self._write_license_status_cache(payload)
        return payload

    def _validate_revocation_status(self, entitlement: LicenseEntitlement) -> None:
        cache = self._read_license_status_cache(entitlement.license_id)
        if cache and str(cache.get("status") or "").lower() == "revoked":
            raise ValueError("Лицензия отозвана.")
        if cache and self._cached_status_is_fresh(cache):
            return
        if not self._license_server_url():
            return
        try:
            status = self._fetch_license_status(entitlement)
        except NativeLicenseError:
            if cache and self._cached_status_within_offline_grace(cache, entitlement):
                return
            # A never-checked license remains usable offline to preserve the existing
            # local-first contract. Once a successful status check exists, expiry of
            # its TTL+grace fails closed until the server can be reached again.
            if cache is None:
                return
            raise ValueError("Не удалось подтвердить статус лицензии после offline-grace.")
        if str(status.get("status") or "").lower() == "revoked":
            raise ValueError("Лицензия отозвана.")

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

    def check_document_creation(self, requested_count: int, *, template_count: int | None = None, profile_count: int | None = None):
        state = self.current_state()
        if _is_owner_unlimited_state(state):
            return AccessDecision(
                True,
                "ok_owner_unlimited",
                "Доступ разрешён",
                "Owner-лицензия: безлимитное создание документов разрешено.",
                state,
                state.warning,
            )
        return super().check_document_creation(requested_count, template_count=template_count, profile_count=profile_count)


def _is_owner_unlimited_state(state) -> bool:
    return (
        state.plan == "enterprise"
        and state.active
        and state.documents_limit_month >= 2_000_000_000
        and state.template_limit >= 999_999
        and state.profile_limit >= 999_999
        and state.watermark_mode == "none"
    )


class NativeProductAccessMixin:
    def _product_access_manager(self) -> NativeProductAccessManager:
        return NativeProductAccessManager()
