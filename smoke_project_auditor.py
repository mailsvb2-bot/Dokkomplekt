"""Regression smoke for the project auditor layer."""

from __future__ import annotations

from pathlib import Path
import tempfile
import time

from project_auditor import audit_project, assert_project_auditor_lock
from project_auditor_imports import local_import_graph
from project_auditor_files import build_file_index
from project_auditor_models import ProjectSeverity
from project_auditor_reports import write_json_report, write_text_report


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    assert_project_auditor_lock()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root / "a.py", "import b\n\ndef unsafe(x):\n    return eval(x)\n")
        _write(root / "b.py", "import a\n")
        _write(root / "syntax_bad.py", "def broken(:\n    pass\n")
        _write(root / "god.py", "\n".join(["def f():", "    pass"] + ["# filler" for _ in range(1300)]) + "\n")
        _write(root / "alias_hazards.py", "import subprocess as sp\nfrom pickle import loads as ploads\nfrom yaml import load as yload\n\ndef bad(cmd, blob, text):\n    sp.run(cmd, shell=True)\n    ploads(blob)\n    yload(text)\n")
        _write(root / "missing_diag.py", "def fallback(exc):\n    record_soft_exception('x', exc)\n")
        _write(root / "duplicate_symbol.py", "def duplicate():\n    return 1\ndef duplicate():\n    return 2\n")
        (root / "bad_encoding.py").write_bytes(b"# coding: utf-8\nname='\xff'\n")
        _write(root / "requirements.txt", "python-docx>=1.1\n")
        report = audit_project(root)
        codes = {item.rule_id for item in report.findings}
        assert "PY000" in codes, report.human_report()
        assert "IMP001" in codes, report.human_report()
        assert "PA001" in codes, report.human_report()
        assert "PA005" in codes, report.human_report()
        assert "PA007" in codes, report.human_report()
        assert "PA008" in codes, report.human_report()
        assert "PA010" in codes, report.human_report()
        assert "PA013" in codes, report.human_report()
        assert "PA014" in codes, report.human_report()
        assert "FS006" in codes, report.human_report()
        assert not report.ok
        assert any(item.severity in {ProjectSeverity.ERROR, ProjectSeverity.CRITICAL} for item in report.findings)
        json_path = write_json_report(report, root / "audit" / "report.json")
        text_path = write_text_report(report, root / "audit" / "report.txt")
        assert json_path.exists() and '"findings"' in json_path.read_text(encoding="utf-8")
        assert text_path.exists() and "Аудит проекта" in text_path.read_text(encoding="utf-8")
        graph = local_import_graph(build_file_index(root))
        assert graph["a"] == {"b"} and graph["b"] == {"a"}

    started = time.perf_counter()
    current = audit_project(Path(__file__).resolve().parent)
    elapsed = time.perf_counter() - started
    assert current.ok, current.human_report()
    assert current.scanned_python_files >= 100, current.to_dict()
    # CI/container load can fluctuate by several seconds.  This smoke should
    # fail on architectural regressions, not on a transient CPU slice.  Keep a
    # generous ceiling and rely on release_check timing logs for performance
    # observation rather than blocking a doctor-facing hotfix.
    assert elapsed < 15.0, f"project auditor is unexpectedly slow: {elapsed:.3f}s"
    assert not any("tkinter" in str(item.evidence).lower() and item.path.startswith("project_auditor") for item in current.findings)
    print("PROJECT AUDITOR SMOKE OK")


if __name__ == "__main__":
    main()
