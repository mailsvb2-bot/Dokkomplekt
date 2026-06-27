from __future__ import annotations

from diagnostic_logging import record_soft_exception

from printer_platform import is_windows

PRINTER_DISCOVERY_HAS_NO_SHELL_FALLBACK = True
PRINTER_DISCOVERY_IS_PYWIN32_ONLY = True


def list_printers() -> list[str]:
    """Return installed/local/network printer names without opening shell windows.

    Doctor-facing startup and desktop-intake flows must never launch external shell
    or a visible console merely to fill the printer combobox.  In production EXE
    builds pywin32 is bundled; in source/dev environments without pywin32 the UI
    shows an empty printer list and the user can still create documents without
    печати.
    """
    if not is_windows():
        return []

    names: list[str] = []
    try:
        import win32print  # type: ignore

        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        for printer in win32print.EnumPrinters(flags):
            # pywin32 usually returns tuples where index 2 is printer name.
            name = str(printer[2]).strip()
            if name and name not in names:
                names.append(name)
    except Exception as exc:
        record_soft_exception("printer_discovery.pywin32_list", exc)
        return []

    return sorted(names, key=str.lower)


def get_default_printer() -> str:
    """Return the default printer without external shell fallbacks."""
    if not is_windows():
        return ""
    try:
        import win32print  # type: ignore

        return str(win32print.GetDefaultPrinter()).strip()
    except Exception as exc:
        record_soft_exception("printer_discovery.pywin32_default", exc)
        return ""


def assert_printer_discovery_lock() -> None:
    if not PRINTER_DISCOVERY_HAS_NO_SHELL_FALLBACK:
        raise AssertionError("Printer discovery must not use external shell in doctor-facing flows")
    if not PRINTER_DISCOVERY_IS_PYWIN32_ONLY:
        raise AssertionError("Printer discovery must stay pywin32-only to avoid shell flashes")
