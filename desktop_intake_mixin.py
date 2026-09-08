from __future__ import annotations

from medical_date_state import current_semantic_date
from diagnostic_logging import record_soft_exception
from pathlib import Path
import os
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

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
        self._desktop_intake_background_agent_ready = bool(settings.get("background_agent_ready", False))
        self._desktop_intake_folder = str(settings["folder"])
        self._desktop_intake_prompt_version = str(settings.get("prompt_version", "") or "")
        self._desktop_intake_seen_signatures: set[str] = set(settings.get("seen_signatures", ()))
        self._desktop_intake_deferred_signatures: set[str] = set()
        self._desktop_intake_poll_job = None
        self._desktop_intake_popup_open = False
        self._desktop_intake_last_popup_opened = False
        self._desktop_intake_popup_outcome = ""
        self._desktop_intake_gui_lock_job = None

    def _desktop_intake_settings_payload(self) -> dict:
        return {
            "asked": bool(getattr(self, "_desktop_intake_asked", False)),
            "enabled": bool(getattr(self, "_desktop_intake_enabled", False)),
            "background_agent_ready": bool(getattr(self, "_desktop_intake_background_agent_ready", False)),
            "folder": str(getattr(self, "_desktop_intake_folder", "") or ""),
            "prompt_version": str(getattr(self, "_desktop_intake_prompt_version", "") or ""),
            "seen_signatures": sorted(getattr(self, "_desktop_intake_seen_signatures", set())),
        }

    def _persist_desktop_intake_settings(self) -> None:
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
            record_soft_exception("desktop_intake_mixin:bootstrap", exc)

    def _start_gui_runtime_lock(self) -> None:
        if getattr(self, "_desktop_intake_gui_lock_job", None) is not None:
            return
        self._refresh_gui_runtime_lock()
        try:
            self.root.protocol("WM_DELETE_WINDOW", self._close_app_with_runtime_lock_release)
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin.gui_lock_close_protocol", exc)

    def _refresh_gui_runtime_lock(self) -> None:
        try:
            from desktop_intake_agent import uninstall_shutdown_requested, write_gui_runtime_lock
            if uninstall_shutdown_requested():
                self._close_app_with_runtime_lock_release()
                return
            write_gui_runtime_lock()
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin.gui_runtime_lock", exc)
        try:
            self._desktop_intake_gui_lock_job = self.root.after(5000, self._refresh_gui_runtime_lock)
        except Exception as exc:
            self._desktop_intake_gui_lock_job = None
            record_soft_exception("desktop_intake_mixin.gui_runtime_lock_after", exc)

    def _close_app_with_runtime_lock_release(self) -> None:
        for attr in ("_desktop_intake_poll_job", "_desktop_intake_gui_lock_job"):
            job = getattr(self, attr, None)
            if job is None:
                continue
            try:
                self.root.after_cancel(job)
            except Exception as exc:
                record_soft_exception("desktop_intake_mixin.cancel_after_on_close", exc, detail=attr)
            setattr(self, attr, None)
        self._desktop_intake_enabled = False
        try:
            pending = tuple(self.root.tk.call("after", "info") or ())
            for job in pending:
                try:
                    self.root.after_cancel(job)
                except Exception as exc:
                    record_soft_exception("desktop_intake_mixin.cancel_pending_after", exc, detail=str(job))
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin.enumerate_pending_after", exc)
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
            "безопасное фоновое наблюдение за папкой в автозагрузке Windows.",
            parent=self.root,
        )
        self._desktop_intake_asked = True
        self._desktop_intake_prompt_version = DESKTOP_INTAKE_SETUP_PROMPT_VERSION
        self._desktop_intake_background_agent_ready = False
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

    def _ensure_background_intake_agent_installed(self, *, start_now: bool = True) -> bool:
        try:
            from desktop_intake_agent import install_agent_autostart
            ok, message = install_agent_autostart(start_now=start_now)
            self._desktop_intake_background_agent_ready = bool(ok)
            self._persist_desktop_intake_settings()
            if ok:
                self._log("\n✅ Фоновое наблюдение за папкой включено в автозагрузке Windows и запущено.\n")
                return True
            self._log(f"\nℹ Фоновое наблюдение за папкой не настроено автоматически: {message}\n")
            if os.name == "nt" and not os.environ.get("CI"):
                messagebox.showwarning(
                    "Фоновое наблюдение за папкой не запущено",
                    "Папка будет обрабатываться, пока программа открыта, но запуск при закрытом окне сейчас не настроен.\n\n" + str(message),
                    parent=getattr(self, "root", None),
                )
            return False
        except Exception as exc:
            self._desktop_intake_background_agent_ready = False
            try:
                self._persist_desktop_intake_settings()
            except Exception as persist_exc:
                record_soft_exception("desktop_intake_mixin.persist_agent_failure", persist_exc)
            record_soft_exception("desktop_intake_mixin.install_background_agent", exc)
            self._log(f"\n⚠ Не удалось автоматически включить фоновое наблюдение за папкой: {exc}\n")
            if os.name == "nt" and not os.environ.get("CI"):
                messagebox.showwarning(
                    "Фоновое наблюдение за папкой не запущено",
                    "Папка работает только при открытой программе. Автозапуск фонового наблюдения завершился ошибкой:\n\n" + str(exc),
                    parent=getattr(self, "root", None),
                )
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
                suppressed = set(self._desktop_intake_seen_signatures) | set(getattr(self, "_desktop_intake_deferred_signatures", set()))
                candidates = scan_primary_candidates(self._desktop_intake_folder, suppressed)
                if candidates:
                    candidate = candidates[0]
                    self._desktop_intake_last_popup_opened = False
                    self._desktop_intake_popup_outcome = ""
                    processed = self._open_desktop_intake_popup(candidate.path)
                    outcome = str(getattr(self, "_desktop_intake_popup_outcome", "") or "")
                    terminal_close = outcome in {"processed", "processed_source_retained", "ignored_explicitly"}
                    if processed or terminal_close:
                        mark_seen(self._desktop_intake_seen_signatures, candidate)
                        self._persist_desktop_intake_settings()
                    elif outcome == "deferred":
                        from desktop_intake import signature_key
                        self._desktop_intake_deferred_signatures.add(
                            signature_key(candidate.path, candidate.signature[0], candidate.signature[1])
                        )
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin:poll", exc)
        finally:
            if not getattr(self, "_desktop_intake_enabled", False):
                self._desktop_intake_poll_job = None
                return
            try:
                self._desktop_intake_poll_job = self.root.after(2500, self._poll_desktop_intake_folder)
            except Exception as exc:
                self._desktop_intake_poll_job = None
                record_soft_exception("desktop_intake_mixin:poll_after", exc)

    def _activate_window_for_desktop_intake(self) -> None:
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin:activate", exc)

    def _apply_desktop_intake_selected_kinds(self, selected_kinds: set[str]) -> None:
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

    def _prompt_intake_folder_identity(self, primary: Path, settings) -> tuple[str, str]:
        """Collect naming-critical FIO/admission before strict folder creation."""
        from desktop_patient_folder import build_patient_folder_info, normalize_folder_naming_settings
        from medical_formatting import parse_date

        info = build_patient_folder_info(primary)
        cfg = normalize_folder_naming_settings(settings)
        parts = set(cfg.get("parts", ()))
        needs_fio = bool(parts & {"full_fio", "surname_initials", "surname_name"})
        needs_admission = bool(parts & {"admission_date", "admission_discharge_dates", "admission_month"})

        fio = str(info.fio or getattr(getattr(self, "patient_name_var", None), "get", lambda: "")() or "").strip()
        admission = str(info.admission_date or current_semantic_date(self, "admission_date") or "").strip()

        if needs_fio and not fio:
            fio = str(simpledialog.askstring(
                "ФИО для папки пациента",
                "В первичном документе не удалось надёжно распознать ФИО.\nВведите ФИО пациента для имени подпапки:",
                parent=self.root,
            ) or "").strip()
            if not fio:
                raise RuntimeError("ФИО пациента нужно для выбранного правила имени подпапки.")
            self._set_ui_var(self.patient_name_var, fio)

        if needs_admission and not admission:
            raw = str(simpledialog.askstring(
                "Дата поступления для папки пациента",
                "В первичном документе не удалось надёжно распознать дату поступления.\nВведите дату поступления (ДД.ММ.ГГГГ):",
                parent=self.root,
            ) or "").strip()
            parsed = parse_date(raw)
            if not parsed:
                raise RuntimeError("Корректная дата поступления нужна для выбранного правила имени подпапки.")
            admission = parsed.strftime("%d.%m.%Y")
            self._set_ui_var(self.admission_date_var, admission)
            try:
                self.data.admission_date = admission
            except Exception as exc:
                record_soft_exception("desktop_intake_mixin:set_manual_admission", exc)
        return fio, admission

    def _prepare_desktop_intake_patient_folder(self, primary: Path, *, keep_source: bool = False) -> Path:
        self._apply_primary_document_path(str(primary), prompt_for_referral=False)
        settings = self._folder_naming_settings()
        resolved_fio, resolved_admission = self._prompt_intake_folder_identity(primary, settings)

        from desktop_patient_folder import folder_naming_uses_discharge_date
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
        from desktop_patient_folder import build_patient_folder_name

        folder_name = build_patient_folder_name(
            fio=resolved_fio,
            admission_date=resolved_admission,
            discharge_date=current_semantic_date(self, "discharge_date"),
            settings=settings,
            fallback=Path(primary).stem,
            strict=True,
        )
        patient_dir, effective_primary = prepare_patient_work_folder(
            self._desktop_intake_folder,
            primary,
            folder_name=folder_name,
            keep_source=keep_source,
        )
        from medical_primary_document_state import sync_selected_primary_document_path
        sync_selected_primary_document_path(self, effective_primary)
        if hasattr(self, "_set_primary_drop_selected"):
            self._set_primary_drop_selected(str(effective_primary))
        if resolved_fio:
            self._set_ui_var(self.patient_name_var, resolved_fio)
        if resolved_admission:
            self._set_ui_var(self.admission_date_var, resolved_admission)
            try:
                self.data.admission_date = resolved_admission
            except Exception as exc:
                record_soft_exception("desktop_intake_mixin:folder_info_admission", exc)
        self._set_output_dir_auto_patient_scoped(patient_dir)
        self._refresh_desktop_intake_diary_inputs()
        return effective_primary

    def _open_desktop_intake_popup(self, primary_path: str | Path) -> bool:
        """Run the modal intake transaction from detected primary document to committed outputs."""
        if getattr(self, "_desktop_intake_popup_open", False):
            return False
        self._desktop_intake_popup_open = True
        primary = Path(primary_path).expanduser()
        processed = False
        prepared_primary: Path | None = None
        attempted_creation = False
        selection_snapshot = {kind: bool(var.get()) for kind, var in getattr(self, "output_vars", {}).items()}
        diary_frequency_snapshot = str(getattr(getattr(self, "diary_frequency_mode_var", None), "get", lambda: "daily")() or "daily")
        try:
            self._activate_window_for_desktop_intake()
            popup = tk.Toplevel(self.root)
            self._desktop_intake_last_popup_opened = True
            self._desktop_intake_popup_outcome = "opened"
            popup.title("Создать документы пациента")
            popup.configure(bg=DEEP)
            popup.geometry("760x560")
            popup.grid_columnconfigure(0, weight=1)
            tk.Label(
                popup,
                text=f"Найден первичный документ:\n{primary.name}\n\nВыберите документы, которые нужно создать.",
                bg=DEEP, fg=TEXT, font=self._font(11, "bold"), justify="left", wraplength=720, padx=14, pady=12,
            ).grid(row=0, column=0, sticky="ew")
            body, intake_wheel = self._build_desktop_intake_scroll_body(popup)
            for col in range(2):
                body.grid_columnconfigure(col, weight=1)
            local_vars: dict[str, tk.BooleanVar] = {}
            entries: list[tuple[str, str, bool, str]] = []
            try:
                from universal_main_documents import profile_choices_for_desktop_intake
                from layout_checklist import _doctor_buttons_setup_completed
                pack = self._load_or_create_universal_pack()
                if _doctor_buttons_setup_completed(pack):
                    for choice in profile_choices_for_desktop_intake(pack, base_dir=self._universal_profile_path().parent):
                        entries.append((choice.kind, choice.label, choice.available, choice.problem))
            except Exception as exc:
                record_soft_exception("desktop_intake_mixin:profile_choices", exc)
            try:
                diary_ready = bool(getattr(self, "status_files", None) or getattr(self, "diary_texts_dir", "") or getattr(self, "diary_files", None) or getattr(self, "diary_template_dir", ""))
                if diary_ready and not any(kind == DIARY_KIND for kind, _label, _available, _problem in entries):
                    entries.append((DIARY_KIND, DIARY_LABEL, True, ""))
            except Exception as exc:
                record_soft_exception("desktop_intake_mixin:add_diary_entry", exc)
            if not entries:
                empty_state = tk.Frame(body, bg=PANEL)
                empty_state.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=8)
                empty_state.grid_columnconfigure(0, weight=1)
                tk.Label(
                    empty_state,
                    text="В блоке 03 ещё нет созданных врачом кнопок. Сначала загрузите Word-шаблоны — программа создаст кнопки из названий документов.",
                    bg=PANEL, fg=WARN, font=self._font(10, "bold"), wraplength=690, justify="left",
                ).grid(row=0, column=0, sticky="ew", pady=(0, 8))
                tk.Button(
                    empty_state,
                    text="Создать свои кнопки",
                    command=lambda: (setattr(self, "_desktop_intake_popup_outcome", "setup_needed"), self._close_desktop_intake_popup(popup), self._open_first_run_create_buttons_popup()),
                    bg=ACCENT_2, fg="#03101f", relief="flat", font=self._font(10, "bold"), padx=14, pady=8,
                ).grid(row=1, column=0, sticky="ew")
            tools_row = 0
            available_entries = [entry for entry in entries if entry[2]]
            if available_entries:
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
            for idx, (kind, label, available, problem) in enumerate(entries):
                var = tk.BooleanVar(value=False)
                if available:
                    local_vars[kind] = var
                display_label = label if available else f"⚠ {label} — {problem or 'Word-шаблон недоступен'}"
                check = tk.Checkbutton(
                    body, text=display_label, variable=var, bg=PANEL,
                    fg=TEXT if available else WARN, disabledforeground=WARN,
                    selectcolor=FIELD, activebackground=PANEL, activeforeground=TEXT,
                    font=self._font(10), anchor="w", state="normal" if available else "disabled",
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
                nonlocal processed, prepared_primary, attempted_creation
                selected_kinds = [kind for kind, var in local_vars.items() if bool(var.get())]
                if not selected_kinds:
                    messagebox.showwarning("Ничего не выбрано", "Отметьте хотя бы одну кнопку из блока 03.", parent=popup)
                    return
                if not self._ensure_patient_folder_naming_configured(force=True):
                    return
                if prepared_primary is None:
                    try:
                        prepared_primary = self._prepare_desktop_intake_patient_folder(primary, keep_source=True)
                    except Exception as exc:
                        messagebox.showerror("Папка выписанных пациентов", str(exc), parent=popup)
                        return
                self._apply_desktop_intake_selected_kinds(set(selected_kinds))
                attempted_creation = True
                success = bool(self.create_selected_outputs(print_after=print_after))
                if not success:
                    self._desktop_intake_popup_outcome = "retry_pending"
                    return
                source_removed = False
                try:
                    primary.unlink()
                    source_removed = True
                except FileNotFoundError:
                    source_removed = True
                except OSError as exc:
                    record_soft_exception("desktop_intake_mixin.commit_remove_source", exc, detail=str(primary))
                    messagebox.showwarning(
                        "Документы созданы, исходник занят",
                        "Документы успешно созданы, но исходный Word-файл не удалось убрать из папки «Выписанные пациенты». "
                        "Закройте его в Word и удалите/переместите вручную. Повторно документы для него создаваться не будут.\n\n" + str(primary),
                        parent=popup,
                    )
                processed = True
                self._desktop_intake_popup_outcome = "processed" if source_removed else "processed_source_retained"
                self._close_desktop_intake_popup(popup)

            def on_close() -> None:
                outcome = str(getattr(self, "_desktop_intake_popup_outcome", "") or "")
                if attempted_creation and not processed:
                    self._desktop_intake_popup_outcome = "retry_pending"
                elif outcome not in {"processed", "processed_source_retained", "setup_needed"}:
                    self._desktop_intake_popup_outcome = "deferred"
                self._close_desktop_intake_popup(popup)

            buttons = tk.Frame(popup, bg=DEEP)
            buttons.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 14))
            for col in range(3):
                buttons.grid_columnconfigure(col, weight=1)
            tk.Button(buttons, text="Создать документы без печати", command=lambda: apply_and_create(print_after=False), bg=FIELD, fg=TEXT, relief="flat", font=self._font(10, "bold"), padx=10, pady=10).grid(row=0, column=0, sticky="ew", padx=(0, 8))
            tk.Button(buttons, text="Создать и распечатать", command=lambda: apply_and_create(print_after=True), bg=ACCENT_2, fg="#03101f", relief="flat", font=self._font(10, "bold"), padx=10, pady=10).grid(row=0, column=1, sticky="ew", padx=(8, 8))
            tk.Button(buttons, text="Отмена", command=on_close, bg=PANEL_3, fg=TEXT, relief="flat", font=self._font(9), padx=10, pady=10).grid(row=0, column=2, sticky="ew", padx=(8, 0))
            popup.protocol("WM_DELETE_WINDOW", on_close)
            popup.transient(self.root)
            popup.grab_set()
            self.root.wait_window(popup)
        except Exception as exc:
            self._show_error("Папка выписанных пациентов", exc)
        finally:
            self._desktop_intake_popup_open = False
            for kind, selected in selection_snapshot.items():
                var = getattr(self, "output_vars", {}).get(kind)
                if var is not None and hasattr(var, "set"):
                    var.set(selected)
            for kind, var in getattr(self, "output_vars", {}).items():
                if kind not in selection_snapshot and hasattr(var, "set"):
                    var.set(False)
            frequency_var = getattr(self, "diary_frequency_mode_var", None)
            if frequency_var is not None and hasattr(frequency_var, "set"):
                frequency_var.set(diary_frequency_snapshot)
            try:
                self._update_selected_outputs_status()
            except Exception as exc:
                record_soft_exception("desktop_intake_mixin.restore_main_selection", exc)
        return processed

    def _refresh_desktop_intake_diary_inputs(self) -> None:
        try:
            if not current_semantic_date(self, "admission_date"):
                self._sync_admission_date_from_title(force=True)
            self._auto_select_diary_text_by_diagnosis(ask_folder=False)
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin:refresh_diary_inputs", exc)

    def _diary_hourly_enabled(self) -> bool:
        try:
            from universal_diary_templates import diary_documents_with_hourly_mode
            return bool(diary_documents_with_hourly_mode(self._load_or_create_universal_pack()))
        except Exception as exc:
            record_soft_exception("desktop_intake_mixin:diary_hourly_enabled", exc)
            return False
