from __future__ import annotations

from diagnostic_logging import record_soft_exception
import tkinter as tk

from app_config import ACCENT, BORDER, FIELD, TEXT


def _search_icd10_f(query: str, *, limit: int, language_id: str | None = "ru"):
    from icd10_f import search_icd10_f as _real_search_icd10_f
    return _real_search_icd10_f(query, limit=limit, language_id=language_id)


def _format_diagnosis(item, *, language_id: str | None = "ru") -> str:
    from icd10_f import format_diagnosis as _real_format_diagnosis
    return _real_format_diagnosis(item, language_id=language_id)

_NAVIGATION_KEYS = {
    "Up", "Left", "Right", "Return", "Escape", "Tab",
    "Shift_L", "Shift_R", "Control_L", "Control_R",
}


class DialogDiagnosisPopup:
    def __init__(self, owner: tk.Toplevel, root: tk.Misc, *, language_id: str | None = "ru") -> None:
        self.owner = owner
        self.root = root
        self.language_id = language_id or "ru"
        self.popup: tk.Toplevel | None = None
        self.listbox: tk.Listbox | None = None
        self.entry: tk.Entry | None = None
        self.var: tk.StringVar | None = None

    @staticmethod
    def is_diagnosis_label(label: str) -> bool:
        return "диагноз" in (label or "").strip().lower()

    def attach(self, entry: tk.Entry, var: tk.StringVar) -> None:
        self.entry = entry
        self.var = var
        entry.bind("<KeyRelease>", self.refresh, add="+")
        entry.bind("<Down>", self.focus_popup)
        entry.bind("<Return>", self.return_if_visible)
        entry.bind("<Escape>", lambda _event: self.hide())
        entry.bind("<FocusOut>", self.schedule_hide, add="+")

    def visible(self) -> bool:
        return bool(
            self.popup is not None
            and self.popup.winfo_exists()
            and self.popup.state() == "normal"
        )

    def hide(self) -> None:
        try:
            if self.popup is not None and self.popup.winfo_exists():
                self.popup.withdraw()
        except Exception as exc:
            record_soft_exception("dialog_fields_popup:56", exc)

    def choose(self, event=None) -> str:
        if self.listbox is None:
            return "break"
        if event is not None and getattr(event, "y", None) is not None:
            index = self.listbox.nearest(event.y)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(index)
            self.listbox.activate(index)
        selection = self.listbox.curselection()
        if selection:
            self.select(self.listbox.get(selection[0]))
        return "break"

    def select(self, value: str) -> None:
        if self.var is not None:
            self.var.set(value.strip())
        if self.entry is not None:
            self.entry.icursor(tk.END)
            self.entry.focus_set()
        self.hide()

    def show(self, values: list[str], *, keep_entry_focus: bool = True) -> None:
        if not values or self.entry is None:
            self.hide()
            return
        if self.popup is None or not self.popup.winfo_exists():
            self._build_popup()
        if self.listbox is None:
            return
        self._fill_list(values)
        self._position_popup(values)
        if keep_entry_focus:
            self.owner.after_idle(lambda: self.entry.focus_set() if self.entry is not None else None)

    def refresh(self, event=None) -> None:
        if event is not None and getattr(event, "keysym", "") in _NAVIGATION_KEYS:
            return
        query = self.var.get().strip() if self.var is not None else ""
        if not query:
            self.hide()
            return
        try:
            values = [_format_diagnosis(item, language_id=self.language_id) for item in _search_icd10_f(query, limit=24, language_id=self.language_id)]
        except Exception as exc:
            record_soft_exception("dialog_fields_popup.refresh", exc, detail=query[:120])
            self.hide()
            return
        if values:
            self.show(values, keep_entry_focus=True)
        else:
            self.hide()

    def focus_popup(self, _event=None) -> str:
        query = self.var.get().strip() if self.var is not None else ""
        if not query:
            self.hide()
            return "break"
        try:
            values = [_format_diagnosis(item, language_id=self.language_id) for item in _search_icd10_f(query, limit=12, language_id=self.language_id)]
        except Exception as exc:
            record_soft_exception("dialog_fields_popup.focus", exc, detail=query[:120])
            self.hide()
            return "break"
        if values:
            self.show(values, keep_entry_focus=False)
        if self.listbox is not None:
            self.listbox.focus_set()
            if not self.listbox.curselection() and self.listbox.size():
                self.listbox.selection_set(0)
                self.listbox.activate(0)
        return "break"

    def return_if_visible(self, _event=None):
        if self.visible() and self.listbox is not None:
            return self.choose()
        return None

    def schedule_hide(self, _event=None) -> None:
        self.owner.after(180, self.hide_if_focus_left)

    def hide_if_focus_left(self) -> None:
        try:
            focus = self.owner.focus_get() or self.root.focus_get()
        except Exception as exc:
            record_soft_exception("dialog_fields_popup.focus_get", exc)
            focus = None
        if focus in {self.entry, self.listbox}:
            return
        self.hide()

    def _build_popup(self) -> None:
        popup = tk.Toplevel(self.owner)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.configure(bg=BORDER)
        popup.transient(self.owner)
        frame = tk.Frame(popup, bg=BORDER, padx=1, pady=1)
        frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(
            frame,
            bg=FIELD,
            fg=TEXT,
            selectbackground=ACCENT,
            selectforeground="#03101f",
            activestyle="none",
            font=("Segoe UI", 9),
            height=6,
            bd=0,
            highlightthickness=0,
            exportselection=False,
        )
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<ButtonRelease-1>", self.choose)
        self.listbox.bind("<Return>", self.choose)
        self.listbox.bind("<Escape>", lambda _event: self.hide())
        self.listbox.bind("<FocusOut>", self.schedule_hide)
        self.popup = popup

    def _fill_list(self, values: list[str]) -> None:
        if self.listbox is None:
            return
        self.listbox.delete(0, tk.END)
        for value in values[:12]:
            self.listbox.insert(tk.END, value)
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(0)
        self.listbox.activate(0)

    def _position_popup(self, values: list[str]) -> None:
        if self.popup is None or self.entry is None:
            return
        rows_count = min(6, max(1, len(values[:12])))
        width_px = max(460, self.entry.winfo_width())
        height_px = rows_count * 22 + 4
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height() + 2
        self.popup.geometry(f"{width_px}x{height_px}+{x}+{y}")
        self.popup.deiconify()
        self.popup.lift()



def configure_required_popup_fields_dialog(app, parent, *, save_pack, refresh_main_tiles, refresh_view) -> None:
    """Let doctor mark extra custom medpack fields as required for generation popup."""
    from dataclasses import replace
    from tkinter import messagebox, simpledialog
    from universal_fields import FieldDefinition
    import hashlib

    def field_id_from_label(label: str) -> str:
        raw = str(label or "").strip().lower()
        slug = "".join(ch if ("a" <= ch <= "z" or ch.isdigit()) else "_" for ch in raw)
        slug = "_".join(part for part in slug.split("_") if part)
        return "custom." + (slug[:48] or ("field_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]))

    try:
        pack = app._load_or_create_universal_pack()
        documents = list(pack.documents)
        if not documents:
            messagebox.showwarning("Обязательные поля popup", "Сначала добавьте хотя бы одну кнопку документа в блок 03.", parent=parent)
            return
        choices = "\n".join(f"{i}. {doc.button_label}" for i, doc in enumerate(documents, 1))
        number_raw = simpledialog.askstring("Обязательные поля popup", "Для какой кнопки добавить обязательные поля?\n\n" + choices + "\n\nВведите номер кнопки:", parent=parent)
        if not number_raw:
            return
        index = int(str(number_raw).strip()) - 1
        if index < 0 or index >= len(documents):
            raise ValueError("Нет кнопки с таким номером.")
        selected_doc = documents[index]
        raw_fields = simpledialog.askstring(
            "Обязательные поля popup",
            "Введите дополнительные обязательные поля для popup — по одному в строке.\n\nЧтобы значение попало в документ, вставьте показанную метку в Word-шаблон.",
            parent=parent,
        )
        labels = [line.strip(" •-\t") for line in str(raw_fields or "").splitlines() if line.strip(" •-\t")]
        if not labels:
            return
        existing_defs = {definition.id: definition for definition in pack.custom_fields}
        field_ids: list[str] = []
        placeholder_lines: list[str] = []
        for label in labels:
            field_id = field_id_from_label(label)
            if field_id in existing_defs and existing_defs[field_id].label != label:
                field_id = "custom.field_" + hashlib.sha1(label.encode("utf-8")).hexdigest()[:8]
            existing_defs[field_id] = FieldDefinition(field_id, label, "custom", (label,), "text", "Дополнительное обязательное поле врача для popup", False)
            field_ids.append(field_id)
            placeholder_lines.append(f"{label}: {{{{{field_id}}}}}")
        pack.custom_fields = tuple(existing_defs.values())
        pack.documents = tuple(
            replace(doc, required_fields=tuple(dict.fromkeys([*doc.required_fields, *field_ids]))) if doc.id == selected_doc.id else doc
            for doc in pack.documents
        )
        save_pack(pack)
        refresh_main_tiles("required_popup_fields")
        refresh_view("Обязательные поля popup сохранены.")
        messagebox.showinfo("Обязательные поля popup", "Сохранено. Перед созданием программа спросит:\n\n" + "\n".join(placeholder_lines), parent=parent)
    except Exception as exc:
        messagebox.showerror("Обязательные поля popup", str(exc), parent=parent)
