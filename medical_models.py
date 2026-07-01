"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import re
from pathlib import Path
from typing import Dict, List, Sequence

from medical_constants import DATE_FMT, DOCUMENT_LABELS, OUTPUT_SUFFIXES
from medical_formatting import parse_date, safe_filename

@dataclass
class PatientData:
    case_number: str = ""
    fio: str = ""
    # Имя пациента для названия создаваемых файлов.
    # ВАЖНО: это отдельное поле; оно не подменяет ФИО внутри документов.
    output_fio: str = ""
    birth: str = ""
    registered: str = ""
    psych_account: str = ""
    work_org: str = ""
    position: str = ""
    sick_leave: str = ""
    # Экспертный анамнез: заполняется из UI/popup, чтобы первичный осмотр,
    # выписной эпикриз и комиссионный осмотр писали одну согласованную формулировку.
    expert_work_status: str = ""  # да / нет
    expert_work_org: str = ""
    expert_position: str = ""
    expert_sick_leave_needed: str = ""  # да / нет
    expert_sick_leave_from: str = ""
    expert_sick_leave_number: str = ""
    disability: str = ""
    rvk_referral: str = ""
    admission: str = ""

    complaints: str = ""
    life_anamnesis: str = ""
    disease_anamnesis: str = ""
    mental_status: str = ""
    somatic_status: str = ""
    examination_plan: str = ""
    treatment_plan: str = ""
    # True only when the primary document itself contains an explicit
    # treatment section row: «Лечение», «Назначенное лечение» or
    # «План лечения». Ordinary prose like «за время лечения» is ignored.
    has_treatment_section: bool = False
    diagnosis: str = ""
    epidemiology: str = ""

    admission_date: str = ""
    discharge_date: str = ""
    epi_text: str = ""
    additional_info_text: str = ""
    additional_info_source: str = ""
    # Универсальный блок анализов. Он заполняется только из явного выбора врача:
    # ручной ввод, отдельный файл анализов, выделение мышкой в разметчике
    # или явное решение «Нет анализов». Программа не генерирует результаты анализов.
    labs_text: str = ""
    labs_source: str = ""
    labs_date_policy: str = "preserve_found_dates"
    labs_without: bool = False
    input_document_kind: str = ""

    # Ручные реквизиты из UI для отдельных документов.
    rvk_act_number: str = ""
    rvk_military_commissariat: str = ""
    rvk_work_position: str = ""
    vk_date: str = ""
    vk_protocol_number: str = ""
    vk_protocol_date: str = ""
    vk_mse_work_org: str = ""
    vk_mse_position: str = ""
    # Combined value for custom/profile placeholders such as vk_mse.work_position.
    vk_mse_work_position: str = ""
    sick_leave_vk_date: str = ""
    sick_leave_vk_protocol_number: str = ""
    sick_leave_vk_protocol_date: str = ""
    sick_leave_vk_commission_date: str = ""
    sick_leave_vk_work_org: str = ""
    sick_leave_vk_position: str = ""
    # Совместимость со старой сборкой, где поле было одним.
    sick_leave_vk_work_position: str = ""
    commission_date: str = ""
    commission_number: str = ""

    # Подписи не должны быть зашиты под конкретного врача/отделение.
    # Если шаблон требует подпись, программа спросит её как обязательное поле
    # или возьмёт из профиля врача.
    doctor: str = ""
    head: str = ""

    warnings: List[str] = field(default_factory=list)

    def lab_dates(self) -> Dict[str, str]:
        result = {"day1": "", "day2": "", "flg": ""}
        from medical_formatting import parse_date

        dt = parse_date(self.admission_date)
        if not dt:
            return result
        result["day1"] = (dt + timedelta(days=1)).strftime(DATE_FMT)
        result["day2"] = (dt + timedelta(days=2)).strftime(DATE_FMT)
        result["flg"] = (dt - timedelta(days=27)).strftime(DATE_FMT)
        return result

    def missing_critical_fields(self) -> List[str]:
        missing = []
        if not self.fio:
            missing.append("Ф.И.О.")
        if not self.birth:
            missing.append("год/дата рождения")
        if not self.admission_date:
            missing.append("дата госпитализации")
        return missing

    def missing_recommended_fields(self) -> List[str]:
        checks = [
            ("жалобы", self.complaints),
            ("анамнез жизни", self.life_anamnesis),
            ("анамнез заболевания", self.disease_anamnesis),
            ("профильный статус", self.mental_status),
            ("диагноз", self.diagnosis),
            ("план лечения", self.treatment_plan),
        ]
        return [name for name, value in checks if not value]


# --- Patient case preflight/control surface ---
_STATUS_OK = "found"
_STATUS_MANUAL = "manual"
_STATUS_WARN = "warn"
_STATUS_MISSING = "missing"


@dataclass(frozen=True)
class PatientCaseField:
    key: str
    label: str
    value: str
    status: str
    source: str = ""
    required: bool = False

    @property
    def icon(self) -> str:
        if self.status in {_STATUS_OK, _STATUS_MANUAL}:
            return "✅"
        if self.status == _STATUS_WARN:
            return "⚠️"
        return "❌"

    @property
    def status_text(self) -> str:
        if self.status == _STATUS_MANUAL:
            return "введено вручную"
        if self.status == _STATUS_OK:
            return "найдено автоматически"
        if self.status == _STATUS_WARN:
            return "нужно проверить"
        return "не найдено, требуется ввод"

    def line(self) -> str:
        suffix = f" — {self.source}" if self.source else ""
        value = self.value if self.value else "—"
        return f"{self.icon} {self.label}: {value} ({self.status_text}{suffix})"


@dataclass(frozen=True)
class PatientCaseReview:
    fields: tuple[PatientCaseField, ...]
    selected_outputs: tuple[str, ...] = ()
    output_dir: str = ""
    primary_path: str = ""
    warnings: tuple[str, ...] = ()

    def critical_missing(self) -> list[PatientCaseField]:
        return [field for field in self.fields if field.required and field.status == _STATUS_MISSING]

    def warning_fields(self) -> list[PatientCaseField]:
        return [field for field in self.fields if field.status == _STATUS_WARN]

    def patient_stem(self) -> str:
        value = self.value("output_fio") or self.value("fio") or "Пациент"
        return safe_filename(value)

    def value(self, key: str) -> str:
        for field in self.fields:
            if field.key == key:
                return field.value
        return ""

    def as_text(self, *, include_sources: bool = True) -> str:
        lines: list[str] = ["ПРОВЕРКА ПЕРЕД СОЗДАНИЕМ ДОКУМЕНТОВ"]
        if self.primary_path:
            lines.append(f"Первичный документ: {Path(self.primary_path).name}")
        if self.output_dir:
            lines.append(f"Папка результата: {self.output_dir}")
        if self.selected_outputs:
            lines.append("Документы к созданию: " + ", ".join(self.selected_outputs))
        lines.append("")
        for field in self.fields:
            if include_sources:
                lines.append(field.line())
            else:
                value = field.value if field.value else "—"
                lines.append(f"{field.icon} {field.label}: {value}")
        missing = self.critical_missing()
        if missing:
            lines.append("")
            lines.append("Критические пропуски: " + ", ".join(field.label for field in missing))
        if self.warnings:
            lines.append("")
            lines.append("Предупреждения:")
            lines.extend(f"- {item}" for item in self.warnings)
        return "\n".join(lines).strip() + "\n"


def _clean(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _manual_status(value: str, is_manual: bool, *, required: bool = False) -> str:
    if value:
        return _STATUS_MANUAL if is_manual else _STATUS_OK
    return _STATUS_MISSING if required else _STATUS_WARN


def _date_status(value: str, is_manual: bool, *, required: bool = False) -> str:
    if not value:
        return _STATUS_MISSING if required else _STATUS_WARN
    if not parse_date(value):
        return _STATUS_MISSING if required else _STATUS_WARN
    return _STATUS_MANUAL if is_manual else _STATUS_OK


def _diagnosis_status(value: str, is_manual: bool, *, required: bool = False, require_icd10: bool = False) -> str:
    if not value:
        return _STATUS_MISSING if required else _STATUS_WARN
    if require_icd10 and not _looks_like_icd10_diagnosis(value):
        return _STATUS_MISSING if required else _STATUS_WARN
    return _STATUS_MANUAL if is_manual else _STATUS_OK


_ICD10_ANY_CODE_RE = re.compile(r"(?<![A-Za-zА-Яа-я0-9])[A-ZА-ЯЁІЇЈ]\s*\d{2}(?:[.,]\s*[0-9A-ZА-ЯЁІЇЈ]+)?", re.IGNORECASE)


def _looks_like_icd10_diagnosis(value: str) -> bool:
    """Accept any ICD-10 class letter, not only the legacy F-class."""
    return bool(_ICD10_ANY_CODE_RE.search(str(value or "")))

def _custom_ids_text(selected_custom: Sequence[str]) -> str:
    return " ".join(str(item or "").strip().lower().replace("ё", "е") for item in selected_custom or ())


def _treatment_required(selected_medical: Sequence[str], selected_custom: Sequence[str] = ()) -> bool:
    custom_text = _custom_ids_text(selected_custom)
    custom_needs = any(marker in custom_text for marker in ("discharge", "epicrisis", "rvk", "commission", "vk_mse", "mse", "treatment"))
    return bool(set(selected_medical) & {"primary", "discharge", "commission", "vk_mse", "sick_leave_vk"}) or custom_needs


def _discharge_required(selected_medical: Sequence[str], selected_diaries: bool, selected_custom: Sequence[str] = ()) -> bool:
    custom_text = _custom_ids_text(selected_custom)
    custom_needs = any(marker in custom_text for marker in ("daily_diary", "diary", "discharge", "epicrisis", "rvk", "discharge_date"))
    return selected_diaries or bool(set(selected_medical) & {"discharge", "rvk"}) or custom_needs


def selected_output_labels(selected_medical: Sequence[str], selected_diaries: bool, selected_custom: Sequence[str] = ()) -> tuple[str, ...]:
    result = [DOCUMENT_LABELS.get(kind, kind) for kind in selected_medical]
    if selected_diaries:
        result.append("Дневники наблюдения")
    result.extend(str(item) for item in selected_custom)
    return tuple(result)


def build_patient_case_review(
    data: PatientData,
    *,
    selected_medical: Sequence[str] = (),
    selected_diaries: bool = False,
    selected_custom: Sequence[str] = (),
    output_dir: str = "",
    primary_path: str = "",
    manual_patient_name: bool = False,
    manual_admission_date: bool = False,
    manual_discharge_date: bool = False,
    manual_diagnosis: bool = False,
    manual_case_number: bool = False,
    manual_treatment: bool = False,
) -> PatientCaseReview:
    """Implement the build_patient_case_review workflow with validation, UI state updates and diagnostics."""
    selected_medical = tuple(selected_medical or ())
    fields: list[PatientCaseField] = []
    selected_labels = selected_output_labels(selected_medical, selected_diaries, selected_custom)

    fio = _clean(data.fio)
    output_fio = _clean(data.output_fio or data.fio)
    case_number = _clean(data.case_number)
    birth = _clean(data.birth)
    admission_date = _clean(data.admission_date)
    discharge_date = _clean(data.discharge_date)
    diagnosis = _clean(data.diagnosis)
    treatment = _clean(data.treatment_plan)

    medical_or_diary = bool(selected_medical or selected_diaries or selected_custom)
    needs_case = bool(selected_medical or selected_custom)
    needs_discharge = _discharge_required(selected_medical, selected_diaries, selected_custom)
    needs_treatment = _treatment_required(selected_medical, selected_custom)

    fields.append(PatientCaseField("fio", "ФИО пациента в документах", fio, _manual_status(fio, False, required=medical_or_diary), "из первичного документа", required=medical_or_diary))
    fields.append(PatientCaseField("output_fio", "Имя пациента для файлов", output_fio, _manual_status(output_fio, manual_patient_name, required=medical_or_diary), "UI/карточка пациента", required=medical_or_diary))
    fields.append(PatientCaseField("case_number", "Номер истории болезни", case_number, _manual_status(case_number, manual_case_number, required=needs_case), "первичный документ или popup", required=needs_case))
    fields.append(PatientCaseField("birth", "Дата/год рождения", birth, _manual_status(birth, False, required=False), "из первичного документа", required=False))
    fields.append(PatientCaseField("admission_date", "Дата поступления", admission_date, _date_status(admission_date, manual_admission_date, required=medical_or_diary), "заголовок/первичный документ/UI", required=medical_or_diary))
    fields.append(PatientCaseField("discharge_date", "Дата выписки", discharge_date, _date_status(discharge_date, manual_discharge_date, required=needs_discharge), "UI/popup", required=needs_discharge))
    diagnosis_required = bool(selected_medical or selected_diaries or selected_custom)
    diagnosis_requires_icd10 = bool(selected_medical or selected_custom)
    fields.append(PatientCaseField(
        "diagnosis",
        "Диагноз",
        diagnosis,
        _diagnosis_status(diagnosis, manual_diagnosis, required=diagnosis_required, require_icd10=diagnosis_requires_icd10),
        "первичный документ/UI",
        required=diagnosis_required,
    ))
    fields.append(PatientCaseField("treatment", "Лечение", treatment, _manual_status(treatment, manual_treatment, required=needs_treatment), "первичный документ или popup", required=needs_treatment))

    warnings = list(data.warnings or [])
    if diagnosis and not _looks_like_icd10_diagnosis(diagnosis) and (selected_medical or selected_custom):
        warnings.append("Диагноз найден без явного шифра МКБ-10 — выберите диагноз из справочника или укажите код вручную.")
    return PatientCaseReview(tuple(fields), selected_labels, output_dir=str(output_dir or ""), primary_path=str(primary_path or ""), warnings=tuple(warnings))



def augment_patient_case_review_with_custom_flags(
    review: PatientCaseReview,
    custom_flags: dict[str, bool],
    *,
    case_number: str = "",
    diagnosis: str = "",
    treatment: str = "",
    discharge_date: str = "",
    labs: str = "",
    labs_without: bool = False,
    manual_case_number: bool = False,
    manual_diagnosis: bool = False,
    manual_treatment: bool = False,
    manual_discharge_date: bool = False,
) -> PatientCaseReview:
    """Promote medpack/custom button requirements into the standard preflight popup."""

    if not custom_flags:
        return review
    fields = list(review.fields)

    def status(value: str, *, manual: bool = False, required: bool = False, date: bool = False, icd10: bool = False) -> str:
        value = str(value or "").strip()
        if not value:
            return _STATUS_MISSING if required else _STATUS_WARN
        if date:
            return _STATUS_OK if parse_date(value) else (_STATUS_MISSING if required else _STATUS_WARN)
        if icd10 and not _looks_like_icd10_diagnosis(value):
            return _STATUS_MISSING if required else _STATUS_WARN
        if manual:
            return _STATUS_MANUAL
        return _STATUS_OK

    def upsert(key: str, label: str, value: str, *, required: bool, source: str, manual: bool = False, date: bool = False, icd10: bool = False) -> None:
        if not required:
            return
        for index, field in enumerate(fields):
            if field.key == key:
                next_value = field.value or value
                next_status = status(
                    next_value,
                    manual=manual or field.status == _STATUS_MANUAL,
                    required=True,
                    date=date,
                    icd10=icd10,
                )
                fields[index] = PatientCaseField(field.key, field.label, next_value, next_status, field.source or source, True)
                return
        fields.append(PatientCaseField(key, label, value, status(value, manual=manual, required=True, date=date, icd10=icd10), source, True))

    upsert("case_number", "Номер истории болезни", case_number, required=bool(custom_flags.get("requires_case_number")), source="custom-кнопка профиля", manual=manual_case_number)
    upsert("diagnosis", "Диагноз", diagnosis, required=bool(custom_flags.get("requires_diagnosis")), source="custom-кнопка профиля", manual=manual_diagnosis, icd10=True)
    upsert("treatment", "Лечение", treatment, required=bool(custom_flags.get("requires_treatment")), source="custom-кнопка профиля", manual=manual_treatment)
    upsert("discharge_date", "Дата выписки", discharge_date, required=bool(custom_flags.get("requires_discharge_date")), source="custom-кнопка профиля", manual=manual_discharge_date, date=True)
    labs_value = str(labs or "").strip()
    if not labs_value and labs_without:
        labs_value = "Нет анализов"
    upsert("labs", "Анализы", labs_value, required=bool(custom_flags.get("requires_labs")), source="custom-кнопка профиля", manual=bool(labs_value))
    return PatientCaseReview(tuple(fields), review.selected_outputs, review.output_dir, review.primary_path, review.warnings)

def expected_medical_filenames(review: PatientCaseReview, selected_medical: Sequence[str]) -> tuple[str, ...]:
    stem = review.patient_stem()
    names: list[str] = []
    for kind in selected_medical:
        suffix = OUTPUT_SUFFIXES.get(kind)
        if suffix:
            names.append(f"{stem} {suffix}.docx")
    return tuple(names)
