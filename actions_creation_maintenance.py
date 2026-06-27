from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from tkinter import messagebox

from app_config import ACCENT_2, APP_VERSION, DEEP, FIELD, MUTED, PANEL, PANEL_3, TEXT
from diagnostic_logging import record_soft_exception

class ActionsCreationMaintenanceMixin:

    def configure_patient_folder_naming_dialog(self) -> None:
        """Ask how patient folders should be named and save the rule."""
        try:
            import tkinter as tk
            from app_config import DEEP, PANEL, FIELD, TEXT, MUTED, ACCENT_2, PANEL_3
            from desktop_patient_folder import (
                build_patient_folder_name,
                folder_naming_option_labels,
                normalize_folder_naming_settings,
            )

            current = normalize_folder_naming_settings(self._settings.get("folder_naming", {}))
            result = {"saved": False}
            win = tk.Toplevel(self.root)
            win.title("Как называть сохранённую папку?")
            win.configure(bg=DEEP)
            win.geometry("620x620")
            win.grid_columnconfigure(0, weight=1)
            tk.Label(
                win,
                text="Как называть сохранённую папку?",
                bg=DEEP,
                fg=TEXT,
                font=self._font(14, "bold"),
                padx=14,
                pady=0,
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", pady=(14, 4))
            tk.Label(
                win,
                text="Поставьте галочки — программа будет комбинировать выбранные части. Ниже сразу видно пример имени папки.",
                bg=DEEP,
                fg=MUTED,
                font=self._font(10),
                padx=14,
                pady=0,
                anchor="w",
                wraplength=570,
                justify="left",
            ).grid(row=1, column=0, sticky="ew", pady=(0, 8))
            body = tk.Frame(win, bg=PANEL, padx=14, pady=14)
            body.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 12))
            body.grid_columnconfigure(0, weight=1)
            vars_by_key: dict[str, tk.BooleanVar] = {}
            for row, (key, label) in enumerate(folder_naming_option_labels()):
                var = tk.BooleanVar(value=key in current["parts"])
                vars_by_key[key] = var
                tk.Checkbutton(
                    body,
                    text=label,
                    variable=var,
                    bg=PANEL,
                    fg=TEXT,
                    selectcolor=FIELD,
                    activebackground=PANEL,
                    activeforeground=TEXT,
                    font=self._font(10),
                    anchor="w",
                    command=lambda: update_preview(),
                ).grid(row=row, column=0, sticky="ew", pady=2)
            date_format_var = tk.StringVar(value=current.get("date_format", "short"))
            fmt_frame = tk.Frame(body, bg=PANEL)
            fmt_frame.grid(row=len(vars_by_key), column=0, sticky="ew", pady=(12, 4))
            fmt_frame.grid_columnconfigure(1, weight=1)
            tk.Label(fmt_frame, text="Формат дат:", bg=PANEL, fg=TEXT, font=self._font(10, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 10))
            tk.Radiobutton(fmt_frame, text="06.06.26", value="short", variable=date_format_var, bg=PANEL, fg=TEXT, selectcolor=FIELD, activebackground=PANEL, command=lambda: update_preview()).grid(row=0, column=1, sticky="w")
            tk.Radiobutton(fmt_frame, text="06.06.2026", value="long", variable=date_format_var, bg=PANEL, fg=TEXT, selectcolor=FIELD, activebackground=PANEL, command=lambda: update_preview()).grid(row=0, column=2, sticky="w")
            preview_var = tk.StringVar()
            tk.Label(body, text="Пример:", bg=PANEL, fg=MUTED, font=self._font(9, "bold"), anchor="w").grid(row=len(vars_by_key)+1, column=0, sticky="ew", pady=(12, 2))
            tk.Label(body, textvariable=preview_var, bg=FIELD, fg=ACCENT_2, font=self._font(11, "bold"), anchor="w", padx=10, pady=9).grid(row=len(vars_by_key)+2, column=0, sticky="ew")

            def current_payload() -> dict:
                return {
                    "parts": [key for key, _label in folder_naming_option_labels() if vars_by_key[key].get()],
                    "date_format": date_format_var.get(),
                }

            def update_preview() -> None:
                payload = current_payload()
                preview = build_patient_folder_name(
                    fio="Иванов Иван Иванович",
                    admission_date="05.05.2026",
                    discharge_date="06.06.2026",
                    settings=payload,
                    fallback="Иванов Иван Иванович",
                )
                preview_var.set(preview or "Иванов И.И. май 2026")

            def save() -> None:
                payload = normalize_folder_naming_settings(current_payload())
                payload["doctor_confirmed"] = True
                self._save_folder_naming_settings(payload)
                self._set_status("Настройка имени папки пациента сохранена")
                result["saved"] = True
                win.destroy()
                if not os.environ.get("CI"):
                    messagebox.showinfo("Папка пациента", "Сохранено. Новые документы будут складываться в папку по этому правилу.")

            buttons = tk.Frame(win, bg=DEEP)
            buttons.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 14))
            buttons.grid_columnconfigure(0, weight=1)
            tk.Button(buttons, text="Сохранить", command=save, bg=ACCENT_2, fg="#03101f", relief="flat", padx=18, pady=8, font=self._font(10, "bold")).grid(row=0, column=1, sticky="e", padx=(0, 8))
            tk.Button(buttons, text="Отмена", command=win.destroy, bg=PANEL_3, fg=TEXT, relief="flat", padx=18, pady=8, font=self._font(9)).grid(row=0, column=2, sticky="e")
            update_preview()
            win.transient(self.root)
            win.grab_set()
            self.root.wait_window(win)
            return bool(result["saved"])
        except Exception as exc:
            record_soft_exception("actions_creation_orchestrator.folder_naming", exc)
            messagebox.showerror("Папка пациента", f"Не удалось открыть настройку папки:\n{exc}")
            return False

    def _ensure_patient_folder_naming_configured(self) -> bool:
        """Ask once how patient subfolders should be named before generation."""
        from desktop_patient_folder import FOLDER_NAMING_SCHEMA_VERSION, normalize_folder_naming_settings

        current = normalize_folder_naming_settings(self._settings.get("folder_naming", {}))
        if current.get("doctor_confirmed") and current.get("schema_version") == FOLDER_NAMING_SCHEMA_VERSION:
            return True
        if os.environ.get("CI"):
            current["doctor_confirmed"] = True
            self._save_folder_naming_settings(current)
            return True
        return bool(self.configure_patient_folder_naming_dialog())

    def show_template_status_dialog(self) -> None:
        """Show doctor-owned template status instead of built-in templates."""
        try:
            pack = self._load_or_create_universal_pack()
            from universal_main_documents import custom_documents_for_main_ui

            docs = custom_documents_for_main_ui(pack, base_dir=self._universal_profile_path().parent)
            rows: list[str] = ["СВОИ ШАБЛОНЫ ВРАЧА", ""]
            if not docs:
                rows.append("Пока нет ни одного документа врача.")
                rows.append("Нажмите «Свои шаблоны» / «+ Добавить шаблоны» и выберите Word-файлы доктора.")
            else:
                for doc in docs:
                    rows.append(f"✅ {doc.label}: {Path(doc.template).name}")
            rows.append("")
            rows.append("Встроенных медицинских шаблонов в пользовательском сценарии нет: каждый доктор загружает свои DOCX/DOCM.")
            message = "\n".join(rows)
            if os.environ.get("CI"):
                self._log("\n" + message + "\n")
            else:
                messagebox.showinfo("Свои шаблоны", message)
        except Exception as exc:
            record_soft_exception("actions_creation_orchestrator.template_status", exc)
            messagebox.showerror("Свои шаблоны", f"Не удалось проверить шаблоны:\n{exc}")

    def reset_settings_dialog(self) -> None:
        """UI action: backup and reset safe technical settings."""
        if not os.environ.get("CI"):
            if not messagebox.askyesno(
                "Сброс настроек",
                "Сбросить технические настройки программы?\n\n"
                "Будут очищены выбранный принтер, сохранённые папки диалогов и служебные настройки.\n"
                "Перед сбросом будет создан backup settings.backup.json.\n\n"
                "Файлы пациентов и созданные документы не трогаются.",
            ):
                return
        ok = self.reset_settings_to_defaults()
        if ok:
            self._set_status("Настройки сброшены")
            if not os.environ.get("CI"):
                messagebox.showinfo("Настройки", "Настройки сброшены. Backup сохранён рядом с settings.json.")
        else:
            messagebox.showerror("Настройки", "Не удалось сбросить настройки. Подробности записаны в диагностику.")

    def _version_tuple_for_compare(self, value: str) -> tuple[int, int, int]:
        match = re.search(r"(\d+)\.(\d+)\.(\d+)", str(value or ""))
        if not match:
            return (0, 0, 0)
        return tuple(int(part) for part in match.groups())  # type: ignore[return-value]

    def _candidate_update_manifests(self) -> list[str]:
        candidates: list[str] = []
        env_value = os.environ.get("MEDICAL_AUTOFILL_UPDATE_MANIFEST", "").strip()
        if env_value:
            candidates.append(env_value)
        try:
            configured = str(self._settings.get("update_manifest", "") or "").strip()
            if configured:
                candidates.append(configured)
        except Exception as exc:
            record_soft_exception("actions_creation_orchestrator.update_manifest_setting", exc)
        root = Path(__file__).resolve().parent
        candidates.extend(str(root / name) for name in ("update_manifest.json", "medical_autofill_update.json"))
        return list(dict.fromkeys(candidates))

    def _read_update_manifest(self) -> tuple[dict, str] | tuple[None, str]:
        errors: list[str] = []
        max_bytes = 1024 * 1024
        for candidate in self._candidate_update_manifests():
            try:
                if candidate.lower().startswith(("http://", "https://")):
                    with urllib.request.urlopen(candidate, timeout=5) as response:  # nosec: optional user-configured manifest URL
                        raw_bytes = response.read(max_bytes + 1)
                    if len(raw_bytes) > max_bytes:
                        raise ValueError("манифест обновлений больше 1 МБ")
                    raw = raw_bytes.decode("utf-8-sig")
                    data = json.loads(raw)
                else:
                    path = Path(candidate).expanduser()
                    if not path.exists():
                        continue
                    if not path.is_file():
                        raise ValueError("это не файл")
                    if path.stat().st_size > max_bytes:
                        raise ValueError("манифест обновлений больше 1 МБ")
                    data = json.loads(path.read_text(encoding="utf-8-sig"))
                    candidate = str(path)
                if not isinstance(data, dict):
                    raise ValueError("манифест обновлений должен быть JSON-объектом")
                return data, candidate
            except Exception as exc:
                errors.append(f"{candidate}: {exc}")
        if errors:
            return None, "\n".join(errors)
        return None, ""

    def check_updates_dialog(self) -> None:
        """Check a local/remote update manifest and explain the result to the doctor."""
        try:
            manifest, source = self._read_update_manifest()
            if not manifest:
                checked = "\n".join("• " + item for item in self._candidate_update_manifests())
                text = (
                    f"Текущая версия: {APP_VERSION}\n\n"
                    "Манифест обновлений не найден.\n\n"
                    "Программа уже умеет проверять обновление по JSON-манифесту. "
                    "Для рабочей продажи положите рядом с программой файл update_manifest.json "
                    "или задайте переменную MEDICAL_AUTOFILL_UPDATE_MANIFEST с путём/URL.\n\n"
                    "Проверенные места:\n" + checked
                )
                if source:
                    text += "\n\nОшибки чтения:\n" + source
                messagebox.showinfo("Проверка обновлений", text)
                return
            latest = str(manifest.get("version") or manifest.get("latest_version") or "").strip()
            notes = str(manifest.get("notes") or manifest.get("release_notes") or "").strip()
            url = str(manifest.get("download_url") or manifest.get("url") or "").strip()
            if not latest:
                raise ValueError("В манифесте обновлений нет поля version/latest_version.")
            current_tuple = self._version_tuple_for_compare(APP_VERSION)
            latest_tuple = self._version_tuple_for_compare(latest)
            if latest_tuple > current_tuple:
                state = "Доступна новая версия."
            elif latest_tuple == current_tuple:
                state = "Установлена актуальная версия."
            else:
                state = "Установленная версия новее манифеста."
            text = f"{state}\n\nТекущая версия: {APP_VERSION}\nПоследняя версия: {latest}\nИсточник: {source}"
            if url:
                text += "\n\nГде скачать:\n" + url
            if notes:
                text += "\n\nЧто изменилось:\n" + notes[:1600]
            messagebox.showinfo("Проверка обновлений", text)
        except Exception as exc:
            record_soft_exception("actions_creation_orchestrator.check_updates", exc)
            messagebox.showerror("Проверка обновлений", f"Не удалось проверить обновления:\n{exc}")

