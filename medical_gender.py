"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

import copy
import re

from docx.document import Document as DocxDocument

try:
    from diary_filler import adapt_text_to_patient_gender, detect_gender_from_patient_name
except Exception:  # pragma: no cover - защитный fallback для автономного использования модуля
    def detect_gender_from_patient_name(_patient_name: str) -> str | None:
        return None

    def adapt_text_to_patient_gender(text: str, _gender: str | None) -> tuple[str, int]:
        return text, 0

from medical_constants import TARGET_MEDICAL_FACILITY
from medical_docx_editor import iter_all_paragraphs, remove_epi_mentions_from_document, set_paragraph_text
from medical_models import PatientData
from medical_text_utils import normalize_match, remove_forbidden_hospitalization_phrases

GENDER_ADAPTED_PATIENT_FIELDS = (
    "complaints",
    "life_anamnesis",
    "disease_anamnesis",
    "mental_status",
    "somatic_status",
    "treatment_plan",
    "epidemiology",
    "admission",
    "psych_account",
    "epi_text",
)


def patient_gender(data: PatientData) -> str | None:
    """Определить род пациента по первой части ФИО, как в заполнителе дневников."""
    return detect_gender_from_patient_name(data.fio or data.output_fio or "")


def adapt_patient_data_to_gender(data: PatientData) -> PatientData:
    """Вернуть копию данных, где клинические текстовые блоки согласованы с родом пациента.

    Диагноз, ФИО, адрес, даты, подписи и служебные реквизиты не трогаем: они
    не являются текстом о пациенте и не должны портиться морфологическим проходом.
    """
    gender = patient_gender(data)
    if gender not in {"male", "female"}:
        return data

    adapted = copy.deepcopy(data)
    for field_name in GENDER_ADAPTED_PATIENT_FIELDS:
        value = getattr(adapted, field_name, "")
        if not isinstance(value, str) or not value:
            continue
        new_value, _changed = adapt_text_to_patient_gender(value, gender)
        setattr(adapted, field_name, new_value)
    return adapted


def adapt_role_owned_patient_phrase(text: str, patient_name: str) -> str:
    """Adapt one explicitly patient-owned renderer phrase, never an entire DOCX.

    Templates contain both patient narrative and fixed legal/clinical boilerplate.
    Whole-document morphology cannot distinguish those ownership classes and has
    previously corrupted valid static wording (for example ``Пациент ознакомлен``
    -> ``Пациентка ознакомлен``).  Callers must opt in only for phrases that the
    renderer itself owns, such as a treatment/observation period sentence.
    """
    gender = detect_gender_from_patient_name(str(patient_name or ""))
    if gender not in {"male", "female"}:
        return text
    updated, _changed = adapt_text_to_patient_gender(str(text or ""), gender)
    return updated



def remove_forbidden_hospitalization_phrase_from_document(doc: DocxDocument) -> None:
    """Remove service hospitalization-decision phrase from every final DOCX paragraph."""
    for paragraph in list(iter_all_paragraphs(doc)):
        original = paragraph.text or ""
        if not original:
            continue
        cleaned = remove_forbidden_hospitalization_phrases(original)
        if cleaned != original:
            set_paragraph_text(paragraph, cleaned)


def normalize_facility_references_in_document(doc: DocxDocument) -> None:
    """Единообразно заменить старые названия учреждения/отделения в итоговых DOCX.

    Пользовательский контракт: если в шаблоне или тексте встречается
    «ГБУЗ НО ПБ №2» либо «отделение №3», в результате должно быть
    «медицинскую организацию по профилю». Отдельно нормализуем финальную фразу
    направления/осмотра приёмного покоя.
    """
    target = TARGET_MEDICAL_FACILITY
    for paragraph in list(iter_all_paragraphs(doc)):
        original = paragraph.text or ""
        if not original.strip():
            continue
        normalized = normalize_match(original)
        if normalized.startswith("направляется на лечение") or normalized.startswith("направляется в гбуз"):
            set_paragraph_text(paragraph, f"Направляется в {target}")
            continue
        updated = original
        replacements = [
            (r"ГБУЗ\s*НО\s*ПБ\s*№\s*2", target),
            (r"ГБУЗНО\s*«?Психиатрическая\s+больница\s*№\s*2»?(?:\s*г\.\s*Н\.\s*Новгорода)?", target),
            (r"ГБУЗ\s*НО\s*«?Психиатрическая\s+больница\s*№\s*2»?(?:\s*г\.\s*Н\.\s*Новгорода)?", target),
            (r"отделени[ея]\s*№\s*3", target),
        ]
        for pattern, replacement in replacements:
            updated = re.sub(pattern, replacement, updated, flags=re.IGNORECASE)
        updated = re.sub(rf"в\s+{re.escape(target)}", f"в {target}", updated, flags=re.IGNORECASE)
        updated = re.sub(r"\s+", " ", updated).strip()
        if updated != original:
            set_paragraph_text(paragraph, updated)


def finalize_medical_document(doc: DocxDocument, data: PatientData) -> None:
    """Общие финальные правки перед сохранением любого медицинского документа."""
    normalize_facility_references_in_document(doc)
    remove_forbidden_hospitalization_phrase_from_document(doc)
    # Patient narrative is gender-adapted before rendering.  Do not run a
    # morphology pass over the whole DOCX: fixed template boilerplate is not
    # patient data and must remain byte-for-byte semantically stable.
    remove_forbidden_hospitalization_phrase_from_document(doc)
    if not data.epi_text:
        remove_epi_mentions_from_document(doc)
