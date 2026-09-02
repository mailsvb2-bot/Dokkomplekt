from __future__ import annotations

import os
from pathlib import Path
from tkinter import messagebox

from diagnostic_logging import record_soft_exception
from error_taxonomy import ErrorCategory, record_classified_error
from medical_formatting import parse_date
from medical_date_state import current_semantic_date

class ActionsCreationExecutionMixin:

    def _rvk_needs_popup(self) -> bool:
        return (
            not all([self.rvk_act_number_var.get().strip(), self.rvk_military_commissariat_var.get().strip()])
            or self._case_number_missing()
            or self._should_prompt_discharge_date()
            or self._manual_treatment_missing()
            or self._hospitalization_details_missing()
        )

    def _sick_leave_vk_details_complete(self) -> bool:
        dates = (
            current_semantic_date(self, "sick_leave_vk_date"),
            current_semantic_date(self, "sick_leave_vk_protocol_date"),
            current_semantic_date(self, "sick_leave_vk_commission_date"),
        )
        if not all([
            *dates,
            self.sick_leave_vk_protocol_number_var.get().strip(),
            self.sick_leave_vk_work_org_var.get().strip(),
            self.sick_leave_vk_position_var.get().strip(),
        ]):
            return False
        return all(self._popup_date_value_is_valid_and_in_episode(value) for value in dates)

    def _vk_mse_details_complete(self) -> bool:
        dates = (
            current_semantic_date(self, "vk_date"),
            current_semantic_date(self, "vk_protocol_date"),
        )
        if not all([
            *dates,
            self.vk_protocol_number_var.get().strip(),
            self.vk_mse_work_org_var.get().strip(),
        ]):
            return False
        return all(self._popup_date_value_is_valid_and_in_episode(value) for value in dates)

    def _popup_date_value_is_valid_and_in_episode(self, value: str) -> bool:
        parsed = parse_date(value)
        if not parsed:
            return False
        if hasattr(self, "_date_is_not_before_admission"):
            return self._date_is_not_before_admission(parsed.strftime("%d.%m.%Y"))
        return True

    def _expert_anamnesis_needed_for_selection(self, selected_medical: list[str], custom_flags: dict[str, bool] | None = None) -> bool:
        legacy_needs = bool(selected_medical and self._selected_docs_need_expert_anamnesis(selected_medical))
        custom_needs = bool(
            custom_flags
            and (custom_flags.get("discharge") or custom_flags.get("commission") or custom_flags.get("sick_leave_vk"))
        )
        return bool((legacy_needs or custom_needs) and self._normalize_yes_no(self.expert_sick_leave_needed_var.get()) == "да")


    def _profile_document_matches_builtin_kind(self, document: object, kind: str) -> bool:
        """Match legacy compatibility buttons only to an explicit persisted role."""
        from universal_main_documents import document_role_matches_builtin_kind
        return document_role_matches_builtin_kind(document, kind)

    def _route_legacy_medical_selection_to_profile_docs(self, selected_medical: list[str], selected_custom: list[str]) -> tuple[list[str], list[str]]:
        """Route legacy button to exactly one doctor-owned role, never by title guess."""
        if not selected_medical:
            return selected_medical, selected_custom
        try:
            pack = self._load_or_create_universal_pack()
        except Exception as exc:
            record_soft_exception("actions_creation_execution.load_profile_for_medical_route", exc)
            return selected_medical, selected_custom
        routed: list[str] = []
        remaining: list[str] = []
        for kind in selected_medical:
            matched = [
                str(getattr(document, "id", "") or "").strip()
                for document in tuple(getattr(pack, "documents", ()) or ())
                if self._profile_document_matches_builtin_kind(document, kind)
            ]
            matched = [item for item in matched if item]
            if len(matched) > 1:
                raise ValueError(
                    f"Для кнопки «{kind}» в профиле найдено несколько документов с одной semantic role: "
                    + ", ".join(matched)
                    + ". Оставьте один role-владелец или выберите нужную пользовательскую кнопку напрямую."
                )
            if matched:
                routed.append(matched[0])
                self._log(f"\nℹ Кнопка «{kind}» создана через doctor-owned шаблон с явной semantic role.\n")
            else:
                remaining.append(kind)
        return remaining, list(dict.fromkeys([*selected_custom, *routed]))

    def _run_creation_jobs(self, selected_medical: list[str], selected_diaries: bool, selected_custom: list[str]) -> tuple[list[Path], list[Path], object | None, list[str]]:
        created_medical: list[Path] = []
        created_custom: list[Path] = []
        diary_result = None
        errors: list[str] = []
        try:
            try:
                selected_medical, selected_custom = self._route_legacy_medical_selection_to_profile_docs(selected_medical, selected_custom)
            except Exception as exc:
                errors.append(f"Маршрутизация документов профиля: {exc}")
                self._log(f"\n❌ Маршрутизация документов профиля: {exc}\n")
                return created_medical, created_custom, diary_result, errors
            if selected_medical:
                created_medical = self._create_medical_documents_with_stop(selected_medical, selected_diaries, created_custom, errors)
                if errors:
                    return created_medical, created_custom, diary_result, errors
            if selected_custom:
                try:
                    created_custom = self._create_custom_documents_impl(selected_custom)
                except Exception as exc:
                    record_classified_error("create_custom_documents", exc, category=ErrorCategory.DOCX_RENDER)
                    errors.append(f"Custom-документы профиля: {exc}")
                    self._log(f"\n❌ Custom-документы профиля: {exc}\n")
            if selected_diaries:
                try:
                    diary_result = self._create_diaries_impl()
                except Exception as exc:
                    record_classified_error("create_diaries", exc, category=ErrorCategory.DOCX_RENDER)
                    errors.append(f"Дневники: {exc}")
                    self._log(f"\n❌ Дневники: {exc}\n")
        finally:
            self._stop_progress()
        return created_medical, created_custom, diary_result, errors

    def _create_medical_documents_with_stop(self, selected_medical: list[str], selected_diaries: bool, created_custom: list[Path], errors: list[str]) -> list[Path]:
        try:
            return self._create_medical_documents_impl(selected_medical)
        except Exception as exc:
            record_classified_error("create_medical_documents", exc, category=ErrorCategory.DOCX_RENDER)
            errors.append(f"Медицинские документы: {exc}")
            self._log(f"\n❌ Медицинские документы не созданы: {exc}\n")
            self._write_creation_report(
                selected_medical=selected_medical,
                selected_diaries=selected_diaries,
                created_medical=[],
                diary_result=None,
                created_custom=created_custom,
                errors=errors,
            )
            messagebox.showerror(
                "Медицинские документы не созданы",
                "Вы отметили медицинские документы, но их создание остановилось с ошибкой:\n\n"
                f"{exc}\n\n"
                "Дневники после этого не запускались, чтобы не получилось частичное создание только одного типа документов.",
            )
            return []

    def _created_files_from_results(self, created_medical: list[Path], created_custom: list[Path], diary_result) -> list[Path]:
        created_files: list[Path] = list(created_medical)
        created_files.extend(created_custom)
        if diary_result is not None:
            created_files.extend(list(diary_result.created_files))
        return created_files


    def _show_created_document_preview(self, created_files: list[Path]) -> None:
        """Show a DOCX preview only when an explicit diagnostic flag is enabled.

        Production creation must not open an unsolicited modal window after the
        doctor has already passed the preflight and received saved files.  The old
        unconditional preview looked like a random popup in the normal workflow.
        Keep the helper as opt-in diagnostics for support sessions only.
        """
        enabled = os.environ.get("MEDICAL_AUTOFILL_SHOW_CREATED_PREVIEW", "").strip().lower() in {"1", "true", "yes", "on"}
        if os.environ.get("CI") or not enabled or not created_files:
            return
        first = Path(created_files[0])
        if first.suffix.lower() not in {".docx", ".docm"}:
            return
        try:
            from medical_docx_reader import extract_docx_text
            text = extract_docx_text(first)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            preview = "\n".join(lines[:20]) or "Документ создан, текстовое превью пустое."
            if len(preview) > 3500:
                preview = preview[:3500].rstrip() + "\n…"
            messagebox.showinfo("Превью созданного документа", f"{first.name}\n\n{preview}")
        except Exception as exc:
            record_classified_error("preview_created_document", exc, category=ErrorCategory.DOCX_RENDER, detail=str(first))

    def _print_created_files_if_requested(self, print_after: bool, created_files: list[Path]) -> None:
        if not print_after:
            return
        unique_files: list[Path] = []
        seen_print_paths: set[str] = set()
        for path in created_files:
            candidate = Path(path)
            try:
                key = str(candidate.resolve())
            except Exception as exc:
                record_soft_exception("actions_creation_execution.print_path_resolve", exc, detail=str(candidate))
                key = str(candidate.absolute())
            if key in seen_print_paths:
                continue
            seen_print_paths.add(key)
            unique_files.append(candidate)
        if not unique_files:
            return
        self._set_status("Отправляю документы на печать...")
        self.root.update_idletasks()
        from printer_support import print_files
        print_result = print_files(unique_files, self.printer_var.get().strip())
        if print_result.errors:
            try:
                record_classified_error("print_created_files", RuntimeError("; ".join(print_result.errors[:10])), category=ErrorCategory.PRINTER)
            except Exception as exc:
                record_soft_exception("actions_creation_execution.print_error_taxonomy", exc)
            messagebox.showwarning(
                "Создано, но печать с ошибками",
                "Файлы сохранены, но часть документов не удалось отправить на печать:\n\n" + "\n".join(print_result.errors[:10]),
            )

    def create_selected_outputs(self, *, print_after: bool = False) -> bool:
        if getattr(self, "_creation_in_progress", False):
            self._log("\n⚠ Создание уже запущено; повторное нажатие проигнорировано, чтобы документы не ушли на печать дважды.\n")
            return False
        self._creation_in_progress = True
        self._allow_missing_required_creation = False
        self._missing_required_override_fields = ()
        try:
            return self._create_selected_outputs_locked(print_after=print_after)
        finally:
            self._creation_in_progress = False

    def _create_selected_outputs_locked(self, *, print_after: bool = False) -> bool:
        """Create the selected patient output set as one filesystem transaction."""
        from dataclasses import replace
        from output_transaction import OutputTransaction

        selected = self._selected_outputs_or_warn()
        if selected is None:
            return False
        selected_medical, selected_diaries, selected_custom = selected
        # Resolve compatibility routing before preflight/collision planning so
        # required fields and duplicate targets describe the documents that will
        # actually be rendered.
        try:
            selected_medical, selected_custom = self._route_legacy_medical_selection_to_profile_docs(selected_medical, selected_custom)
        except Exception as exc:
            messagebox.showerror("Неоднозначный профиль документов", str(exc))
            return False
        self._active_patient_output_dir = None
        self._pending_output_commit = None
        self._planned_custom_output_format = None
        if not self._ensure_patient_folder_naming_configured():
            return False
        if not self._collect_creation_requirements(selected_medical, selected_diaries, selected_custom):
            return False

        review = self._build_patient_case_review_for_selection(selected_medical, selected_diaries, selected_custom)
        try:
            from doctor_action_journal import append_doctor_action
            append_doctor_action(
                output_dir=review.output_dir or self._result_output_dir(),
                action="Показана проверка перед созданием",
                review=review,
                details={"docs": ", ".join(self._selected_output_names(selected_medical, selected_diaries, selected_custom))},
                category="preflight",
            )
        except Exception as exc:
            record_soft_exception("actions_creation_execution.journal_preflight", exc)
        if not self._confirm_patient_case_before_creation(review):
            try:
                from doctor_action_journal import append_doctor_action
                append_doctor_action(output_dir=review.output_dir or self._result_output_dir(), action="Создание отменено на проверке", review=review, category="preflight")
            except Exception as exc:
                record_soft_exception("actions_creation_execution.journal_preflight_cancel", exc)
            return False

        review = self._build_patient_case_review_for_selection(selected_medical, selected_diaries, selected_custom)
        self._active_patient_output_dir = Path(review.output_dir)
        if selected_custom and hasattr(self, "_prepare_custom_document_output_format"):
            self._prepare_custom_document_output_format(selected_custom)
        if not self._apply_duplicate_policy(review, selected_medical, selected_custom, selected_diaries):
            self._active_patient_output_dir = None
            return False
        plan = dict(getattr(self, "_pending_output_commit", None) or {})
        final_dir = Path(plan.get("final_dir") or review.output_dir or self._result_output_dir()).expanduser()
        overwrite_paths = tuple(Path(item) for item in plan.get("overwrite_paths", ()))
        review = replace(review, output_dir=str(final_dir))
        self._last_patient_case_review = review
        self._active_patient_output_dir = final_dir

        if print_after and not self.printer_var.get().strip():
            if not self._select_default_printer_sync():
                self._active_patient_output_dir = final_dir
                messagebox.showwarning("Принтер не выбран", "Выберите принтер перед печатью или используйте кнопку сохранения без печати.")
                return False

        transaction = OutputTransaction(final_dir=final_dir, overwrite_paths=overwrite_paths)
        try:
            staging_dir = transaction.begin()
        except Exception as exc:
            self._active_patient_output_dir = final_dir
            messagebox.showerror("Не удалось начать создание", f"Не удалось подготовить безопасную временную папку:\n{exc}")
            return False

        self._active_patient_output_dir = staging_dir
        self._start_progress()
        try:
            created_medical, created_custom, diary_result, errors = self._run_creation_jobs(selected_medical, selected_diaries, selected_custom)
        except Exception as exc:
            transaction.rollback()
            self._active_patient_output_dir = final_dir
            record_classified_error("create_selected_outputs_transaction", exc, category=ErrorCategory.DOCX_RENDER)
            messagebox.showerror("Документы не созданы", f"Создание остановлено до изменения папки пациента:\n\n{exc}")
            return False

        staged_files = self._created_files_from_results(created_medical, created_custom, diary_result)
        if errors or not staged_files:
            transaction.rollback()
            self._active_patient_output_dir = final_dir
            if not errors:
                errors = ["Ничего не создано: выбранные документы не дали итоговых файлов. Проверьте шаблоны и повторите."]
            try:
                from doctor_action_journal import append_doctor_action
                append_doctor_action(output_dir=final_dir, action="Создание отменено без изменения готовых документов", review=review, errors=errors, category="error")
            except Exception as exc:
                record_soft_exception("actions_creation_execution.journal_errors", exc)
            self._write_creation_report(
                selected_medical=selected_medical, selected_diaries=selected_diaries,
                created_medical=[], diary_result=None, created_custom=[], errors=errors,
            )
            messagebox.showwarning("Документы не созданы", "Папка пациента оставлена без частичного комплекта:\n\n" + "\n".join(errors))
            self._set_status("Создание отменено: готовые документы не изменены")
            return False

        try:
            mapping = transaction.commit()
        except Exception as exc:
            transaction.rollback()
            self._active_patient_output_dir = final_dir
            record_classified_error("commit_output_transaction", exc, category=ErrorCategory.DOCX_RENDER)
            messagebox.showerror("Не удалось сохранить комплект", "Все временные файлы отменены; прежние документы восстановлены.\n\n" + str(exc))
            return False

        self._active_patient_output_dir = final_dir

        def committed_path(path: Path) -> Path:
            candidate = Path(path)
            direct = mapping.get(candidate)
            if direct is not None:
                return direct
            try:
                return final_dir / candidate.relative_to(staging_dir)
            except ValueError:
                return candidate

        created_medical = [committed_path(path) for path in created_medical]
        created_custom = [committed_path(path) for path in created_custom]
        if diary_result is not None:
            diary_result.created_files = [committed_path(path) for path in diary_result.created_files]
            if getattr(diary_result, "report_path", None):
                diary_result.report_path = committed_path(diary_result.report_path)
        created_files = self._created_files_from_results(created_medical, created_custom, diary_result)
        override_fields = tuple(getattr(self, "_missing_required_override_fields", ()) or ())
        details = {"print_after": "да" if print_after else "нет"}
        if override_fields:
            details["explicit_missing_override"] = ", ".join(override_fields)
        try:
            from doctor_action_journal import append_doctor_action
            append_doctor_action(
                output_dir=final_dir,
                action="Документы созданы с явно разрешёнными пропусками" if override_fields else "Документы созданы",
                review=review, created_files=created_files, details=details,
                category="warning" if override_fields else "created",
            )
        except Exception as exc:
            record_soft_exception("actions_creation_execution.journal_created", exc)

        self._print_created_files_if_requested(print_after, created_files)
        creation_report = self._write_creation_report(
            selected_medical=selected_medical, selected_diaries=selected_diaries,
            created_medical=created_medical, diary_result=diary_result, created_custom=created_custom, errors=None,
        )
        self._show_created_document_preview(created_files)
        opened_folder = self._open_output_folder_after_creation(created_files=created_files, creation_report=creation_report)
        if override_fields:
            self._set_status("Готово с явно разрешёнными пропусками")
            self._log("\n⚠ Комплект создан с явным разрешением врача оставить обязательные поля пустыми.\n")
        else:
            self._set_status("Готово: файлы сохранены")
            self._log("\n✅ Готово: файлы сохранены.{}\n".format(" Папка результата открыта." if opened_folder else ""))
        return True
