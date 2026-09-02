from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IntakeProfileChoice:
    kind: str
    label: str
    available: bool
    problem: str = ""


def profile_choices_for_desktop_intake(pack, *, base_dir: str | Path | None = None) -> tuple[IntakeProfileChoice, ...]:
    """Return visible intake choices without making broken templates selectable."""
    from universal_main_documents import custom_documents_for_main_ui

    choices: list[IntakeProfileChoice] = []
    for document in custom_documents_for_main_ui(pack, base_dir=base_dir):
        available = bool(document.available)
        problem = str(document.problem or "").strip()
        if not available and not problem:
            problem = "Word-шаблон документа недоступен."
        choices.append(IntakeProfileChoice(document.kind, document.label, available, problem))
    return tuple(choices)
