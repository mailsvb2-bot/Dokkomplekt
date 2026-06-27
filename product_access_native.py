from __future__ import annotations

"""Python boundary for the optional Rust native license core.

This module intentionally contains no patient data logic and no payment secrets.
It only bridges a signed Rust license document into the existing Python product
access model. If a paid Rust license cannot be checked by the native core, the
caller must treat paid access as unavailable.
"""

import importlib
import json
import os
from typing import Any, Mapping

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
