from __future__ import annotations

from pathlib import Path

DOCUMENT_OUTPUT_FORMAT_LOCK_VERSION = "v1.0"
SUPPORTED_OUTPUT_FORMATS = ("docx", "pdf")


def normalize_output_format(value: object) -> str:
    text = str(value or "docx").strip().lower()
    aliases = {
        "word": "docx",
        "doc": "docx",
        "docx": "docx",
        "ворд": "docx",
        "pdf": "pdf",
        "пдф": "pdf",
    }
    return aliases.get(text, "docx")


def export_docx_to_pdf(docx_path: str | Path, pdf_path: str | Path | None = None) -> Path:
    source = Path(docx_path).expanduser()
    target = Path(pdf_path).expanduser() if pdf_path else source.with_suffix(".pdf")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        import win32com.client  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - Windows/Office specific
        raise RuntimeError("PDF export requires Microsoft Word on this Windows computer") from exc
    word = None
    document = None
    try:  # pragma: no cover - Windows/Office specific
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        document = word.Documents.Open(str(source.resolve()))
        document.SaveAs(str(target.resolve()), FileFormat=17)
    finally:  # pragma: no cover - Windows/Office specific
        if document is not None:
            document.Close(False)
        if word is not None:
            word.Quit()
    return target


def assert_document_output_format_lock() -> None:
    if DOCUMENT_OUTPUT_FORMAT_LOCK_VERSION != "v1.0":
        raise AssertionError("Document output format lock changed unexpectedly")
    if set(SUPPORTED_OUTPUT_FORMATS) != {"docx", "pdf"}:
        raise AssertionError("User output choice must stay Word/PDF")
