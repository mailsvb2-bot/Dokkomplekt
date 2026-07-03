"""Full ICD-10 detail rows (non-F classes), loaded from a bundled resource.

The catalog data lives in ``resources/icd10_full_non_f.tsv`` (one
``code<TAB>russian_title`` per line) rather than inline, so this module stays
small and diff-friendly while still shipping the complete classification.

Source: the official Russian Ministry of Health ICD-10 registry
(OID 1.2.643.5.1.13.13.11.1005), the WHO-based Russian edition distributed
under the MIT license by the ak4nv/mkb10 project. Contains actual three-digit
rubrics and four-digit subrubrics for classes A-Z except F; the detailed,
localized F00-F99 rows already live in icd10_f_data and keep their trusted
psychiatric wording. Non-Russian UI languages fall back to the Russian title.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

_RESOURCE_NAME = "icd10_full_non_f.tsv"


def _resource_candidates() -> tuple[Path, ...]:
    """Locations to look for the bundled ICD-10 resource.

    In a PyInstaller ``--onefile`` build the data is unpacked next to the code
    under ``sys._MEIPASS``; in a normal checkout it sits in ``resources/`` beside
    this module. Check both so the full catalog survives the frozen EXE.
    """

    here = Path(__file__).resolve().parent
    candidates = [here / "resources" / _RESOURCE_NAME]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
        candidates.append(base / "resources" / _RESOURCE_NAME)
        candidates.append(base / _RESOURCE_NAME)
    return tuple(candidates)


@lru_cache(maxsize=1)
def _load_rows() -> tuple[tuple[str, str], ...]:
    text = ""
    for candidate in _resource_candidates():
        try:
            text = candidate.read_text(encoding="utf-8")
            break
        except OSError:
            continue
    if not text:
        return ()
    rows: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        code, _, title = line.partition("\t")
        code = code.strip()
        title = title.strip()
        if code and title:
            rows.append((code, title))
    return tuple(rows)


FULL_ICD10_NON_F_ROWS: tuple[tuple[str, str], ...] = _load_rows()
