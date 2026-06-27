from __future__ import annotations

"""Runtime enforcement of Dokkomplekt product plans inside creation workflow."""

from pathlib import Path
from tkinter import messagebox

from diagnostic_logging import record_soft_exception
from product_watermark import apply_watermark_to_files


class ProductAccessMixin:
    """Wrap document creation with local licensing, limits and watermark policy."""

    def _estimate_selected_document_count(self, selected_medical: list[str], selected_diaries: bool, selected_custom: list[str]) -> int:
        # Diary generation may produce several files, but at the access boundary we
        # reserve one minimum unit before creation and record exact output count
        # after successful generation.
        return max(1, len(selected_medical or []) + len(selected_custom or []) + (1 if selected_diaries else 0))

    def create_selected_outputs(self, *, print_after: bool = False) -> None:
        from product_licensing import ProductAccessManager

        selected = self._selected_outputs_or_warn()
        if selected is None:
            return
        selected_medical, selected_diaries, selected_custom = selected
        estimated_count = self._estimate_selected_document_count(selected_medical, selected_diaries, selected_custom)
        manager = self._product_access_manager() if hasattr(self, "_product_access_manager") else ProductAccessManager()
        decision = manager.check_document_creation(estimated_count)
        if not decision.allowed:
            messagebox.showwarning(decision.title, decision.message)
            try:
                self._log(f"\n⚠ {decision.title}: {decision.message}\n")
            except Exception as exc:
                record_soft_exception("product_access.log_denied", exc)
            return
        if decision.warning:
            try:
                self._log(f"\n⚠ Лицензия: {decision.warning}\n")
            except Exception as exc:
                record_soft_exception("product_access.log_warning", exc)
        return super().create_selected_outputs(print_after=print_after)

    def _created_files_from_results(self, created_medical: list[Path], created_custom: list[Path], diary_result):
        from product_licensing import ProductAccessManager

        created_files = super()._created_files_from_results(created_medical, created_custom, diary_result)
        if not created_files:
            return created_files
        manager = self._product_access_manager() if hasattr(self, "_product_access_manager") else ProductAccessManager()
        watermark = manager.current_watermark_text()
        if watermark:
            result = apply_watermark_to_files(created_files, watermark)
            if result.errors:
                try:
                    self._log("\n⚠ Водяной знак trial/demo применён не ко всем документам:\n" + "\n".join(result.errors[:10]) + "\n")
                except Exception as exc:
                    record_soft_exception("product_access.watermark_log", exc)
        try:
            manager.record_created_documents(len(created_files))
        except Exception as exc:
            record_soft_exception("product_access.record_created_documents", exc)
        return created_files
