from __future__ import annotations

import tkinter as tk
import sys
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app_config import DEEP, MUTED, TEXT
from diagnostic_logging import record_soft_exception
from i18n_strings import tr
from medical_language_catalog import language_choices, language_id_from_choice, language_profile

class WindowChromeMixin:
    def _install_text_shortcuts(self) -> None:
        """Нормальные Ctrl+A/C/V/X во всех полях, включая popup-окна.

        На Windows с русской раскладкой Tkinter иногда видит Ctrl+C не как
        латинскую C, а как Cyrillic_es. Поэтому ловим общий Control-KeyPress
        и вызываем стандартные виртуальные события Entry вручную.
        """
        for cls in ("Entry", "TEntry"):
            try:
                self.root.bind_class(cls, "<Control-KeyPress>", self._entry_control_shortcut, add="+")
            except tk.TclError as exc:
                record_soft_exception("window_mixin:119", exc)

    def _entry_control_shortcut(self, event) -> str | None:
        widget = getattr(event, "widget", None)
        if widget is None:
            return None
        keysym = str(getattr(event, "keysym", "")).lower()
        char = str(getattr(event, "char", "")).lower()
        keycode = getattr(event, "keycode", None)

        def is_key(*names: str, codes: int = -1) -> bool:
            return keysym in names or char in names or (codes != -1 and keycode == codes)

        try:
            if is_key("a", "ф", "cyrillic_ef", codes=65):
                widget.selection_range(0, tk.END)
                widget.icursor(tk.END)
                return "break"
            if is_key("c", "с", "cyrillic_es", codes=67):
                widget.event_generate("<<Copy>>")
                return "break"
            if is_key("v", "м", "cyrillic_em", codes=86):
                widget.event_generate("<<Paste>>")
                return "break"
            if is_key("x", "ч", "cyrillic_che", codes=88):
                widget.event_generate("<<Cut>>")
                return "break"
        except tk.TclError:
            return None
        return None

    def _apply_custom_window_chrome(self) -> None:
        """Apply custom chrome only where restore/minimize is reliable.

        On Windows, Tk + overrideredirect windows can become non-restorable
        after minimize from a frameless window.  Reliability is more important
        than a decorative frame, so Windows keeps the native shell frame.
        """
        if sys.platform.startswith("win"):
            try:
                self.root.overrideredirect(False)
            except tk.TclError as exc:
                record_soft_exception("window_mixin:156_win_native", exc)
            return
        try:
            if self.root.state() == "normal":
                self.root.overrideredirect(True)
        except tk.TclError as exc:
            record_soft_exception("window_mixin:156", exc)

    def _disable_custom_window_chrome(self) -> None:
        """Return a normal Windows shell frame before minimizing.

        Tk/Windows плохо сворачивает окно с overrideredirect(True): приложение может
        исчезать из обычной цепочки окон или не разворачиваться обратно с панели
        задач. Поэтому перед minimize временно возвращаем системную рамку и даём
        Windows реально зарегистрировать окно как обычное shell-window.
        """
        try:
            self.root.overrideredirect(False)
            self.root.update_idletasks()
            # На Windows одного update_idletasks() иногда мало: оболочка ещё не
            # успевает вернуть окно в Alt-Tab/taskbar, и restore после сворачивания
            # выглядит как «программа не разворачивается». Полный update здесь
            # безопасен: он выполняется только по нажатию кнопки свернуть.
            self.root.update()
        except tk.TclError as exc:
            record_soft_exception("window_mixin:170", exc)

    def _restore_custom_window_chrome_after_map(self) -> None:
        try:
            if self.root.state() != "normal":
                return
            self.root.overrideredirect(True)
            self.root.update_idletasks()
            self._custom_chrome_restore_pending = False
            self._custom_chrome_restore_job = None
        except tk.TclError as exc:
            record_soft_exception("window_mixin:180", exc)

    def _schedule_custom_chrome_restore(self) -> None:
        if sys.platform.startswith("win"):
            self._custom_chrome_restore_pending = False
            self._custom_chrome_restore_job = None
            return
        try:
            old_job = getattr(self, "_custom_chrome_restore_job", None)
            if old_job:
                try:
                    self.root.after_cancel(old_job)
                except tk.TclError as exc:
                    record_soft_exception("window_mixin:restore_cancel", exc)
            # Не включаем overrideredirect прямо в <Map>: Windows ещё завершает
            # restore из панели задач. Небольшая задержка убирает эффект, когда
            # окно «возвращается» в невидимое/неактивируемое состояние.
            self._custom_chrome_restore_job = self.root.after(350, self._restore_custom_window_chrome_after_map)
        except tk.TclError as exc:
            record_soft_exception("window_mixin:188", exc)

    def _on_root_mapped(self, event) -> None:
        if getattr(event, "widget", None) is not self.root:
            return
        try:
            if sys.platform.startswith("win"):
                # Windows must keep a native shell frame after restore.  Do not
                # re-enable overrideredirect here: that is the classic Tk cause
                # of «свернул и больше не разворачивается».
                self.root.overrideredirect(False)
                if self.root.state() == "normal":
                    self.root.after(60, self._raise_restored_window_safely)
                self._custom_chrome_restore_pending = False
                return
            if not getattr(self, "_custom_chrome_restore_pending", False):
                return
            if self.root.state() == "normal":
                self._schedule_custom_chrome_restore()
        except tk.TclError as exc:
            record_soft_exception("window_mixin:191", exc)

    def _raise_restored_window_safely(self) -> None:
        """Best-effort focus after restoring from the Windows taskbar."""

        try:
            if self.root.state() == "normal":
                self.root.lift()
                self.root.focus_force()
        except tk.TclError as exc:
            record_soft_exception("window_mixin.restore_focus", exc)

    def _bind_window_drag(self, widget) -> None:
        widget.bind("<ButtonPress-1>", self._start_window_drag, add="+")
        widget.bind("<B1-Motion>", self._move_window_drag, add="+")

    def _start_window_drag(self, event) -> None:
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _move_window_drag(self, event) -> None:
        if self._is_maximized:
            return
        x = self.root.winfo_pointerx() - self._drag_start_x
        y = self.root.winfo_pointery() - self._drag_start_y
        self.root.geometry(f"+{x}+{y}")

    def _minimize_window(self) -> None:
        try:
            if sys.platform.startswith("win"):
                self._custom_chrome_restore_pending = False
                self.root.overrideredirect(False)
                self.root.update()
                self.root.state("iconic")
                return
            self._custom_chrome_restore_pending = True
            self._disable_custom_window_chrome()
            self.root.iconify()
        except tk.TclError:
            try:
                self.root.overrideredirect(False)
                self.root.update()
                self.root.state("iconic")
            except tk.TclError as exc:
                record_soft_exception("window_mixin:217", exc)

    def _toggle_maximize(self) -> None:
        try:
            if self._is_maximized:
                self.root.geometry(self._normal_geometry)
                self._is_maximized = False
                return
            self._normal_geometry = self.root.geometry()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            self.root.geometry(f"{sw}x{sh}+0+0")
            self._is_maximized = True
        except tk.TclError as exc:
            record_soft_exception("window_mixin:231", exc)

    def _window_control_button(self, parent, text: str, command, *, danger: bool = False) -> tk.Canvas:
        width, height = self._px(48, 34), self._px(32, 24)
        c = tk.Canvas(parent, width=width, height=height, bg=DEEP, highlightthickness=0, bd=0, cursor="hand2")
        def draw(active: bool = False) -> None:
            c.delete("all")
            bg = "#2c1018" if danger and active else ("#0d1b2a" if active else DEEP)
            fg = "#ff8ba0" if danger and active else (TEXT if active else MUTED)
            c.create_rectangle(0, 0, width, height, fill=bg, outline=bg)
            c.create_text(width // 2, height // 2 - 1, text=text, fill=fg, font=self._font(18 if text == "×" else 14))
        draw(False)
        c.bind("<Enter>", lambda _e: draw(True))
        c.bind("<Leave>", lambda _e: draw(False))
        c.bind("<Button-1>", lambda _e: command())
        return c
