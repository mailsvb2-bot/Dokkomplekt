"""Configurable document-pack model for future universal medical profiles."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from collections.abc import Mapping as MappingABC
from typing import Iterable, Mapping, Sequence

from medical_paths import atomic_write_text, prune_old_files
from universal_fields import FieldDefinition, FieldRegistry, default_field_registry, normalize_field_id, normalize_field_id_for_context

PACK_SCHEMA_VERSION = 1
MAX_MEDPACK_UNCOMPRESSED_BYTES = 100 * 1024 * 1024

PACK_MANIFEST_NAME = "pack.json"
TEMPLATE_DIR_NAME = "templates"
ALLOWED_PACK_SUFFIXES = {".json", ".medpack", ".zip"}
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
    shutil.copy2(candidate, backup)
    prune_old_files(backup_dir, pattern=f"{candidate.stem}_*{candidate.suffix}", keep=32)
    return backup


def save_document_pack(pack: DocumentPack, path: str | Path, *, backup_reason: str = "save") -> Path:
    candidate = Path(path).expanduser()
    candidate.parent.mkdir(parents=True, exist_ok=True)
    _backup_existing_document_pack(candidate, reason=backup_reason)
    atomic_write_text(candidate, json.dumps(pack.to_dict(), ensure_ascii=False, indent=2) + "\n")
    return candidate



def count_managed_profiles(directory: str | Path) -> int:
    """Count real user profiles; ignore the untouched bootstrap constructor."""
    root = Path(directory).expanduser()
    if not root.exists() or not root.is_dir():
        return 0
    candidates = {item for item in root.glob("*.json") if item.is_file()}
    count = 0
    for candidate in candidates:
        try:
            pack = load_document_pack(candidate)
            if candidate.name == "default_custom.medpack.json" and not pack.documents:
                continue
        except Exception:
            # Corrupt manifests still consume a profile slot until the doctor
            # removes/repairs them; fail closed instead of creating unlimited files.
            pass
        count += 1
    return count

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
        pack = load_document_pack(candidate)
        before_cleanup = pack.to_dict()
        pack = _strip_builtin_documents(pack)
        # Persist only an actual one-time migration.  Merely opening/refreshing
        # an already-clean profile must not rewrite it or create backup churn.
        if pack.to_dict() != before_cleanup:
            save_document_pack(pack, candidate, backup_reason="strip_legacy_builtin_documents")
        return pack
    pack = default_document_pack()
    save_document_pack(pack, candidate)
    return pack


def resolve_pack_template_path(template_value: str, base_dir: str | Path | None) -> Path:
    template = Path(template_value).expanduser()
    if template.is_absolute():
        return template
    if base_dir:
        base = Path(base_dir).expanduser()
        direct = base / template
        if direct.exists():
            return direct
        in_templates = base / TEMPLATE_DIR_NAME / template.name
        if in_templates.exists():
            return in_templates
        return direct
    return template


def available_template_copy_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Не удалось сохранить копию шаблона: {path}")


def _available_profile_manifest_path(path: Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.exists():
        return candidate
    stem = candidate.name[:-len(".medpack.json")] if candidate.name.endswith(".medpack.json") else candidate.stem
    suffix = ".medpack.json" if candidate.name.endswith(".medpack.json") else candidate.suffix
    for index in range(2, 1000):
        next_candidate = candidate.with_name(f"{stem} ({index}){suffix}")
        if not next_candidate.exists():
            return next_candidate
    raise FileExistsError(f"Не удалось сохранить импортированный профиль: {candidate}")


def _assert_safe_zip_name(name: str) -> None:
    path = PurePosixPath(name)
    normalized = str(name or "")
    first_part = path.parts[0] if path.parts else ""
    if (
        path.is_absolute()
        or ".." in path.parts
        or normalized.startswith(("/", "\\"))
        or "\\" in normalized
        or "\x00" in normalized
        or ":" in first_part
    ):
        raise ValueError(f"Небезопасный путь внутри medpack: {name}")


def _validate_word_package(source: Path, label: str) -> None:
    try:
        with zipfile.ZipFile(source, "r") as probe:
            names = set(probe.namelist())
            required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
            absent = sorted(required - names)
            bad_member = probe.testzip()
            if absent:
                raise ValueError("нет обязательных частей Word: " + ", ".join(absent))
            if bad_member:
                raise ValueError(f"ошибка CRC в {bad_member}")
    except Exception as exc:
        raise ValueError(f"{label}: шаблон повреждён ({exc})") from exc


def _copy_json_profile_templates(pack: DocumentPack, source_base: Path, target_base: Path, created_out: list[Path]) -> DocumentPack:
    updated: list[DocumentTemplateSpec] = []
    templates_dir = target_base / TEMPLATE_DIR_NAME
    templates_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for document in pack.documents:
            source = resolve_pack_template_path(document.template, source_base)
            if not source.exists() or not source.is_file() or source.suffix.lower() not in {".docx", ".docm"}:
                raise ValueError(f"Профиль повреждён: не найден шаблон для «{document.button_label or document.id}»: {document.template}")
            _validate_word_package(source, document.button_label or document.id)
            target = available_template_copy_path(templates_dir / source.name)
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
                created.append(target); created_out.append(target)
            updated.append(replace(document, template=(PurePosixPath(TEMPLATE_DIR_NAME) / target.name).as_posix()))
        pack.documents = tuple(updated)
        return pack
    except Exception:
        for item in reversed(created):
            with suppress(OSError):
                item.unlink()
        raise


def _copy_zip_profile_templates(pack: DocumentPack, zf: zipfile.ZipFile, names: set[str], target_base: Path, created_out: list[Path]) -> DocumentPack:
    updated: list[DocumentTemplateSpec] = []
    templates_dir = target_base / TEMPLATE_DIR_NAME
    templates_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for document in pack.documents:
            template_value = str(document.template or "").replace("\\", "/").strip()
            candidates = [template_value]
            if template_value:
                candidates.append((PurePosixPath(TEMPLATE_DIR_NAME) / PurePosixPath(template_value).name).as_posix())
            archive_name = next((item for item in candidates if item in names and PurePosixPath(item).suffix.lower() in {".docx", ".docm"}), "")
            if not archive_name:
                raise ValueError(f"medpack повреждён: нет шаблона для «{document.button_label or document.id}»: {document.template}")
            target = available_template_copy_path(templates_dir / PurePosixPath(archive_name).name)
            with zf.open(archive_name, "r") as source_file, target.open("wb") as target_file:
                shutil.copyfileobj(source_file, target_file)
            created.append(target); created_out.append(target)
            _validate_word_package(target, document.button_label or document.id)
            updated.append(replace(document, template=(PurePosixPath(TEMPLATE_DIR_NAME) / target.name).as_posix()))
        pack.documents = tuple(updated)
        return pack
    except Exception:
        for item in reversed(created):
            with suppress(OSError):
                item.unlink()
        raise


def export_document_pack_zip(pack: DocumentPack, target_zip: str | Path, *, template_base_dir: str | Path | None = None) -> Path:
    target = Path(target_zip).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    base = Path(template_base_dir).expanduser() if template_base_dir else None
    planned: list[tuple[DocumentTemplateSpec, Path, str]] = []
    missing: list[str] = []
    for document in pack.documents:
        source = resolve_pack_template_path(document.template, base)
        if not source.exists() or not source.is_file() or source.suffix.lower() not in {".docx", ".docm"}:
            missing.append(f"{document.button_label or document.id}: {document.template or 'template не указан'}")
            continue
        try:
            _validate_word_package(source, document.button_label or document.id)
        except ValueError as exc:
            missing.append(str(exc)); continue
        planned.append((document, source, (PurePosixPath(TEMPLATE_DIR_NAME) / source.name).as_posix()))
    if missing:
        raise ValueError("Профиль нельзя экспортировать: не все Word-шаблоны доступны. " + "; ".join(missing[:10]))

    used: dict[str, tuple[str, str]] = {}
    collision_safe: list[tuple[DocumentTemplateSpec, Path, str]] = []
    for document, source, base_arcname in planned:
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        identity = (str(source.resolve()), digest)
        arcname = base_arcname
        if arcname in used and used[arcname] != identity:
            stem, suffix = source.stem, source.suffix
            arcname = (PurePosixPath(TEMPLATE_DIR_NAME) / f"{stem}_{digest[:12]}{suffix}").as_posix()
            index = 2
            while arcname in used and used[arcname] != identity:
                arcname = (PurePosixPath(TEMPLATE_DIR_NAME) / f"{stem}_{digest[:12]}_{index}{suffix}").as_posix(); index += 1
        used[arcname] = identity
        collision_safe.append((document, source, arcname))

    manifest = pack.to_dict()
    portable_documents: list[dict] = []
    fd, raw_temp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)); os.close(fd)
    temp_target = Path(raw_temp)
    try:
        with zipfile.ZipFile(temp_target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            written: set[str] = set()
            for document, source, arcname in collision_safe:
                doc_data = document.to_dict()
                if arcname not in written:
                    zf.write(source, arcname); written.add(arcname)
                doc_data["template"] = arcname; portable_documents.append(doc_data)
            manifest["documents"] = portable_documents
            zf.writestr(PACK_MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        os.replace(temp_target, target)
        return target
    except Exception:
        with suppress(OSError):
            temp_target.unlink()
        raise


def inspect_document_pack_source(source_path: str | Path) -> DocumentPack:
    source = Path(source_path).expanduser()
    if source.suffix.lower() not in ALLOWED_PACK_SUFFIXES:
        raise ValueError(f"Неподдерживаемый формат профиля: {source.suffix}")
    if source.suffix.lower() == ".json" or source.name.endswith(".medpack.json"):
        return load_document_pack(source)
    with zipfile.ZipFile(source, "r") as zf:
        infos = zf.infolist()
        for info in infos:
            _assert_safe_zip_name(str(getattr(info, "orig_filename", info.filename))); _assert_safe_zip_name(info.filename)
        names = [info.filename for info in infos]
        if PACK_MANIFEST_NAME not in names:
            raise ValueError("В medpack-архиве нет pack.json.")
        if len(infos) > 250:
            raise ValueError("Слишком много файлов внутри medpack-архива.")
        if sum(max(0, info.file_size) for info in infos) > MAX_MEDPACK_UNCOMPRESSED_BYTES:
            raise ValueError("medpack-архив слишком большой для безопасного импорта.")
        data = json.loads(zf.read(PACK_MANIFEST_NAME).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("pack.json внутри medpack должен содержать JSON-объект.")
        pack = DocumentPack.from_dict(data)
        if pack.schema_version != PACK_SCHEMA_VERSION:
            raise ValueError(f"Неподдерживаемая версия профиля: {pack.schema_version}")
        return pack


def import_document_pack_zip(source_zip: str | Path, target_dir: str | Path, *, validate_pack) -> tuple[DocumentPack, Path]:
    source = Path(source_zip).expanduser()
    if source.suffix.lower() not in ALLOWED_PACK_SUFFIXES:
        raise ValueError(f"Неподдерживаемый формат профиля: {source.suffix}")
    target = Path(target_dir).expanduser(); target.mkdir(parents=True, exist_ok=True)
    created_templates: list[Path] = []; pack_path: Path | None = None
    try:
        if source.suffix.lower() == ".json" or source.name.endswith(".medpack.json"):
            pack = load_document_pack(source)
            pack = _copy_json_profile_templates(pack, source.parent, target, created_templates)
            pack_path = _available_profile_manifest_path(target / source.name)
        else:
            with zipfile.ZipFile(source, "r") as zf:
                infos = zf.infolist()
                for info in infos:
                    _assert_safe_zip_name(str(getattr(info, "orig_filename", info.filename))); _assert_safe_zip_name(info.filename)
                names = [info.filename for info in infos]
                if PACK_MANIFEST_NAME not in names:
                    raise ValueError("В medpack-архиве нет pack.json.")
                if len(infos) > 250:
                    raise ValueError("Слишком много файлов внутри medpack-архива.")
                if sum(max(0, info.file_size) for info in infos) > MAX_MEDPACK_UNCOMPRESSED_BYTES:
                    raise ValueError("medpack-архив слишком большой для безопасного импорта.")
                data = json.loads(zf.read(PACK_MANIFEST_NAME).decode("utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("pack.json внутри medpack должен содержать JSON-объект.")
                pack = DocumentPack.from_dict(data)
                pack = _copy_zip_profile_templates(pack, zf, set(names), target, created_templates)
            pack_path = _available_profile_manifest_path(target / PACK_MANIFEST_NAME)
        validation = validate_pack(pack, base_dir=target)
        if not validation.ok:
            raise ValueError("Импортированный профиль повреждён:\n" + validation.human_report())
        save_document_pack(pack, pack_path)
        return pack, pack_path
    except Exception:
        if pack_path is not None:
            with suppress(OSError):
                pack_path.unlink()
        for item in reversed(created_templates):
            with suppress(OSError):
                item.unlink()
        templates_dir = target / TEMPLATE_DIR_NAME
        if templates_dir.exists() and not any(templates_dir.iterdir()):
            with suppress(OSError):
                templates_dir.rmdir()
        raise
