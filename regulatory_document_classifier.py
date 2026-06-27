"""Deterministic medical document-role classifier for soft advice."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Sequence

from regulatory_document_roles import DocumentRole, default_document_role_registry
from regulatory_section_registry import default_section_registry, normalize_text
from regulatory_specialty_overlays import SpecialtyOverlay, default_specialty_overlay_registry
from universal_scanner import extract_docx_blocks


@dataclass(frozen=True)
class DocumentRoleScore:
    role_id: str
    label: str
    confidence: float
    matched_markers: tuple[str, ...]
    matched_sections: tuple[str, ...]
    specialty_overlay: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DocumentClassificationResult:
    source_path: str
    text_length: int
    best: DocumentRoleScore | None
    scores: tuple[DocumentRoleScore, ...]

    @property
    def role_id(self) -> str:
        return self.best.role_id if self.best else "unknown"

    @property
    def confidence(self) -> float:
        return self.best.confidence if self.best else 0.0

    def to_dict(self) -> dict:
        return {"source_path": self.source_path, "text_length": self.text_length, "best": self.best.to_dict() if self.best else None, "scores": [item.to_dict() for item in self.scores]}

    def human_report(self) -> str:
        if not self.best:
            return "Роль документа не определена. Подсказки будут общими и не блокирующими."
        lines = [f"Похоже, это: {self.best.label} ({int(round(self.best.confidence * 100))}%)"]
        if self.best.matched_markers:
            lines.append("Найденные признаки: " + ", ".join(self.best.matched_markers[:10]))
        if self.best.matched_sections:
            lines.append("Похожие разделы: " + ", ".join(self.best.matched_sections[:10]))
        return "\n".join(lines)


def classify_docx(path: str | Path, *, explicit_specialty: str = "") -> DocumentClassificationResult:
    blocks = extract_docx_blocks(path)
    return classify_document_text("\n".join(block.text for block in blocks), source_path=str(Path(path).expanduser()), explicit_specialty=explicit_specialty)


def classify_document_text(text: str, *, source_path: str = "", explicit_specialty: str = "") -> DocumentClassificationResult:
    roles = default_document_role_registry().roles()
    section_registry = default_section_registry()
    overlay = default_specialty_overlay_registry().detect(text, explicit_specialty=explicit_specialty)
    found_sections = set(section_registry.detect_sections(text))
    scored: list[DocumentRoleScore] = []
    for role in roles:
        score, markers = _score_role(role, text, found_sections, overlay)
        if score <= 0:
            continue
        confidence = min(0.99, score / 10.0)
        scored.append(DocumentRoleScore(role.id, role.label, confidence, tuple(markers), tuple(sorted(found_sections & set(role.typical_sections))), overlay.id if overlay else ""))
    scored.sort(key=lambda item: (item.confidence, len(item.matched_markers), len(item.matched_sections)), reverse=True)
    best = scored[0] if scored else None
    return DocumentClassificationResult(source_path, len(text or ""), best, tuple(scored[:8]))


def text_from_docx(path: str | Path) -> str:
    return "\n".join(block.text for block in extract_docx_blocks(path))


def _score_role(role: DocumentRole, text: str, found_sections: set[str], overlay: SpecialtyOverlay | None) -> tuple[float, list[str]]:
    haystack = normalize_text(text)
    markers: list[str] = []
    score = 0.0
    for phrase in (*role.aliases, *role.marker_phrases):
        if phrase and normalize_text(phrase) in haystack:
            markers.append(phrase)
            score += 2.0 if phrase in role.aliases else 1.2
    section_hits = found_sections & set(role.typical_sections)
    score += min(3.0, 0.6 * len(section_hits))
    if overlay and role.specialty and overlay.id == role.specialty:
        score += 1.5
        markers.append(f"профиль: {overlay.label}")
    # Strong phrase pairs reduce false positives for common words like "врач".
    if role.id == "discharge_epicrisis" and _has_all(haystack, ["дата поступления", "дата выписки"]):
        score += 2.0
    if role.id == "operation_protocol" and _has_any(haystack, ["ход операции", "оперативное вмешательство", "протокол операции"]):
        score += 2.0
    if role.id == "primary_exam" and _has_all(haystack, ["жалобы", "анамнез", "диагноз"]):
        score += 1.5
    return score, list(dict.fromkeys(markers))


def _has_all(text: str, needles: Sequence[str]) -> bool:
    return all(normalize_text(needle) in text for needle in needles)


def _has_any(text: str, needles: Sequence[str]) -> bool:
    return any(normalize_text(needle) in text for needle in needles)
