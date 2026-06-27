"""Public auditor layer for the configurable medical document product.

The layer is a small orchestrator over focused auditors.  It never imports
Tkinter, never mutates profiles/templates, and can be used both from UI and
release gates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from auditor_models import AuditReport, merge_reports
from auditor_profile import audit_document_pack
from auditor_runtime import audit_generation_readiness
from auditor_template import audit_template
from universal_fields import PatientCase
from universal_profiles import DocumentPack

AUDITOR_LAYER_LOCK_VERSION = "v1.0"
AUDITOR_LAYER_HAS_NO_UI_DEPENDENCY = True
AUDITOR_LAYER_IS_NOT_SECOND_ENGINE = True


def audit_profile(pack: DocumentPack, *, base_dir: str | Path | None = None) -> AuditReport:
    return audit_document_pack(pack, base_dir=base_dir)


def audit_profile_and_case(
    pack: DocumentPack,
    case: PatientCase,
    *,
    document_ids: Sequence[str] = (),
    base_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> AuditReport:
    return merge_reports(
        "Аудит профиля и выбранного случая",
        (
            audit_document_pack(pack, base_dir=base_dir),
            audit_generation_readiness(pack, case, document_ids, output_dir=output_dir),
        ),
        target=pack.pack_id,
    )


def audit_one_template(path: str | Path) -> AuditReport:
    return audit_template(path)


def save_audit_report(report: AuditReport, path: str | Path) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report.human_report() + "\n", encoding="utf-8")
    return target


def assert_auditor_layer_lock() -> None:
    if AUDITOR_LAYER_LOCK_VERSION != "v1.0":
        raise AssertionError("Auditor layer lock changed unexpectedly")
    if not AUDITOR_LAYER_HAS_NO_UI_DEPENDENCY:
        raise AssertionError("Auditor layer must stay UI-free")
    if not AUDITOR_LAYER_IS_NOT_SECOND_ENGINE:
        raise AssertionError("Auditor layer must not become a second render/parser engine")
