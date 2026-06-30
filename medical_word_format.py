"""Word file format compatibility helpers.

The production document engine is DOCX-based because ``python-docx`` reads Office
Open XML files only.  Doctors, however, may still have legacy binary ``.doc``
files.  This module centralizes support for those files without making every
parser/template path know about COM automation.
"""

from __future__ import annotations

from contextlib import suppress
import hashlib
import os
from pathlib import Path
import tempfile

from diagnostic_logging import record_soft_exception

OPENXML_WORD_SUFFIXES = {".docx", ".docm"}
LEGACY_WORD_SUFFIXES = {".doc"}
SUPPORTED_WORD_SUFFIXES = OPENXML_WORD_SUFFIXES | LEGACY_WORD_SUFFIXES

WORD_FORMAT_LOCK_VERSION = "v1.0"
WORD_FORMAT_ACCEPTS_LEGACY_DOC = True
WORD_FORMAT_CONVERTS_DOC_TO_DOCX = True


def is_supported_word_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_WORD_SUFFIXES


def supported_word_filetypes() -> list[tuple[str, str]]:
    return [("Word", "*.docx *.docm *.doc"), ("All files", "*.*")]


def existing_word_file(path: str | Path | None, label: str) -> Path:
    if path is None or str(path).strip() == "":
        raise ValueError(f"Не выбран файл: {label}.")
    candidate = Path(path).expanduser()
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(f"Не найден файл ({label}): {candidate}")
    if candidate.suffix.lower() not in SUPPORTED_WORD_SUFFIXES:
        allowed = ", ".join(sorted(SUPPORTED_WORD_SUFFIXES))
        raise ValueError(f"Неверный формат файла ({label}): {candidate.suffix or 'без расширения'}. Разрешено: {allowed}.")
    return candidate


def ensure_docx_compatible(path: str | Path, *, label: str = "Word-документ") -> Path:
    """Return a path that ``python-docx`` can open.

    ``.docx`` and ``.docm`` are returned unchanged.  Legacy ``.doc`` files are
    converted into a deterministic temporary ``.docx`` copy.  Conversion is
    intentionally local-only and uses Microsoft Word COM when available.
    """

    source = existing_word_file(path, label)
    if source.suffix.lower() in OPENXML_WORD_SUFFIXES:
        return source
    return convert_doc_to_docx(source)


def convert_doc_to_docx(path: str | Path) -> Path:
    source = existing_word_file(path, "legacy .doc")
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
        raise RuntimeError(
            "Файл .doc можно автоматически открыть только на Windows с установленным Microsoft Word. "
            "Сохраните документ как .docx и повторите."
        )
    try:
        import win32com.client  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - depends on real Windows/pywin32
        raise RuntimeError(
            "Для .doc нужен установленный Microsoft Word и pywin32. "
            "Сохраните файл как .docx или установите Word."
        ) from exc

    word = None
    doc = None
    try:  # pragma: no cover - exercised only on real Windows with Word
        target.parent.mkdir(parents=True, exist_ok=True)
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(source.resolve()), ReadOnly=True, AddToRecentFiles=False)
        # 16 = wdFormatXMLDocument (.docx)
        doc.SaveAs2(str(target.resolve()), FileFormat=16)
        return target
    except Exception as exc:  # pragma: no cover - depends on local Word install
        with suppress(Exception):
            if target.exists() and target.stat().st_size <= 0:
                target.unlink()
        record_soft_exception("medical_word_format.convert_doc_to_docx", exc, detail=str(source))
        raise RuntimeError(
            "Не удалось конвертировать .doc в .docx. Закройте документ в Word или сохраните его вручную как .docx."
        ) from exc
    finally:  # pragma: no cover - depends on local Word install
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


def assert_word_format_lock() -> None:
    if WORD_FORMAT_LOCK_VERSION != "v1.0":
        raise AssertionError("Word format compatibility lock changed unexpectedly")
    if not WORD_FORMAT_ACCEPTS_LEGACY_DOC or not WORD_FORMAT_CONVERTS_DOC_TO_DOCX:
        raise AssertionError("Legacy .doc files must remain accepted through conversion")
    if ".doc" not in SUPPORTED_WORD_SUFFIXES or ".docx" not in SUPPORTED_WORD_SUFFIXES or ".docm" not in SUPPORTED_WORD_SUFFIXES:
        raise AssertionError("Supported Word suffixes are incomplete")
