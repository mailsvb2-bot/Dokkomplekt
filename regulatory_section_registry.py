"""Medical document section registry for soft regulatory/template advice.

This module is intentionally small and data-focused.  It does not decide
whether a doctor's document is "allowed".  It only normalizes common section
names so the template advisor can gently suggest missing blocks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Iterable, Sequence

from regulatory_caucasus_aliases import section_aliases_for


@dataclass(frozen=True)
class RegulatorySection:
    """One reusable medical-document section meaning."""

    id: str
    label: str
    aliases: tuple[str, ...]
    field_ids: tuple[str, ...] = ()
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class RegulatorySectionRegistry:
    """Lookup and marker search for known medical sections."""

    def __init__(self, sections: Iterable[RegulatorySection]):
        normalized: dict[str, RegulatorySection] = {}
        for section in sections:
            section_id = normalize_section_id(section.id)
            if section_id in normalized:
                raise ValueError(f"Дублируется раздел нормативного справочника: {section_id}")
            normalized[section_id] = RegulatorySection(
                id=section_id,
                label=section.label or section_id,
                aliases=tuple(alias.strip() for alias in section.aliases if alias.strip()),
                field_ids=tuple(dict.fromkeys(item.strip() for item in section.field_ids if item.strip())),
                description=section.description,
            )
        self._sections = normalized

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._sections))

    def get(self, section_id: str) -> RegulatorySection | None:
        return self._sections.get(normalize_section_id(section_id))

    def require(self, section_id: str) -> RegulatorySection:
        section = self.get(section_id)
        if section is None:
            raise KeyError(f"Неизвестный раздел документа: {section_id}")
        return section

    def sections(self) -> tuple[RegulatorySection, ...]:
        return tuple(self._sections[key] for key in sorted(self._sections))

    def detect_sections(self, text: str) -> tuple[str, ...]:
        haystack = normalize_text(text)
        found: list[str] = []
        for section in self.sections():
            if any(normalize_text(alias) in haystack for alias in section.aliases):
                found.append(section.id)
        return tuple(dict.fromkeys(found))

    def missing_sections(self, expected_section_ids: Sequence[str], text: str) -> tuple[str, ...]:
        found = set(self.detect_sections(text))
        result: list[str] = []
        for section_id in expected_section_ids:
            normalized = normalize_section_id(section_id)
            if normalized not in found:
                result.append(normalized)
        return tuple(dict.fromkeys(result))


def normalize_section_id(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_.]+", "_", str(value or "").strip().lower()).strip("_")
    if not text:
        raise ValueError("Пустой идентификатор раздела")
    return text


def normalize_text(value: str) -> str:
    return " ".join(str(value or "").lower().replace("ё", "е").split())


def _section(section_id: str, label: str, aliases: Sequence[str], field_ids: Sequence[str] = (), description: str = "") -> RegulatorySection:
    merged_aliases = tuple(dict.fromkeys([*aliases, *section_aliases_for(section_id)]))
    return RegulatorySection(section_id, label, merged_aliases, tuple(field_ids), description)


DEFAULT_REGULATORY_SECTIONS: tuple[RegulatorySection, ...] = (
    _section("patient_identity", "Идентификация пациента", ("Ф.И.О.", "ФИО", "Пациент", "Больной", "Дата рождения"), ("patient.fio", "patient.birth_date")),
    _section("case_admin", "Реквизиты случая", ("История болезни", "ИБ №", "Номер карты", "Отделение"), ("case.number", "case.department")),
    _section("admission", "Поступление", ("Дата поступления", "Дата госпитализации", "Поступил", "Госпитализирован"), ("admission.date",)),
    _section("discharge", "Выписка", ("Дата выписки", "Выписан", "Выписана", "Состояние при выписке"), ("discharge.date", "condition.discharge")),
    _section("complaints", "Жалобы", ("Жалобы", "Скарги", "Жалобы на момент осмотра"), ("complaints",)),
    _section("anamnesis_disease", "Анамнез заболевания", ("Анамнез заболевания", "Анамнез болезни", "Anamnesis morbi"), ("anamnesis.disease",)),
    _section("anamnesis_life", "Анамнез жизни", ("Анамнез жизни", "Anamnesis vitae"), ("anamnesis.life",)),
    _section("objective_status", "Объективный статус", ("Объективный статус", "Объективно", "Status praesens"), ("status.objective",)),
    _section("specialty_status", "Профильный статус", ("Психический статус", "Неврологический статус", "Локальный статус", "Послеоперационный статус"), ("status.mental", "status.neurological", "postoperative.status")),
    _section("diagnosis", "Диагноз", ("Диагноз", "Клинический диагноз", "Предварительный диагноз", "Заключительный диагноз"), ("diagnosis.main", "diagnosis.icd10")),
    _section("treatment", "Лечение", ("Лечение", "План лечения", "Назначенное лечение", "Проведенное лечение", "Проведённое лечение"), ("treatment.plan", "treatment.summary")),
    _section("labs", "Лабораторные исследования", ("Анализы", "Лабораторные исследования", "Результаты анализов"), ("labs.results", "labs.types")),
    _section("instrumental", "Инструментальные исследования", ("УЗИ", "ЭКГ", "ЭЭГ", "КТ", "МРТ", "Рентген", "Эндоскопия"), ("instrumental.results",)),
    _section("procedure", "Операция / процедура", ("Операция", "Протокол операции", "Оперативное вмешательство", "Манипуляция"), ("procedure.name", "procedure.date", "procedure.description")),
    _section("anesthesia", "Анестезия", ("Анестезия", "Обезболивание", "Наркоз", "Анестезиолог"), ("procedure.anesthesia", "anesthesia.type")),
    _section("consent", "Информированное согласие", ("Информированное согласие", "Согласие на операцию", "Согласие на вмешательство"), ("consent.informed",)),
    _section("recommendations", "Рекомендации", ("Рекомендовано", "Рекомендации", "Даны рекомендации"), ("recommendations",)),
    _section("commission", "Комиссия / МСЭ / ЛКК", ("ВК", "ЛКК", "МСЭ", "Врачебная комиссия", "Нетрудоспособность"), ("commission.decision", "mse.referral_reason")),
    _section("signatures", "Подписи", ("Врач", "Подпись", "Зав. отделением", "Начмед", "Председатель комиссии"), ("doctor.signature", "head.signature", "chief.signature")),
)


def default_section_registry() -> RegulatorySectionRegistry:
    return RegulatorySectionRegistry(DEFAULT_REGULATORY_SECTIONS)
