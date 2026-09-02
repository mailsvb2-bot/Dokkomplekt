"""Живая эмуляция врача: реальное Tk-приложение, реальные клики по виджетам.

Использование: импортировать DoctorSim, прогнать сценарий, получить журнал
попапов (метрика трения) и созданные файлы.
"""
from __future__ import annotations

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..")))

import json
import os
import shutil
import time
from pathlib import Path
from tempfile import mkdtemp

for _k in ("CI", "MEDICAL_AUTOFILL_DISABLE_AUTOSTART"):
    os.environ.pop(_k, None)

from docx import Document
import tkinter as tk
import tkinter.messagebox as mb
import tkinter.simpledialog as sd
import tkinter.filedialog as fd


def make_docx(path, lines):
    d = Document()
    for line in lines:
        d.add_paragraph(line)
    d.save(path)


class DoctorSim:
    def __init__(self, answers: dict | None = None):
        self.answers = answers or {}
        self.popups: list[tuple[str, str]] = []
        self.errors: list[str] = []
        self.root_dir = Path(mkdtemp())
        self.intake = self.root_dir / "Выписанные пациенты"
        self.intake.mkdir()
        # Live GUI emulation must never consume the developer's real trial or
        # reuse real source/AppData state.  This is test isolation, not a runtime
        # bypass: frozen builds ignore the test-disable flag.
        os.environ["DOKKOMPLEKT_TEST_DISABLE_PRODUCT_ACCESS"] = "1"
        os.environ["MEDICAL_AUTOFILL_PORTABLE_SOURCE_DATA"] = "0"
        os.environ["APPDATA"] = str(self.root_dir / "appdata")
        self.answers.setdefault(("askyesno", "Папка «Выписанные пациенты»"), False)
        self._patch_dialogs()
        # изолируем data root приложения
        import desktop_intake_agent as agent
        self._data_root = self.root_dir / ".data"
        agent._data_root = lambda: self._data_root

        from app import CombinedMedicalDiaryApp
        from desktop_patient_folder import (
            FOLDER_NAMING_SCHEMA_VERSION,
            normalize_folder_naming_settings,
        )

        sim = self

        def skip_folder_dialog(app_self):
            sim.popups.append(("dialog", "Имя папки пациента (авто-подтверждено)"))
            cur = normalize_folder_naming_settings(app_self._settings.get("folder_naming", {}))
            cur["doctor_confirmed"] = True
            cur["schema_version"] = FOLDER_NAMING_SCHEMA_VERSION
            app_self._save_folder_naming_settings(cur)
            return True

        def fake_fields(app_self, *, title, rows, width=28, linked_groups=None,
                        include_labs_block=False, date_field_keys=None):
            sim.popups.append(("fields", f"{title}: {[r[0] for r in rows]}"))
            out = []
            for r in rows:
                label = str(r[0])
                default = str(r[1]) if len(r) > 1 else ""
                out.append(str(sim.answers.get(("field", label), default)))
            return out

        def fake_confirm_case(app_self, review):
            sim.popups.append(("dialog", "Проверка перед созданием документов"))
            return True

        CombinedMedicalDiaryApp.configure_patient_folder_naming_dialog = skip_folder_dialog
        CombinedMedicalDiaryApp._prompt_fields = fake_fields
        CombinedMedicalDiaryApp._confirm_patient_case_before_creation = fake_confirm_case

        self.tk_root = tk.Tk()
        self.app = CombinedMedicalDiaryApp(self.tk_root)
        self.pump(0.2)

    # --- эмуляция диалогов ---
    def _patch_dialogs(self):
        sim = self

        def askstring(title, prompt, **kw):
            sim.popups.append(("askstring", title))
            return str(sim.answers.get(("askstring", title), "1"))

        def askyesno(title, message, **kw):
            sim.popups.append(("askyesno", title))
            return bool(sim.answers.get(("askyesno", title), True))

        def warn(title, message, **kw):
            sim.popups.append(("warning", f"{title}: {str(message)[:120]}"))

        def info(title, message, **kw):
            sim.popups.append(("info", title))

        def error(title, message, **kw):
            sim.popups.append(("ERROR", f"{title}: {str(message)[:200]}"))
            sim.errors.append(f"{title}: {message}")

        sd.askstring = askstring
        mb.askyesno = askyesno
        mb.showwarning = warn
        mb.showinfo = info
        mb.showerror = error
        fd.askopenfilenames = lambda **kw: tuple(sim.answers.get("openfilenames", ()))
        fd.askdirectory = lambda **kw: str(sim.answers.get("directory", sim.root_dir))

    # --- утилиты ---
    def pump(self, seconds: float = 0.5):
        end = time.time() + seconds
        while time.time() < end:
            self.tk_root.update()
            time.sleep(0.02)

    def drop(self, path):
        self.app._handle_dropped_files([str(path)])
        self.pump(0.3)

    def widgets(self, root=None):
        root = root or self.tk_root
        out = [root]
        for child in root.winfo_children():
            out.extend(self.widgets(child))
        return out

    def click_button(self, text_part, root=None):
        for w in self.widgets(root):
            if isinstance(w, tk.Button) and text_part in str(w.cget("text")):
                w.invoke()
                self.pump(0.3)
                return True
        return False

    def toggle_check(self, text_part, root=None):
        for w in self.widgets(root):
            if isinstance(w, tk.Checkbutton) and text_part in str(w.cget("text")):
                w.invoke()
                return True
        return False

    def toplevels(self):
        return [w for w in self.tk_root.winfo_children() if isinstance(w, tk.Toplevel)]

    def outputs(self):
        out = Path(self.app._result_output_dir())
        return sorted(p for p in out.rglob("*.docx"))

    def create_diaries(self):
        """Create diaries through the same block-03 selection transaction as a doctor."""
        from diary_constants import DIARY_KIND

        # A repeated patient run opens the real modal duplicate-policy Toplevel.
        # Drive that UI just like the doctor choosing the safe versioned output.
        def drive_duplicate_dialog(attempt=0):
            try:
                for top in self.toplevels():
                    if str(top.title()) == "Документы уже существуют":
                        self.popups.append(("dialog", "Документы уже существуют → Создать новую версию"))
                        self.click_button("Создать новую версию", top)
                        return
            except Exception:
                return
            if attempt < 80:
                self.tk_root.after(25, lambda: drive_duplicate_dialog(attempt + 1))

        if self.outputs():
            self.tk_root.after(25, drive_duplicate_dialog)
        diary_var = self.app.output_vars[DIARY_KIND]
        diary_var.set(True)
        self.app._on_output_toggle(DIARY_KIND)
        if diary_var.get():
            self.app.create_selected_outputs()
        self.pump(0.4)

    def close(self):
        try:
            closer = getattr(self.app, "_close_app_with_runtime_lock_release", None)
            if callable(closer):
                closer()
            else:
                self.tk_root.destroy()
        except Exception as exc:
            self.popups.append(("note", f"destroy: {exc}"))
        shutil.rmtree(self.root_dir, ignore_errors=True)
