"""Template-level auditor for doctor-supplied DOCX files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Sequence

from auditor_models import AuditFinding, AuditReport, AuditSeverity, compute_score
from medical_language_detector import detect_docx_language
from regulatory_template_advisor import advise_template
from universal_template_engine import validate_template

AUDITOR_TEMPLATE_LOCK_VERSION = "v1.0"
TEMPLATE_AUDIT_NEVER_BLOCKS_DOCTOR_DECLINE = True


@lru_cache(maxsize=128)
def _cached_template_signature(path_text: str, mtime_ns: int, size: int) -> tuple:
    path = Path(path_text)
    validation = validate_template(path)
    detected = detect_docx_language(path)
    advice = advise_template(path)
    return validation, detected, advice


def audit_template(path: str | Path, *, required_fields: Sequence[str] = (), explicit_specialty: str = "") -> AuditReport:
    candidate = Path(path).expanduser()
    findings: list[AuditFinding] = []
    if not candidate.exists():
        finding = AuditFinding("TEMPLATE_NOT_FOUND", "Шаблон не найден.", AuditSeverity.ERROR, str(candidate), blocking=True)
        return AuditReport("Аудит шаблона", (finding,), str(candidate), compute_score((finding,)))
    if candidate.suffix.lower() not in {".docx", ".docm"}:
        finding = AuditFinding("TEMPLATE_UNSUPPORTED_FORMAT", "Поддерживаются только DOCX/DOCM-шаблоны.", AuditSeverity.ERROR, str(candidate), blocking=True)
        return AuditReport("Аудит шаблона", (finding,), str(candidate), compute_score((finding,)))
    stat = candidate.stat()
    validation, detected, advice = _cached_template_signature(str(candidate.resolve()), stat.st_mtime_ns, stat.st_size)
    if not validation.placeholders:
        findings.append(AuditFinding("TEMPLATE_HAS_NO_PLACEHOLDERS", "В шаблоне нет placeholders вида {{patient.fio}}; universal-движок не сможет его заполнить.", AuditSeverity.ERROR, candidate.name, blocking=True))
    for field_id in validation.unknown_fields:
        findings.append(AuditFinding("UNKNOWN_PLACEHOLDER", f"Неизвестное поле: {field_id}", AuditSeverity.ERROR, candidate.name, {"field_id": field_id}, blocking=True))
    for field_id in validation.missing_required_placeholders:
        findings.append(AuditFinding("MISSING_REQUIRED_PLACEHOLDER", f"Нет обязательного placeholder: {field_id}", AuditSeverity.ERROR, candidate.name, {"field_id": field_id}, blocking=True))
    for warning in validation.warnings:
        if "нет placeholders" in warning.lower():
            continue
        findings.append(AuditFinding("TEMPLATE_WARNING", warning, AuditSeverity.WARNING, candidate.name))
    if detected.language_id == "auto":
        findings.append(AuditFinding("LANGUAGE_NOT_CONFIDENT", "Язык шаблона не определён уверенно; подпись кнопки лучше проверить вручную.", AuditSeverity.ADVICE, candidate.name, detected.to_dict()))
    else:
        findings.append(AuditFinding("LANGUAGE_DETECTED", f"Язык шаблона: {detected.language_id} ({int(detected.confidence * 100)}%).", AuditSeverity.INFO, candidate.name, detected.to_dict()))
    if advice.role_id != "unknown":
        findings.append(AuditFinding("DOCUMENT_ROLE_DETECTED", f"Похоже, это: {advice.role_label}.", AuditSeverity.INFO, candidate.name, {"role_id": advice.role_id}))
    if advice.suggestions:
        for suggestion in advice.suggestions[:12]:
            findings.append(
                AuditFinding(
                    "OPTIONAL_DOCUMENT_ADDITION",
                    f"Возможно, здесь стоит указать ещё и: {suggestion.label}.",
                    AuditSeverity.ADVICE,
                    candidate.name,
                    {"field_id": suggestion.field_id, "reason": suggestion.reason},
                    blocking=False,
                )
            )
    return AuditReport("Аудит шаблона", tuple(findings), str(candidate), compute_score(findings))


def assert_auditor_template_lock() -> None:
    if AUDITOR_TEMPLATE_LOCK_VERSION != "v1.0":
        raise AssertionError("Auditor template lock changed unexpectedly")
    if not TEMPLATE_AUDIT_NEVER_BLOCKS_DOCTOR_DECLINE:
        raise AssertionError("Template auditor suggestions must never override doctor's decline path")
