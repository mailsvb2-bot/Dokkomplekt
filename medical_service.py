"""Medical document service boundary for primary parsing and legacy batch generation."""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from diagnostic_logging import record_soft_exception
from medical_constants import DOCUMENT_LABELS, DOCUMENT_ORDER, OUTPUT_SUFFIXES
from medical_docx_reader import extract_docx_text
from medical_formatting import available_path, parse_date, redact_technical_text, safe_filename, strip_leading_epi_label, technical_ref
from medical_models import PatientData
from medical_parser import MedicalTextParser
from medical_paths import bundled_template_path
from medical_renderer import MedicalDocumentRenderer

_TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "cp1251")
_PRIMARY_SUFFIXES = {".docx", ".docm", ".doc"}
_EPI_TEXT_SUFFIXES = {".txt"}
_EPI_DOCX_SUFFIXES = {".docx", ".docm", ".doc"}


def _normalize_yes_no_text(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("ё", "е")
    if normalized in {"да", "д", "yes", "y", "1", "+", "нужен", "нужна", "нужно", "работает"}:
        return "да"
    if normalized in {"нет", "н", "no", "n", "0", "-", "не нужен", "не нужна", "не нужно", "не работает"}:
        return "нет"
    return ""


def _not_working_value(value: str) -> bool:
    normalized = " ".join(str(value or "").strip().lower().replace("ё", "е").split())
    return normalized in {"", "нет", "не работает", "безработный", "безработная", "неработающий", "неработающая"}


def _ensure_word_compatible_for_service(path: Path) -> Path:
    if path.suffix.lower() != ".doc":
        return path
    try:
        from medical_docx_xml_fragments import ensure_docx_compatible
        return ensure_docx_compatible(path)
    except Exception as exc:
        raise ValueError("Файл .doc требует локального Microsoft Word/конвертера для чтения. Сохраните документ как .docx или установите Microsoft Word на этот компьютер.") from exc


def legacy_fixed_template_backend_enabled() -> bool:
    return os.environ.get("DOKKOMPLEKT_ENABLE_LEGACY_FIXED_TEMPLATES", "").strip().lower() in {"1", "true", "yes", "да"}


class MedicalDocumentService:
    def __init__(self):
        self.parser = MedicalTextParser()
        self.renderer = MedicalDocumentRenderer()

    def parse_primary_document(self, path: str | Path) -> PatientData:
        primary_path = self._existing_file(path, "первичный документ", allowed_suffixes=_PRIMARY_SUFFIXES)
        return self.parser.parse_docx(_ensure_word_compatible_for_service(primary_path))

    def parse_navigation(self, path: str | Path) -> PatientData:
        return self.parse_primary_document(path)

    @staticmethod
    def _existing_file(path: str | Path | None, label: str, *, allowed_suffixes: set[str] | None = None) -> Path:
        if path is None or str(path).strip() == "":
            raise ValueError(f"Не выбран файл: {label}.")
        candidate = Path(path).expanduser()
        if not candidate.exists() or not candidate.is_file():
            raise FileNotFoundError(f"Не найден файл ({label}): {candidate}")
        if allowed_suffixes is not None and candidate.suffix.lower() not in allowed_suffixes:
            allowed_text = ", ".join(sorted(allowed_suffixes))
            raise ValueError(f"Неверный формат файла ({label}): {candidate.suffix or 'без расширения'}. Разрешено: {allowed_text}.")
        return candidate

    @staticmethod
    def _read_text_file(path: Path) -> str:
        raw = path.read_bytes()
        for encoding in _TEXT_ENCODINGS:
            try:
                return raw.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace").strip()

    @staticmethod
    def _normalize_selected_docs(selected_docs: Sequence[str] | str | None) -> tuple[str, ...]:
        allowed = set(DOCUMENT_ORDER)
        label_to_kind = {label: kind for kind, label in DOCUMENT_LABELS.items()}
        normalized: list[str] = []
        unknown: list[str] = []
        seen: set[str] = set()
        selected_iterable: Sequence[str]
        if selected_docs is None:
            selected_iterable = ()
        elif isinstance(selected_docs, str):
            selected_iterable = (selected_docs,)
        else:
            selected_iterable = selected_docs
        for raw_kind in selected_iterable:
            kind = str(raw_kind).strip()
            if not kind:
                continue
            kind = label_to_kind.get(kind, kind)
            if kind not in allowed:
                if kind not in unknown:
                    unknown.append(str(raw_kind).strip())
                continue
            if kind not in seen:
                seen.add(kind)
                normalized.append(kind)
        if unknown:
            raise ValueError("Неизвестный тип медицинского документа: " + ", ".join(unknown))
        if not normalized:
            raise ValueError("Не выбран ни один медицинский документ.")
        return tuple(normalized)

    @staticmethod
    def _resolve_output_dir(output_dir: str | Path | None, fallback_dir: Path) -> Path:
        result = fallback_dir if output_dir is None or str(output_dir).strip() == "" else Path(output_dir).expanduser()
        if result.exists() and not result.is_dir():
            raise ValueError(f"Папка результата указывает на файл, а не на папку: {result}")
        result.mkdir(parents=True, exist_ok=True)
        return result

    @staticmethod
    def _normalize_discharge_date(value: str) -> str:
        value = str(value or "").strip()
        if not value:
            return ""
        parsed = parse_date(value)
        if not parsed:
            raise ValueError("Дата выписки должна быть в формате ДД.ММ.ГГГГ, ДД.ММ.ГГ, ДДММГГГГ, ДДММГГ или ДМГГ.")
        return parsed.strftime("%d.%m.%Y")

    @staticmethod
    def _ensure_discharge_not_before_admission(admission_date: str, discharge_date: str) -> None:
        if not admission_date or not discharge_date:
            return
        admission = parse_date(admission_date)
        discharge = parse_date(discharge_date)
        if admission and discharge and discharge.date() < admission.date():
            raise ValueError("Дата выписки не может быть раньше даты госпитализации.")

    @staticmethod
    def _ensure_date_not_before_admission(admission_date: str, value: str, label: str) -> None:
        if not admission_date or not value:
            return
        admission = parse_date(admission_date)
        parsed = parse_date(value)
        if admission and parsed and parsed.date() < admission.date():
            raise ValueError(f"{label} не может быть раньше даты госпитализации.")

    @staticmethod
    def _require_core_text(value: str, label: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"Не найдено обязательное поле пациента: {label}.")
        return normalized

    @staticmethod
    def _require_text(value: str, label: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"Не заполнено обязательное поле: {label}.")
        return normalized

    @staticmethod
    def _normalize_required_date(value: str, label: str) -> str:
        parsed = parse_date(str(value or "").strip())
        if not parsed:
            raise ValueError(f"{label} должна быть в формате ДД.ММ.ГГГГ, ДД.ММ.ГГ, ДДММГГГГ, ДДММГГ или коротко ДМГГ.")
        return parsed.strftime("%d.%m.%Y")

    @staticmethod
    def _normalize_work_text(value: str) -> str:
        return str(value or "").strip().strip(" ,.;:")

    @staticmethod
    def _infer_expert_sick_leave_needed(data: PatientData) -> str:
        explicit = _normalize_yes_no_text(data.expert_sick_leave_needed)
        if explicit:
            return explicit
        raw = str(data.sick_leave or "").strip().lower().replace("ё", "е")
        if not raw:
            return ""
        if "не нуж" in raw or raw == "нет":
            return "нет"
        if "нуж" in raw or "лн" in raw or "больнич" in raw:
            return "да"
        return ""

    def _validate_and_normalize_selected_data(self, data: PatientData, selected: Sequence[str]) -> None:
        selected_set = set(selected)
        data.fio = self._require_core_text(data.fio, "Ф.И.О.")
        self._require_core_text(data.admission_date, "дата госпитализации")
        data.admission_date = self._normalize_required_date(data.admission_date, "Дата госпитализации")
        data.case_number = self._require_text(data.case_number, "номер истории болезни")
        data.diagnosis = self._require_text(data.diagnosis, "диагноз")
        if selected_set & {"primary", "discharge", "commission", "vk_mse", "sick_leave_vk"}:
            data.treatment_plan = self._require_text(data.treatment_plan, "лечение")
        if {"discharge", "rvk"} & selected_set:
            data.discharge_date = self._normalize_required_date(data.discharge_date, "Дата выписки")
            self._ensure_discharge_not_before_admission(data.admission_date, data.discharge_date)
        expert_sick_needed = self._infer_expert_sick_leave_needed(data)
        if expert_sick_needed:
            data.expert_sick_leave_needed = expert_sick_needed
        if expert_sick_needed == "да" and selected_set & {"primary", "discharge", "commission"}:
            data.expert_sick_leave_from = self._normalize_required_date(data.expert_sick_leave_from, "Дата начала больничного")
            self._ensure_date_not_before_admission(data.admission_date, data.expert_sick_leave_from, "Дата начала больничного")
            data.expert_work_org = self._normalize_work_text(data.expert_work_org or data.work_org)
            data.expert_position = self._normalize_work_text(data.expert_position or data.position)
            data.expert_work_status = "да"
            data.work_org = data.expert_work_org or data.work_org
            data.position = data.expert_position or data.position
            data.expert_work_org = self._require_text(data.expert_work_org, "организация для больничного листа")
            data.expert_position = self._require_text(data.expert_position, "должность для больничного листа")
            if "discharge" in selected_set:
                data.expert_sick_leave_number = self._require_text(data.expert_sick_leave_number, "номер больничного листа")
        if "commission" in selected_set:
            data.commission_date = self._normalize_required_date(data.commission_date, "Дата совместного осмотра")
            self._ensure_date_not_before_admission(data.admission_date, data.commission_date, "Дата совместного осмотра")
            data.commission_number = self._require_text(data.commission_number, "номер совместного осмотра")
        if "vk_mse" in selected_set:
            data.vk_date = self._normalize_required_date(data.vk_date, "Дата ВК на МСЭ")
            self._ensure_date_not_before_admission(data.admission_date, data.vk_date, "Дата ВК на МСЭ")
            data.vk_protocol_number = self._require_text(data.vk_protocol_number, "номер протокола ВК на МСЭ")
            data.vk_protocol_date = self._normalize_required_date(data.vk_protocol_date, "Дата протокола ВК на МСЭ")
            self._ensure_date_not_before_admission(data.admission_date, data.vk_protocol_date, "Дата протокола ВК на МСЭ")
            data.vk_mse_work_org = (data.vk_mse_work_org or data.work_org or "не работает").strip()
            data.vk_mse_position = (data.vk_mse_position or data.position).strip()
            combined = str(getattr(data, "vk_mse_work_position", "") or "").strip()
            if not _not_working_value(data.vk_mse_work_org) and not (data.vk_mse_position or combined):
                data.vk_mse_position = self._require_text(data.vk_mse_position, "должность для ВК на МСЭ")
            data.vk_mse_work_position = combined or ", ".join(part for part in [data.vk_mse_work_org, data.vk_mse_position] if part)
        if "sick_leave_vk" in selected_set:
            data.sick_leave_vk_date = self._normalize_required_date(data.sick_leave_vk_date, "Дата ВК больничного")
            self._ensure_date_not_before_admission(data.admission_date, data.sick_leave_vk_date, "Дата ВК больничного")
            data.sick_leave_vk_protocol_number = self._require_text(data.sick_leave_vk_protocol_number, "номер протокола ВК больничного")
            data.sick_leave_vk_protocol_date = self._normalize_required_date(data.sick_leave_vk_protocol_date, "Дата протокола ВК больничного")
            self._ensure_date_not_before_admission(data.admission_date, data.sick_leave_vk_protocol_date, "Дата протокола ВК больничного")
            data.sick_leave_vk_commission_date = self._normalize_required_date(data.sick_leave_vk_commission_date, "Дата проведения комиссии ВК больничного")
            self._ensure_date_not_before_admission(data.admission_date, data.sick_leave_vk_commission_date, "Дата проведения комиссии ВК больничного")
            data.sick_leave_vk_work_org = (data.sick_leave_vk_work_org or data.work_org or "не работает").strip()
            data.sick_leave_vk_position = (data.sick_leave_vk_position or data.position).strip()
            data.sick_leave_vk_work_position = data.sick_leave_vk_work_position or ", ".join(part for part in [data.sick_leave_vk_work_org, data.sick_leave_vk_position] if part)
        if "rvk" in selected_set:
            data.rvk_act_number = self._require_text(data.rvk_act_number, "номер медицинского заключения РВК")
            data.rvk_military_commissariat = self._require_text(data.rvk_military_commissariat, "военкомат для Акта РВК")

    def _normalize_available_selected_data(self, data: PatientData, selected: Sequence[str]) -> None:
        if data.admission_date:
            data.admission_date = self._normalize_required_date(data.admission_date, "Дата госпитализации")
        if data.discharge_date:
            data.discharge_date = self._normalize_required_date(data.discharge_date, "Дата выписки")
        if data.admission_date and data.discharge_date:
            self._ensure_discharge_not_before_admission(data.admission_date, data.discharge_date)

    def load_epi_text(self, path: str | Path) -> str:
        if not path:
            return ""
        target = self._existing_file(path, "ЭПИ", allowed_suffixes=_EPI_DOCX_SUFFIXES | _EPI_TEXT_SUFFIXES)
        if target.suffix.lower() in _EPI_DOCX_SUFFIXES:
            return strip_leading_epi_label(extract_docx_text(_ensure_word_compatible_for_service(target)))
        return strip_leading_epi_label(self._read_text_file(target))

    def available_templates(self) -> Dict[str, Path]:
        return {kind: bundled_template_path(kind) for kind in DOCUMENT_ORDER}

    def missing_templates(self) -> List[Path]:
        return [path for path in self.available_templates().values() if not path.exists()]

    def create_documents(self, *, navigation_path: str | Path, output_dir: str | Path | None, discharge_date: str = "", epi_path: str | Path | None = None, selected_docs: Sequence[str] | str | None = DOCUMENT_ORDER, override_data: Optional[PatientData] = None, allow_missing_required: bool = False) -> Tuple[List[Path], PatientData]:
        selected = self._normalize_selected_docs(selected_docs)
        primary_path = _ensure_word_compatible_for_service(self._existing_file(navigation_path, "первичный документ", allowed_suffixes=_PRIMARY_SUFFIXES))
        normalized_discharge_date = self._normalize_discharge_date(discharge_date)
        data = copy.deepcopy(override_data) if override_data is not None else self.parse_primary_document(primary_path)
        data.discharge_date = normalized_discharge_date or data.discharge_date
        self._ensure_discharge_not_before_admission(data.admission_date, data.discharge_date)
        if epi_path:
            data.epi_text = self.load_epi_text(epi_path)
        if allow_missing_required:
            self._normalize_available_selected_data(data, selected)
        else:
            self._validate_and_normalize_selected_data(data, selected)
        output_path_root = self._resolve_output_dir(output_dir, primary_path.parent)
        template_paths = {kind: bundled_template_path(kind) for kind in selected}
        if not legacy_fixed_template_backend_enabled():
            missing_text = "\n".join(str(path) for path in template_paths.values())
            raise FileNotFoundError("Не найдены шаблоны старого фиксированного набора. Старый fixed-template backend отключён по умолчанию; используйте doctor-owned шаблоны/профиль документов или включите DOKKOMPLEKT_ENABLE_LEGACY_FIXED_TEMPLATES=1 только для совместимости.\n" + missing_text)
        missing = [path for path in template_paths.values() if not path.exists()]
        if missing:
            missing_text = "\n".join(str(path) for path in missing)
            raise FileNotFoundError(f"Не найдены шаблоны старого фиксированного набора:\n{missing_text}")
        stem = safe_filename(data.output_fio or data.fio or primary_path.stem)
        created: List[Path] = []
        for kind in selected:
            output_path = available_path(output_path_root / f"{stem} {OUTPUT_SUFFIXES[kind]}.docx")
            self.renderer.render(kind, template_paths[kind], output_path, data)
            created.append(output_path)
        return created, data


@dataclass(frozen=True)
class BatchItemResult:
    source: str
    patient_label: str = ""
    output_dir: str = ""
    created_files: tuple[str, ...] = ()
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    def human_line(self) -> str:
        name = self.patient_label or Path(self.source).stem
        suffix = f" → {self.output_dir}" if self.output_dir else ""
        if self.ok:
            return f"✅ {name}: создано файлов — {len(self.created_files)}{suffix}"
        return f"❌ {name}{suffix}: {self.error}"

    def technical_line(self) -> str:
        ref = technical_ref(self.source, self.patient_label, self.output_dir)
        if self.ok:
            return f"✅ {ref}: создано файлов — {len(self.created_files)}"
        return f"❌ {ref}: {redact_technical_text(self.error)}"


@dataclass(frozen=True)
class BatchGenerationResult:
    items: tuple[BatchItemResult, ...] = field(default_factory=tuple)
    output_root: str = ""
    selected_docs: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.error_count == 0

    @property
    def patient_count(self) -> int:
        return len(self.items)

    @property
    def created_count(self) -> int:
        return sum(len(item.created_files) for item in self.items)

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.items if item.error)

    def human_report(self) -> str:
        lines = ["Пакетная обработка", f"Пациентов/файлов обработано: {self.patient_count}", f"Создано документов: {self.created_count}", f"Ошибок: {self.error_count}"]
        if self.output_root:
            lines.append(f"Папка результата: {self.output_root}")
        if self.selected_docs:
            lines.append("Документы: " + ", ".join(DOCUMENT_LABELS.get(kind, kind) for kind in self.selected_docs))
        if self.items:
            lines.append("")
            lines.append("Результаты:")
            lines.extend(item.human_line() for item in self.items)
        return "\n".join(lines)

    def technical_report(self) -> str:
        lines = ["Пакетная обработка — технический обезличенный отчёт", f"Пациентов/файлов обработано: {self.patient_count}", f"Создано документов: {self.created_count}", f"Ошибок: {self.error_count}"]
        if self.output_root:
            lines.append("Папка результата: " + technical_ref(self.output_root))
        if self.selected_docs:
            lines.append("Документы: " + ", ".join(DOCUMENT_LABELS.get(kind, kind) for kind in self.selected_docs))
        if self.items:
            lines.append("")
            lines.append("Результаты:")
            lines.extend(item.technical_line() for item in self.items)
        return "\n".join(lines)


def save_batch_generation_report(result: BatchGenerationResult, path: str | Path) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target = available_path(target)
    target.write_text(result.technical_report() + "\n", encoding="utf-8")
    return target


def discover_primary_documents(folder: str | Path) -> tuple[Path, ...]:
    root = Path(folder).expanduser()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Папка пакетной обработки не найдена: {root}")
    result: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("~$"):
            continue
        if path.suffix.lower() not in {".docx", ".docm", ".doc"}:
            continue
        if any(part.startswith("_medical_autofill_history") for part in path.parts):
            continue
        if any(part in {"profiles", "templates", "release"} for part in path.parts):
            continue
        probe_text = _safe_docx_probe_text(path)
        if "{{" in probe_text and "}}" in probe_text:
            continue
        result.append(path)
    return tuple(result)


def create_documents_batch(*, primary_documents: Iterable[str | Path], output_root: str | Path, selected_docs: Sequence[str], discharge_date: str = "", epi_path: str | Path | None = None, service: MedicalDocumentService | None = None, patient_subfolders: bool = True, folder_naming_settings: object | None = None) -> BatchGenerationResult:
    svc = service or MedicalDocumentService()
    selected = svc._normalize_selected_docs(selected_docs)
    normalized_discharge = svc._normalize_discharge_date(discharge_date) if str(discharge_date or "").strip() else ""
    output_root = Path(output_root).expanduser()
    if output_root.exists() and not output_root.is_dir():
        raise ValueError(f"Папка результата указывает на файл, а не на папку: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    normalized_sources: list[Path] = []
    seen_sources: set[Path] = set()
    for source in primary_documents:
        source_path = Path(source).expanduser()
        try:
            resolved = source_path.resolve()
        except Exception as exc:
            record_soft_exception("medical_service.source_resolve", exc, detail=str(source_path))
            resolved = source_path.absolute()
        if resolved in seen_sources:
            continue
        seen_sources.add(resolved)
        normalized_sources.append(source_path)
    if not normalized_sources:
        raise ValueError("В пакетной обработке нет ни одного первичного DOC/DOCX/DOCM документа пациента.")
    items: list[BatchItemResult] = []
    for source_path in normalized_sources:
        patient_label = source_path.stem
        patient_dir_text = ""
        try:
            patient = svc.parse_primary_document(source_path)
            if normalized_discharge:
                patient.discharge_date = normalized_discharge
            patient_label = patient.output_fio or patient.fio or source_path.stem
            patient_dir_name = _batch_patient_dir_name(patient, source_path, folder_naming_settings)
            patient_dir = output_root / patient_dir_name if patient_subfolders else output_root
            patient_dir_text = str(patient_dir)
            created, used = svc.create_documents(navigation_path=source_path, output_dir=patient_dir, discharge_date=normalized_discharge, epi_path=epi_path, selected_docs=selected, override_data=patient)
            items.append(BatchItemResult(str(source_path), used.output_fio or used.fio or source_path.stem, str(patient_dir), tuple(str(path) for path in created), ""))
        except Exception as exc:
            items.append(BatchItemResult(str(source_path), patient_label, patient_dir_text, (), str(exc)))
    return BatchGenerationResult(tuple(items), str(output_root), tuple(selected))


def _batch_patient_dir_name(patient: PatientData, source_path: Path, folder_naming_settings: object | None = None) -> str:
    from desktop_patient_folder import build_patient_folder_name

    name = build_patient_folder_name(fio=patient.output_fio or patient.fio, admission_date=patient.admission_date, discharge_date=patient.discharge_date, settings=folder_naming_settings, fallback=source_path.stem)
    case_number = str(patient.case_number or "").strip().strip("№ ")
    if case_number and case_number not in name:
        name = f"{name} история {case_number}" if name else f"история {case_number}"
    return safe_filename(name) or safe_filename(source_path.stem) or "patient"


def _safe_docx_probe_text(path: Path) -> str:
    try:
        return extract_docx_text(_ensure_word_compatible_for_service(path))[:2000]
    except Exception as exc:
        record_soft_exception("medical_service.safe_docx_probe", exc, detail=str(path))
        return ""
