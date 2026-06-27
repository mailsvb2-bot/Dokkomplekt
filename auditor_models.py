"""Auditor value objects for profile/template/runtime checks.

The auditor layer is intentionally side-effect-free and UI-free.  It returns
structured findings that the UI may display gently, while release gates can use
it headlessly.  It is not a second document engine: it only observes and
explains readiness, risks and suggestions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Sequence

AUDITOR_MODELS_LOCK_VERSION = "v1.0"
AUDITOR_LAYER_IS_OBSERVATIONAL = True
AUDITOR_FINDINGS_ARE_STRUCTURED = True


class AuditSeverity(str, Enum):
    INFO = "info"
    ADVICE = "advice"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class AuditFinding:
    code: str
    message: str
    severity: AuditSeverity = AuditSeverity.INFO
    target: str = ""
    details: Mapping[str, object] = field(default_factory=dict)
    blocking: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        data["severity"] = self.severity.value
        data["details"] = dict(self.details)
        return data


@dataclass(frozen=True)
class AuditReport:
    title: str
    findings: tuple[AuditFinding, ...] = ()
    target: str = ""
    score: int = 100

    @property
    def errors(self) -> tuple[AuditFinding, ...]:
        return tuple(item for item in self.findings if item.severity == AuditSeverity.ERROR)

    @property
    def warnings(self) -> tuple[AuditFinding, ...]:
        return tuple(item for item in self.findings if item.severity == AuditSeverity.WARNING)

    @property
    def advice(self) -> tuple[AuditFinding, ...]:
        return tuple(item for item in self.findings if item.severity == AuditSeverity.ADVICE)

    @property
    def ok(self) -> bool:
        return not self.errors and not any(item.blocking for item in self.findings)

    def grouped_counts(self) -> dict[str, int]:
        result = {severity.value: 0 for severity in AuditSeverity}
        for item in self.findings:
            result[item.severity.value] = result.get(item.severity.value, 0) + 1
        return result

    def human_report(self) -> str:
        counts = self.grouped_counts()
        lines = [self.title, f"Статус: {'OK' if self.ok else 'есть риски'}", f"Оценка: {self.score}/100"]
        lines.append(
            "Находки: "
            f"ошибки={counts.get('error', 0)}, предупреждения={counts.get('warning', 0)}, "
            f"подсказки={counts.get('advice', 0)}, информация={counts.get('info', 0)}"
        )
        if not self.findings:
            lines.append("\nСущественных замечаний нет.")
            return "\n".join(lines)
        for severity in (AuditSeverity.ERROR, AuditSeverity.WARNING, AuditSeverity.ADVICE, AuditSeverity.INFO):
            group = [item for item in self.findings if item.severity == severity]
            if not group:
                continue
            caption = {
                AuditSeverity.ERROR: "Ошибки",
                AuditSeverity.WARNING: "Предупреждения",
                AuditSeverity.ADVICE: "Рекомендации",
                AuditSeverity.INFO: "Информация",
            }[severity]
            lines.append("\n" + caption + ":")
            for item in group:
                target = f" [{item.target}]" if item.target else ""
                lines.append(f"• {item.code}{target}: {item.message}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "target": self.target,
            "ok": self.ok,
            "score": self.score,
            "counts": self.grouped_counts(),
            "findings": [item.to_dict() for item in self.findings],
        }


def compute_score(findings: Sequence[AuditFinding]) -> int:
    score = 100
    for finding in findings:
        if finding.severity == AuditSeverity.ERROR:
            score -= 25 if finding.blocking else 18
        elif finding.severity == AuditSeverity.WARNING:
            score -= 7
        elif finding.severity == AuditSeverity.ADVICE:
            score -= 2
    return max(0, min(100, score))


def merge_reports(title: str, reports: Iterable[AuditReport], *, target: str = "") -> AuditReport:
    findings: list[AuditFinding] = []
    for report in reports:
        findings.extend(report.findings)
    return AuditReport(title=title, target=target, findings=tuple(findings), score=compute_score(findings))


def assert_auditor_models_lock() -> None:
    if AUDITOR_MODELS_LOCK_VERSION != "v1.0":
        raise AssertionError("Auditor models lock changed unexpectedly")
    if not AUDITOR_LAYER_IS_OBSERVATIONAL:
        raise AssertionError("Auditor layer must stay observational")
    if not AUDITOR_FINDINGS_ARE_STRUCTURED:
        raise AssertionError("Auditor findings must stay structured")
    report = AuditReport("test", (AuditFinding("A", "msg", AuditSeverity.WARNING),))
    if report.ok is not True or report.score != 100:
        # Score is explicit, not auto-mutating; compute_score is used by builders.
        raise AssertionError("AuditReport must stay immutable and explicit")
