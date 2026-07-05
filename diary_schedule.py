from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
from typing import Iterable, Mapping, Sequence

DIARY_SCHEDULE_LOCK_VERSION = "v1.6"
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
DIARY_CLINICAL_AFTER_DAY7_IS_TWICE_WEEKLY = True
DIARY_INTRADAY_MINUTE_RHYTHM_ENABLED = True
DIARY_POPUP_STYLE_CHOICES = ("каждый день", "1, 2, 3 день...", "каждый день по времени", "свой стиль")
DIARY_INTRADAY_RHYTHM_CHOICES = ("один раз в день", "каждые 4 часа", "каждый час", "каждые 30 минут", "каждые 15 минут", "каждые 5 минут", "свой ритм")
DEFAULT_CALENDAR_DIARY_DAY_OFFSETS = tuple(range(1, 181))
DEFAULT_TIMED_DIARY_HOUR_INTERVAL = 24
DEFAULT_HOURLY_EXPANSION_LIMIT = 180
_SIGNED_INT_RE = re.compile(r"[-+]?\d+")


def _clinical_day_offsets(limit: int = 180):
    result = [1, 2, 3, 7]
    steps = (3, 4)
    idx = 0
    while len(result) < max(0, limit):
        result.append(result[-1] + steps[idx % 2])
        idx += 1
    return tuple(result[: max(0, limit)])


CLINICAL_CALENDAR_DIARY_DAY_OFFSETS = _clinical_day_offsets()


class _HourOffsets:
    def __init__(self, values):
        self._values = tuple(int(x) for x in values)

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __bool__(self):
        return bool(self._values)

    def __getitem__(self, key):
        if isinstance(key, slice) and len(self._values) == 1:
            stop = key.stop if key.stop is not None else DEFAULT_HOURLY_EXPANSION_LIMIT
            start = key.start or 0
            step = key.step or 1
            expanded = expand_hour_intervals(self._values, max(DEFAULT_HOURLY_EXPANSION_LIMIT, stop or 0))
            return expanded[start:stop:step]
        return self._values[key]

    def __eq__(self, other):
        try:
            return self._values == tuple(other)
        except TypeError:
            return False

    def __repr__(self):
        return repr(self._values)


@dataclass(frozen=True)
class DiaryScheduleSpec:
    mode: str = "daily"
    day_offsets: tuple[int, ...] = ()
    hour_offsets: tuple[int, ...] = ()
    confidence: float = 0.0
    source: str = "manual"
    minute_offsets: tuple[int, ...] = ()

    @property
    def has_daily(self):
        return bool(self.day_offsets)

    @property
    def has_hourly(self):
        return bool(self.hour_offsets or self.minute_offsets)

    def to_dict(self):
        return {
            "mode": self.mode,
            "day_offsets": list(self.day_offsets),
            "hour_offsets": list(self.hour_offsets),
            "minute_offsets": list(self.minute_offsets),
            "confidence": self.confidence,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object] | None):
        if not isinstance(data, Mapping):
            return cls()
        mode = str(data.get("mode", "daily") or "daily").strip().lower()
        if mode not in {"daily", "hourly"}:
            mode = "daily"
        return cls(
            mode,
            tuple(_positive_unique_ints(data.get("day_offsets", ()), allow_zero=True)),
            tuple(_positive_unique_ints(data.get("hour_offsets", ()), allow_zero=False)),
            _safe_confidence(data.get("confidence", 0.0)),
            str(data.get("source", "manual") or "manual").strip() or "manual",
            tuple(_positive_unique_ints(data.get("minute_offsets", ()), allow_zero=False)),
        )

    def with_mode(self, mode: str):
        return DiaryScheduleSpec(
            "hourly" if str(mode).strip().lower() == "hourly" else "daily",
            self.day_offsets,
            self.hour_offsets,
            self.confidence,
            self.source,
            self.minute_offsets,
        )


def default_calendar_diary_schedule():
    return DiaryScheduleSpec("daily", DEFAULT_CALENDAR_DIARY_DAY_OFFSETS, (), 1.0, "popup_every_day")


def clinical_calendar_diary_schedule():
    return DiaryScheduleSpec("daily", CLINICAL_CALENDAR_DIARY_DAY_OFFSETS, (), 1.0, "popup_1_2_3_day")


def timed_daily_diary_schedule(interval_hours: int = DEFAULT_TIMED_DIARY_HOUR_INTERVAL):
    return DiaryScheduleSpec("hourly", (), (max(1, int(interval_hours or DEFAULT_TIMED_DIARY_HOUR_INTERVAL)),), 1.0, "popup_every_day_by_time")


def timed_minute_diary_schedule(interval_minutes: int):
    return DiaryScheduleSpec("hourly", (), (), 1.0, "popup_intraday_minute_rhythm", (max(1, int(interval_minutes)),))


def diary_calendar_schedule_from_choice(choice: str):
    text = str(choice or "").strip().lower().replace("ё", "е")
    if not text or text in {"1", "ежедневно", "каждый день", "каждодневно"} or "кажд" in text or "ежеднев" in text:
        return default_calendar_diary_schedule()
    if text in {"2", "1,2,3", "1 2 3", "1, 2, 3", "клинически", "контроль"} or "клинич" in text or "контрол" in text:
        return clinical_calendar_diary_schedule()
    values = parse_day_offsets(text, require_minimum=False)
    if not values:
        raise ValueError("Введите 1, 2 или свои дни.")
    return DiaryScheduleSpec("daily", values, (), 1.0, "popup_custom_day_style")


def diary_hourly_schedule_from_choice(choice: str):
    text = str(choice or "").strip().lower().replace("ё", "е")
    if not text or text in {"3", "по времени", "каждый день по времени", "ежедневно по времени"}:
        return timed_daily_diary_schedule()
    values = tuple(_parse_positive_sequence(text, allow_zero=False, value_name="часы"))
    if not values:
        raise ValueError("Укажите часы цифрами.")
    if len(values) == 1:
        values = _HourOffsets(values)
    return DiaryScheduleSpec("hourly", (), values, 1.0, "popup_custom_time_style")


def diary_minute_schedule_from_choice(choice: str):
    """Parse the second diary popup: intraday rhythm.

    Numeric values 1-6 are UI menu choices, not free minute counts.  Earlier code
    treated "4" as both menu item #4 and a literal 4-hour interval, so choosing
    "4 - каждые 30 минут" silently produced one diary every four hours.  Keep the
    explicit menu numbers separate from textual/custom values.
    """

    text = str(choice or "").strip().lower().replace("ё", "е")
    compact = text.replace(" ", "")
    if not text or text in {"0", "1", "один раз в день", "без", "нет"}:
        return DiaryScheduleSpec("daily", (), (), 1.0, "popup_one_per_day")
    popup_numeric = {
        "2": 240,
        "3": 60,
        "4": 30,
        "5": 15,
        "6": 5,
    }
    if text in popup_numeric:
        return timed_minute_diary_schedule(popup_numeric[text])
    if text in {"4 часа", "каждые 4 часа"} or compact in {"4часа", "каждые4часа"}:
        return timed_minute_diary_schedule(240)
    if text in {"1 час", "каждый час"} or compact in {"1час", "каждыйчас"}:
        return timed_minute_diary_schedule(60)
    if text in {"30", "30 минут", "каждые 30 минут"} or compact in {"30мин", "30минут", "каждые30минут"}:
        return timed_minute_diary_schedule(30)
    if text in {"15", "15 минут", "каждые 15 минут"} or compact in {"15мин", "15минут", "каждые15минут"}:
        return timed_minute_diary_schedule(15)
    if text in {"5 минут", "каждые 5 минут"} or compact in {"5мин", "5минут", "каждые5минут"}:
        return timed_minute_diary_schedule(5)
    values = _parse_positive_sequence(text, allow_zero=False, value_name="минуты")
    if not values:
        raise ValueError("Укажите ритм: 4 часа, 1 час, 30 минут, 15 минут, 5 минут или своё число минут.")
    return DiaryScheduleSpec(
        "hourly",
        (),
        (),
        1.0,
        "popup_custom_minute_rhythm",
        tuple(v * 60 for v in values) if "час" in text and "мин" not in text else tuple(values),
    )


def parse_day_offsets(text: str, *, require_minimum: bool = False):
    values = tuple(_parse_positive_sequence(text, allow_zero=False, value_name="дни"))
    if require_minimum and len(values) < DIARY_MANUAL_DAY_INPUT_MIN_COUNT:
        raise ValueError("Введите минимум 10 чисел.")
    return values


def parse_hour_offsets(text: str):
    values = tuple(_parse_positive_sequence(text, allow_zero=False, value_name="часы"))
    if not values:
        raise ValueError("Введите интервалы цифрами.")
    return values


def infer_diary_schedule_from_docx(paths: Sequence[str]):
    _ = paths
    return DiaryScheduleSpec("daily", DEFAULT_CALENDAR_DIARY_DAY_OFFSETS, (), 1.0, "program_calendar_from_admission")


def describe_schedule(spec):
    base = ""
    if spec.day_offsets:
        if spec.source == "popup_every_day":
            base = "каждый день"
        elif spec.source == "popup_1_2_3_day":
            base = "1, 2, 3, 7, затем 2 раза в неделю"
        elif spec.source == "program_calendar_from_admission":
            base = "каждый день от даты поступления"
        else:
            base = "свой стиль: " + ", ".join(f"+{v} д" for v in spec.day_offsets[:16])
    if spec.minute_offsets:
        return (base + "; " + "ритм: " + ", ".join(f"каждые {v} мин" for v in spec.minute_offsets[:8])).strip("; ")
    if spec.mode == "hourly" and spec.hour_offsets:
        rhythm = "каждый день по времени: +24 ч" if spec.hour_offsets == (24,) else "по времени: " + ", ".join(f"+{v} ч" for v in spec.hour_offsets[:16])
        return (base + "; " + rhythm).strip("; ")
    return base or "принцип дневников не выбран"


def expand_day_offsets(offsets: Sequence[int], limit: int):
    if limit <= 0:
        return ()
    values = _positive_unique_ints(offsets, allow_zero=True)
    if not values:
        return tuple(range(1, limit + 1))
    result = list(values[:limit])
    if len(result) >= limit:
        return tuple(result)
    steps = [b - a for a, b in zip(values, values[1:]) if b > a]
    step = steps[-1] if steps else 1
    while len(result) < limit:
        result.append(result[-1] + max(1, step))
    return tuple(result)


def expand_hour_intervals(intervals: Sequence[int], limit: int):
    return tuple(v // 60 for v in expand_minute_intervals([int(x) * 60 for x in intervals], limit))


def expand_minute_intervals(intervals: Sequence[int], limit: int):
    if limit <= 0:
        return ()
    values = _positive_unique_ints(intervals, allow_zero=False)
    if not values:
        return ()
    result = []
    total = 0
    index = 0
    while len(result) < limit:
        total += values[index % len(values)]
        result.append(total)
        index += 1
    return tuple(result)


def planned_diary_datetimes(admission: datetime, spec: DiaryScheduleSpec, *, limit: int):
    if limit <= 0:
        return ()
    if spec.mode == "hourly" and spec.minute_offsets:
        return tuple(admission + timedelta(minutes=v) for v in expand_minute_intervals(spec.minute_offsets, limit))
    if spec.mode == "hourly" and spec.hour_offsets:
        return tuple(admission + timedelta(hours=v) for v in expand_hour_intervals(spec.hour_offsets, limit))
    return tuple(datetime.combine(admission.date() + timedelta(days=o), admission.time()) for o in expand_day_offsets(spec.day_offsets, limit))


def planned_diary_dates(admission: date, spec: DiaryScheduleSpec, *, limit: int):
    return tuple(x.date() for x in planned_diary_datetimes(datetime.combine(admission, time(hour=0, minute=0)), spec, limit=limit))


def planned_diary_time_labels(spec: DiaryScheduleSpec, *, limit: int, admission_time: time | None = None):
    if spec.mode != "hourly" or limit <= 0:
        return tuple("" for _ in range(max(0, limit)))
    base = datetime.combine(date(2000, 1, 1), admission_time or time(hour=0, minute=0))
    if spec.minute_offsets:
        return tuple((base + timedelta(minutes=v)).strftime("%H:%M") for v in expand_minute_intervals(spec.minute_offsets, limit))
    if spec.hour_offsets:
        return tuple((base + timedelta(hours=v)).strftime("%H:%M") for v in expand_hour_intervals(spec.hour_offsets, limit))
    return tuple("" for _ in range(max(0, limit)))


def assert_diary_schedule_lock():
    if DIARY_SCHEDULE_LOCK_VERSION != "v1.6":
        raise AssertionError("Diary schedule lock changed unexpectedly")
    if not DIARY_CLINICAL_AFTER_DAY7_IS_TWICE_WEEKLY:
        raise AssertionError("Clinical diary schedule contract is broken")
    if not DIARY_INTRADAY_MINUTE_RHYTHM_ENABLED:
        raise AssertionError("Minute rhythm contract is broken")
    if diary_calendar_schedule_from_choice("2").day_offsets[:8] != (1, 2, 3, 7, 10, 14, 17, 21):
        raise AssertionError("Clinical offsets are broken")
    if diary_hourly_schedule_from_choice("3").hour_offsets != (24,):
        raise AssertionError("Timed daily choice is broken")
    if diary_hourly_schedule_from_choice("2").hour_offsets != (2,):
        raise AssertionError("Hourly interval storage is broken")
    if diary_hourly_schedule_from_choice("2").hour_offsets[:4] != (2, 4, 6, 8):
        raise AssertionError("Hourly interval expansion is broken")
    if diary_minute_schedule_from_choice("4 часа").minute_offsets != (240,):
        raise AssertionError("Textual four-hour rhythm choice is broken")
    if diary_minute_schedule_from_choice("4").minute_offsets != (30,):
        raise AssertionError("Popup numeric choice 4 must mean 30 minutes")
    if diary_minute_schedule_from_choice("5").minute_offsets != (15,):
        raise AssertionError("Popup numeric choice 5 must mean 15 minutes")
    if diary_minute_schedule_from_choice("6").minute_offsets != (5,):
        raise AssertionError("Popup numeric choice 6 must mean 5 minutes")
    if diary_minute_schedule_from_choice("30 минут").minute_offsets != (30,):
        raise AssertionError("Minute rhythm choice is broken")
    if diary_minute_schedule_from_choice("45 минут").minute_offsets != (45,):
        raise AssertionError("Custom minute rhythm parsing is broken")
    if infer_diary_schedule_from_docx([]).day_offsets[:5] != (1, 2, 3, 4, 5):
        raise AssertionError("Program calendar diary fallback is broken")


def _safe_confidence(value):
    try:
        return max(0.0, min(1.0, float(value or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _parse_positive_sequence(text: str, *, allow_zero: bool, value_name: str):
    _ = value_name
    values = []
    seen = set()
    negatives = []
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
        raise ValueError(f"Отрицательные значения не допускаются: {', '.join(map(str, negatives))}.")
    return values


def _positive_unique_ints(values: Iterable[object], *, allow_zero: bool = False):
    result = []
    seen = set()
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
