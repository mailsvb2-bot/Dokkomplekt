from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import urllib.error

import pytest

import product_access.native as native
from product_access import LicenseEntitlement


def _entitlement() -> LicenseEntitlement:
    return LicenseEntitlement(
        license_id="lic-1",
        plan="doctor_pro",
        valid_until="2027-09-03T00:00:00+00:00",
        issued_at="2026-09-01T00:00:00+00:00",
        offline_grace_days=7,
        features=(native.RUST_NATIVE_VERIFIED_FEATURE,),
        signature="rust-ed25519",
    )


def test_cached_revoked_license_fails_closed(tmp_path: Path) -> None:
    manager = native.NativeProductAccessManager(tmp_path, now=datetime(2026, 9, 3, tzinfo=timezone.utc))
    manager._write_license_status_cache({
        "schema": native.LICENSE_STATUS_SCHEMA,
        "license_id": "lic-1",
        "status": "revoked",
        "checked_at": "2026-09-03T00:00:00+00:00",
        "revoked_at": "2026-09-03T00:00:00+00:00",
        "cache_ttl_seconds": 86400,
    })
    with pytest.raises(ValueError, match="отозвана"):
        manager._validate_revocation_status(_entitlement())


def test_active_cache_allows_offline_within_grace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = native.NativeProductAccessManager(tmp_path, now=datetime(2026, 9, 5, tzinfo=timezone.utc))
    manager._write_license_status_cache({
        "schema": native.LICENSE_STATUS_SCHEMA,
        "license_id": "lic-1",
        "status": "active",
        "checked_at": "2026-09-03T00:00:00+00:00",
        "revoked_at": None,
        "cache_ttl_seconds": 86400,
    })
    monkeypatch.setenv(native.LICENSE_SERVER_URL_ENV, "https://licenses.example.test")
    monkeypatch.setattr(manager, "_fetch_license_status", lambda _ent: (_ for _ in ()).throw(native.NativeLicenseError("offline")))
    manager._validate_revocation_status(_entitlement())


def test_active_cache_fails_closed_after_grace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = native.NativeProductAccessManager(tmp_path, now=datetime(2026, 9, 20, tzinfo=timezone.utc))
    manager._write_license_status_cache({
        "schema": native.LICENSE_STATUS_SCHEMA,
        "license_id": "lic-1",
        "status": "active",
        "checked_at": "2026-09-03T00:00:00+00:00",
        "revoked_at": None,
        "cache_ttl_seconds": 86400,
    })
    monkeypatch.setenv(native.LICENSE_SERVER_URL_ENV, "https://licenses.example.test")
    monkeypatch.setattr(manager, "_fetch_license_status", lambda _ent: (_ for _ in ()).throw(native.NativeLicenseError("offline")))
    with pytest.raises(ValueError, match="offline-grace"):
        manager._validate_revocation_status(_entitlement())
