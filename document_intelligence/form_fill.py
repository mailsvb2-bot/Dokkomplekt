from __future__ import annotations

from pathlib import Path
from typing import Mapping

from docx import Document

from .text_utils import custom_field_id, normalize


def fill_docx_visible_fields(path: str | Path, values: Mapping[str, str]) -> tuple[str, ...]:
    document = Document(str(path))
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
    if filled:
        document.save(str(path))
    return tuple(dict.fromkeys(filled))
