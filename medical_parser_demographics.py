from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from medical_docx_reader import (
    extract_admission_date_from_title_docx,
    extract_docx_text,
    _first_valid_full_date,
    _is_birth_or_demographic_context,
    _is_primary_title_context,
)
from medical_models import PatientData
from medical_parser_sanitize import sanitize_diagnosis
from medical_field_line_pairs import line_starts_with_label
from medical_text_utils import (
    DIAGNOSIS_STOP_MARKERS,
    clean_value,
    looks_like_label,
    normalize_match,
    normalize_text,
)


class MedicalParserDemographicsMixin:
    def _repair_compact_demographics(self, data: PatientData, text: str) -> None:
        """Восстановить ФИО/возраст/адрес из одной строки.

        Поддерживаемые варианты:
        - "Ф.И.О.: Иванова Ирина Ивановна, Возраст: 45 лет, Место жительства: город N"
        - "Ф.И.О.: Иванова Ирина Ивановна, 45 лет, город N, ул. ..."
        - "Иванова Ирина Ивановна, 45 лет, проживает: город N ..."

        Значения из явно найденных отдельных строк не перетираются, кроме случая,
        когда в ФИО явно попал хвост с возрастом/адресом.
        """
        candidates: List[str] = []
        if data.fio:
            candidates.append(data.fio)
        candidates.extend(text.splitlines())

        for candidate in candidates:
            parsed = self._parse_compact_demographics_line(candidate)
            if not parsed:
                continue
            fio, birth_or_age, address, work_org = parsed

            if fio and (not data.fio or self._fio_value_looks_overgrown(data.fio)):
                data.fio = fio
            if birth_or_age and not data.birth:
                data.birth = birth_or_age
            if address and (
                not data.registered
                or not self._looks_like_address_tail(data.registered)
            ):
                data.registered = address
            if work_org and not data.work_org:
                data.work_org = work_org

            if data.fio and data.birth and data.registered and not self._fio_value_looks_overgrown(data.fio):
                break

        # Real Word forms often split a single FIO across several table cells or
        # paragraphs. The generic inline reader intentionally consumes only one
        # neighbouring value, so it can leave just the surname here. Upgrade that
        # incomplete value from the same local demographic block before the core
        # sanitizer rejects it as an invalid patient identity.
        if not self._fio_is_usable(data.fio):
            recovered_fio = self._recover_structured_fio(text)
            if recovered_fio:
                data.fio = recovered_fio

    _FIO_STRUCTURED_LABEL_RE = re.compile(
        r"^\s*(?:ф\.?\s*и\.?\s*о\.?|фио|фамилия\s*,?\s*имя\s*,?\s*отчество|пациент(?:ка)?|больн(?:ой|ая))"
        r"(?:\s+(?:пациент(?:а|ки)|больн(?:ого|ой)))?"
        r"(?:\s*\([^\n)]{0,60}\))?\s*[:№N#.-]*\s*",
        flags=re.IGNORECASE,
    )
    _FIO_NAME_TOKEN = r"(?:[А-ЯЁ][а-яё]+|[А-ЯЁ]{2,})(?:-(?:[А-ЯЁ][а-яё]+|[А-ЯЁ]{2,}))?"
    _FIO_FULL_RE = re.compile(
        rf"(?<![А-ЯЁа-яё-])({_FIO_NAME_TOKEN}\s+{_FIO_NAME_TOKEN}\s+{_FIO_NAME_TOKEN})(?![А-ЯЁа-яё-])"
    )
    _FIO_FULL_LINE_RE = re.compile(
        rf"^\s*({_FIO_NAME_TOKEN}\s+{_FIO_NAME_TOKEN}\s+{_FIO_NAME_TOKEN})\s*[.,;:]?\s*$"
    )

    @staticmethod
    def _fio_is_usable(value: str) -> bool:
        cleaned = clean_value(value)
        if not cleaned:
            return False
        words = re.findall(r"[А-ЯЁA-Z][а-яёa-z]+|[А-ЯЁA-Z]\.", cleaned)
        if len(words) >= 2:
            return True
        return len(re.findall(r"[А-ЯЁA-Z]{2,}", cleaned)) >= 2

    def _recover_structured_fio(self, text: str) -> str:
        """Recover a full patient name split by real Word table/form layout.

        `extract_docx_text()` deliberately flattens table cells and paragraphs to
        separate lines.  In production referrals this can turn one visible row
        into ``Ф.И.О. больного`` / ``Баннина`` / ``Елена Геннадьевна``.  The
        generic inline reader returns only the first value line, so the surname
        later fails FIO validation.  Reassemble only a tiny, label-bound window;
        never guess a patient from an arbitrary doctor/signature name.
        """
        lines = [normalize_text(line or "") for line in str(text or "").splitlines()]
        all_aliases = self._all_inline_aliases()

        for index, line in enumerate(lines):
            match = self._FIO_STRUCTURED_LABEL_RE.match(line)
            if not match:
                continue
            chunks: List[str] = []
            inline_tail = clean_value(line[match.end():])
            if inline_tail:
                chunks.append(inline_tail)
                fio = self._full_fio_from_candidate(" ".join(chunks))
                if fio:
                    return fio

            # Three lines are enough for surname / name / patronymic while
            # remaining narrow enough not to cross into a clinical section.
            for next_index in range(index + 1, min(len(lines), index + 4)):
                candidate = clean_value(lines[next_index])
                if not candidate:
                    continue
                if line_starts_with_label(candidate, all_aliases) or looks_like_label(candidate):
                    break
                chunks.append(candidate)
                fio = self._full_fio_from_candidate(" ".join(chunks))
                if fio:
                    return fio

        # Some hospital forms render the caption as a drawing and the value as a
        # normal body paragraph.  The raw XML scanner can then expose only the
        # standalone full-name line.  Accept it only near another demographic
        # marker and near the top of the primary document; reject doctor/signature
        # neighbourhoods so this fallback cannot silently choose a clinician.
        non_empty = [(i, line) for i, line in enumerate(lines) if line]
        for pos, (index, line) in enumerate(non_empty[:40]):
            full_match = self._FIO_FULL_LINE_RE.fullmatch(line)
            if not full_match:
                continue
            nearby_items = non_empty[max(0, pos - 3): min(len(non_empty), pos + 4)]
            nearby = normalize_match(" ".join(value for _idx, value in nearby_items))
            has_demographics = any(
                marker in nearby
                for marker in (
                    "дата рождения", "год рождения", "г.р", "возраст",
                    "зарегистрирован", "место жительства", "адрес проживания",
                    "адрес регистрации",
                )
            )
            role_window = normalize_match(
                " ".join(
                    value
                    for _idx, value in non_empty[max(0, pos - 2): min(len(non_empty), pos + 3)]
                    if value != line
                )
            )
            doctor_context = any(
                marker in role_window
                for marker in (
                    "лечащий врач", "врач-психиатр", "врач психиатр", "заведующ",
                    "зав. отд", "подпись врача", "направил врач", "фельдшер",
                )
            )
            if has_demographics and not doctor_context:
                return clean_value(full_match.group(1))
        return ""

    def _full_fio_from_candidate(self, value: str) -> str:
        candidate = normalize_text(value or "")
        match = self._FIO_FULL_RE.search(candidate)
        if not match:
            return ""
        return clean_value(match.group(1))

    @staticmethod
    def _fio_value_looks_overgrown(value: str) -> bool:
        low = normalize_match(value)
        return bool(
            re.search(r"\b\d{1,3}\s*(?:лет|года|год)\b", low)
            or "проживает" in low
            or "место жительства" in low
            or "адрес" in low
            or "зарегистрирован" in low
            or "возраст" in low
            or bool(re.search(r"\b[12]\d{3}\s*г\.?\s*р?\.?", low))
        )

    def _parse_compact_demographics_line(self, line: str) -> Optional[Tuple[str, str, str, str]]:
        """Implement the _parse_compact_demographics_line workflow with validation, UI state updates and diagnostics."""
        raw = normalize_text(line)
        if not raw:
            return None
        low = normalize_match(raw)

        has_demographic_hint = any(
            hint in low
            for hint in (
                "ф.и.о", "фио", "возраст", "лет", "года", "год", "год рождения", "дата рождения",
                "проживает", "место жительства", "адрес", "зарегистрирован", "г.", "город", "улица", "ул.",
                "работает", "место работы", "работа", "ооо", "ао", "пао", "ип", "гбуз", "мбуз"
            )
        )
        if not has_demographic_hint:
            return None

        # Удаляем ведущие служебные подписи, но оставляем значение.
        compact = re.sub(
            r"^(?:ф\.\s*и\.\s*о\.?|фио|фамилия\s+имя\s+отчество|пациент(?:ка)?|больн(?:ой|ая))\s*[:.-]?\s*",
            "",
            raw,
            flags=re.IGNORECASE,
        ).strip()

        fio = ""
        fio_match = re.search(
            r"\b([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+"
            r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+"
            r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)\b",
            compact,
        )
        if fio_match:
            fio = clean_value(fio_match.group(1))
        else:
            # Редкий вариант без отчества: берём только если строка явно начинается с ФИО.
            two = re.match(
                r"([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)\b",
                compact,
            )
            if two and ("фио" in low or "ф.и.о" in low):
                fio = clean_value(two.group(1))

        # Возраст / год рождения / дата рождения.
        birth_or_age = ""
        labelled_birth = re.search(
            r"(?:возраст|год\s+рождения|дата\s+рождения|г\.\s*р\.)\s*[:.-]?\s*"
            r"(\d{1,3}\s*(?:лет|года|год)?|\d{2}\.\d{2}\.(?:\d{2}|\d{4})|[12]\d{3}\s*(?:г\.?\s*р\.?)?)",
            compact,
            flags=re.IGNORECASE,
        )
        if labelled_birth:
            birth_or_age = clean_value(labelled_birth.group(1))
        else:
            age = re.search(r"\b(\d{1,3}\s*(?:лет|года|год))\b", compact, flags=re.IGNORECASE)
            if age:
                birth_or_age = clean_value(age.group(1))
            else:
                date_or_year = re.search(r"\b(\d{2}\.\d{2}\.(?:\d{2}|\d{4})|[12]\d{3}\s*(?:г\.?\s*р\.?)?)\b", compact)
                if date_or_year:
                    birth_or_age = clean_value(date_or_year.group(1))

        # Адрес / место жительства и место работы.
        address = ""
        work_org = ""

        labelled_work = re.search(
            r"(?<![А-Яа-яA-Za-z0-9])(?:работает(?:\s+в\s+организации)?|место\s+работы|работа)"
            r"(?![А-Яа-яA-Za-z0-9])\s*[:.-]?\s*(.+)$",
            compact,
            flags=re.IGNORECASE,
        )
        if labelled_work and re.search(r"(?:^|\s)не\s+работает\b", compact[:labelled_work.end()], flags=re.IGNORECASE):
            labelled_work = None
        if labelled_work:
            work_org = clean_value(labelled_work.group(1))
            work_org = self._cut_at_next_inline_marker(work_org, self.FIELD_ALIASES["work_org"])
            work_org = clean_value(work_org)

        labelled_address = re.search(
            r"(?:место\s+жительства|адрес(?:\s+проживания|\s+регистрации|\s+места\s+жительства)?|проживает|зарегистрирован(?:а)?(?:\s+по\s+адресу)?)"
            r"\s*[:.-]?\s*(.+)$",
            compact,
            flags=re.IGNORECASE,
        )
        if labelled_address:
            address = clean_value(labelled_address.group(1))
            address = self._cut_at_next_inline_marker(address, self.FIELD_ALIASES["registered"])
            address, inline_work = self._split_address_work_tail(address)
            if inline_work and not work_org:
                work_org = inline_work
            address = clean_value(address)
        elif birth_or_age:
            # Если адрес без подписи идёт после возраста: "..., 45 лет, город N, ул. ..., ООО Организация".
            pos = compact.lower().find(birth_or_age.lower())
            if pos >= 0:
                tail = compact[pos + len(birth_or_age):]
                tail = re.sub(r"^[\s,;:.-]+", "", tail)
                if self._looks_like_address_tail(tail):
                    address, inline_work = self._split_address_work_tail(tail)
                    address = clean_value(address)
                    if inline_work and not work_org:
                        work_org = inline_work

        if not fio and not birth_or_age and not address and not work_org:
            return None
        return fio, birth_or_age, address, work_org

    @staticmethod
    def _split_address_work_tail(text: str) -> Tuple[str, str]:
        """Разделить хвост компактной строки на адрес и место работы.

        Пример: "г. Нижний Новгород, ул. Ленина 34-15, ООО Организация".
        Возвращает адрес без организации и найденную организацию.
        """
        raw = clean_value(text)
        if not raw:
            return "", ""
        org_pattern = (
            r"(?:,|;|\s)\s*("
            r"(?:ООО|ОАО|АО|ПАО|ЗАО|ИП|ГБУЗ|МБУЗ|ФГБУ|ФКУ|ГУФСИН|МВД|МОУ|МАОУ|МБОУ|ГКУ|АНО)"
            r"\b.*)$"
        )
        m = re.search(org_pattern, raw, flags=re.IGNORECASE)
        if not m:
            return raw, ""
        work = clean_value(m.group(1))
        address = clean_value(raw[:m.start(1)]).rstrip(" ,;")
        return address, work

    @staticmethod
    def _looks_like_address_tail(text: str) -> bool:
        low = normalize_match(text)
        if not low or looks_like_label(low):
            return False
        address_hints = (
            "г.", "город", "н.", "нижний", "новгород", "ул", "улица", "просп", "пр-т",
            "пер.", "дом", "д.", "кв", "район", "область", "пос", "село", "деревня"
        )
        return any(hint in low for hint in address_hints)
