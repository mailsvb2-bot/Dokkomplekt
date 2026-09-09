from __future__ import annotations

from actions_creation import ActionsFolderNamingPreflightMixin
from desktop_patient_folder import FOLDER_NAMING_SCHEMA_VERSION


class _Parent:
    def _ensure_patient_folder_naming_configured(self, *, force: bool = False) -> bool:
        self.parent_calls.append(force)
        return True


class _Subject(ActionsFolderNamingPreflightMixin, _Parent):
    def __init__(self, settings):
        self._settings = settings
        self.parent_calls = []


def test_confirmed_folder_rule_is_not_reasked_even_for_legacy_force_call() -> None:
    app = _Subject(
        {
            "folder_naming": {
                "schema_version": FOLDER_NAMING_SCHEMA_VERSION,
                "parts": ["surname_initials", "admission_month"],
                "date_format": "short",
                "doctor_confirmed": True,
            }
        }
    )

    assert app._ensure_patient_folder_naming_configured(force=True) is True
    assert app.parent_calls == []


def test_old_or_unconfirmed_folder_rule_still_reopens_upgrade_setup() -> None:
    app = _Subject(
        {
            "folder_naming": {
                "schema_version": "old",
                "parts": ["surname_initials", "admission_month"],
                "doctor_confirmed": True,
            }
        }
    )

    assert app._ensure_patient_folder_naming_configured(force=True) is True
    assert app.parent_calls == [True]
