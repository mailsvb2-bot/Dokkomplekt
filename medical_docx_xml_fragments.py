from __future__ import annotations

from contextlib import suppress
from diagnostic_logging import record_soft_exception
import hashlib
import importlib
import os
from pathlib import Path
import tempfile
import zipfile
import xml.etree.ElementTree as ET

from medical_text_utils import normalize_text

OPENXML_WORD_SUFFIXES = {".docx", ".docm"}
LEGACY_WORD_SUFFIXES = {".doc"}
SUPPORTED_WORD_SUFFIXES = OPENXML_WORD_SUFFIXES | LEGACY_WORD_SUFFIXES


def is_supported_word_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_WORD_SUFFIXES


def supported_word_filetypes() -> list[tuple[str, str]]:
    return [("Word", "*.docx *.docm *.doc"), ("All files", "*.*")]


def existing_word_file(path: str | Path | None, label: str) -> Path:
    if path is None or str(path).strip() == "":
        raise ValueError(f"No file selected: {label}.")
    candidate = Path(path).expanduser()
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(f"File not found ({label}): {candidate}")
    if candidate.suffix.lower() not in SUPPORTED_WORD_SUFFIXES:
        allowed = ", ".join(sorted(SUPPORTED_WORD_SUFFIXES))
        raise ValueError(f"Unsupported file format ({label}): {candidate.suffix or 'no extension'}. Allowed: {allowed}.")
    return candidate


def ensure_docx_compatible(path: str | Path, *, label: str = "Word document") -> Path:
    source = existing_word_file(path, label)
    if source.suffix.lower() in OPENXML_WORD_SUFFIXES:
        return source
    return convert_doc_to_docx(source)


def convert_doc_to_docx(path: str | Path) -> Path:
    source = existing_word_file(path, "legacy doc")
    if source.suffix.lower() != ".doc":
        return source
    target = _conversion_target(source)
    try:
        source_stat = source.stat()
        if target.exists() and target.stat().st_mtime_ns >= source_stat.st_mtime_ns and target.stat().st_size > 0:
            return target
    except OSError as exc:
        record_soft_exception("medical_word_format.stat", exc, detail=str(source))
    if os.name != "nt":
        raise RuntimeError("Legacy DOC conversion requires Windows with Microsoft Word. Save the file as DOCX and retry.")
    try:
        win32com_client = importlib.import_module("win32com.client")
    except Exception as exc:
        raise RuntimeError("Legacy DOC conversion requires Microsoft Word and pywin32. Save the file as DOCX and retry.") from exc
    word = None
    doc = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        word = win32com_client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(source.resolve()), ReadOnly=True, AddToRecentFiles=False)
        doc.SaveAs2(str(target.resolve()), FileFormat=16)
        return target
    except Exception as exc:
        with suppress(Exception):
            if target.exists() and target.stat().st_size <= 0:
                target.unlink()
        record_soft_exception("medical_word_format.convert_doc_to_docx", exc, detail=str(source))
        raise RuntimeError("Failed to convert DOC to DOCX. Close the file in Word or save it as DOCX manually.") from exc
    finally:
        with suppress(Exception):
            if doc is not None:
                doc.Close(False)
        with suppress(Exception):
            if word is not None:
                word.Quit()


def _conversion_target(source: Path) -> Path:
    try:
        stat = source.stat()
        seed = f"{source.resolve()}|{stat.st_mtime_ns}|{stat.st_size}"
    except OSError:
        seed = str(source)
    digest = hashlib.sha256(seed.encode("utf-8", errors="surrogatepass")).hexdigest()[:16]
    root = Path(tempfile.gettempdir()) / "MedicalDiaryAutofill" / "converted_doc"
    return root / f"{source.stem}.{digest}.docx"


def _docx_xml_text_fragments(path: str | Path) -> list[str]:
    fragments: list[str] = []
    try:
        with zipfile.ZipFile(str(path)) as zf:
            names = [
                name for name in zf.namelist()
                if name.startswith("word/")
                and name.endswith(".xml")
                and (name == "word/document.xml" or name.startswith("word/header") or name.startswith("word/footer"))
            ]
            names.sort(key=lambda n: (0 if n == "word/document.xml" else 1, n))
            for name in names:
                try:
                    root = ET.fromstring(zf.read(name))
                except Exception as exc:
                    record_soft_exception("medical_docx_xml_fragments.parse_xml", exc, detail=name)
                    continue
                for para in root.iter():
                    if not str(para.tag).endswith("}p"):
                        continue
                    parts: list[str] = []
                    for node in para.iter():
                        tag = str(node.tag)
                        if (tag.endswith("}t") or tag.endswith("}instrText")) and node.text:
                            parts.append(node.text)
                    value = normalize_text("".join(parts))
                    if value:
                        fragments.append(value)
    except Exception as exc:
        record_soft_exception("medical_docx_xml_fragments.open_zip", exc, detail=str(path))
        return []
    return fragments
