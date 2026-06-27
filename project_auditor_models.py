"""Project-auditor data contracts.

This is the auditor for the project itself, not the medical-profile auditor.
It is deterministic, local-only and stdlib-only so it can run inside release
checks before optional QA tools are installed.  The model mirrors the principle
used by ai-code-filter: explicit findings, stable fingerprints and honest
severity, not vague score theatre.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
from typing import Iterable, Mapping, Sequence

PROJECT_AUDITOR_MODELS_LOCK_VERSION = "v1.1"
PROJECT_AUDITOR_FINDINGS_ARE_DETERMINISTIC = True
PROJECT_AUDITOR_IS_NOT_RUNTIME_ENGINE = True
PROJECT_AUDITOR_JSON_HAS_COUNTS_AND_SUMMARY = True


class ProjectSeverity(str, Enum):
    INFO = "info"
    ADVICE = "advice"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ProjectFinding:
    rule_id: str
    title: str
    message: str
    severity: ProjectSeverity
    path: str = ""
    line: int | None = None
    evidence: Mapping[str, object] = field(default_factory=dict)
    blocking: bool = False

    @property
    def fingerprint(self) -> str:
        material = f"{self.rule_id}|{self.path}|{self.line or 0}|{self.title}|{self.message}"
        return hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()[:16]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["severity"] = self.severity.value
        data["evidence"] = dict(self.evidence)
        data["fingerprint"] = self.fingerprint
        return data


@dataclass(frozen=True)
class ProjectAuditReport:
    title: str
    target: str
    findings: tuple[ProjectFinding, ...] = ()
    scanned_files: int = 0
    scanned_python_files: int = 0
    duration_ms: int = 0

    @property
    def errors(self) -> tuple[ProjectFinding, ...]:
        return tuple(item for item in self.findings if item.severity in {ProjectSeverity.ERROR, ProjectSeverity.CRITICAL} or item.blocking)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def score(self) -> int:
        counts = self.grouped_counts()
        penalty = 0
        penalty += counts.get("critical", 0) * 35
        penalty += counts.get("error", 0) * 20
        # Warnings/advice are useful trend signals, but a mature legacy project
        # can have many known warnings while still being releasable.  Cap their
        # effect so the score remains interpretable instead of collapsing to 0.
        penalty += min(35, counts.get("warning", 0) * 2)
        penalty += min(10, counts.get("advice", 0))
        return max(0, min(100, 100 - penalty))

    def grouped_counts(self) -> dict[str, int]:
        counts = {severity.value: 0 for severity in ProjectSeverity}
        for item in self.findings:
            counts[item.severity.value] = counts.get(item.severity.value, 0) + 1
        return counts

    def to_dict(self) -> dict:
        counts = self.grouped_counts()
        return {
            "title": self.title,
            "target": self.target,
            "ok": self.ok,
            "score": self.score,
            "duration_ms": self.duration_ms,
            "scanned_files": self.scanned_files,
            "scanned_python_files": self.scanned_python_files,
            "counts": counts,
            # Backward-compatible alias for older smoke/report consumers.
            "summary": counts,
            "findings": [item.to_dict() for item in self.findings],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    def human_report(self) -> str:
        counts = self.grouped_counts()
        lines = [
            self.title,
            f"Цель: {self.target}",
            f"Статус: {'OK' if self.ok else 'есть ошибки'}",
            f"Оценка: {self.score}/100",
            f"Файлы: всего={self.scanned_files}, python={self.scanned_python_files}, время={self.duration_ms} ms",
            "Находки: "
            f"critical={counts.get('critical', 0)}, error={counts.get('error', 0)}, "
            f"warning={counts.get('warning', 0)}, advice={counts.get('advice', 0)}, info={counts.get('info', 0)}",
        ]
        if not self.findings:
            lines.append("\nСущественных замечаний нет.")
            return "\n".join(lines)
        order = (ProjectSeverity.CRITICAL, ProjectSeverity.ERROR, ProjectSeverity.WARNING, ProjectSeverity.ADVICE, ProjectSeverity.INFO)
        captions = {
            ProjectSeverity.CRITICAL: "Критичные ошибки",
            ProjectSeverity.ERROR: "Ошибки",
            ProjectSeverity.WARNING: "Предупреждения",
            ProjectSeverity.ADVICE: "Рекомендации",
            ProjectSeverity.INFO: "Информация",
        }
        for severity in order:
            group = [item for item in self.findings if item.severity == severity]
            if not group:
                continue
            lines.append("\n" + captions[severity] + ":")
            for item in sorted(group, key=lambda f: (f.path, f.line or 0, f.rule_id)):
                where = f" [{item.path}:{item.line}]" if item.line else (f" [{item.path}]" if item.path else "")
                lines.append(f"• {item.rule_id}{where}: {item.message} #{item.fingerprint}")
        return "\n".join(lines)


def finding(
    rule_id: str,
    title: str,
    message: str,
    severity: ProjectSeverity,
    *,
    path: str = "",
    line: int | None = None,
    evidence: Mapping[str, object] | None = None,
    blocking: bool = False,
) -> ProjectFinding:
    return ProjectFinding(rule_id, title, message, severity, path, line, evidence or {}, blocking)


def merge_findings(chunks: Iterable[Iterable[ProjectFinding]]) -> tuple[ProjectFinding, ...]:
    seen: set[str] = set()
    merged: list[ProjectFinding] = []
    for chunk in chunks:
        for item in chunk:
            key = item.fingerprint
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return tuple(merged)


def assert_project_auditor_models_lock() -> None:
    if PROJECT_AUDITOR_MODELS_LOCK_VERSION != "v1.1":
        raise AssertionError("Project auditor models lock changed unexpectedly")
    if not PROJECT_AUDITOR_FINDINGS_ARE_DETERMINISTIC:
        raise AssertionError("Project auditor findings must stay deterministic")
    if not PROJECT_AUDITOR_IS_NOT_RUNTIME_ENGINE:
        raise AssertionError("Project auditor must not become a runtime engine")
    if not PROJECT_AUDITOR_JSON_HAS_COUNTS_AND_SUMMARY:
        raise AssertionError("Project auditor JSON must keep counts and summary keys")
    sample = finding("X", "Title", "Message", ProjectSeverity.WARNING, path="a.py", line=1)
    if sample.fingerprint != finding("X", "Title", "Message", ProjectSeverity.WARNING, path="a.py", line=1).fingerprint:
        raise AssertionError("Finding fingerprints must be stable")
    report = ProjectAuditReport("t", ".", (sample,))
    data = report.to_dict()
    if data.get("counts") != data.get("summary"):
        raise AssertionError("Project auditor JSON summary/counts drift")
