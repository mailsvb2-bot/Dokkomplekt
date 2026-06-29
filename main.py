"""Entry point for MedicalDiaryAutofill.

The large Tkinter controller is intentionally split into focused modules:
configuration, reusable UI components, settings persistence, dialogs, file input,
numbered diary-template discovery, drag-and-drop, and creation actions.
``main.py`` stays small so the executable entry point remains stable.
"""

from __future__ import annotations

import json
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


def _check_native_license_core() -> int:
    """CLI/EXE diagnostic that stays GUI-free and checks packaged Rust verifier."""
    result = {
        "check": "native_license_core",
        "module": "dokkomplekt_license_native",
        "ok": False,
        "version": None,
        "functions": {},
        "error": None,
    }
    try:
        import dokkomplekt_license_native as native

        version = native.native_core_version()
        functions = {
            "native_core_version": callable(getattr(native, "native_core_version", None)),
            "license_plan": callable(getattr(native, "license_plan", None)),
            "proof_ok": callable(getattr(native, "proof_ok", None)),
            "access_decision": callable(getattr(native, "access_decision", None)),
        }
        result["version"] = str(version)
        result["functions"] = functions
        result["ok"] = version == "0.1.0" and all(functions.values())
    except Exception as exc:  # pragma: no cover - used by packaged EXE smoke
        result["error"] = repr(exc)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


def main() -> None:
    # Background and diagnostic modes must stay GUI-free: check them before importing Tk/app.
    # This keeps Windows autostart lighter and avoids hidden GUI dependency failures when
    # launched by pythonw.exe or the packaged EXE.
    if "--check-native-license-core" in sys.argv:
        raise SystemExit(_check_native_license_core())

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
