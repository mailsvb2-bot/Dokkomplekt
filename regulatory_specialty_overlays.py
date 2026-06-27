"""Specialty overlays for soft medical-document advice.

Overlays add specialty-specific recommended fields without changing the core
DocumentPack model and without forcing doctors to accept the suggestions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

from regulatory_caucasus_aliases import specialty_aliases_for


@dataclass(frozen=True)
class SpecialtyOverlay:
    id: str
    label: str
    aliases: tuple[str, ...]
    recommended_fields: tuple[str, ...] = ()
    recommended_sections: tuple[str, ...] = ()
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class SpecialtyOverlayRegistry:
    def __init__(self, overlays: Iterable[SpecialtyOverlay]):
        self._overlays = {item.id: item for item in overlays}

    def overlays(self) -> tuple[SpecialtyOverlay, ...]:
        return tuple(self._overlays[key] for key in sorted(self._overlays))

    def get(self, overlay_id: str) -> SpecialtyOverlay | None:
        return self._overlays.get(str(overlay_id or "").strip().lower())

    def detect(self, text: str, *, explicit_specialty: str = "") -> SpecialtyOverlay | None:
        haystack = " ".join(str(text or "").lower().replace("ё", "е").split())
        explicit = str(explicit_specialty or "").strip().lower()
        if explicit:
            for overlay in self.overlays():
                if explicit == overlay.id or explicit in [alias.lower() for alias in overlay.aliases]:
                    return overlay
        best: tuple[int, SpecialtyOverlay] | None = None
        for overlay in self.overlays():
            score = sum(1 for alias in overlay.aliases if alias.lower().replace("ё", "е") in haystack)
            if score and (best is None or score > best[0]):
                best = (score, overlay)
        return best[1] if best else None


def _overlay(
    overlay_id: str,
    label: str,
    aliases: Sequence[str],
    fields: Sequence[str],
    sections: Sequence[str],
    notes: str = "",
) -> SpecialtyOverlay:
    merged_aliases = tuple(dict.fromkeys([*aliases, *specialty_aliases_for(overlay_id)]))
    return SpecialtyOverlay(overlay_id, label, merged_aliases, tuple(fields), tuple(sections), notes)


DEFAULT_SPECIALTY_OVERLAYS: tuple[SpecialtyOverlay, ...] = (
    _overlay("therapy", "Терапия", ("терапевт", "терапия", "АД", "ЧСС", "отёки", "отеки"), ("vitals.blood_pressure", "vitals.pulse", "vitals.temperature", "treatment.result"), ("objective_status", "labs", "instrumental")),
    _overlay("surgery", "Хирургия", ("хирург", "операция", "рана", "дренаж", "анестезия"), ("procedure.name", "procedure.date", "procedure.anesthesia", "procedure.description", "procedure.complications", "postoperative.status", "surgeon.signature"), ("procedure", "anesthesia", "consent")),
    _overlay("neurology", "Неврология", ("невролог", "неврологический", "рефлексы", "координация", "менингеальные"), ("status.neurological", "treatment.result"), ("specialty_status",)),
    _overlay("expert_commission", "Экспертно-комиссионный профиль", ("экспертный анамнез", "комиссия", "мсэ", "нетрудоспособность", "РВК"), ("anamnesis.expert",), ("specialty_status", "commission")),
    _overlay("dentistry", "Стоматология", ("стоматолог", "зуб", "прикус", "полость рта"), ("custom.dental_formula", "custom.oral_status", "procedure.name"), ("procedure", "recommendations")),
    _overlay("obstetrics", "Акушерство и гинекология", ("акушер", "гинеколог", "беременность", "роды", "новорожден"), ("custom.gestational_age", "custom.obstetric_status", "custom.newborn_status"), ("anamnesis_life", "objective_status")),
    _overlay("intensive_care", "Реанимация / интенсивная терапия", ("реанимация", "интенсивная терапия", "ИВЛ", "сатурация", "диурез"), ("vitals.blood_pressure", "vitals.pulse", "vitals.temperature", "custom.saturation", "custom.diuresis", "custom.ventilation_mode"), ("objective_status", "treatment")),
)


def default_specialty_overlay_registry() -> SpecialtyOverlayRegistry:
    return SpecialtyOverlayRegistry(DEFAULT_SPECIALTY_OVERLAYS)
