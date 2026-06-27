"""Supported languages and locale metadata for the medical document builder.

This module deliberately contains only small immutable metadata.  It is not a
translator and not a spelling engine; those responsibilities live in separate
modules so the multilingual layer does not become a god module.
"""

from __future__ import annotations

from dataclasses import dataclass

LANGUAGE_CATALOG_LOCK_VERSION = "v1.0"
SUPPORTED_LANGUAGE_IDS = ("auto", "ru", "uk", "be", "kk", "uz", "az", "hy", "ka", "tg", "tk", "en")


@dataclass(frozen=True)
class LanguageProfile:
    id: str
    native_name: str
    ui_name_ru: str
    script: str
    default_output: str = "same_as_source"

    def choice_label(self) -> str:
        return f"{self.ui_name_ru} / {self.native_name} [{self.id}]"


_LANGUAGE_PROFILES: dict[str, LanguageProfile] = {
    "auto": LanguageProfile("auto", "Auto", "Авто", "mixed"),
    "ru": LanguageProfile("ru", "Русский", "Русский", "cyrillic"),
    "uk": LanguageProfile("uk", "Українська", "Украинский", "cyrillic"),
    "be": LanguageProfile("be", "Беларуская", "Белорусский", "cyrillic"),
    "kk": LanguageProfile("kk", "Қазақша", "Казахский", "cyrillic"),
    "uz": LanguageProfile("uz", "O‘zbekcha", "Узбекский", "latin"),
    "az": LanguageProfile("az", "Azərbaycanca", "Азербайджанский", "latin"),
    "hy": LanguageProfile("hy", "Հայերեն", "Армянский", "armenian"),
    "ka": LanguageProfile("ka", "ქართული", "Грузинский", "georgian"),
    "tg": LanguageProfile("tg", "Тоҷикӣ", "Таджикский", "cyrillic"),
    "tk": LanguageProfile("tk", "Türkmençe", "Туркменский", "latin"),
    "en": LanguageProfile("en", "English", "Английский", "latin"),
}


def normalize_language_id(value: str | None, *, default: str = "auto") -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "": default,
        "рус": "ru", "russian": "ru", "ru-ru": "ru",
        "ua": "uk", "ukrainian": "uk", "uk-ua": "uk",
        "bel": "be", "be-by": "be",
        "kaz": "kk", "kk-kz": "kk",
        "uzb": "uz", "uz-uz": "uz",
        "aze": "az", "az-az": "az",
        "arm": "hy", "hy-am": "hy",
        "geo": "ka", "kat": "ka", "ka-ge": "ka",
        "taj": "tg", "tg-tj": "tg",
        "turkmen": "tk", "tk-tm": "tk",
        "eng": "en", "en-us": "en", "en-gb": "en",
    }
    text = aliases.get(text, text.split("-", 1)[0])
    return text if text in _LANGUAGE_PROFILES else default


def language_profile(language_id: str | None) -> LanguageProfile:
    return _LANGUAGE_PROFILES[normalize_language_id(language_id)]


def language_choices() -> tuple[str, ...]:
    return tuple(_LANGUAGE_PROFILES[item].choice_label() for item in SUPPORTED_LANGUAGE_IDS)


def language_id_from_choice(choice: str) -> str:
    marker = str(choice or "").rsplit("[", 1)
    if len(marker) == 2 and marker[1].endswith("]"):
        return normalize_language_id(marker[1][:-1])
    return normalize_language_id(choice)


def assert_language_catalog_lock() -> None:
    if LANGUAGE_CATALOG_LOCK_VERSION != "v1.0":
        raise AssertionError("Language catalog lock changed unexpectedly")
    for required in ("ru", "uk", "be", "kk", "uz", "az", "hy", "ka", "tg", "tk", "en"):
        if required not in _LANGUAGE_PROFILES:
            raise AssertionError(f"Missing supported medical language: {required}")
