from __future__ import annotations

from contextlib import contextmanager, suppress
from diagnostic_logging import record_soft_exception
import hashlib
import importlib
import os
import shutil
from pathlib import Path
import tempfile
import time
import zipfile
import xml.etree.ElementTree as ET

from medical_text_utils import normalize_text

OPENXML_WORD_SUFFIXES = {".docx", ".docm"}
LEGACY_WORD_SUFFIXES = {".doc"}
SUPPORTED_WORD_SUFFIXES = OPENXML_WORD_SUFFIXES | LEGACY_WORD_SUFFIXES


def is_supported_word_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_WORD_SUFFIXES


def supported_word_filetypes() -> list[tuple[str, str]]:
    return [("Word DOCX/DOCM; старый DOC требует Microsoft Word", "*.docx *.docm *.doc"), ("Все файлы", "*.*")]


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
    if source.suffix.lower() == ".docx":
        return source
    if source.suffix.lower() == ".docm":
        return convert_docm_to_docx(source)
    return convert_doc_to_docx(source)


def convert_docm_to_docx(path: str | Path) -> Path:
    """Create a macro-free DOCX view of a DOCM package for python-docx.

    ``python-docx`` rejects the macro-enabled main content type even though the
    document body is ordinary WordprocessingML. For reading/rendering doctor
    templates we deliberately strip VBA parts and rewrite the package content
    type into a temporary DOCX. The original user-owned DOCM is never changed.
    """

    source = existing_word_file(path, "macro-enabled Word document")
    if source.suffix.lower() != ".docm":
        return source
    target = _conversion_target(source)
    if _converted_target_is_current(source, target, diagnostic_key="medical_word_format.docm_stat"):
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _conversion_publish_lock(target):
            # Another process may have published the same deterministic cache
            # target while we were waiting. Re-check under the cross-process
            # lock so only one process ever replaces the canonical target.
            if _converted_target_is_current(source, target, diagnostic_key="medical_word_format.docm_stat"):
                return target
            workspace = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=str(target.parent)))
            tmp_target = workspace / target.name
            macro_main_type = b"application/vnd.ms-word.document.macroEnabled.main+xml"
            docx_main_type = b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
            try:
                with zipfile.ZipFile(source, "r") as src, zipfile.ZipFile(tmp_target, "w", compression=zipfile.ZIP_DEFLATED) as dst:
                    for info in src.infolist():
                        name = info.filename
                        lower_name = name.casefold()
                        if lower_name.startswith("word/vba") or lower_name.endswith("vbaproject.bin"):
                            continue
                        data = src.read(name)
                        if name == "[Content_Types].xml":
                            data = data.replace(macro_main_type, docx_main_type)
                            try:
                                root = ET.fromstring(data)
                                for child in list(root):
                                    ctype = str(child.attrib.get("ContentType", "")).casefold()
                                    extension = str(child.attrib.get("Extension", "")).casefold()
                                    part_name = str(child.attrib.get("PartName", "")).casefold()
                                    if "vba" in ctype or (extension == "bin" and "vba" in part_name):
                                        root.remove(child)
                                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                            except ET.ParseError as exc:
                                record_soft_exception("medical_word_format.docm_content_types", exc, detail=str(source))
                        elif lower_name.endswith(".rels") and b"vbaProject" in data:
                            try:
                                root = ET.fromstring(data)
                                for child in list(root):
                                    rel_type = str(child.attrib.get("Type", ""))
                                    target_name = str(child.attrib.get("Target", ""))
                                    if "vbaProject" in rel_type or "vbaProject" in target_name:
                                        root.remove(child)
                                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                            except ET.ParseError as exc:
                                record_soft_exception("medical_word_format.docm_relationships", exc, detail=str(source))
                        dst.writestr(info, data)
                os.replace(tmp_target, target)
                return target
            finally:
                shutil.rmtree(workspace, ignore_errors=True)
    except Exception as exc:
        record_soft_exception("medical_word_format.convert_docm_to_docx", exc, detail=str(source))
        raise RuntimeError("Failed to prepare DOCM as a macro-free DOCX copy.") from exc


def convert_doc_to_docx(path: str | Path) -> Path:
    source = existing_word_file(path, "legacy doc")
    if source.suffix.lower() != ".doc":
        return source
    target = _conversion_target(source)
    if _converted_target_is_current(source, target, diagnostic_key="medical_word_format.stat"):
        return target
    if os.name != "nt":
        raise RuntimeError("Legacy DOC conversion requires Windows with Microsoft Word. Save the file as DOCX and retry.")
    try:
        win32com_client = importlib.import_module("win32com.client")
    except Exception as exc:
        raise RuntimeError("Legacy DOC conversion requires Microsoft Word and pywin32. Save the file as DOCX and retry.") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _conversion_publish_lock(target):
            if _converted_target_is_current(source, target, diagnostic_key="medical_word_format.stat"):
                return target
            word = None
            doc = None
            workspace = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=str(target.parent)))
            tmp_target = workspace / target.name
            try:
                word = win32com_client.DispatchEx("Word.Application")
                word.Visible = False
                word.DisplayAlerts = 0
                doc = word.Documents.Open(str(source.resolve()), ReadOnly=True, AddToRecentFiles=False)
                doc.SaveAs2(str(tmp_target.resolve()), FileFormat=16)
                if not tmp_target.exists() or tmp_target.stat().st_size <= 0:
                    raise RuntimeError("Microsoft Word did not create the converted DOCX file")
                os.replace(tmp_target, target)
                return target
            finally:
                with suppress(Exception):
                    if doc is not None:
                        doc.Close(False)
                with suppress(Exception):
                    if word is not None:
                        word.Quit()
                shutil.rmtree(workspace, ignore_errors=True)
    except Exception as exc:
        record_soft_exception("medical_word_format.convert_doc_to_docx", exc, detail=str(source))
        raise RuntimeError("Failed to convert DOC to DOCX. Close the file in Word or save it as DOCX manually.") from exc


def _converted_target_is_current(source: Path, target: Path, *, diagnostic_key: str) -> bool:
    try:
        source_stat = source.stat()
        target_stat = target.stat()
        return target_stat.st_mtime_ns >= source_stat.st_mtime_ns and target_stat.st_size > 0
    except FileNotFoundError:
        return False
    except OSError as exc:
        record_soft_exception(diagnostic_key, exc, detail=str(source))
        return False


@contextmanager
def _conversion_publish_lock(target: Path, *, timeout_seconds: float = 180.0):
    """Serialize publication of one deterministic conversion target across processes.

    Staging files are already per-process, but Windows forbids replacing a file
    that another process currently has open. A tiny atomic lock directory keeps
    publication single-writer, while the caller re-checks the cache after
    acquiring it. Crashed-process locks are reclaimed after a conservative age.
    """

    lock_path = target.parent / f".{target.name}.publish-lock"
    deadline = time.monotonic() + max(1.0, float(timeout_seconds))
    stale_after = max(300.0, float(timeout_seconds) * 2.0)
    acquired = False
    while not acquired:
        try:
            lock_path.mkdir()
            acquired = True
            break
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except FileNotFoundError:
                continue
            except OSError as exc:
                record_soft_exception("medical_word_format.conversion_lock_stat", exc, detail=str(lock_path))
                age = 0.0
            if age > stale_after:
                shutil.rmtree(lock_path, ignore_errors=True)
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for Word conversion cache lock: {target.name}")
            time.sleep(0.025)
    try:
        yield
    finally:
        if acquired:
            shutil.rmtree(lock_path, ignore_errors=True)


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
