from __future__ import annotations

from tkinter import filedialog, messagebox


def open_pdf_template_import_dialog(app, *, parent=None) -> None:
    source_paths = filedialog.askopenfilenames(
        title="Select PDF document examples",
        filetypes=[("PDF", "*.pdf"), ("All files", "*.*")],
        parent=parent or getattr(app, "root", None),
    )
    if not source_paths:
        return
    try:
        pack = app._load_or_create_universal_pack()
        base_dir = app._universal_profile_path().parent
        from pdf_template_importer import import_pdf_templates_to_pack
        from universal_profiles import save_document_pack

        labels = import_pdf_templates_to_pack(pack, source_paths, base_dir)
        save_document_pack(pack, app._universal_profile_path(), backup_reason="pdf_template_import")
        try:
            app._refresh_custom_profile_tiles()
        except Exception as exc:
            from diagnostic_logging import record_soft_exception

            record_soft_exception("window_pdf_template_import.refresh", exc)
        messagebox.showinfo(
            "PDF",
            "Imported PDF document buttons: " + (", ".join(labels) if labels else "none"),
            parent=parent or getattr(app, "root", None),
        )
    except Exception as exc:
        messagebox.showerror("PDF", str(exc), parent=parent or getattr(app, "root", None))
