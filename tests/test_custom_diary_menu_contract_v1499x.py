from __future__ import annotations

from diary_schedule import diary_minute_schedule_from_choice


def test_intraday_popup_numeric_choices_match_visible_menu():
    assert diary_minute_schedule_from_choice("2").minute_offsets == (240,)
    assert diary_minute_schedule_from_choice("3").minute_offsets == (60,)
    assert diary_minute_schedule_from_choice("4").minute_offsets == (30,)
    assert diary_minute_schedule_from_choice("5").minute_offsets == (15,)
    assert diary_minute_schedule_from_choice("6").minute_offsets == (5,)
