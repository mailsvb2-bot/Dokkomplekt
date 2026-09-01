from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PdfReadResult:
    path: str
    text: str
    page_count: int = 0
    encrypted: bool = False
    warnings: tuple[str, ...] = ()

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


def read_pdf_text(path: str | Path) -> PdfReadResult:
    source = Path(path).expanduser()
    warnings: list[str] = []
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - dependency failure is environment-specific
        return PdfReadResult(str(source), "", warnings=(f"PDF parser is unavailable: {exc}",))
    try:
        reader = PdfReader(str(source))
        encrypted = bool(getattr(reader, "is_encrypted", False))
        if encrypted:
            try:
                reader.decrypt("")
            except Exception:
                return PdfReadResult(str(source), "", len(reader.pages), True, ("PDF is encrypted",))
        parts: list[str] = []
        for page in reader.pages:
            try:
                parts.append(str(page.extract_text() or ""))
            except Exception as exc:
                warnings.append(f"Could not read one PDF page: {exc}")
        return PdfReadResult(str(source), "\n".join(parts), len(reader.pages), encrypted, tuple(warnings))
    except Exception as exc:
        return PdfReadResult(str(source), "", warnings=(f"Could not read PDF: {exc}",))
