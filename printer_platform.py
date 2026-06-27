from __future__ import annotations

from diagnostic_logging import record_soft_exception
import os
from pathlib import Path
import platform
import subprocess
import sys

WINDOWS_SUBPROCESS_DEFAULT_CREATIONFLAGS_NO_WINDOW = True


def is_windows() -> bool:
    return platform.system().lower().startswith("win")


def _startupinfo():
    if not is_windows():
        return None
    try:
        info = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
        info.wShowWindow = 0
        return info
    except Exception as exc:
        record_soft_exception("printer_platform.startupinfo", exc)
        return None


def _creationflags_no_window() -> int:
    if not is_windows():
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def can_open_desktop_path() -> bool:
    """Return whether opening a file/folder can be done without a console popup.

    Windows uses ShellExecute via ``os.startfile``; macOS/Linux use direct argv
    subprocesses with no shell.  Linux headless/source tests deliberately return
    False so ``xdg-open`` does not create noisy errors.
    """
    if os.environ.get("CI"):
        return False
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def open_desktop_path(path: str | Path, *, require_dir: bool = False, require_file: bool = False) -> bool:
    """Open a desktop file/folder through one audited no-shell boundary.

    Scattered ``os.startfile``/``subprocess.Popen`` calls easily regress into
    PowerShell/cmd windows on Windows.  All user-visible open-folder/open-DOCX
    flows should go through this helper.
    """
    candidate = Path(path).expanduser()
    try:
        if not can_open_desktop_path() or not candidate.exists():
            return False
        if require_dir and not candidate.is_dir():
            return False
        if require_file and not candidate.is_file():
            return False
        text = str(candidate)
        if sys.platform.startswith("win"):
            os.startfile(text)  # type: ignore[attr-defined]
            return True
        if sys.platform == "darwin":
            command = ["open", text]
        else:
            command = ["xdg-open", text]
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
            startupinfo=_startupinfo(),
            creationflags=_creationflags_no_window(),
        )
        return True
    except Exception as exc:
        record_soft_exception("printer_platform.open_desktop_path", exc, detail=str(candidate))
        return False
