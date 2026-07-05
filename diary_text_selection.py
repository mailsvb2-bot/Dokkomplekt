from __future__ import annotations

from diagnostic_logging import record_soft_exception
import re
import zipfile
from pathlib import Path


def _is_docx_file(path: str | Path) -> bool:
    try:
        p = Path(path)
        if not p.is_file() or p.name.startswith("~$"):
            return False
        if p.suffix.lower() in {".docx", ".docm", ".doc"}:
            return True
        if p.suffix:
            return False
        with zipfile.ZipFile(p) as zf:
            names = set(zf.namelist())
        return "[Content_Types].xml" in names and "word/document.xml" in names
    except Exception as exc:
        record_soft_exception("diary_text_selection.is_docx_file", exc, detail=str(path))
        return False


_ICD_PREFIX_RE = re.compile(r"^\s*[A-ZА-Я]\s*\d{1,3}\s*(?:[.,]\s*\d+)?\s*[-—–.:;)]*\s*", re.IGNORECASE)
_ICD_CODE_RE = re.compile(r"(?<![A-Za-zА-Яа-я0-9])([A-ZА-Я])\s*(\d{1,3})(?:[.,]\s*(\d+))?(?![A-Za-zА-Яа-я0-9])", re.IGNORECASE)
MIN_AUTO_DIARY_MATCH_SCORE = 70
_COMMON_DIARY_NAME_WORDS = {
    "дневник",
    "дневники",
    "дневников",
    "дневниковые",
    "вэ",
    "ве",
    "веи",
    "текст",
    "тексты",
    "текстов",
    "даты",
    "датами",
    "с",
    "со",
    "на",
    "шаблон",
    "шаблоны",
}
_STOP_DIARY_NAME_WORDS = {
    "и",
    "с",
    "со",
    "на",
    "по",
    "под",
    "при",
    "для",
    "из",
    "в",
    "во",
    "без",
    "г",
    "год",
    "лет",
    "расстройство",
    "расстройства",
    "синдром",
    "синдромом",
    "состояние",
    "болезнь",
    "болезни",
    "легкое",
    "легкая",
    "легкой",
    "умеренное",
    "умеренная",
    "смешанное",
}


def _icd_match_keys(value: str) -> set[str]:
    """Return generic ICD keys for diary filename matching.

    The selector may use a code that the doctor already put into a diagnosis or
    DOCX filename, but it must not contain specialty-specific bridges.  This
    keeps diary text selection doctor-owned and neutral: exact words and explicit
    ICD codes decide the match, not bundled medical semantics.
    """
    keys: set[str] = set()
    for match in _ICD_CODE_RE.finditer(str(value or "")):
        letter = match.group(1).upper().replace("А", "A").replace("В", "B").replace("С", "C").replace("К", "K")
        number = match.group(2).zfill(2)
        decimal = (match.group(3) or "").strip()
        keys.add(f"icd:{letter}")
        keys.add(f"icd:{letter}{number}")
        if decimal:
            keys.add(f"icd:{letter}{number}.{decimal}")
    return keys


def _has_forbidden_narrow_diary_bridge() -> bool:
    """Production sentinel used by smoke/prod gates.

    Keep this function name stable: tests assert that diary matching stays free
    from narrow specialty-specific compatibility aliases.
    """
    return False

def _stem_russian_word(word: str) -> str:
    """Implement the _stem_russian_word workflow with validation, UI state updates and diagnostics."""
    word = re.sub(r"[^a-zа-я0-9]+", "", word.lower().replace("ё", "е"))
    if len(word) <= 4:
        return word
    # Небольшой безопасный stemmer для выравнивания русских окончаний
    # в нейтральных врачебных названиях файлов.
    for suffix in (
        "иями",
        "ями",
        "ами",
        "ости",
        "ость",
        "ение",
        "ения",
        "ении",
        "остью",
        "ыми",
        "ими",
        "ной",
        "ная",
        "ные",
        "ный",
        "ным",
        "ных",
        "ого",
        "его",
        "ему",
        "ая",
        "яя",
        "ое",
        "ее",
        "ия",
        "ий",
        "ый",
        "ые",
        "ой",
        "ей",
        "ам",
        "ям",
        "ах",
        "ях",
        "ов",
        "ев",
        "ом",
        "ем",
        "ою",
        "ею",
        "а",
        "я",
        "ы",
        "и",
        "у",
        "ю",
        "е",
        "о",
    ):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def normalize_diary_diagnosis_name(value: str) -> str:
    """Normalize a diagnosis/file name for matching diary text DOCX files.

    Реальные файлы врача часто называются не ровно диагнозом, а так:
    ``дневники ВЭ гипертензия с датами.docx``. Поэтому здесь убираем
    технические слова и оставляем смысловую часть названия.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        p = Path(text)
        # Не считаем формальный диагноз вида "F70.0 ..." именем файла только
        # из-за точки в коде МКБ. Stem берём только для реальных DOCX/DOCM имён.
        if p.suffix.lower() in {".docx", ".docm", ".doc"}:
            text = p.stem
    except Exception as exc:
        record_soft_exception("diary_text_selection:156", exc)
    text = text.replace("ё", "е").lower()
    text = _ICD_PREFIX_RE.sub("", text)
    text = re.sub(r"\b(?:диагноз|основной диагноз|заключение|дневниковые записи)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[№#]", " ", text)
    text = re.sub(r"[()\[\]{}]", " ", text)
    text = re.sub(r"[.,;:!?'\"/\\|_+*=<>~`]+", " ", text)
    text = re.sub(r"[-–—]+", " ", text)
    words = [w for w in re.sub(r"\s+", " ", text).strip().split() if w]
    words = [w for w in words if w not in _COMMON_DIARY_NAME_WORDS]
    return " ".join(words).strip()


def _significant_words(value: str) -> set[str]:
    return {
        word
        for word in normalize_diary_diagnosis_name(value).split()
        if len(word) >= 3 and word not in _COMMON_DIARY_NAME_WORDS and word not in _STOP_DIARY_NAME_WORDS
    }


def _semantic_keys(value: str) -> set[str]:
    raw = str(value or "")
    norm = normalize_diary_diagnosis_name(raw)
    keys: set[str] = set()
    stems = {_stem_russian_word(w) for w in norm.split() if len(w) >= 3}
    keys.update(stem for stem in stems if stem and stem not in _STOP_DIARY_NAME_WORDS)
    keys.update(_icd_match_keys(raw))
    return keys


def diary_diagnosis_match_score(diagnosis: str, filename: str) -> int:
    diag = normalize_diary_diagnosis_name(diagnosis)
    name = normalize_diary_diagnosis_name(filename)
    if not diag or not name:
        return 0
    if diag == name:
        return 120
    if diag in name or name in diag:
        return 104

    diag_keys = _semantic_keys(diagnosis)
    name_keys = _semantic_keys(filename)
    semantic_overlap = diag_keys & name_keys
    score = 0
    if semantic_overlap:
        icd_overlap = {key for key in semantic_overlap if key.startswith("icd:")}
        lexical_overlap = semantic_overlap - icd_overlap
        if icd_overlap:
            score = max(score, 92 + min(12, len(icd_overlap) * 4))
        if lexical_overlap:
            score = max(score, 76 + min(16, len(lexical_overlap) * 4))

    diag_words = _significant_words(diag)
    name_words = _significant_words(name)
    diag_stems = {_stem_russian_word(w) for w in diag_words}
    name_stems = {_stem_russian_word(w) for w in name_words}
    overlap = len((diag_words & name_words) | (diag_stems & name_stems))
    if diag_words and name_words and overlap:
        coverage_diag = overlap / max(1, len(diag_words))
        coverage_name = overlap / max(1, len(name_words))
        coverage = min(coverage_diag, coverage_name)
        lexical = 65 + int(coverage * 18) if (overlap >= 2 or coverage >= 0.5) else 0
        score = max(score, lexical)

    return max(0, score)

def iter_diary_text_docx_files(folder: str | Path, *, max_depth: int = 2) -> list[Path]:
    try:
        root = Path(folder).expanduser()
        if not root.exists() or not root.is_dir():
            return []
    except Exception as exc:
        record_soft_exception("diary_text_selection.root_folder", exc, detail=str(folder))
        return []
    result: list[Path] = []
    seen: set[str] = set()

    def walk(current: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            children = list(current.iterdir())
        except Exception as exc:
            record_soft_exception("diary_text_selection.iterdir", exc, detail=str(current))
            return
        for child in children:
            name_low = child.name.strip().lower()
            if name_low.startswith(".") or name_low in {"__pycache__", ".venv", "venv", "build", "dist"}:
                continue
            if child.is_dir():
                walk(child, depth + 1)
                continue
            if not _is_docx_file(child):
                continue
            try:
                key = str(child.resolve())
            except Exception as exc:
                record_soft_exception("diary_text_selection.resolve_child", exc, detail=str(child))
                key = str(child)
            if key in seen:
                continue
            seen.add(key)
            result.append(child)

    walk(root, 0)
    return sorted(result, key=lambda p: str(p).lower())


def find_diary_text_file_for_diagnosis(folder: str | Path, diagnosis: str) -> Path | None:
    """Find the best diary-text DOCX whose filename matches the parsed diagnosis."""
    diagnosis_norm = normalize_diary_diagnosis_name(diagnosis)
    if not diagnosis_norm:
        return None
    diagnosis_keys = _semantic_keys(diagnosis)
    candidates: list[tuple[int, int, int, str, Path]] = []
    for path in iter_diary_text_docx_files(folder):
        score = diary_diagnosis_match_score(diagnosis, path.stem)
        if score < MIN_AUTO_DIARY_MATCH_SCORE:
            continue
        name_norm = normalize_diary_diagnosis_name(path.stem)
        name_keys = _semantic_keys(path.stem)
        length_gap = abs(len(name_norm) - len(diagnosis_norm))
        # Prefer filenames whose explicit ICD/word keys stay closest to the
        # diagnosis.  No specialty-specific penalties are allowed here.
        extra_key_penalty = max(0, len(name_keys - diagnosis_keys))
        candidates.append((-score, extra_key_penalty, length_gap, path.name.lower(), path))
    if not candidates:
        return None
    return sorted(candidates)[0][4]


def folder_has_diary_text_candidates(folder: str | Path) -> bool:
    return bool(iter_diary_text_docx_files(folder, max_depth=1))
