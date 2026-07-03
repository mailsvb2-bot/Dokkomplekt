from __future__ import annotations

from datetime import date
from typing import Sequence

NEUTRAL_FINAL_DIARY_TEXT = (
    "Состояние улучшилось. Жалоб активно не предъявляет. Отрицательной динамики не отмечается. "
    "Общее самочувствие стабильное, режим соблюдает, назначения выполняет. "
    "На текущую дату оформлена выписка из стационара. Даны рекомендации"
)


# Preserve doctor-owned values: the legacy table filler is intentionally closed
# so saved 01-31 table schedules cannot override the text-diary calendar route.
# if not str(hosp_cell.text or "").strip()

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
