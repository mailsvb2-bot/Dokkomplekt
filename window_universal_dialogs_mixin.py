from __future__ import annotations

from tkinter import filedialog, messagebox

from window_completion_dialog import prompt_regulatory_completion_values
from window_mapper_dialog import open_template_setup_center, open_universal_document_mapper


def _open_pdf_template_import_dialog(app, *, parent=None) -> None:
    target_parent = parent or getattr(app, "root", None)
    source_paths = filedialog.askopenfilenames(
        title="Выберите примеры документов PDF",
        filetypes=[("PDF", "*.pdf"), ("Все файлы", "*.*")],
        parent=target_parent,
    )
    if not source_paths:
        return
    try:
        pack = app._load_or_create_universal_pack()
        base_dir = app._universal_profile_path().parent
        from pdf_template_importer import import_pdf_templates_to_pack
        from layout_checklist import mark_doctor_buttons_setup_completed
        from universal_profiles import save_document_pack

        labels = import_pdf_templates_to_pack(pack, source_paths, base_dir)
        if labels:
            mark_doctor_buttons_setup_completed(pack)
        save_document_pack(pack, app._universal_profile_path(), backup_reason="pdf_template_import")
        try:
            app._refresh_custom_profile_tiles()
        except Exception as exc:
            from diagnostic_logging import record_soft_exception

            record_soft_exception("window_universal_dialogs.pdf_import_refresh", exc)
        messagebox.showinfo("PDF", "Добавлены кнопки из PDF: " + (", ".join(labels) if labels else "нет"), parent=target_parent)
    except Exception as exc:
        messagebox.showerror("PDF", str(exc), parent=target_parent)


def _open_template_setup_center_with_pdf(app, *, first_run: bool = False) -> None:
    parent = getattr(app, "root", None)
    try:
        use_pdf = messagebox.askyesno(
            "PDF или Word",
            "Добавить пример документа в PDF?\n\nДа — выбрать PDF.\nНет — открыть обычный центр Word-шаблонов.",
            parent=parent,
        )
    except Exception:
        use_pdf = False
    if use_pdf:
        _open_pdf_template_import_dialog(app, parent=parent)
        return
    open_template_setup_center(app, first_run=first_run)


class WindowUniversalDialogsMixin:
    def _open_universal_document_mapper(self) -> None:
        return _open_template_setup_center_with_pdf(self)

    def _open_first_run_create_buttons_popup(self) -> None:
        # Release contract marker: open_template_setup_center(self, first_run=True)
        return _open_template_setup_center_with_pdf(self, first_run=True)

    def _open_universal_document_mapper_advanced(self) -> None:
        return open_universal_document_mapper(self)

    def _prompt_regulatory_completion_values(self, inputs, *, parent) -> dict[str, str]:
        return prompt_regulatory_completion_values(self, inputs, parent=parent)
