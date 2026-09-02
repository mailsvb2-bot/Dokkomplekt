from __future__ import annotations

from pathlib import Path


def test_release_gate_exercises_medpack_export_behavior() -> None:
    import release_check

    release_check._assert_medpack_export_contract()


def test_release_gate_does_not_lock_old_arcname_implementation_text() -> None:
    source = Path("release_check.py").read_text(encoding="utf-8")

    assert 'doc_data["template"] = arcname.as_posix()' not in source
    assert "_assert_medpack_export_contract()" in source
