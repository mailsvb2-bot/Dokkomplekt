from __future__ import annotations

"""Doctor-facing product license dialog for the local desktop app."""

import tkinter as tk
from tkinter import filedialog, messagebox

from product_licensing import ProductAccessManager


class ProductLicenseMixin:
    def _initialize_app(self, root: tk.Tk) -> None:
        # Product licensing is intentionally attached after the normal UI boot so
        # the existing doctor workflow stays unchanged.
        super()._initialize_app(root)
        self._install_product_license_entrypoints()

    def _install_product_license_entrypoints(self) -> None:
        try:
            self.root.bind_all("<Control-l>", lambda _event: self.show_product_license_dialog())
            self.root.bind_all("<Control-L>", lambda _event: self.show_product_license_dialog())
        except Exception:
            pass

    def _product_access_manager(self) -> ProductAccessManager:
        return ProductAccessManager()

    def show_product_license_dialog(self) -> None:
        """Open a small local-only license/access dialog.

        The dialog shows plan, limits and usage counters and lets the doctor/IT
        paste or load an offline license JSON. It never displays patient data.
        """

        manager = self._product_access_manager()
        window = tk.Toplevel(self.root)
        window.title("Лицензия Dokkomplekt")
        window.transient(self.root)
        window.grab_set()
        window.geometry("620x520")
        window.minsize(560, 460)

        outer = tk.Frame(window, padx=16, pady=14)
        outer.pack(fill="both", expand=True)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(1, weight=1)

        tk.Label(outer, text="Лицензия и лимиты продукта", font=("Segoe UI", 13, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")

        summary = tk.Text(outer, height=11, wrap="word")
        summary.grid(row=1, column=0, sticky="nsew", pady=(10, 10))
        summary.configure(state="normal")
        summary.insert("1.0", manager.summary_text())
        summary.configure(state="disabled")

        tk.Label(
            outer,
            text=(
                "Для offline-активации вставьте JSON лицензии или загрузите .json файл. "
                "Программа проверяет доступ локально и не отправляет документы пациента наружу."
            ),
            justify="left",
            wraplength=560,
            anchor="w",
        ).grid(row=2, column=0, sticky="ew", pady=(0, 8))

        license_text = tk.Text(outer, height=7, wrap="word")
        license_text.grid(row=3, column=0, sticky="ew")

        buttons = tk.Frame(outer)
        buttons.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        for column in range(4):
            buttons.grid_columnconfigure(column, weight=1)

        def refresh() -> None:
            nonlocal manager
            manager = self._product_access_manager()
            summary.configure(state="normal")
            summary.delete("1.0", "end")
            summary.insert("1.0", manager.summary_text())
            summary.configure(state="disabled")

        def install_from_text() -> None:
            raw = license_text.get("1.0", "end").strip()
            if not raw:
                messagebox.showwarning("Лицензия", "Вставьте JSON лицензии или загрузите файл лицензии.")
                return
            try:
                manager.install_license_text(raw)
                refresh()
                messagebox.showinfo("Лицензия", "Лицензия установлена.")
            except Exception as exc:
                messagebox.showerror("Лицензия не установлена", str(exc))

        def load_file() -> None:
            path = filedialog.askopenfilename(
                title="Выберите файл лицензии",
                filetypes=(("License JSON", "*.json"), ("All files", "*.*")),
            )
            if not path:
                return
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = fh.read()
                license_text.delete("1.0", "end")
                license_text.insert("1.0", data)
            except OSError as exc:
                messagebox.showerror("Лицензия", f"Не удалось прочитать файл лицензии:\n{exc}")

        tk.Button(buttons, text="Загрузить файл", command=load_file).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        tk.Button(buttons, text="Установить", command=install_from_text).grid(row=0, column=1, sticky="ew", padx=(0, 6))
        tk.Button(buttons, text="Обновить", command=refresh).grid(row=0, column=2, sticky="ew", padx=(0, 6))
        tk.Button(buttons, text="Закрыть", command=window.destroy).grid(row=0, column=3, sticky="ew")
