"""Privacy-safe doctor-facing action journal for document creation workflows.

The journal is local-only and stored in the application data folder, but it is
still a technical/support boundary.  It stores pseudonymous references and
counts instead of raw FIO, case numbers, dates, full diagnosis text, paths or
created patient file names.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

from diagnostic_logging import record_soft_exception
from medical_formatting import redact_technical_text, technical_ref

DOCTOR_ACTION_JOURNAL_LOCK_VERSION = "v1.3"
HISTORY_DIR_NAME = "_medical_autofill_history"
JOURNAL_TXT_NAME = "doctor_action_journal.txt"
JOURNAL_JSONL_NAME = "doctor_action_journal.jsonl"


def _journal_data_root() -> Path:
    """Return a technical data folder outside patient result folders."""

    import os

    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base).expanduser() / "MedicalDiaryAutofill"
    return Path.home() / ".medical_diary_autofill"


def _history_dir(output_dir: str | Path) -> Path:
    # ``output_dir`` stays in the signature for compatibility and contextual
    # routing, but technical journals must not be created inside the patient's
    # folder. Doctors expect that folder to contain only patient documents.
    _ = output_dir
    folder = _journal_data_root() / HISTORY_DIR_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe_text(value: object, *, limit: int = 240) -> str:
    return redact_technical_text(value, limit=limit)


def _diagnosis_code_for_journal(value: object) -> str:
    """Keep only the short ICD-10 code in the action journal, not full clinical text."""

    match = re.search(r"(?i)\b([A-ZА-Я]\s?\d{2}(?:\.\d+)?)\b", str(value or ""))
    return match.group(1).replace(" ", "").upper() if match else ""


def _sanitize_details(details: Mapping[str, object] | None) -> dict[str, str]:
    """Remove patient identifiers and full diagnosis prose from action details."""

    result: dict[str, str] = {}
    for key, value in dict(details or {}).items():
        key_text = str(key)
        key_l = key_text.lower().replace("ё", "е")
        if "diagnosis" in key_l or "диагноз" in key_l:
            result[key_text] = _diagnosis_code_for_journal(value) or "код не указан"
        elif any(marker in key_l for marker in ("fio", "пациент", "истори", "case", "date", "дата", "path", "путь")):
            result[key_text] = redact_technical_text(value, limit=120)
        else:
            result[key_text] = _safe_text(value, limit=240)
    return result


def _review_snapshot(review) -> dict[str, str]:
    if review is None:
        return {}
    try:
        patient_ref = technical_ref(review.value("output_fio"), review.value("case_number"), review.value("admission_date"))
    except Exception as exc:
        record_soft_exception("doctor_action_journal.review_ref", exc)
        patient_ref = ""
    result: dict[str, str] = {}
    if patient_ref:
        result["patient_ref"] = patient_ref
    try:
        diagnosis_code = _diagnosis_code_for_journal(review.value("diagnosis"))
        if diagnosis_code:
            result["diagnosis"] = diagnosis_code
            result["diagnosis_code"] = diagnosis_code
    except Exception as exc:
        record_soft_exception("doctor_action_journal.review_diagnosis", exc)
    try:
        result["selected_outputs"] = _safe_text(", ".join(review.selected_outputs), limit=400)
    except Exception as exc:
        record_soft_exception("doctor_action_journal.review_selected_outputs", exc)
    try:
        result["warning_count"] = str(len(getattr(review, "warnings", []) or []))
    except Exception as exc:
        record_soft_exception("doctor_action_journal.review_warning_count", exc)
    return result


def append_doctor_action(
    *,
    output_dir: str | Path,
    action: str,
    details: Mapping[str, object] | None = None,
    review=None,
    created_files: Sequence[str | Path] = (),
    errors: Sequence[str] = (),
    category: str = "workflow",
) -> Path | None:
    """Append one privacy-safe action to TXT and machine-readable JSONL logs."""

    try:
        folder = _history_dir(output_dir)
        now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        payload = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "category": _safe_text(category, limit=80),
            "action": _safe_text(action, limit=160),
            "details": _sanitize_details(details),
            "review": _review_snapshot(review),
            "created_file_count": str(len(list(created_files or ()))),
            "error_count": str(len(list(errors or ()))),
            "errors_redacted": [_safe_text(item, limit=400) for item in errors],
        }
        txt_path = folder / JOURNAL_TXT_NAME
        with txt_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{now}] {payload['action']}\n")
            if payload["review"]:
                review_bits = []
                for label, key in (("ref", "patient_ref"), ("диагноз", "diagnosis"), ("выбрано", "selected_outputs"), ("предупреждений", "warning_count")):
                    if payload["review"].get(key):
                        review_bits.append(f"{label}: {payload['review'][key]}")
                if review_bits:
                    handle.write("  " + "; ".join(review_bits) + "\n")
            if payload["details"]:
                handle.write("  " + "; ".join(f"{k}: {v}" for k, v in payload["details"].items()) + "\n")
            handle.write(f"  создано файлов: {payload['created_file_count']}\n")
            if payload["errors_redacted"]:
                handle.write("  ошибки: " + "; ".join(payload["errors_redacted"]) + "\n")
        jsonl_path = folder / JOURNAL_JSONL_NAME
        with jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return txt_path
    except Exception as exc:
        record_soft_exception("doctor_action_journal.append", exc, detail=str(output_dir))
        return None


def assert_doctor_action_journal_lock() -> None:
    if DOCTOR_ACTION_JOURNAL_LOCK_VERSION != "v1.3":
        raise AssertionError("Doctor action journal lock changed unexpectedly")
    test_dir = _history_dir(Path.home())
    if test_dir.parent == Path.home():
        raise AssertionError("Doctor action journal must not live directly inside patient/output folders")
    if JOURNAL_TXT_NAME != "doctor_action_journal.txt" or JOURNAL_JSONL_NAME != "doctor_action_journal.jsonl":
        raise AssertionError("Doctor action journal file names drifted")
    source = Path(__file__).read_text(encoding="utf-8", errors="replace")
    raw_output_payload = 'result[' + chr(34) + 'output_fio' + chr(34) + ']'
    raw_case_payload = 'result[' + chr(34) + 'case_number' + chr(34) + ']'
    raw_created_payload = chr(34) + 'created_files' + chr(34) + ':'
    if raw_output_payload in source or raw_case_payload in source or raw_created_payload in source:
        raise AssertionError("Doctor action journal must not store raw patient fields or file names")
