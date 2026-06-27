"""Language-aware offline ICD-10 search.

The public function names keep the historical ``*_f`` suffix so older code does
not break.  Internally the search now uses the full ICD-10 catalog, not only
F00-F99.
"""

from __future__ import annotations

import re

from diagnostic_logging import record_soft_exception
from medical_parser_sanitize import sanitize_diagnosis

from medical_language_catalog import normalize_language_id
from icd10_models import ICD10Diagnosis
from icd10_f_data import ICD10_DIAGNOSES, ICD10_F_DIAGNOSES, _code_sort_key


def format_diagnosis(item: ICD10Diagnosis, *, language_id: str | None = "ru") -> str:
    return item.display_for_language(language_id)


_CYRILLIC_CODE_LETTER_MAP = str.maketrans({
    "А": "A", "В": "B", "С": "C", "Е": "E", "Н": "H", "К": "K",
    "М": "M", "О": "O", "Р": "P", "Т": "T", "Х": "X", "У": "Y",
    "Ф": "F", "З": "Z", "І": "I", "Ї": "I", "Ј": "J",
})
_CODE_LIKE_RE = re.compile(r"^[A-ZА-ЯЁІЇЈ][0-9]{2}(?:[.,][0-9A-ZА-ЯЁІЇЈ]+)?$", re.IGNORECASE)


def _normalize_code_letters(value: str) -> str:
    """Normalize only ICD-code-looking tokens, not diagnosis prose.

    Primary documents are often typed with a Russian keyboard layout: ``К35``
    instead of ``K35``. Search should still
    find the official Latin ICD-10 code, but words like ``Острый`` must not be
    transliterated accidentally.
    """
    token = (value or "").strip().upper().replace(",", ".").replace("Ё", "Е")
    compact = re.sub(r"\s+", "", token)
    if not _CODE_LIKE_RE.fullmatch(compact):
        return token
    return compact.translate(_CYRILLIC_CODE_LETTER_MAP)


def normalize_query(value: str) -> str:
    value = (value or "").strip().upper().replace(",", ".")
    value = value.replace("Ё", "Е")
    value = re.sub(r"\s+", " ", value)
    return value


def _digits_only(value: str) -> str:
    return re.sub(r"\D+", "", value)


def _letter_normalized_code(value: str) -> str:
    compact = re.sub(r"\s+", "", (value or "").upper().replace(",", ".").replace("Ё", "Е"))
    return _normalize_code_letters(compact)


def _searchable_text(item: ICD10Diagnosis) -> str:
    titles = " ".join(str(title) for title in item.titles.values()) if item.titles else item.title
    return f"{item.code} {item.title} {titles}".upper().replace("Ё", "Е")


def _rank_match(item: ICD10Diagnosis, q: str, q_no_space: str, q_digits: str) -> int | None:
    code = item.code.upper()
    code_digits = _digits_only(code)
    text = _searchable_text(item)

    query_letters = re.findall(r"[A-Z]", q_no_space)
    same_code_family = not query_letters or code.startswith(query_letters[0])

    if q_no_space == code:
        return 0
    if q_no_space and code.startswith(q_no_space):
        return 1
    if same_code_family and q_digits and code_digits == q_digits:
        return 2
    if same_code_family and q_digits and code_digits.startswith(q_digits):
        return 3
    if same_code_family and q_digits and q_digits in code_digits:
        return 4
    if q and q in text:
        return 5

    parts = [part for part in re.split(r"\s+", q) if part]
    if parts and all(part in text for part in parts):
        return 6
    return None


def search_icd10_f(query: str, *, limit: int = 80, language_id: str | None = "ru") -> list[ICD10Diagnosis]:
    """Search ICD-10 by code, code digits or localized title fragment.

    Backward-compatible name, full-catalog behavior:
    - any valid ICD-10 chapter code still works;
    - ``K35`` or ``аппендицит`` finds surgical ICD-10 rows;
    - ``neoplasms`` / translated chapter titles work in supported UI languages.
    """
    _ = normalize_language_id(language_id, default="ru")  # validates caller value and documents the contract
    q = normalize_query(query)
    if not q:
        return ICD10_DIAGNOSES[:limit]

    q_digits = _digits_only(q)
    q_no_space = _letter_normalized_code(q)
    ranked: list[tuple[int, tuple[int, ...], str, ICD10Diagnosis]] = []

    for item in ICD10_DIAGNOSES:
        score = _rank_match(item, q, q_no_space, q_digits)
        if score is not None:
            ranked.append((score, _code_sort_key(item.code), item.title, item))

    ranked.sort(key=lambda row: (row[0], row[1], row[2]))
    return [item for *_prefix, item in ranked[:limit]]


def all_diagnosis_display_values(*, language_id: str | None = "ru") -> list[str]:
    return [format_diagnosis(item, language_id=language_id) for item in ICD10_DIAGNOSES]


# --- Safe ICD-10 normalization for parsed diagnoses ---
ICD10_NORMALIZATION_LOCK_VERSION = "v1.4.42-p1"


_SYNONYM_CODE_ALIASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("артериальная гипертензия", "гипертоническая болезнь", "гипертония"), "I10"),
    (("сахарный диабет 2", "сахарный диабет второго", "диабет 2 типа", "диабет ii типа"), "E11"),
    (("сахарный диабет 1", "сахарный диабет первого", "диабет 1 типа", "диабет i типа"), "E10"),
    (("острый аппендицит", "аппендицит"), "K35"),
    (("пневмония", "внебольничная пневмония"), "J18"),
    (("инфаркт миокарда", "острый инфаркт"), "I21"),
    (("инсульт", "ишемический инсульт", "инфаркт мозга"), "I63"),
    (("перелом предплечья", "перелом лучевой кости", "перелом локтевой кости"), "S52"),
)


def _alias_code_for_text(value: str) -> str:
    low = " ".join(str(value or "").lower().replace("ё", "е").split())
    for aliases, code in _SYNONYM_CODE_ALIASES:
        if any(alias in low for alias in aliases):
            return code
    return ""

_CODE_RE = re.compile(r"(?<![A-Za-zА-Яа-я0-9])([A-ZА-ЯЁІЇЈ][0-9]{2}(?:[.,][0-9A-ZА-ЯЁІЇЈ]+)?)(?![A-Za-zА-Яа-я0-9])", re.IGNORECASE)


def _canonical_code(value: str) -> str:
    return _normalize_code_letters(str(value or "").strip().upper().replace(",", "."))


def _strip_existing_code(value: str, code: str) -> str:
    if not code:
        return value.strip()
    # Strip both official Latin codes and accidental Cyrillic-keyboard variants
    # from the beginning of the diagnosis string.
    direct = re.compile(rf"^\s*{re.escape(code)}\s*[—\-:.,;]*\s*", re.IGNORECASE)
    stripped = direct.sub("", value or "").strip()
    if stripped != (value or "").strip():
        return stripped
    return re.sub(
        r"^\s*[A-ZА-ЯЁІЇЈ][0-9]{2}(?:[.,][0-9A-ZА-ЯЁІЇЈ]+)?\s*[—\-:.,;]*\s*",
        "",
        value or "",
        flags=re.IGNORECASE,
    ).strip()


def _norm_words(value: str) -> set[str]:
    text = (value or "").lower().replace("ё", "е")
    words = re.findall(r"[а-яa-z0-9]{3,}", text)
    stop = {
        "диагноз", "клинический", "предварительный", "основной", "заключительный",
        "болезнь", "болезни", "состояние", "синдром", "неуточненный", "неуточненная",
        "без", "при", "для", "данных", "пациента", "пациентки",
    }
    return {word for word in words if word not in stop}


def _strong_text_match(source: str, title: str) -> bool:
    source_words = _norm_words(source)
    title_words = _norm_words(title)
    if not source_words or not title_words:
        return False
    joined_source = " ".join(sorted(source_words))
    joined_title = " ".join(sorted(title_words))
    if joined_source == joined_title:
        return True
    if source_words <= title_words and len(source_words) >= 1:
        return True
    overlap = source_words & title_words
    return len(overlap) >= 2 and len(overlap) >= min(len(source_words), len(title_words)) * 0.67


def normalize_diagnosis_with_icd10(value: str, *, language_id: str | None = "ru") -> str:
    """Return ``CODE title`` when ICD-10 can be inferred safely.

    The function supports two safe paths:
    - the source already contains a code (``K35``/``I10``/``J18``): format it
      through the full catalog and keep extra doctor's wording if present;
    - the source is a close textual match to one catalog row.
    """
    diagnosis = sanitize_diagnosis(value)
    if not diagnosis:
        return ""
    try:
        code_match = _CODE_RE.search(diagnosis)
        if code_match:
            code = _canonical_code(code_match.group(1))
            matches = search_icd10_f(code, limit=6, language_id=language_id)
            exact = next((item for item in matches if _canonical_code(item.code) == code), None)
            if exact is not None:
                display = format_diagnosis(exact, language_id=language_id)
                extra = _strip_existing_code(diagnosis, code)
                # If the doctor/source already wrote a diagnosis after the ICD
                # code, keep that wording.  Replacing it with the local catalog
                # title can duplicate or subtly change the clinical phrase.
                if extra:
                    return f"{code} {extra}".strip()
                return display
            extra = _strip_existing_code(diagnosis, code)
            return f"{code} {extra}".strip() if extra else code

        alias_code = _alias_code_for_text(diagnosis)
        if alias_code:
            alias_matches = search_icd10_f(alias_code, limit=6, language_id=language_id)
            alias_exact = next((item for item in alias_matches if _canonical_code(item.code) == alias_code), None)
            if alias_exact is not None:
                return format_diagnosis(alias_exact, language_id=language_id)

        matches = search_icd10_f(diagnosis, limit=5, language_id=language_id)
        if not matches:
            return diagnosis
        best = matches[0]
        title = best.title_for_language(language_id)
        if _strong_text_match(diagnosis, title):
            return format_diagnosis(best, language_id=language_id)
    except Exception as exc:
        record_soft_exception("icd10_matcher.normalize", exc, detail=str(value)[:200])
    return diagnosis



def diagnosis_has_icd10_code(value: str) -> bool:
    """Return True only when a diagnosis contains a real ICD-10-like code.

    ``normalize_diagnosis_with_icd10`` intentionally returns unknown free text
    unchanged so parsed source documents are not falsified.  Popup validation
    needs a stricter predicate: an unknown phrase must keep the window open
    until the doctor selects a catalog diagnosis or enters a code such as
    ``K35``/``I10``/``J18.9``.
    """
    text = sanitize_diagnosis(value)
    if not text:
        return False
    match = _CODE_RE.search(text)
    if not match:
        return False
    code = _canonical_code(match.group(1))
    return bool(re.fullmatch(r"[A-Z][0-9]{2}(?:\.[0-9A-Z]+)?", code))


def normalize_required_diagnosis_with_icd10(value: str, *, language_id: str | None = "ru") -> str:
    """Normalize a doctor-entered required diagnosis and reject unresolved text.

    Used by modal popup validation.  This deliberately differs from
    ``normalize_diagnosis_with_icd10``: parser normalization is lossless, while
    required user input must be actionable and contain/resolve to an ICD-10
    code before the popup may close.
    """
    normalized = normalize_diagnosis_with_icd10(value, language_id=language_id)
    return normalized if diagnosis_has_icd10_code(normalized) else ""

def assert_icd10_diagnosis_normalizer_lock() -> None:
    if ICD10_NORMALIZATION_LOCK_VERSION != "v1.4.42-p1":
        raise AssertionError("ICD-10 diagnosis normalization lock changed")
    checks = (
        (normalize_diagnosis_with_icd10("Острый аппендицит").startswith("K35"), "appendicitis must map to K35"),
        (normalize_diagnosis_with_icd10("I10").startswith("I10"), "explicit I10 code must stay I10"),
        (normalize_diagnosis_with_icd10("К35").startswith("K35"), "Cyrillic keyboard ICD-10 K35 must normalize to Latin K35"),
        (normalize_diagnosis_with_icd10("К35.8") == "K35.8", "unknown Cyrillic-layout ICD-10 subcode must still become canonical Latin code"),
        (normalize_diagnosis_with_icd10("Артериальная гипертензия").startswith("I10"), "hypertension alias must map to I10"),
        (normalize_diagnosis_with_icd10("какая-то техническая инструкция") == "какая-то техническая инструкция", "unknown free text must not be invented"),
        (normalize_required_diagnosis_with_icd10("какая-то техническая инструкция") == "", "required popup diagnosis must reject unresolved free text"),
        (normalize_required_diagnosis_with_icd10("Острый аппендицит").startswith("K35"), "required popup diagnosis must accept safe text-to-code matches"),
    )
    for ok, message in checks:
        if not ok:
            raise AssertionError(message)
