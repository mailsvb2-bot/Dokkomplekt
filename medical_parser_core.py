# mypy: disable-error-code=attr-defined
# dynamic mixin attributes are provided by MedicalTextParser composition
from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

from medical_docx_reader import (
    extract_admission_date_from_title_docx,
    extract_docx_text,
    _first_valid_full_date,
    _is_birth_or_demographic_context,
    _is_primary_title_context,
)
from medical_admission_resolver import extract_admission_date_from_primary_docx, extract_admission_date_from_primary_text
from medical_text_utils import sanitize_case_number_candidate
from medical_models import PatientData
from medical_text_utils import sanitize_patient_data_forbidden_phrases
from medical_parser_sanitize import sanitize_diagnosis
from icd10_f_search import normalize_diagnosis_with_icd10
from medical_treatment_detection import has_treatment_section_marker
from medical_text_utils import (
    DIAGNOSIS_STOP_MARKERS,
    clean_value,
    looks_like_label,
    normalize_match,
    normalize_text,
)


class MedicalParserCoreMixin:
    @staticmethod
    def _detect_document_kind(text: str) -> str:
        """Определить тип входного первичного документа для статуса/диагностики.

        Это не влияет на схему данных: и направление, и первичный осмотр
        разбираются в один PatientData и затем используются всеми выбранными
        документами.
        """
        low = normalize_match(text)
        # Сначала направление: в реальных файлах оно может содержать слова
        # «первичный осмотр» как часть текста/шапки, но popup нужен именно для
        # направления на госпитализацию.
        if (
            "направление на госпитализацию" in low
            or "госпитализируется по направлению" in low
            or "целесообразна госпитализация" in low
        ):
            return "направление на госпитализацию"
        if "первичный осмотр" in low:
            return "первичный осмотр"
        return "первичный документ"

    def parse_docx(self, path: str | Path) -> PatientData:
        text = extract_docx_text(path)
        data = self.parse_text(text)
        # Дата поступления в DOCX имеет один источник истины: заголовок
        # документа / имя файла рядом с названием. Если структурный DOCX-поиск
        # нашёл дату рядом с заголовком, он имеет приоритет. Если нет, сохраняем
        # строгий text-fallback из parse_text вместо обнуления уже найденной даты.
        admission_date = extract_admission_date_from_primary_docx(path)
        if admission_date:
            data.admission_date = admission_date
        self._refresh_warnings(data)
        sanitize_patient_data_forbidden_phrases(data)
        return data

    def parse_text(self, text: str) -> PatientData:
        """Implement the parse_text workflow with validation, UI state updates and diagnostics."""
        text = normalize_text(text)
        data = PatientData()
        data.input_document_kind = self._detect_document_kind(text)
        # Full-document scan: if the primary DOCX has no explicit treatment
        # row, the UI must ask the doctor for «Лечение» when any medical
        # document is selected in block 03.
        data.has_treatment_section = has_treatment_section_marker(text)

        for field_name, aliases in self.FIELD_ALIASES.items():
            value = self._extract_inline(text, aliases, field_name=field_name)
            if value:
                # "Проживает - в семье" в анамнезе жизни не является адресом регистрации.
                # Адрес берём только из явных адресных строк или компактной строки пациента.
                if field_name == "registered" and not self._looks_like_address_tail(value):
                    continue
                if field_name == "case_number":
                    value = sanitize_case_number_candidate(value)
                    if not value:
                        continue
                setattr(data, field_name, value)

        for field_name, aliases in self.BLOCK_ALIASES.items():
            value = self._extract_block(text, aliases)
            if value:
                setattr(data, field_name, value)

        data.admission_date = extract_admission_date_from_primary_text(text) or self._extract_admission_date(text)

        # Поддержка компактных первичных документов: ФИО, возраст и адрес
        # могут быть написаны в одну строку, а не в отдельный столбец.
        self._repair_compact_demographics(data, text)

        # Работа и должность должны подтягиваться из первичного документа в
        # popup-окна как два отдельных значения. Поддерживаем как отдельные
        # поля «Работает в организации» / «Должность», так и одну фразу
        # «Работает в ..., в должности ...».
        self._repair_work_details(data, text)

        # После восстановления ФИО повторно чистим номер истории болезни уже с
        # контекстом пациента.  Первичный проход идёт по FIELD_ALIASES и видит
        # ``case_number`` раньше ``fio``; без второго прохода строка вида
        # «История болезни № Иванов Иван Иванович 123» могла попасть в popup
        # целиком или быть отброшена вместе с настоящим номером.
        if data.case_number:
            data.case_number = sanitize_case_number_candidate(data.case_number, patient_name=data.fio)

        # Анамнез жизни может быть не только таблицей/столбцом с явной меткой
        # «Анамнез жизни», но и свободным абзацем: "наследственность - ...
        # Родился... Беременность и роды...". Берём исходные слова и стиль
        # из первичного документа, не пересобирая текст искусственно.
        self._repair_life_anamnesis_from_free_style(data, text)

        if not data.diagnosis:
            diagnosis = self._extract_after_phrase(text, r"был\s+выставлен\s+диагноз\s*[:.]?")
            if diagnosis:
                data.diagnosis = diagnosis

        if data.diagnosis:
            data.diagnosis = normalize_diagnosis_with_icd10(data.diagnosis)

        for key, value in list(asdict(data).items()):
            if isinstance(value, str) and self._parsed_field_value_is_only_label(key, value):
                setattr(data, key, "")

        if data.diagnosis:
            data.diagnosis = normalize_diagnosis_with_icd10(data.diagnosis)
        if data.fio:
            data.fio = self._sanitize_fio_value(data.fio)

        # Универсальный режим не имеет зашитого города, врача, заведующего или
        # профильного эпиданамнеза. Если шаблон требует эти значения, они
        # должны прийти из исходного документа, профиля врача или popup-а.
        sanitize_patient_data_forbidden_phrases(data)

        self._refresh_warnings(data)

        return data

    @staticmethod
    def _sanitize_fio_value(value: str) -> str:
        """Reject accidental non-name fragments captured as patient FIO."""
        cleaned = clean_value(value)
        if not cleaned:
            return ""
        low = cleaned.lower()
        forbidden = (
            "лечение", "диагноз", "документ", "шаблон", "кнопк", "попап",
            "история болезни", "дата", "осмотр", "жалобы", "анамнез",
            "комиссия", "мсэ", "рвк", "эпикриз", "подпись",
        )
        if any(word in low for word in forbidden):
            return ""
        if len(cleaned) > 90:
            return ""
        words = re.findall(r"[А-ЯЁA-Z][а-яёa-z]+|[А-ЯЁA-Z]\.", cleaned)
        if len(words) >= 2:
            return cleaned
        # Also support all-caps table values like "ИВАНОВ ИВАН ИВАНОВИЧ".
        plain_words = re.findall(r"[А-ЯЁA-Z]{2,}", cleaned)
        if len(plain_words) >= 2:
            return cleaned
        return ""

    @staticmethod
    def _refresh_warnings(data: PatientData) -> None:
        """Rebuild parser warnings after late repairs/overrides.

        parse_docx can fill admission_date after parse_text has already run.
        Recomputing warnings prevents stale "missing admission date" messages in
        the UI preview and strict-mode diagnostics.
        """
        data.warnings.clear()
        for field_name in data.missing_critical_fields():
            data.warnings.append(f"Не найдено критическое поле: {field_name}")
        for field_name in data.missing_recommended_fields():
            data.warnings.append(f"Не найдено рекомендуемое поле: {field_name}")
