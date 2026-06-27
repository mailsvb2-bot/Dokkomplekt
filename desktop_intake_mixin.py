from __future__ import annotations

from medical_date_state import current_semantic_date

from diagnostic_logging import record_soft_exception
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from app_config import (
    ACCENT_2,
    DEEP,
    DIARY_KIND,
    DIARY_LABEL,
    FIELD,
    MUTED,
    PANEL,
    PANEL_3,
    TEXT,
    WARN,
)
from medical_constants import DOCUMENT_LABELS, DOCUMENT_ORDER


class DesktopIntakeMixin:
    def _init_desktop_intake_state(self) -> None:
        from desktop_intake import normalize_intake_settings
        settings = normalize_intake_settings(self._settings.get("desktop_intake"))
        self._desktop_intake_enabled = bool(settings["enabled"])
        self._desktop_intake_asked = bool(settings["asked"])
        self._desktop_intake_folder = str(settings["folder"])
        self._desktop_intake_prompt_version = str(settings.get("prompt_version", "") or "")
        self._desktop_intake_seen_signatures: set[str] = set(settings.get("seen_signatures", ()))
        self._desktop_intake_poll_job = None
        self._desktop_intake_popup_open = False
        self._desktop_intake_last_popup_opened = False
        self._desktop_intake_popup_outcome = ""
        self._desktop_intake_gui_lock_job = None

    def _desktop_intake_settings_payload(self) -> dict:
        return {
            "asked": bool(getattr(self, "_desktop_intake_asked", False)),
            "enabled": bool(getattr(self, "_desktop_intake_enabled", False)),
            "folder": str(getattr(self, "_desktop_intake_folder", "") or ""),
            "prompt_version": str(getattr(self, "_desktop_intake_prompt_version", "") or ""),
            "seen_signatures": sorted(getattr(self, "_desktop_intake_seen_signatures", set()))[-300:],
        }

    def _persist_desktop_intake_settings(self) -> None:
        """Persist only the desktop-intake technical preference.

        This method intentionally writes through the common settings store
        instead of calling itself: the startup prompt must be shown once on a
        clean profile, then the doctor's Yes/No answer must survive restarts.
        """
        self._settings["desktop_intake"] = self._desktop_intake_settings_payload()
        self._save_settings()

    def _bootstrap_desktop_intake_watcher(self) -> None:
        self._start_gui_runtime_lock()
        try:
            from desktop_intake import should_prompt_intake_setup
            if should_prompt_intake_setup(self._desktop_intake_settings_payload()):
                self._ask_create_desktop_intake_folder()
            if getattr(self, "_desktop_intake_enabled", False):
                self._ensure_background_intake_agent_installed(start_now=True)
                self._start_desktop_intake_watcher()
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin:38", exc)


    def _start_gui_runtime_lock(self) -> None:
        """Publish a lightweight heartbeat so the background agent does not open a second GUI."""
        if getattr(self, "_desktop_intake_gui_lock_job", None) is not None:
            return
        self._refresh_gui_runtime_lock()
        try:
            self.root.protocol("WM_DELETE_WINDOW", self._close_app_with_runtime_lock_release)
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin.gui_lock_close_protocol", exc)

    def _refresh_gui_runtime_lock(self) -> None:
        try:
            from desktop_intake_agent import write_gui_runtime_lock
            write_gui_runtime_lock()
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin.gui_runtime_lock", exc)
        try:
            self._desktop_intake_gui_lock_job = self.root.after(5000, self._refresh_gui_runtime_lock)
        except Exception as exc:
            self._desktop_intake_gui_lock_job = None
            record_soft_exception("desktop_intake_mixin.gui_runtime_lock_after", exc)

    def _close_app_with_runtime_lock_release(self) -> None:
        try:
            from desktop_intake_agent import release_gui_runtime_lock
            release_gui_runtime_lock()
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin.gui_runtime_lock_release", exc)
        try:
            self.root.destroy()
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin.root_destroy", exc)


    def _ask_create_desktop_intake_folder(self) -> None:
        from desktop_intake import DESKTOP_INTAKE_SETUP_PROMPT_VERSION, prompt_intake_folder
        folder = prompt_intake_folder(getattr(self, "_desktop_intake_folder", "")).expanduser()
        try:
            self.root.lift()
            self.root.focus_force()
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin:prompt_focus", exc)
        answer = messagebox.askyesno(
            "Папка «Выписанные пациенты»",
            "Создать на рабочем столе папку «Выписанные пациенты»?\n\n"
            "Врач сможет перетащить туда первичный документ, а программа предложит "
            "создать нужные документы в отдельной подпапке пациента.\n\n"
            "Чтобы это срабатывало даже при закрытом окне программы, программа сама включит "
            "безопасный фоновый watcher в автозагрузке Windows. Это обычный ярлык автозапуска, "
            "без службы Windows и без опасных перехватчиков мыши/клавиатуры.",
            parent=self.root,
        )
        self._desktop_intake_asked = True
        self._desktop_intake_prompt_version = DESKTOP_INTAKE_SETUP_PROMPT_VERSION
        if answer:
            try:
                folder.mkdir(parents=True, exist_ok=True)
                self._desktop_intake_enabled = True
                self._desktop_intake_folder = str(folder)
                self._log(f"\n✅ Папка «Выписанные пациенты» включена: {folder}\n")
            except Exception as exc:
                self._desktop_intake_enabled = False
                self._desktop_intake_folder = str(folder)
                messagebox.showerror(
                    "Папка «Выписанные пациенты»",
                    f"Не удалось создать папку:\n{folder}\n\n{exc}",
                    parent=self.root,
                )
                record_soft_exception("desktop_intake_mixin:create_folder", exc, detail=str(folder))
        else:
            self._desktop_intake_enabled = False
            self._desktop_intake_folder = str(folder)
        self._persist_desktop_intake_settings()
        # Background agent is installed once by _bootstrap_desktop_intake_watcher after settings are persisted.

    def _ensure_background_intake_agent_installed(self, *, start_now: bool = True) -> bool:
        """Install/start the optional watcher so closed-app intake really works.

        A closed GUI cannot watch the folder by itself.  Earlier builds only
        told the doctor to run a BAT file, so the feature looked broken in real
        use.  This method performs the same safe per-user Startup shortcut setup
        automatically after the doctor agrees to the «Выписанные пациенты»
        workflow.  On non-Windows/source CI it is a harmless no-op.
        """

        try:
            from desktop_intake_agent import install_agent_autostart

            ok, message = install_agent_autostart(start_now=start_now)
            if ok:
                self._log("\n✅ Фоновый watcher включён в автозагрузке Windows и запущен.\n")
                return True
            # Source/Linux tests legitimately return a no-op.  Keep this as a
            # diagnostic line, not a blocking popup, because the in-process
            # watcher still handles the folder while the UI is open.
            self._log(f"\nℹ Фоновый watcher не установлен автоматически: {message}\n")
            return False
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin.install_background_agent", exc)
            self._log(f"\n⚠ Не удалось автоматически включить watcher: {exc}\n")
            return False

    def _start_desktop_intake_watcher(self) -> None:
        if getattr(self, "_desktop_intake_poll_job", None) is not None:
            return
        folder = Path(getattr(self, "_desktop_intake_folder", "")).expanduser()
        try:
            if not folder.exists():
                folder.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self._desktop_intake_enabled = False
            self._persist_desktop_intake_settings()
            messagebox.showerror(
                "Папка «Выписанные пациенты»",
                f"Не удалось открыть или создать папку:\n{folder}\n\n{exc}",
                parent=self.root,
            )
            record_soft_exception("desktop_intake_mixin:start_watcher_folder", exc, detail=str(folder))
            return
        self._poll_desktop_intake_folder()

    def _poll_desktop_intake_folder(self) -> None:
        try:
            from desktop_intake import mark_seen, scan_primary_candidates
            if not getattr(self, "_desktop_intake_enabled", False):
                self._desktop_intake_poll_job = None
                return
            if not getattr(self, "_desktop_intake_popup_open", False):
                candidates = scan_primary_candidates(self._desktop_intake_folder, self._desktop_intake_seen_signatures)
                if candidates:
                    candidate = candidates[0]
                    self._desktop_intake_last_popup_opened = False
                    self._desktop_intake_popup_outcome = ""
                    processed = self._open_desktop_intake_popup(candidate.path)
                    outcome = str(getattr(self, "_desktop_intake_popup_outcome", "") or "")
                    # Mark the dropped file only after a real terminal outcome.
                    # "setup_needed" is deliberately not terminal: if the doctor
                    # must first create block-03 buttons, the same primary DOCX
                    # should be offered again after setup, not silently disappear.
                    terminal_close = outcome in {"processed", "ignored"} or (
                        outcome in {"", "opened"} and bool(getattr(self, "_desktop_intake_last_popup_opened", False))
                    )
                    if processed or terminal_close:
                        mark_seen(self._desktop_intake_seen_signatures, candidate)
                        self._persist_desktop_intake_settings()
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin:83", exc)
        finally:
            if not getattr(self, "_desktop_intake_enabled", False):
                self._desktop_intake_poll_job = None
                return
            try:
                self._desktop_intake_poll_job = self.root.after(2500, self._poll_desktop_intake_folder)
            except Exception as exc:
                self._desktop_intake_poll_job = None
                record_soft_exception("desktop_intake_mixin:88", exc)

    def _activate_window_for_desktop_intake(self) -> None:
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin:96", exc)

    def _apply_desktop_intake_selected_kinds(self, selected_kinds: set[str]) -> None:
        """Apply the desktop-intake popup selection as an isolated choice.

        Desktop intake is a separate patient workflow.  It must not inherit
        stale checkboxes from the main window; otherwise a previously selected
        document can be generated for the next dropped patient without being
        shown in the popup.
        """
        for var in list(getattr(self, "output_vars", {}).values()):
            try:
                var.set(False)
            except Exception as exc:
                record_soft_exception("desktop_intake_mixin:clear_output_var", exc)
        for kind in selected_kinds:
            if kind not in self.output_vars:
                try:
                    self.output_vars[kind] = self.custom_output_vars.get(kind) or tk.BooleanVar(value=False)
                    self.custom_output_vars[kind] = self.output_vars[kind]
                except Exception as exc:
                    record_soft_exception("desktop_intake_mixin:create_custom_var", exc)
                    continue
            try:
                self.output_vars[kind].set(True)
            except Exception as exc:
                record_soft_exception("desktop_intake_mixin:set_selected_output", exc, detail=kind)
        try:
            self._update_selected_outputs_status()
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin:update_selected_status", exc)

    def _close_desktop_intake_popup(self, popup) -> None:
        """Close the intake selection popup without leaving a modal grab behind."""
        try:
            popup.grab_release()
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin.popup_grab_release", exc)
        try:
            popup.withdraw()
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin.popup_withdraw", exc)
        try:
            popup.destroy()
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin.popup_destroy", exc)


    def _build_desktop_intake_scroll_body(self, popup: tk.Toplevel) -> tuple[tk.Frame, object]:
        """Create scrollable intake body while keeping the footer buttons fixed."""
        body_outer = tk.Frame(popup, bg=PANEL, padx=12, pady=12)
        body_outer.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 12))
        body_outer.grid_columnconfigure(0, weight=1)
        body_outer.grid_rowconfigure(0, weight=1)
        popup.grid_rowconfigure(1, weight=1)
        body_canvas = tk.Canvas(body_outer, bg=PANEL, highlightthickness=0, borderwidth=0)
        body_scroll = ttk.Scrollbar(body_outer, orient="vertical", command=body_canvas.yview)
        body_canvas.configure(yscrollcommand=body_scroll.set)
        body_canvas.grid(row=0, column=0, sticky="nsew")
        body_scroll.grid(row=0, column=1, sticky="ns")
        body = tk.Frame(body_canvas, bg=PANEL)
        body_id = body_canvas.create_window((0, 0), window=body, anchor="nw")

        def sync_body_scroll(_event=None) -> None:
            try:
                body_canvas.configure(scrollregion=body_canvas.bbox("all"))
                body_canvas.itemconfigure(body_id, width=body_canvas.winfo_width())
            except tk.TclError as exc:
                record_soft_exception("desktop_intake_mixin.scroll_region", exc)

        def intake_wheel(event) -> None:
            try:
                delta = -1 if getattr(event, "delta", 0) > 0 else 1
                body_canvas.yview_scroll(delta, "units")
            except tk.TclError as exc:
                record_soft_exception("desktop_intake_mixin.scroll_wheel", exc)

        body.bind("<Configure>", sync_body_scroll)
        body_canvas.bind("<Configure>", sync_body_scroll)
        body.bind("<MouseWheel>", intake_wheel)
        body_canvas.bind("<MouseWheel>", intake_wheel)
        return body, intake_wheel


    def _prepare_desktop_intake_patient_folder(self, primary: Path) -> None:
        """Move dropped primary DOCX into a patient folder named by doctor settings."""

        from desktop_patient_folder import folder_naming_uses_discharge_date

        settings = self._folder_naming_settings()
        if folder_naming_uses_discharge_date(settings) and not current_semantic_date(self, "discharge_date"):
            ok = self._prompt_common_output_requirements(
                include_discharge_date=True,
                include_case_number=False,
                include_medical_details=False,
                include_labs_block=False,
            )
            if not ok:
                raise RuntimeError("Дата выписки нужна для выбранного врачом имени подпапки пациента.")

        from desktop_intake import prepare_patient_work_folder
        from desktop_patient_folder import build_patient_folder_info, build_patient_folder_name_from_info

        folder_info = build_patient_folder_info(primary)
        folder_name = build_patient_folder_name_from_info(
            folder_info,
            settings=settings,
            discharge_date=current_semantic_date(self, "discharge_date"),
            fallback=Path(primary).stem,
        )
        patient_dir, effective_primary = prepare_patient_work_folder(
            self._desktop_intake_folder,
            primary,
            folder_name=folder_name,
        )
        self._apply_primary_document_path(str(effective_primary), prompt_for_referral=False)
        if folder_info.fio:
            self._set_ui_var(self.patient_name_var, folder_info.fio)
        if folder_info.admission_date:
            self._set_ui_var(self.admission_date_var, folder_info.admission_date)
            try:
                self.data.admission_date = folder_info.admission_date
            except Exception as exc:
                record_soft_exception("desktop_intake_mixin:folder_info_admission", exc)
        self._set_output_dir_auto_patient_scoped(patient_dir)
        self._refresh_desktop_intake_diary_inputs()

    def _open_desktop_intake_popup(self, primary_path: str | Path) -> bool:
        """Implement the _open_desktop_intake_popup workflow with validation, UI state updates and diagnostics."""
        if getattr(self, "_desktop_intake_popup_open", False):
            return False
        self._desktop_intake_popup_open = True
        primary = Path(primary_path).expanduser()
        processed = False
        try:
            self._activate_window_for_desktop_intake()
            popup = tk.Toplevel(self.root)
            self._desktop_intake_last_popup_opened = True
            self._desktop_intake_popup_outcome = "opened"
            popup.title("Создать документы пациента")
            popup.configure(bg=DEEP)
            popup.geometry("760x560")
            popup.grid_columnconfigure(0, weight=1)
            tk.Label(popup, text=f"Найден первичный документ:\n{primary.name}\n\nВыберите документы, которые нужно создать.", bg=DEEP, fg=TEXT, font=self._font(11, "bold"), justify="left", wraplength=720, padx=14, pady=12).grid(row=0, column=0, sticky="ew")
            body, intake_wheel = self._build_desktop_intake_scroll_body(popup)
            for col in range(2):
                body.grid_columnconfigure(col, weight=1)
            local_vars: dict[str, tk.BooleanVar] = {}
            entries: list[tuple[str, str]] = []
            try:
                from layout_checklist import _doctor_buttons_setup_completed
                from universal_main_documents import custom_documents_for_main_ui
                pack = self._load_or_create_universal_pack()
                # Keep this popup exactly in sync with visible block 03 buttons.
                if _doctor_buttons_setup_completed(pack):
                    for doc in custom_documents_for_main_ui(pack, base_dir=self._universal_profile_path().parent):
                        entries.append((doc.kind, doc.label))
            except Exception as exc:
                record_soft_exception("desktop_intake_mixin:154", exc)
            try:
                diary_ready = bool(getattr(self, "status_files", None) or getattr(self, "diary_texts_dir", "") or getattr(self, "diary_files", None) or getattr(self, "diary_template_dir", ""))
                if diary_ready and not any(kind == DIARY_KIND for kind, _label in entries):
                    entries.append((DIARY_KIND, DIARY_LABEL))
            except Exception as exc:
                record_soft_exception("desktop_intake_mixin:add_diary_entry", exc)
            if not entries:
                empty_state = tk.Frame(body, bg=PANEL)
                empty_state.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=8)
                empty_state.grid_columnconfigure(0, weight=1)
                tk.Label(empty_state, text="В блоке 03 ещё нет созданных врачом кнопок. Сначала загрузите Word-шаблоны — программа создаст кнопки из названий документов.", bg=PANEL, fg=WARN, font=self._font(10, "bold"), wraplength=690, justify="left").grid(row=0, column=0, sticky="ew", pady=(0, 8))
                tk.Button(empty_state, text="Создать свои кнопки", command=lambda: (setattr(self, "_desktop_intake_popup_outcome", "setup_needed"), self._close_desktop_intake_popup(popup), self._open_first_run_create_buttons_popup()), bg=ACCENT_2, fg="#03101f", relief="flat", font=self._font(10, "bold"), padx=14, pady=8).grid(row=1, column=0, sticky="ew")
            tools_row = 0
            if entries:
                tools = tk.Frame(body, bg=PANEL)
                tools.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 8))
                tools.grid_columnconfigure(0, weight=1)
                tools.grid_columnconfigure(1, weight=1)
                def select_all_docs() -> None:
                    for item_var in local_vars.values():
                        item_var.set(True)
                def clear_all_docs() -> None:
                    for item_var in local_vars.values():
                        item_var.set(False)
                tk.Button(tools, text="Выбрать всё", command=select_all_docs, bg=FIELD, fg=TEXT, relief="flat", font=self._font(9, "bold"), padx=8, pady=6).grid(row=0, column=0, sticky="ew", padx=(0, 6))
                tk.Button(tools, text="Снять всё", command=clear_all_docs, bg=PANEL_3, fg=TEXT, relief="flat", font=self._font(9), padx=8, pady=6).grid(row=0, column=1, sticky="ew", padx=(6, 0))
                tools_row = 1
            for idx, (kind, label) in enumerate(entries):
                var = tk.BooleanVar(value=False)
                local_vars[kind] = var
                check = tk.Checkbutton(
                    body,
                    text=label,
                    variable=var,
                    bg=PANEL,
                    fg=TEXT,
                    selectcolor=FIELD,
                    activebackground=PANEL,
                    activeforeground=TEXT,
                    font=self._font(10),
                    anchor="w",
                )
                check.grid(row=tools_row + idx // 2, column=idx % 2, sticky="ew", padx=6, pady=4)
                check.bind("<MouseWheel>", intake_wheel, add="+")
            freq_row = max(tools_row + 1, tools_row + (len(entries) + 1) // 2)
            if self._diary_hourly_enabled():
                tk.Label(body, text="Дневники этому пациенту", bg=PANEL, fg=MUTED, font=self._font(9, "bold")).grid(row=freq_row, column=0, sticky="w", padx=6, pady=(12, 4))
                freq = tk.Frame(body, bg=PANEL)
                freq.grid(row=freq_row, column=1, sticky="ew", padx=6, pady=(12, 4))
                tk.Radiobutton(freq, text="ежедневно", value="daily", variable=self.diary_frequency_mode_var, bg=PANEL, fg=TEXT, selectcolor=FIELD).pack(side="left")
                tk.Radiobutton(freq, text="ежечасно", value="hourly", variable=self.diary_frequency_mode_var, bg=PANEL, fg=TEXT, selectcolor=FIELD).pack(side="left", padx=(12, 0))

            def apply_and_create(*, print_after: bool) -> None:
                nonlocal processed
                selected_kinds = [kind for kind, var in local_vars.items() if bool(var.get())]
                if not selected_kinds:
                    messagebox.showwarning("Ничего не выбрано", "Отметьте хотя бы одну кнопку из блока 03.", parent=popup)
                    return
                if not self._ensure_patient_folder_naming_configured():
                    return
                try:
                    self._prepare_desktop_intake_patient_folder(primary)
                except Exception as exc:
                    messagebox.showerror("Папка выписанных пациентов", str(exc), parent=popup)
                    return
                selected_set = set(selected_kinds)
                self._apply_desktop_intake_selected_kinds(selected_set)
                self._close_desktop_intake_popup(popup)
                processed = True
                self._desktop_intake_popup_outcome = "processed"
                self.create_selected_outputs(print_after=print_after)

            buttons = tk.Frame(popup, bg=DEEP)
            buttons.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 14))
            buttons.grid_columnconfigure(0, weight=1)
            buttons.grid_columnconfigure(1, weight=1)
            buttons.grid_columnconfigure(2, weight=1)
            tk.Button(buttons, text="Создать документы без печати", command=lambda: apply_and_create(print_after=False), bg=FIELD, fg=TEXT, relief="flat", font=self._font(10, "bold"), padx=10, pady=10).grid(row=0, column=0, sticky="ew", padx=(0, 8))
            tk.Button(buttons, text="Создать и распечатать", command=lambda: apply_and_create(print_after=True), bg=ACCENT_2, fg="#03101f", relief="flat", font=self._font(10, "bold"), padx=10, pady=10).grid(row=0, column=1, sticky="ew", padx=(8, 8))
            tk.Button(buttons, text="Отмена", command=lambda: on_close(), bg=PANEL_3, fg=TEXT, relief="flat", font=self._font(9), padx=10, pady=10).grid(row=0, column=2, sticky="ew", padx=(8, 0))
            def on_close() -> None:
                if str(getattr(self, "_desktop_intake_popup_outcome", "") or "") not in {"processed", "setup_needed"}:
                    self._desktop_intake_popup_outcome = "ignored"
                self._close_desktop_intake_popup(popup)
            popup.protocol("WM_DELETE_WINDOW", on_close)
            popup.transient(self.root)
            popup.grab_set()
            self.root.wait_window(popup)
        except Exception as exc:
            self._show_error("Папка выписанных пациентов", exc)
        finally:
            self._desktop_intake_popup_open = False
        return processed


    def _refresh_desktop_intake_diary_inputs(self) -> None:
        """Re-run diary auto-discovery after the primary file was moved.

        Desktop intake first moves the primary DOCX into the patient subfolder.
        Only after that do we know the final output/navigation roots.  This
        method intentionally reruns the old diary selectors so the legacy
        behaviour stays intact, but now also works from the intake folder.
        """
        try:
            if not current_semantic_date(self, "admission_date"):
                self._sync_admission_date_from_title(force=True)
            self._auto_select_diary_text_by_diagnosis(ask_folder=False)
            self._auto_select_numbered_diary_template(ask_folder=False)
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin:refresh_diary_inputs", exc)

    def _diary_hourly_enabled(self) -> bool:
        try:
            from universal_diary_templates import diary_documents_with_hourly_mode
            return bool(diary_documents_with_hourly_mode(self._load_or_create_universal_pack()))
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin:diary_hourly_enabled", exc)
            return False
