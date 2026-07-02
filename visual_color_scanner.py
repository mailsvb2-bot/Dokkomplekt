"""Visual color scanner contracts for doctor-owned template mapping.

The module keeps the configurable profile scanner explicit: a doctor can mark a
source fragment, map it to a placeholder, and choose whether the generated DOCX
should replace the selected text or insert the placeholder after it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

VISUAL_SCANNER_LOCK_VERSION = "v1.0"
visual_scanner_enabled = True
external_word_scanner_enabled = True
external_word_clipboard_selection = "Сканер Word: открыть и взять выделение"
source_extraction = "source_extraction"
template_replace = "template_replace"
template_insert_after = "template_insert_after"


@dataclass(frozen=True)
class VisualColorMark:
    """A doctor-confirmed colored fragment selected inside a source document."""

    field_id: str
    selected_text: str
    start: int = -1
    end: int = -1
    action: Literal["source_extraction", "template_replace", "template_insert_after"] = source_extraction

    @property
    def placeholder(self) -> str:
        return placeholder_for_field(self.field_id)


def placeholder_for_field(field_id: str) -> str:
    """Return the portable placeholder syntax used by DOCX template rendering."""
    normalized = str(field_id or "field.id").strip() or "field.id"
    return "{{" + normalized + "}}"


def visual_color_marks(marks: Iterable[VisualColorMark]) -> tuple[VisualColorMark, ...]:
    """Return deterministic non-empty marks for the visual scanner review table."""
    cleaned = [mark for mark in marks if str(mark.field_id).strip() and str(mark.selected_text).strip()]
    return tuple(sorted(cleaned, key=lambda item: (item.field_id, item.start, item.end, item.selected_text)))


def replace_selection_with_placeholder(text: str, start: int, end: int, field_id: str = "field.id") -> str:
    """Replace a selected template fragment with a placeholder such as {{field.id}}."""
    source = str(text or "")
    left = max(0, min(len(source), int(start)))
    right = max(left, min(len(source), int(end)))
    return source[:left] + placeholder_for_field(field_id) + source[right:]


def insert_placeholder_after_selection(text: str, start: int, end: int, field_id: str = "field.id") -> str:
    """Insert a placeholder immediately after the selected template fragment."""
    source = str(text or "")
    right = max(0, min(len(source), int(end)))
    return source[:right] + placeholder_for_field(field_id) + source[right:]


def open_visual_scanner_dialog(parent=None, *, title: str = "Цветной сканер внутри программы") -> dict[str, object]:
    """Return the UI contract for the in-app visual scanner dialog."""
    return {
        "parent": parent,
        "title": title,
        "instruction": "Цветной сканер: выделите фрагмент",
        "enabled": visual_scanner_enabled,
        "actions": (source_extraction, template_replace, template_insert_after),
    }


def open_external_word_selection_scanner_dialog(parent=None) -> dict[str, object]:
    """Return the UI contract for taking the current selection from Word."""
    return {
        "parent": parent,
        "title": external_word_clipboard_selection,
        "enabled": external_word_scanner_enabled,
        "instruction": "Скопируйте выделение из Word и назначьте поле профиля.",
    }
