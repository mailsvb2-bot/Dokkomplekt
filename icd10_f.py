"""Backward-compatible facade for the full local ICD-10 directory."""
from __future__ import annotations

from icd10_models import ICD10Diagnosis
from icd10_f_data import (
    ICD10_DIAGNOSES,
    ICD10_F_DIAGNOSES,
    _BASE_ROWS,
    _BLOCK_ROWS,
    _COMMON_RUBRIC_ROWS,
    _SECTION_ROWS,
    _SUBSTANCE_STATES,
    _SUBSTANCE_TITLES,
    _build_rows,
    _code_sort_key,
    _substance_rows,
    assert_icd10_full_catalog_lock,
)
from icd10_f_search import all_diagnosis_display_values, format_diagnosis, normalize_query, search_icd10_f, _digits_only, normalize_diagnosis_with_icd10, assert_icd10_diagnosis_normalizer_lock

__all__ = [
    "ICD10Diagnosis",
    "ICD10_DIAGNOSES",
    "ICD10_F_DIAGNOSES",
    "format_diagnosis",
    "normalize_query",
    "search_icd10_f",
    "all_diagnosis_display_values",
    "normalize_diagnosis_with_icd10",
    "assert_icd10_diagnosis_normalizer_lock",
    "assert_icd10_full_catalog_lock",
    "_SECTION_ROWS",
    "_BLOCK_ROWS",
    "_COMMON_RUBRIC_ROWS",
    "_BASE_ROWS",
    "_SUBSTANCE_STATES",
    "_SUBSTANCE_TITLES",
    "_build_rows",
    "_code_sort_key",
    "_substance_rows",
    "_digits_only",
]
