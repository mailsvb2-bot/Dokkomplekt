from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from diagnostic_logging import record_soft_exception

PRIMARY_DOCUMENT_SUFFIXES = {".docx", ".docm"}


def clean_primary_document_path(value: object) -> str:
    """Return one stable filesystem path from Tk/filedialog/DnD values.

    Tk/TkDND may pass a selected file as ``{C:\\path with spaces\\file.docx}``,
    as a Tcl list, or as a ``file:///`` URI.  Creation/preflight must consume
    the same path the UI shows; otherwise the drop-zone can say that a primary
    document is selected while generation later reports that it is missing.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.strip().strip('"').strip("'").strip()
    text = _single_tk_path_item(text)
    text = text.strip().strip('"').strip("'").strip()
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1].strip()
    return _clean_file_uri(text)


def _single_tk_path_item(text: str) -> str:
    """Unwrap a single Tk/Tcl list item without breaking normal Windows paths."""
    if not text:
        return ""
    # Fast path for the common TkDND representation.
    if text.startswith("{") and text.endswith("}") and text.count("{") == 1 and text.count("}") == 1:
        return text[1:-1].strip()
    # ``Tcl().splitlist`` is the correct parser for paths wrapped by TkDND, but
    # it must stay best-effort so Linux CI/headless machines and plain strings
    # never become dependent on a GUI session.
    if "{" not in text and "}" not in text:
        return text
    try:
        import tkinter as tk

        parts = tuple(str(part).strip() for part in tk.Tcl().splitlist(text) if str(part).strip())
    except Exception as exc:
        record_soft_exception("medical_primary_document_state.tk_splitlist", exc, detail=text[:160])
        return text
    if len(parts) == 1:
        return parts[0]
    for part in parts:
        suffix = Path(part).suffix.lower()
        if suffix in PRIMARY_DOCUMENT_SUFFIXES:
            return part
    return parts[0] if parts else text


def _clean_file_uri(text: str) -> str:
    if not text.lower().startswith("file:"):
        return text
    try:
        parsed = urlparse(text)
        path = unquote(parsed.path or "")
        if parsed.netloc:
            path = f"//{parsed.netloc}{path}"
        # Windows file URIs commonly look like file:///C:/Users/...; pathlib on
        # Windows expects C:/Users/... without the leading slash.
        if len(path) >= 4 and path[0] == "/" and path[2] == ":" and path[1].isalpha():
            path = path[1:]
        return path or text
    except Exception as exc:
        record_soft_exception("medical_primary_document_state.file_uri", exc, detail=text[:160])
        return text


def _var_get(app: Any, name: str) -> str:
    try:
        var = getattr(app, name, None)
        return clean_primary_document_path(var.get()) if var is not None and hasattr(var, "get") else ""
    except Exception as exc:
        record_soft_exception("medical_primary_document_state.var_get", exc, detail=name)
        return ""


def _candidate_values(app: Any) -> list[str]:
    values: list[str] = []
    for name in ("navigation_path_var",):
        value = _var_get(app, name)
        if value:
            values.append(value)
    for attr in ("_last_primary_document_path", "_active_primary_document_path"):
        value = clean_primary_document_path(getattr(app, attr, ""))
        if value:
            values.append(value)
    try:
        review = getattr(app, "_last_patient_case_review", None)
        value = clean_primary_document_path(getattr(review, "primary_path", ""))
        if value:
            values.append(value)
    except Exception as exc:
        record_soft_exception("medical_primary_document_state.review_path", exc)
    # Preserve order while removing duplicates that only differ by trivial wrappers.
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def is_existing_primary_document_path(path: str | Path) -> bool:
    try:
        candidate = Path(clean_primary_document_path(path)).expanduser()
        return candidate.exists() and candidate.is_file() and candidate.suffix.lower() in PRIMARY_DOCUMENT_SUFFIXES
    except Exception as exc:
        record_soft_exception("medical_primary_document_state.is_existing", exc, detail=str(path))
        return False


def selected_primary_document_path(app: Any) -> Path | None:
    """Find the actual selected primary DOCX/DOCM and resync UI state.

    The visual drop-zone status and the internal navigation path must never drift.
    This resolver makes creation/preflight use one canonical source instead of
    reading navigation_path_var directly in many places.
    """
    stale: list[str] = []
    for raw in _candidate_values(app):
        candidate = Path(raw).expanduser()
        try:
            if candidate.exists() and candidate.is_file() and candidate.suffix.lower() in PRIMARY_DOCUMENT_SUFFIXES:
                sync_selected_primary_document_path(app, candidate)
                return candidate
        except Exception as exc:
            record_soft_exception("medical_primary_document_state.exists", exc, detail=str(candidate))
        stale.append(str(candidate))
    if stale:
        try:
            setattr(app, "_last_missing_primary_document_path", stale[0])
        except Exception as exc:
            record_soft_exception("medical_primary_document_state.store_stale", exc)
    return None


def sync_selected_primary_document_path(app: Any, path: str | Path) -> str:
    """Persist one selected primary source into all UI/runtime holders."""
    value = clean_primary_document_path(path)
    if not value:
        return ""
    try:
        candidate = Path(value).expanduser()
        # Keep the user's Windows spelling; resolve only when safe.
        try:
            value = str(candidate.resolve()) if candidate.exists() else str(candidate)
        except Exception as exc:
            record_soft_exception("medical_primary_document_state.resolve", exc, detail=str(candidate))
            value = str(candidate)
    except Exception as exc:
        record_soft_exception("medical_primary_document_state.path_normalize", exc, detail=value)
    try:
        setattr(app, "_last_primary_document_path", value)
        setattr(app, "_active_primary_document_path", value)
    except Exception as exc:
        record_soft_exception("medical_primary_document_state.set_attr", exc)
    try:
        var = getattr(app, "navigation_path_var", None)
        if var is not None and hasattr(var, "get") and clean_primary_document_path(var.get()) != value:
            var.set(value)
    except Exception as exc:
        record_soft_exception("medical_primary_document_state.set_navigation", exc, detail=value)
    try:
        refresh = getattr(app, "_set_primary_drop_selected", None)
        if callable(refresh):
            refresh(value)
    except Exception as exc:
        record_soft_exception("medical_primary_document_state.refresh_drop", exc, detail=value)
    return value


def clear_selected_primary_document_path(app: Any) -> None:
    """Clear visual/runtime primary source after a truly missing source is detected."""
    try:
        setattr(app, "_last_primary_document_path", "")
        setattr(app, "_active_primary_document_path", "")
    except Exception as exc:
        record_soft_exception("medical_primary_document_state.clear_attr", exc)
    try:
        var = getattr(app, "navigation_path_var", None)
        if var is not None and hasattr(var, "set"):
            var.set("")
    except Exception as exc:
        record_soft_exception("medical_primary_document_state.clear_var", exc)
    try:
        empty = getattr(app, "_set_primary_drop_empty", None)
        if callable(empty):
            empty()
    except Exception as exc:
        record_soft_exception("medical_primary_document_state.clear_drop", exc)

def selected_primary_document_path_text(app: Any) -> str:
    """Return the current selected primary DOCX/DOCM as text or an empty string.

    Use this in dialog/action code instead of reading ``navigation_path_var``
    directly.  It preserves the single-source-of-truth contract introduced for
    block 01: visible UI state, runtime attributes and creation flows must agree
    about the selected primary document.
    """
    path = selected_primary_document_path(app)
    return str(path) if path is not None else ""

