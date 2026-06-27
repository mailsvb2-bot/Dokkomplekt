from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="replace")


def main() -> None:
    from doctor_action_journal import assert_doctor_action_journal_lock
    from error_taxonomy import assert_error_taxonomy_lock, ErrorCategory
    from universal_profiles import default_document_pack, mark_pack_as_department_profile, profile_scope_label

    assert_doctor_action_journal_lock()
    assert_error_taxonomy_lock()
    assert ErrorCategory.USER_INPUT.value == "user_input_error"

    pack = default_document_pack()
    mark_pack_as_department_profile(pack, department_name="Приёмное отделение")
    assert "Профиль отделения" in profile_scope_label(pack)
    assert pack.workflow_principles["department_shared_templates"] is True

    execution = _read("actions_creation_execution.py")
    assert "append_doctor_action" in execution
    assert "Показана проверка перед созданием" in execution
    assert "Документы созданы" in execution
    assert "record_classified_error" in execution

    preflight = _read("actions_creation_preflight.py")
    assert "Исправить данные" in preflight

    profiles = _read("universal_profiles.py")
    assert "_backup_existing_document_pack" in profiles
    assert "mark_pack_as_department_profile" in profiles
    assert "profile_kind" in profiles

    settings = _read("settings_mixin.py")
    assert "_settings_backups" in settings
    assert "settings.backup.json" in settings

    workflow = _read(".github/workflows/windows-build.yml")
    assert "python -m ruff check ." in workflow
    assert "python -m mypy --config-file pyproject.toml" in workflow
    assert "--cov=error_taxonomy" in workflow
    assert "--cov=doctor_action_journal" in workflow

    tests = {p.name for p in (ROOT / "tests").glob("test_*.py")}
    assert "test_points_5_11_logic.py" in tests
    print("POINTS 5-11 SMOKE OK")


if __name__ == "__main__":
    main()
