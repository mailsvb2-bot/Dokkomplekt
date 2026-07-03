"""Deterministic text-diary schedule model.

This module answers only one question: which calendar or hour offsets should the
text diary generator use relative to admission.  It must not inspect or fill
DOCX diary tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
from typing import Iterable, Mapping, Sequence

DIARY_SCHEDULE_LOCK_VERSION = "v1.3"
DIARY_SCHEDULE_DOCTOR_CONFIRMATION_REQUIRED = True
DIARY_MANUAL_DAY_INPUT_MIN_COUNT = 10
DIARY_HOURLY_MODE_IS_PATIENT_LEVEL_CHOICE = True
DIARY_SCHEDULE_REJECTS_NEGATIVE_INPUTS = True
DIARY_SCHEDULE_EXTENDS_DAY_PATTERN_INSTEAD_OF_CYCLING = True
DIARY_HOURLY_VALUES_ARE_INTERVALS = True
DIARY_SCHEDULE_REJECTS_BOOL_VALUES = True
DIARY_SCHEDULE_TOLERATES_BAD_CONFIDENCE = True
DIARY_CALENDAR_NO_TEMPLATE_REQUIRED = True
DIARY_CALENDAR_STARTS_AFTER_ADMISSION = True
DIARY_SCHEDULE_HAS_NO_TABLE_INFERENCE = True
DIARY_POPUP_STYLE_CHOICES = (
    "каждый день",
    "1, 2, 3 день...",
    "каждый день по времени",
    "свой стиль",
)
DEFAULT_CALENDAR_DIARY_DAY_OFFSETS: tuple[int, ...] = tuple(range(1, 11))
CLINICAL_CALENDAR_DIARY_DAY_OFFSETS: tuple[int, ...] = (1, 2, 3, 7, 10, 14, 17, 21, 24, 28)
DEFAULT_TIMED_DIARY_HOUR_INTERVAL = 24

_SIGNED_INT_RE = re.compile(r"[-+]?\d+")


@dataclass(frozen=True)
class DiaryScheduleSpec:
    """A doctor-confirmed diary date/time principle."""

    mode: str = "daily"  # daily / hourly
    day_offsets: tuple[int, ...] = ()
    hour_offsets: tuple[int, ...] = ()
    confidence: float = 0.0
    source: str = "manual"

    @property
    def has_daily(self) -> bool:
        return bool(self.day_offsets)

    @property
    def has_hourly(self) -> bool:
        return bool(self.hour_offsets)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "day_offsets": list(self.day_offsets),
            "hour_offsets": list(self.hour_offsets),
            "confidence": self.confidence,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object] | None) -> "DiaryScheduleSpec":
        if not isinstance(data, Mapping):
            return cls()
        mode = str(data.get("mode", "daily") or "daily").strip().lower()
        if mode not in {"daily", "hourly"}:
            mode = "daily"
        return cls(
            mode=mode,
            day_offsets=tuple(_positive_unique_ints(data.get("day_offsets", ()), allow_zero=True)),
            hour_offsets=tuple(_positive_unique_ints(data.get("hour_offsets", ()), allow_zero=False)),
            confidence=_safe_confidence(data.get("confidence", 0.0)),
            source=str(data.get("source", "manual") or "manual").strip() or "manual",
        )

    def with_mode(self, mode: str) -> "DiaryScheduleSpec":
        mode = "hourly" if str(mode).strip().lower() == "hourly" else "daily"
        return DiaryScheduleSpec(mode, self.day_offsets, self.hour_offsets, self.confidence, self.source)


def default_calendar_diary_schedule() -> DiaryScheduleSpec:
    return DiaryScheduleSpec("daily", DEFAULT_CALENDAR_DIARY_DAY_OFFSETS, (), 1.0, "popup_every_day")


def clinical_calendar_diary_schedule() -> DiaryScheduleSpec:
    return DiaryScheduleSpec("daily", CLINICAL_CALENDAR_DIARY_DAY_OFFSETS, (), 1.0, "popup_1_2_3_day")


def timed_daily_diary_schedule(interval_hours: int = DEFAULT_TIMED_DIARY_HOUR_INTERVAL) -> DiaryScheduleSpec:
    interval = max(1, int(interval_hours or DEFAULT_TIMED_DIARY_HOUR_INTERVAL))
    return DiaryScheduleSpec("hourly", (), (interval,), 1.0, "popup_every_day_by_time")


def diary_calendar_schedule_from_choice(choice: str) -> DiaryScheduleSpec:
    """Turn the doctor's day-style popup choice into a daily calendar schedule."""

    text = str(choice or "").strip().lower().replace("ё", "е")
    if not text or text in {"1", "ежедневно", "каждый день", "каждодневно"} or "кажд" in text or "ежеднев" in text:
        return default_calendar_diary_schedule()
    if text in {"2", "1,2,3", "1 2 3", "1, 2, 3", "клинически", "контроль"} or "клинич" in text or "контрол" in text:
        return clinical_calendar_diary_schedule()
    values = parse_day_offsets(text, require_minimum=False)
    if not values:
        raise ValueError("Введите 1 для ежедневных дневников, 2 для схемы 1,2,3 день... или свои дни: +1, +2, +3, +7, +14.")
    return DiaryScheduleSpec("daily", values, (), 1.0, "popup_custom_day_style")


def diary_hourly_schedule_from_choice(choice: str) -> DiaryScheduleSpec:
    """Turn the doctor's time-style popup choice into hour intervals.

    A single value is treated as an interval and later expanded cumulatively.
    For example, 24 means every day at the same time as admission; 2 means every
    2 hours.  A list such as 1, 2, 4 is treated as a repeating interval pattern.
    """

    text = str(choice or "").strip().lower().replace("ё", "е")
    if not text or text in {"3", "по времени", "каждый день по времени", "ежедневно по времени"}:
        return timed_daily_diary_schedule()
    values = tuple(_parse_positive_sequence(text, allow_zero=False, value_name="часы"))
    if not values:
        raise ValueError("Укажите интервал в часах: 24 — каждый день по времени, 2 — каждые 2 часа, или свой стиль: 1, 2, 4, 8.")
    return DiaryScheduleSpec("hourly", (), values, 1.0, "popup_custom_time_style")


def parse_day_offsets(text: str, *, require_minimum: bool = False) -> tuple[int, ...]:
    values = tuple(_parse_positive_sequence(text, allow_zero=False, value_name="дни"))
    if require_minimum and len(values) < DIARY_MANUAL_DAY_INPUT_MIN_COUNT:
        raise ValueError(f"Введите минимум {DIARY_MANUAL_DAY_INPUT_MIN_COUNT} чисел. Например: +1, +2, +3, +5, +7, +14, +21, +28, +35, +42.")
    return values


def parse_hour_offsets(text: str) -> tuple[int, ...]:
    values = tuple(_parse_positive_sequence(text, allow_zero=False, value_name="часы"))
    if not values:
        raise ValueError("Введите интервалы цифрами, например: 24 или 1, 2, 3, 4, 6, 8, 12, 24.")
    return values


def infer_diary_schedule_from_docx(paths: Sequence[str]) -> DiaryScheduleSpec:
    """Legacy compatibility: table-template inference is removed."""
    _ = paths
    return DiaryScheduleSpec("daily", (), (), 0.0, "table_inference_removed")


def describe_schedule(spec: DiaryScheduleSpec) -> str:
    if spec.mode == "hourly" and spec.hour_offsets:
        if spec.source == "popup_every_day_by_time" and spec.hour_offsets == (DEFAULT_TIMED_DIARY_HOUR_INTERVAL,):
            return "каждый день по времени: +24 ч от времени госпитализации"
        return "по времени от момента поступления: " + ", ".join(f"+{value} ч" for value in spec.hour_offsets[:16])
    if spec.day_offsets:
        if spec.source == "popup_every_day":
            return "каждый день: ежедневно, начиная с даты госпитализации +1 день"
        if spec.source == "popup_1_2_3_day":
            return "1, 2, 3 день...: +1, +2, +3, +7 день, затем продолжение по той же схеме"
        return "свой стиль: " + ", ".join(f"+{value} д" for value in spec.day_offsets[:16])
    return "принцип дневников не выбран"


def expand_day_offsets(offsets: Sequence[int], limit: int) -> tuple[int, ...]:
    """Expand a confirmed day pattern without cycling back to the beginning."""

    if limit <= 0:
        return ()
    values = _positive_unique_ints(offsets, allow_zero=True)
    if not values:
        return tuple(range(1, limit + 1))
    result = list(values[:limit])
    if len(result) >= limit:
        return tuple(result)
    positive_steps = [b - a for a, b in zip(values, values[1:]) if b > a]
    step = positive_steps[-1] if positive_steps else 1
    while len(result) < limit:
        result.append(result[-1] + max(1, step))
    return tuple(result)


def expand_hour_intervals(intervals: Sequence[int], limit: int) -> tuple[int, ...]:
    """Convert doctor-entered hour intervals into cumulative hour offsets."""

    if limit <= 0:
        return ()
    values = _positive_unique_ints(intervals, allow_zero=False)
    if not values:
        return ()
    result: list[int] = []
    total = 0
    index = 0
    while len(result) < limit:
        total += values[index % len(values)]
        result.append(total)
        index += 1
    return tuple(result)


def planned_diary_datetimes(admission: datetime, spec: DiaryScheduleSpec, *, limit: int) -> tuple[datetime, ...]:
    if limit <= 0:
        return ()
    if spec.mode == "hourly" and spec.hour_offsets:
        return tuple(admission + timedelta(hours=hour) for hour in expand_hour_intervals(spec.hour_offsets, limit))
    offsets = expand_day_offsets(spec.day_offsets, limit)
    return tuple(datetime.combine(admission.date() + timedelta(days=offset), admission.time()) for offset in offsets)


def planned_diary_dates(admission: date, spec: DiaryScheduleSpec, *, limit: int) -> tuple[date, ...]:
    if limit <= 0:
        return ()
    base = datetime.combine(admission, time(hour=0, minute=0))
    return tuple(item.date() for item in planned_diary_datetimes(base, spec, limit=limit))


def planned_diary_time_labels(spec: DiaryScheduleSpec, *, limit: int, admission_time: time | None = None) -> tuple[str, ...]:
    if spec.mode != "hourly" or not spec.hour_offsets or limit <= 0:
        return tuple("" for _ in range(max(0, limit)))
    base = datetime.combine(date(2000, 1, 1), admission_time or time(hour=0, minute=0))
    return tuple((base + timedelta(hours=hour)).strftime("%H:%M") for hour in expand_hour_intervals(spec.hour_offsets, limit))


def assert_diary_schedule_lock() -> None:
    if DIARY_SCHEDULE_LOCK_VERSION != "v1.3":
        raise AssertionError("Diary schedule lock changed unexpectedly")
    if not DIARY_SCHEDULE_DOCTOR_CONFIRMATION_REQUIRED:
        raise AssertionError("Diary schedule inference must remain doctor-confirmed")
    if not DIARY_HOURLY_MODE_IS_PATIENT_LEVEL_CHOICE:
        raise AssertionError("Hourly diary mode must remain a per-patient choice")
    if not DIARY_SCHEDULE_REJECTS_NEGATIVE_INPUTS:
        raise AssertionError("Negative diary schedule inputs must stay rejected")
    if not DIARY_SCHEDULE_EXTENDS_DAY_PATTERN_INSTEAD_OF_CYCLING:
        raise AssertionError("Daily diary schedules must extend, not cycle")
    if not DIARY_HOURLY_VALUES_ARE_INTERVALS:
        raise AssertionError("Hourly values must remain interval patterns")
    if not DIARY_SCHEDULE_REJECTS_BOOL_VALUES:
        raise AssertionError("Bool values must not become diary day/hour offsets")
    if not DIARY_SCHEDULE_TOLERATES_BAD_CONFIDENCE:
        raise AssertionError("Bad saved confidence must not crash diary schedule loading")
    if not DIARY_CALENDAR_NO_TEMPLATE_REQUIRED or not DIARY_CALENDAR_STARTS_AFTER_ADMISSION:
        raise AssertionError("Program calendar must remain available without date DOCX templates")
    if not DIARY_SCHEDULE_HAS_NO_TABLE_INFERENCE:
        raise AssertionError("Diary schedule must not infer from DOCX table templates")
    if default_calendar_diary_schedule().day_offsets[:3] != (1, 2, 3):
        raise AssertionError("Default diary calendar must start from admission +1 day")
    if diary_calendar_schedule_from_choice("2").day_offsets[:4] != (1, 2, 3, 7):
        raise AssertionError("1,2,3 day diary choice is broken")
    if diary_hourly_schedule_from_choice("3").hour_offsets != (24,):
        raise AssertionError("Every day by time diary choice is broken")
    if expand_day_offsets((1, 2, 5), 5) != (1, 2, 5, 8, 11):
        raise AssertionError("Daily pattern extension contract is broken")
    if expand_hour_intervals((1,), 4) != (1, 2, 3, 4):
        raise AssertionError("Hourly interval expansion contract is broken")
    restored = DiaryScheduleSpec.from_dict({"day_offsets": [True, "2", 0], "hour_offsets": [False, "3"], "confidence": "bad"})
    if restored.day_offsets != (2, 0) or restored.hour_offsets != (3,) or restored.confidence != 0.0:
        raise AssertionError("Diary schedule safe restore contract is broken")


def _safe_confidence(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _parse_positive_sequence(text: str, *, allow_zero: bool, value_name: str) -> list[int]:
    values: list[int] = []
    seen: set[int] = set()
    negatives: list[int] = []
    for token in _SIGNED_INT_RE.findall(str(text or "")):
        value = int(token)
        if value < 0:
            negatives.append(value)
            continue
        if value == 0 and not allow_zero:
            continue
        if value not in seen:
            values.append(value)
            seen.add(value)
    if negatives:
        raise ValueError(f"Отрицательные значения для расписания дневников не допускаются: {', '.join(map(str, negatives))}.")
    return values


def _positive_unique_ints(values: Iterable[object], *, allow_zero: bool = False) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for raw in values:
        if isinstance(raw, bool):
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value < 0 or (value == 0 and not allow_zero):
            continue
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
