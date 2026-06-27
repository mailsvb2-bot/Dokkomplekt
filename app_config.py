from __future__ import annotations

APP_TITLE = "Медицинский автозаполнитель"
APP_VERSION = "v1.4.89_release_gate_runtime_isolation_SOURCE"

# Цветовая схема точно по референсу: глубокий navy-midnight, cyan-акцент, card-стиль блоков.
BG = "#07111d"
BG_2 = "#050d18"
PANEL = "#071827"      # фон карточек секций (блоки 01-04)
PANEL_2 = "#0a1b2b"   # фон элементов внутри карточек (чекбоксы)
PANEL_3 = "#0c2b47"   # кнопки «Выбрать», активные состояния
SECTION_SIDE = "#071626"  # левая боковая колонка
SECTION_SIDE_2 = "#09243a"
BORDER = "#126493"
BORDER_SOFT = "#153e5f"
BORDER_FAINT = "#15314a"
ACCENT = "#5bd0ff"    # cyan-blue из референса
ACCENT_2 = "#08a7df"  # кнопка «печать» — ярче
ACCENT_3 = "#94bdd7"
TEXT = "#e8f4ff"
MUTED = "#92a8bc"
MUTED_2 = "#5e7a91"
WARN = "#ffd166"
ERROR = "#ff7a9c"
SUCCESS = "#6fd4a8"
SAVE_ACCENT = "#0f3354"   # тёмная кнопка «сохранить без печати»
SAVE_ACCENT_ACTIVE = "#173f66"
PRINT_ACCENT = "#1096cc"  # синяя кнопка «печатать»
PRINT_ACCENT_ACTIVE = "#18a8dd"
FIELD = "#06101b"     # поля ввода — очень тёмные
FIELD_BORDER = "#193a56"
GLOW = "#39c9ff"
DEEP = "#030912"      # самый тёмный — фон окна и шапка

# Backwards-compatible re-export facade for UI modules and old smoke scripts.
# Domain modules must import these constants from diary_constants/medical_constants
# directly; architecture_contracts.py enforces that app_config stays UI-facing.
from diary_constants import (
    DIARY_KIND,
    DIARY_LABEL,
    DIR_DIARY_TEXTS,
    DIR_DIARY_TEMPLATES,
    DIR_NUMBERED_DIARY_TEMPLATES,
)
from medical_constants import DIR_EPI, DIR_OUTPUT, DIR_PRIMARY_DOCUMENTS
