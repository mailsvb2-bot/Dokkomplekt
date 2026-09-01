from __future__ import annotations

from pathlib import Path

from document_intelligence.models import DocumentSource
from document_intelligence.pdf_reader import PdfReadResult
from document_output_format import normalize_output_format, assert_document_output_format_lock


def test_document_intelligence_analyzes_text_pdf_without_builtin_templates(monkeypatch, tmp_path):
    from document_intelligence import analyzer

    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% user supplied placeholder\n")

    def fake_read_pdf_text(path: str | Path) -> PdfReadResult:
        return PdfReadResult(
            str(path),
            "INVOICE\nInvoice number: ______\nAmount: ______\nChief accountant ______",
            page_count=1,
        )

    monkeypatch.setattr(analyzer, "read_pdf_text", fake_read_pdf_text)
    blueprint = analyzer.DocumentIntelligenceCore().analyze_source(DocumentSource(str(pdf_path), user_label="Invoice PDF"))
    labels = {field.label for field in blueprint.fields}

    assert blueprint.source.endswith("invoice.pdf")
    assert blueprint.domain == "accounting"
    assert blueprint.shape == "blank_form"
    assert {"Invoice number", "Amount"} <= labels
    assert any(signature.role == "accountant" for signature in blueprint.signatures)


def test_output_format_contract_supports_user_word_or_pdf_choice():
    assert normalize_output_format("word") == "docx"
    assert normalize_output_format("ворд") == "docx"
    assert normalize_output_format("pdf") == "pdf"
    assert normalize_output_format("пдф") == "pdf"
    assert_document_output_format_lock()
