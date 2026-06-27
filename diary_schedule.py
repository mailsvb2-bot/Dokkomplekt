"""Deterministic diary schedule model and inference.

This layer keeps diary-date logic out of UI code.  It answers only one
question: which calendar/hour offsets should diary rows use relative to
admission?  It is intentionally conservative; if inference is unclear, a doctor
confirms or enters the sequence manually.
"""

from __future__ import annotations

from diagnostic_logging import record_soft_exception
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
import re
from typing import Iterable, Mapping, Sequence

from docx import Document

from diary_table_columns import find_day_column, find_hospitalization_day_column, is_data_row
from diary_table_numbers import cell_int

DIARY_SCHEDULE_LOCK_VERSION = "v1.2"
DIARY_SCHEDULE_DOCTOR_CONFIRMATION_REQUIRED = True
DIARY_MANUAL_DAY_INPUT_MIN_COUNT = 10
DIARY_HOURLY_MODE_IS_PATIENT_LEVEL_CHOICE = True
DIARY_SCHEDULE_REJECTS_NEGATIVE_INPUTS = True
DIARY_SCHEDULE_EXTENDS_DAY_PATTERN_INSTEAD_OF_CYCLING = True
DIARY_HOURLY_VALUES_ARE_INTERVALS = True
DIARY_SCHEDULE_REJECTS_BOOL_VALUES = True
DIARY_SCHEDULE_TOLERATES_BAD_CONFIDENCE = True

_SIGNED_INT_RE = re.compile(r"[-+]?\d+")


@dataclass(frozen=True)
class DiaryScheduleSpec:
    """A saved date principle for custom diary templates."""

    mode: str = "daily"  # daily / hourly
    day_offsets: tuple[int, ...] = ()
    hour_offsets: tuple[int, ...] = ()  # doctor-entered hour interval pattern
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


def parse_day_offsets(text: str, *, require_minimum: bool = False) -> tuple[int, ...]:
    """Parse doctor's input like '+1, 2, 3, 5, 7, 14'."""

    values = tuple(_parse_positive_sequence(text, allow_zero=False, value_name="дни"))
    if require_minimum and len(values) < DIARY_MANUAL_DAY_INPUT_MIN_COUNT:
        raise ValueError(
            f"Введите минимум {DIARY_MANUAL_DAY_INPUT_MIN_COUNT} чисел. Например: +1, +2, +3, +5, +7, +14, +21, +28, +35, +42."
        )
    return values


def parse_hour_offsets(text: str) -> tuple[int, ...]:
    """Parse hourly diary interval pattern relative to admission time.

    The values are intervals, not absolute offsets.  For example ``1`` means
    every 1 hour; ``1, 2, 3`` means +1h, then +2h, then +3h, repeating the
    interval pattern for long tables.
    """

    values = tuple(_parse_positive_sequence(text, allow_zero=False, value_name="часы"))
    if not values:
        raise ValueError("Введите интервалы цифрами, например: 1, 2, 3, 4, 6, 8, 12, 24.")
    return values


def infer_diary_schedule_from_docx(paths: Sequence[str | Path]) -> DiaryScheduleSpec:
    """Infer day offsets from diary tables.

    The strongest signal is a column named like 'День госпитализации'.  If it is
    absent, the function falls back to numeric calendar-day rows and reports a
    lower confidence.  The doctor still confirms the result in UI.
    """

    values: list[int] = []
    weak_calendar_values: list[int] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if not path.exists() or path.suffix.lower() not in {".docx", ".docm"}:
            continue
        try:
            doc = Document(str(path))
        except Exception as exc:
            record_soft_exception("diary_schedule.open_template", exc, detail=str(path))
            continue
        for table in doc.tables:
            hospital_col = find_hospitalization_day_column(table)
            day_col = find_day_column(table)
            for row in table.rows:
                if not is_data_row(row, day_col, hospital_col):
                    continue
                if hospital_col is not None and len(row.cells) > hospital_col:
                    value = cell_int(row.cells[hospital_col].text)
                    if value is not None:
                        values.append(max(0, value))
                        continue
                if day_col is not None and len(row.cells) > day_col:
                    value = cell_int(row.cells[day_col].text)
                    if value is not None:
                        weak_calendar_values.append(max(0, value))
    if values:
        return DiaryScheduleSpec("daily", tuple(_positive_unique_ints(values, allow_zero=True)), (), 0.86, "inferred_hospitalization_day_column")
    if weak_calendar_values:
        return DiaryScheduleSpec("daily", tuple(_positive_unique_ints(weak_calendar_values, allow_zero=True)), (), 0.52, "inferred_calendar_day_column")
    return DiaryScheduleSpec("daily", (), (), 0.0, "unknown")


def describe_schedule(spec: DiaryScheduleSpec) -> str:
    if spec.mode == "hourly" and spec.hour_offsets:
        return "от момента поступления через интервалы: " + ", ".join(f"+{value} ч" for value in spec.hour_offsets[:16])
    if spec.day_offsets:
        return "от даты поступления: " + ", ".join(f"+{value} д" for value in spec.day_offsets[:16])
    return "принцип дат не определён автоматически"


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
    if DIARY_SCHEDULE_LOCK_VERSION != "v1.2":
        raise AssertionError("Diary schedule lock changed unexpectedly")
    if not DIARY_SCHEDULE_DOCTOR_CONFIRMATION_REQUIRED:
        raise AssertionError("Diary schedule inference must remain doctor-confirmed")
    if DIARY_MANUAL_DAY_INPUT_MIN_COUNT < 10:
        raise AssertionError("Manual diary day input must require at least 10 numbers")
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
