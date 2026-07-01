from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from docx import Document

from desktop_intake import DesktopCandidate
from desktop_intake_mixin import DesktopIntakeMixin
from diary_template_selection import DiaryTemplateSelectionMixin


class _TemplateSelectionHarness(DiaryTemplateSelectionMixin):
    def __init__(self, folder: Path, admission: datetime) -> None:
        self.folder = folder
        self.admission = admission
        self.diary_template_dir = str(folder)
        self.diary_files: list[str] = []
        self._diary_files_auto_selected = True
        self.label_states: list[bool | None] = []
        self.logs: list[str] = []
        self.redraw_count = 0

    def _admission_datetime_for_diary_template(self):
        return self.admission

    def _candidate_numbered_diary_template_dirs(self):
        return [self.folder]

    def _iter_diary_template_docx_files(self, root):
        return sorted(Path(root).iterdir(), key=lambda p: p.name.lower())

    def _is_numbered_diary_template_file(self, path, day):
        return path.stem == f"{day:02d}" or path.stem == str(day)

    def _template_content_first_day(self, path):
        return None

    def _remember_numbered_diary_template_dir(self, folder):
        self.remembered = str(folder)

    def _update_diary_template_label(self, *, success=None):
        self.label_states.append(success)

    def _redraw_selection_controls(self):
        self.redraw_count += 1

    def _log(self, message):
        self.logs.append(message)


def _make_docx(path: Path) -> None:
    doc = Document()
    doc.add_paragraph("template")
    doc.save(path)


def test_auto_diary_template_selector_clears_stale_auto_file_when_current_day_is_missing(tmp_path: Path) -> None:
    folder = tmp_path / "dates"
    folder.mkdir()
    old_template = folder / "01.docx"
    _make_docx(old_template)

    app = _TemplateSelectionHarness(folder, datetime(2026, 6, 2))
    app.diary_files = [str(old_template)]
    app._diary_files_auto_selected = True

    assert app._auto_select_numbered_diary_template(ask_folder=False) is False
    assert app.diary_files == []
    assert app._diary_files_auto_selected is False
    assert app.label_states[-1] is False


def test_manual_diary_template_selection_is_preserved_when_current_day_is_missing(tmp_path: Path) -> None:
    folder = tmp_path / "dates"
    folder.mkdir()
    manual_template = folder / "01.docx"
    _make_docx(manual_template)

    app = _TemplateSelectionHarness(folder, datetime(2026, 6, 2))
    app.diary_files = [str(manual_template)]
    app._diary_files_auto_selected = False

    assert app._auto_select_numbered_diary_template(ask_folder=False) is True
    assert app.diary_files == [str(manual_template)]
    assert app._diary_files_auto_selected is False


class _Root:
    def __init__(self) -> None:
        self.after_calls: list[tuple[int, object]] = []

    def after(self, delay_ms, callback):
        self.after_calls.append((delay_ms, callback))
        return "after-id"


class _DesktopPollHarness(DesktopIntakeMixin):
    def __init__(self, candidate: DesktopCandidate) -> None:
        self.root = _Root()
        self._candidate = candidate
        self._desktop_intake_enabled = True
        self._desktop_intake_folder = str(candidate.path.parent)
        self._desktop_intake_seen_signatures: set[str] = set()
        self._desktop_intake_popup_open = False
        self._desktop_intake_popup_outcome = ""
        self._desktop_intake_last_popup_opened = False
        self._desktop_intake_poll_job = None
        self.persist_count = 0

    def _open_desktop_intake_popup(self, primary_path):
        self._desktop_intake_last_popup_opened = True
        self._desktop_intake_popup_outcome = "opened"
        return False

    def _persist_desktop_intake_settings(self):
        self.persist_count += 1


def test_desktop_intake_does_not_mark_seen_after_only_opened_popup(tmp_path: Path) -> None:
    primary = tmp_path / "primary.docx"
    _make_docx(primary)
    candidate = DesktopCandidate(primary, (primary.stat().st_size, int(primary.stat().st_mtime)))
    app = _DesktopPollHarness(candidate)
    marked: list[DesktopCandidate] = []

    with (
        patch("desktop_intake.scan_primary_candidates", return_value=(candidate,)),
        patch("desktop_intake.mark_seen", lambda seen, item: marked.append(item)),
    ):
        app._poll_desktop_intake_folder()

    assert marked == []
    assert app.persist_count == 0
    assert app.root.after_calls, "poller must still reschedule itself"


def test_desktop_intake_marks_seen_after_explicit_ignored_popup(tmp_path: Path) -> None:
    primary = tmp_path / "primary.docx"
    _make_docx(primary)
    candidate = DesktopCandidate(primary, (primary.stat().st_size, int(primary.stat().st_mtime)))
    app = _DesktopPollHarness(candidate)

    def ignored_popup(_primary_path):
        app._desktop_intake_last_popup_opened = True
        app._desktop_intake_popup_outcome = "ignored"
        return False

    app._open_desktop_intake_popup = ignored_popup
    marked: list[DesktopCandidate] = []

    with (
        patch("desktop_intake.scan_primary_candidates", return_value=(candidate,)),
        patch("desktop_intake.mark_seen", lambda seen, item: marked.append(item)),
    ):
        app._poll_desktop_intake_folder()

    assert marked == [candidate]
    assert app.persist_count == 1


def test_background_agent_trusts_gui_seen_signature_before_retrying_pending(tmp_path: Path, monkeypatch) -> None:
    import json
    import desktop_intake_agent
    from desktop_intake import DESKTOP_INTAKE_SETUP_PROMPT_VERSION

    signature = "a" * 64
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "desktop_intake": {
            "asked": True,
            "enabled": True,
            "folder": str(tmp_path),
            "prompt_version": DESKTOP_INTAKE_SETUP_PROMPT_VERSION,
            "seen_signatures": [signature],
        }
    }), encoding="utf-8")
    monkeypatch.setattr(desktop_intake_agent, "_settings_path", lambda: settings_path)
    monkeypatch.setattr(desktop_intake_agent, "_write_log", lambda _message: None)

    seen: set[str] = set()
    active, changed = desktop_intake_agent._resolve_pending_state(
        {"pending": {"signature": signature, "launched_at": 0}},
        seen,
        folder=tmp_path,
    )

    assert active == {}
    assert changed is True
    assert signature in seen
