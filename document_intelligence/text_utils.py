from __future__ import annotations

import hashlib
import re

_PLACEHOLDER_ID_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)+")
_DATE_HINT_RE = re.compile(r"(?i)(date|day|period|дата|срок)")
_NUMBER_HINT_RE = re.compile(r"(?i)(number|amount|total|qty|price|номер|сумма|итого|цена|количество|№)")
_PERSON_HINT_RE = re.compile(r"(?i)(name|person|employee|customer|client|фио|сотрудник|клиент|заказчик)")
_BLOCK_HINT_RE = re.compile(r"(?i)(description|comment|summary|notes|текст|комментар|описание|заключение)")


def normalize(text: object) -> str:
    return " ".join(str(text or "").replace("\xa0", " ").strip().split())


def safe_token(label: str) -> str:
    text = normalize(label).lower().replace("ё", "е")
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if text:
        return text[:64]
    digest = hashlib.sha1(normalize(label).encode("utf-8")).hexdigest()[:12]
    return "field_" + digest


def custom_field_id(label: str) -> str:
    return "custom." + safe_token(label)


def field_id_from_placeholder(raw: str) -> str:
    raw = normalize(raw).strip("{} ")
    if _PLACEHOLDER_ID_RE.fullmatch(raw):
        return raw.lower()
    return custom_field_id(raw)


def value_kind(label: str, field_id: str = "") -> str:
    text = f"{label} {field_id}"
    if _DATE_HINT_RE.search(text):
        return "date"
    if _NUMBER_HINT_RE.search(text):
        return "number"
    if _PERSON_HINT_RE.search(text):
        return "person"
    if _BLOCK_HINT_RE.search(text):
        return "block"
    return "text"
