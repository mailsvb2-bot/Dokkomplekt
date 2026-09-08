from __future__ import annotations

"""Production-only boundary between licensing and output publication.

The licensing owner remains ``ProductAccessManager``/``NativeProductAccessManager``.
This module only preserves actionable denial reasons across the filesystem
transaction and validates the public verification key embedded in release builds.
"""

import base64
from pathlib import Path
from typing import Iterable

PRODUCTION_ACCESS_BOUNDARY_VERSION = "v1.0"
ED25519_PUBLIC_KEY_BYTES = 32


def validate_license_public_key_b64(value: str) -> tuple[bool, str]:
    raw = str(value or "").strip()
    if not raw:
        return False, "Ed25519 public verification key is missing from this build."
    try:
        decoded = base64.b64decode(raw, validate=True)
    except Exception:
        return False, "Ed25519 public verification key is not valid base64."
    if len(decoded) != ED25519_PUBLIC_KEY_BYTES:
        return False, f"Ed25519 public verification key must be {ED25519_PUBLIC_KEY_BYTES} bytes, got {len(decoded)}."
    return True, "ok"


def packaged_license_public_key_status() -> tuple[bool, str]:
    from product_access.native import _verification_key

    return validate_license_public_key_b64(_verification_key())


def require_packaged_license_public_key() -> None:
    ok, reason = packaged_license_public_key_status()
    if not ok:
        raise RuntimeError(reason)


def _publication_failure(exc: Exception, *, operation: str) -> Exception:
    """Expose the real access failure without weakening fail-closed cleanup."""
    cause = exc.__cause__
    detail = str(cause or exc).strip()
    if isinstance(cause, PermissionError):
        return PermissionError(f"Документы не выданы: {detail}")
    if detail and detail not in {
        "Документы не выданы: не удалось надёжно зарезервировать счётчик лицензии.",
        "Документы не выданы: не удалось надёжно записать счётчик лицензии.",
    }:
        return RuntimeError(f"Документы не выданы ({operation}): {detail}")
    return exc


class ProductionAccessBoundaryMixin:
    """Keep the original licensing engine, but never hide why publication failed."""

    def _reserve_product_access_for_staged_files(self, created_files: Iterable[str | Path]):
        try:
            owner = getattr(super(), "_reserve_product_access_for_staged_files")
            return owner(created_files)
        except Exception as exc:
            surfaced = _publication_failure(exc, operation="проверка лицензии")
            if surfaced is exc:
                raise
            raise surfaced from (exc.__cause__ or exc)

    def _enforce_product_access_on_created_files(self, created_files: Iterable[str | Path]) -> list[Path]:
        try:
            owner = getattr(super(), "_enforce_product_access_on_created_files")
            return owner(created_files)
        except Exception as exc:
            surfaced = _publication_failure(exc, operation="учёт созданных документов")
            if surfaced is exc:
                raise
            raise surfaced from (exc.__cause__ or exc)
