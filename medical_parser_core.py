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
        low = normalize_match(text)
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
        admission_date = extract_admission_date_from_primary_docx(path)
        if admission_date:
            data.admission_date = admission_date
        self._refresh_warnings(data)
        sanitize_patient_data_forbidden_phrases(data)
        return data

    def _split_solid_primary_text(self, text: str) -> str:
        text = normalize_text(text)
        if not text:
            return ""
        non_empty_lines = [line for line in text.splitlines() if line.strip()]
        if len(non_empty_lines) > 2:
            return text
        aliases: list[str] = []
        for values in tuple(self.FIELD_ALIASES.values()) + tuple(self.BLOCK_ALIASES.values()):
            aliases.extend(str(item) for item in values if str(item).strip())
        aliases.extend(str(item) for item in self.SECTION_MARKERS if str(item).strip())
        aliases = sorted(set(aliases), key=len, reverse=True)
        repaired = " " + text.strip()
        for alias in aliases:
            alias_pattern = re.escape(alias).replace(r"\ ", r"\s+").replace("ё", "[её]").replace("Ё", "[ЕЁ]")
            pattern = rf"(?<![\nА-Яа-яA-Za-z0-9])({alias_pattern})(?![А-Яа-яA-Za-z0-9])\s*(?=[:№N#.-]|\s)"
            repaired = re.sub(pattern, r"\n\1", repaired, flags=re.IGNORECASE)
        repaired = re.sub(r"\n{2,}", "\n", repaired).strip()
        return normalize_text(repaired)

    def parse_text(self, text: str) -> PatientData:
        text = self._split_solid_primary_text(text)
        data = PatientData()
        data.input_document_kind = self._detect_document_kind(text)
        data.has_treatment_section = has_treatment_section_marker(text)

        for field_name, aliases in self.FIELD_ALIASES.items():
            value = self._extract_inline(text, aliases, field_name=field_name)
            if value:
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
        self._repair_compact_demographics(data, text)
        self._repair_work_details(data, text)
        if data.case_number:
            data.case_number = sanitize_case_number_candidate(data.case_number, patient_name=data.fio)
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
        sanitize_patient_data_forbidden_phrases(data)
        self._refresh_warnings(data)
        return data

    @staticmethod
    def _sanitize_fio_value(value: str) -> str:
        cleaned = clean_value(value)
        if not cleaned:
            return ""
        low = cleaned.lower()
        forbidden = (
            "лечение", "диагноз", "документ", "шаблон", "кнопк",
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
        plain_words = re.findall(r"[А-ЯЁA-Z]{2,}", cleaned)
        if len(plain_words) >= 2:
            return cleaned
        return ""

    @staticmethod
    def _refresh_warnings(data: PatientData) -> None:
        data.warnings.clear()
        for field_name in data.missing_critical_fields():
            data.warnings.append(f"Не найдено критическое поле: {field_name}")
        for field_name in data.missing_recommended_fields():
            data.warnings.append(f"Не найдено рекомендуемое поле: {field_name}")
