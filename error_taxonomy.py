"""Error taxonomy for doctor-facing workflows and diagnostics.

The application should not show raw Python failures to a doctor when it can
classify the problem.  This module keeps categories small and stdlib-only so UI,
watcher and domain code can share the same vocabulary without importing Tk.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Any

from diagnostic_logging import record_soft_exception

ERROR_TAXONOMY_LOCK_VERSION = "v1.0"


class ErrorCategory(str, Enum):
    """Stable categories used by UI messages, logs and test contracts."""

    USER_INPUT = "user_input_error"
    TEMPLATE = "template_error"
    PARSER = "parser_error"
    DOCX_RENDER = "docx_render_error"
    WATCHER = "watcher_error"
    PRINTER = "printer_error"
    PROFILE = "profile_error"
    SYSTEM = "system_error"


class ErrorSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class ClassifiedError:
    """One classified error event without patient document contents."""

    category: ErrorCategory
    severity: ErrorSeverity
    context: str
    message: str
    detail: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, str]:
        data = asdict(self)
        data["category"] = self.category.value
        data["severity"] = self.severity.value
        return data


def _normalize_detail(detail: Any | None, *, limit: int = 600) -> str:
    text = " ".join(str(detail or "").split())
    # Keep logs useful, but do not dump full clinical text into JSONL/history.
    return text[:limit]


def classify_error(context: str, exc: BaseException | None = None, *, category: ErrorCategory | str | None = None, severity: ErrorSeverity | str = ErrorSeverity.ERROR, detail: Any | None = None) -> ClassifiedError:
    """Return a deterministic category for a failure context.

    Callers can pass an explicit category; otherwise a conservative keyword map
    is used.  The fallback is ``system_error`` because unknown failures are not
    safe to present as user mistakes.
    """

    if category is not None:
        try:
            chosen = ErrorCategory(str(category))
        except Exception as exc_category:
            record_soft_exception("error_taxonomy.invalid_category", exc_category, detail=str(category))
            chosen = ErrorCategory.SYSTEM
    else:
        needle = f"{context} {type(exc).__name__ if exc else ''} {exc or ''}".casefold()
        if any(word in needle for word in ("printer", "print", "принтер", "печать")):
            chosen = ErrorCategory.PRINTER
        elif any(word in needle for word in ("watcher", "intake_agent", "desktop_intake", "автозапуск", "папк")):
            chosen = ErrorCategory.WATCHER
        elif any(word in needle for word in ("template", "шаблон", "placeholder", "medpack")):
            chosen = ErrorCategory.TEMPLATE
        elif any(word in needle for word in ("profile", "профиль", "pack")):
            chosen = ErrorCategory.PROFILE
        elif any(word in needle for word in ("parse", "parser", "scan", "scanner", "распозн", "docx")):
            chosen = ErrorCategory.PARSER
        elif any(word in needle for word in ("render", "save", "write", "создан", "document")):
            chosen = ErrorCategory.DOCX_RENDER
        elif any(word in needle for word in ("required", "input", "ввод", "поле", "manual")):
            chosen = ErrorCategory.USER_INPUT
        else:
            chosen = ErrorCategory.SYSTEM
    try:
        chosen_severity = ErrorSeverity(str(severity))
    except Exception as exc_severity:
        record_soft_exception("error_taxonomy.severity", exc_severity, detail=str(severity))
        chosen_severity = ErrorSeverity.ERROR
    return ClassifiedError(
        category=chosen,
        severity=chosen_severity,
        context=str(context or "unknown"),
        message=_normalize_detail(exc, limit=220),
        detail=_normalize_detail(detail),
        created_at=datetime.now().isoformat(timespec="seconds"),
    )


def doctor_message(event: ClassifiedError) -> str:
    """Short Russian message that can be safely shown in a messagebox."""

    titles = {
        ErrorCategory.USER_INPUT: "Проверьте введённые данные.",
        ErrorCategory.TEMPLATE: "Проверьте Word-шаблон или профиль кнопок.",
        ErrorCategory.PARSER: "Не удалось надёжно прочитать документ.",
        ErrorCategory.DOCX_RENDER: "Не удалось создать или сохранить DOCX.",
        ErrorCategory.WATCHER: "Фоновое наблюдение за папкой сработало с ошибкой.",
        ErrorCategory.PRINTER: "Документ сохранён, но печать требует проверки.",
        ErrorCategory.PROFILE: "Профиль врача или отделения требует проверки.",
        ErrorCategory.SYSTEM: "Произошла системная ошибка программы.",
    }
    base = titles.get(event.category, titles[ErrorCategory.SYSTEM])
    tail = f"\n\nТехническая причина: {event.message}" if event.message else ""
    return base + tail


def record_classified_error(context: str, exc: BaseException, *, category: ErrorCategory | str | None = None, severity: ErrorSeverity | str = ErrorSeverity.WARNING, detail: Any | None = None) -> ClassifiedError:
    """Classify and record an exception through the existing soft diagnostics."""

    event = classify_error(context, exc, category=category, severity=severity, detail=detail)
    record_soft_exception(f"{event.category.value}:{context}", exc, detail=event.to_dict())
    return event


def assert_error_taxonomy_lock() -> None:
    if ERROR_TAXONOMY_LOCK_VERSION != "v1.0":
        raise AssertionError("Error taxonomy lock changed unexpectedly")
    expected = {
        "user_input_error",
        "template_error",
        "parser_error",
        "docx_render_error",
        "watcher_error",
        "printer_error",
        "profile_error",
        "system_error",
    }
    actual = {item.value for item in ErrorCategory}
    if actual != expected:
        raise AssertionError(f"Error taxonomy categories drifted: {actual}")
