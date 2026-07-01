from __future__ import annotations

from diagnostic_logging import record_soft_exception
from medical_primary_document_state import PRIMARY_DOCUMENT_SUFFIXES, clean_primary_document_path, selected_primary_document_path_text, sync_selected_primary_document_path, clear_selected_primary_document_path
from pathlib import Path
from typing import List
from tkinter import filedialog, messagebox
import threading

from app_config import MUTED, SUCCESS
from diary_constants import DIARY_KIND, DIR_DIARY_TEMPLATES, DIR_DIARY_TEXTS, DIR_NUMBERED_DIARY_TEMPLATES
from medical_constants import DIR_EPI, DIR_OUTPUT, DIR_PRIMARY_DOCUMENTS
from medical_models import PatientData
from diary_text_selection import (
    diary_diagnosis_match_score,
    find_diary_text_file_for_diagnosis,
    folder_has_diary_text_candidates,
    iter_diary_text_docx_files,
)


class FilesMixin:
    def _mark_manual_output_dir(self) -> None:
        if self._suspend_output_dir_tracking:
            return
        # Пользователь изменил папку результата вручную или через кнопку:
        # дальше автоматический выбор первичного документа её не перетирает.
        self._manual_output_dir = True
        self._output_dir_auto_locked_to_patient = False

    def _set_output_dir_auto(self, path: str | Path) -> None:
        value = str(path).strip()
        if not value:
            return
        self._suspend_output_dir_tracking = True
        try:
            self.output_dir_var.set(value)
        finally:
            self._suspend_output_dir_tracking = False

    def _release_patient_scoped_output_dir_before_new_primary(self) -> None:
        """Release desktop-intake auto folder before switching to another patient."""
        if getattr(self, "_output_dir_auto_locked_to_patient", False):
            self._manual_output_dir = False
            self._output_dir_auto_locked_to_patient = False

    def _set_output_dir_auto_patient_scoped(self, path: str | Path) -> None:
        """Use a desktop-intake patient folder for the current detected patient only."""
        self._set_output_dir_auto(path)
        self._manual_output_dir = True
        self._output_dir_auto_locked_to_patient = True

    def _set_output_dir_from_primary_default(self, primary_path: str | Path) -> None:
        # Главный пользовательский контракт: если выбран первичный осмотр
        # или направление на госпитализацию, папка сохранения по умолчанию
        # становится папкой этого входного файла.
        if self._manual_output_dir:
            return
        try:
            parent = Path(primary_path).resolve().parent
        except Exception as exc:
            record_soft_exception("files_mixin.primary_parent_resolve", exc, detail=str(primary_path))
            parent = Path(primary_path).parent
        self._set_output_dir_auto(parent)

    def choose_output_dir(self) -> None:
        path = filedialog.askdirectory(
            title="Выберите папку результата",
            initialdir=self._dialog_initial_dir(DIR_OUTPUT),
        )
        if path:
            self.output_dir_var.set(path)
            self._manual_output_dir = True
            self._remember_dialog_directory(DIR_OUTPUT, path, selected_is_dir=True)

    def _set_primary_document_type(self, selected_type: str) -> None:
        selected_type = "hospitalization_referral" if selected_type == "hospitalization_referral" else "primary_exam"
        self.primary_document_type_var.set(selected_type)
        self.primary_document_type_display_var.set(
            "Направление на госпитализацию" if selected_type == "hospitalization_referral" else "Первичный осмотр"
        )

    def _reset_primary_document_runtime_state(self) -> None:
        """Сбросить данные прошлого пациента перед новым первичным файлом."""
        self.assigned_treatment_var.set("")
        self.case_number_var.set("")
        self.expert_work_status_var.set("")
        self.expert_work_org_var.set("")
        self.expert_position_var.set("")
        self.expert_sick_leave_needed_var.set("нет")
        self.expert_sick_leave_from_var.set("")
        self.expert_sick_leave_number_var.set("")
        self.vk_mse_work_org_var.set("")
        self.vk_mse_position_var.set("")
        self.sick_leave_vk_work_org_var.set("")
        self.sick_leave_vk_position_var.set("")
        self.sick_leave_vk_work_position_var.set("")
        # Реквизиты специальных popup-окон относятся к конкретному пациенту.
        # При новом первичном документе они не должны перетекать из прошлого
        # случая в РВК/ВК/МСЭ/комиссию/больничный лист.
        for _var_name in (
            "rvk_act_number_var", "rvk_work_position_var",
            "sick_leave_vk_date_var", "sick_leave_vk_protocol_number_var",
            "sick_leave_vk_protocol_date_var", "sick_leave_vk_commission_date_var",
            "commission_date_var", "commission_number_var",
            "vk_date_var", "vk_protocol_number_var", "vk_protocol_date_var",
            "labs_text_var", "labs_source_path_var", "labs_explicit_date_var",
        ):
            try:
                getattr(self, _var_name).set("")
            except Exception as exc:
                record_soft_exception("files_mixin.reset_patient_popup_var", exc, detail=_var_name)
        try:
            self.labs_date_policy_var.set("preserve_found_dates")
            self.labs_without_var.set(False)
        except Exception as exc:
            record_soft_exception("files_mixin.reset_labs_vars", exc)
        self._primary_work_org_default = ""
        self._primary_work_position_default = ""
        self._work_details_manually_edited = False
        self._update_expert_sick_leave_display()
        self._manual_patient_name = False
        self._manual_admission_date = False
        self._manual_discharge_date = False
        self._manual_diagnosis = False
        self._popup_diagnosis_override = ""
        self._popup_discharge_date_override = ""
        try:
            self._semantic_date_state.clear()
        except Exception as exc:
            record_soft_exception("files_mixin.reset_semantic_date_state", exc)
        # Новый первичный документ — новый пациент.  Ручной выбор дневников
        # сохраняется только внутри текущего пациента: иначе старые «Тексты» и
        # конкретный файл «Даты» блокируют автоподбор по новому диагнозу/дате.
        # Папки оставляем, выбранные файлы очищаем и помечаем как auto-ready.
        if getattr(self, "status_files", None):
            self.status_files = []
        self._diary_text_files_auto_selected = True
        self._update_diary_text_label(success=bool(getattr(self, "diary_texts_dir", "")))
        if getattr(self, "diary_files", None):
            self.diary_files = []
        self._diary_files_auto_selected = True
        if getattr(self, "diary_template_dir", ""):
            try:
                self._update_diary_template_label(success=bool(self._folder_contains_numbered_diary_templates(self.diary_template_dir)))
            except Exception as exc:
                record_soft_exception("files_mixin:109", exc)
                self._update_diary_template_label(success=True)
        else:
            self._update_diary_template_label(success=False)
        self._set_ui_var(self.patient_name_var, "")
        self._set_ui_var(self.admission_date_var, "")
        self._set_ui_var(self.discharge_date_var, "")
        self._set_ui_var(self.diagnosis_var, "")
        if hasattr(self, "_set_primary_drop_empty"):
            self._set_primary_drop_empty()
        elif hasattr(self, "primary_selected_status_var"):
            self.primary_selected_status_var.set(" ")
        self.data = PatientData()

    def _primary_type_from_parsed_data(data: PatientData) -> str:
        kind = (data.input_document_kind or "").lower().replace("ё", "е")
        if "направ" in kind or "госпитализируется" in kind:
            return "hospitalization_referral"
        return "primary_exam"

    def _apply_primary_document_path(self, path: str, *, prompt_for_referral: bool) -> None:
        """Load a primary DOCX, reset previous-patient state and sync UI/autoselection."""
        path = clean_primary_document_path(path)
        candidate = Path(path).expanduser() if path else None
        if (
            not candidate
            or not candidate.exists()
            or not candidate.is_file()
            or candidate.suffix.lower() not in PRIMARY_DOCUMENT_SUFFIXES
        ):
            clear_selected_primary_document_path(self)
            if path:
                messagebox.showwarning(
                    "Нужен Word-документ",
                    "В блок 01 нужно выбрать первичный документ Word в формате DOC/DOCX/DOCM.",
                )
            return
        path = sync_selected_primary_document_path(self, candidate)
        self._remember_dialog_directory(DIR_PRIMARY_DOCUMENTS, path)
        self._release_patient_scoped_output_dir_before_new_primary()
        self._reset_primary_document_runtime_state()
        self._set_output_dir_from_primary_default(path)

        try:
            parsed = self._parse_primary_document(path)
            self._set_primary_document_type(self._primary_type_from_parsed_data(parsed))
        except Exception as exc:
            # Если файл формально выбран, но тип не удалось понять до основного
            # разбора, оставляем безопасный режим первичного осмотра без popup.
            record_soft_exception("files_mixin.apply_primary_document_type", exc, detail=path)
            self._set_primary_document_type("primary_exam")

        if hasattr(self, "_set_primary_drop_selected"):
            self._set_primary_drop_selected(path)
        elif hasattr(self, "primary_selected_status_var"):
            kind_text = "Выбрано направление на госпитализацию" if self.primary_document_type_var.get() == "hospitalization_referral" else "Выбран первичный осмотр"
            self.primary_selected_status_var.set(f"{kind_text}: {Path(path).name}")
        # Drop-зона показывает только короткое имя файла, чтобы длинный путь не
        # растягивал первый блок и не сдвигал поля/кнопки.

        self.reparse_navigation()
        # Перед popup ещё раз жёстко подтягиваем дату поступления из строки
        # заголовка, например «15.04.2026 Направление на госпитализацию».
        # Это не даёт полю даты остаться пустым или подхватить дату рождения.
        self._sync_admission_date_from_title(force=True)
        if self.primary_document_type_var.get() == "hospitalization_referral" and prompt_for_referral:
            self._prompt_assigned_treatment_if_needed(force=True)
            # reparse_navigation нужен, чтобы обновить preview и данные из файла,
            # но он не имеет права стереть дату выписки, введённую врачом в popup.
            popup_discharge_after_prompt = self._popup_discharge_date_override.strip()
            self.reparse_navigation(silent=True)
            if popup_discharge_after_prompt:
                self._popup_discharge_date_override = popup_discharge_after_prompt
                self._set_ui_var(self.discharge_date_var, popup_discharge_after_prompt)
                self._manual_discharge_date = True
                self.data.discharge_date = popup_discharge_after_prompt
        else:
            self._set_status("Первичный осмотр распознан. Popup не требуется.")
        # После того как диагноз и дата поступления точно подтянуты, пробуем
        # автоматически подобрать тексты дневников по названию диагноза и
        # конкретный 01–31-шаблон по дате госпитализации.
        self._auto_select_diary_text_by_diagnosis(ask_folder=False)
        self._auto_select_numbered_diary_template(ask_folder=False)
        try:
            from doctor_action_journal import append_doctor_action
            append_doctor_action(
                output_dir=self.output_dir_var.get().strip() or Path(path).parent,
                action="Найден и прочитан первичный документ",
                details={
                    "file": Path(path).name,
                    "document_type": self.primary_document_type_display_var.get(),
                    "diagnosis": self.diagnosis_var.get().strip(),
                },
                category="primary_document",
            )
        except Exception as exc:
            record_soft_exception("files_mixin.journal_primary_selected", exc)

    def choose_navigation(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите первичный документ",
            initialdir=self._dialog_initial_dir(DIR_PRIMARY_DOCUMENTS),
            filetypes=[("Word DOC/DOCX/DOCM", "*.doc *.docx *.docm"), ("All files", "*.*")],
        )
        if not path:
            return
        self._apply_primary_document_path(path, prompt_for_referral=True)

    def choose_epi(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите файл ЭПИ",
            initialdir=self._dialog_initial_dir(DIR_EPI),
            filetypes=[("Word DOC/DOCX/DOCM", "*.doc *.docx *.docm"), ("Text", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.epi_path_var.set(path)
            self._remember_dialog_directory(DIR_EPI, path)
            self.reparse_navigation(silent=True)

    def _diary_text_label_text(self) -> str:
        max_chars = 56 if self._compact_ui else 96
        if self.status_files:
            text = self._short_file_list(
                self.status_files,
                limit=2 if self._compact_ui else 3,
                single_line=self._compact_ui,
                max_chars=max_chars,
            )
            return "Тексты: " + text
        if getattr(self, "diary_texts_dir", ""):
            return "Тексты: " + self._truncate_label_text(Path(self.diary_texts_dir).name, max_chars=max_chars)
        return "Тексты: не выбраны"

    def _update_diary_text_label(self, *, success: bool | None = None) -> None:
        if not hasattr(self, "status_files_label"):
            return
        text = self._diary_text_label_text()
        color = SUCCESS if (success or self.status_files or getattr(self, "diary_texts_dir", "")) else MUTED
        self.status_files_label.config(text=text, foreground=color)

    def _candidate_diary_text_dirs(self) -> list[Path]:
        """Implement the _candidate_diary_text_dirs workflow with validation, UI state updates and diagnostics."""
        result: list[Path] = []
        seen: set[str] = set()

        def add_folder(candidate: str | Path) -> None:
            if not candidate:
                return
            try:
                folder = Path(candidate).expanduser()
                if folder.is_file():
                    folder = folder.parent
                if not folder.exists() or not folder.is_dir():
                    return
                if not folder_has_diary_text_candidates(folder):
                    return
                key = str(folder.resolve())
            except Exception as exc:
                record_soft_exception("files_mixin.candidate_diary_text_dirs.add_folder", exc, detail=str(candidate))
                return
            if key not in seen:
                seen.add(key)
                result.append(folder)

        if getattr(self, "diary_texts_dir", ""):
            add_folder(self.diary_texts_dir)
        add_folder(self._get_saved_directory(DIR_DIARY_TEXTS))

        # Автопоиск рядом с первичным документом: только прямые папки с
        # понятными именами, чтобы не шерстить весь компьютер и не взять чужой DOCX.
        roots: list[Path] = []
        primary_value = ""
        try:
            primary_value = selected_primary_document_path_text(self)
        except Exception as exc:
            record_soft_exception("files_mixin.candidate_diary_text_dirs.primary_resolver", exc)
            primary_value = clean_primary_document_path(self.navigation_path_var.get().strip())
        for value in (primary_value, clean_primary_document_path(self.output_dir_var.get().strip())):
            if value:
                try:
                    p = Path(value).expanduser()
                    base = p.parent if p.is_file() else p
                    for candidate in (base, base.parent, base.parent.parent):
                        if candidate.exists() and candidate.is_dir():
                            roots.append(candidate)
                except Exception as exc:
                    record_soft_exception("files_mixin.candidate_diary_text_dirs.roots", exc, detail=str(value))
        for root in roots:
            try:
                children = [root, *sorted(root.iterdir(), key=lambda item: item.name.lower())[:160]]
            except Exception as exc:
                record_soft_exception("files_mixin.candidate_diary_text_dirs.iterdir", exc, detail=str(root))
                children = [root]
            for child in children:
                if not child.is_dir():
                    continue
                name = child.name.lower().replace("ё", "е")
                if any(token in name for token in ("дневник", "дневники", "тексты", "текст", "статус", "статусы", "наблюден", "status", "statuses", "notes")):
                    add_folder(child)
        return result

    def _auto_select_diary_text_by_diagnosis(self, *, ask_folder: bool = False) -> bool:
        """Auto-select diary text DOCX files using diagnosis, folder hints, and safe fallbacks."""
        diagnosis = self.diagnosis_var.get().strip()
        if not diagnosis and getattr(self, "data", None) is not None:
            diagnosis = getattr(self.data, "diagnosis", "") or ""
        if not diagnosis:
            return False
        # Ручной выбор нескольких файлов врачом сохраняем. Автоподбор может
        # заменить только пустой выбор или прошлый автоматический выбор.
        if self.status_files and not getattr(self, "_diary_text_files_auto_selected", False):
            return True

        for folder in self._candidate_diary_text_dirs():
            found = find_diary_text_file_for_diagnosis(folder, diagnosis)
            fallback_reason = "по диагнозу"
            if not found:
                # Doctor-owned deployments often keep exactly one neutral DOCX
                # with daily text in a folder named «Тексты дневников».  When no
                # filename matches the diagnosis, selecting that single file is
                # safer than silently leaving diaries empty and failing later.
                try:
                    candidates = iter_diary_text_docx_files(folder, max_depth=1)
                    if len(candidates) == 1:
                        found = candidates[0]
                        fallback_reason = "как единственный файл в папке текстов"
                    else:
                        scored = [
                            (diary_diagnosis_match_score(diagnosis, path.stem), path.name.lower(), path)
                            for path in candidates
                        ]
                        scored = [item for item in scored if item[0] >= 55]
                        if scored:
                            found = sorted(scored, key=lambda item: (-item[0], item[1]))[0][2]
                            fallback_reason = "по близкому названию"
                except Exception as exc:
                    record_soft_exception("files_mixin.diary_text_fallback", exc, detail=str(folder))
            if not found:
                continue
            self.diary_texts_dir = str(found.parent)
            self.status_files = [str(found)]
            self._diary_text_files_auto_selected = True
            self._remember_dialog_directory(DIR_DIARY_TEXTS, str(found))
            self._update_diary_text_label(success=True)
            self._redraw_selection_controls()
            self._log(f"\n✅ Автоматически выбран текст дневников {fallback_reason}: {found.name}.\n")
            return True

        if ask_folder:
            selected = filedialog.askopenfilename(
                title="Выберите любой Word-файл из папки с текстами дневников",
                initialdir=self._dialog_initial_dir(DIR_DIARY_TEXTS),
                filetypes=[("Word DOC/DOCX/DOCM", "*.doc *.docx *.docm"), ("All files", "*.*")],
            )
            if selected:
                folder = Path(selected).parent
                self.diary_texts_dir = str(folder)
                self._remember_dialog_directory(DIR_DIARY_TEXTS, str(folder), selected_is_dir=True)
                found = find_diary_text_file_for_diagnosis(folder, diagnosis)
                if found:
                    self.status_files = [str(found)]
                    self._diary_text_files_auto_selected = True
                    self._remember_dialog_directory(DIR_DIARY_TEXTS, str(found))
                    self._update_diary_text_label(success=True)
                    self._redraw_selection_controls()
                    self._log(f"\n✅ Автоматически выбран текст дневников по диагнозу: {found.name}.\n")
                    return True
                # Если совпадения нет, выбранный файл остаётся ручным fallback.
                self.status_files = [str(selected)]
                self._diary_text_files_auto_selected = False
                self._update_diary_text_label(success=True)
                self._redraw_selection_controls()
                return True
        return False

    def choose_status_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Выберите файл(ы) с текстами дневников",
            initialdir=self._dialog_initial_dir(DIR_DIARY_TEXTS),
            filetypes=[("Word DOC/DOCX/DOCM", "*.doc *.docx *.docm"), ("All files", "*.*")],
        )
        if not paths:
            return
        # Это именно ручной выбор врача.  Автоподбор по diagnosis_var больше
        # не имеет права заменить выбранный файл на другой DOCX из той же папки:
        # иначе кнопка «Тексты» визуально позволяла выбрать файл, но фактически
        # генератор брал старый/автоматический текст.
        selected_paths = [str(Path(path)) for path in paths]
        self.diary_texts_dir = str(Path(selected_paths[0]).parent)
        self.status_files = selected_paths
        self._diary_text_files_auto_selected = False
        self._remember_dialog_directory(DIR_DIARY_TEXTS, selected_paths[0])
        self._update_diary_text_label(success=True)
        try:
            if hasattr(self, "output_vars") and DIARY_KIND in self.output_vars:
                self.output_vars[DIARY_KIND].set(True)
        except Exception as exc:
            record_soft_exception("files_mixin.diary_texts_select_output", exc)
        self._redraw_selection_controls()
        try:
            if hasattr(self, "_update_selected_outputs_status"):
                self._update_selected_outputs_status()
        except Exception as exc:
            record_soft_exception("files_mixin.diary_texts_status_update", exc)
        self._log(f"\n✅ Врач вручную выбрал тексты дневников: {len(self.status_files)} файл(ов).\n")
        if self.status_files and not self.output_dir_var.get().strip():
            self._set_output_dir_auto(Path(self.status_files[0]).parent)

    def _diary_template_label_text(self) -> str:
        max_chars = 42 if getattr(self, "_compact_ui", False) else 78
        if self.diary_files:
            path = Path(self.diary_files[0])
            return "Даты: " + self._truncate_label_text(path.name, max_chars=max_chars)
        if getattr(self, "diary_template_dir", ""):
            return "Даты: " + self._truncate_label_text(Path(self.diary_template_dir).name, max_chars=max_chars)
        return "Даты: не выбраны"

    def _update_diary_template_label(self, *, success: bool | None = None) -> None:
        if not hasattr(self, "diary_files_label"):
            return
        text = self._diary_template_label_text()
        color = SUCCESS if (success or self.diary_files or getattr(self, "diary_template_dir", "")) else MUTED
        self.diary_files_label.config(text=text, foreground=color)

    def _set_numbered_diary_template_dir(self, folder: str | Path, *, auto_select: bool = True, warn_if_missing: bool = False) -> bool:
        root = Path(folder).expanduser()
        if not root.exists() or not root.is_dir():
            if warn_if_missing:
                messagebox.showwarning("Папка не найдена", "Выбранная папка шаблонов дневников не найдена.")
            return False
        if not self._folder_contains_numbered_diary_templates(root):
            if warn_if_missing:
                messagebox.showwarning(
                    "Нет шаблонов 01–31",
                    "В выбранной папке не найдены DOCX-шаблоны с именами 01.docx, 02.docx, 03.docx … 31.docx.",
                )
            return False
        self.diary_template_dir = str(root)
        self.diary_files = []
        self._diary_files_auto_selected = True
        self._remember_numbered_diary_template_dir(root)
        self._update_diary_template_label(success=True)
        self._redraw_selection_controls()
        selected = self._auto_select_numbered_diary_template(ask_folder=False) if auto_select else False
        try:
            self.output_vars[DIARY_KIND].set(True)
        except Exception as exc:
            record_soft_exception("files_mixin.set_numbered_diary_select_output", exc, detail=str(root))
        if not selected:
            self._log("\nℹ️ Папка дат дневников сохранена. Конкретный шаблон 01–31 будет выбран после чтения даты поступления.\n")
        self._log(f"\n✅ Выбрана папка шаблонов дневников: {root}\n")
        return True

    def _set_manual_diary_template_file(self, selected: str | Path) -> bool:
        path = Path(selected).expanduser()
        if not path.exists() or not path.is_file():
            messagebox.showwarning("Файл не найден", "Выбранный DOCX-шаблон дневников не найден.")
            return False
        if path.suffix.lower() not in {".docx", ".docm"}:
            messagebox.showwarning("Не DOCX", "Для дат дневников выберите Word-файл DOCX/DOCM.")
            return False
        folder = path.parent
        if not self._folder_contains_numbered_diary_templates(folder):
            messagebox.showwarning(
                "Нет шаблонов 01–31",
                "В папке выбранного файла не найдены DOCX-шаблоны с именами 01.docx, 02.docx, 03.docx … 31.docx.",
            )
            return False
        self.diary_template_dir = str(folder)
        self.diary_files = [str(path)]
        self._diary_files_auto_selected = False
        self._remember_numbered_diary_template_dir(folder)
        self._remember_dialog_directory(DIR_NUMBERED_DIARY_TEMPLATES, str(path))
        self._update_diary_template_label(success=True)
        self._redraw_selection_controls()
        self.output_vars[DIARY_KIND].set(True)
        self._log(f"\n✅ Врач вручную выбрал файл дат дневников: {path.name}.\n")
        return True

    def choose_diary_files(self) -> None:
        # Кнопка «Даты» теперь честно поддерживает два сценария:
        # 1) врач выбирает конкретный DOCX — это ручной выбор, не автоподбор;
        # 2) врач отменяет выбор файла и выбирает папку — тогда программа
        #    продолжает автоподбор 01–31 по дате поступления.
        initial_dir = self._dialog_initial_dir(
            DIR_NUMBERED_DIARY_TEMPLATES,
            self._get_saved_directory(DIR_DIARY_TEMPLATES),
        )
        selected = filedialog.askopenfilename(
            title="Выберите конкретный DOCX с датами дневников или отмените для выбора папки",
            initialdir=initial_dir,
            filetypes=[("Word DOCX/DOCM", "*.docx *.docm"), ("All files", "*.*")],
        )
        if selected:
            if self._set_manual_diary_template_file(selected) and not self.output_dir_var.get().strip():
                self._set_output_dir_auto(Path(selected).parent)
            return
        folder_value = filedialog.askdirectory(
            title="Выберите папку «шаблоны дневников» для автоподбора 01–31",
            initialdir=initial_dir,
        )
        if not folder_value:
            return
        folder = Path(folder_value)
        if self._set_numbered_diary_template_dir(folder, auto_select=True, warn_if_missing=True):
            if not self.output_dir_var.get().strip():
                self._set_output_dir_auto(folder)

    @staticmethod
    def _truncate_label_text(text: str, *, max_chars: int = 64) -> str:
        """Return a stable one-line label that cannot stretch compact UI rows."""
        value = " ".join(str(text or "").split())
        if len(value) <= max_chars:
            return value
        if max_chars <= 12:
            return value[:max_chars].rstrip()
        left = max(4, (max_chars - 1) // 2)
        right = max(4, max_chars - left - 1)
        return value[:left].rstrip() + "…" + value[-right:].lstrip()

    def _short_file_list(
        self,
        paths: List[str],
        limit: int = 3,
        *,
        single_line: bool = False,
        max_chars: int = 80,
    ) -> str:
        names = [self._truncate_label_text(Path(path).name, max_chars=max_chars) for path in paths]
        separator = ", " if single_line else "\n"
        if len(names) <= limit:
            return separator.join(names)
        tail = f"… ещё {len(names) - limit}"
        return separator.join(names[:limit] + [tail])

    def _apply_printer_discovery_result(self, printers: list[str], default: str = "", *, silent: bool = False) -> None:
        self.available_printers = printers
        if hasattr(self, "printer_combo"):
            self.printer_combo.configure(values=printers)
        current = self.printer_var.get().strip()
        saved = str(self._settings.get("printer", "")).strip()
        if printers:
            if current in printers:
                chosen = current
            elif saved in printers:
                chosen = saved
            elif default in printers:
                chosen = default
            else:
                chosen = printers[0]
            self.printer_var.set(chosen)
            if not silent:
                self._log(f"\n🖨 Найдены принтеры: {len(printers)}. Выбран: {chosen}\n")
        else:
            self.printer_var.set("")
            if not silent:
                self._log("\n🖨 Принтеры не найдены. Печать доступна в Windows при установленном принтере.\n")

    def _select_default_printer_sync(self) -> bool:
        """Synchronously choose a printer only when the user explicitly asked to print."""
        try:
            from printer_support import get_default_printer, list_printers
            printers = list_printers()
            default = get_default_printer() if printers else ""
        except Exception as exc:
            record_soft_exception("files_mixin.select_default_printer_sync", exc)
            printers = []
            default = ""
        self._apply_printer_discovery_result(printers, default, silent=True)
        return bool(self.printer_var.get().strip())

    def refresh_printers(self, *, silent: bool = False) -> None:
        """Обновить список системных принтеров без подвисания UI.

        Discovery is user-explicit and pywin32-only. It runs in a daemon thread
        and returns only the final combobox update to the Tk thread, so dropping
        a primary document into «Выписанные пациенты» cannot trigger a scary
        PowerShell/cmd window just because the app started.
        """
        if getattr(self, "_printer_refresh_in_progress", False):
            return
        self._printer_refresh_in_progress = True

        def worker() -> None:
            try:
                from printer_support import get_default_printer, list_printers
                printers = list_printers()
                default = get_default_printer() if printers else ""
            except Exception as exc:
                record_soft_exception("files_mixin.refresh_printers.worker", exc)
                printers = []
                default = ""

            def apply_result() -> None:
                self._printer_refresh_in_progress = False
                self._apply_printer_discovery_result(printers, default, silent=silent)

            try:
                self.root.after(0, apply_result)
            except Exception as exc:
                record_soft_exception("files_mixin.refresh_printers.after", exc)
                self._printer_refresh_in_progress = False

        if not silent:
            self._set_status("Ищу принтеры…")
        threading.Thread(target=worker, name="printer-discovery", daemon=True).start()

    def _on_printer_selected(self, _event=None) -> None:
        selected = self.printer_var.get().strip()
        if selected:
            self._settings["printer"] = selected
            self._save_settings()
            self._log(f"\n🖨 Принтер сохранён: {selected}\n")
