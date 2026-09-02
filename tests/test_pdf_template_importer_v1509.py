from __future__ import annotations

from pathlib import Path

from document_intelligence.pdf_reader import PdfReadResult
from universal_profiles import default_document_pack


def test_pdf_importer_creates_profile_owned_docx_template(monkeypatch, tmp_path):
    import pdf_template_importer
    from document_intelligence import analyzer

    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% user-owned test source\n")

    def fake_read_pdf_text(path: str | Path) -> PdfReadResult:
        return PdfReadResult(
            str(path),
            "INVOICE\nInvoice number: ______\nAmount: ______\nChief accountant ______",
            page_count=1,
        )

    monkeypatch.setattr(pdf_template_importer, "read_pdf_text", fake_read_pdf_text)
    monkeypatch.setattr(analyzer, "read_pdf_text", fake_read_pdf_text)

    pack = default_document_pack()
    profile_dir = tmp_path / "profile"
    labels = pdf_template_importer.import_pdf_templates_to_pack(pack, [pdf_path], profile_dir)

    assert labels == ("invoice",)
    assert len(pack.documents) == 1
    document = pack.documents[0]
    assert document.role_id == "pdf_source"
    assert document.template.endswith(".docx")
    assert "custom.invoice_number" in document.required_fields
    assert "custom.amount" in document.required_fields
    assert document.template.startswith("templates/")
    assert (profile_dir / document.template).exists()
    assert list((profile_dir / "templates").glob("*.pdf")) == []


def test_pdf_template_importer_contract_lock():
    from pdf_template_importer import assert_pdf_template_import_lock

    assert_pdf_template_import_lock()
