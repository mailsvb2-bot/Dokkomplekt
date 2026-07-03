from __future__ import annotations

from datetime import date
from typing import Sequence

NEUTRAL_FINAL_DIARY_TEXT = "".join(map(chr, (
    1057, 1086, 1089, 1090, 1086, 1103, 1085, 1080, 1077, 32, 1091, 1083, 1091, 1095, 1096, 1080,
    1083, 1086, 1089, 1100, 46, 32, 1046, 1072, 1083, 1086, 1073, 32, 1072, 1082, 1090, 1080,
    1074, 1085, 1086, 32, 1085, 1077, 32, 1087, 1088, 1077, 1076, 1098, 1103, 1074, 1083, 1103,
    1077, 1090, 46, 32, 1054, 1090, 1088, 1080, 1094, 1072, 1090, 1077, 1083, 1100, 1085, 1086,
    1081, 32, 1076, 1080, 1085, 1072, 1084, 1080, 1082, 1080, 32, 1085, 1077, 32, 1086, 1090,
    1084, 1077, 1095, 1072, 1077, 1090, 1089, 1103, 46, 32, 1054, 1073, 1097, 1077, 1077, 32,
    1089, 1072, 1084, 1086, 1095, 1091, 1074, 1089, 1090, 1074, 1080, 1077, 32, 1089, 1090, 1072,
    1073, 1080, 1083, 1100, 1085, 1086, 1077, 44, 32, 1088, 1077, 1078, 1080, 1084, 32, 1089,
    1086, 1073, 1083, 1102, 1076, 1072, 1077, 1090, 44, 32, 1085, 1072, 1079, 1085, 1072, 1095,
    1077, 1085, 1080, 1103, 32, 1074, 1099, 1087, 1086, 1083, 1085, 1103, 1077, 1090, 46, 32,
    1053, 1072, 32, 1090, 1077, 1082, 1091, 1097, 1091, 1102, 32, 1076, 1072, 1090, 1091, 32,
    1086, 1092, 1086, 1088, 1084, 1083, 1077, 1085, 1072, 32, 1074, 1099, 1087, 1080, 1089, 1082,
    1072, 32, 1080, 1079, 32, 1089, 1090, 1072, 1094, 1080, 1086, 1085, 1072, 1088, 1072, 46,
    32, 1044, 1072, 1085, 1099, 32, 1088, 1077, 1082, 1086, 1084, 1077, 1085, 1076, 1072, 1094,
    1080, 1080,
)))


def apply_diary_entries(
    data_entries: list[object],
    dated_entries: list[object],
    statuses: Sequence[str],
    *,
    start_idx: int,
    repeat_statuses: bool,
    keep_signature: bool,
    fill_months: bool,
    discharge_date: date | None,
    force_final_diary: bool,
    final_entry_index: int | None,
    patient_gender: str | None,
) -> dict[str, int]:
    _ = (
        data_entries,
        dated_entries,
        statuses,
        start_idx,
        repeat_statuses,
        keep_signature,
        fill_months,
        discharge_date,
        force_final_diary,
        final_entry_index,
        patient_gender,
    )
    raise NotImplementedError("Legacy diary table filling is removed; use the text diary route.")
