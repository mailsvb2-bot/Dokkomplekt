from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence

from diagnostic_logging import record_soft_exception
from medical_field_line_pairs import line_starts_with_label
from medical_text_utils import clean_value, looks_like_label, normalize_match, normalize_text


_INVISIBLE_WORD_FORMATTING_RE = re.compile(r"[\u00ad\u200b\u200c\u200d\u2060\ufeff]")
_WORD_SEPARATOR_RE = re.compile(r"[\ufffc\ufffe\uffff]")
_NAME_TOKEN = r"(?:[А-ЯЁ][а-яё]+|[А-ЯЁ]{2,})(?:-(?:[А-ЯЁ][а-яё]+|[А-ЯЁ]{2,}))?"
_FULL_FIO_RE = re.compile(rf"(?<![А-ЯЁа-яё-])({_NAME_TOKEN}\s+{_NAME_TOKEN}\s+{_NAME_TOKEN})(?![А-ЯЁа-яё-])")
_PATIENT_FIO_LABEL_RE = re.compile(
    r"^\s*(?:ф\.?\s*и\.?\s*о\.?|фио|фамилия\s*,?\s*имя\s*,?\s*отчество|пациент(?:ка)?|больн(?:ой|ая))"
    r"(?:\s+(?:пациент(?:а|ки)|больн(?:ого|ой)))?"
    r"(?:\s*\([^\n)]{0,60}\))?\s*[:№N#.-]*\s*",
    flags=re.IGNORECASE,
)
_CLINICIAN_QUALIFIER_RE = re.compile(
    r"(?i)(?:лечащ\w*|врач\w*|доктор\w*|фельдшер\w*|заведующ\w*|"
    r"хирург\w*|терапевт\w*|психиатр\w*|ординатор\w*)"
)


def normalize_word_parser_text(text: str) -> str:
    value = str(text or "")
    if not value:
        return ""
    value = _INVISIBLE_WORD_FORMATTING_RE.sub("", value)
    value = _WORD_SEPARATOR_RE.sub(" ", value)
    value = value.replace("\f", "\n").replace("\u2028", "\n").replace("\u2029", "\n")
    return normalize_text(value)


def _full_fio(chunks: Iterable[str]) -> str:
    combined = " ".join(clean_value(normalize_word_parser_text(chunk)) for chunk in chunks if str(chunk or "").strip())
    match = _FULL_FIO_RE.search(combined)
    return clean_value(match.group(1)) if match else ""


def _iter_tables(container):
    for table in getattr(container, "tables", ()):
        yield table
        for row in table.rows:
            seen: set[int] = set()
            for cell in row.cells:
                cell_id = id(cell._tc)
                if cell_id in seen:
                    continue
                seen.add(cell_id)
                yield from _iter_tables(cell)


def reconcile_patient_fio_from_docx(path: str | Path, *, parsed_fio: str, all_aliases: Sequence[str]) -> str:
    """Validate/recover patient FIO from Word table geometry.

    Patient-labelled geometry wins. A parsed name that is physically located
    under a clinician FIO caption is rejected instead of being promoted to the
    patient identity by the flattened-text fallback.
    """
    try:
        from docx import Document
        from medical_docx_xml_fragments import ensure_docx_compatible

        document = Document(str(ensure_docx_compatible(path, label="primary Word document")))
    except Exception as exc:
        record_soft_exception("medical_docx_fio_recovery.open", exc, detail=str(path))
        return parsed_fio

    clinician_fios: set[str] = set()

    def candidate_from(chunks: Iterable[str]) -> str:
        collected: list[str] = []
        for raw in chunks:
            value = clean_value(normalize_word_parser_text(raw))
            if not value:
                continue
            if looks_like_label(value) or line_starts_with_label(value, all_aliases):
                break
            collected.append(value)
            fio = _full_fio(collected)
            if fio:
                return fio
        return ""

    try:
        containers = [document]
        for section in document.sections:
            containers.extend((section.header, section.footer))
        for container in containers:
            for table in _iter_tables(container):
                rows = [[normalize_word_parser_text(cell.text) for cell in row.cells] for row in table.rows]
                for row_index, cells in enumerate(rows):
                    for col_index, cell_text in enumerate(cells):
                        match = _PATIENT_FIO_LABEL_RE.match(cell_text)
                        if not match:
                            continue
                        tail = clean_value(cell_text[match.end():])
                        if _CLINICIAN_QUALIFIER_RE.search(normalize_match(tail)):
                            for next_row in range(row_index + 1, min(len(rows), row_index + 4)):
                                clinician = _full_fio(rows[next_row][col_index: col_index + 3])
                                if clinician:
                                    clinician_fios.add(normalize_match(clinician))
                                    break
                            continue

                        fio = candidate_from(([tail] if tail else []) + cells[col_index + 1: col_index + 4])
                        if fio:
                            return fio

                        for next_row in range(row_index + 1, min(len(rows), row_index + 4)):
                            below = rows[next_row][col_index: col_index + 3]
                            fio = candidate_from(below)
                            if fio:
                                return fio
                            if any(
                                looks_like_label(value) or line_starts_with_label(value, all_aliases)
                                for value in below if value
                            ):
                                break
    except Exception as exc:
        record_soft_exception("medical_docx_fio_recovery.scan", exc, detail=str(path))
    if parsed_fio and normalize_match(parsed_fio) in clinician_fios:
        return ""
    return parsed_fio
