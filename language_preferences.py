"""User language preferences stored safely in settings.json."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Mapping

from medical_language_catalog import normalize_language_id

LANGUAGE_PREFERENCES_LOCK_VERSION = "v1.1"


def _settings_bool(value: object, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"", "0", "false", "no", "off", "нет", "не", "n", "disabled", "disable"}:
            return False
        if lowered in {"1", "true", "yes", "on", "да", "y", "enabled", "enable"}:
            return True
    if value is None:
        return default
    return bool(value)


@dataclass(frozen=True)
class LanguagePreferences:
    ui_language: str = "ru"
    document_language: str = "auto"
    output_language: str = "same_as_source"
    spellcheck_enabled: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_settings(cls, data: Mapping[str, object] | None) -> "LanguagePreferences":
        raw = data if isinstance(data, Mapping) else {}
        output = str(raw.get("output_language", "same_as_source") or "same_as_source")
        if output != "same_as_source":
            output = normalize_language_id(output, default="ru")
        return cls(
            ui_language=normalize_language_id(str(raw.get("ui_language", "ru") or "ru"), default="ru"),
            document_language=normalize_language_id(str(raw.get("document_language", "auto") or "auto")),
            output_language=output,
            spellcheck_enabled=_settings_bool(raw.get("spellcheck_enabled", True), default=True),
        )


def assert_language_preferences_lock() -> None:
    if LANGUAGE_PREFERENCES_LOCK_VERSION != "v1.1":
        raise AssertionError("Language preferences lock changed")
    prefs = LanguagePreferences.from_settings({"ui_language": "az", "document_language": "auto", "output_language": "same_as_source"})
    if prefs.ui_language != "az" or prefs.document_language != "auto":
        raise AssertionError("Language preferences normalization failed")
    if LanguagePreferences.from_settings({"spellcheck_enabled": "false"}).spellcheck_enabled:
        raise AssertionError("String false must not enable spellcheck")
