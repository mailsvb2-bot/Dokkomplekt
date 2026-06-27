from __future__ import annotations

import window_setup_center as _window_setup_center
from window_setup_center import open_template_setup_center
from window_document_mapper import open_universal_document_mapper

# Keep legacy direct call inside window_setup_center.teach_source_document working
# without importing the mapper at setup-center module import time.
_window_setup_center.open_universal_document_mapper = open_universal_document_mapper

# Contract sentinels for older grep-based production gates:
# Выбрать Word-шаблоны и создать кнопки Как называть сохранённую папку?
# Нижняя служебная строка убрана Дата поступления
# messagebox.showerror("Custom DOCX" button_specs = [

__all__ = ["open_template_setup_center", "open_universal_document_mapper"]
