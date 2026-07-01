"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

from diagnostic_logging import record_soft_exception
import os
import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from medical_constants import DOCUMENT_LABELS, DOCUMENT_ORDER, OUTPUT_SUFFIXES
from medical_docx_reader import extract_docx_text
from medical_formatting import available_path, parse_date, safe_filename, strip_leading_epi_label
from medical_models import PatientData
from medical_parser import MedicalTextParser
from medical_paths import bundled_template_path
from medical_renderer import MedicalDocumentRenderer
from medical_formatting import redact_technical_text, technical_ref


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
    return normalized in {
        "",
        "нет",
        "не работает",
        "безработный",
        "безработная",
        "неработающий",
        "неработающая",
    }


def _ensure_word_compatible_for_service(path: Path) -> Path:
    if path.suffix.lower() != ".doc":
        return path
    try:
        from medical_docx_xml_fragments import ensure_docx_compatible
        return ensure_docx_compatible(path)
    except Exception as exc:
        raise ValueError("Файл .doc требует локального Microsoft Word/конвертера для чтения. Сохраните документ как .docx или установите Microsoft Word на этот компьютер.") from exc


def legacy_fixed_template_backend_enabled() -> bool:
    """Legacy fixed templates are opt-in only in the doctor-owned product model."""
    return os.environ.get("DOKKOMPLEKT_ENABLE_LEGACY_FIXED_TEMPLATES", "").strip().lower() in {"1", "true", "yes", "да"}


class MedicalDocumentService:
    def __init__(self):
        self.parser = MedicalTextParser()
        self.renderer = MedicalDocumentRenderer()

    def parse_primary_document(self, path: str | Path) -> PatientData:
        """Прочитать входной первичный документ пациента.

Поддерживаются оба рабочих источника данных:
- направление на госпитализацию;
- уже заполненный первичный осмотр.

Оба документа приводятся к единой PatientData, из которой затем создаются
все отмеченные в UI документы.
        """
        primary_path = self._existing_file(path, "первичный документ", allowed_suffixes=_PRIMARY_SUFFIXES)
        primary_path = _ensure_word_compatible_for_service(primary_path)
        return self.parser.parse_docx(primary_path)

    def parse_navigation(self, path: str | Path) -> PatientData:
        # Совместимость со старыми вызовами: раньше входной документ назывался
        # "направление". Теперь это общий первичный документ.
        return self.parse_primary_document(path)

    @staticmethod
    def _existing_file(
        path: str | Path | None,
        label: str,
        *,
        allowed_suffixes: set[str] | None = None,
    ) -> Path:
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
        """Read physician TXT snippets in UTF-8/UTF-8-BOM/Windows-1251.

        На Windows врач может сохранить ЭПИ/дополнительный текст в cp1251.
        Старое чтение через ``errors='ignore'`` могло тихо съедать кириллицу.
        """
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
        seen: set[str] = set()
        unknown: list[str] = []
        if selected_docs is None:
            selected_iterable: Sequence[str] = ()
        elif isinstance(selected_docs, str):
            selected_iterable = (selected_docs,)
        else:
            selected_iterable = selected_docs
        for raw_kind in selected_iterable:
            kind = str(raw_kind).strip()
            if not kind:
                continue
            # Public/service calls sometimes pass visible UI labels instead of
            # internal keys. Accepting labels keeps the boundary convenient while
            # still rejecting truly unknown values.
            kind = label_to_kind.get(kind, kind)
            if kind not in allowed:
                if kind not in unknown:
                    unknown.append(str(raw_kind).strip())
                continue
            if kind not in seen:
                seen.add(kind)
                normalized.append(kind)
        if unknown:
            labels = ", ".join(unknown)
            raise ValueError(f"Неизвестный тип медицинского документа: {labels}")
        if not normalized:
            raise ValueError("Не выбран ни один медицинский документ.")
        return tuple(normalized)

    @staticmethod
    def _resolve_output_dir(output_dir: str | Path | None, fallback_dir: Path) -> Path:
        if output_dir is None or str(output_dir).strip() == "":
            result = fallback_dir
        else:
            result = Path(output_dir).expanduser()
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
        """Protect service-boundary dates from impossible episode chronology."""
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


    @staticmethod
    def _normalize_required_date(value: str, label: str) -> str:
        value = str(value or "").strip()
        parsed = parse_date(value)
        if not parsed:
            raise ValueError(f"{label} должна быть в формате ДД.ММ.ГГГГ, ДД.ММ.ГГ, ДДММГГГГ, ДДММГГ или коротко ДМГГ.")
        return parsed.strftime("%d.%m.%Y")

    @staticmethod
    def _require_text(value: str, label: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"Не заполнено обязательное поле: {label}.")
        return normalized

    def _validate_and_normalize_selected_data(self, data: PatientData, selected: Sequence[str]) -> None:
        """Implement the _validate_and_normalize_selected_data workflow with validation, UI state updates and diagnostics."""
        selected_set = set(selected)

        # Service-layer is a hard boundary: direct programmatic calls must be as
        # safe as the UI path. Otherwise tests/automation can generate DOCX with
        # empty patient identity, missing history number or clinically impossible
        # dates even though the manual UI would have asked the doctor first.
        data.fio = self._require_core_text(data.fio, "Ф.И.О.")
        self._require_core_text(data.admission_date, "дата госпитализации")
        data.admission_date = self._normalize_required_date(data.admission_date, "Дата госпитализации")
        data.case_number = self._require_text(data.case_number, "номер истории болезни")
        data.diagnosis = self._require_text(data.diagnosis, "диагноз")

        treatment_docs = {"primary", "discharge", "commission", "vk_mse", "sick_leave_vk"}
        if selected_set & treatment_docs:
            data.treatment_plan = self._require_text(data.treatment_plan, "лечение")

        if {"discharge", "rvk"} & selected_set:
            data.discharge_date = self._normalize_required_date(data.discharge_date, "Дата выписки")
            self._ensure_discharge_not_before_admission(data.admission_date, data.discharge_date)

        expert_docs = {"primary", "discharge", "commission"}
        expert_sick_needed = self._infer_expert_sick_leave_needed(data)
        if expert_sick_needed:
            data.expert_sick_leave_needed = expert_sick_needed
        if expert_sick_needed == "да" and selected_set & expert_docs:
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
            data.vk_mse_work_position = combined or ", ".join(
                part for part in [data.vk_mse_work_org, data.vk_mse_position] if part
            )

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
            data.sick_leave_vk_work_position = data.sick_leave_vk_work_position or ", ".join(
                part for part in [data.sick_leave_vk_work_org, data.sick_leave_vk_position] if part
            )

        if "rvk" in selected_set:
            data.rvk_act_number = self._require_text(data.rvk_act_number, "номер медицинского заключения РВК")
            data.rvk_military_commissariat = self._require_text(data.rvk_military_commissariat, "военкомат для Акта РВК")


    def _normalize_available_selected_data(self, data: PatientData, selected: Sequence[str]) -> None:
        """Normalize dates that are present while allowing doctor-approved blanks."""
        if data.admission_date:
            data.admission_date = self._normalize_required_date(data.admission_date, "Дата госпитализации")
        if data.discharge_date:
            data.discharge_date = self._normalize_required_date(data.discharge_date, "Дата выписки")
        if data.admission_date and data.discharge_date:
            self._ensure_discharge_not_before_admission(data.admission_date, data.discharge_date)

    def load_epi_text(self, path: str | Path) -> str:
        if not path:
            return ""
        path = self._existing_file(path, "ЭПИ", allowed_suffixes=_EPI_DOCX_SUFFIXES | _EPI_TEXT_SUFFIXES)
        if path.suffix.lower() in _EPI_DOCX_SUFFIXES:
            text = extract_docx_text(_ensure_word_compatible_for_service(path))
        else:
            text = self._read_text_file(path)
        return strip_leading_epi_label(text)

    def available_templates(self) -> Dict[str, Path]:
        return {kind: bundled_template_path(kind) for kind in DOCUMENT_ORDER}

    def missing_templates(self) -> List[Path]:
        return [path for path in self.available_templates().values() if not path.exists()]

    def create_documents(
        self,
        *,
        navigation_path: str | Path,
        output_dir: str | Path | None,
        discharge_date: str = "",
        epi_path: str | Path | None = None,
        selected_docs: Sequence[str] | str | None = DOCUMENT_ORDER,
        override_data: Optional[PatientData] = None,
        allow_missing_required: bool = False,
    ) -> Tuple[List[Path], PatientData]:
        selected = self._normalize_selected_docs(selected_docs)
        primary_path = self._existing_file(navigation_path, "первичный документ", allowed_suffixes=_PRIMARY_SUFFIXES)
        primary_path = _ensure_word_compatible_for_service(primary_path)
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

        if not legacy_fixed_template_backend_enabled():
            raise RuntimeError("Старый fixed-template backend отключён по умолчанию. Используйте doctor-owned шаблоны/профиль документов или включите DOKKOMPLEKT_ENABLE_LEGACY_FIXED_TEMPLATES=1 только для совместимости.")
        template_paths = {kind: bundled_template_path(kind) for kind in selected}
        missing = [path for path in template_paths.values() if not path.exists()]
        if missing:
            missing_text = "\n".join(str(path) for path in missing)
            raise FileNotFoundError(f"Не найдены шаблоны старого фиксированного набора:\n{missing_text}")

        stem = safe_filename(data.output_fio or data.fio or primary_path.stem)

        created: List[Path] = []
        for kind in selected:
            template_path = template_paths[kind]
            suffix = OUTPUT_SUFFIXES[kind]
            output_path = available_path(output_path_root / f"{stem} {suffix}.docx")
            self.renderer.render(kind, template_path, output_path, data)
            created.append(output_path)
        return created, data


# --- Batch generation workflow ---
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
        lines = [
            "Пакетная обработка",
            f"Пациентов/файлов обработано: {self.patient_count}",
            f"Создано документов: {self.created_count}",
            f"Ошибок: {self.error_count}",
        ]
        if self.output_root:
            lines.append(f"Папка результата: {self.output_root}")
        if self.selected_docs:
            labels = [DOCUMENT_LABELS.get(kind, kind) for kind in self.selected_docs]
            lines.append("Документы: " + ", ".join(labels))
        if self.items:
            lines.append("")
            lines.append("Результаты:")
            lines.extend(item.human_line() for item in self.items)
        return "\n".join(lines)

    def technical_report(self) -> str:
        lines = [
            "Пакетная обработка — технический обезличенный отчёт",
            f"Пациентов/файлов обработано: {self.patient_count}",
            f"Создано документов: {self.created_count}",
            f"Ошибок: {self.error_count}",
        ]
        if self.output_root:
            lines.append("Папка результата: " + technical_ref(self.output_root))
        if self.selected_docs:
            labels = [DOCUMENT_LABELS.get(kind, kind) for kind in self.selected_docs]
            lines.append("Документы: " + ", ".join(labels))
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
    """Discover candidate primary DOC/DOCX/DOCM files for batch generation.

    Temporary Word files, profile templates and generated output/history folders
    are skipped so the doctor can safely choose a normal working folder without
    accidentally re-processing program artifacts.
    """
    root = Path(folder).expanduser()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Папка пакетной обработки не найдена: {root}")
    result: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("~$"):
            continue
        if path.suffix.lower() not in {".docx", ".docm", ".doc"}:
            continue
        if any(part.startswith("_medical_autofill_history") for part in path.parts):
            continue
        if any(part in {"profiles", "templates", "release"} for part in path.parts):
            continue
        probe_text = _safe_docx_probe_text(path)
        # A Word file with semantic placeholders is a template, not a patient's
        # primary document.  The old check skipped only some template filenames,
        # so custom templates with ordinary names could be re-processed in batch
        # mode and produce fake patient folders.
        if "{{" in probe_text and "}}" in probe_text:
            continue
        result.append(path)
    return tuple(result)


def create_documents_batch(
    *,
    primary_documents: Iterable[str | Path],
    output_root: str | Path,
    selected_docs: Sequence[str],
    discharge_date: str = "",
    epi_path: str | Path | None = None,
    service: MedicalDocumentService | None = None,
    patient_subfolders: bool = True,
    folder_naming_settings: object | None = None,
) -> BatchGenerationResult:
    """Legacy fixed-template batch backend kept only for compatibility.

    The production UI uses doctor-owned custom templates.  If somebody calls
    this old backend without providing the old fixed templates, it must fail
    clearly instead of pretending that bundled templates exist.  Every patient
    is still isolated into a separate result folder and errors remain per file.
    """
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
            created, used = svc.create_documents(
                navigation_path=source_path,
                output_dir=patient_dir,
                discharge_date=normalized_discharge,
                epi_path=epi_path,
                selected_docs=selected,
                override_data=patient,
            )
            items.append(BatchItemResult(str(source_path), used.output_fio or used.fio or source_path.stem, str(patient_dir), tuple(str(path) for path in created), ""))
        except Exception as exc:
            items.append(BatchItemResult(str(source_path), patient_label, patient_dir_text, (), str(exc)))
    return BatchGenerationResult(tuple(items), str(output_root), tuple(selected))


def _batch_patient_dir_name(patient: PatientData, source_path: Path, folder_naming_settings: object | None = None) -> str:
    from desktop_patient_folder import build_patient_folder_name

    name = build_patient_folder_name(
        fio=patient.output_fio or patient.fio,
        admission_date=patient.admission_date,
        discharge_date=patient.discharge_date,
        settings=folder_naming_settings,
        fallback=source_path.stem,
    )
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
