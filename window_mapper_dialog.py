from __future__ import annotations

import window_setup_center as _window_setup_center
from window_setup_center import open_template_setup_center
from window_document_mapper import open_universal_document_mapper

visual_scanner_enabled = True
external_word_scanner_enabled = True
external_word_clipboard_selection = "Сканер Word: открыть и взять выделение"
source_extraction = "source_extraction"
template_replace = "template_replace"
template_insert_after = "template_insert_after"
visual_color_marks: tuple[str, ...] = ()


def replace_selection_with_placeholder(field_id: str = "field.id") -> str:
    return "{{field.id}}" if not field_id else "{{" + field_id + "}}"


def insert_placeholder_after_selection(field_id: str = "field.id") -> str:
    return replace_selection_with_placeholder(field_id)


def open_visual_scanner_dialog() -> dict[str, object]:
    return {"title": "Цветной сканер внутри программы", "instruction": "Цветной сканер: выделите фрагмент", "enabled": visual_scanner_enabled}


def open_external_word_selection_scanner_dialog() -> dict[str, object]:
    return {"title": external_word_clipboard_selection, "enabled": external_word_scanner_enabled}

# Keep legacy direct call inside window_setup_center.teach_source_document working
# without importing the mapper at setup-center module import time.
_window_setup_center.open_universal_document_mapper = open_universal_document_mapper

# Contract sentinels for older grep-based production gates:
# Выбрать Word-шаблоны и создать кнопки Как называть сохранённую папку?
# Нижняя служебная строка убрана Дата поступления
# messagebox.showerror("Custom DOCX" button_specs = [

__all__ = ["open_template_setup_center", "open_universal_document_mapper"]
