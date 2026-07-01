from __future__ import annotations

from diagnostic_logging import record_soft_exception
from medical_primary_document_state import selected_primary_document_path
from medical_date_state import current_semantic_date
import re
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox

from diary_constants import DIR_DIARY_TEMPLATES, DIR_NUMBERED_DIARY_TEMPLATES
from medical_constants import DATE_FMT
from medical_formatting import parse_date


class DiaryTemplateSelectionMixin:
    def _find_numbered_diary_template(self, folder: str | Path, day: int) -> Path | None:
        try:
            root = Path(folder).expanduser()
            if not root.exists() or not root.is_dir():
                return None
            files = self._iter_diary_template_docx_files(root)
            day = int(day)

            # 1) Самый строгий контракт: файл называется 15.docx / 15.docm.
            exact_names = {
                f"{day:02d}.docx", f"{day}.docx", f"{day:02d}.docm", f"{day}.docm",
                f"{day:02d}", f"{day}",
            }
            for path in files:
                if path.name.strip().lower() in exact_names:
                    return path

            # 2) Мягкие имена: 15(2).docx, №15.docx, шаблон 15.docx, 15 дневник.DOCX.
            matches = [path for path in files if self._is_numbered_diary_template_file(path, day)]
            if matches:
                def priority(path: Path) -> tuple[int, int, str]:
                    stem = path.stem.strip().lower().replace("ё", "е")
                    starts_with_day = bool(re.match(rf"^\s*0?{day}(?=\D|$)", stem))
                    exactish = bool(re.match(rf"^\s*0?{day}\s*(?:\(\d+\))?\s*$", stem))
                    return (0 if exactish else 1, 0 if starts_with_day else 1, path.name.lower())
                return sorted(matches, key=priority)[0]

            # 3) Запасной контур: если файл назван странно, определяем номер
            # шаблона по первой строке таблицы внутри самого DOCX.
            content_matches = []
            for path in files:
                if self._template_content_first_day(path) == day:
                    content_matches.append(path)
            if content_matches:
                return sorted(content_matches, key=lambda item: item.name.lower())[0]
            return None
        except Exception as exc:
            record_soft_exception("diary_template_selection.find_numbered_template", exc, detail=str(folder))
            return None

    def _template_not_found_message(self, days: list[int], available: list[str]) -> str:
        day_list = ", ".join(f"{day:02d}" for day in days) or "нужного числа"
        examples: list[str] = []
        for day in days[:2]:
            examples.extend([f"{day:02d}", f"{day:02d}.docx", f"{day}", f"{day}.docx", f"{day:02d}(2).docx", f"№{day:02d}.docx"])
        # Убираем повторы вроде 01 и 1 для однозначной подсказки.
        deduped_examples: list[str] = []
        for item in examples:
            if item not in deduped_examples:
                deduped_examples.append(item)
        text = (
            f"В папке «шаблоны дневников» не найден шаблон для числа {day_list}. "
            f"Программа одинаково понимает имена: " + ", ".join(deduped_examples) + ". "
            "Также она пробует определить номер по первой строке таблицы внутри DOCX."
        )
        if available:
            text += "\n\nПрограмма увидела DOCX/Word-файлы в выбранной папке и подпапках:\n" + "\n".join(available)
        return text

    def _available_diary_template_names(self, folder: str | Path, *, limit: int = 80) -> list[str]:
        try:
            root_path = Path(folder).resolve()
            available: list[str] = []
            for p in self._iter_diary_template_docx_files(folder)[:limit]:
                try:
                    available.append(str(p.resolve().relative_to(root_path)))
                except Exception as exc:
                    record_soft_exception("diary_template_selection.available_relative", exc, detail=str(p))
                    available.append(p.name)
            return available
        except Exception as exc:
            record_soft_exception("diary_template_selection.available_names", exc, detail=str(folder))
            return []

    def _try_find_template_in_dirs(
        self,
        dirs: list[Path],
        candidates: list[tuple[int, str, datetime]],
    ) -> tuple[Path | None, int | None, str, datetime | None]:
        seen_dirs: set[str] = set()
        for folder in dirs:
            try:
                folder_key = str(Path(folder).resolve())
            except Exception as exc:
                record_soft_exception("diary_template_selection.dir_resolve", exc, detail=str(folder))
                folder_key = str(folder)
            if folder_key in seen_dirs:
                continue
            seen_dirs.add(folder_key)
            for day, reason, template_date in candidates:
                found = self._find_numbered_diary_template(folder, day)
                if found:
                    return found, day, reason, template_date
        return None, None, "", None

    def _sync_admission_date_from_title(self, *, force: bool = False) -> str:
        """Подтянуть дату поступления из первичного DOCX.

        Это UI-обвязка вокруг безопасного admission-resolver. Она не меняет diary_filler.py и нужна
        только для того, чтобы поле "Дата поступления / месяц, год" не
        оставалось пустым и не подхватывало дату рождения пациента.
        """
        primary_path = selected_primary_document_path(self)
        if primary_path is None:
            return ""
        path = str(primary_path)
        try:
            from medical_admission_resolver import extract_admission_date_from_primary_docx
            title_date = extract_admission_date_from_primary_docx(path)
        except Exception as exc:
            record_soft_exception("diary_template_selection.sync_admission_title", exc, detail=str(path))
            title_date = ""
        if not title_date:
            return ""
        current = current_semantic_date(self, "admission_date")
        # Ручной/doctor-confirmed ввод всегда финальный. Даже force-вызовы из
        # создания дневников, desktop-intake или смены первичного документа не
        # должны перетирать дату, которую врач уже подтвердил в popup/UI. После
        # выбора нового первичного документа runtime state сбрасывается отдельно,
        # поэтому здесь можно безопасно сохранять ручной приоритет.
        if current and bool(getattr(self, "_manual_admission_date", False)):
            return title_date
        if force or not current:
            self._set_ui_var(self.admission_date_var, title_date)
        return title_date

    def _admission_datetime_for_diary_template(self) -> datetime | None:
        # Для автоподбора шаблона дневников ручной doctor-confirmed ввод имеет
        # приоритет: если врач исправил дату госпитализации, шаблон 01–31 должен
        # выбираться по исправленной дате, а не по устаревшей дате заголовка.
        if bool(getattr(self, "_manual_admission_date", False)):
            manual_value = current_semantic_date(self, "admission_date")
            parsed_manual = parse_date(manual_value)
            if parsed_manual:
                return parsed_manual
        # Если ручной даты нет, сначала берём дату из самого первичного
        # документа/направления. Это защищает от ситуации, когда в UI случайно
        # попала дата рождения пациента.
        title_date = self._sync_admission_date_from_title(force=False)
        parsed_from_doc = parse_date(title_date)
        if parsed_from_doc:
            return parsed_from_doc
        # Если первичный документ выбран, но дата в его заголовке не найдена,
        # используем уже распознанную основным парсером дату поступления. Старый
        # полный запрет на UI-дату ломал автоподбор 01-31 для документов, где
        # дата находится в таблице/теле, а не в заголовке файла.
        data_date = ""
        try:
            data_date = str(getattr(getattr(self, "data", None), "admission_date", "") or "").strip()
        except Exception as exc:
            record_soft_exception("diary_template_selection.data_admission_date", exc)
        parsed_data = parse_date(data_date)
        if parsed_data:
            return parsed_data
        value = current_semantic_date(self, "admission_date")
        parsed_ui = parse_date(value)
        if parsed_ui:
            return parsed_ui
        return None

    def _diary_template_day_candidates(self, admission_dt: datetime) -> list[tuple[int, str, datetime]]:
        """Вернуть номера шаблонов, которые допустимо пробовать для даты поступления.

        Основной контракт пользователя: число в дате госпитализации равно имени
        шаблона дневников, то есть 02.04.2026 → 02 / 02.docx.
        Дополнительный резерв нужен только для уже существующих папок, где
        шаблоны исторически назывались по первой строке дневника: дата
        поступления + 1 день. Если точного 02 нет, но есть 03, программа сможет
        продолжить работу вместо ошибки.
        """
        result: list[tuple[int, str, datetime]] = []
        seen: set[int] = set()

        def add(day_dt: datetime, reason: str) -> None:
            day = int(day_dt.day)
            if day not in seen:
                seen.add(day)
                result.append((day, reason, day_dt))

        add(admission_dt, "дате госпитализации")
        add(admission_dt + timedelta(days=1), "первому дню дневника")
        return result

    def _auto_select_numbered_diary_template(self, *, ask_folder: bool = False) -> bool:
        """Автоматически выбрать один шаблон 01–31 по дате госпитализации.

        Главный контракт: 02.04.2026 → 02 / 02.docx / 2 / 2.docx.
        Если такого файла физически нет, резервно пробуется дата + 1 день
        для старых наборов шаблонов. Внутренний diary_filler.py не меняется.
        """
        if self.diary_files and not getattr(self, "_diary_files_auto_selected", False):
            return True

        stale_auto_selection = bool(self.diary_files and getattr(self, "_diary_files_auto_selected", False))

        def clear_stale_auto_selection() -> None:
            if not stale_auto_selection:
                return
            self.diary_files = []
            self._diary_files_auto_selected = False
            try:
                self._update_diary_template_label(success=False)
            except Exception as exc:
                record_soft_exception("diary_template_selection.clear_stale_auto_template", exc)

        admission_dt = self._admission_datetime_for_diary_template()
        if not admission_dt:
            clear_stale_auto_selection()
            return False

        day_candidates = self._diary_template_day_candidates(admission_dt)
        preferred_dirs: list[Path] = []
        if getattr(self, "diary_template_dir", ""):
            preferred_dirs.append(Path(self.diary_template_dir))
        preferred_dirs.extend(self._candidate_numbered_diary_template_dirs())

        found, day, reason, template_date = self._try_find_template_in_dirs(preferred_dirs, day_candidates)
        if found and day is not None and template_date is not None:
            self.diary_template_dir = str(found.parent)
            self.diary_files = [str(found)]
            self._diary_files_auto_selected = True
            self._remember_numbered_diary_template_dir(found.parent)
            self._update_diary_template_label(success=True)
            if hasattr(self, "_redraw_selection_controls"):
                self._redraw_selection_controls()
            self._log(
                f"\n✅ Автоматически выбран шаблон дневников: {found.name} "
                f"по {reason} {template_date.strftime(DATE_FMT)}.\n"
            )
            return True

        clear_stale_auto_selection()

        if ask_folder:
            selected_file = filedialog.askopenfilename(
                title="Выберите любой DOCX из папки «шаблоны дневников»",
                initialdir=self._dialog_initial_dir(DIR_NUMBERED_DIARY_TEMPLATES, self._get_saved_directory(DIR_DIARY_TEMPLATES)),
                filetypes=[("Word DOCX", "*.docx *.docm"), ("All files", "*.*")],
            )
            if selected_file:
                folder = str(Path(selected_file).parent)
                self._set_numbered_diary_template_dir(folder, auto_select=False, warn_if_missing=True)
                found, day, reason, template_date = self._try_find_template_in_dirs([Path(folder)], day_candidates)
                if found and day is not None and template_date is not None:
                    self.diary_template_dir = str(Path(folder))
                    self.diary_files = [str(found)]
                    self._diary_files_auto_selected = True
                    self._remember_numbered_diary_template_dir(folder)
                    self._update_diary_template_label(success=True)
                    if hasattr(self, "_redraw_selection_controls"):
                        self._redraw_selection_controls()
                    self._log(
                        f"\n✅ Автоматически выбран шаблон дневников: {found.name} "
                        f"по {reason} {template_date.strftime(DATE_FMT)}.\n"
                    )
                    return True
                messagebox.showwarning(
                    "Шаблон не найден",
                    self._template_not_found_message(
                        [day for day, _reason, _dt in day_candidates],
                        self._available_diary_template_names(folder),
                    ),
                )
        return False
