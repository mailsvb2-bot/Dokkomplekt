"""Compatibility wrapper that lets the public medical service accept legacy .doc.

The legacy binary Word format is converted locally to DOCX by
``medical_word_format`` before the existing parser/renderer pipeline sees the
file.  This keeps the old service implementation intact while extending the
public facade used by the GUI.
"""

from __future__ import annotations

from pathlib import Path

from medical_service import MedicalDocumentService as _BaseMedicalDocumentService
from medical_word_format import SUPPORTED_WORD_SUFFIXES, ensure_docx_compatible, existing_word_file


class MedicalDocumentService(_BaseMedicalDocumentService):
    """MedicalDocumentService with .doc acceptance at the boundary."""

    @staticmethod
    def _existing_file(
        path: str | Path | None,
        label: str,
        *,
        allowed_suffixes: set[str] | None = None,
    ) -> Path:
        if allowed_suffixes is not None and ({".docx", ".docm"} & set(allowed_suffixes)):
            allowed_suffixes = set(allowed_suffixes) | {".doc"}
        return _BaseMedicalDocumentService._existing_file(path, label, allowed_suffixes=allowed_suffixes)

    def parse_primary_document(self, path: str | Path):
        source = existing_word_file(path, "первичный документ")
        return self.parser.parse_docx(ensure_docx_compatible(source, label="первичный документ"))

    def load_epi_text(self, path: str | Path) -> str:
        if not path:
            return ""
        source = existing_word_file(path, "ЭПИ")
        if source.suffix.lower() == ".txt":
            text = self._read_text_file(source)
        else:
            from medical_docx_reader import extract_docx_text
            text = extract_docx_text(source)
        from medical_formatting import strip_leading_epi_label
        return strip_leading_epi_label(text)


def assert_medical_service_doc_compat_lock() -> None:
    if ".doc" not in SUPPORTED_WORD_SUFFIXES:
        raise AssertionError("Medical service must keep legacy .doc support")
    service = MedicalDocumentService()
    try:
        service._existing_file("missing.doc", "тест", allowed_suffixes={".docx", ".docm"})
    except FileNotFoundError:
        pass
    except ValueError as exc:
        raise AssertionError("Medical service must not reject .doc by suffix before existence/parse handling") from exc
