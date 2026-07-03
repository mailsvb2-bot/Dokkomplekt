from __future__ import annotations

from pathlib import Path

from app import RegressionStateOverlayMixin

ROOT = Path(__file__).resolve().parents[1]


class _DiaryRouteProbe(RegressionStateOverlayMixin):
    pass


def test_app_overlay_keeps_diaries_on_text_calendar_route():
    probe = _DiaryRouteProbe()

    assert probe._auto_select_numbered_diary_template(ask_folder=False) is False


def test_diary_runtime_does_not_pass_table_templates_to_generator():
    source = (ROOT / "actions_diary_flow.py").read_text(encoding="utf-8")

    assert "text_output = True" in source
    assert "diary_files=[]" in source
    assert "fill_diary_batch(" in source
    assert "_diary_text_output_enabled = True" in source


def test_diary_batch_keeps_text_fallback_route_available():
    source = (ROOT / "diary_batch.py").read_text(encoding="utf-8")

    assert "def _fill_text_diary_batch" in source
    assert "def _create_text_diary_document" in source
    assert "text_output" in source
