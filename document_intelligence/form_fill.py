from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, Mapping

from docx import Document

from .text_utils import custom_field_id, normalize
BLANK_RE = re.compile(r"[_—–-]{3,}|\.{4,}")
SIGNATURE_RE = re.compile(r"(?i)(подпись|директор|бухгалтер|врач|зав\.?\s*отдел|исполнитель|составил|утверждаю|signature|accountant|director|approved)")


@dataclass(frozen=True)
class VisibleBlankSlot:
    label: str
    start: int
    end: int


def visible_blank_slot(text: object) -> VisibleBlankSlot | None:
    """Find one human-labelled blank while preserving all fixed surrounding text."""
    raw = str(text or "")
    matches = list(BLANK_RE.finditer(raw))
    if not matches:
        return None
    first, last = matches[0], matches[-1]
    prefix = raw[: first.start()].rstrip()
    if not prefix:
        return None
    # Prefer an explicit colon (ASCII or full-width).  Otherwise the historical
    # ``ФИО ______`` form uses everything before the blank as the label.
    colon_at = max(prefix.rfind(":"), prefix.rfind("："))
    if colon_at >= 0:
        label = prefix[:colon_at].strip()
    else:
        label = prefix.strip()
    label = label.strip(" :：\t")
    if len(label) < 2 or len(label) > 90 or SIGNATURE_RE.search(label):
        return None
    return VisibleBlankSlot(label, first.start(), last.end())


def blank_region(text: object) -> tuple[int, int] | None:
    raw = str(text or "")
    matches = list(BLANK_RE.finditer(raw))
    if not matches:
        return None
    return matches[0].start(), matches[-1].end()


def unique_cells(table) -> Iterable:
    seen: set[int] = set()
    for row in table.rows:
        for cell in row.cells:
            key = id(cell._tc)
            if key in seen:
                continue
            seen.add(key)
            yield cell


def iter_tables_recursive(table) -> Iterable:
    yield table
    for cell in unique_cells(table):
        for nested in cell.tables:
            yield from iter_tables_recursive(nested)


def iter_document_tables(document) -> Iterable:
    seen: set[int] = set()

    def emit(table):
        key = id(table._tbl)
        if key in seen:
            return
        seen.add(key)
        yield from iter_tables_recursive(table)

    for table in document.tables:
        yield from emit(table)
    for section in document.sections:
        for area in (section.header, section.footer):
            for table in area.tables:
                yield from emit(table)


def iter_direct_story_paragraphs(document) -> Iterable:
    """Paragraphs not inside tables: body plus each unique header/footer."""
    seen: set[int] = set()
    for paragraph in document.paragraphs:
        key = id(paragraph._p)
        if key not in seen:
            seen.add(key)
            yield paragraph
    for section in document.sections:
        for area in (section.header, section.footer):
            for paragraph in area.paragraphs:
                key = id(paragraph._p)
                if key not in seen:
                    seen.add(key)
                    yield paragraph


def iter_all_story_paragraphs(document) -> Iterable:
    """Yield every Word paragraph once, including tables and text-box XML."""
    from docx.oxml.ns import qn
    from docx.text.paragraph import Paragraph

    seen: set[object] = set()

    def emit(paragraph):
        key = paragraph._p
        if key in seen:
            return
        seen.add(key)
        yield paragraph

    for paragraph in iter_direct_story_paragraphs(document):
        yield from emit(paragraph)
    for table in iter_document_tables(document):
        for cell in unique_cells(table):
            for paragraph in cell.paragraphs:
                yield from emit(paragraph)
    # python-docx high-level collections omit text boxes/shapes. Walk raw story
    # XML after structured paragraphs so analyzer and renderer see the same slots.
    roots = [(document.element.body, document)]
    for section in document.sections:
        roots.extend(((section.header._element, section.header), (section.footer._element, section.footer)))
    for root, parent in roots:
        for element in root.iter(qn("w:p")):
            yield from emit(Paragraph(element, parent))

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



def known_semantic_field_id(label: str, *, role_id: str = "", category: str = "", button_label: str = "") -> str:
    """Resolve only canonical registry fields; never invent a custom field from sample text."""
    try:
        from universal_fields import default_field_registry, normalize_field_id_for_context
        field_id = normalize_field_id_for_context(
            label,
            role_id=role_id,
            category=category,
            document_label=button_label,
        )
        return field_id if default_field_registry().get(field_id) is not None else ""
    except (KeyError, ValueError):
        return ""


def _semantic_inline_slot(text: object, *, role_id: str = "", category: str = "", button_label: str = "") -> tuple[str, int, int] | None:
    """Find ``known label: old sample value`` so the sample can never be patient data."""
    raw = str(text or "")
    if not raw or BLANK_RE.search(raw):
        return None
    match = re.match(r"^\s*(?P<label>.{2,180}?)(?P<sep>\s*[:：]\s*|\s+[–—-]\s+)(?P<value>.*)$", raw)
    if not match:
        return None
    label = match.group("label").strip()
    if SIGNATURE_RE.search(label):
        return None
    field_id = known_semantic_field_id(label, role_id=role_id, category=category, button_label=button_label)
    if not field_id:
        normalized_label = normalize(label).lower().replace("ё", "е")
        if normalized_label.endswith("диагноз") or "выставлен диагноз" in normalized_label:
            field_id = "diagnosis.main"
    if not field_id:
        return None
    return field_id, match.start("value"), len(raw)


def _exact_semantic_label(text: object, *, role_id: str = "", category: str = "", button_label: str = "") -> str:
    raw = normalize(text).strip(" \t:：–—-")
    if not raw or SIGNATURE_RE.search(raw):
        return ""
    return known_semantic_field_id(raw, role_id=role_id, category=category, button_label=button_label)


def _semantic_definition(field_id: str):
    try:
        from universal_fields import default_field_registry
        return default_field_registry().get(field_id)
    except (KeyError, ValueError):
        return None


def _replace_entire_paragraph(paragraph, value: str) -> None:
    text = paragraph.text or ""
    if text:
        if not _replace_paragraph_span(paragraph, 0, len(text), value):
            paragraph.text = value
    elif value:
        paragraph.add_run(value)


def _replace_cell_value(cell, value: str) -> None:
    paragraphs = list(cell.paragraphs)
    if not paragraphs:
        paragraphs = [cell.add_paragraph()]
    _replace_entire_paragraph(paragraphs[0], value)
    for paragraph in paragraphs[1:]:
        _replace_entire_paragraph(paragraph, "")



_NAME_TOKEN = r"[А-ЯЁ][А-ЯЁа-яё'-]{1,60}"
_DEMOGRAPHIC_LINE_RE = re.compile(
    rf"^\s*(?P<fio>{_NAME_TOKEN}\s+{_NAME_TOKEN}\s+{_NAME_TOKEN})\s*,\s*"
    r"(?P<birth>\d{1,2}[.]\d{1,2}[.]\d{2,4})\s*г\.?\s*р\.?(?P<rest>.*)$"
)
_EPISODE_PERIOD_RE = re.compile(
    r"(?P<prefix>\bс\s+)(?P<start>\d{1,2}[.]\d{1,2}[.]\d{2,4})(?P<middle>\s+по\s+)(?P<end>\d{1,2}[.]\d{1,2}[.]\d{2,4})",
    flags=re.IGNORECASE,
)
_DISCHARGE_TITLE_RE = re.compile(r"^\s*(?P<date>\d{1,2}[.]\d{1,2}[.]\d{2,4})(?P<tail>\s+Выпис\w*\s+эпикриз\b.*)$", flags=re.IGNORECASE)


def _replace_structured_patient_sentences(document: Document, values: Mapping[str, str]) -> list[str]:
    """Replace patient-specific sample prose that has no explicit blank/placeholder."""
    filled: list[str] = []
    for paragraph in iter_all_story_paragraphs(document):
        raw = str(paragraph.text or "")
        if not raw:
            continue
        demographic = _DEMOGRAPHIC_LINE_RE.match(raw)
        if demographic:
            fio = str(values.get("patient.fio", "") or "").strip()
            birth = str(values.get("patient.birth_date", "") or "").strip()
            address = str(values.get("patient.address", "") or "").strip()
            if fio:
                parts = [fio]
                if birth:
                    parts.append(f"{birth} г.р.")
                replacement = ", ".join(parts)
                if address:
                    replacement += f", зарегистрирован по адресу: {address}"
                _replace_entire_paragraph(paragraph, replacement)
                filled.extend([field for field, value in (
                    ("patient.fio", fio), ("patient.birth_date", birth), ("patient.address", address)
                ) if value])
                continue

        if "лечен" in raw.lower().replace("ё", "е") or "госпитал" in raw.lower().replace("ё", "е"):
            period = _EPISODE_PERIOD_RE.search(raw)
            admission = str(values.get("admission.date", "") or "").strip()
            discharge = str(values.get("discharge.date", "") or "").strip()
            if period and admission and discharge:
                replacement = raw[:period.start()] + period.group("prefix") + admission + period.group("middle") + discharge + raw[period.end():]
                _replace_entire_paragraph(paragraph, replacement)
                filled.extend(("admission.date", "discharge.date"))
                continue

        title = _DISCHARGE_TITLE_RE.match(raw)
        discharge = str(values.get("discharge.date", "") or "").strip()
        if title and discharge:
            replacement = discharge + title.group("tail")
            case_number = str(values.get("case.number", "") or "").strip()
            if case_number:
                replacement = re.sub(r"(№\s*)[^\s,;]+", lambda match: match.group(1) + case_number, replacement, count=1)
                filled.append("case.number")
            _replace_entire_paragraph(paragraph, replacement)
            filled.append("discharge.date")
    return filled


def _fill_prefilled_semantic_paragraphs(
    document: Document,
    values: Mapping[str, str],
    *,
    role_id: str = "",
    category: str = "",
    button_label: str = "",
    skip_field_ids: Iterable[str] = (),
) -> list[str]:
    filled: list[str] = []
    skipped = {str(field_id).strip() for field_id in skip_field_ids if str(field_id).strip()}
    for paragraph in iter_all_story_paragraphs(document):
        slot = _semantic_inline_slot(paragraph.text, role_id=role_id, category=category, button_label=button_label)
        if slot is None:
            continue
        field_id, start, end = slot
        if field_id in skipped:
            continue
        definition = _semantic_definition(field_id)
        value = str(values.get(field_id, "") or "").strip()
        # Fixed signature names belong to the doctor/template profile, not patient data.
        if definition is not None and definition.group == "signatures" and not value:
            continue
        if _replace_paragraph_span(paragraph, start, end, value):
            filled.append(field_id)
    return filled


def _fill_semantic_block_sections(document: Document, values: Mapping[str, str], *, role_id: str = "", category: str = "", button_label: str = "") -> list[str]:
    """Replace/clear sample block text following an exact semantic heading."""
    paragraphs = list(iter_direct_story_paragraphs(document))
    filled: list[str] = []
    for index, paragraph in enumerate(paragraphs):
        field_id = _exact_semantic_label(paragraph.text, role_id=role_id, category=category, button_label=button_label)
        definition = _semantic_definition(field_id) if field_id else None
        if not field_id or definition is None or definition.value_kind != "block" or definition.group == "signatures":
            continue
        end = index + 1
        while end < len(paragraphs):
            probe = paragraphs[end]
            if _semantic_inline_slot(probe.text, role_id=role_id, category=category, button_label=button_label):
                break
            if _exact_semantic_label(probe.text, role_id=role_id, category=category, button_label=button_label):
                break
            if SIGNATURE_RE.search(normalize(probe.text)):
                break
            end += 1
        if end <= index + 1:
            continue
        value = str(values.get(field_id, "") or "").strip()
        wrote = False
        for target in paragraphs[index + 1:end]:
            if value and not wrote:
                _replace_entire_paragraph(target, value)
                wrote = True
            else:
                _replace_entire_paragraph(target, "")
        filled.append(field_id)
    return filled


def _row_unique_cells(row) -> list:
    cells: list = []
    seen: set[int] = set()
    for cell in row.cells:
        key = id(cell._tc)
        if key in seen:
            continue
        seen.add(key)
        cells.append(cell)
    return cells


def _fill_prefilled_semantic_tables(document: Document, values: Mapping[str, str], *, role_id: str = "", category: str = "", button_label: str = "") -> list[str]:
    filled: list[str] = []
    for table in iter_document_tables(document):
        rows = [_row_unique_cells(row) for row in table.rows]
        for row_index, cells in enumerate(rows):
            known = [
                _exact_semantic_label(cell.text, role_id=role_id, category=category, button_label=button_label)
                for cell in cells
            ]
            # Label/value pairs in the same row, including already populated sample values.
            for index, field_id in enumerate(known[:-1]):
                if not field_id or known[index + 1]:
                    continue
                target = cells[index + 1]
                # Leave visible blank templates to the legacy blank filler so
                # fixed framing text such as ``№ ____ / ____ архив`` survives.
                if any(blank_region(paragraph.text) is not None for paragraph in target.paragraphs):
                    continue
                definition = _semantic_definition(field_id)
                value = str(values.get(field_id, "") or "").strip()
                if definition is not None and definition.group == "signatures" and not value:
                    continue
                _replace_cell_value(target, value)
                filled.append(field_id)
            # Header-row forms: ФИО | Дата рождения | Адрес, values in the row below.
            known_count = sum(1 for field_id in known if field_id)
            if known_count >= 2 and row_index + 1 < len(rows):
                below = rows[row_index + 1]
                for index, field_id in enumerate(known):
                    if not field_id or index >= len(below):
                        continue
                    target = below[index]
                    if any(blank_region(paragraph.text) is not None for paragraph in target.paragraphs):
                        continue
                    definition = _semantic_definition(field_id)
                    value = str(values.get(field_id, "") or "").strip()
                    if definition is not None and definition.group == "signatures" and not value:
                        continue
                    _replace_cell_value(target, value)
                    filled.append(field_id)
    return filled


def semantic_fill_field_ids(path: str | Path, *, role_id: str = "", category: str = "", button_label: str = "") -> tuple[str, ...]:
    """Discover canonical fields even when a doctor template contains sample values."""
    document = Document(str(Path(path).expanduser()))
    found: list[str] = []
    for paragraph in iter_all_story_paragraphs(document):
        slot = _semantic_inline_slot(paragraph.text, role_id=role_id, category=category, button_label=button_label)
        if slot:
            found.append(slot[0])
        field_id = _exact_semantic_label(paragraph.text, role_id=role_id, category=category, button_label=button_label)
        if field_id:
            found.append(field_id)
    for table in iter_document_tables(document):
        rows = [_row_unique_cells(row) for row in table.rows]
        for cells in rows:
            known = [
                _exact_semantic_label(cell.text, role_id=role_id, category=category, button_label=button_label)
                for cell in cells
            ]
            found.extend(field_id for field_id in known if field_id)
    return tuple(dict.fromkeys(found))


def _replace_paragraph_span(paragraph, start: int, end: int, value: str) -> bool:
    """Replace a character span without flattening the paragraph's run formatting."""
    if end <= start:
        return False
    runs = list(paragraph.runs)
    if not runs:
        paragraph.add_run(value)
        return True
    cursor = 0
    touched = False
    inserted = False
    for run in runs:
        text = run.text or ""
        run_start, run_end = cursor, cursor + len(text)
        cursor = run_end
        if run_end <= start or run_start >= end:
            continue
        local_start = max(0, start - run_start)
        local_end = min(len(text), end - run_start)
        prefix = text[:local_start]
        suffix = text[local_end:]
        if not inserted:
            run.text = prefix + value + suffix
            inserted = True
        else:
            run.text = prefix + suffix
        touched = True
    return touched


def _fill_labelled_paragraphs(
    document: Document,
    values: Mapping[str, str],
    *,
    role_id: str = "",
    category: str = "",
    button_label: str = "",
) -> list[str]:
    filled: list[str] = []
    for paragraph in iter_all_story_paragraphs(document):
        slot = visible_blank_slot(paragraph.text)
        if slot is None:
            continue
        field_id = visible_field_id(slot.label, role_id=role_id, category=category, button_label=button_label)
        value = str(values.get(field_id, "") or "").strip()
        if value and _replace_paragraph_span(paragraph, slot.start, slot.end, value):
            filled.append(field_id)
    return filled


def _cell_blank_paragraph(cell):
    for paragraph in cell.paragraphs:
        region = blank_region(paragraph.text)
        if region is not None:
            return paragraph, region
    # A genuinely empty cell is also a fill target.
    if not normalize(cell.text):
        paragraph = cell.paragraphs[0] if cell.paragraphs else cell.add_paragraph()
        return paragraph, None
    return None, None


def _fill_tables(
    document: Document,
    values: Mapping[str, str],
    *,
    role_id: str = "",
    category: str = "",
    button_label: str = "",
) -> list[str]:
    filled: list[str] = []
    for table in iter_document_tables(document):
        for row in table.rows:
            cells = []
            seen: set[int] = set()
            for cell in row.cells:
                key = id(cell._tc)
                if key in seen:
                    continue
                seen.add(key)
                cells.append(cell)
            for index, cell in enumerate(cells[:-1]):
                label = normalize(cell.text).strip(" :：")
                if not label:
                    continue
                target = cells[index + 1]
                paragraph, region = _cell_blank_paragraph(target)
                if paragraph is None:
                    continue
                field_id = visible_field_id(label, role_id=role_id, category=category, button_label=button_label)
                value = str(values.get(field_id, "") or "").strip()
                if not value:
                    continue
                if region is None:
                    paragraph.add_run(value)
                else:
                    _replace_paragraph_span(paragraph, region[0], region[1], value)
                filled.append(field_id)
    return filled


def fill_docx_visible_fields(
    path: str | Path,
    values: Mapping[str, str],
    *,
    role_id: str = "",
    category: str = "",
    button_label: str = "",
    skip_semantic_fields: Iterable[str] = (),
) -> tuple[str, ...]:
    document = Document(str(path))
    filled = [
        *_replace_structured_patient_sentences(document, values),
        *_fill_prefilled_semantic_paragraphs(
            document,
            values,
            role_id=role_id,
            category=category,
            button_label=button_label,
            skip_field_ids=skip_semantic_fields,
        ),
        *_fill_semantic_block_sections(
            document, values, role_id=role_id, category=category, button_label=button_label,
        ),
        *_fill_prefilled_semantic_tables(
            document, values, role_id=role_id, category=category, button_label=button_label,
        ),
        *_fill_labelled_paragraphs(
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


def visible_fill_field_ids(
    path: str | Path,
    *,
    role_id: str = "",
    category: str = "",
    button_label: str = "",
) -> tuple[str, ...]:
    """Return semantic ids for every ordinary Word blank this renderer can fill."""
    document = Document(str(Path(path).expanduser()))
    field_ids: list[str] = []
    for paragraph in iter_all_story_paragraphs(document):
        slot = visible_blank_slot(paragraph.text)
        if slot is not None:
            field_ids.append(visible_field_id(slot.label, role_id=role_id, category=category, button_label=button_label))
    for table in iter_document_tables(document):
        for row in table.rows:
            cells: list = []
            seen: set[int] = set()
            for cell in row.cells:
                key = id(cell._tc)
                if key in seen:
                    continue
                seen.add(key); cells.append(cell)
            for index, cell in enumerate(cells[:-1]):
                label = normalize(cell.text).strip(" :：")
                if not label:
                    continue
                paragraph, _region = _cell_blank_paragraph(cells[index + 1])
                if paragraph is not None:
                    field_ids.append(visible_field_id(label, role_id=role_id, category=category, button_label=button_label))
    return tuple(dict.fromkeys(field_ids))



def _normalized_case_text(value: object) -> str:
    return " ".join(str(value or "").lower().replace("ё", "е").split())


def _normalized_identity_text(value: object) -> str:
    """Normalize FIO punctuation/spacing without weakening identity matching.

    Orthography may render initials as ``И. И.`` even when the canonical case
    stores ``И.И.``.  Consistency checks must compare the letters themselves,
    not typography around them.  Removing only non-word separators preserves
    every surname/name/initial character and digit while making those two
    spellings equivalent.
    """
    normalized = str(value or "").casefold().replace("ё", "е")
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


def _normalized_icd_code(value: object) -> str:
    match = re.search(r"(?i)([A-ZА-ЯЁ])\s*(\d{2})(?:[.,]\s*([0-9A-ZА-ЯЁ]+))?", str(value or ""))
    if not match:
        return ""
    suffix = f".{match.group(3)}" if match.group(3) else ""
    return (match.group(1) + match.group(2) + suffix).upper().replace("Ё", "Е")


def rendered_case_consistency_errors(output: str | Path, case: object, document: object) -> tuple[str, ...]:
    """Return contradictions between a rendered medical DOCX and its canonical case."""
    try:
        from medical_docx_reader import extract_docx_text
        text = extract_docx_text(output)
    except Exception as exc:
        return (f"не удалось повторно прочитать созданный DOCX: {exc}",)

    normalized_text = _normalized_case_text(text)
    try:
        from universal_main_documents import semantic_role_for_document
        role = semantic_role_for_document(document)
    except Exception:
        role = "unknown"
    try:
        from universal_fields import normalize_field_id_for_context
        declared = {
            normalize_field_id_for_context(
                raw,
                role_id=getattr(document, "role_id", ""),
                category=getattr(document, "category", ""),
                document_label=getattr(document, "button_label", ""),
            )
            for raw in (*tuple(getattr(document, "required_fields", ()) or ()), *tuple(getattr(document, "optional_fields", ()) or ()))
            if str(raw or "").strip()
        }
    except Exception:
        declared = set()

    def case_get(field_id: str) -> str:
        getter = getattr(case, "get", None)
        return str(getter(field_id) if callable(getter) else "").strip()

    errors: list[str] = []
    medical_roles = {
        "primary_exam", "admission_doctor_exam", "hospitalization_referral",
        "discharge_epicrisis", "transfer_epicrisis", "rvk_act", "medical_commission",
        "joint_medical_exam", "mse_referral", "sick_leave_vk", "temporary_disability_commission",
    }
    expected_fio = case_get("patient.fio")
    if expected_fio and ("patient.fio" in declared or role in medical_roles):
        normalized_identity = _normalized_identity_text(expected_fio)
        rendered_identity = _normalized_identity_text(text)
        if normalized_identity and normalized_identity not in rendered_identity:
            errors.append("ФИО созданного документа не совпадает с канонической карточкой пациента")

    demographic_re = re.compile(
        r"^\s*(?P<fio>[А-ЯЁ][А-ЯЁа-яё'-]+\s+[А-ЯЁ][А-ЯЁа-яё'-]+\s+[А-ЯЁ][А-ЯЁа-яё'-]+)\s*,\s*"
        r"(?P<birth>\d{1,2}[.]\d{1,2}[.]\d{2,4})\s*г\.?\s*р\.?,?",
    )
    for line in text.splitlines()[:80]:
        match = demographic_re.match(line)
        if not match:
            continue
        if expected_fio and _normalized_identity_text(match.group("fio")) != _normalized_identity_text(expected_fio):
            errors.append("в демографической строке остались данные другого пациента")
        expected_birth = case_get("patient.birth_date")
        if expected_birth and match.group("birth") != expected_birth:
            errors.append("дата рождения в демографической строке расходится с канонической карточкой")
        break

    expected_admission = case_get("admission.date")
    expected_discharge = case_get("discharge.date")
    if role in {"discharge_epicrisis", "transfer_epicrisis"}:
        period = re.search(
            r"\bс\s+(\d{1,2}[.]\d{1,2}[.]\d{2,4})\s+по\s+(\d{1,2}[.]\d{1,2}[.]\d{2,4})",
            text, flags=re.IGNORECASE,
        )
        if period:
            if expected_admission and period.group(1) != expected_admission:
                errors.append("дата поступления в периоде лечения расходится с канонической карточкой")
            if expected_discharge and period.group(2) != expected_discharge:
                errors.append("дата выписки в периоде лечения расходится с канонической карточкой")
        title = re.search(r"(?m)^\s*(\d{1,2}[.]\d{1,2}[.]\d{2,4})\s+Выпис\w*\s+эпикриз\b", text, flags=re.IGNORECASE)
        if title and expected_discharge and title.group(1) != expected_discharge:
            errors.append("дата в заголовке выписного эпикриза расходится с канонической карточкой")

    expected_code = _normalized_icd_code(case_get("diagnosis.main"))
    if expected_code and (
        "diagnosis.main" in declared
        or "diagnosis.icd10" in declared
        or role in {"discharge_epicrisis", "transfer_epicrisis", "rvk_act", "medical_commission", "joint_medical_exam", "mse_referral", "sick_leave_vk"}
    ):
        compact_text = re.sub(r"\s+", "", text.upper().replace(",", "."))
        if expected_code not in compact_text:
            errors.append("диагноз/МКБ созданного документа расходится с канонической карточкой")

    return tuple(dict.fromkeys(errors))
