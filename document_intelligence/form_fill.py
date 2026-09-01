from __future__ import annotations

from pathlib import Path
from typing import Mapping

from docx import Document

from .text_utils import custom_field_id, normalize


def _fill_paragraphs(document: Document, values: Mapping[str, str]) -> list[str]:
    filled: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text or ""
        if ":" not in text:
            continue
        label, tail = text.split(":", 1)
        if "___" not in tail:
            continue
        field_id = custom_field_id(label)
        value = str(values.get(field_id, "") or "").strip()
        if value:
            paragraph.text = f"{normalize(label)}: {value}"
            filled.append(field_id)
    return filled


def _fill_tables(document: Document, values: Mapping[str, str]) -> list[str]:
    filled: list[str] = []
    for table in document.tables:
        for row in table.rows:
            cells = list(row.cells)
            for index, cell in enumerate(cells[:-1]):
                label = normalize(cell.text).strip(" :")
                target = cells[index + 1]
                if not label or normalize(target.text):
                    continue
                field_id = custom_field_id(label)
                value = str(values.get(field_id, "") or "").strip()
                if value:
                    target.text = value
                    filled.append(field_id)
    return filled


def fill_docx_visible_fields(path: str | Path, values: Mapping[str, str]) -> tuple[str, ...]:
    document = Document(str(path))
    filled = [*_fill_paragraphs(document, values), *_fill_tables(document, values)]
    if filled:
        document.save(str(path))
    return tuple(dict.fromkeys(filled))
