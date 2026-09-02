from __future__ import annotations

from pathlib import Path
import re
from typing import Mapping

from docx import Document

from .text_utils import custom_field_id, normalize

_VISIBLE_BLANK_RE = re.compile(r"^[\s_—–.\-]{3,}$")


def visible_field_id(label: str, *, role_id: str = "", category: str = "", button_label: str = "") -> str:
    """Resolve a visible human label through the canonical field registry first."""

    try:
        from universal_fields import default_field_registry, normalize_field_id_for_context

        normalized = normalize_field_id_for_context(
            label,
            role_id=role_id,
            category=category,
            document_label=button_label,
        )
        if normalized.startswith("custom.") or normalized in default_field_registry():
            return normalized
        return custom_field_id(label)
    except ValueError:
        return custom_field_id(label)


def _is_visible_blank(value: object) -> bool:
    text = str(value or "")
    normalized = normalize(text)
    return not normalized or bool(_VISIBLE_BLANK_RE.fullmatch(text.strip()))


def visible_fill_field_ids(
    path: str | Path,
    *,
    role_id: str = "",
    category: str = "",
    button_label: str = "",
) -> tuple[str, ...]:
    """Return fields that can be filled from ordinary visible DOCX blanks.

    This is the non-programmer path for doctor-owned templates: labels such as
    ``ФИО: ______`` or a table row ``ФИО | ______`` are fillable without adding
    technical ``{{...}}`` markers by hand.
    """

    from .analyzer import DocumentIntelligenceCore
    from .models import DocumentSource

    blueprint = DocumentIntelligenceCore().analyze_source(DocumentSource(str(Path(path).expanduser())))
    field_ids = [
        visible_field_id(
            field.label,
            role_id=role_id,
            category=category,
            button_label=button_label,
        )
        for field in blueprint.fields
        if field.source in {"visible_blank", "table_neighbor_blank"}
    ]
    return tuple(dict.fromkeys(field_ids))


def _fill_paragraphs(
    document: Document,
    values: Mapping[str, str],
    *,
    role_id: str = "",
    category: str = "",
    button_label: str = "",
) -> list[str]:
    filled: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text or ""
        if ":" not in text:
            continue
        label, tail = text.split(":", 1)
        if not _is_visible_blank(tail):
            continue
        field_id = visible_field_id(label, role_id=role_id, category=category, button_label=button_label)
        value = str(values.get(field_id, "") or "").strip()
        if value:
            paragraph.text = f"{normalize(label)}: {value}"
            filled.append(field_id)
    return filled


def _fill_tables(
    document: Document,
    values: Mapping[str, str],
    *,
    role_id: str = "",
    category: str = "",
    button_label: str = "",
) -> list[str]:
    filled: list[str] = []
    for table in document.tables:
        for row in table.rows:
            cells = list(row.cells)
            for index, cell in enumerate(cells[:-1]):
                label = normalize(cell.text).strip(" :")
                target = cells[index + 1]
                if not label or not _is_visible_blank(target.text):
                    continue
                field_id = visible_field_id(label, role_id=role_id, category=category, button_label=button_label)
                value = str(values.get(field_id, "") or "").strip()
                if value:
                    target.text = value
                    filled.append(field_id)
    return filled


def fill_docx_visible_fields(
    path: str | Path,
    values: Mapping[str, str],
    *,
    role_id: str = "",
    category: str = "",
    button_label: str = "",
) -> tuple[str, ...]:
    document = Document(str(path))
    filled = [
        *_fill_paragraphs(
            document,
            values,
            role_id=role_id,
            category=category,
            button_label=button_label,
        ),
        *_fill_tables(
            document,
            values,
            role_id=role_id,
            category=category,
            button_label=button_label,
        ),
    ]
    if filled:
        document.save(str(path))
    return tuple(dict.fromkeys(filled))
