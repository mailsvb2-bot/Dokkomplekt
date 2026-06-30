from __future__ import annotations

import tkinter as tk

from settings_mixin import SettingsMixin
from window_mixin import WindowMixin
from layout_mixin import LayoutMixin
from dialogs_mixin import DialogsMixin
from files_mixin import FilesMixin
from dnd_mixin import DragDropMixin
from actions_mixin import ActionsMixin
from app_initialization import AppInitializationMixin
from desktop_intake_mixin import DesktopIntakeMixin
from ui_cards import UiCardsMixin
from ui_icons import UiIconsMixin
from ui_buttons import UiButtonsMixin
from ui_fields import UiFieldsMixin
from diagnosis_widget import DiagnosisWidgetMixin
from ui_file_rows import UiFileRowsMixin
from diary_template_discovery import DiaryTemplateDiscoveryMixin
from diary_template_selection import DiaryTemplateSelectionMixin
from legacy_word_file_mixin import LegacyWordFileMixin
from product_access import ProductAccessMixin, ProductLicenseMixin
from product_access_native import NativeProductAccessMixin


class WidgetsMixin(UiCardsMixin, UiIconsMixin, UiButtonsMixin, UiFieldsMixin, DiagnosisWidgetMixin, UiFileRowsMixin):
    """Aggregates focused widget helper mixins without an extra shim module."""


class DiaryTemplateMixin(DiaryTemplateDiscoveryMixin, DiaryTemplateSelectionMixin):
    """Aggregates diary-template discovery/selection without an extra shim module."""


class CombinedMedicalDiaryApp(
    NativeProductAccessMixin,
    ProductAccessMixin,
    ProductLicenseMixin,
    AppInitializationMixin,
    SettingsMixin,
    DesktopIntakeMixin,
    WindowMixin,
    LayoutMixin,
    DialogsMixin,
    WidgetsMixin,
    LegacyWordFileMixin,
    FilesMixin,
    DiaryTemplateMixin,
    DragDropMixin,
    ActionsMixin,
):
    def __init__(self, root: tk.Tk):
        self._initialize_app(root)
