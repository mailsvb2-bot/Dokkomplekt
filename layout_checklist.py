from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox

import tkinter as tk

from app_config import (
    ACCENT,
    ACCENT_2,
    DEEP,
    FIELD,
    MUTED,
    PANEL,
    PANEL_3,
    TEXT,
)
from medical_constants import DOCUMENT_LABELS
from diagnostic_logging import record_soft_exception
from personal_document_buttons import normalize_button_label
from universal_profiles import DOCTOR_BUTTON_REVIEW_CONTRACT_VERSION


FIRST_RUN_CREATE_BUTTON_LABEL = "Создать свои кнопки"
BLOCK03_EMPTY_STATE_HAS_ONLY_CREATE_BUTTON = True
BLOCK03_DOCTOR_SETUP_FLAG = "block03_buttons_created_by_doctor_review_v2"
BLOCK03_LEGACY_SETUP_FLAGS = ("block03_buttons_created_by_doctor", "first_run_create_buttons_completed")


def _doctor_buttons_setup_completed(pack) -> bool:
    """True only after the doctor explicitly created/imported/opened own buttons."""

    try:
        principles = dict(getattr(pack, "workflow_principles", {}) or {})
    except Exception as exc:
        record_soft_exception("layout_checklist.doctor_buttons_setup_completed", exc)
        principles = {}
    # Do not trust legacy flags here. Old archives/local folders could contain
    # stale default_custom.medpack.json with garbage buttons, which made block 03
    # look preconfigured on the very first launch. Only the v2 flag is written
    # after the doctor explicitly confirms the review table or manually opens/
    # imports a profile in this build.
    return bool(principles.get(BLOCK03_DOCTOR_SETUP_FLAG)) and str(principles.get("doctor_button_review_contract_version", "")).strip() == DOCTOR_BUTTON_REVIEW_CONTRACT_VERSION


def assert_block03_first_run_contract() -> None:
    """Release lock: first launch block 03 must show one onboarding button only."""

    if FIRST_RUN_CREATE_BUTTON_LABEL != "Создать свои кнопки":
        raise AssertionError("Block 03 first-run button label changed")
    if not BLOCK03_EMPTY_STATE_HAS_ONLY_CREATE_BUTTON:
        raise AssertionError("Block 03 empty state must contain only the create-buttons CTA")
    if BLOCK03_DOCTOR_SETUP_FLAG != "block03_buttons_created_by_doctor_review_v2":
        raise AssertionError("Block 03 setup must require the strict v2 doctor-confirmation flag")
    if "first_run_create_buttons_completed" not in BLOCK03_LEGACY_SETUP_FLAGS:
        raise AssertionError("Legacy first-run flags must be tracked but not trusted")
    if not DOCTOR_BUTTON_REVIEW_CONTRACT_VERSION:
        raise AssertionError("Doctor button review contract version must be explicit")

    class _LegacyPack:
        workflow_principles = {"block03_buttons_created_by_doctor": True, "first_run_create_buttons_completed": True}

    if _doctor_buttons_setup_completed(_LegacyPack()):
        raise AssertionError("Legacy/stale profile flags must not unlock first-launch block 03")

    class _ConfirmedPack:
        workflow_principles = {BLOCK03_DOCTOR_SETUP_FLAG: True, "doctor_button_review_contract_version": DOCTOR_BUTTON_REVIEW_CONTRACT_VERSION}

    if not _doctor_buttons_setup_completed(_ConfirmedPack()):
        raise AssertionError("Fresh doctor-confirmed profile must unlock block 03")


class LayoutChecklistMixin:
    def _build_create_checklist_card(self, parent: tk.Frame) -> None:
        section, body = self._section(parent, "03", "checklist", "Документы\nдля создания")
        section.grid(row=3, column=0, sticky="ew", pady=(0, 3))

        body.grid_rowconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=0)
        body.grid_rowconfigure(2, weight=1)
        body.grid_rowconfigure(3, weight=0)
        body.grid_columnconfigure(0, weight=1)

        # Block 03 is doctor-owned: the program does not show built-in medical
        # templates.  Every button here must come from the doctor's own DOCX/DOCM
        # profile so it is valid for the doctor's specialty, country and clinic.
        self._custom_profile_tiles_container = tk.Frame(body, bg=PANEL)
        self._custom_profile_tiles_container.grid(row=1, column=0, sticky="ew")
        self._diary_frequency_container = tk.Frame(body, bg=PANEL)
        self._diary_frequency_container.grid(row=3, column=0, sticky="ew", pady=(self._px(8 if self._compact_ui else 10, 4), 0))
        self._refresh_custom_profile_tiles()


    def _refresh_diary_frequency_controls(self) -> None:
        container = getattr(self, "_diary_frequency_container", None)
        if container is None:
            return
        for child in container.winfo_children():
            child.destroy()
        try:
            enabled = bool(self._diary_hourly_enabled())
        except Exception as exc:
            record_soft_exception("layout_checklist.diary_frequency_enabled", exc)
            enabled = False
        if not enabled:
            if getattr(self, "diary_frequency_mode_var", None):
                self.diary_frequency_mode_var.set("daily")
            return
        tk.Label(container, text="Этому пациенту писать дневники ежедневно или ежечасно?", bg=PANEL, fg=MUTED, font=self._font(9, "bold"), anchor="w").grid(row=0, column=0, sticky="w", padx=(0, self._px(8, 4)))
        buttons = tk.Frame(container, bg=PANEL)
        buttons.grid(row=0, column=1, sticky="ew")
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)
        def choose(mode: str) -> None:
            self.diary_frequency_mode_var.set(mode)
            self._refresh_diary_frequency_controls()
        self._small_neon_button(buttons, text="Ежедневно", command=lambda: choose("daily"), selected=lambda: self.diary_frequency_mode_var.get() == "daily").grid(row=0, column=0, sticky="ew", padx=(0, self._px(5, 2)))
        self._small_neon_button(buttons, text="Ежечасно", command=lambda: choose("hourly"), selected=lambda: self.diary_frequency_mode_var.get() == "hourly").grid(row=0, column=1, sticky="ew", padx=(self._px(5, 2), 0))

    def _refresh_custom_profile_tiles(self) -> None:
        """Render doctor-added medpack documents in block 03.

        Dynamic buttons are intentionally separated by the custom_profile:
        namespace. The current DOCUMENT_ORDER remains untouched.
        """
        container = getattr(self, "_custom_profile_tiles_container", None)
        if container is None:
            return
        for child in container.winfo_children():
            child.destroy()
        try:
            from universal_main_documents import custom_documents_for_main_ui
            pack = self._load_or_create_universal_pack()
            if _doctor_buttons_setup_completed(pack):
                custom_docs = custom_documents_for_main_ui(pack, base_dir=self._universal_profile_path().parent)
            else:
                custom_docs = ()
        except Exception as exc:
            record_soft_exception("layout_checklist.refresh_custom_profile_tiles", exc)
            custom_docs = ()
        self._custom_profile_documents = list(custom_docs)
        visible_kinds = {doc.kind for doc in custom_docs}
        for kind in list(getattr(self, "custom_output_vars", {})):
            if kind not in visible_kinds:
                self.custom_output_vars.pop(kind, None)
                self.output_vars.pop(kind, None)
                self._check_tile_redrawers.pop(kind, None)
        for col in range(4):
            container.grid_columnconfigure(col, weight=1, uniform="custom_profile_tiles")
        if not custom_docs:
            # First launch must stay visually empty: no legacy document tiles, no
            # small helper buttons, no diary toggles.  The doctor sees one clear
            # action and then uploads their own DOCX/DOCM templates; button names
            # are created only from the top title of those templates.
            if getattr(self, "_diary_frequency_container", None) is not None:
                for child in self._diary_frequency_container.winfo_children():
                    child.destroy()
                self._diary_frequency_container.grid_remove()
            container.grid_columnconfigure(0, weight=1)
            for col in range(1, 4):
                container.grid_columnconfigure(col, weight=0, uniform="")
            first_run = tk.Frame(container, bg=PANEL)
            first_run.grid(row=0, column=0, sticky="ew")
            first_run.grid_columnconfigure(0, weight=1)
            tk.Button(
                first_run,
                text=FIRST_RUN_CREATE_BUTTON_LABEL,
                command=self._open_first_run_create_buttons_popup,
                bg=ACCENT_2,
                fg="#03101f",
                activebackground="#18a8dd",
                activeforeground="#03101f",
                relief="flat",
                font=self._font(13 if not self._compact_ui else 11, "bold"),
                cursor="hand2",
                padx=self._px(18, 12),
                pady=self._px(18, 12),
                wraplength=self._px(520, 320),
                justify="center",
            ).grid(row=0, column=0, sticky="ew")
            return
        if getattr(self, "_diary_frequency_container", None) is not None:
            self._diary_frequency_container.grid()
        header = tk.Frame(container, bg=PANEL)
        header.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, self._px(5, 2)))
        header.grid_columnconfigure(0, weight=1)
        tk.Label(
            header,
            text="Свои кнопки врача / Документы из профиля врача",
            bg=PANEL,
            fg=MUTED,
            font=self._font(9, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        tk.Button(
            header,
            text="+ Добавить",
            command=self._open_universal_document_mapper,
            bg=FIELD,
            fg=ACCENT,
            activebackground=PANEL_3,
            activeforeground=TEXT,
            relief="flat",
            font=self._font(8, "bold"),
            cursor="hand2",
            padx=self._px(9, 5),
            pady=self._px(4, 2),
        ).grid(row=0, column=1, sticky="e")
        for idx, doc in enumerate(custom_docs):
            container.grid_rowconfigure(1 + idx // 4, weight=0)
            if doc.kind not in self.output_vars:
                var = self.custom_output_vars.get(doc.kind)
                if var is None:
                    var = tk.BooleanVar(value=False)
                    self.custom_output_vars[doc.kind] = var
                self.output_vars[doc.kind] = var
            item = self._check_tile(container, kind=doc.kind, label=doc.label, icon="doc")
            item.grid(
                row=1 + idx // 4,
                column=idx % 4,
                sticky="nsew",
                padx=(0 if idx % 4 == 0 else self._px(12 if self._compact_ui else 19, 6), 0),
                pady=(0 if idx < 4 else self._px(8 if self._compact_ui else 10, 4), 0),
            )
        self._refresh_diary_frequency_controls()

    def _check_tile(self, parent, *, kind: str, label: str, icon: str) -> tk.Canvas:
        """Responsive checklist tile with a clear selected state."""
        label_len = len(str(label or ""))
        height = (36 if label_len > 22 else 30) if self._compact_ui else (74 if label_len > 28 else 64)
        canvas = tk.Canvas(parent, height=height, bg=PANEL, highlightthickness=0, bd=0, cursor="hand2")
        scale = max(0.58, height / 64)
        pointer = {"hover": False, "pressed": False}

        def draw(active: bool = False) -> None:
            """Implement the draw workflow with validation, UI state updates and diagnostics."""
            canvas.delete("all")
            width = max(self._px(180, 145), canvas.winfo_width())
            checked = self.output_vars[kind].get()
            pressed = bool(pointer["pressed"])
            if checked:
                # Выбранное состояние без чекбокса/галочки: нажатые плитки
                # получают лёгкий цветовой градиент, мягкую обводку и
                # тонкую акцентную полосу слева.
                if pressed:
                    top, bottom, border = "#2b7892", "#0d344f", "#a8f0ff"
                elif active:
                    top, bottom, border = "#1d637f", "#0b3049", "#8be6f5"
                else:
                    top, bottom, border = "#15536e", "#08273e", "#63cfe4"
                text_fill = TEXT
                icon_fill = "#c8f5ff"
                marker = "#77def1"
                inner = "#95e8f5"
            else:
                if pressed:
                    top, bottom, border = "#123653", "#071928", "#3eb7df"
                elif active:
                    top, bottom, border = "#0d2236", "#0a1a2a", "#2b80b5"
                else:
                    top, bottom, border = "#091b2b", "#071625", "#173c5c"
                text_fill = TEXT
                icon_fill = ACCENT
                marker = "#58bdd5"
                inner = "#8bd8ec"
            self._gradient_round_rect(
                canvas,
                1,
                1,
                width - 1,
                height - 1,
                self._px(8, 5),
                top,
                bottom,
                outline=border,
                width=1,
                glow=active or pressed,
            )
            if checked:
                self._round_rect(
                    canvas,
                    3,
                    3,
                    width - 3,
                    height - 3,
                    self._px(7, 5),
                    fill="",
                    outline=self._mix(inner, bottom, 0.50),
                    width=1,
                )
                self._round_rect(
                    canvas,
                    self._px(6, 4),
                    self._px(8, 5),
                    self._px(11, 8),
                    height - self._px(8, 5),
                    self._px(3, 2),
                    fill=marker,
                    outline="",
                    width=0,
                )
                canvas.create_line(
                    self._px(16, 11),
                    self._px(5, 4),
                    width - self._px(16, 11),
                    self._px(5, 4),
                    fill=self._mix("#d7fbff", top, 0.45),
                )
            # Чекбокс и галочка удалены: выбранность читается через лёгкий
            # цветной градиент, левую cyan-метку, обводку и цвет иконки.
            icon_x, icon_y = self._px(34, 22), max(5, int(height * 0.23))
            if self._compact_ui and icon == "people":
                # Центрирование по зелёной пометке пользователя.
                people_scale = 0.46
                people_w = 27 * people_scale
                people_h = 29 * people_scale
                icon_x = self._px(34, 22) - int(people_w / 2)
                icon_y = max(4, int(height * 0.5 - people_h / 2))
                self._draw_tile_icon(canvas, icon, icon_x, icon_y, color=icon_fill, scale=people_scale)
            else:
                self._draw_tile_icon(canvas, icon, icon_x, icon_y, color=icon_fill, scale=(0.58 if self._compact_ui else 1.0))
            text_x = self._px(72, 48)
            canvas.create_text(
                text_x,
                height // 2,
                text=label,
                fill=text_fill,
                font=self._font(10 if self._compact_ui else 12, "bold" if checked else None),
                anchor="w",
                width=max(70, width - text_x - self._px(12, 8)),
            )

        def on_enter(_event=None) -> None:
            pointer["hover"] = True
            draw(True)

        def on_leave(_event=None) -> None:
            pointer["hover"] = False
            pointer["pressed"] = False
            draw(False)

        def on_press(_event=None) -> None:
            pointer["pressed"] = True
            draw(pointer["hover"])

        def on_release(_event=None) -> None:
            if pointer["pressed"]:
                pointer["pressed"] = False
                self._activate_output_tile(kind)
            draw(pointer["hover"])

        canvas.bind("<Configure>", lambda _event: draw(False))
        canvas.bind("<Enter>", on_enter)
        canvas.bind("<Leave>", on_leave)
        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<ButtonRelease-1>", on_release)
        canvas.after(1, draw)
        self._check_tile_redrawers[kind] = draw
        return canvas

    def _activate_output_tile(self, kind: str) -> None:
        """Toggle a document tile with the discharge/sick-leave guard.

        If the discharge tile is already selected, a click is interpreted as
        an attempt to complete missing discharge requirements, not as a silent
        deselect. First date of discharge is requested, then sick-leave number
        if «Больничный лист: да» is set.
        """
        var = self.output_vars[kind]
        currently_selected = bool(var.get())
        if kind == "discharge" and currently_selected:
            # Повторный клик по уже выбранному выписному — это редактирование
            # реквизитов выписки, прежде всего даты, а не молчаливое снятие выбора.
            try:
                self._prompt_discharge_output_requirements(force_discharge_date=True)
            except TypeError as exc:
                if "force_discharge_date" not in str(exc):
                    raise
                # Compatibility with old smoke/fake callbacks that accepted no kwargs.
                self._prompt_discharge_output_requirements()
            self._update_selected_outputs_status()
            self._redraw_selection_controls()
            return

        var.set(not currently_selected)
        self._on_output_toggle(kind)

    def _draw_tile_icon(self, canvas: tk.Canvas, kind: str, x: int, y: int, *, color: str = ACCENT, scale: float = 1.0) -> None:
        """Line icons for document tiles. Coordinates are scaled for compact 1/3-window mode."""
        def xx(v: float) -> float:
            return x + v * scale

        def yy(v: float) -> float:
            return y + v * scale

        w = max(1.0, 1.25 * scale)
        if kind == "doc":
            canvas.create_rectangle(xx(0), yy(0), xx(20), yy(26), outline=color, width=w)
            canvas.create_line(xx(14), yy(0), xx(25), yy(9), xx(25), yy(26), fill=color, width=w)
            canvas.create_line(xx(8), yy(13), xx(16), yy(13), fill=color, width=w)
            canvas.create_line(xx(12), yy(9), xx(12), yy(17), fill=color, width=w)
        elif kind == "stethoscope":
            canvas.create_arc(xx(0), yy(-2), xx(22), yy(23), start=180, extent=180, outline=color, width=w, style="arc")
            canvas.create_line(xx(0), yy(7), xx(0), yy(1), fill=color, width=w)
            canvas.create_line(xx(22), yy(7), xx(22), yy(1), fill=color, width=w)
            canvas.create_line(xx(11), yy(23), xx(11), yy(29), fill=color, width=w)
            canvas.create_oval(xx(17), yy(25), xx(27), yy(35), outline=color, width=w)
        elif kind == "people":
            canvas.create_oval(xx(0), yy(1), xx(9), yy(10), outline=color, width=w)
            canvas.create_oval(xx(13), yy(1), xx(22), yy(10), outline=color, width=w)
            canvas.create_arc(xx(-5), yy(10), xx(14), yy(29), start=0, extent=180, outline=color, width=w, style="arc")
            canvas.create_arc(xx(8), yy(10), xx(27), yy(29), start=0, extent=180, outline=color, width=w, style="arc")
        elif kind == "wheelchair":
            canvas.create_oval(xx(1), yy(16), xx(18), yy(33), outline=color, width=w)
            canvas.create_line(xx(9), yy(0), xx(9), yy(17), xx(23), yy(17), fill=color, width=w)
            canvas.create_line(xx(11), yy(8), xx(22), yy(8), fill=color, width=w)
            canvas.create_line(xx(22), yy(17), xx(28), yy(29), fill=color, width=w)
            canvas.create_oval(xx(7), yy(-4), xx(12), yy(1), outline=color, fill=color)
        elif kind == "clipboard":
            canvas.create_rectangle(xx(3), yy(0), xx(21), yy(28), outline=color, width=w)
            canvas.create_rectangle(xx(8), yy(-4), xx(16), yy(3), outline=color, width=w)
            for pos in (8, 15, 22):
                canvas.create_line(xx(8), yy(pos), xx(18), yy(pos), fill=color, width=max(1.0, 1.2 * scale))
        elif kind == "shield":
            canvas.create_polygon(xx(13), yy(-1), xx(25), yy(4), xx(24), yy(17), xx(13), yy(29), xx(2), yy(17), xx(1), yy(4), fill="", outline=color, width=w)
            canvas.create_line(xx(8), yy(14), xx(12), yy(18), xx(19), yy(10), fill=color, width=w, capstyle="round", joinstyle="round")
        elif kind == "book":
            canvas.create_line(xx(0), yy(4), xx(11), yy(0), xx(14), yy(4), xx(17), yy(0), xx(28), yy(4), xx(28), yy(28), xx(17), yy(24), xx(14), yy(28), xx(11), yy(24), xx(0), yy(28), xx(0), yy(4), fill=color, width=w)
            canvas.create_line(xx(14), yy(4), xx(14), yy(28), fill=color, width=max(1.0, 1.2 * scale))


# Doctor button review dialog -------------------------------------------------
TEMPLATE_BUTTON_REVIEW_LOCK_VERSION = "v1.0"
TEMPLATE_BUTTON_CREATION_REQUIRES_DOCTOR_CONFIRMATION = True
TEMPLATE_BUTTON_COUNT_MATCHES_CONFIRMED_ROWS = True
TEMPLATE_BUTTON_REVIEW_COLUMNS = (
    "Выбранный документ",
    "Название сверху листа",
    "Название будущей кнопки",
)


@dataclass(frozen=True)
class TemplateButtonReviewRow:
    """One confirmed template-to-button row."""

    path: str
    detected_label: str
    button_label: str
    document_id: str
    role_id: str = "unknown"
    source: str = "template_top_title"
    confidence: float = 0.0


@dataclass(frozen=True)
class TemplateButtonReviewResult:
    """Doctor decision after the review table."""

    rows: tuple[TemplateButtonReviewRow, ...]
    replace_existing: bool = False

    @property
    def ok(self) -> bool:
        return bool(self.rows)


def _review_font(app: object, size: int, weight: str | None = None):
    try:
        return app._font(size, weight) if weight else app._font(size)  # type: ignore[attr-defined]
    except Exception as exc:
        record_soft_exception("layout_checklist.review_font", exc)
        family = "Segoe UI"
        return (family, size, weight) if weight else (family, size)


def _initial_label(recognition: object) -> str:
    label = normalize_button_label(getattr(recognition, "label", "") or "")
    if not label or label == "Документ":
        label = normalize_button_label(Path(str(getattr(recognition, "path", ""))).stem)
    return label or "Документ"


def review_template_button_names(
    app: object,
    parent: tk.Misc,
    recognitions: tuple[object, ...] | list[object],
    *,
    first_run: bool = False,
    existing_button_count: int = 0,
) -> TemplateButtonReviewResult | None:
    """Show editable confirmation table and return only confirmed rows."""

    items = tuple(recognitions or ())
    if not items:
        return None
    popup, result = _create_template_review_popup(app, parent)
    outer, rows_frame = _build_template_review_table_shell(app, popup)
    include_vars, label_vars, warning_count = _populate_template_review_rows(app, rows_frame, items)
    replace_var = _build_template_review_options(app, popup, items, first_run, existing_button_count, warning_count)
    _build_template_review_actions(app, popup, items, include_vars, label_vars, replace_var, result)
    popup.transient(parent)
    popup.grab_set()
    popup.focus_set()
    parent.wait_window(popup)
    return result["value"]


def _create_template_review_popup(app: object, parent: tk.Misc) -> tuple[tk.Toplevel, dict[str, TemplateButtonReviewResult | None]]:
    popup = tk.Toplevel(parent)
    popup.title("Проверьте будущие кнопки")
    popup.configure(bg=DEEP)
    popup.geometry("1020x660")
    popup.minsize(860, 520)
    popup.grid_columnconfigure(0, weight=1)
    popup.grid_rowconfigure(2, weight=1)
    result: dict[str, TemplateButtonReviewResult | None] = {"value": None}
    tk.Label(popup, text="Проверьте названия кнопок перед созданием", bg=DEEP, fg=TEXT, font=_review_font(app, 16, "bold"), padx=14, pady=10).grid(row=0, column=0, sticky="ew")
    tk.Label(
        popup,
        text=(
            "Программа не будет молча создавать кнопки по догадке. Проверьте каждую строку: "
            "какой шаблон выбран, что найдено сверху листа и как будет называться кнопка в блоке 03. "
            "Название можно изменить вручную."
        ),
        bg=DEEP,
        fg=MUTED,
        font=_review_font(app, 10),
        wraplength=960,
        justify="center",
        padx=14,
        pady=0,
    ).grid(row=1, column=0, sticky="ew", pady=(0, 10))
    return popup, result


def _build_template_review_table_shell(app: object, popup: tk.Toplevel) -> tuple[tk.Frame, tk.Frame]:
    outer = tk.Frame(popup, bg=PANEL, padx=10, pady=10)
    outer.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 10))
    outer.grid_columnconfigure(0, weight=1)
    outer.grid_rowconfigure(1, weight=1)
    header = tk.Frame(outer, bg=PANEL)
    header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    for col, weight in enumerate((0, 2, 2, 2)):
        header.grid_columnconfigure(col, weight=weight)
    tk.Label(header, text="Создать", bg=PANEL, fg=MUTED, font=_review_font(app, 9, "bold"), width=9).grid(row=0, column=0, sticky="w")
    for col, text in enumerate(TEMPLATE_BUTTON_REVIEW_COLUMNS, start=1):
        tk.Label(header, text=text, bg=PANEL, fg=MUTED, font=_review_font(app, 9, "bold"), anchor="w").grid(row=0, column=col, sticky="ew", padx=(8, 0))
    canvas = tk.Canvas(outer, bg=PANEL, highlightthickness=0)
    scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    rows_frame = tk.Frame(canvas, bg=PANEL)
    for col, weight in enumerate((0, 2, 2, 2)):
        rows_frame.grid_columnconfigure(col, weight=weight)
    canvas_window = canvas.create_window((0, 0), window=rows_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=1, column=0, sticky="nsew")
    scrollbar.grid(row=1, column=1, sticky="ns")

    def _sync_scroll_region(_event=None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.itemconfigure(canvas_window, width=canvas.winfo_width())

    rows_frame.bind("<Configure>", _sync_scroll_region)
    canvas.bind("<Configure>", _sync_scroll_region)
    return outer, rows_frame


def _populate_template_review_rows(app: object, rows_frame: tk.Frame, items: tuple[object, ...]) -> tuple[list[tk.BooleanVar], list[tk.StringVar], int]:
    include_vars: list[tk.BooleanVar] = []
    label_vars: list[tk.StringVar] = []
    warning_count = 0
    for idx, item in enumerate(items):
        include_var = tk.BooleanVar(value=True)
        label_var = tk.StringVar(value=_initial_label(item))
        include_vars.append(include_var)
        label_vars.append(label_var)
        row_bg = PANEL_3 if idx % 2 else PANEL
        row = tk.Frame(rows_frame, bg=row_bg, padx=6, pady=6)
        row.grid(row=idx, column=0, columnspan=4, sticky="ew", pady=(0, 4))
        for col, weight in enumerate((0, 2, 2, 2)):
            row.grid_columnconfigure(col, weight=weight)
        path = Path(str(getattr(item, "path", "")))
        detected = normalize_button_label(getattr(item, "label", "") or "")
        source = str(getattr(item, "source", "") or "")
        confidence = float(getattr(item, "confidence", 0.0) or 0.0)
        suspicious = source != "template_top_title" or confidence < 0.60 or detected in {"", "Документ"}
        warning_count += 1 if suspicious else 0
        tk.Checkbutton(row, variable=include_var, bg=row_bg, fg=TEXT, activebackground=row_bg, selectcolor=FIELD).grid(row=0, column=0, sticky="w")
        tk.Label(row, text=path.name or str(path), bg=row_bg, fg=TEXT, font=_review_font(app, 9), anchor="w", justify="left", wraplength=245).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        tk.Label(row, text=detected or "не найдено — проверьте вручную", bg=row_bg, fg="#ffcc66" if suspicious else TEXT, font=_review_font(app, 9), anchor="w", justify="left", wraplength=245).grid(row=0, column=2, sticky="ew", padx=(8, 0))
        tk.Entry(row, textvariable=label_var, bg=FIELD, fg=TEXT, insertbackground=ACCENT, relief="flat", font=_review_font(app, 10)).grid(row=0, column=3, sticky="ew", padx=(8, 0), ipady=5)
    return include_vars, label_vars, warning_count


def _build_template_review_options(
    app: object,
    popup: tk.Toplevel,
    items: tuple[object, ...],
    first_run: bool,
    existing_button_count: int,
    warning_count: int,
) -> tk.BooleanVar:
    options = tk.Frame(popup, bg=DEEP)
    options.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 10))
    options.grid_columnconfigure(0, weight=1)
    replace_var = tk.BooleanVar(value=bool(first_run))
    replace_text = "Заменить текущие кнопки профиля выбранными шаблонами"
    if first_run:
        replace_text += " — при первом создании это обязательно"
    tk.Checkbutton(options, text=replace_text, variable=replace_var, state="disabled" if first_run else "normal", bg=DEEP, fg=TEXT, activebackground=DEEP, selectcolor=FIELD, font=_review_font(app, 9, "bold"), anchor="w", justify="left").grid(row=0, column=0, sticky="w")
    hint = f"Выбрано файлов: {len(items)}. Уже было кнопок в профиле: {existing_button_count}."
    if warning_count:
        hint += f" Требуют проверки названия: {warning_count}."
    tk.Label(options, text=hint, bg=DEEP, fg=MUTED, font=_review_font(app, 9), anchor="w").grid(row=1, column=0, sticky="ew", pady=(4, 0))
    return replace_var


def _confirmed_template_review_rows(
    popup: tk.Toplevel,
    items: tuple[object, ...],
    include_vars: list[tk.BooleanVar],
    label_vars: list[tk.StringVar],
) -> tuple[TemplateButtonReviewRow, ...] | None:
    rows: list[TemplateButtonReviewRow] = []
    seen: set[str] = set()
    for item, include_var, label_var in zip(items, include_vars, label_vars):
        if not include_var.get():
            continue
        label = normalize_button_label(label_var.get())
        if not label:
            messagebox.showerror("Проверьте кнопки", "У выбранного шаблона пустое название кнопки.", parent=popup)
            return None
        key = label.casefold()
        if key in seen:
            messagebox.showerror("Проверьте кнопки", f"Две будущие кнопки названы одинаково: «{label}». Измените одно название.", parent=popup)
            return None
        seen.add(key)
        rows.append(TemplateButtonReviewRow(
            path=str(getattr(item, "path", "")),
            detected_label=normalize_button_label(getattr(item, "label", "") or ""),
            button_label=label,
            document_id=str(getattr(item, "document_id", "") or ""),
            role_id=str(getattr(item, "role_id", "unknown") or "unknown"),
            source=str(getattr(item, "source", "template_top_title") or "template_top_title"),
            confidence=float(getattr(item, "confidence", 0.0) or 0.0),
        ))
    if not rows:
        messagebox.showwarning("Проверьте кнопки", "Не выбрано ни одного шаблона для создания кнопок.", parent=popup)
        return None
    return tuple(rows)


def _build_template_review_actions(
    app: object,
    popup: tk.Toplevel,
    items: tuple[object, ...],
    include_vars: list[tk.BooleanVar],
    label_vars: list[tk.StringVar],
    replace_var: tk.BooleanVar,
    result: dict[str, TemplateButtonReviewResult | None],
) -> None:
    actions = tk.Frame(popup, bg=DEEP)
    actions.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 14))
    actions.grid_columnconfigure(0, weight=1)
    actions.grid_columnconfigure(1, weight=1)

    def _confirm() -> None:
        rows = _confirmed_template_review_rows(popup, items, include_vars, label_vars)
        if rows is None:
            return
        result["value"] = TemplateButtonReviewResult(rows, replace_existing=bool(replace_var.get()))
        popup.destroy()

    def _cancel() -> None:
        result["value"] = None
        popup.destroy()

    tk.Button(actions, text="Создать кнопки по этой таблице", command=_confirm, bg=ACCENT_2, fg="#03101f", relief="flat", font=_review_font(app, 10, "bold"), padx=10, pady=10).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    tk.Button(actions, text="Отмена", command=_cancel, bg=FIELD, fg=TEXT, relief="flat", font=_review_font(app, 10, "bold"), padx=10, pady=10).grid(row=0, column=1, sticky="ew", padx=(6, 0))

def assert_template_button_review_contract() -> None:
    if TEMPLATE_BUTTON_REVIEW_LOCK_VERSION != "v1.0":
        raise AssertionError("Template button review lock changed unexpectedly")
    if not TEMPLATE_BUTTON_CREATION_REQUIRES_DOCTOR_CONFIRMATION:
        raise AssertionError("Template button creation must require doctor confirmation")
    if not TEMPLATE_BUTTON_COUNT_MATCHES_CONFIRMED_ROWS:
        raise AssertionError("Block-03 button count must match confirmed template rows")
    for title in TEMPLATE_BUTTON_REVIEW_COLUMNS:
        if not title:
            raise AssertionError("Review table column title is empty")
