"""Soft-advisory policy lock for regulatory/template suggestions.

Critical product rule: regulatory knowledge is a helper, never a weapon.  The
program may say "возможно, здесь стоит указать ещё и...", but it must not block
or shame the doctor when they choose "нет, не буду, делай как есть".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

REGULATORY_SOFT_ADVISORY_LOCK_VERSION = "v1.0"
ADVISORY_IS_NEVER_BLOCKING = True
DECLINE_LABEL = "Нет, не буду, делай как есть"
ACCEPT_LABEL = "Буду дополнять"
SOFT_PROMPT_PREFIX = "Возможно, здесь стоит указать ещё и"


@dataclass(frozen=True)
class AdvisoryDecision:
    accepted: bool
    label: str
    should_block_generation: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


DOCTOR_DECLINED = AdvisoryDecision(False, DECLINE_LABEL, False)
DOCTOR_ACCEPTED = AdvisoryDecision(True, ACCEPT_LABEL, False)


def format_soft_advisory_prompt(items: Sequence[str], *, role_label: str = "документ") -> str:
    unique = [str(item).strip() for item in dict.fromkeys(items) if str(item).strip()]
    if not unique:
        return f"По роли «{role_label}» дополнительных мягких подсказок нет. Можно делать как есть."
    lines = [f"{SOFT_PROMPT_PREFIX} для «{role_label}»:"]
    lines.extend("• " + item for item in unique)
    lines.extend(["", "Будете дополнять?", f"Можно выбрать: «{DECLINE_LABEL}». Программа полностью примет ваш шаблон и продолжит работу."])
    return "\n".join(lines)


def make_completion_blocks(items: Sequence[tuple[str, str]]) -> tuple[str, ...]:
    """Return copy-paste friendly placeholder blocks for a doctor/support user."""

    blocks: list[str] = []
    for label, field_id in items:
        label = str(label or field_id).strip()
        field_id = str(field_id or "").strip()
        if not field_id:
            continue
        blocks.append(f"{label}: {{{{{field_id}}}}}")
    return tuple(dict.fromkeys(blocks))


def assert_soft_advisory_lock() -> None:
    """Release-gate lock: advice must never become a hard blocker."""

    if not ADVISORY_IS_NEVER_BLOCKING:
        raise AssertionError("Regulatory advisory layer must remain non-blocking")
    if DOCTOR_DECLINED.should_block_generation:
        raise AssertionError("Doctor decline path must keep generation allowed")
