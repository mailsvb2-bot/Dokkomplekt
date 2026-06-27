"""Entry point for MedicalDiaryAutofill.

The large Tkinter controller is intentionally split into focused modules:
configuration, reusable UI components, settings persistence, dialogs, file input,
numbered diary-template discovery, drag-and-drop, and creation actions.
``main.py`` stays small so the executable entry point remains stable.
"""

from __future__ import annotations

import sys
import traceback


def __getattr__(name: str):
    """Expose legacy smoke imports lazily without heavy startup imports."""
    if name == "CombinedMedicalDiaryApp":
        from app import CombinedMedicalDiaryApp

        return CombinedMedicalDiaryApp
    try:
        import app_config

        return getattr(app_config, name)
    except AttributeError as exc:
        raise AttributeError(name) from exc


def main() -> None:
    # Background mode must stay GUI-free: check it before importing Tk/app.
    # This keeps Windows autostart lighter and avoids hidden GUI dependency
    # failures when the watcher is launched by pythonw.exe or the packaged EXE.
    if "--install-intake-agent" in sys.argv:
        from desktop_intake_agent import install_agent_autostart

        ok, message = install_agent_autostart(start_now=True)
        print(message)
        raise SystemExit(0 if ok else 1)

    if "--intake-agent" in sys.argv:
        from desktop_intake_agent import run_forever

        run_forever()
        return

    from diagnostic_logging import record_soft_exception
    from tkinter import messagebox
    from app import CombinedMedicalDiaryApp
    from startup import _create_root, _startup_log_path, _write_startup_error

    try:
        root = _create_root()
        CombinedMedicalDiaryApp(root)
        root.mainloop()
    except Exception as exc:  # pragma: no cover - safety net for Windows double-click start
        details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        _write_startup_error(details)
        try:
            messagebox.showerror(
                "Ошибка запуска",
                f"Программа не запустилась. Подробности записаны в файл:\n{_startup_log_path()}\n\n{exc}",
            )
        except Exception as dialog_exc:
            record_soft_exception("main.startup_error_dialog", dialog_exc)
        raise


if __name__ == "__main__":
    main()
