from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_version_info_numeric_tuple_matches_release_version() -> None:
    import prod_audit

    version_info = (ROOT / "version_info.txt").read_text(encoding="utf-8")
    expected = prod_audit._target_version_tuple_literal()
    assert f"filevers={expected}" in version_info
    assert f"prodvers={expected}" in version_info
    assert prod_audit.TARGET_VERSION_LABEL in version_info


def test_prod_audit_does_not_lock_previous_version_tuple() -> None:
    import prod_audit

    source = Path(prod_audit.__file__).read_text(encoding="utf-8")
    assert 'filevers=(1, 4, 73, 0)' not in source
    assert 'prodvers=(1, 4, 73, 0)' not in source
    assert "_target_version_tuple_literal" in source


def test_privacy_redactor_handles_two_token_russian_names() -> None:
    from diagnostic_logging import redact_diagnostic_text

    redacted = redact_diagnostic_text(r"Ошибка для Иванов Иван: C:\Users\Пользователь\Desktop\Иванов Иван выписка.docx 01.02.2026 история болезни №123")
    assert "Иванов" not in redacted
    assert "01.02.2026" not in redacted
    assert "123" not in redacted
    assert "C:" not in redacted
    assert "<person>" in redacted or "<path>" in redacted or "<file>" in redacted


def test_stress_smoke_is_wired_as_isolated_release_subprocess() -> None:
    release_check = (ROOT / "release_check.py").read_text(encoding="utf-8")
    stress_smoke = (ROOT / "smoke_stress_hardening.py").read_text(encoding="utf-8")
    assert '_run([sys.executable, "smoke_stress_hardening.py"], timeout=180)' in release_check
    assert "os._exit(0)" in stress_smoke
    assert "sys.stdout.flush()" in stress_smoke
