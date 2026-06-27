from __future__ import annotations

from diagnostic_logging import record_soft_exception
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path




def _setting_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"", "0", "false", "no", "off", "нет", "не", "n", "disabled", "disable"}:
            return False
        if lowered in {"1", "true", "yes", "on", "да", "y", "enabled", "enable"}:
            return True
    return bool(value)


def _env_flag_disabled(value: object) -> bool:
    lowered = str(value or "").strip().casefold()
    return lowered in {"0", "false", "no", "off", "нет", "disable", "disabled"}


def _source_portable_data_root() -> Path | None:
    """Return an isolated data root for source/portable runs.

    Doctors must keep their buttons across installed EXE updates, so frozen
    builds continue to use %APPDATA%/MedicalDiaryAutofill.  Source archives,
    however, are often unpacked as fresh test builds.  If they read the shared
    AppData profile, an old default_custom.medpack.json can make a supposedly
    first launch show previously created buttons instead of the single
    onboarding CTA.  Therefore source runs are isolated next to the project.
    """

    if getattr(sys, "frozen", False):
        return None
    if _env_flag_disabled(os.environ.get("MEDICAL_AUTOFILL_PORTABLE_SOURCE_DATA", "1")):
        return None
    return Path(__file__).resolve().parent / ".medical_diary_autofill_data"


class SettingsMixin:
    def _get_settings_path(self) -> Path:
        portable_root = _source_portable_data_root()
        if portable_root is not None:
            return portable_root / "settings.json"
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home()
        return root / "MedicalDiaryAutofill" / "settings.json"

    def _quarantine_broken_settings(self, details: Exception | str) -> None:
        """Сохранить битый settings.json рядом, чтобы новый запуск не падал.

        В settings.json хранятся только технические удобства: последние папки
        диалогов и выбранный принтер. Данные пациентов туда не пишутся. Если
        файл оказался повреждён из-за аварийного завершения Windows/диска,
        программа стартует с пустыми настройками и оставляет копию для разбора.
        """
        try:
            if not self._settings_path.exists():
                return
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            broken_path = self._settings_path.with_name(f"settings.broken.{stamp}.json")
            broken_path.write_text(
                self._settings_path.read_text(encoding="utf-8", errors="replace")
                + "\n\n/* settings.json был проигнорирован программой: "
                + str(details).replace("*/", "")
                + " */\n",
                encoding="utf-8",
            )
            # After quarantining the broken file, replace the live settings with
            # a valid empty object.  Otherwise a user who only opens the program
            # and closes it without changing settings will get the same broken
            # settings parsed and quarantined on every launch.
            self._settings_path.write_text("{}\n", encoding="utf-8")
        except Exception as exc:
            record_soft_exception("settings_mixin:37", exc)

    def _load_settings(self) -> dict:
        try:
            if self._settings_path.exists():
                data = json.loads(self._settings_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
                # JSON может быть синтаксически валидным, но иметь неверный
                # тип (например, список после ручной правки). Такой файл тоже
                # изолируем, иначе программа будет стартовать с пустыми
                # настройками без объяснимого следа диагностики.
                self._quarantine_broken_settings(f"ожидался объект JSON, получено {type(data).__name__}")
        except json.JSONDecodeError as exc:
            self._quarantine_broken_settings(exc)
        except Exception as exc:
            record_soft_exception("settings_mixin:53", exc)
        return {}

    def _settings_payload_for_disk(self) -> dict:
        """Вернуть только безопасные настройки для записи на диск.

        Production-контракт: история пациентов, диагнозы, даты лечения, пути
        созданных документов и содержимое медицинских файлов никогда не
        сохраняются в settings.json. На диск уходят только папки диалогов и
        выбранный принтер.
        """
        payload: dict = {}
        folders_raw = self._settings.get("folders")
        folders: dict[str, str] = {}
        if isinstance(folders_raw, dict):
            for key, value in folders_raw.items():
                key_text = str(key).strip()
                value_text = str(value).strip()
                if key_text and value_text:
                    folders[key_text] = value_text
        if folders:
            payload["folders"] = folders
        printer = str(self._settings.get("printer", "")).strip()
        if printer:
            payload["printer"] = printer
        language_raw = self._settings.get("language")
        if isinstance(language_raw, dict):
            language_payload = {}
            for key in ("ui_language", "document_language", "output_language", "spellcheck_enabled"):
                if key in language_raw:
                    if key == "spellcheck_enabled":
                        language_payload[key] = _setting_bool(language_raw[key])
                    else:
                        language_payload[key] = language_raw[key]
            if language_payload:
                payload["language"] = language_payload
        folder_naming = self._settings.get("folder_naming")
        if isinstance(folder_naming, dict):
            try:
                from desktop_patient_folder import normalize_folder_naming_settings

                payload["folder_naming"] = normalize_folder_naming_settings(folder_naming)
            except Exception as exc:
                record_soft_exception("settings_mixin.folder_naming_payload", exc)
        defaults_raw = self._settings.get("defaults")
        if isinstance(defaults_raw, dict):
            rvk_value = str(defaults_raw.get("rvk_military_commissariat", "") or "").strip()
            if rvk_value:
                payload["defaults"] = {"rvk_military_commissariat": rvk_value}
        desktop_intake = self._settings.get("desktop_intake")
        if isinstance(desktop_intake, dict):
            seen_signatures: list[str] = []
            raw_seen = desktop_intake.get("seen_signatures", ())
            if isinstance(raw_seen, (list, tuple, set)):
                for item in raw_seen:
                    value = str(item or "").strip().lower()
                    if len(value) == 64 and all(ch in "0123456789abcdef" for ch in value):
                        seen_signatures.append(value)
            payload["desktop_intake"] = {
                "asked": _setting_bool(desktop_intake.get("asked", False)),
                "enabled": _setting_bool(desktop_intake.get("enabled", False)),
                "folder": str(desktop_intake.get("folder", "") or ""),
                "prompt_version": str(desktop_intake.get("prompt_version", "") or ""),
                "seen_signatures": list(dict.fromkeys(seen_signatures[-300:])),
            }
        return payload

    def _settings_backup_path(self) -> Path:
        return self._settings_path.with_name("settings.backup.json")

    def _settings_timestamped_backup_path(self, *, reason: str = "save") -> Path:
        safe_reason = "".join(ch for ch in str(reason or "save") if ch.isalnum() or ch in {"_", "-"})[:32] or "save"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return self._settings_path.parent / "_settings_backups" / f"settings_{safe_reason}_{stamp}.json"

    def _backup_settings_file(self, *, reason: str = "save") -> Path | None:
        try:
            if self._settings_path.exists():
                backup_path = self._settings_backup_path()
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self._settings_path, backup_path)
                timestamped = self._settings_timestamped_backup_path(reason=reason)
                timestamped.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self._settings_path, timestamped)
                return timestamped
        except Exception as exc:
            record_soft_exception("settings_mixin.backup", exc, detail=str(self._settings_path))
        return None

    def _save_settings(self) -> None:
        tmp_path = self._settings_path.with_name(self._settings_path.name + ".tmp")
        try:
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            self._backup_settings_file(reason="save")
            tmp_path.write_text(
                json.dumps(self._settings_payload_for_disk(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(tmp_path, self._settings_path)
        except Exception as exc:
            # Настройки — удобство, не критичная функция. Ошибку не показываем врачу,
            # но не оставляем рядом битый settings.json.tmp после неудачной записи.
            record_soft_exception("settings_mixin:save", exc, detail=str(self._settings_path))
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception as cleanup_exc:
                record_soft_exception("settings_mixin:104", cleanup_exc)

    def _settings_folders(self) -> dict:
        folders = self._settings.get("folders")
        if not isinstance(folders, dict):
            folders = {}
            self._settings["folders"] = folders
        return folders

    def _get_saved_directory(self, key: str) -> str:
        value = str(self._settings_folders().get(key, "")).strip()
        if not value:
            return ""
        try:
            path = Path(value).expanduser()
            if path.exists() and path.is_dir():
                return str(path)
        except Exception as exc:
            record_soft_exception("settings_mixin.get_saved_directory", exc, detail=value)
            return ""
        return ""

    def _dialog_initial_dir(self, key: str, *fallbacks: str) -> str:
        candidates = [self._get_saved_directory(key), *fallbacks, self.output_dir_var.get().strip(), str(Path.home())]
        for value in candidates:
            if not value:
                continue
            try:
                path = Path(value).expanduser()
                if path.is_file():
                    path = path.parent
                if path.exists() and path.is_dir():
                    return str(path)
            except Exception as exc:
                record_soft_exception("settings_mixin.dialog_initial_dir", exc, detail=str(value))
                continue
        return ""

    def _remember_dialog_directory(self, key: str, selected_path: str, *, selected_is_dir: bool = False) -> None:
        if not selected_path:
            return
        try:
            path = Path(selected_path).expanduser()
            folder = path if selected_is_dir else path.parent
            if folder.exists() and folder.is_dir():
                self._settings_folders()[key] = str(folder)
                self._save_settings()
        except Exception as exc:
            # Память папок — удобство, не критичная функция.
            record_soft_exception("settings_mixin:150", exc)


    def backup_settings_now(self) -> Path | None:
        """Manual settings backup action for the UI."""
        self._save_settings()
        return self._backup_settings_file(reason="manual") or self._settings_path

    def reset_settings_to_defaults(self) -> bool:
        """Reset safe technical settings without touching patient files."""
        try:
            self._backup_settings_file(reason="reset")
            self._settings = {}
            self._save_settings()
            if hasattr(self, "printer_var"):
                self.printer_var.set("")
            if hasattr(self, "output_dir_var"):
                self._suspend_output_dir_tracking = True
                try:
                    self.output_dir_var.set("")
                finally:
                    self._suspend_output_dir_tracking = False
                self._manual_output_dir = False
            if hasattr(self, "diary_template_dir"):
                self.diary_template_dir = ""
            if hasattr(self, "diary_texts_dir"):
                self.diary_texts_dir = ""
            if hasattr(self, "_update_diary_template_label"):
                self._update_diary_template_label(success=False)
            self._settings["folder_naming"] = {}
            if hasattr(self, "_update_diary_text_label"):
                self._update_diary_text_label(success=False)
            return True
        except Exception as exc:
            record_soft_exception("settings_mixin.reset", exc)
            return False
