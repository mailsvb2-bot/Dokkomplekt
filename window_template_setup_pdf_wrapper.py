from __future__ import annotations

from tkinter import messagebox

from window_mapper_dialog import open_template_setup_center
from window_pdf_template_import import open_pdf_template_import_dialog


def open_template_setup_center_with_pdf(app, *, first_run: bool = False) -> None:
    parent = getattr(app, "root", None)
    try:
        use_pdf = messagebox.askyesno(
            "PDF or Word",
            "Add a PDF document example now?\n\nYes - select PDF.\nNo - open the usual Word template center.",
            parent=parent,
        )
    except Exception:
        use_pdf = False
    if use_pdf:
        open_pdf_template_import_dialog(app, parent=parent)
        return
    open_template_setup_center(app, first_run=first_run)
