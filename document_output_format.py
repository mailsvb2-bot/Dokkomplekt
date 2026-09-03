from __future__ import annotations

from pathlib import Path

DOCUMENT_OUTPUT_FORMAT_LOCK_VERSION = "v1.1"
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
    """Export a Word file read-only, without recent-file pollution or partial PDF leftovers."""
    source = Path(docx_path).expanduser()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Word-документ для PDF не найден: {source}")
    if source.suffix.lower() not in {".docx", ".docm"}:
        raise ValueError(f"Для PDF нужен DOCX/DOCM, получен: {source.name}")
    target = Path(pdf_path).expanduser() if pdf_path else source.with_suffix(".pdf")
    if target.suffix.lower() != ".pdf":
        raise ValueError("Файл результата PDF должен иметь расширение .pdf")
    if target.resolve() == source.resolve():
        raise ValueError("PDF не может перезаписывать исходный Word-файл")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        import win32com.client  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - Windows/Office specific
        raise RuntimeError("Для создания PDF на этом компьютере требуется Microsoft Word") from exc
    word = None
    document = None
    try:  # pragma: no cover - Windows/Office specific
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        document = word.Documents.Open(
            FileName=str(source.resolve()),
            ReadOnly=True,
            AddToRecentFiles=False,
            ConfirmConversions=False,
        )
        document.ExportAsFixedFormat(
            OutputFileName=str(target.resolve()),
            ExportFormat=17,
            OpenAfterExport=False,
        )
        if not target.exists() or not target.is_file() or target.stat().st_size <= 0:
            raise RuntimeError("Microsoft Word не создал итоговый PDF-файл")
        return target
    except Exception:
        try:
            if target.exists():
                target.unlink()
        except OSError:
            pass
        raise
    finally:  # pragma: no cover - Windows/Office specific
        if document is not None:
            document.Close(False)
        if word is not None:
            word.Quit()


def assert_document_output_format_lock() -> None:
    if DOCUMENT_OUTPUT_FORMAT_LOCK_VERSION != "v1.1":
        raise AssertionError("Document output format lock changed unexpectedly")
    if set(SUPPORTED_OUTPUT_FORMATS) != {"docx", "pdf"}:
        raise AssertionError("User output choice must stay Word/PDF")
