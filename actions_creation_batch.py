from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

from actions_reports import history_dir
from medical_constants import DIR_OUTPUT, DIR_PRIMARY_DOCUMENTS
from medical_date_state import current_semantic_date
from medical_formatting import redact_technical_text, technical_ref
from diagnostic_logging import record_soft_exception

class ActionsCreationBatchingMixin:

    def batch_generate_documents_dialog(self) -> None:
        """Batch generation for doctor-owned profile documents."""
        selected_medical = self.selected_medical_docs()
        selected_custom = self.selected_custom_docs()
        if not selected_medical and not selected_custom:
            messagebox.showwarning(
                "Пакетная обработка",
                "Сначала отметьте в блоке 03, какие документы создавать.\n\n"
                "Если кнопок документов ещё нет — нажмите «+ Добавить шаблоны» и загрузите Word-шаблоны врача.",
            )
            return
        source_dir = filedialog.askdirectory(
            title="Выберите папку с первичными документами пациентов",
            initialdir=self._dialog_initial_dir(DIR_PRIMARY_DOCUMENTS),
        )
        if not source_dir:
            return
        try:
            self._remember_dialog_directory(DIR_PRIMARY_DOCUMENTS, source_dir)
        except Exception as exc:
            record_soft_exception("actions_creation_orchestrator.batch_source_last_dir", exc)
        try:
            from medical_service import discover_primary_documents
            primary_documents = discover_primary_documents(source_dir)
        except Exception as exc:
            messagebox.showerror("Пакетная обработка", str(exc))
            return
        if not primary_documents:
            messagebox.showwarning("Пакетная обработка", "В выбранной папке не найдено первичных DOCX/DOCM документов пациентов.")
            return
        output_root = filedialog.askdirectory(
            title="Куда сохранить пакетный результат",
            initialdir=str(self._base_output_dir()),
        )
        if not output_root:
            return
        try:
            self._remember_dialog_directory(DIR_OUTPUT, output_root)
        except Exception as exc:
            record_soft_exception("actions_creation_orchestrator.batch_output_last_dir", exc)
        names = ", ".join(self._selected_output_names(selected_medical, False, selected_custom))
        if not messagebox.askyesno(
            "Пакетная обработка",
            f"Найдено файлов пациентов: {len(primary_documents)}\n"
            f"Документы: {names}\n"
            f"Папка результата: {output_root}\n\n"
            "Запустить пакетное создание?",
        ):
            return
        try:
            self._set_status("Пакетная обработка...")
            self.root.update_idletasks()
            reports: list[str] = []
            if selected_medical:
                from medical_service import create_documents_batch, save_batch_generation_report
                result = create_documents_batch(
                    primary_documents=primary_documents,
                    output_root=output_root,
                    selected_docs=selected_medical,
                    discharge_date=current_semantic_date(self, "discharge_date"),
                    epi_path=self.epi_path_var.get().strip() or None,
                    service=self.service,
                    folder_naming_settings=self._folder_naming_settings(),
                )
                report_path = save_batch_generation_report(result, history_dir(output_root) / "batch_generation_report.txt")
                reports.append(result.human_report() + f"\nОтчёт: {report_path}")
            if selected_custom:
                reports.append(self._create_custom_documents_batch(primary_documents, Path(output_root), selected_custom))
            message = "\n\n".join(item for item in reports if item)
            self._log("\n" + message + "\n")
            self._open_result_folder_silent(Path(output_root))
            messagebox.showinfo("Пакет готов", message[:3500] if message else "Пакетная обработка завершена")
            self._set_status("Пакетная обработка завершена")
        except Exception as exc:
            record_soft_exception("actions_creation_orchestrator.batch_generate", exc)
            messagebox.showerror("Пакетная обработка", f"Не удалось выполнить пакетную обработку:\n{exc}")
            self._set_status("Ошибка пакетной обработки")

    def _create_custom_documents_batch(self, primary_documents, output_root: Path, selected_custom: list[str]) -> str:
        """Implement the _create_custom_documents_batch workflow with validation, UI state updates and diagnostics."""
        from universal_case_adapter import merge_patient_cases, patient_data_to_case
        from universal_generation import render_documents_from_pack
        from universal_scanner import scan_docx

        pack = self._load_or_create_universal_pack()
        base_dir = self._universal_profile_path().parent
        display_lines = ["ПАКЕТНАЯ ОБРАБОТКА СВОИХ ШАБЛОНОВ", ""]
        technical_lines = ["ПАКЕТНАЯ ОБРАБОТКА СВОИХ ШАБЛОНОВ — технический обезличенный отчёт", ""]
        ok = 0
        errors = 0
        for source in primary_documents:
            source_path = Path(source)
            try:
                patient = self.service.parse_primary_document(source_path)
                shared_discharge = current_semantic_date(self, "discharge_date")
                if shared_discharge:
                    patient.discharge_date = shared_discharge
                patient_dir = self._patient_output_dir_for_data(patient, base_dir=output_root)
                case = patient_data_to_case(patient, source_document=source_path)
                try:
                    scan = scan_docx(source_path, registry=pack.registry(), rules=pack.extraction_rules)
                    case = merge_patient_cases(case, scan.patient_case())
                except Exception as scan_exc:
                    record_soft_exception("actions_creation_orchestrator.custom_batch_scan", scan_exc, detail=str(source_path))
                result = render_documents_from_pack(
                    pack=pack,
                    case=case,
                    document_ids=selected_custom,
                    output_dir=patient_dir,
                    base_dir=base_dir,
                    strict=False,
                    output_language=self._effective_output_language(),
                    spellcheck_enabled=bool(getattr(self, "spellcheck_enabled_var", None) and self.spellcheck_enabled_var.get()),
                )
                ref = technical_ref(source_path, patient_dir, getattr(patient, "case_number", ""))
                if result.created_files:
                    ok += 1
                    display_lines.append(f"✅ {source_path.name}: создано {len(result.created_files)} файл(ов) → {patient_dir}")
                    technical_lines.append(f"✅ {ref}: создано {len(result.created_files)} файл(ов)")
                else:
                    errors += 1
                    skipped = "; ".join(result.skipped_documents or result.warnings or ("ничего не создано",))
                    display_lines.append(f"❌ {source_path.name}: {skipped}")
                    technical_lines.append(f"❌ {ref}: {redact_technical_text(skipped)}")
            except Exception as exc:
                errors += 1
                ref = technical_ref(source_path)
                display_lines.append(f"❌ {source_path.name}: {exc}")
                technical_lines.append(f"❌ {ref}: {redact_technical_text(exc)}")
        summary = f"Готово: успешно {ok}, с ошибками {errors}"
        display_lines.insert(2, summary)
        technical_lines.insert(2, summary)
        report_dir = history_dir(output_root)
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "custom_batch_generation_report.txt"
        from medical_formatting import available_path
        report_path = available_path(report_path)
        report_path.write_text("\n".join(technical_lines) + "\n", encoding="utf-8")
        display_lines.append("")
        display_lines.append(f"Отчёт: {report_path}")
        return "\n".join(display_lines)

    def _open_result_folder_silent(self, folder: Path) -> bool:
        """Открыть папку результата без дополнительного popup-уведомления."""
        try:
            folder = Path(folder).expanduser()
            from printer_platform import open_desktop_path
            return open_desktop_path(folder, require_dir=True)
        except Exception as exc:
            record_soft_exception("actions_creation_orchestrator.open_result_folder", exc, detail=str(folder))
            return False

    def _open_output_folder_after_creation(
        self,
        *,
        created_files: List[Path],
        creation_report: Path | None,
    ) -> bool:
        if not getattr(self, "open_result_folder_var", None) or not self.open_result_folder_var.get():
            return False
        folder: Path | None = None
        if created_files:
            folder = created_files[0].parent
        elif creation_report is not None:
            folder = creation_report.parent
        else:
            folder = self._result_output_dir()
        return self._open_result_folder_silent(folder)

    def _selected_outputs_or_warn(self) -> tuple[list[str], bool, list[str]] | None:
        selected_medical = self.selected_medical_docs()
        selected_diaries = self.diaries_selected()
        selected_custom = self.selected_custom_docs()
        if not selected_medical and not selected_diaries and not selected_custom:
            messagebox.showwarning(
                "Ничего не выбрано",
                "Отметьте хотя бы один документ, custom-документ профиля или «Дневники наблюдения».",
            )
            return None
        names = self._selected_output_names(selected_medical, selected_diaries, selected_custom)
        self._log("\n▶ Выбрано для создания: " + ", ".join(names) + "\n")
        return selected_medical, selected_diaries, selected_custom

    def _selected_custom_document_specs(self, selected_custom: list[str] | None):
        if not selected_custom:
            return ()
        try:
            pack = self._load_or_create_universal_pack()
        except Exception as exc:
            record_soft_exception("actions_creation_orchestrator.custom_specs", exc)
            return ()
        docs = []
        for document_id in selected_custom:
            document = pack.document_by_id(document_id)
            if document is not None:
                docs.append(document)
        return tuple(docs)

    def _custom_requirement_flags(self, selected_custom: list[str] | None) -> dict[str, bool]:
        """Infer popup needs for doctor-owned block-03 buttons from saved medpack data."""
        from universal_main_documents import custom_requirement_flags_for_documents
        return custom_requirement_flags_for_documents(self._selected_custom_document_specs(selected_custom))

    def _collect_creation_requirements(self, selected_medical: list[str], selected_diaries: bool, selected_custom: list[str] | None = None) -> bool:
        """Collect all blocking doctor inputs before generation starts.

        The routing is deliberately centralized here so mixed selections do not
        produce duplicated popups or silently skip custom-template requirements.
        Ordinary documents use the common popup; discharge templates merge their
        own date/labs questions; custom special documents that require analyses
        receive a standalone labs popup when no discharge popup will cover it.
        """
        custom = self._custom_requirement_flags(selected_custom)
        self._active_custom_requirement_flags = custom
        custom_special = custom["discharge"] or custom["rvk"]
        custom_regular_non_special = custom["regular"] and not custom_special
        diary_selected = selected_diaries or custom["diary"]
        special_selected = any(kind in selected_medical for kind in {"discharge", "rvk"}) or custom_special
        non_special = any(kind not in {"discharge", "rvk"} for kind in selected_medical) or custom_regular_non_special
        custom_needs_common = any(
            custom.get(key, False)
            for key in ("requires_case_number", "requires_diagnosis", "requires_treatment", "requires_discharge_date", "requires_labs")
        )
        common_prompted_for_labs = False
        if not special_selected and (non_special or diary_selected or custom_needs_common):
            common_prompted_for_labs = bool(custom.get("requires_labs"))
            if not self._prompt_common_output_requirements(
                include_discharge_date=diary_selected or bool(custom.get("requires_discharge_date")),
                include_case_number=non_special or bool(custom.get("requires_case_number")),
                include_medical_details=non_special or bool(custom.get("requires_diagnosis") or custom.get("requires_treatment") or custom.get("requires_labs")),
                include_labs_block=bool(custom.get("requires_labs")),
            ):
                return False
        labs_deferred_to_discharge = bool(custom.get("requires_labs") and ("discharge" in selected_medical or custom["discharge"]))
        if bool(custom.get("requires_labs")) and not common_prompted_for_labs and not labs_deferred_to_discharge:
            try:
                labs_missing = self._labs_required_missing()
            except Exception as exc:
                record_soft_exception("actions_creation_batch.labs_required_missing", exc)
                labs_missing = False
            if labs_missing and not self._prompt_common_output_requirements(
                include_discharge_date=False,
                include_case_number=False,
                include_medical_details=False,
                include_labs_block=True,
            ):
                return False
        if ("commission" in selected_medical or custom["commission"]) and not all([current_semantic_date(self, "commission_date"), self.commission_number_var.get().strip()]):
            if not self._prompt_commission_details():
                return False
        if ("rvk" in selected_medical or custom["rvk"]) and self._rvk_needs_popup():
            if not self._prompt_rvk_details():
                return False
        if ("vk_mse" in selected_medical or custom["vk_mse"]) and not self._vk_mse_details_complete():
            if not self._prompt_vk_mse_details():
                return False
        if ("sick_leave_vk" in selected_medical or custom["sick_leave_vk"]) and not self._sick_leave_vk_details_complete():
            if not self._prompt_sick_leave_vk_details():
                return False
        try:
            expert_needed = self._expert_anamnesis_needed_for_selection(selected_medical, custom)
        except TypeError:
            expert_needed = self._expert_anamnesis_needed_for_selection(selected_medical)
        if expert_needed:
            if not self._prompt_expert_anamnesis_details(force=False):
                return False
        if ("discharge" in selected_medical or custom["discharge"]) and not self._prompt_discharge_output_requirements(include_labs_block=bool(custom.get("requires_labs"))):
            return False
        remaining = [kind for kind in selected_medical if kind not in {"discharge", "rvk"}]
        if (remaining or (custom_regular_non_special and custom.get("requires_treatment"))) and not self._prompt_assigned_treatment_if_needed(force=False):
            return False
        return True

