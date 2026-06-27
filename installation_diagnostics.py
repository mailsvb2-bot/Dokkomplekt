"""Doctor-facing installation self-check for Windows/portable builds.

The diagnostic intentionally stays stdlib-only and keeps patient data out of the
report.  It answers the practical support question: why does nothing happen when
an intake DOCX is dropped into ``Выписанные пациенты``?
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import sys
from typing import Iterable

from diagnostic_logging import record_soft_exception

INSTALLATION_DIAGNOSTICS_LOCK_VERSION = "v1.0"


@dataclass(frozen=True)
class DiagnosticRow:
    """One doctor-readable self-check row."""

    name: str
    ok: bool
    value: str
    advice: str = ""

    def line(self) -> str:
        icon = "✅" if self.ok else "⚠"
        suffix = f" — {self.advice}" if self.advice else ""
        return f"{icon} {self.name}: {self.value}{suffix}"


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _data_root() -> Path:
    if getattr(sys, "frozen", False):
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home()
        return root / "MedicalDiaryAutofill"
    return _app_root() / ".medical_diary_autofill_data"


def _startup_dir() -> Path | None:
    if os.name != "nt":
        return None
    startup = os.environ.get("APPDATA")
    if not startup:
        return None
    return Path(startup) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _startup_autostart_paths() -> tuple[Path, Path] | tuple[()]:
    folder = _startup_dir()
    if folder is None:
        return ()
    return (
        folder / "MedicalDiaryAutofill Intake Agent.vbs",
        folder / "MedicalDiaryAutofill Intake Agent.lnk",
    )


def _safe_exists(path: Path | None) -> bool:
    try:
        return bool(path and path.exists())
    except Exception as exc:
        record_soft_exception("installation_diagnostics.exists", exc, detail=str(path))
        return False


def _safe_text_tail(path: Path, *, limit: int = 1200) -> str:
    try:
        if not path.exists() or not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[-limit:].strip()
    except Exception as exc:
        record_soft_exception("installation_diagnostics.tail", exc, detail=str(path))
        return ""


def _has_word_or_docx_opener() -> bool:
    if os.name == "nt":
        # Windows shell association is the normal route; winword.exe in PATH is
        # a bonus, not a requirement.
        return True
    return bool(shutil.which("libreoffice") or shutil.which("soffice") or shutil.which("open") or shutil.which("xdg-open"))


def _doctor_button_count(app: object | None) -> int:
    try:
        if app is None:
            return 0
        from layout_checklist import _doctor_buttons_setup_completed
        from universal_main_documents import custom_documents_for_main_ui
        pack = app._load_or_create_universal_pack() if hasattr(app, "_load_or_create_universal_pack") else None
        if pack is None or not _doctor_buttons_setup_completed(pack):
            return 0
        return len(custom_documents_for_main_ui(pack, base_dir=app._universal_profile_path().parent if hasattr(app, "_universal_profile_path") else None))
    except Exception as exc:
        record_soft_exception("installation_diagnostics.button_count", exc)
        return 0


def collect_installation_diagnostics(app: object | None = None) -> list[DiagnosticRow]:
    """Collect actionable installation diagnostics without importing Tk."""

    rows: list[DiagnosticRow] = []
    root = _app_root()
    data = _data_root()
    rows.append(DiagnosticRow("Папка программы", root.exists(), str(root), "проверьте распаковку архива" if not root.exists() else ""))
    rows.append(DiagnosticRow("Папка настроек", data.exists(), str(data), "запустите программу один раз" if not data.exists() else ""))

    try:
        from desktop_intake import default_intake_folder, is_desktop_intake_folder_path

        intake = default_intake_folder()
        rows.append(
            DiagnosticRow(
                "Папка «Выписанные пациенты»",
                intake.exists() and intake.is_dir() and is_desktop_intake_folder_path(intake),
                str(intake),
                "создайте папку через первый запуск программы" if not intake.exists() else "",
            )
        )
    except Exception as exc:
        record_soft_exception("installation_diagnostics.intake_folder", exc)
        rows.append(DiagnosticRow("Папка «Выписанные пациенты»", False, "не удалось проверить", "откройте настройки первого запуска"))

    autostart_paths = _startup_autostart_paths()
    if os.name == "nt":
        existing_autostart = [path for path in autostart_paths if _safe_exists(path)]
        value = ", ".join(str(path) for path in existing_autostart) if existing_autostart else "не найден"
        rows.append(DiagnosticRow("Автозагрузка watcher", bool(existing_autostart), value, "переустановите watcher из программы" if not existing_autostart else ""))
    else:
        rows.append(DiagnosticRow("Автозагрузка watcher", True, "не Windows-среда", "боевой тест нужен на Windows"))

    lock = data / "desktop_intake_agent.lock"
    log = data / "desktop_intake_agent.log"
    lock_ok = lock.exists()
    lock_value = str(lock) if lock_ok else "нет активного lock"
    try:
        if lock_ok:
            age = max(0, int(__import__("time").time() - lock.stat().st_mtime))
            lock_value = f"{lock} (обновлён {age} сек назад)"
            if age > 180:
                lock_ok = False
                lock_value += "; похоже, stale-lock"
    except Exception as exc:
        record_soft_exception("installation_diagnostics.lock_age", exc, detail=str(lock))
    rows.append(DiagnosticRow("Watcher lock", lock_ok, lock_value, "перезапустите программу, чтобы watcher переустановился" if not lock_ok else ""))
    rows.append(DiagnosticRow("Watcher log", log.exists(), str(log) if log.exists() else "лог пока не создан", "перенесите тестовый DOCX в папку" if not log.exists() else ""))
    tail = _safe_text_tail(log, limit=500)
    if tail:
        rows.append(DiagnosticRow("Последние строки watcher", True, tail.replace("\n", " | ")))

    rows.append(DiagnosticRow("Открытие DOCX", _has_word_or_docx_opener(), "системная ассоциация/Word/LibreOffice", "установите Word или LibreOffice" if not _has_word_or_docx_opener() else ""))
    count = _doctor_button_count(app)
    rows.append(DiagnosticRow("Кнопки документов блока 03", count > 0, f"{count} активных", "создайте кнопки документов в центре шаблонов" if count <= 0 else ""))

    try:
        diary_texts = bool(getattr(app, "status_files", None) or getattr(app, "diary_texts_dir", "")) if app is not None else False
        diary_dates = bool(getattr(app, "diary_files", None) or getattr(app, "diary_template_dir", "")) if app is not None else False
        rows.append(DiagnosticRow("Дневники — тексты", diary_texts, "выбраны/папка задана" if diary_texts else "не выбраны", "нажмите «Тексты» во втором блоке" if not diary_texts else ""))
        rows.append(DiagnosticRow("Дневники — даты", diary_dates, "выбраны/папка задана" if diary_dates else "не выбраны", "нажмите «Даты» во втором блоке" if not diary_dates else ""))
    except Exception as exc:
        record_soft_exception("installation_diagnostics.diary_state", exc)

    return rows


def render_installation_diagnostics(rows: Iterable[DiagnosticRow]) -> str:
    """Render self-check rows as a compact support report."""

    lines = ["ПРОВЕРКА УСТАНОВКИ MEDICALDIARYAUTOFILL", ""]
    for row in rows:
        lines.append(row.line())
    lines.extend([
        "",
        "Если есть ⚠ — исправьте верхний пункт и повторите проверку.",
        "Боевой тест Windows: закрыть программу → перенести DOCX в «Выписанные пациенты» → программа должна открыться сама.",
    ])
    return "\n".join(lines)


def show_installation_diagnostics(app: object) -> None:
    """Show the doctor-facing self-check window from the main UI."""

    try:
        from tkinter import messagebox

        text = render_installation_diagnostics(collect_installation_diagnostics(app))
        messagebox.showinfo("Проверить программу", text)
        try:
            if hasattr(app, "_set_status"):
                app._set_status("Проверка программы завершена")
        except Exception as status_exc:
            record_soft_exception("installation_diagnostics.status", status_exc)
    except Exception as exc:
        record_soft_exception("installation_diagnostics.show", exc)


def assert_installation_diagnostics_lock() -> None:
    if INSTALLATION_DIAGNOSTICS_LOCK_VERSION != "v1.0":
        raise AssertionError("Installation diagnostics lock changed unexpectedly")
    rows = collect_installation_diagnostics(None)
    if len(rows) < 6:
        raise AssertionError("Installation diagnostics must return actionable rows")
