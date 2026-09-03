from __future__ import annotations

from pathlib import Path
from typing import List


class ActionsDocumentIntelligenceFlowMixin:
    def _missing_custom_completion_inputs(self, current_pack, case, selected_custom_ids: List[str]):
        missing: list[str] = []
        inferred_missing = []
        selected = {str(item).strip() for item in selected_custom_ids if str(item).strip()}
        try:
            base_dir = self._universal_profile_path().parent
        except Exception as exc:
            from diagnostic_logging import record_soft_exception

            record_soft_exception("actions_document_intelligence.profile_base", exc)
            base_dir = None
        for document in current_pack.documents:
            if selected and document.id not in selected:
                continue
            from universal_template_engine import missing_required_fields
            from universal_document_principles import missing_fields_from_principles

            missing.extend(missing_required_fields(case, document))
            inferred_missing.extend(missing_fields_from_principles(case, document, base_dir=base_dir))
        from regulatory_completion_blocks import completion_inputs_for_missing_fields
        from universal_document_principles import completion_inputs_from_inferred_fields

        inputs = list(
            completion_inputs_for_missing_fields(
                tuple(dict.fromkeys(missing)),
                registry=current_pack.registry(),
                existing_case=case,
                reason_prefix="Не заполнено обязательное поле",
            )
        )
        inputs.extend(
            completion_inputs_from_inferred_fields(
                tuple(inferred_missing),
                existing_case=case,
                reason_prefix="Шаблон документа требует поле",
            )
        )
        dedup = {}
        for item in inputs:
            dedup.setdefault(item.field_id, item)
        return tuple(dedup.values())

    def _prepare_custom_document_output_format(self, selected_custom_ids: List[str]) -> str:
        """Choose the regular custom-document format once for the whole transaction."""
        self._planned_custom_output_format = "docx"
        if not selected_custom_ids:
            return "docx"
        current_pack = self._load_or_create_universal_pack()
        _diary_ids, regular_ids = self._split_custom_diary_document_ids(current_pack, selected_custom_ids)
        if regular_ids:
            self._planned_custom_output_format = self._ask_custom_document_output_format()
        return self._planned_custom_output_format

    def _ask_custom_document_output_format(self) -> str:
        try:
            from tkinter import messagebox
            wants_pdf = messagebox.askyesno(
                "Формат результата",
                "Создать выбранные документы из ваших шаблонов в PDF?\n\nДа — PDF.\nНет — Word/DOCX.",
                parent=getattr(self, "root", None),
            )
            return "pdf" if wants_pdf else "docx"
        except Exception as exc:
            from diagnostic_logging import record_soft_exception

            record_soft_exception("actions_document_intelligence.output_format_popup", exc)
            return "docx"

    def _create_regular_custom_documents(self, current_pack, case, regular_ids: List[str], out_dir) -> List[Path]:
        from medical_formatting import technical_report_path
        from universal_generation import render_documents_from_pack, save_generation_report

        output_format = str(getattr(self, "_planned_custom_output_format", "") or "").strip().lower()
        if output_format not in {"docx", "pdf"}:
            output_format = self._ask_custom_document_output_format()
        result = render_documents_from_pack(
            pack=current_pack,
            case=case,
            document_ids=regular_ids,
            output_dir=out_dir,
            base_dir=self._universal_profile_path().parent,
            strict=not bool(getattr(self, "_allow_missing_required_creation", False)),
            output_language=self._effective_output_language(),
            spellcheck_enabled=bool(getattr(self, "spellcheck_enabled_var", None) and self.spellcheck_enabled_var.get()),
            output_format="docx",
        )
        created_paths = [Path(item) for item in result.created_files]
        if output_format == "pdf" and created_paths:
            watermark_before_pdf = getattr(self, "_apply_product_watermark_before_pdf_export", None)
            if callable(watermark_before_pdf):
                watermark_before_pdf(created_paths)
            created_paths = self._export_custom_documents_to_pdf(created_paths)
        report_path = save_generation_report(result, technical_report_path(out_dir, "custom_profile_generation_report.txt")) if self._diagnostic_reports_enabled() else None
        if result.skipped_documents:
            self._log("\n⚠ Документы из ваших шаблонов пропущены:\n")
            for item in result.skipped_documents:
                self._log(f"- {item}\n")
        if result.warnings:
            self._log("\n⚠ Документы из ваших шаблонов созданы с предупреждениями:\n")
            for warning in result.warnings:
                self._log(f"- {warning}\n")
        if created_paths:
            self._log("\n✅ Созданы документы из ваших шаблонов:\n")
            for path in created_paths:
                self._log(f"- {path}\n")
        if result.skipped_documents:
            raise ValueError("Не удалось создать полный комплект документов из ваших шаблонов: " + "; ".join(str(item) for item in result.skipped_documents[:5]))
        if self._diagnostic_reports_enabled() and report_path is not None:
            self._log(f"Технический отчёт по вашим шаблонам: {report_path}\n")
        return created_paths

    def _export_custom_documents_to_pdf(self, paths: List[Path]) -> List[Path]:
        from document_output_format import export_docx_to_pdf

        exported: list[Path] = []
        errors: list[str] = []
        for path in paths:
            try:
                pdf_path = export_docx_to_pdf(path)
                exported.append(pdf_path)
                if pdf_path != path:
                    path.unlink()
            except Exception as exc:
                from diagnostic_logging import record_soft_exception

                record_soft_exception("actions_document_intelligence.pdf_export", exc, detail=str(path))
                errors.append(f"{path.name}: {exc}")
        if errors:
            raise RuntimeError(
                "Выбран формат PDF, но PDF не удалось создать. Комплект не будет опубликован:\n"
                + "\n".join(errors[:10])
            )
        return exported
