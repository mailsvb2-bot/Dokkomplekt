"""Lightweight privacy-safe diagnostics for intentionally non-blocking UI/OS fallbacks.

The helper is deliberately tiny and stdlib-only. It records soft failures without
interrupting the doctor and without copying patient identifiers, raw filesystem
paths or selected document names into technical logs.
"""

from __future__ import annotations

import logging
import re
import traceback
from pathlib import Path
from typing import Any

DIAGNOSTIC_LOGGING_LOCK_VERSION = "v1.2"
SOFT_EXCEPTION_EVENTS_ARE_NON_BLOCKING = True
SOFT_EXCEPTION_TRACEBACK_IS_PRIVACY_SAFE = True
SOFT_EXCEPTION_REDACTS_DETAIL = True

_LOGGER = logging.getLogger("MedicalDiaryAutofill.soft_fail")


def redact_diagnostic_text(value: Any, *, limit: int = 500) -> str:
    """Return a diagnostic string without raw patient/path information.

    Soft-fail diagnostics are support signals, not medical records.  They must
    not persist a doctor's local paths such as ``C:\\Users\\...\\Иванов...docx``,
    dates, case numbers or FIO-like fragments.
    """

    text = " ".join(str(value or "").split())
    if not text:
        return ""
    text = re.sub(r"[A-Za-z]:\\\\[^\s\"']+", "<path>", text)
    text = re.sub(r"[A-Za-z]:\\[^\s\"']+", "<path>", text)
    text = re.sub(r"/(?:home|mnt|Users|tmp|var)/[^\s\"']+", "<path>", text)
    text = re.sub(r"\b\d{1,2}[./-]\d{1,2}[./-](?:\d{2}|\d{4})\b", "<date>", text)
    text = re.sub(r"(?i)(истори[ияи]\s*(?:болезни)?\s*№?\s*)[\w\-/.]+", r"\1<case>", text)
    text = re.sub(r"(?i)(case(?:_number)?\s*[=:]\s*)[\w\-/.]+", r"\1<case>", text)
    text = re.sub(r"\b[А-ЯЁ][а-яё]+_[А-ЯЁ][а-яё]+(?:_[А-ЯЁ][а-яё]+)?\b", "<person>", text)
    # Two-token names like «Иванов Иван» leaked through the old three-token
    # FIO redactor.  Technical diagnostics are not medical documents, so the
    # safer default is to redact two- and three-token Russian proper-name spans.
    text = re.sub(r"\b[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2}\b", "<person>", text)
    text = re.sub(r"[^\s\"']+\.(?:docx|docm|pdf|txt|json|jsonl|csv)\b", "<file>", text, flags=re.IGNORECASE)
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def _safe_traceback(exc: BaseException) -> str:
    """Format only module basenames/line numbers/functions, not raw exception text."""

    frames = []
    try:
        for frame in traceback.extract_tb(exc.__traceback__)[-6:]:
            frames.append(f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}")
    except Exception:
        return ""
    return " > ".join(frames)


def record_soft_exception(context: str, exc: BaseException, *, detail: Any | None = None) -> None:
    """Record an intentionally non-blocking exception at debug level.

    This function must never raise. It is used in UI fallback paths, optional
    printer discovery and settings conveniences where failure should be visible
    to diagnostics but should not interrupt a doctor while working.  It records
    only redacted summaries and privacy-safe traceback coordinates.
    """
    try:
        summary = f"{type(exc).__name__}: {redact_diagnostic_text(exc)}"
        safe_context = redact_diagnostic_text(context, limit=160)
        safe_detail = redact_diagnostic_text(detail, limit=500) if detail is not None else ""
        safe_tb = _safe_traceback(exc)
        if detail is None:
            _LOGGER.debug("soft-fail: %s: %s; tb=%s", safe_context, summary, safe_tb)
        else:
            _LOGGER.debug("soft-fail: %s: %s; detail=%s; tb=%s", safe_context, summary, safe_detail, safe_tb)
    except Exception:
        # Last-resort fallback: diagnostics must not break production flow.
        return


def assert_diagnostic_logging_lock() -> None:
    if DIAGNOSTIC_LOGGING_LOCK_VERSION != "v1.2":
        raise AssertionError("Diagnostic logging lock changed unexpectedly")
    if not SOFT_EXCEPTION_EVENTS_ARE_NON_BLOCKING:
        raise AssertionError("Soft exception diagnostics must remain non-blocking")
    if not SOFT_EXCEPTION_TRACEBACK_IS_PRIVACY_SAFE or not SOFT_EXCEPTION_REDACTS_DETAIL:
        raise AssertionError("Soft exception diagnostics must redact details and avoid raw exc_info tracebacks")
    sample = redact_diagnostic_text(r"C:\Users\Пользователь\Desktop\Выписанные пациенты\Иванов_Иван.docx Иванов Иван 12.05.2026 история болезни №123")
    if "Иванов" in sample or "123" in sample or "C:" in sample or "12.05.2026" in sample:
        raise AssertionError("Diagnostic redaction is unsafe")
