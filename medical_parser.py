"""Facade парсера медицинского текста.

Реализация разложена по parse/inline/demographics/work/block mixin-модулям,
а публичный класс MedicalTextParser сохранён для старых импортов.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, Sequence

from medical_parser_blocks import MedicalParserBlocksMixin
from medical_parser_core import MedicalParserCoreMixin
from medical_parser_demographics import MedicalParserDemographicsMixin
from medical_parser_inline import MedicalParserInlineMixin
from medical_parser_sanitize import sanitize_diagnosis
from medical_parser_work import MedicalParserWorkMixin
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


def _filename_fio_hint(path: str | Path) -> tuple[str, tuple[str, ...]]:
    """Return a generic surname/initials hint from the selected filename.

    The filename is only a disambiguation/fallback source for *output naming*.
    Full patient FIO still comes from the document whenever it is present.
    """
    stem = normalize_word_parser_text(Path(path).stem.replace("_", " "))
    match = re.search(
        rf"(?<![А-ЯЁа-яё-])(?P<surname>{_NAME_TOKEN})\s+"
        r"(?P<i1>[А-ЯЁ])\.\s*(?P<i2>[А-ЯЁ])\.(?![А-ЯЁа-яё])",
        stem,
    )
    if match:
        return clean_value(match.group("surname")), (match.group("i1").upper(), match.group("i2").upper())
    full = _FULL_FIO_RE.search(stem)
    if full:
        fio = clean_value(full.group(1))
        parts = fio.split()
        return parts[0], tuple(part[0].upper() for part in parts[1:3] if part)
    return "", ()


def _fio_matches_filename_hint(fio: str, surname: str, initials: Sequence[str]) -> bool:
    parts = [part.strip(" .,:;-") for part in normalize_word_parser_text(fio).split() if part.strip(" .,:;-")]
    if not parts or not surname or normalize_match(parts[0]) != normalize_match(surname):
        return False
    if not initials:
        return True
    candidate_initials = tuple(part[0].upper() for part in parts[1:3] if part)
    return candidate_initials[: len(initials)] == tuple(initials)


def recover_patient_fio_from_flattened_docx(path: str | Path) -> str:
    """Recover patient identity from flattened Word/XML when table geometry is hidden.

    Real hospital forms may wrap table-like content in content controls, text boxes,
    or drawing containers. ``python-docx`` then cannot expose the table geometry,
    while the raw Word XML still contains the visible paragraphs.  Score full-name
    candidates against demographic anchors and the generic filename initials hint;
    reject clinician/signature neighbourhoods.  No surname is hard-coded.
    """
    try:
        from medical_docx_reader import extract_docx_text

        text = normalize_word_parser_text(extract_docx_text(path))
    except Exception as exc:
        record_soft_exception("medical_docx_fio_recovery.flattened_text", exc, detail=str(path))
        return ""
    if not text:
        return ""

    lines = [normalize_word_parser_text(line) for line in text.splitlines() if normalize_word_parser_text(line)]
    if not lines:
        return ""
    surname_hint, initials_hint = _filename_fio_hint(path)
    demographic_markers = (
        "дата рождения", "год рождения", "возраст", "г.р",
        "адрес", "зарегистрирован", "место жительства", "проживает",
    )
    patient_markers = ("ф.и.о", "фио", "пациент", "пациентка", "больной", "больная")
    clinician_caption_re = re.compile(
        r"^\s*(?:(?:ф\.?\s*и\.?\s*о\.?|фио)\s+)?(?:лечащ\w*\s+)?"
        r"(?:врач\w*|доктор\w*|фельдшер\w*|заведующ\w*|хирург\w*|"
        r"терапевт\w*|психиатр\w*|ординатор\w*)\b|"
        r"^\s*(?:подпись|направил)\s+врач\w*\b",
        flags=re.IGNORECASE,
    )
    heading_markers = ("направление на госпитализац", "первичный осмотр", "история болезни")

    candidates: dict[str, tuple[int, int]] = {}
    scan_limit = min(len(lines), 120)
    for start in range(scan_limit):
        for width in (1, 2, 3):
            end = min(scan_limit, start + width)
            if end <= start:
                continue
            candidate = _full_fio(lines[start:end])
            if not candidate:
                continue
            key = normalize_match(candidate)
            if not key or key in candidates:
                continue
            context_lo = max(0, start - 5)
            context_hi = min(scan_limit, end + 6)
            before_lo = max(0, start - 3)
            context = " | ".join(lines[context_lo:context_hi])
            context_norm = normalize_match(context)
            score = 0
            if surname_hint and _fio_matches_filename_hint(candidate, surname_hint, initials_hint):
                score += 10
            if any(marker in context_norm for marker in demographic_markers):
                score += 5
            if any(marker in context_norm for marker in patient_markers):
                score += 4
            if any(marker in context_norm for marker in heading_markers):
                score += 1
            span_lines = lines[start:end]
            if any(clinician_caption_re.search(normalize_match(value)) for value in span_lines):
                continue
            if any(clinician_caption_re.search(normalize_match(value)) for value in lines[before_lo:start]):
                continue
            if any(clinician_caption_re.search(normalize_match(value)) for value in lines[context_lo:context_hi]):
                score -= 4
            candidates[key] = (score, start)

    if not candidates:
        return ""
    ranked = sorted(
        ((score, -start, key) for key, (score, start) in candidates.items()),
        reverse=True,
    )
    best_score, _neg_start, best_key = ranked[0]
    if best_score < 5:
        return ""
    for start in range(scan_limit):
        for width in (1, 2, 3):
            candidate = _full_fio(lines[start:min(scan_limit, start + width)])
            if candidate and normalize_match(candidate) == best_key:
                return candidate
    return ""


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


class MedicalTextParser(
    MedicalParserCoreMixin,
    MedicalParserInlineMixin,
    MedicalParserDemographicsMixin,
    MedicalParserWorkMixin,
    MedicalParserBlocksMixin,
):
    def parse_text(self, text: str):
        return super().parse_text(normalize_word_parser_text(text))

    def parse_docx(self, path):
        data = super().parse_docx(path)
        reconciled = reconcile_patient_fio_from_docx(
            path,
            parsed_fio=data.fio,
            all_aliases=self._all_inline_aliases(),
        )
        if not reconciled:
            reconciled = recover_patient_fio_from_flattened_docx(path)
        normalized = self._sanitize_fio_value(reconciled) if reconciled else ""
        if normalized != data.fio:
            data.fio = normalized
            self._refresh_warnings(data)
        if not data.output_fio:
            data.output_fio = data.fio
        if not data.output_fio:
            surname_hint, initials_hint = _filename_fio_hint(path)
            if surname_hint and initials_hint:
                data.output_fio = f"{surname_hint} {''.join(item + '.' for item in initials_hint)}"
        return data

    FIELD_ALIASES: Dict[str, Sequence[str]] = {
        "case_number": ("История болезни №", "История болезни N", "ИБ №", "Nr historii choroby", "Numer historii choroby", "Historia choroby nr", "Nr dokumentacji", "Numer dokumentacji", "Nr karty"),
        "fio": ("Ф.И.О.", "Ф.И.О", "ФИО", "ФИО пациента", "Ф.И.О. пациента", "Ф.И.О пациента", "Фамилия Имя Отчество", "Пациент", "Пациентка", "Больной", "Больная", "Pacjent", "Pacjentka", "Imię i nazwisko", "Imie i nazwisko", "Nazwisko i imię", "Nazwisko i imie"),
        "birth": ("Год рождения", "Дата рождения", "г.р.", "Data urodzenia", "Urodzony", "Urodzona"),
        "registered": ("Зарегистрирован", "зарегистрирован по адресу", "Проживает", "Место жительства", "Адрес проживания", "Адрес места жительства", "Адрес регистрации", "Adres", "Adres zamieszkania", "Miejsce zamieszkania"),
        "psych_account": ("На учёте у психиатров", "На учете у психиатров"),
        "work_org": ("Работает в организации", "Работает", "Место работы", "Работа", "Miejsce pracy", "Pracuje", "Zakład pracy", "Zaklad pracy"),
        "position": ("Должность", "Stanowisko", "Zawód", "Zawod"),
        "sick_leave": ("Больничный лист", "ЛН", "Лист нетрудоспособности"),
        "disability": ("Оформление инвалидности", "Инвалидность"),
        "rvk_referral": ("Направление от РВК", "РВК"),
        "admission": ("Поступает", "Поступил", "Поступила", "Госпитализирован", "Госпитализирована", "Przyjęty", "Przyjety", "Przyjęta", "Przyjeta", "Hospitalizowany", "Hospitalizowana"),
        "doctor": ("Лечащий врач", "Врач", "Врач психиатр", "Врач-психиатр", "Хирург", "Терапевт", "Lekarz", "Lekarz prowadzący", "Lekarz prowadzacy", "Chirurg", "Terapeuta"),
        "head": ("Заведующий отделением", "Зав. отделением", "Зав. отд.", "Зав отд", "Зав.отделением", "Ordynator", "Kierownik oddziału", "Kierownik oddzialu"),
    }

    BLOCK_ALIASES: Dict[str, Sequence[str]] = {
        "complaints": ("Жалобы на момент осмотра", "Жалобы при поступлении", "Жалобы", "Skargi", "Dolegliwości", "Dolegliwosci", "Skargi przy przyjęciu", "Skargi przy przyjeciu"),
        "life_anamnesis": ("Анамнез жизни", "Wywiad życiowy", "Wywiad zyciowy", "Wywiad osobniczy"),
        "disease_anamnesis": ("Анамнез заболевания", "Wywiad chorobowy", "Wywiad obecnej choroby", "Historia choroby"),
        "mental_status": ("Профильный статус при поступлении", "Профильный статус", "Психический статус при поступлении", "Психический статус", "Stan psychiczny", "Badanie psychiatryczne"),
        "somatic_status": ("Сомато-неврологический статус", "Соматический статус", "Объективный статус", "Объективно", "Status praesens", "Stan przedmiotowy", "Badanie przedmiotowe", "Stan somatyczny"),
        "examination_plan": ("План обследования", "Plan badań", "Plan badan"),
        "treatment_plan": ("План лечения", "Назначенное лечение", "Лечение", "Plan leczenia", "Zalecone leczenie", "Zastosowane leczenie", "Leczenie", "Terapia"),
        "diagnosis": ("Клинический диагноз", "Предварительный диагноз", "Основной диагноз", "Заключительный диагноз", "Диагноз", "был выставлен диагноз", "установлен диагноз", "выставлен диагноз", "Rozpoznanie kliniczne", "Rozpoznanie główne", "Rozpoznanie glowne", "Rozpoznanie", "Diagnoza"),
        "epidemiology": ("Эпидемиологический анамнез", "Wywiad epidemiologiczny"),
    }

    SECTION_MARKERS: Sequence[str] = (
        "Дата, время", "Дата поступления", "Дата госпитализации", "Дата приема", "Дата приёма", "Дата осмотра", "Дата выписки",
        "История болезни №", "Ф.И.О.", "Ф.И.О", "ФИО", "ФИО пациента", "Ф.И.О. пациента", "Год рождения", "Дата рождения", "Возраст",
        "Зарегистрирован", "Проживает", "Место жительства", "Адрес проживания", "Адрес места жительства", "На учёте у психиатров", "На учете у психиатров",
        "Работает в организации", "Место работы", "Должность", "Больничный лист", "Оформление инвалидности", "Направление от РВК", "Поступает", "Поступил", "Поступила", "Госпитализирован", "Госпитализирована", "В 3 отделение КДП поступает",
        "Жалобы на момент осмотра", "Жалобы при поступлении", "Жалобы", "Анамнез жизни", "Анамнез заболевания", "Профильный статус при поступлении", "Профильный статус", "Психический статус при поступлении", "Психический статус", "Сомато-неврологический статус", "Соматический статус",
        "План обследования", "План лечения", "Назначенное лечение", "На основании данных", "Клинический диагноз", "Предварительный диагноз", "Основной диагноз", "Заключительный диагноз", "Диагноз", "Эпидемиологический анамнез", "Результаты обследований", "Результаты исследований", "ЭЭГ", "ЭПИ", "За время лечения", "Рекомендовано", "Лечение", "Экспертный анамнез",
        "Лечащий врач", "Врач", "Врач психиатр", "Врач-психиатр", "Заведующий отделением", "Зав. отделением", "Зав. отд.", "Зав отд",
        "Karta informacyjna leczenia szpitalnego", "Historia choroby", "Dokumentacja medyczna", "Pacjent", "Pacjentka", "Imię i nazwisko", "Imie i nazwisko", "Data urodzenia", "Nr historii choroby", "Numer historii choroby", "Data przyjęcia", "Data przyjecia", "Data hospitalizacji", "Data wypisu", "Skargi", "Dolegliwości", "Dolegliwosci", "Wywiad chorobowy", "Wywiad życiowy", "Wywiad zyciowy", "Stan psychiczny", "Stan somatyczny", "Stan przedmiotowy", "Plan badań", "Plan badan", "Plan leczenia", "Zalecone leczenie", "Zastosowane leczenie", "Leczenie", "Rozpoznanie kliniczne", "Rozpoznanie główne", "Rozpoznanie glowne", "Rozpoznanie", "Wyniki badań", "Wyniki badan", "Zalecenia", "Lekarz", "Lekarz prowadzący", "Lekarz prowadzacy", "Ordynator", "Kierownik oddziału", "Kierownik oddzialu",
    )

    LIFE_ANAMNESIS_START_RE = re.compile(
        r"(?i)(?<![А-Яа-яA-Za-z0-9])(" 
        r"наследственность|рождение\s+в\s+городе|родил(?:ся|ась)?\s+в|"
        r"на\s+момент\s+рождения\s+семья|в\s+настоящее\s+время\s+семья|"
        r"братья\s*/\s*с[её]стры|братьев|с[её]ст[её]р|"
        r"беременность\s*/\s*роды|беременность\s+и\s+роды|"
        r"дду|общение\s+в\s+дду|общеобразовательн\w*\s+школ\w*|"
        r"коррекционн\w*\s+школ\w*|во\s+время\s+уч[её]бы|"
        r"после\s+школы|специальность|окончание\s+уч[её]бы|"
        r"в\s+настоящее\s+время\s+работа|брак|дети|проживает\s*[-:])"
    )
