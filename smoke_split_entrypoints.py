"""smoke_split_entrypoints.py verifies split combined part entrypoint wiring.

The check validates static standalone guards for every split file and executes the deepest dependency bootstrap once in a fresh Python process. This covers the full dependency chain without repeatedly replaying heavy DOCX smoke setup in one CI step.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from smoke_combined_runner import PARTS

ROOT = Path(__file__).resolve().parent
SPLIT_PARTS = (
    "smoke_combined_part02_ui_parser_regressions.py",
    "smoke_combined_part03_medical_parser_manual.py",
    "smoke_combined_part04_medical_generation.py",
    "smoke_combined_part05_diary_basic_templates.py",
    "smoke_combined_part06_diary_columns_settings.py",
)
SPLIT_ENTRYPOINT_DEEPEST_BOOTSTRAP_CHECK = True


def _assert_source_contract(part: str) -> None:
    source = (ROOT / part).read_text(encoding="utf-8", errors="replace")
    assert "build_namespace_before" in source, f"{part} misses standalone dependency loader"
    assert "_SMOKE_COMBINED_RUNNER_ACTIVE" in source, f"{part} misses runner guard"


def _assert_deepest_bootstrap_contract_in_isolated_process() -> None:
    deepest_part = SPLIT_PARTS[-1]
    code = (
        "from smoke_combined_runner import build_namespace_before; "
        f"ns = build_namespace_before({deepest_part!r}); "
        "assert ns.get('OUT') is not None, 'dependency namespace misses OUT'; "
        "assert ns.get('_main_module') is not None, 'dependency namespace misses main module'"
    )
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True, timeout=180)


def main() -> None:
    for part in SPLIT_PARTS:
        print(f"[SPLIT-CHECK] {part}", flush=True)
        _assert_source_contract(part)
    _assert_deepest_bootstrap_contract_in_isolated_process()
    assert all(part in PARTS for part in SPLIT_PARTS)
    assert SPLIT_ENTRYPOINT_DEEPEST_BOOTSTRAP_CHECK is True
    print("SPLIT SMOKE ENTRYPOINTS OK")


if __name__ == "__main__":
    main()
