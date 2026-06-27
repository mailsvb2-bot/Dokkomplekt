"""Runtime auditor for a selected PatientCase and document pack."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from auditor_models import AuditFinding, AuditReport, AuditSeverity, compute_score
from regulatory_completion_blocks import completion_inputs_for_missing_fields
from universal_fields import PatientCase
from universal_profiles import DocumentPack
from universal_template_engine import missing_required_fields

AUDITOR_RUNTIME_LOCK_VERSION = "v1.0"
RUNTIME_AUDIT_DOES_NOT_BLOCK_DECLINE = True


def audit_generation_readiness(pack: DocumentPack, case: PatientCase, document_ids: Sequence[str] = (), *, output_dir: str | Path | None = None) -> AuditReport:
    selected = {str(item).strip() for item in document_ids if str(item).strip()}
    known = {doc.id for doc in pack.documents}
    findings: list[AuditFinding] = []
    for unknown in sorted(selected - known):
        findings.append(AuditFinding("UNKNOWN_SELECTED_DOCUMENT", f"Выбран неизвестный документ профиля: {unknown}", AuditSeverity.ERROR, unknown, blocking=True))
    if output_dir is not None:
        out = Path(output_dir).expanduser()
        if out.exists() and out.is_file():
            findings.append(AuditFinding("OUTPUT_DIR_IS_FILE", "Папка результата указывает на файл.", AuditSeverity.ERROR, str(out), blocking=True))
    for document in pack.documents:
        if selected and document.id not in selected:
            continue
        missing = missing_required_fields(case, document)
        if missing:
            inputs = completion_inputs_for_missing_fields(missing, registry=pack.registry(), existing_case=case)
            findings.append(
                AuditFinding(
                    "GENERATION_HAS_MISSING_FIELDS",
                    "Для документа есть незаполненные поля; врач может дополнить документ или создать как есть.",
                    AuditSeverity.WARNING,
                    document.button_label,
                    {"document_id": document.id, "missing_fields": list(missing), "completion_inputs": [item.to_dict() for item in inputs]},
                    blocking=False,
                )
            )
    return AuditReport("Аудит готовности создания", tuple(findings), pack.pack_id, compute_score(findings))


def assert_auditor_runtime_lock() -> None:
    if AUDITOR_RUNTIME_LOCK_VERSION != "v1.0":
        raise AssertionError("Auditor runtime lock changed unexpectedly")
    if not RUNTIME_AUDIT_DOES_NOT_BLOCK_DECLINE:
        raise AssertionError("Runtime auditor must not block doctor decline path")
