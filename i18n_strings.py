"""Small UI string registry for multilingual surfaces.

The legacy Russian UI remains the first production language.  New universal and
language-selection surfaces go through this registry so further translations can
be added without touching business logic.
"""

from __future__ import annotations

from medical_language_catalog import normalize_language_id

I18N_STRINGS_LOCK_VERSION = "v1.0"

_STRINGS: dict[str, dict[str, str]] = {
    "app.title": {"ru": "Медицинский автозаполнитель", "en": "Medical document autofill", "uk": "Медичний автозаповнювач", "az": "Tibbi sənəd doldurucu", "hy": "Բժշկական փաստաթղթերի լրացում", "ka": "სამედიცინო დოკუმენტების შევსება"},
    "app.subtitle": {"ru": "Автоматическое заполнение медицинских документов", "en": "Automatic medical document filling", "uk": "Автоматичне заповнення медичних документів", "az": "Tibbi sənədlərin avtomatik doldurulması", "hy": "Բժշկական փաստաթղթերի ավտոմատ լրացում", "ka": "სამედიცინო დოკუმენტების ავტომატური შევსება"},
    "button.profiles": {"ru": "Свои шаблоны", "en": "Profiles", "uk": "Профілі", "az": "Profillər", "hy": "Պրոֆիլներ", "ka": "პროფილები"},
    "button.language": {"ru": "Язык", "en": "Language", "uk": "Мова", "az": "Dil", "hy": "Լեզու", "ka": "ენა"},
    "language.dialog.title": {"ru": "Язык программы", "en": "Program language", "uk": "Мова програми", "az": "Proqram dili", "hy": "Ծրագրի լեզու", "ka": "პროგრამის ენა"},
    "language.ui": {"ru": "Язык интерфейса", "en": "Interface language", "uk": "Мова інтерфейсу", "az": "İnterfeys dili", "hy": "Միջերեսի լեզու", "ka": "ინტერფეისის ენა"},
    "language.document": {"ru": "Язык загружаемых документов", "en": "Uploaded document language", "uk": "Мова завантажених документів", "az": "Yüklənən sənədlərin dili", "hy": "Վերբեռնվող փաստաթղթերի լեզու", "ka": "ატვირთული დოკუმენტების ენა"},
    "language.output": {"ru": "Язык создаваемых документов", "en": "Generated document language", "uk": "Мова створюваних документів", "az": "Yaradılan sənədlərin dili", "hy": "Ստեղծվող փաստաթղթերի լեզու", "ka": "შექმნილი დოკუმენტების ენა"},
    "language.spellcheck": {"ru": "Проверять орфографию под капотом", "en": "Check spelling under the hood", "uk": "Перевіряти правопис під капотом", "az": "Orfoqrafiyanı daxildə yoxlamaq", "hy": "Ստուգել ուղղագրությունը ներքին կերպով", "ka": "მართლწერის შიდა შემოწმება"},
    "button.save": {"ru": "Сохранить", "en": "Save", "uk": "Зберегти", "az": "Saxla", "hy": "Պահել", "ka": "შენახვა"},
    "button.cancel": {"ru": "Отмена", "en": "Cancel", "uk": "Скасувати", "az": "Ləğv et", "hy": "Չեղարկել", "ka": "გაუქმება"},
    "language.saved": {"ru": "Языковые настройки сохранены", "en": "Language settings saved", "uk": "Мовні налаштування збережено", "az": "Dil parametrləri saxlanıldı", "hy": "Լեզվի կարգավորումները պահպանվեցին", "ka": "ენის პარამეტრები შენახულია"},
}


def tr(key: str, language_id: str | None = "ru") -> str:
    lang = normalize_language_id(language_id, default="ru")
    values = _STRINGS.get(key, {})
    return values.get(lang) or values.get("ru") or key


def assert_i18n_strings_lock() -> None:
    if I18N_STRINGS_LOCK_VERSION != "v1.0":
        raise AssertionError("I18N strings lock changed unexpectedly")
    for key in ("button.language", "language.ui", "language.document", "language.output", "language.spellcheck"):
        if key not in _STRINGS:
            raise AssertionError(f"Missing i18n key: {key}")
