"""Universal semantic field registry for configurable medical document packs.

This module is the first product layer above the current legacy fixed-document
workflow.  It does not replace the existing ``PatientData`` parser yet; instead
it defines a stable vocabulary of meanings that future source scanners,
per-specialty profiles and dynamic buttons can share.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from collections.abc import Iterable as IterableABC, Mapping as MappingABC
from typing import Iterable, Mapping, Sequence

from regulatory_caucasus_aliases import field_aliases_for

_FIELD_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")

_FIELD_ID_ALIASES = {
    "fio": "patient.fio",
    "ф.и.о": "patient.fio",
    "ф.и.о.": "patient.fio",
    "фио": "patient.fio",
    "фамилия.имя.отчество": "patient.fio",
    "фамилия_имя_отчество": "patient.fio",
    "пациент": "patient.fio",
    "больной": "patient.fio",
    "больная": "patient.fio",
    "full.name": "patient.fio",
    "full_name": "patient.fio",
    "patient.name": "patient.fio",
    "patient_name": "patient.fio",
    "patient.fio": "patient.fio",
    "patient_fio": "patient.fio",
    "fio.patient": "patient.fio",
    "fio_patient": "patient.fio",
    "patient.full_name": "patient.fio",
    "patient_full_name": "patient.fio",
    "surname.name.patronymic": "patient.fio",
    "surname_name_patronymic": "patient.fio",
    "birth": "patient.birth_date",
    "birth_date": "patient.birth_date",
    "birthdate": "patient.birth_date",
    "dob": "patient.birth_date",
    "date.birth": "patient.birth_date",
    "date_birth": "patient.birth_date",
    "birth.date": "patient.birth_date",
    "дата.рождения": "patient.birth_date",
    "дата_рождения": "patient.birth_date",
    "год.рождения": "patient.birth_date",
    "год_рождения": "patient.birth_date",
    "patient_birth_date": "patient.birth_date",
    "address": "patient.address",
    "registration.address": "patient.address",
    "registration_address": "patient.address",
    "registered.address": "patient.address",
    "registered_address": "patient.address",
    "residence.address": "patient.address",
    "residence_address": "patient.address",
    "адрес": "patient.address",
    "адрес.регистрации": "patient.address",
    "адрес_регистрации": "patient.address",
    "место.жительства": "patient.address",
    "место_жительства": "patient.address",
    "registered": "patient.address",
    "patient_registered": "patient.address",
    "case": "case.number",
    "case_number": "case.number",
    "case.no": "case.number",
    "case_no": "case.number",
    "case.number": "case.number",
    "case.nr": "case.number",
    "case_nr": "case.number",
    "case.n": "case.number",
    "case_n": "case.number",
    "case.num": "case.number",
    "case.nr": "case.number",
    "case.n": "case.number",
    "case.id": "case.number",
    "case_id": "case.number",
    "history.number": "case.number",
    "history_number": "case.number",
    "history.no": "case.number",
    "history_no": "case.number",
    "history.nr": "case.number",
    "history_nr": "case.number",
    "history.n": "case.number",
    "history_n": "case.number",
    "history.case": "case.number",
    "medical.record.number": "case.number",
    "medical_record_number": "case.number",
    "medical.record.no": "case.number",
    "medical_record_no": "case.number",
    "medical.record.nr": "case.number",
    "medical_record_nr": "case.number",
    "medical.card.number": "case.number",
    "medical_card_number": "case.number",
    "medical.card.no": "case.number",
    "medical_card_no": "case.number",
    "record.number": "case.number",
    "record_number": "case.number",
    "record.no": "case.number",
    "record_no": "case.number",
    "record.nr": "case.number",
    "record_nr": "case.number",
    "record.n": "case.number",
    "record_n": "case.number",
    "ib.number": "case.number",
    "ib_number": "case.number",
    "patient.case_number": "case.number",
    "patient.case.number": "case.number",
    "patient.history_number": "case.number",
    "patient.history.number": "case.number",
    "patient.record_number": "case.number",
    "patient.record.number": "case.number",
    "номер.истории.болезни": "case.number",
    "номер_истории_болезни": "case.number",
    "история.болезни": "case.number",
    "история_болезни": "case.number",
    "истории.болезни": "case.number",
    "истории_болезни": "case.number",
    "иб": "case.number",
    "иб.номер": "case.number",
    "иб_номер": "case.number",
    "номер.медицинской.карты": "case.number",
    "номер_медицинской_карты": "case.number",
    "медицинская.карта": "case.number",
    "медицинская_карта": "case.number",
    "admission": "admission.date",
    "admission_date": "admission.date",
    "admission.dt": "admission.date",
    "admission_dt": "admission.date",
    "date.admission": "admission.date",
    "date.of.admission": "admission.date",
    "date_of_admission": "admission.date",
    "admission.day": "admission.date",
    "admission_day": "admission.date",
    "дата.поступления": "admission.date",
    "дата_поступления": "admission.date",
    "дата.госпитализации": "admission.date",
    "дата_госпитализации": "admission.date",
    "поступил": "admission.date",
    "поступила": "admission.date",
    "госпитализирован": "admission.date",
    "госпитализирована": "admission.date",
    "admitted.at": "admission.date",
    "admitted_at": "admission.date",
    "hospital.admission_date": "admission.date",
    "hospital_admission_date": "admission.date",
    "hospitalization.date": "admission.date",
    "hospitalization_date": "admission.date",
    "hospitalisation.date": "admission.date",
    "hospitalisation_date": "admission.date",
    "discharge": "discharge.date",
    "discharge_date": "discharge.date",
    "discharge.dt": "discharge.date",
    "discharge_dt": "discharge.date",
    "date.discharge": "discharge.date",
    "date.of.discharge": "discharge.date",
    "date_of_discharge": "discharge.date",
    "discharge.day": "discharge.date",
    "discharge_day": "discharge.date",
    "дата.выписки": "discharge.date",
    "дата_выписки": "discharge.date",
    "выписан": "discharge.date",
    "выписана": "discharge.date",
    "выписывается": "discharge.date",
    "discharged.at": "discharge.date",
    "discharged_at": "discharge.date",
    "hospital.discharge_date": "discharge.date",
    "hospital_discharge_date": "discharge.date",
    "condition.discharge_date": "discharge.date",
    "condition.discharge.date": "discharge.date",
    "diagnosis": "diagnosis.main",
    "diagnosis.text": "diagnosis.main",
    "diagnosis_text": "diagnosis.main",
    "diagnosis.main_text": "diagnosis.main",
    "main.diagnosis": "diagnosis.main",
    "main_diagnosis": "diagnosis.main",
    "primary.diagnosis": "diagnosis.main",
    "primary_diagnosis": "diagnosis.main",
    "clinical.diagnosis": "diagnosis.main",
    "clinical_diagnosis": "diagnosis.main",
    "patient.diagnosis": "diagnosis.main",
    "patient_diagnosis": "diagnosis.main",
    "диагноз": "diagnosis.main",
    "клинический.диагноз": "diagnosis.main",
    "клинический_диагноз": "diagnosis.main",
    "основной.диагноз": "diagnosis.main",
    "основной_диагноз": "diagnosis.main",
    "diagnosis_code": "diagnosis.icd10",
    "diagnosis.code": "diagnosis.icd10",
    "diagnosis.icd_code": "diagnosis.icd10",
    "diagnosis_icd_code": "diagnosis.icd10",
    "icd": "diagnosis.icd10",
    "icd10": "diagnosis.icd10",
    "icd.code": "diagnosis.icd10",
    "icd_code": "diagnosis.icd10",
    "icd10.code": "diagnosis.icd10",
    "icd10_code": "diagnosis.icd10",
    "icd_10": "diagnosis.icd10",
    "icd_10_code": "diagnosis.icd10",
    "mkb": "diagnosis.icd10",
    "mkb10": "diagnosis.icd10",
    "mkb.code": "diagnosis.icd10",
    "mkb_code": "diagnosis.icd10",
    "mkb10.code": "diagnosis.icd10",
    "mkb10_code": "diagnosis.icd10",
    "mkb_10": "diagnosis.icd10",
    "mkb_10_code": "diagnosis.icd10",
    "мкб": "diagnosis.icd10",
    "мкб10": "diagnosis.icd10",
    "код.мкб": "diagnosis.icd10",
    "код_мкб": "diagnosis.icd10",
    "код.мкб10": "diagnosis.icd10",
    "код_мкб10": "diagnosis.icd10",
    "код_мкб_10": "diagnosis.icd10",
    "шифр.мкб": "diagnosis.icd10",
    "шифр_мкб": "diagnosis.icd10",
    "шифр_мкб_10": "diagnosis.icd10",
    "treatment": "treatment.plan",
    "treatment_plan": "treatment.plan",
    "treatment.summary": "treatment.plan",
    "treatment.assigned": "treatment.plan",
    "assigned.treatment": "treatment.plan",
    "assigned_treatment": "treatment.plan",
    "prescribed.treatment": "treatment.plan",
    "prescribed_treatment": "treatment.plan",
    "therapy": "treatment.plan",
    "therapy.plan": "treatment.plan",
    "therapy_plan": "treatment.plan",
    "лечение": "treatment.plan",
    "назначенное.лечение": "treatment.plan",
    "назначенное_лечение": "treatment.plan",
    "план.лечения": "treatment.plan",
    "план_лечения": "treatment.plan",
    "назначения": "treatment.plan",
    "treatment_result": "treatment.result",
    "labs.block": "labs.results",
    "labs_block": "labs.results",
    "lab.block": "labs.results",
    "lab_block": "labs.results",
    "lab.results": "labs.results",
    "lab_results": "labs.results",
    "laboratory.analysis": "labs.results",
    "laboratory_analysis": "labs.results",
    "analysis.results": "labs.results",
    "analysis_results": "labs.results",
    "analysis_block": "labs.results",
    "analyses": "labs.results",
    "analyses.results": "labs.results",
    "analyses_results": "labs.results",
    "analyses_block": "labs.results",
    "laboratory.results": "labs.results",
    "laboratory.block": "labs.results",
    "laboratory_results": "labs.results",
    "laboratory_block": "labs.results",
    "instrumental_results": "instrumental.results",
    "instrumental.block": "instrumental.results",
    "instrumental_block": "instrumental.results",
    "analysis": "labs.results",
    "анализы": "labs.results",
    "результаты.анализов": "labs.results",
    "результаты_анализов": "labs.results",
    "лабораторные.исследования": "labs.results",
    "лабораторные_исследования": "labs.results",
    "лабораторные.анализы": "labs.results",
    "лабораторные_анализы": "labs.results",
    "analysis.date": "labs.date",
    "analysis_date": "labs.date",
    "lab.date": "labs.date",
    "lab_date": "labs.date",
    "laboratory.date": "labs.date",
    "laboratory_date": "labs.date",
    "labs_date": "labs.date",
    "work": "patient.work",
    "work.place": "patient.work",
    "work_place": "patient.work",
    "job.place": "patient.work",
    "job_place": "patient.work",
    "место.работы": "patient.work",
    "место_работы": "patient.work",
    "position": "patient.position",
    "job.title": "patient.position",
    "job_title": "patient.position",
    "должность": "patient.position",
    "профессия": "patient.position",
    "expert_work_status": "expert.work_status",
    "expert_work_org": "expert.work_org",
    "expert_position": "expert.position",
    "expert_sick_leave_needed": "expert.sick_leave_needed",
    "expert_sick_leave_from": "expert.sick_leave_from",
    "expert_sick_leave_number": "expert.sick_leave_number",
    "sick_leave_number": "expert.sick_leave_number",
    "sick_leave_no": "expert.sick_leave_number",
    "sick_leave_nr": "expert.sick_leave_number",
    "sick_leave_from": "expert.sick_leave_from",
    "sick_leave_start": "expert.sick_leave_from",
    "sick_leave_needed": "expert.sick_leave_needed",
    "sick_leave_required": "expert.sick_leave_needed",
    "требуется_больничный": "expert.sick_leave_needed",
    "нужен_больничный": "expert.sick_leave_needed",
    "нужен_лн": "expert.sick_leave_needed",
    "номер_больничного": "expert.sick_leave_number",
    "номер_лн": "expert.sick_leave_number",
    "с_какого_числа_больничный": "expert.sick_leave_from",
    "больничный_с": "expert.sick_leave_from",
    "commission_date": "commission.date",
    "commission_number": "commission.number",
    "committee.date": "commission.date",
    "committee.number": "commission.number",
    "дата_совместного_осмотра": "commission.date",
    "дата_проведения_совместного_осмотра": "commission.date",
    "номер_совместного_осмотра": "commission.number",
    "rvk_act_number": "rvk.act_number",
    "rvk_military_commissariat": "rvk.military_commissariat",
    "rvk_work_position": "rvk.work_position",
    "номер_акта_рвк": "rvk.act_number",
    "акт_рвк": "rvk.act_number",
    "акт_рвк_n": "rvk.act_number",
    "акт_рвк_no": "rvk.act_number",
    "номер_медицинского_заключения_рвк": "rvk.act_number",
    "медицинское_заключение_рвк": "rvk.act_number",
    "военный_комиссариат": "rvk.military_commissariat",
    "военкомат": "rvk.military_commissariat",
    "место_работы_и_должность_рвк": "rvk.work_position",
    "работа_и_должность_рвк": "rvk.work_position",
    "vk_date": "vk_mse.date",
    "vk_mse_date": "vk_mse.date",
    "vk_protocol_number": "vk_mse.protocol_number",
    "vk_protocol_date": "vk_mse.protocol_date",
    "номер_протокола_вк": "vk_mse.protocol_number",
    "протокол_вк": "vk_mse.protocol_number",
    "протокол_номер_вк": "vk_mse.protocol_number",
    "vk_mse_protocol_number": "vk_mse.protocol_number",
    "vk_mse_protocol_date": "vk_mse.protocol_date",
    "vk_mse_work_org": "vk_mse.work",
    "vk_mse_position": "vk_mse.position",
    "vk_mse_work_position": "vk_mse.work_position",
    "место_работы_и_должность_вк_мсэ": "vk_mse.work_position",
    "место_работы_должность_вк_мсэ": "vk_mse.work_position",
    "sick_leave_vk_date": "sick_leave_vk.date",
    "sick_leave_vk_protocol_number": "sick_leave_vk.protocol_number",
    "sick_leave_vk_protocol_date": "sick_leave_vk.protocol_date",
    "sick_leave_vk_commission_date": "sick_leave_vk.commission_date",
    "sick_leave_vk_work_org": "sick_leave_vk.work",
    "sick_leave_vk_position": "sick_leave_vk.position",
    "sick_leave_vk_work_position": "sick_leave_vk.work_position",
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


@dataclass(frozen=True)
class FieldDefinition:
    """A reusable meaning that can be extracted from source docs or rendered.

    ``id`` is intentionally semantic, not visual.  For example, a surgeon and a
    therapist may have different labels in DOCX, but both can map to
    ``diagnosis.main``.  Unknown specialty-specific values should live under
    ``custom.*`` instead of forcing a new core field into the application.
    """

    id: str
    label: str
    group: str
    aliases: tuple[str, ...] = ()
    value_kind: str = "text"  # text/date/person/number/block/signature/identifier
    description: str = ""
    required_by_default: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        data["aliases"] = list(self.aliases)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "FieldDefinition":
        return cls(
            id=str(data.get("id", "")).strip(),
            label=str(data.get("label", "")).strip(),
            group=str(data.get("group", "custom")).strip() or "custom",
            aliases=tuple(str(item).strip() for item in _object_sequence(data.get("aliases", ())) if str(item).strip()),
            value_kind=str(data.get("value_kind", "text")).strip() or "text",
            description=str(data.get("description", "")).strip(),
            required_by_default=bool(data.get("required_by_default", False)),
        )


class FieldRegistry:
    """Lookup table for semantic fields and their human labels/aliases."""

    def __init__(self, definitions: Iterable[FieldDefinition]):
        normalized: dict[str, FieldDefinition] = {}
        for definition in definitions:
            field_id = normalize_field_id(definition.id)
            if field_id in normalized:
                raise ValueError(f"Дублируется поле реестра: {field_id}")
            normalized[field_id] = FieldDefinition(
                id=field_id,
                label=definition.label or field_id,
                group=definition.group or "custom",
                aliases=tuple(alias for alias in definition.aliases if alias.strip()),
                value_kind=definition.value_kind or "text",
                description=definition.description,
                required_by_default=definition.required_by_default,
            )
        self._definitions = normalized

    def __contains__(self, field_id: str) -> bool:
        return normalize_field_id(field_id) in self._definitions

    def get(self, field_id: str) -> FieldDefinition | None:
        return self._definitions.get(normalize_field_id(field_id))

    def require(self, field_id: str) -> FieldDefinition:
        normalized = normalize_field_id(field_id)
        definition = self.get(normalized)
        if definition is None:
            if normalized.startswith("custom."):
                return FieldDefinition(id=normalized, label=custom_label_from_id(normalized), group="custom", aliases=(), value_kind="text")
            raise KeyError(f"Неизвестное поле: {field_id}")
        return definition

    def definitions(self) -> tuple[FieldDefinition, ...]:
        return tuple(self._definitions.values())

    def ids(self) -> tuple[str, ...]:
        return tuple(self._definitions)

    def choices(self) -> tuple[str, ...]:
        return tuple(f"{definition.id} — {definition.label}" for definition in self.definitions())

    def aliases_for(self, field_id: str) -> tuple[str, ...]:
        definition = self.require(field_id)
        base = (definition.label,) if definition.label else ()
        return tuple(dict.fromkeys([*base, *definition.aliases]))

    def to_dict(self) -> dict:
        return {"fields": [definition.to_dict() for definition in self.definitions()]}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "FieldRegistry":
        return cls(FieldDefinition.from_dict(_object_mapping(item)) for item in _object_sequence(data.get("fields", ())))


@dataclass(frozen=True)
class FieldValue:
    """A confirmed value for a specific patient case."""

    field_id: str
    value: str
    confidence: float = 1.0
    source_document: str = ""
    source_hint: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PatientCase:
    """Generic patient/document case used by universal packs.

    The old application keeps using ``PatientData``.  ``PatientCase`` is the
    new neutral container that can represent therapy, surgery, specialty-specific profiles and
    specialty-specific custom fields without changing code for every doctor.
    """

    values: dict[str, FieldValue] = field(default_factory=dict)

    def set(self, field_id: str, value: str, *, confidence: float = 1.0, source_document: str = "", source_hint: str = "") -> None:
        normalized = normalize_field_id(field_id)
        text = str(value or "").strip()
        if not text:
            return
        self.values[normalized] = FieldValue(normalized, text, max(0.0, min(1.0, float(confidence))), source_document, source_hint)

    def get(self, field_id: str, default: str = "") -> str:
        value = self.values.get(normalize_field_id(field_id))
        return value.value if value else default

    def update_from_pairs(self, pairs: Mapping[str, str], *, confidence: float = 1.0, source_document: str = "") -> None:
        for field_id, value in pairs.items():
            self.set(field_id, value, confidence=confidence, source_document=source_document)

    def to_dict(self) -> dict:
        return {"values": {field_id: value.to_dict() for field_id, value in sorted(self.values.items())}}


def _normalize_field_identifier_text(value: str) -> str:
    """Normalize doctor/profile field ids without losing semantic aliases.

    User-owned DOCX packs are often produced by humans or export tools, so the
    same meaning may arrive as ``admissionDate``, ``admission_date``,
    ``admission-date`` or ``admission/date``.  The registry keeps one canonical
    vocabulary, but accepts common identifier spelling variants before lookup.
    Cyrillic labels are intentionally not forced through this function; labels
    are handled by the higher-level semantic signature matchers.
    """

    text = str(value or "").strip()
    # Split common camelCase/PascalCase ids before lowercasing.
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    text = text.lower().replace("ё", "е")
    # Human DOCX placeholders often include visual numbering marks.  Remove
    # them before strict id validation so {{История болезни №}} and
    # {{case #}} resolve to the same semantic aliases instead of becoming
    # malformed custom fields.
    text = re.sub(r"[№#]+", " ", text)
    text = re.sub(r"[()\[\]{}\"'«»;,]+", " ", text)
    text = re.sub(r"[\s\-]+", "_", text)
    text = re.sub(r"[\/\\:]+", ".", text)
    text = re.sub(r"_+", "_", text)
    text = re.sub(r"\.+", ".", text)
    return text.strip("._")


_ALIAS_LOOKUP_CACHE: dict[str, str] | None = None
_CONTEXT_ONLY_ALIAS_GROUPS = {"commission", "rvk", "vk_mse", "sick_leave_vk"}


def _definition_alias_lookup(normalized: str) -> str:
    """Resolve normalized field ids through the registry's own labels/aliases.

    The same meaning may arrive from a doctor-owned DOCX as a canonical id
    (``labs.date``), an export id (``labsDate``/``labs_date``), or a human
    placeholder (``{{Дата анализов}}``).  Keeping that knowledge only in
    ``DEFAULT_FIELD_DEFINITIONS`` and separately hand-copying it into
    ``_FIELD_ID_ALIASES`` creates regression drift.  This lazy lookup makes
    the registry itself the source of truth while refusing ambiguous labels
    such as ``Номер`` or ``От``.
    """

    global _ALIAS_LOOKUP_CACHE
    if _ALIAS_LOOKUP_CACHE is not None:
        return _ALIAS_LOOKUP_CACHE.get(normalized, "")

    definitions = globals().get("DEFAULT_FIELD_DEFINITIONS")
    if not definitions:
        return ""

    candidates: dict[str, list[str]] = {}

    def add(raw: object, field_id: str) -> None:
        token = _normalize_field_identifier_text(str(raw or ""))
        if not token:
            return
        candidates.setdefault(token, []).append(field_id)

    for definition in definitions:
        field_id = str(getattr(definition, "id", "") or "").strip()
        if not field_id:
            continue
        # Canonical field ids and common export spellings are semantic, not
        # visual labels.  ``expert.sick_leave_number`` must therefore also
        # accept ``expertSickLeaveNumber`` / ``expert_sick_leave_number``.
        add(field_id, field_id)
        add(field_id.replace(".", "_"), field_id)
        add(field_id.replace(".", ""), field_id)
        add(field_id.replace(".", "/"), field_id)
        # Human labels from role-specific documents are context-sensitive.
        # Example: ``Место работы / должность`` inside an RVK template is not
        # the same field as the same phrase inside a sick-leave VK template.
        # Canonical/export ids remain accepted globally; visual labels for these
        # groups must go through ``normalize_field_id_for_context``.
        group = str(getattr(definition, "group", "") or "").strip()
        if group not in _CONTEXT_ONLY_ALIAS_GROUPS:
            add(getattr(definition, "label", ""), field_id)
            for alias in getattr(definition, "aliases", ()) or ():
                add(alias, field_id)

    resolved: dict[str, str] = {}
    for token, ids in candidates.items():
        unique = tuple(dict.fromkeys(ids))
        # Short one-letter aliases (for example ``F`` for ICD) and ambiguous
        # human labels are intentionally excluded from the automatic layer.
        # Explicit entries in _FIELD_ID_ALIASES may still allow safe exceptions.
        if len(unique) == 1 and len(token) >= 2:
            resolved[token] = unique[0]
    _ALIAS_LOOKUP_CACHE = resolved
    return resolved.get(normalized, "")



def _normalize_context_role_token(value: object) -> str:
    """Normalize document role/category labels without importing UI modules.

    Universal field normalization lives below profile/document layers, so it
    cannot import ``universal_main_documents``.  This local role tokenizer keeps
    context-aware placeholder resolution dependency-free and deterministic.
    """

    text = str(value or "").strip()
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[№#]+", " ", text)
    text = re.sub(r"[()\[\]{}\"'«»;,]+", " ", text)
    text = re.sub(r"[\s\-]+", "_", text)
    text = re.sub(r"[\/\\:]+", ".", text)
    text = re.sub(r"_+", "_", text)
    text = re.sub(r"\.+", ".", text)
    return text.strip("._")


_CONTEXT_ROLE_ALIASES = {
    "commission": "commission",
    "medical_commission": "commission",
    "medical.commission": "commission",
    "joint_medical_exam": "commission",
    "joint.medical.exam": "commission",
    "sovmestnyy_osmotr": "commission",
    "совместный_осмотр": "commission",
    "врачебная_комиссия": "commission",
    "vk_mse": "vk_mse",
    "vk.mse": "vk_mse",
    "mse_referral": "vk_mse",
    "mse.referral": "vk_mse",
    "вк_на_мсэ": "vk_mse",
    "мсэ": "vk_mse",
    "sick_leave_vk": "sick_leave_vk",
    "sick.leave.vk": "sick_leave_vk",
    "temporary_disability_commission": "sick_leave_vk",
    "temporary.disability.commission": "sick_leave_vk",
    "вк_больничный": "sick_leave_vk",
    "больничный_вк": "sick_leave_vk",
    "rvk": "rvk",
    "rvk_act": "rvk",
    "rvk.act": "rvk",
    "military_commissariat_act": "rvk",
    "military.commissariat.act": "rvk",
    "акт_рвк": "rvk",
    "акт_для_рвк": "rvk",
    "primary_exam": "patient",
    "primary.exam": "patient",
    "admission_doctor_exam": "patient",
    "admission.doctor.exam": "patient",
    "hospitalization_referral": "patient",
    "hospitalization.referral": "patient",
    "discharge_epicrisis": "patient",
    "discharge.epicrisis": "patient",
}

_WORK_TOKENS = {
    "work", "work_place", "work.place", "workplace", "job_place", "job.place",
    "organization", "organisation", "work_org", "work.org", "org",
    "место_работы", "место.работы", "где_работает", "где.работает",
    "организация", "работает", "работает_в_организации", "работает.в.организации",
}
_POSITION_TOKENS = {"position", "job_title", "job.title", "title", "должность", "профессия"}
_PROTOCOL_NUMBER_TOKENS = {
    "protocol_number", "protocol.number", "protocol_no", "protocol.no", "protocol_nr", "protocol.nr",
    "protocol_num", "protocol.num", "protocol_n", "protocol.n",
    "номер_протокола", "номер.протокола", "номер_протокола_вк", "номер.протокола.вк",
    "протокол_номер", "протокол.номер", "протокол", "протокол_no", "протокол.no",
    "протокол_nr", "протокол.nr", "протокол_num", "протокол.num",
    "протокол_n", "протокол.n", "номер", "number", "num", "no", "nr",
}
_PROTOCOL_DATE_TOKENS = {
    "protocol_date", "protocol.date", "date_protocol", "date.protocol",
    "дата_протокола", "дата.протокола", "от_дата_протокола", "от.дата.протокола",
    "от_протокола", "от.протокола", "дата_от_протокола", "дата.от.протокола", "от",
}
_VK_DATE_TOKENS = {
    "vk_date", "vk.date", "date_vk", "date.vk", "дата_вк", "дата.вк",
    "дата_проведения_вк", "дата.проведения.вк",
    # In real doctor-owned templates this is often written simply as
    # "Дата комиссии" inside a VK/MSE document.  The word is ambiguous
    # globally, but document role makes it safe and prevents registry drift.
    "дата_комиссии", "дата.комиссии", "дата_проведения_комиссии", "дата.проведения.комиссии",
    "дата_комиссии_мсэ", "дата.комиссии.мсэ",
}
_COMMISSION_DATE_TOKENS = {
    "commission_date", "commission.date", "committee_date", "committee.date",
    "дата_комиссии", "дата.комиссии", "дата_проведения_комиссии", "дата.проведения.комиссии",
}
_COMMISSION_NUMBER_TOKENS = {
    "number", "num", "no", "nr", "номер", "commission_number", "commission.number",
    "committee_number", "committee.number", "номер_комиссии", "номер.комиссии",
    "номер_совместного_осмотра", "номер.совместного.осмотра",
}
_RVK_ACT_NUMBER_TOKENS = {
    "act_number", "act.number", "rvk_act_number", "rvk.act_number", "rvk.act.number",
    "номер_акта_рвк", "номер.акта.рвк", "акт_рвк", "акт.рвк",
    "номер_медицинского_заключения", "номер.медицинского.заключения",
}
_RVK_ORG_TOKENS = {
    "military_commissariat", "military.commissariat", "commissariat",
    "военкомат", "военный_комиссариат", "военный.комиссариат", "организация_направления",
}
_RVK_WORK_POSITION_TOKENS = {
    "work_position", "work.position", "job_position", "job.position",
    "работа_и_должность", "работа.и.должность", "место_работы_и_должность", "место.работы.и.должность",
    "место_работы_должность", "место.работы.должность", "место_работы_._должность",
}
_CONTEXTUAL_FIELD_ALIASES: dict[str, dict[str, str]] = {
    "commission": {
        **{token: "commission.date" for token in _COMMISSION_DATE_TOKENS},
        **{token: "commission.number" for token in _COMMISSION_NUMBER_TOKENS},
    },
    "vk_mse": {
        **{token: "vk_mse.work" for token in _WORK_TOKENS},
        **{token: "vk_mse.position" for token in _POSITION_TOKENS},
        **{token: "vk_mse.work_position" for token in _RVK_WORK_POSITION_TOKENS},
        **{token: "vk_mse.protocol_number" for token in _PROTOCOL_NUMBER_TOKENS},
        **{token: "vk_mse.protocol_date" for token in _PROTOCOL_DATE_TOKENS},
        **{token: "vk_mse.date" for token in _VK_DATE_TOKENS},
    },
    "sick_leave_vk": {
        **{token: "sick_leave_vk.work" for token in _WORK_TOKENS},
        **{token: "sick_leave_vk.position" for token in _POSITION_TOKENS},
        **{token: "sick_leave_vk.work_position" for token in _RVK_WORK_POSITION_TOKENS},
        **{token: "sick_leave_vk.protocol_number" for token in _PROTOCOL_NUMBER_TOKENS},
        **{token: "sick_leave_vk.protocol_date" for token in _PROTOCOL_DATE_TOKENS},
        **{token: "sick_leave_vk.date" for token in _VK_DATE_TOKENS},
        **{token: "sick_leave_vk.commission_date" for token in _COMMISSION_DATE_TOKENS},
    },
    "rvk": {
        **{token: "rvk.act_number" for token in _RVK_ACT_NUMBER_TOKENS},
        **{token: "rvk.military_commissariat" for token in _RVK_ORG_TOKENS},
        **{token: "rvk.work_position" for token in _RVK_WORK_POSITION_TOKENS},
    },
}


def _context_key(*, role_id: object = "", category: object = "", document_label: object = "") -> str:
    tokens = [_normalize_context_role_token(role_id), _normalize_context_role_token(category), _normalize_context_role_token(document_label)]
    for token in tokens:
        mapped = _CONTEXT_ROLE_ALIASES.get(token)
        if mapped:
            return mapped
    joined = " ".join(token.replace("_", " ").replace(".", " ") for token in tokens if token)
    if any(marker in joined for marker in ("вк на мсэ", "мсэ", "mse")):
        return "vk_mse"
    if ("больнич" in joined or "нетрудоспособ" in joined or "sick leave" in joined) and ("вк" in joined or "комисс" in joined or "protocol" in joined):
        return "sick_leave_vk"
    if any(marker in joined for marker in ("рвк", "военком", "military commissariat")):
        return "rvk"
    if any(marker in joined for marker in ("совместный осмотр", "врачебная комиссия", "комиссион", "commission")):
        return "commission"
    return ""


def normalize_field_id_for_context(
    value: str,
    *,
    role_id: object = "",
    category: object = "",
    document_label: object = "",
    button_label: object = "",
) -> str:
    """Normalize a field id using document-role context when a label is ambiguous.

    Human DOCX templates frequently use short labels such as ``Место работы``,
    ``Должность`` or ``Номер протокола``.  Globally those labels are ambiguous:
    they may mean the patient's base job, a VK-on-MSE requisition, a sick-leave
    commission field or a joint-commission number.  This resolver keeps
    ``normalize_field_id()`` backward-compatible for existing templates, while
    role-aware profile flows can route the same human placeholder to the exact
    field required by the selected doctor-owned document.
    """

    normalized = _normalize_field_identifier_text(value)
    context = _context_key(role_id=role_id, category=category, document_label=document_label or button_label)
    mapped = _CONTEXTUAL_FIELD_ALIASES.get(context, {}).get(normalized) if context else ""
    if mapped:
        return mapped
    return normalize_field_id(value)

def normalize_field_id(value: str) -> str:
    normalized = _normalize_field_identifier_text(value)
    if not normalized:
        raise ValueError("Пустой идентификатор поля")
    if normalized.startswith("custom_"):
        normalized = "custom." + normalized.removeprefix("custom_")
    # Known human/Russian aliases are allowed before the strict ASCII id check.
    # Unknown Cyrillic labels still fail below, so malformed placeholders do not
    # silently become unfillable fields.
    alias = _FIELD_ID_ALIASES.get(normalized)
    if alias:
        return alias
    registry_alias = _definition_alias_lookup(normalized)
    if registry_alias:
        return registry_alias
    if not _FIELD_ID_RE.match(normalized):
        raise ValueError(f"Некорректный идентификатор поля: {value!r}")
    if normalized.startswith("custom."):
        return normalized
    return normalized


def custom_label_from_id(field_id: str) -> str:
    normalized = normalize_field_id(field_id)
    tail = normalized.split(".", 1)[1] if "." in normalized else normalized
    return tail.replace("_", " ").strip().capitalize() or "Пользовательское поле"


def _fd(
    field_id: str,
    label: str,
    group: str,
    aliases: Sequence[str],
    value_kind: str = "text",
    description: str = "",
    required: bool = False,
) -> FieldDefinition:
    merged_aliases = tuple(dict.fromkeys([*aliases, *field_aliases_for(field_id)]))
    return FieldDefinition(field_id, label, group, merged_aliases, value_kind, description, required)


DEFAULT_FIELD_DEFINITIONS: tuple[FieldDefinition, ...] = (
    _fd("document.title", "Название документа", "document", ("Первичный осмотр", "Направление на госпитализацию", "Выписной эпикриз")),
    _fd("patient.fio", "ФИО пациента", "patient", ("Ф.И.О.", "ФИО", "Пациент", "Больной", "Фамилия Имя Отчество"), "person", required=True),
    _fd("patient.birth_date", "Дата рождения", "patient", ("Дата рождения", "Год рождения", "г.р.", "Возраст"), "date"),
    _fd("patient.age", "Возраст", "patient", ("Возраст", "полных лет", "лет"), "number"),
    _fd("patient.sex", "Пол пациента", "patient", ("Пол", "мужской", "женский")),
    _fd("patient.address", "Адрес пациента", "patient", ("Зарегистрирован", "Проживает", "Адрес", "Место жительства", "Адрес регистрации")),
    _fd("patient.snils", "СНИЛС", "patient", ("СНИЛС", "Страховой номер"), "identifier"),
    _fd("patient.passport", "Паспорт", "patient", ("Паспорт", "серия", "номер паспорта", "выдан"), "identifier"),
    _fd("patient.work", "Место работы", "patient", ("Работает", "Место работы", "Работает в организации", "Организация")),
    _fd("patient.position", "Должность", "patient", ("Должность", "профессия")),
    _fd("case.number", "Номер истории болезни", "case", ("История болезни №", "История болезни N", "ИБ №", "№ истории болезни"), "identifier", required=True),
    _fd("case.department", "Отделение", "case", ("Отделение", "поступает в", "госпитализируется в")),
    _fd("admission.date", "Дата госпитализации", "admission", ("Дата госпитализации", "Дата поступления", "Поступил", "Поступила", "Госпитализирован", "Госпитализирована"), "date", required=True),
    _fd("discharge.date", "Дата выписки", "discharge", ("Дата выписки", "Выписан", "Выписана"), "date"),
    _fd("expert.work_status", "Работает", "expert", ("Работает", "Трудоустроен", "Экспертный анамнез: работает"), "text"),
    _fd("expert.work_org", "Организация работы", "expert", ("Где работает", "Место работы", "Организация"), "text"),
    _fd("expert.position", "Должность", "expert", ("Должность", "Профессия"), "text"),
    _fd("expert.sick_leave_needed", "Нужен больничный лист", "expert", ("Нужен больничный", "Нужен ЛН", "Лист нетрудоспособности"), "text"),
    _fd("expert.sick_leave_from", "Дата начала больничного", "expert", ("С какого числа больничный", "Дата начала ЛН", "Больничный с"), "date"),
    _fd("expert.sick_leave_number", "Номер больничного листа", "expert", ("Номер больничного", "Номер ЛН"), "identifier"),
    _fd("commission.date", "Дата совместного осмотра", "commission", ("Дата совместного осмотра", "Дата проведения комиссии", "Дата комиссии"), "date"),
    _fd("commission.number", "Номер совместного осмотра", "commission", ("Номер совместного осмотра", "Номер комиссии", "Номер"), "identifier"),
    _fd("rvk.act_number", "Номер медицинского заключения РВК", "rvk", ("Номер медицинского заключения", "Номер Акта РВК", "Акт РВК №"), "identifier"),
    _fd("rvk.military_commissariat", "Военкомат / организация направления", "rvk", ("Военкомат", "Военный комиссариат", "Организация направления"), "text"),
    _fd("rvk.work_position", "Работа/должность для РВК", "rvk", ("Работа и должность", "Место работы и должность"), "text"),
    _fd("vk_mse.date", "Дата ВК на МСЭ", "vk_mse", ("Дата ВК на МСЭ", "Дата проведения ВК", "Дата комиссии МСЭ"), "date"),
    _fd("vk_mse.protocol_number", "Номер протокола ВК на МСЭ", "vk_mse", ("Протокол номер", "Номер протокола ВК", "Протокол №"), "identifier"),
    _fd("vk_mse.protocol_date", "Дата протокола ВК на МСЭ", "vk_mse", ("От", "Дата протокола", "От / дата протокола"), "date"),
    _fd("vk_mse.work", "Место работы для ВК на МСЭ", "vk_mse", ("Место работы", "Где работает"), "text"),
    _fd("vk_mse.position", "Должность для ВК на МСЭ", "vk_mse", ("Должность",), "text"),
    _fd("vk_mse.work_position", "Место работы и должность для ВК на МСЭ", "vk_mse", ("Работа и должность", "Место работы / должность"), "text"),
    _fd("sick_leave_vk.date", "Дата ВК больничного", "sick_leave_vk", ("Дата ВК больничного", "Дата проведения ВК"), "date"),
    _fd("sick_leave_vk.protocol_number", "Номер протокола ВК больничного", "sick_leave_vk", ("Номер протокола", "Протокол номер", "Протокол №"), "identifier"),
    _fd("sick_leave_vk.protocol_date", "Дата протокола ВК больничного", "sick_leave_vk", ("Дата протокола", "От / дата протокола", "От"), "date"),
    _fd("sick_leave_vk.commission_date", "Дата комиссии ВК больничного", "sick_leave_vk", ("Дата проведения комиссии", "Дата комиссии"), "date"),
    _fd("sick_leave_vk.work", "Место работы для ВК больничного", "sick_leave_vk", ("Место работы", "Где работает"), "text"),
    _fd("sick_leave_vk.position", "Должность для ВК больничного", "sick_leave_vk", ("Должность",), "text"),
    _fd("sick_leave_vk.work_position", "Место работы и должность для ВК больничного", "sick_leave_vk", ("Работа и должность", "Место работы / должность"), "text"),
    _fd("complaints", "Жалобы", "clinical", ("Жалобы", "Жалобы на момент осмотра", "Жалобы при поступлении"), "block"),
    _fd("anamnesis.life", "Анамнез жизни", "clinical", ("Анамнез жизни",)),
    _fd("anamnesis.disease", "Анамнез заболевания", "clinical", ("Анамнез заболевания", "Анамнез болезни"), "block"),
    _fd("anamnesis.expert", "Экспертный анамнез", "clinical", ("Экспертный анамнез", "Больничный лист", "Лист нетрудоспособности"), "block"),
    _fd("status.objective", "Объективный статус", "clinical", ("Объективный статус", "Status praesens", "Объективно"), "block"),
    _fd("status.mental", "Профильный статус", "clinical", ("Профильный статус", "Специальный статус", "Статус при поступлении"), "block"),
    _fd("status.somatic", "Соматический статус", "clinical", ("Соматический статус", "Сомато-неврологический статус"), "block"),
    _fd("status.neurological", "Неврологический статус", "clinical", ("Неврологический статус", "Невростатус"), "block"),
    _fd("diagnosis.main", "Диагноз", "clinical", ("Диагноз", "Клинический диагноз", "На основании данных"), "block", required=True),
    _fd("diagnosis.icd10", "Код МКБ-10", "clinical", ("МКБ", "МКБ-10", "F", "Код диагноза"), "identifier"),
    _fd("treatment.plan", "Лечение / план лечения", "clinical", ("Лечение", "План лечения", "Назначенное лечение", "Терапия"), "block"),
    _fd("treatment.result", "Результат лечения", "clinical", ("За время лечения", "Состояние при выписке", "Динамика"), "block"),
    _fd("labs.results", "Анализы", "labs", ("Анализы", "Результаты анализов", "Лабораторные исследования", "Результаты обследований", "LABS", "LABS_BLOCK"), "block"),
    _fd("labs.date", "Дата анализов", "labs", ("Дата анализов", "Дата лабораторных исследований", "Дата забора", "Дата исследования"), "date"),
    _fd("labs.source", "Источник анализов", "labs", ("Файл анализов", "Источник анализов"), "text"),
    _fd("labs.date_policy", "Правило дат анализов", "labs", ("Пусть даты подставит программа", "Без анализов", "Дата документа"), "text"),
    _fd("labs.types", "Виды анализов", "labs", ("ОАК", "ОАМ", "БАК", "ЭКГ", "ЭЭГ", "КТ", "МРТ"), "block"),
    _fd("procedure.name", "Операция / процедура", "procedure", ("Операция", "Оперативное вмешательство", "Манипуляция", "Процедура"), "block"),
    _fd("procedure.date", "Дата операции / процедуры", "procedure", ("Дата операции", "Дата оперативного вмешательства", "Оперирован", "Оперирована"), "date"),
    _fd("procedure.anesthesia", "Вид анестезии", "procedure", ("Анестезия", "Вид анестезии", "Обезболивание"), "text"),
    _fd("procedure.complications", "Осложнения", "procedure", ("Осложнения", "Интраоперационные осложнения", "Послеоперационные осложнения"), "block"),
    _fd("postoperative.status", "Послеоперационный статус", "procedure", ("Послеоперационный статус", "После операции", "Послеоперационный период"), "block"),
    _fd("vitals.blood_pressure", "Артериальное давление", "vitals", ("АД", "Артериальное давление", "Давление"), "text"),
    _fd("vitals.pulse", "Пульс", "vitals", ("Пульс", "ЧСС"), "number"),
    _fd("vitals.temperature", "Температура", "vitals", ("Температура", "T тела", "t тела"), "number"),
    _fd("consent.informed", "Информированное согласие", "consent", ("Информированное согласие", "Согласие на операцию", "Согласие на вмешательство"), "block"),
    _fd("condition.discharge", "Состояние при выписке", "discharge", ("Состояние при выписке", "Выписывается", "На момент выписки"), "block"),
    _fd("instrumental.results", "Инструментальные исследования", "labs", ("Инструментальные исследования", "УЗИ", "ЭКГ", "КТ", "МРТ", "Рентген", "Эндоскопия"), "block"),
    _fd("consultation.reason", "Цель консультации", "consultation", ("Цель консультации", "Повод консультации", "Причина консультации"), "block"),
    _fd("consultant.specialty", "Специальность консультанта", "consultation", ("Специальность консультанта", "Консультант", "Врач-консультант"), "text"),
    _fd("consultant.signature", "Подпись консультанта", "signatures", ("Подпись консультанта", "Консультант __________"), "signature"),
    _fd("procedure.description", "Ход операции / описание процедуры", "procedure", ("Ход операции", "Описание процедуры", "Оперативное вмешательство выполнено"), "block"),
    _fd("anesthesia.type", "Тип анестезии", "procedure", ("Тип анестезии", "Вид анестезии", "Анестезия"), "text"),
    _fd("surgeon.signature", "Подпись хирурга", "signatures", ("Хирург", "Оперировал", "Подпись хирурга"), "signature"),
    _fd("assistant.signature", "Подпись ассистента", "signatures", ("Ассистент", "Подпись ассистента"), "signature"),
    _fd("commission.decision", "Решение комиссии", "commission", ("Решение комиссии", "Заключение комиссии", "Постановили"), "block"),
    _fd("mse.referral_reason", "Основание направления на МСЭ", "commission", ("Основание направления на МСЭ", "Причина направления на МСЭ", "Инвалидность"), "block"),
    _fd("diary.schedule", "Принцип дневников", "diary", ("Принцип дневников", "График дневников"), "block"),
    _fd("diary.dates", "Даты дневников", "diary", ("Даты дневников", "График дат"), "block"),
    _fd("diary.entries", "Дневниковые записи", "diary", ("Дневниковые записи", "Дневники"), "block"),
    _fd("diary.frequency", "Частота дневников", "diary", ("Ежедневно", "Ежечасно"), "text"),
    _fd("recommendations", "Рекомендации", "discharge", ("Рекомендовано", "Рекомендации", "Даны рекомендации"), "block"),
    _fd("doctor.name", "Врач", "signatures", ("Врач", "Лечащий врач", "Хирург", "Терапевт"), "signature"),
    _fd("doctor.signature", "Подпись врача", "signatures", ("Подпись врача", "Врач __________", "Врач:"), "signature"),
    _fd("head.name", "Заведующий отделением", "signatures", ("Зав. отделением", "Заведующий отделением", "Зав. отд."), "signature"),
    _fd("head.signature", "Подпись заведующего", "signatures", ("Подпись зав. отделением", "Зав. отделением __________"), "signature"),
    _fd("chief.name", "Начмед", "signatures", ("Начмед", "Заместитель главного врача", "Зам. главного врача"), "signature"),
    _fd("chief.signature", "Подпись начмеда", "signatures", ("Подпись начмеда", "Начмед __________"), "signature"),
)


def default_field_registry(extra_definitions: Iterable[FieldDefinition] = ()) -> FieldRegistry:
    return FieldRegistry([*DEFAULT_FIELD_DEFINITIONS, *extra_definitions])
