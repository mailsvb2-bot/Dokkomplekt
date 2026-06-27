"""Universal labs block support for doctor-owned medical templates.

The program must not invent laboratory results.  This module stores analyses as
explicit case data: typed by the doctor, loaded from a separate file, extracted
from a source document, or selected manually in the scanner.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import TYPE_CHECKING, Iterable, Mapping, Sequence

from medical_formatting import parse_date

if TYPE_CHECKING:
    from medical_docx_editor import DocxBlockEditor

_DATE_RE = re.compile(r"(?<!\d)([0-3]?\d[.\-/][01]?\d[.\-/](?:19|20)?\d{2}|[0-3]?\d[01]\d(?:19|20)?\d{2})(?!\d)")
_TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "cp1251")

LABS_FIELD_ID = "labs.results"
LABS_DATE_FIELD_ID = "labs.date"
LABS_SOURCE_FIELD_ID = "labs.source"
LABS_DATE_POLICY_FIELD_ID = "labs.date_policy"

LABS_PLACEHOLDER_ALIASES: dict[str, str] = {
    "labs.block": LABS_FIELD_ID,
    "labs.results": LABS_FIELD_ID,
    "analysis.results": LABS_FIELD_ID,
    "analyses.results": LABS_FIELD_ID,
    "laboratory.results": LABS_FIELD_ID,
    "laboratory.block": LABS_FIELD_ID,
    "laboratory_results": LABS_FIELD_ID,
    "laboratory_block": LABS_FIELD_ID,
    "lab.results": LABS_FIELD_ID,
    "lab.block": LABS_FIELD_ID,
    "labs_block": LABS_FIELD_ID,
    "lab_block": LABS_FIELD_ID,
    "analysis_block": LABS_FIELD_ID,
    "analyses_block": LABS_FIELD_ID,
    "анализы": LABS_FIELD_ID,
    "блок_анализов": LABS_FIELD_ID,
    "результаты_анализов": LABS_FIELD_ID,
    "лабораторные_исследования": LABS_FIELD_ID,
}

LABS_DATE_POLICIES: dict[str, str] = {
    "preserve_found_dates": "оставить найденные даты",
    "auto_from_source_or_document": "пусть даты подставит программа",
    "document_date": "использовать дату документа",
    "manual": "дата введена врачом",
}

_LABS_MARKERS = (
    "анализ", "анализы", "лаборатор", "оак", "оам", "бак", "биохим",
    "общий анализ крови", "общий анализ мочи", "глюкоз", "креатинин",
    "лейкоц", "эритроц", "гемоглоб", "тромбоц", "алт", "аст", "билирубин",
    "мочевин", "соэ", "crp", "с-реактив", "коагул", "rw", "hcv", "hbsag", "вич",
)

_LABS_STOP_MARKERS = (
    "диагноз", "лечение", "рекомендации", "анамнез", "жалобы", "статус",
    "осмотр", "выписан", "выписана", "заключение", "подпись", "врач",
)


@dataclass(frozen=True)
class LabsBlock:
    text: str = ""
    source: str = ""
    date_policy: str = "preserve_found_dates"
    explicit_date: str = ""
    without_labs: bool = False

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip()) and not self.without_labs

    def to_case_values(self) -> dict[str, str]:
        if self.without_labs:
            return {LABS_FIELD_ID: "", LABS_DATE_POLICY_FIELD_ID: "without_labs"}
        result = {LABS_FIELD_ID: self.text.strip(), LABS_DATE_POLICY_FIELD_ID: self.date_policy}
        if self.source:
            result[LABS_SOURCE_FIELD_ID] = self.source
        if self.explicit_date:
            result[LABS_DATE_FIELD_ID] = self.explicit_date
        return {key: value for key, value in result.items() if value}


def canonical_labs_placeholder(raw: str) -> str:
    key = "_".join(str(raw or "").strip().lower().replace("-", "_").split())
    return LABS_PLACEHOLDER_ALIASES.get(key, key)


def normalize_labs_block(
    raw_text: str,
    *,
    default_date: str = "",
    date_policy: str = "preserve_found_dates",
    explicit_date: str = "",
    without_labs: bool = False,
) -> str:
    """Return a safe human-readable labs block without invented results."""

    if without_labs:
        return ""
    text = _clean_multiline(raw_text)
    if not text:
        return ""
    policy = str(date_policy or "preserve_found_dates").strip() or "preserve_found_dates"
    if policy == "auto_from_source_or_document" and not contains_date(text):
        date = normalize_date(explicit_date) or normalize_date(default_date)
        if date:
            text = f"Дата анализов: {date}\n{text}"
    elif policy == "document_date" and not contains_date(text):
        date = normalize_date(default_date)
        if date:
            text = f"Дата анализов: {date}\n{text}"
    elif policy == "manual" and explicit_date and not contains_date(text):
        date = normalize_date(explicit_date)
        if date:
            text = f"Дата анализов: {date}\n{text}"
    return text


def labs_block_from_values(
    *,
    text: str = "",
    source: str = "",
    date_policy: str = "preserve_found_dates",
    default_date: str = "",
    explicit_date: str = "",
    without_labs: bool = False,
) -> LabsBlock:
    normalized = normalize_labs_block(
        text,
        default_date=default_date,
        date_policy=date_policy,
        explicit_date=explicit_date,
        without_labs=without_labs,
    )
    normalized_policy = "without_labs" if without_labs else (date_policy or "preserve_found_dates")
    return LabsBlock(normalized, source=source, date_policy=normalized_policy, explicit_date=explicit_date, without_labs=without_labs)


def extract_labs_from_file(path: str | Path, *, date_policy: str = "preserve_found_dates", default_date: str = "") -> LabsBlock:
    source = Path(path).expanduser()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Файл с анализами не найден: {source}")
    suffix = source.suffix.lower()
    if suffix in {".docx", ".docm"}:
        from medical_docx_reader import extract_docx_text
        raw = extract_docx_text(source)
    elif suffix in {".txt", ".csv"}:
        raw = _read_text_file(source)
    else:
        raise ValueError(f"Файл анализов должен быть DOCX/DOCM/TXT/CSV, получено: {source.suffix or 'без расширения'}")
    extracted = extract_labs_from_text(raw)
    if not extracted:
        raise ValueError("В выбранном файле не распознан блок анализов. Выберите файл с результатами анализов или вставьте текст вручную.")
    return labs_block_from_values(text=extracted, source=str(source), date_policy=date_policy, default_date=default_date)


def extract_labs_from_text(text: str) -> str:
    """Extract a likely laboratory-results section; return full cleaned text as fallback."""

    cleaned = _clean_multiline(text)
    if not cleaned:
        return ""
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    start = _first_labs_line_index(lines)
    if start is None:
        return cleaned if looks_like_labs_source_text(cleaned, strong_only=True) else ""
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        low = _norm(lines[idx])
        if any(low.startswith(marker) for marker in _LABS_STOP_MARKERS) and not any(marker in low for marker in _LABS_MARKERS):
            end = idx
            break
    selected = "\n".join(lines[start:end]).strip()
    return selected or cleaned


def looks_like_labs_source_text(text: str, *, strong_only: bool = False) -> bool:
    low = _norm(text)
    if not low:
        return False
    marker_hits = sum(1 for marker in _LABS_MARKERS if marker in low)
    numeric_result = bool(re.search(r"(?i)\b(?:hb|hgb|лейкоц|эритроц|тромбоц|глюкоз|алт|аст|креатинин|соэ)\b[^\n\r]{0,40}\d", low))
    if strong_only:
        return marker_hits >= 2 or numeric_result
    return marker_hits >= 1 and (numeric_result or "результат" in low or "норма" in low or "ед" in low)


def contains_date(text: str) -> bool:
    return bool(_DATE_RE.search(str(text or "")))


def normalize_date(value: str) -> str:
    """Normalize an analyses date with the same strict parser as UI episode dates."""

    text = str(value or "").strip()
    if not text:
        return ""
    direct = parse_date(text.replace("-", ".").replace("/", "."))
    if direct:
        return direct.strftime("%d.%m.%Y")
    for match in _DATE_RE.finditer(text):
        parsed = parse_date(match.group(1).replace("-", ".").replace("/", "."))
        if parsed:
            return parsed.strftime("%d.%m.%Y")
    for match in re.finditer(r"(?<!\d)\d{4,8}(?!\d)", text):
        parsed = parse_date(match.group(0))
        if parsed:
            return parsed.strftime("%d.%m.%Y")
    return ""


def _read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in _TEXT_ENCODINGS:
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace").strip()


def _first_labs_line_index(lines: Iterable[str]) -> int | None:
    for idx, line in enumerate(lines):
        low = _norm(line)
        if any(_marker_in_text(marker, low) for marker in _LABS_MARKERS):
            return idx
    return None


def _marker_in_text(marker: str, normalized_text: str) -> bool:
    marker = _norm(marker)
    if not marker:
        return False
    # Short lab abbreviations must be matched as separate tokens.  A plain
    # substring check would treat a surname ending with «...вич» as HIV/ВИЧ.
    if len(marker) <= 4 or marker in {"оак", "оам", "бак", "алт", "аст", "соэ", "rw", "crp", "hcv", "hbsag", "вич"}:
        return bool(re.search(rf"(?<![0-9a-zа-яё]){re.escape(marker)}(?![0-9a-zа-яё])", normalized_text, flags=re.IGNORECASE))
    return marker in normalized_text


def _clean_multiline(value: object) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.strip().split()) for line in text.split("\n")]
    compact: list[str] = []
    previous_blank = False
    for line in lines:
        if not line:
            if not previous_blank and compact:
                compact.append("")
            previous_blank = True
            continue
        compact.append(line)
        previous_blank = False
    return "\n".join(compact).strip()


def _norm(value: object) -> str:
    return " ".join(str(value or "").lower().replace("ё", "е").split())

# --- Legacy/bundled DOCX renderer integration ---

_DEFAULT_GENERATED_LAB_MARKERS = (
    "ОАК", "ОАМ", "RW", "HCV", "HBsAg", "ВИЧ", "Биохимия крови",
    "Глюкоза крови", "Кал на яйца глист", "Флюорография", "ЭКГ",
)
_USER_LAB_BLOCK_MARKERS = (
    "{{labs.results}}", "{{labs.block}}", "{{analysis.results}}", "{{анализы}}",
    "Анализы", "Результаты анализов", "Лабораторные исследования", "Лабораторные данные",
)


class MedicalRendererLabsMixin:
    @staticmethod
    def _replace_lab_lines(
        editor: DocxBlockEditor,
        dates: dict[str, str],
        *,
        data=None,
        all_markers: Sequence[str] = (),
    ) -> None:
        """Fill the analyses block only from explicit doctor-provided data.

        Legacy bundled templates may still contain marker lines like ``ОАК`` /
        ``ОАМ``.  They are placeholders, not facts: without user-entered,
        loaded or selected analyses the renderer removes them instead of
        generating synthetic "normal" results.
        """

        without_labs = bool(getattr(data, "labs_without", False)) if data is not None else False
        user_labs = str(getattr(data, "labs_text", "") or "").strip() if data is not None else ""

        if without_labs:
            editor.remove_all_matching_paragraphs([*_USER_LAB_BLOCK_MARKERS, *_DEFAULT_GENERATED_LAB_MARKERS])
            return

        if user_labs:
            stop_markers = tuple(dict.fromkeys([*all_markers, *_DEFAULT_GENERATED_LAB_MARKERS]))
            inserted = editor.replace_block(_USER_LAB_BLOCK_MARKERS, "Анализы:", user_labs, stop_markers or _DEFAULT_GENERATED_LAB_MARKERS, allow_empty=True)
            if not inserted:
                first_line, *tail = [line.strip() for line in user_labs.splitlines() if line.strip()]
                inserted = editor.replace_first_matching_paragraph(_DEFAULT_GENERATED_LAB_MARKERS, "Анализы: " + first_line)
                if inserted:
                    # The compact legacy path writes the whole block into the first
                    # marker line.  Keep line breaks readable when possible by
                    # folding subsequent lines into semicolon-separated text.
                    if tail:
                        editor.replace_first_matching_paragraph(["Анализы:"], "Анализы: " + "; ".join([first_line, *tail]))
            editor.remove_all_matching_paragraphs([marker for marker in _DEFAULT_GENERATED_LAB_MARKERS if marker != "ОАК"])
            return

        # No doctor-provided analyses means no generated analyses.  Older
        # builds filled legacy placeholders with "в норме" values; that is unsafe
        # for a constructor used with real clinical templates.  Remove only the
        # empty legacy/template marker lines and let required-labs preflight ask
        # the doctor before custom documents are rendered.
        editor.remove_all_matching_paragraphs([*_USER_LAB_BLOCK_MARKERS, *_DEFAULT_GENERATED_LAB_MARKERS])
