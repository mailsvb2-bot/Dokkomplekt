from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

from app_config import ACCENT_2, DEEP, FIELD, PANEL_3, TEXT, WARN
from diagnostic_logging import record_soft_exception
from medical_date_state import current_semantic_date
from medical_formatting import safe_filename
from medical_models import expected_medical_filenames

class ActionsCreationFolderingMixin:

    def _existing_medical_targets(self, review, selected_medical: list[str]) -> list[Path]:
        out_dir = Path(review.output_dir or self._result_output_dir()).expanduser()
        names = expected_medical_filenames(review, selected_medical)
        existing: list[Path] = []
        for name in names:
            direct = out_dir / name
            if direct.exists():
                existing.append(direct)
            base = direct.with_suffix("")
            for candidate in out_dir.glob(base.name + " (*).docx"):
                if candidate.exists():
                    existing.append(candidate)
        return existing

    def _versioned_output_dir(self, out_dir: Path, patient_stem: str) -> Path:
        date_part = datetime.now().strftime("%Y-%m-%d")
        base = out_dir / f"{safe_filename(patient_stem)}_{date_part}_версия"
        for counter in range(2, 10000):
            candidate = Path(f"{base}_{counter}")
            if not candidate.exists():
                candidate.mkdir(parents=True, exist_ok=False)
                return candidate
        raise RuntimeError("Не удалось создать версионную папку пациента.")

    def _prompt_duplicate_policy(self, existing: list[Path]) -> str:
        if not existing:
            return "none"
        if os.environ.get("CI"):
            return "version"
        try:
            import tkinter as tk
            from app_config import PANEL, FIELD, TEXT, MUTED, WARN, ACCENT_2, PANEL_3, DEEP
            win = tk.Toplevel(self.root)
            win.title("Документы уже существуют")
            win.configure(bg=DEEP)
            win.geometry("720x420")
            win.grid_columnconfigure(0, weight=1)
            result = {"policy": "cancel"}
            tk.Label(win, text="Для этого пациента уже есть созданные документы", bg=DEEP, fg=WARN, font=self._font(13, "bold"), padx=14, pady=10, anchor="w").grid(row=0, column=0, sticky="ew")
            msg = "Найдены файлы:\n" + "\n".join(f"- {p.name}" for p in existing[:12])
            if len(existing) > 12:
                msg += f"\n… ещё {len(existing) - 12}"
            box = tk.Text(win, bg=FIELD, fg=TEXT, relief="flat", wrap="word", font=self._font(10), padx=10, pady=10, height=10)
            box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
            box.insert("end", msg)
            box.configure(state="disabled")
            win.grid_rowconfigure(1, weight=1)
            buttons = tk.Frame(win, bg=DEEP)
            buttons.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
            for col in range(4):
                buttons.grid_columnconfigure(col, weight=1)
            def choose(policy):
                result["policy"] = policy
                win.destroy()
            tk.Button(buttons, text="Открыть папку", command=lambda: choose("open"), bg=PANEL_3, fg=TEXT, relief="flat", padx=10, pady=8, font=self._font(9, "bold")).grid(row=0, column=0, sticky="ew", padx=(0, 6))
            tk.Button(buttons, text="Создать новую версию", command=lambda: choose("version"), bg=ACCENT_2, fg="#03101f", relief="flat", padx=10, pady=8, font=self._font(9, "bold")).grid(row=0, column=1, sticky="ew", padx=6)
            tk.Button(buttons, text="Перезаписать", command=lambda: choose("overwrite"), bg=PANEL_3, fg=TEXT, relief="flat", padx=10, pady=8, font=self._font(9, "bold")).grid(row=0, column=2, sticky="ew", padx=6)
            tk.Button(buttons, text="Отмена", command=lambda: choose("cancel"), bg=FIELD, fg=TEXT, relief="flat", padx=10, pady=8, font=self._font(9)).grid(row=0, column=3, sticky="ew", padx=(6, 0))
            win.transient(self.root)
            win.grab_set()
            self.root.wait_window(win)
            return str(result["policy"])
        except Exception as exc:
            record_soft_exception("actions_creation_orchestrator.duplicate_policy", exc)
            return "version" if messagebox.askyesno("Документы уже существуют", "Создать новую версию, чтобы не перезаписать старые документы?") else "cancel"


    def _backup_existing_output_file(self, path: Path) -> Path:
        """Rename an existing result file before overwrite instead of deleting it."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        base = path.with_name(f"{path.stem}_backup_{timestamp}{path.suffix}")
        candidate = base
        counter = 2
        while candidate.exists():
            candidate = path.with_name(f"{path.stem}_backup_{timestamp}_{counter}{path.suffix}")
            counter += 1
        path.rename(candidate)
        return candidate

    def _apply_duplicate_policy(self, review, selected_medical: list[str]) -> bool:
        existing = self._existing_medical_targets(review, selected_medical)
        if not existing:
            return True
        policy = self._prompt_duplicate_policy(existing)
        if policy == "open":
            self._open_result_folder_silent(existing[0].parent)
            return False
        if policy == "cancel":
            return False
        if policy == "version":
            new_dir = self._versioned_output_dir(Path(review.output_dir or self._result_output_dir()), review.patient_stem())
            self._set_output_dir_auto_patient_scoped(new_dir)
            return True
        if policy == "overwrite":
            for path in existing:
                try:
                    self._backup_existing_output_file(path)
                except Exception as exc:
                    record_soft_exception("actions_creation_orchestrator.overwrite_existing", exc, detail=str(path))
                    messagebox.showerror("Не удалось перезаписать", f"Не удалось создать резервную копию старого файла:\n{path}")
                    return False
            return True
        return False

    def _folder_naming_settings(self) -> dict:
        from desktop_patient_folder import normalize_folder_naming_settings

        raw = self._settings.get("folder_naming") if isinstance(getattr(self, "_settings", None), dict) else {}
        return normalize_folder_naming_settings(raw)

    def _save_folder_naming_settings(self, settings: dict) -> None:
        from desktop_patient_folder import normalize_folder_naming_settings

        normalized = normalize_folder_naming_settings(settings)
        if isinstance(settings, dict) and settings.get("doctor_confirmed"):
            normalized["doctor_confirmed"] = True
        self._settings["folder_naming"] = normalized
        self._save_settings()

    def _patient_output_dir_for_data(self, data, *, base_dir: Path | None = None) -> Path:
        from desktop_patient_folder import build_patient_folder_name

        root = Path(base_dir or self._base_output_dir()).expanduser()
        # Desktop intake has already created the exact patient folder inside
        # «Выписанные пациенты» and moved the primary file there. Do not create
        # a second nested patient folder during preflight/review.
        if getattr(self, "_output_dir_auto_locked_to_patient", False):
            return root
        name = build_patient_folder_name(
            fio=getattr(data, "output_fio", "") or getattr(data, "fio", ""),
            admission_date=getattr(data, "admission_date", ""),
            discharge_date=getattr(data, "discharge_date", "") or current_semantic_date(self, "discharge_date"),
            settings=self._folder_naming_settings(),
            fallback=getattr(data, "output_fio", "") or getattr(data, "fio", "") or "Пациент",
        )
        return root / (name or "Пациент")

