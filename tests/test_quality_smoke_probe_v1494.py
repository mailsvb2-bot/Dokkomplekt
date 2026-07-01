from __future__ import annotations

from smoke_quality_modernization import _missing_large_docstrings


def test_quality_smoke_reports_no_missing_docstrings():
    assert not _missing_large_docstrings()
