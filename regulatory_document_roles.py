"""Document-role knowledge base for soft medical template advice.

The goal is not to enforce one country's exact form.  The goal is to recognize
recurring medical-document roles and suggest meaningful sections that are often
present in those roles.  Doctors can always keep their own template as-is.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

from regulatory_caucasus_aliases import role_aliases_for, role_markers_for


@dataclass(frozen=True)
class DocumentRole:
    id: str
    label: str
    aliases: tuple[str, ...]
    marker_phrases: tuple[str, ...]
    core_fields: tuple[str, ...]
    suggested_fields: tuple[str, ...]
    typical_sections: tuple[str, ...]
    specialty: str = ""
    source_note: str = "Сводная медицинская практика форм стационара/амбулатории; используется только как мягкая подсказка."

    def all_advisory_fields(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.core_fields, *self.suggested_fields)))

    def to_dict(self) -> dict:
        return asdict(self)


class DocumentRoleRegistry:
    def __init__(self, roles: Iterable[DocumentRole]):
        self._roles = {role.id: role for role in roles}

    def roles(self) -> tuple[DocumentRole, ...]:
        return tuple(self._roles[key] for key in sorted(self._roles))

    def get(self, role_id: str) -> DocumentRole | None:
        return self._roles.get(str(role_id or "").strip().lower())

    def require(self, role_id: str) -> DocumentRole:
        role = self.get(role_id)
        if role is None:
            raise KeyError(f"Неизвестная роль медицинского документа: {role_id}")
        return role


def _role(
    role_id: str,
    label: str,
    aliases: Sequence[str],
    markers: Sequence[str],
    core: Sequence[str],
    suggested: Sequence[str],
    sections: Sequence[str],
    specialty: str = "",
) -> DocumentRole:
    merged_aliases = tuple(dict.fromkeys([*aliases, *role_aliases_for(role_id)]))
    merged_markers = tuple(dict.fromkeys([*markers, *role_markers_for(role_id)]))
    return DocumentRole(role_id, label, merged_aliases, merged_markers, tuple(core), tuple(suggested), tuple(sections), specialty)


_COMMON = ("patient.fio", "case.number")
_ADMISSION = (*_COMMON, "admission.date", "diagnosis.main")
_DISCHARGE = (*_COMMON, "admission.date", "discharge.date", "diagnosis.main")

DEFAULT_DOCUMENT_ROLES: tuple[DocumentRole, ...] = (
    _role("hospitalization_referral", "Направление на госпитализацию", ("направление на госпитализацию", "направлення на госпіталізацію"), ("направление", "госпитализация", "диагноз направившего"), _ADMISSION, ("patient.address", "patient.passport", "patient.snils", "case.department"), ("patient_identity", "case_admin", "admission", "diagnosis")),
    _role("admission_doctor_exam", "Осмотр врача приёмного покоя", ("осмотр врача приемного покоя", "осмотр врача приёмного покоя", "приймальне відділення"), ("приемный покой", "приёмный покой", "поступает", "госпитализирован"), _ADMISSION, ("complaints", "anamnesis.disease", "status.objective", "treatment.plan", "doctor.signature"), ("patient_identity", "admission", "complaints", "objective_status", "diagnosis", "signatures")),
    _role("primary_exam", "Первичный осмотр", ("первичный осмотр", "первинний огляд", "осмотр при поступлении"), ("жалобы", "анамнез", "объективный статус", "диагноз", "план лечения"), _ADMISSION, ("complaints", "anamnesis.disease", "anamnesis.life", "status.objective", "treatment.plan", "doctor.signature"), ("patient_identity", "case_admin", "admission", "complaints", "anamnesis_disease", "anamnesis_life", "objective_status", "diagnosis", "treatment", "signatures")),
    _role("inpatient_record", "Медицинская карта / история болезни", ("история болезни", "медицинская карта стационарного", "медична карта стаціонарного"), ("титульный лист", "дневник", "назначения", "консультации", "эпикриз"), _ADMISSION, ("complaints", "anamnesis.disease", "anamnesis.life", "labs.results", "instrumental.results", "treatment.plan", "recommendations"), ("patient_identity", "case_admin", "admission", "complaints", "anamnesis_disease", "objective_status", "diagnosis", "labs", "instrumental", "treatment")),
    _role("daily_diary", "Дневник наблюдения", ("дневник наблюдения", "щоденник", "динамическое наблюдение"), ("состояние", "динамика", "жалобы", "назначения"), _COMMON, ("admission.date", "diagnosis.main", "treatment.plan", "status.objective", "vitals.temperature", "doctor.signature"), ("patient_identity", "case_admin", "objective_status", "treatment", "signatures")),
    _role("discharge_epicrisis", "Выписной эпикриз", ("выписной эпикриз", "виписний епікриз", "выписка из медицинской карты"), ("дата поступления", "дата выписки", "проведенное лечение", "рекомендации", "состояние при выписке"), _DISCHARGE, ("treatment.summary", "labs.results", "instrumental.results", "condition.discharge", "recommendations", "doctor.signature", "head.signature"), ("patient_identity", "case_admin", "admission", "discharge", "diagnosis", "treatment", "labs", "instrumental", "recommendations", "signatures")),
    _role("transfer_epicrisis", "Переводной эпикриз", ("переводной эпикриз", "перевод в отделение", "переведен"), ("перевод", "динамика", "лечение", "рекомендации"), _ADMISSION, ("treatment.summary", "condition.discharge", "recommendations", "doctor.signature"), ("patient_identity", "admission", "diagnosis", "treatment", "recommendations")),
    _role("specialist_consultation", "Консультационное заключение", ("консультационное заключение", "консультация специалиста", "консультація"), ("цель консультации", "заключение", "рекомендации", "консультант"), _COMMON, ("consultation.reason", "consultant.specialty", "status.objective", "diagnosis.main", "recommendations", "consultant.signature"), ("patient_identity", "complaints", "objective_status", "diagnosis", "recommendations", "signatures")),
    _role("operation_protocol", "Протокол операции", ("протокол операции", "оперативное вмешательство", "журнал операций"), ("операция", "анестезия", "ход операции", "осложнения", "хирург"), _COMMON, ("procedure.name", "procedure.date", "procedure.anesthesia", "procedure.description", "procedure.complications", "diagnosis.main", "surgeon.signature", "assistant.signature"), ("patient_identity", "case_admin", "diagnosis", "procedure", "anesthesia", "signatures"), "surgery"),
    _role("anesthesia_preop", "Предоперационный осмотр анестезиолога", ("предоперационный осмотр анестезиолога", "анестезиолог"), ("анестезиолог", "премедикация", "риск", "обезболивание"), _COMMON, ("procedure.name", "procedure.date", "procedure.anesthesia", "vitals.blood_pressure", "vitals.pulse", "doctor.signature"), ("patient_identity", "procedure", "anesthesia", "objective_status", "signatures"), "surgery"),
    _role("informed_consent", "Информированное согласие", ("информированное согласие", "согласие на операцию", "согласие на вмешательство"), ("согласие", "риски", "осложнения", "подпись пациента"), ("patient.fio",), ("procedure.name", "procedure.anesthesia", "consent.informed", "doctor.signature"), ("patient_identity", "consent", "procedure", "signatures")),
    _role("medical_commission", "Врачебная комиссия / ЛКК / ВК", ("врачебная комиссия", "ВК", "ЛКК", "комиссионный осмотр"), ("комиссия", "протокол", "решение", "трудоспособность"), _COMMON, ("diagnosis.main", "treatment.summary", "recommendations", "commission.decision", "doctor.signature", "head.signature"), ("patient_identity", "case_admin", "diagnosis", "commission", "signatures")),
    _role("joint_medical_exam", "Совместный осмотр", ("совместный осмотр", "комиссионный осмотр", "осмотр комиссией"), ("совместный осмотр", "комиссия", "протокол", "решение"), _COMMON, ("diagnosis.main", "treatment.summary", "recommendations", "commission.decision", "doctor.signature", "head.signature"), ("patient_identity", "case_admin", "diagnosis", "commission", "treatment", "signatures")),
    _role("mse_referral", "МСЭ / направление на экспертизу", ("МСЭ", "медико-социальная экспертиза", "направление на мсэ"), ("инвалидность", "ограничение жизнедеятельности", "реабилитация"), _COMMON, ("diagnosis.main", "treatment.summary", "mse.referral_reason", "recommendations", "doctor.signature"), ("patient_identity", "diagnosis", "commission", "recommendations")),
    _role("vk_mse", "ВК на МСЭ", ("ВК на МСЭ", "врачебная комиссия на мсэ", "направление на мсэ"), ("мсэ", "комиссия", "протокол", "реабилитация"), _COMMON, ("diagnosis.main", "treatment.summary", "mse.referral_reason", "recommendations", "doctor.signature", "head.signature"), ("patient_identity", "case_admin", "diagnosis", "commission", "recommendations", "signatures")),
    _role("sick_leave_vk", "ВК больничный", ("ВК больничный", "лист нетрудоспособности", "больничный лист", "продление нетрудоспособности"), ("нетрудоспособность", "больничный", "протокол", "комиссия"), _COMMON, ("patient.work", "patient.position", "diagnosis.main", "treatment.summary", "commission.decision", "doctor.signature", "head.signature"), ("patient_identity", "case_admin", "diagnosis", "commission", "treatment", "signatures")),
    _role("military_commissariat_act", "Акт для РВК", ("акт для рвк", "акт рвк", "военный комиссариат", "военкомат"), ("рвк", "военкомат", "медицинское заключение"), _DISCHARGE, ("treatment.summary", "condition.discharge", "recommendations", "doctor.signature", "head.signature"), ("patient_identity", "case_admin", "admission", "discharge", "diagnosis", "treatment", "recommendations", "signatures")),
    _role("lab_results", "Лабораторные результаты", ("лабораторные исследования", "анализы", "ОАК", "ОАМ", "биохимия"), ("анализ", "результат", "норма", "единицы"), ("patient.fio",), ("labs.results", "labs.types", "doctor.signature"), ("patient_identity", "labs", "signatures")),
    _role("instrumental_study", "Инструментальное исследование", ("УЗИ", "ЭКГ", "ЭЭГ", "КТ", "МРТ", "рентген", "эндоскопия"), ("заключение", "описание", "исследование"), ("patient.fio",), ("instrumental.results", "diagnosis.main", "doctor.signature"), ("patient_identity", "instrumental", "diagnosis", "signatures")),
)


def default_document_role_registry() -> DocumentRoleRegistry:
    return DocumentRoleRegistry(DEFAULT_DOCUMENT_ROLES)
