from __future__ import annotations

VALID_ADMISSION_MODES = ("первично", "повторно")


def normalize_admission_mode(value: object) -> str:
    text = " ".join(str(value or "").strip().casefold().replace("ё", "е").split())
    if text in {"первично", "первичный", "первичная", "впервые", "первый раз"}:
        return "первично"
    if text in {"повторно", "повторный", "повторная", "не впервые", "повторный раз"}:
        return "повторно"
    return ""


def admission_to_department_phrase(value: object) -> str:
    mode = normalize_admission_mode(value)
    return f"В 3 отделение КДП поступает {mode}" if mode else "В 3 отделение КДП поступает"
