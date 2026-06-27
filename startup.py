from __future__ import annotations

from diagnostic_logging import record_soft_exception
import traceback
from pathlib import Path
import tkinter as tk

from app_config import APP_TITLE

def _startup_log_path() -> Path:
    try:
        return Path(__file__).resolve().parent / "startup_error.log"
    except Exception as exc:
        record_soft_exception("startup.log_path", exc)
        return Path.cwd() / "startup_error.log"

def _write_startup_error(details: str) -> None:
    try:
        _startup_log_path().write_text(details, encoding="utf-8")
    except Exception as exc:
        record_soft_exception("startup:18", exc)

def _create_root():
    """Создать root без падения, даже если drag/drop-библиотека не установлена."""
    try:
        from tkinterdnd2 import TkinterDnD  # type: ignore
        return TkinterDnD.Tk()
    except Exception as exc:
        record_soft_exception("startup.tkinterdnd_fallback", exc)
        return tk.Tk()

