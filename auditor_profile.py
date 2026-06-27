"""Medpack/profile auditor.

This module audits the doctor's configurable profile without mutating it.  It
checks identity uniqueness, template availability, template fillability and
soft regulatory suggestions.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from auditor_models import AuditFinding, AuditReport, AuditSeverity, compute_score
from auditor_template import audit_template
from universal_profiles import DocumentPack

AUDITOR_PROFILE_LOCK_VERSION = "v1.0"
PROFILE_AUDIT_IS_READ_ONLY = True


def audit_document_pack(pack: DocumentPack, *, base_dir: str | Path | None = None) -> AuditReport:
    base = Path(base_dir).expanduser() if base_dir else Path.cwd()
    findings: list[AuditFinding] = []
    if not pack.documents:
        findings.append(AuditFinding("PACK_HAS_NO_DOCUMENTS", "В профиле нет документов/кнопок.", AuditSeverity.WARNING, pack.pack_id))
    ids = [doc.id for doc in pack.documents]
    labels = [doc.button_label.strip().lower() for doc in pack.documents if doc.button_label.strip()]
    for doc_id, count in Counter(ids).items():
        if count > 1:
            findings.append(AuditFinding("DUPLICATE_DOCUMENT_ID", f"Повторяется id документа: {doc_id}", AuditSeverity.ERROR, pack.pack_id, {"id": doc_id}, blocking=True))
    for label, count in Counter(labels).items():
        if count > 1:
            findings.append(AuditFinding("DUPLICATE_BUTTON_LABEL", f"Несколько кнопок имеют одинаковую подпись: {label}", AuditSeverity.WARNING, pack.pack_id, {"label": label}))
    for document in pack.documents:
        target = document.button_label or document.id
        if not document.button_label.strip():
            findings.append(AuditFinding("EMPTY_BUTTON_LABEL", "У документа нет подписи кнопки.", AuditSeverity.ERROR, target, blocking=True))
        if not document.template.strip():
            findings.append(AuditFinding("EMPTY_TEMPLATE_PATH", "У документа не указан шаблон.", AuditSeverity.ERROR, target, blocking=True))
            continue
        template_path = _resolve_template(document.template, base)
        if not template_path.exists():
            findings.append(AuditFinding("PROFILE_TEMPLATE_NOT_FOUND", f"Шаблон не найден: {document.template}", AuditSeverity.ERROR, target, {"template": document.template}, blocking=True))
            continue
        template_report = audit_template(template_path, required_fields=document.required_fields, explicit_specialty=pack.specialty)
        for item in template_report.findings:
            # Prefix with document id so a profile-wide report stays readable.
            findings.append(
                AuditFinding(
                    code=item.code,
                    message=item.message,
                    severity=item.severity,
                    target=f"{target} / {Path(template_path).name}",
                    details={**dict(item.details), "document_id": document.id},
                    blocking=item.blocking,
                )
            )
    for rule in pack.extraction_rules:
        if not rule.field_id:
            findings.append(AuditFinding("EMPTY_EXTRACTION_RULE_FIELD", "В правиле извлечения нет field_id.", AuditSeverity.ERROR, pack.pack_id, blocking=True))
        if not rule.strategy:
            findings.append(AuditFinding("EMPTY_EXTRACTION_RULE_STRATEGY", f"У правила {rule.field_id} нет стратегии.", AuditSeverity.WARNING, pack.pack_id))
    return AuditReport("Аудит профиля врача", tuple(findings), pack.pack_id, compute_score(findings))


def _resolve_template(template: str, base: Path) -> Path:
    path = Path(template).expanduser()
    if path.is_absolute():
        return path
    direct = base / path
    if direct.exists():
        return direct
    return base / "templates" / path.name


def assert_auditor_profile_lock() -> None:
    if AUDITOR_PROFILE_LOCK_VERSION != "v1.0":
        raise AssertionError("Auditor profile lock changed unexpectedly")
    if not PROFILE_AUDIT_IS_READ_ONLY:
        raise AssertionError("Profile auditor must stay read-only")
