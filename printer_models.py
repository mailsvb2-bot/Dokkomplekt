from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PrintResult:
    """Structured print outcome returned to the UI.

    This must stay a real dataclass, not a bare annotated shell: printer_jobs
    instantiates it on every print path, including the safe non-Windows/no-file
    branches.  If this regresses, the doctor sees a technical exception instead
    of a clear printing status.
    """

    printed_files: list[Path]
    errors: list[str]

    @property
    def ok(self) -> bool:
        return bool(self.printed_files) and not self.errors

    @property
    def error_count(self) -> int:
        return len(self.errors)
