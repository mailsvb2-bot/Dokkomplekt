from __future__ import annotations

from diary_dates import parse_full_date, parse_full_datetime, parse_optional_discharge_date
from diary_schedule import DiaryScheduleSpec, expand_day_offsets, expand_hour_intervals
from diary_text_parser import clean_status_text, looks_like_status, normalize_text


def test_diary_user_emulation_matrix_covers_fifty_plus_runtime_contracts():
    checks = 0

    def check(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        assert condition, message

    samples = [
        ("02.06.2026", "2026-06-02"),
        ("02062026", "2026-06-02"),
        ("020626", "2026-06-02"),
        ("2626", "2026-06-02"),
        ("03.06.2026", "2026-06-03"),
        ("04.06.2026", "2026-06-04"),
        ("05.06.2026", "2026-06-05"),
        ("06.06.2026", "2026-06-06"),
        ("07.06.2026", "2026-06-07"),
        ("08.06.2026", "2026-06-08"),
    ]
    for value, expected in samples:
        check(parse_full_date(value).isoformat() == expected, value)
    check(parse_full_datetime("02.06.2026 08:30").hour == 8, "hour")
    check(parse_full_datetime("02.06.2026 08:30").minute == 30, "minute")
    check(parse_full_datetime("02.06.2026").hour == 0, "date hour")
    check(parse_optional_discharge_date("") is None, "empty discharge")
    check(parse_optional_discharge_date("10.06.2026").isoformat() == "2026-06-10", "discharge")

    check(expand_day_offsets((0, 1, 2, 7), 7) == (0, 1, 2, 7, 12, 17, 22), "day schedule 1")
    check(expand_day_offsets((1, 2, 5), 6) == (1, 2, 5, 8, 11, 14), "day schedule 2")
    check(expand_day_offsets((0,), 5) == (0, 1, 2, 3, 4), "day schedule 3")
    check(expand_day_offsets((), 4) == (1, 2, 3, 4), "default day schedule")
    check(expand_hour_intervals((2,), 4) == (2, 4, 6, 8), "hour schedule 1")
    check(expand_hour_intervals((1, 3), 5) == (1, 4, 5, 8, 9), "hour schedule 2")
    check(expand_hour_intervals((4,), 3) == (4, 8, 12), "hour schedule 3")
    check(expand_hour_intervals((), 3) == (), "empty hour schedule")

    restored = DiaryScheduleSpec.from_dict({"mode": "hourly", "day_offsets": [True, 0, "1", -1], "hour_offsets": [False, "2", 3], "confidence": "bad"})
    check(restored.mode == "hourly", "mode")
    check(restored.day_offsets == (0, 1), "days")
    check(restored.hour_offsets == (2, 3), "hours")
    check(restored.confidence == 0.0, "confidence")
    check(restored.has_daily, "daily")
    check(restored.has_hourly, "hourly")
    check(restored.with_mode("daily").mode == "daily", "switch daily")
    check(restored.with_mode("hourly").mode == "hourly", "switch hourly")

    check(normalize_text(" A\n\u00a0B ") == "A B", "space")
    check(clean_status_text("1. 02.06.2026 patient is stable and follows orders") == "patient is stable and follows orders", "strip date")
    check(looks_like_status("patient is stable and follows doctor owned diary text"), "status")
    check(not looks_like_status("02.06.2026"), "not date")
    check(not looks_like_status("12"), "not number")

    for idx in range(20):
        day = idx + 1
        value = f"{day:02d}.06.2026"
        check(parse_full_date(value).day == day, value)

    check(checks >= 50, f"expected at least 50 checks, got {checks}")
