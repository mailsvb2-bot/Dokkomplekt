"""Configurable document-pack model for future universal medical profiles."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from collections.abc import Mapping as MappingABC
from typing import Iterable, Mapping, Sequence

from universal_fields import FieldDefinition, FieldRegistry, default_field_registry, normalize_field_id, normalize_field_id_for_context

PACK_SCHEMA_VERSION = 1
DEFAULT_PACK_ID = "doctor.empty_custom"
DOCTOR_BUTTON_REVIEW_CONTRACT_VERSION = "doctor_review_v3_deep_audit_20260624"
DEFAULT_WORKFLOW_PRINCIPLES = {
    "profile_scope": "specialty_neutral_medical",
    "profile_kind": "doctor",
    "doctor_name": "",
    "department_name": "",
    "department_shared_templates": False,
    "button_title_source": "docx_visible_top_title",
    "required_field_policy": "ask_missing_field_then_allow_continue",
    "custom_required_fields_are_profile_owned": True,
    "block03_buttons_created_by_doctor_review_v2": False,
    "doctor_button_review_contract_version": "",
    "forbidden_phrases_are_removed_from_output": True,
    "source_document_detection": "content_based_primary_or_referral",
    "print_deduplication": True,
}


def _object_sequence(value: object) -> tuple[object, ...]:
    """Return a safe tuple for JSON-loaded list/tuple fields."""

    if isinstance(value, (list, tuple)):
        return tuple(value)
    return ()


def _object_mapping(value: object) -> Mapping[str, object]:
    """Return a safe mapping for JSON-loaded object fields."""

    if isinstance(value, MappingABC):
        return value
    return {}


def _object_dict(value: object) -> dict[str, object]:
    """Return a plain dict for JSON-loaded object fields."""

    return dict(value) if isinstance(value, MappingABC) else {}


def _object_float(value: object, default: float) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _object_int(value: object, default: int) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class ExtractionRule:
    """A saved rule that explains how to read one semantic field from a DOCX."""

    field_id: str
    strategy: str  # label_after / block_between_markers / exact_selection / regex / table_cell
    label: str = ""
    regex: str = ""
    block_hint: str = ""
    selected_text: str = ""
    confidence: float = 0.75
    created_from: str = "auto"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["field_id"] = normalize_field_id(self.field_id)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "ExtractionRule":
        return cls(
            field_id=normalize_field_id(str(data.get("field_id", ""))),
            strategy=str(data.get("strategy", "label_after")).strip() or "label_after",
            label=str(data.get("label", "")).strip(),
            regex=str(data.get("regex", "")).strip(),
            block_hint=str(data.get("block_hint", "")).strip(),
            selected_text=str(data.get("selected_text", "")).strip(),
            confidence=_object_float(data.get("confidence", 0.75), 0.75),
            created_from=str(data.get("created_from", "auto")).strip() or "auto",
        )


@dataclass(frozen=True)
class DocumentTemplateSpec:
    """One dynamic button/document inside a medical pack.

    ``button_label`` is profile-owned data.  For doctor-created regular
    documents it is generated from the detected document role and language, then
    saved into pack.json so the same button appears on the next launch without
    relying on hard-coded UI labels.
    """

    id: str
    button_label: str
    template: str
    output_name: str = "{{patient.fio}} {{document.label}}.docx"
    required_fields: tuple[str, ...] = ()
    optional_fields: tuple[str, ...] = ()
    category: str = "medical"
    description: str = ""
    role_id: str = ""
    button_language: str = "auto"
    source_language: str = "auto"
    button_label_source: str = "manual"
    diary_schedule: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["required_fields"] = list(self.required_fields)
        data["optional_fields"] = list(self.optional_fields)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "DocumentTemplateSpec":
        category = str(data.get("category", "medical")).strip() or "medical"
        role_id = str(data.get("role_id", "")).strip()
        button_label = str(data.get("button_label", "")).strip()
        return cls(
            id=str(data.get("id", "")).strip(),
            button_label=button_label,
            template=str(data.get("template", "")).strip(),
            output_name=str(data.get("output_name", "{{patient.fio}} {{document.label}}.docx")).strip(),
            required_fields=tuple(
                normalize_field_id_for_context(str(item), role_id=role_id, category=category, document_label=button_label)
                for item in _object_sequence(data.get("required_fields", ()))
            ),
            optional_fields=tuple(
                normalize_field_id_for_context(str(item), role_id=role_id, category=category, document_label=button_label)
                for item in _object_sequence(data.get("optional_fields", ()))
            ),
            category=category,
            description=str(data.get("description", "")).strip(),
            role_id=role_id,
            button_language=str(data.get("button_language", "auto")).strip() or "auto",
            source_language=str(data.get("source_language", "auto")).strip() or "auto",
            button_label_source=str(data.get("button_label_source", "manual")).strip() or "manual",
            diary_schedule=_object_dict(data.get("diary_schedule", {})),
        )


@dataclass
class DocumentPack:
    """A configurable product profile for a doctor/specialty/clinic."""

    pack_id: str
    name: str
    specialty: str = ""
    schema_version: int = PACK_SCHEMA_VERSION
    source_document_types: tuple[str, ...] = ("any_medical_source", "primary_exam", "hospitalization_referral", "admission_doctor_exam")
    documents: tuple[DocumentTemplateSpec, ...] = ()
    extraction_rules: tuple[ExtractionRule, ...] = ()
    custom_fields: tuple[FieldDefinition, ...] = ()
    workflow_principles: dict = field(default_factory=lambda: dict(DEFAULT_WORKFLOW_PRINCIPLES))
    notes: str = ""

    def registry(self) -> FieldRegistry:
        return default_field_registry(self.custom_fields)

    def document_labels(self) -> tuple[str, ...]:
        return tuple(doc.button_label for doc in self.documents)

    def required_field_ids(self) -> tuple[str, ...]:
        """All semantic fields needed by at least one document in the pack."""

        return tuple(dict.fromkeys(field_id for document in self.documents for field_id in document.required_fields))

    def document_by_id(self, document_id: str) -> DocumentTemplateSpec | None:
        needle = str(document_id or "").strip()
        for document in self.documents:
            if document.id == needle:
                return document
        return None

    def add_document(self, document: DocumentTemplateSpec) -> None:
        kept = [old for old in self.documents if old.id != document.id]
        self.documents = tuple([*kept, document])

    def rename_document(self, document_id: str, new_button_label: str) -> DocumentTemplateSpec:
        """Rename one doctor-owned block-03 button without changing its id/template.

        The document id is a stable internal handle used by saved selections,
        medpack exports and generation.  A doctor-facing rename must therefore
        update only profile-owned button metadata, while preserving the DOCX
        template, role, required fields and diary schedule.
        """

        renamed = rename_document_button(self, document_id, new_button_label)
        self.documents = tuple(
            renamed if document.id == renamed.id else document
            for document in self.documents
        )
        return renamed

    def remove_document(self, document_id: str) -> DocumentTemplateSpec:
        """Remove one doctor-owned block-03 button from this profile.

        The copied DOCX file is intentionally left on disk.  Deleting a button
        should be reversible by re-adding the template and must not destroy a
        doctor's original work by surprise.
        """

        removed, kept = remove_document_button(self, document_id)
        self.documents = kept
        return removed

    def add_rule(self, rule: ExtractionRule) -> None:
        normalized = rule.to_dict()
        candidate = ExtractionRule.from_dict(normalized)
        kept = [old for old in self.extraction_rules if not (old.field_id == candidate.field_id and old.strategy == candidate.strategy and old.label == candidate.label and old.selected_text == candidate.selected_text)]
        self.extraction_rules = tuple([*kept, candidate])

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "pack_id": self.pack_id,
            "name": self.name,
            "specialty": self.specialty,
            "source_document_types": list(self.source_document_types),
            "documents": [doc.to_dict() for doc in self.documents],
            "extraction_rules": [rule.to_dict() for rule in self.extraction_rules],
            "custom_fields": [definition.to_dict() for definition in self.custom_fields],
            "workflow_principles": dict(self.workflow_principles or DEFAULT_WORKFLOW_PRINCIPLES),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "DocumentPack":
        return cls(
            schema_version=_object_int(data.get("schema_version", PACK_SCHEMA_VERSION), PACK_SCHEMA_VERSION),
            pack_id=str(data.get("pack_id", DEFAULT_PACK_ID)).strip() or DEFAULT_PACK_ID,
            name=str(data.get("name", "Медицинский профиль")).strip() or "Медицинский профиль",
            specialty=str(data.get("specialty", "")).strip(),
            source_document_types=tuple(str(item).strip() for item in (_object_sequence(data.get("source_document_types", ())) or ("any_medical_source", "primary_exam", "hospitalization_referral", "admission_doctor_exam")) if str(item).strip()),
            documents=tuple(DocumentTemplateSpec.from_dict(_object_mapping(item)) for item in _object_sequence(data.get("documents", ()))),
            extraction_rules=tuple(ExtractionRule.from_dict(_object_mapping(item)) for item in _object_sequence(data.get("extraction_rules", ()))),
            custom_fields=tuple(FieldDefinition.from_dict(_object_mapping(item)) for item in _object_sequence(data.get("custom_fields", ()))),
            workflow_principles={**DEFAULT_WORKFLOW_PRINCIPLES, **_object_dict(data.get("workflow_principles", {}))},
            notes=str(data.get("notes", "")).strip(),
        )



def _doctor_document_by_id(pack: DocumentPack, document_id: str) -> DocumentTemplateSpec:
    needle = str(document_id or "").strip()
    if not needle:
        raise ValueError("Не выбрана кнопка документа.")
    for document in pack.documents:
        if document.id == needle:
            return document
    raise KeyError(f"Кнопка документа не найдена: {needle}")


def _clean_button_label(value: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        raise ValueError("Введите понятное название кнопки.")
    if len(text) > 80:
        raise ValueError("Название кнопки слишком длинное. Оставьте до 80 символов.")
    return text


def _unique_renamed_button_label(pack: DocumentPack, document_id: str, new_button_label: str) -> str:
    base = _clean_button_label(new_button_label)
    used = {str(document.button_label or "").casefold() for document in pack.documents if document.id != document_id}
    if base.casefold() not in used:
        return base
    for index in range(2, 1000):
        candidate = f"{base} ({index})"
        if candidate.casefold() not in used:
            return candidate
    raise ValueError(f"Слишком много кнопок с одинаковым названием: {base}")


def rename_document_button(pack: DocumentPack, document_id: str, new_button_label: str) -> DocumentTemplateSpec:
    """Return an updated document spec for a doctor-facing button rename."""

    document = _doctor_document_by_id(pack, document_id)
    from dataclasses import replace

    label = _unique_renamed_button_label(pack, document.id, new_button_label)
    return replace(document, button_label=label, button_label_source="doctor_renamed")


def remove_document_button(pack: DocumentPack, document_id: str) -> tuple[DocumentTemplateSpec, tuple[DocumentTemplateSpec, ...]]:
    """Return removed document and kept list for a doctor-facing button delete."""

    removed = _doctor_document_by_id(pack, document_id)
    kept = tuple(document for document in pack.documents if document.id != removed.id)
    return removed, kept

def current_builtin_documents() -> tuple[DocumentTemplateSpec, ...]:
    """Legacy compatibility hook: no user-facing built-in templates.

    The commercial product starts as an empty doctor-owned constructor.  Every
    doctor/clinic/country adds its own DOCX/DOCM templates; the program reads
    their top titles and creates block-03 buttons from those names.  This
    function remains only so older imports do not crash, but it intentionally
    returns no medical documents.
    """

    return ()


def _strip_builtin_documents(pack: DocumentPack) -> DocumentPack:
    """Remove old seeded/builtin documents from a medpack in-place."""

    builtin_ids = {
        "primary",
        "discharge",
        "commission",
        "vk_mse",
        "admission_doctor_referral",
        "sick_leave_vk",
        "rvk",
        "diaries",
    }
    kept = []
    for doc in pack.documents:
        if doc.id in builtin_ids:
            continue
        if str(getattr(doc, "button_label_source", "")).strip().lower() == "builtin":
            continue
        kept.append(doc)
    pack.documents = tuple(kept)
    if pack.pack_id.startswith("builtin."):
        pack.pack_id = DEFAULT_PACK_ID
    pack.workflow_principles = {**DEFAULT_WORKFLOW_PRINCIPLES, **dict(getattr(pack, "workflow_principles", {}) or {})}
    if "встро" in pack.name.lower() or "текущий комплект" in pack.name.lower():
        pack.name = "Профиль врача"
    if pack.notes and "встро" in pack.notes.lower():
        pack.notes = "Пустой профиль: добавьте свои Word-шаблоны врача."
    return pack


def default_document_pack() -> DocumentPack:
    return DocumentPack(
        pack_id=DEFAULT_PACK_ID,
        name="Профиль врача",
        specialty="generic",
        documents=(),
        extraction_rules=(),
        custom_fields=(),
        workflow_principles=dict(DEFAULT_WORKFLOW_PRINCIPLES),
        notes="Пустой профиль: врач добавляет свои Word-шаблоны всех документов. Нейтральный медицинский режим: подходит врачу любой специальности.",
    )


def load_document_pack(path: str | Path) -> DocumentPack:
    candidate = Path(path).expanduser()
    data = json.loads(candidate.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Файл профиля должен содержать JSON-объект.")
    pack = DocumentPack.from_dict(data)
    if pack.schema_version != PACK_SCHEMA_VERSION:
        raise ValueError(f"Неподдерживаемая версия профиля: {pack.schema_version}")
    return pack


def _backup_existing_document_pack(candidate: Path, *, reason: str = "save") -> Path | None:
    """Create a timestamped profile backup before overwriting a medpack JSON."""
    if not candidate.exists() or not candidate.is_file():
        return None
    from datetime import datetime
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = candidate.parent / "_profile_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    safe_reason = "".join(ch for ch in str(reason or "save") if ch.isalnum() or ch in {"_", "-"})[:32] or "save"
    backup = backup_dir / f"{candidate.stem}_{safe_reason}_{stamp}{candidate.suffix}"
    counter = 2
    while backup.exists():
        backup = backup_dir / f"{candidate.stem}_{safe_reason}_{stamp}_{counter}{candidate.suffix}"
        counter += 1
    backup.write_text(candidate.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return backup


def save_document_pack(pack: DocumentPack, path: str | Path, *, backup_reason: str = "save") -> Path:
    candidate = Path(path).expanduser()
    candidate.parent.mkdir(parents=True, exist_ok=True)
    _backup_existing_document_pack(candidate, reason=backup_reason)
    tmp = candidate.with_name(candidate.name + ".tmp")
    tmp.write_text(json.dumps(pack.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(candidate)
    return candidate


def mark_pack_as_doctor_profile(pack: DocumentPack, *, doctor_name: str = "") -> DocumentPack:
    """Mark a pack as an individual doctor profile without changing documents."""
    principles = {**DEFAULT_WORKFLOW_PRINCIPLES, **dict(pack.workflow_principles or {})}
    principles.update({"profile_kind": "doctor", "doctor_name": str(doctor_name or "").strip(), "department_shared_templates": False})
    pack.workflow_principles = principles
    return pack


def mark_pack_as_department_profile(pack: DocumentPack, *, department_name: str = "") -> DocumentPack:
    """Mark a pack as a shared department profile for several doctors."""
    principles = {**DEFAULT_WORKFLOW_PRINCIPLES, **dict(pack.workflow_principles or {})}
    principles.update({
        "profile_kind": "department",
        "department_name": str(department_name or "").strip(),
        "department_shared_templates": True,
    })
    pack.workflow_principles = principles
    if not pack.name or pack.name == "Профиль врача":
        pack.name = "Профиль отделения"
    return pack


def profile_scope_label(pack: DocumentPack) -> str:
    """Human label for the current profile scope: doctor or department."""
    principles = dict(getattr(pack, "workflow_principles", {}) or {})
    kind = str(principles.get("profile_kind", "doctor") or "doctor").strip().lower()
    if kind == "department":
        name = str(principles.get("department_name", "") or "").strip()
        return "Профиль отделения" + (f": {name}" if name else "")
    name = str(principles.get("doctor_name", "") or "").strip()
    return "Профиль врача" + (f": {name}" if name else "")


def ensure_default_pack(path: str | Path) -> DocumentPack:
    candidate = Path(path).expanduser()
    if candidate.exists():
        pack = _strip_builtin_documents(load_document_pack(candidate))
        # Persist one-time cleanup so old seeded packs do not keep reappearing
        # as if the program shipped ready-made medical templates.
        save_document_pack(pack, candidate)
        return pack
    pack = default_document_pack()
    save_document_pack(pack, candidate)
    return pack
