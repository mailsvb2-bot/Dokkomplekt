"""Full ICD-10 catalog integrity tests.

The catalog was upgraded from chapter/block-only to the complete WHO/Minzdrav
classification by bundling ~14k non-F detail rows in
``resources/icd10_full_non_f.tsv``. These tests guard against silent
regressions: the resource missing from the build, the loader breaking, curated
F rows being overwritten, or somatic classes losing their detail again.
"""
from __future__ import annotations

from icd10_full_data import FULL_ICD10_NON_F_ROWS, _resource_candidates
from icd10_f_data import ICD10_DIAGNOSES, assert_icd10_full_catalog_lock
from icd10_f_search import normalize_diagnosis_with_icd10, search_icd10_f


def test_resource_file_present():
    assert any(candidate.exists() for candidate in _resource_candidates())


def test_full_non_f_layer_loaded():
    assert len(FULL_ICD10_NON_F_ROWS) > 10000


def test_catalog_lock_passes():
    assert_icd10_full_catalog_lock()


def test_somatic_detailed_codes_present():
    codes = {item.code for item in ICD10_DIAGNOSES}
    for code in ("A00.0", "C50.9", "E11.9", "I21.0", "J18.9", "K35.8", "N23", "S72.0"):
        assert code in codes, code


def test_curated_f_wording_not_overwritten():
    # The detailed, localized F rows must keep priority over the bulk layer.
    result = normalize_diagnosis_with_icd10("Депрессивный эпизод F32.1")
    assert result.startswith("F32.1")
    assert "Депрессивный эпизод" in result


def test_non_psychiatric_search_works():
    for query, expected_prefix in (
        ("аппендицит", "K35"),
        ("инфаркт миокарда", "I21"),
        ("перелом шейки бедра", "S72"),
    ):
        hits = search_icd10_f(query, limit=3)
        assert hits, query
        assert any(h.code.startswith(expected_prefix) for h in hits), (query, [h.code for h in hits])


def test_no_duplicate_codes():
    codes = [item.code for item in ICD10_DIAGNOSES]
    assert len(codes) == len(set(codes))
