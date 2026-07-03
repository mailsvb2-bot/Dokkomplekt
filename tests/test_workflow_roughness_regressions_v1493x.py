"""Regression tests for two workflow roughnesses found by scenario emulation.

1. A trailing period on a parsed diagnosis ("Параноидная шизофрения.") broke the
   ICD-10 catalog search, so the automatic name->code lookup never fired on real
   documents and the doctor had to open the diagnosis selector by hand.
2. Russian worded dates ("1 июня 2026") did not parse (only Polish month names
   were supported), so on a Russian primary document the admission/discharge
   date silently failed and had to be re-typed.

Both must keep working so "drop the file, the program does the rest" holds.
"""
from __future__ import annotations

from medical_formatting import parse_date
from medical_parser_sanitize import sanitize_diagnosis
from icd10_f_search import normalize_diagnosis_with_icd10
from medical_admission_resolver import (
    extract_admission_date_from_primary_text,
    extract_discharge_date_from_primary_text,
)


def test_trailing_period_diagnosis_resolves_to_code():
    assert normalize_diagnosis_with_icd10("Параноидная шизофрения.").startswith("F20.0")
    assert normalize_diagnosis_with_icd10("Депрессивный эпизод средней степени.").startswith("F32.1")
    assert normalize_diagnosis_with_icd10("Биполярное аффективное расстройство.").startswith("F31")


def test_diagnosis_code_with_internal_dot_is_untouched():
    # The dot inside F20.0 / K35.8 must survive: only the trailing sentence dot is cut.
    assert sanitize_diagnosis("F20.0") == "F20.0"
    assert sanitize_diagnosis("Острый аппендицит K35.8.") == "Острый аппендицит K35.8"
    assert normalize_diagnosis_with_icd10("Острый аппендицит K35.8.").startswith("K35.8")


def test_russian_worded_dates_parse():
    assert parse_date("1 июня 2026").strftime("%d.%m.%Y") == "01.06.2026"
    assert parse_date("10 февраля 2026 г.").strftime("%d.%m.%Y") == "10.02.2026"
    assert parse_date("15 января 2025").strftime("%d.%m.%Y") == "15.01.2025"
    assert parse_date("5 мая 2026").strftime("%d.%m.%Y") == "05.05.2026"


def test_polish_worded_dates_still_parse():
    assert parse_date("1 czerwca 2026").strftime("%d.%m.%Y") == "01.06.2026"
    assert parse_date("15 stycznia 2025").strftime("%d.%m.%Y") == "15.01.2025"


def test_russian_worded_dates_extracted_from_primary_text():
    text = "Дата поступления: 1 июня 2026 г. Дата выписки: 10 июня 2026 г."
    assert extract_admission_date_from_primary_text(text) == "01.06.2026"
    assert extract_discharge_date_from_primary_text(text) == "10.06.2026"

    verb = "Поступил 5 мая 2026, выписан 20 мая 2026."
    assert extract_admission_date_from_primary_text(verb) == "05.05.2026"
    assert extract_discharge_date_from_primary_text(verb) == "20.05.2026"
