from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_built_in_user_docx_templates_are_shipped():
    forbidden = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".docx", ".docm", ".dotx", ".dotm"}:
            forbidden.append(path.relative_to(ROOT).as_posix())
    assert forbidden == []


def test_embedded_template_storage_stays_empty():
    import embedded_templates

    assert embedded_templates.TEMPLATE_B64 == {}


def test_document_intelligence_core_is_not_a_builtin_template_pack():
    from document_intelligence.analyzer import DocumentIntelligenceCore
    from document_intelligence.models import SUPPORTED_DOCUMENT_SHAPES

    assert DocumentIntelligenceCore is not None
    assert {"blank_form", "table_form", "free_text", "mixed"}.issubset(set(SUPPORTED_DOCUMENT_SHAPES))
