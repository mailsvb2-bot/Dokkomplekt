from __future__ import annotations

import base64
from pathlib import Path

import pytest

from product_access.production_boundary import (
    ProductionAccessBoundaryMixin,
    validate_license_public_key_b64,
)
from product_access_native import NativeProductAccessMixin


ROOT = Path(__file__).resolve().parents[1]


class _DeniedReservationOwner:
    def _reserve_product_access_for_staged_files(self, _files):
        try:
            raise PermissionError("Пробный период закончился; активируйте лицензию.")
        except PermissionError as exc:
            raise RuntimeError(
                "Документы не выданы: не удалось надёжно зарезервировать счётчик лицензии."
            ) from exc


class _DeniedReservationApp(ProductionAccessBoundaryMixin, _DeniedReservationOwner):
    pass


def test_publication_boundary_preserves_real_license_denial() -> None:
    app = _DeniedReservationApp()
    with pytest.raises(PermissionError) as error:
        app._reserve_product_access_for_staged_files([Path("staged.docx")])
    text = str(error.value)
    assert "Пробный период закончился" in text
    assert "зарезервировать счётчик" not in text


def test_native_product_access_mro_contains_publication_boundary() -> None:
    assert ProductionAccessBoundaryMixin in NativeProductAccessMixin.__mro__


def test_ed25519_public_key_validation_is_strict() -> None:
    valid = base64.b64encode(bytes(range(32))).decode("ascii")
    assert validate_license_public_key_b64(valid) == (True, "ok")
    assert validate_license_public_key_b64("")[0] is False
    assert validate_license_public_key_b64("not-base64")[0] is False
    assert validate_license_public_key_b64(base64.b64encode(b"short").decode("ascii"))[0] is False


def test_windows_release_cannot_publish_without_production_key() -> None:
    build = (ROOT / "build_exe_windows.bat").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/windows-build.yml").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")

    assert "CI-сборка без production public key" not in build
    assert "Production EXE без DOKKOMPLEKT_LICENSE_PUBLIC_KEY_B64 запрещён" in build
    assert "validate_license_public_key_b64" in build
    assert "secrets.DOKKOMPLEKT_LICENSE_PUBLIC_KEY_B64" in workflow
    assert "--check-production-license-key" in workflow
    assert "--check-production-license-key" in main


def test_ci_runs_real_gui_create_command_with_product_access_enabled() -> None:
    workflow = (ROOT / ".github/workflows/windows-build.yml").read_text(encoding="utf-8")
    smoke = (ROOT / "tools/doctor_emulation/run_product_access_scenario.py").read_text(encoding="utf-8")

    assert "run_product_access_scenario.py" in workflow
    assert 'DOKKOMPLEKT_TEST_DISABLE_PRODUCT_ACCESS"] = "0"' in smoke
    assert "sim.create_diaries()" in smoke
    assert "NativeProductAccessManager" in smoke
    assert "documents_used_total_trial" in smoke
