"""Desktop intake folder helpers."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import time
from typing import Mapping

from diagnostic_logging import record_soft_exception
from medical_docx_reader import extract_docx_text
from medical_formatting import available_path, safe_filename

DESKTOP_INTAKE_LOCK_VERSION = "v1.15"
PRIMARY_FILE_QUIET_SECONDS = 1.5
DESKTOP_INTAKE_SETUP_PROMPT_VERSION = "v5-intake-critical-path"
DESKTOP_INTAKE_FOLDER_NAME = "Выписанные пациенты"
DESKTOP_INTAKE_REQUIRES_RUNNING_APP = False
DESKTOP_INTAKE_BACKGROUND_AGENT_SUPPORTED = True
DESKTOP_INTAKE_SCANS_TOP_LEVEL_ONLY = True
DESKTOP_INTAKE_VALIDATES_PRIMARY_DOCUMENT_ROLE = True
DESKTOP_INTAKE_CREATES_PATIENT_FOLDER_AFTER_SELECTION = True
DESKTOP_INTAKE_MOVES_PRIMARY_INTO_PATIENT_FOLDER = True
DESKTOP_INTAKE_PATIENT_FOLDER_USES_PRIMARY_DATA = True
DESKTOP_INTAKE_REASKS_ON_FEATURE_UPGRADE = True
DESKTOP_INTAKE_IGNORES_WORD_TEMP_FILES = True
DESKTOP_INTAKE_REUSES_EXISTING_CASE_INSENSITIVE_FOLDER = True
DESKTOP_INTAKE_USES_ROLE_SCORE_CLASSIFIER = True
DESKTOP_INTAKE_COPY_FALLBACK_RETURNS_PATIENT_COPY = True
DESKTOP_INTAKE_DOES_NOT_TRUST_GENERIC_HOSPITALIZATION_WORD = True
DESKTOP_INTAKE_SEEN_SIGNATURES_ARE_HASHED = True
DESKTOP_INTAKE_SEEN_SIGNATURES_ARE_PERSISTABLE = True
DESKTOP_INTAKE_USES_WINDOWS_DESKTOP_REGISTRY = True
DESKTOP_INTAKE_MOVE_FAILURE_IS_VISIBLE = True
DESKTOP_INTAKE_NORMALIZES_LEGACY_BOOL_STRINGS = True
DESKTOP_INTAKE_FIRST_LAUNCH_PROMPT_IS_MANDATORY = True
DESKTOP_INTAKE_REASKS_OLD_V2_PROMPT_SETTINGS = True
DESKTOP_INTAKE_MISSING_ENABLED_FOLDER_REASKS = True
DESKTOP_INTAKE_IGNORES_HIDDEN_DOT_FILES = True
DESKTOP_INTAKE_COPY_FALLBACK_TRIES_TO_UNLINK_SOURCE = True
DESKTOP_INTAKE_RELAXED_PRIMARY_THRESHOLD_FOR_DOCTOR_FOLDER = True
DESKTOP_INTAKE_TOP_LEVEL_DOCX_DROP_STARTS_APP = True
DESKTOP_INTAKE_REJECTS_UNREADABLE_DOCX_FALLBACKS = True
DESKTOP_INTAKE_REASKS_AFTER_FOLDER_NAMING_REGRESSION = True
DESKTOP_INTAKE_SUPPORTS_SAME_WORD_FORMATS_AS_MANUAL_FLOW = True
DESKTOP_INTAKE_EXACT_CONTENT_DEDUP_PRECEDES_METADATA = True
DESKTOP_INTAKE_PRIORITY_USES_ROLE_SCORE = True
DESKTOP_INTAKE_PERSISTS_BACKGROUND_AGENT_READINESS = True
DESKTOP_INTAKE_MAX_SEEN_SIGNATURES = 1000

_ALLOWED_PRIMARY_SUFFIXES = {".docx", ".docm", ".doc"}
_EXCLUDED_DOCUMENT_MARKERS = (
    "выписной эпикриз",
    "переводной эпикриз",
    "протокол операции",
    "операционный протокол",
    "информированное согласие",
    "консультационное заключение",
)


@dataclass(frozen=True)
class DesktopCandidate:
    path: Path
    signature: tuple[int, int]


def primary_document_score(text: str) -> int:
    """Score whether Word text is a primary intake source."""

    low = (text or "").lower().replace("ё", "е")
    if not low.strip():
        return 0
    negative = sum(5 for marker in _EXCLUDED_DOCUMENT_MARKERS if marker in low)
    strong_markers = (
        "первичный осмотр",
        "первинний огляд",
        "осмотр врача приемного покоя",
        "осмотр врача приёмного покоя",
        "направление на госпитализацию",
    )
    identity_markers = (
        "ф.и.о", "фио", "фамилия имя отчество", "пациент", "больной", "больная",
        "история болезни", "номер истории",
    )
    admission_markers = (
        "дата поступления", "дата госпитализации", "поступил", "поступила",
        "поступает", "госпитализирован", "госпитализирована",
    )
    clinical_markers = (
        "диагноз", "жалобы", "анамнез", "объективный статус",
        "соматический статус", "план лечения",
    )
    score = 6 * sum(1 for marker in strong_markers if marker in low)
    score += 2 * sum(1 for marker in identity_markers if marker in low)
    score += 3 * sum(1 for marker in admission_markers if marker in low)
    score += sum(1 for marker in clinical_markers if marker in low)
    if "госпитализац" in low and not any(marker in low for marker in admission_markers + strong_markers):
        score -= 2
    return max(0, score - negative)


def _desktop_from_windows_registry() -> Path | None:
    if os.name != "nt":
        return None
    try:
        import winreg  # type: ignore[import-not-found]
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        ) as key:
            raw, _kind = winreg.QueryValueEx(key, "Desktop")
        candidate = Path(os.path.expandvars(str(raw))).expanduser()
        if candidate.exists() and candidate.is_dir():
            return candidate
    except Exception as exc:
        record_soft_exception("desktop_intake.windows_desktop_registry", exc)
    return None


def desktop_path() -> Path:
    registry_desktop = _desktop_from_windows_registry()
    if registry_desktop is not None:
        return registry_desktop
    home = Path.home()
    candidates: list[Path] = []

    def add_base(raw: str | None) -> None:
        if not raw:
            return
        try:
            base = Path(raw).expanduser()
        except Exception as exc:
            record_soft_exception("desktop_intake.userprofile_expand", exc, detail=raw)
            return
        candidates.extend((base / "Desktop", base / "Рабочий стол"))

    for key in ("OneDriveCommercial", "OneDriveConsumer", "OneDrive", "USERPROFILE"):
        add_base(os.environ.get(key))
    candidates.extend((home / "Desktop", home / "Рабочий стол"))
    seen: set[str] = set()
    for candidate in candidates:
        try:
            marker = str(candidate.resolve())
        except Exception as exc:
            record_soft_exception("desktop_intake.resolve_desktop_candidate", exc, detail=str(candidate))
            marker = str(candidate)
        if marker in seen:
            continue
        seen.add(marker)
        if candidate.exists() and candidate.is_dir():
            return candidate
    return home / "Desktop"


def default_intake_folder() -> Path:
    return _existing_intake_folder_on_desktop() or (desktop_path() / DESKTOP_INTAKE_FOLDER_NAME)


def prompt_intake_folder(saved_folder: str | Path | None = None) -> Path:
    if saved_folder:
        try:
            candidate = Path(saved_folder).expanduser()
            if candidate.exists() and candidate.is_dir() and candidate.name.casefold() == DESKTOP_INTAKE_FOLDER_NAME.casefold():
                return candidate
        except Exception as exc:
            record_soft_exception("desktop_intake.prompt_intake_folder.saved_folder", exc, detail=str(saved_folder))
    return default_intake_folder()


def _existing_intake_folder_on_desktop() -> Path | None:
    root = desktop_path()
    target = DESKTOP_INTAKE_FOLDER_NAME.casefold()
    try:
        for child in root.iterdir():
            if child.is_dir() and child.name.casefold() == target:
                return child
    except Exception as exc:
        record_soft_exception("desktop_intake.existing_intake_folder_on_desktop", exc, detail=str(root))
    return None


def _is_ignored_candidate_name(path: str | Path) -> bool:
    name = Path(path).name
    return name.startswith("~$") or name.startswith(".")


def _is_supported_intake_document_name(path: str | Path) -> bool:
    candidate = Path(path)
    return candidate.suffix.lower() in _ALLOWED_PRIMARY_SUFFIXES and not _is_ignored_candidate_name(candidate)


def _setting_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"", "0", "false", "no", "off", "нет", "не", "n", "disabled", "disable"}:
            return False
        if lowered in {"1", "true", "yes", "on", "да", "y", "enabled", "enable"}:
            return True
    return bool(value)


def is_desktop_intake_folder_path(path: str | Path) -> bool:
    try:
        return Path(path).expanduser().name.casefold() == DESKTOP_INTAKE_FOLDER_NAME.casefold()
    except Exception as exc:
        record_soft_exception("desktop_intake.folder_path_check", exc, detail=str(path))
        return False


def normalize_intake_settings(raw: Mapping[str, object] | None) -> dict:
    data = dict(raw or {}) if isinstance(raw, Mapping) else {}
    folder = str(data.get("folder", "") or "").strip() or str(default_intake_folder())
    prompt_version = str(data.get("prompt_version", "") or "").strip()
    raw_seen = data.get("seen_signatures", ())
    seen: list[str] = []
    if isinstance(raw_seen, (list, tuple, set)):
        for item in raw_seen:
            value = str(item or "").strip()
            if len(value) == 64 and all(ch in "0123456789abcdef" for ch in value.lower()):
                seen.append(value.lower())
    return {
        "asked": _setting_bool(data.get("asked", False)),
        "enabled": _setting_bool(data.get("enabled", False)),
        "background_agent_ready": _setting_bool(data.get("background_agent_ready", False)),
        "folder": folder,
        "prompt_version": prompt_version,
        "seen_signatures": tuple(dict.fromkeys(seen))[-DESKTOP_INTAKE_MAX_SEEN_SIGNATURES:],
    }


def should_prompt_intake_setup(settings: Mapping[str, object] | None) -> bool:
    normalized = normalize_intake_settings(settings)
    folder = Path(str(normalized["folder"])).expanduser()
    enabled = bool(normalized["enabled"])
    asked = bool(normalized["asked"])
    prompt_version = str(normalized.get("prompt_version", "") or "")
    folder_ready = folder.exists() and folder.is_dir() and is_desktop_intake_folder_path(folder)
    if enabled and folder_ready and prompt_version == DESKTOP_INTAKE_SETUP_PROMPT_VERSION:
        return False
    if not asked or prompt_version != DESKTOP_INTAKE_SETUP_PROMPT_VERSION:
        return True
    if enabled and not folder_ready:
        return True
    return False


def _available_dir(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.exists():
        return candidate
    parent = candidate.parent
    stem = candidate.name.rstrip(" .") or "Patient"
    index = 2
    while True:
        next_candidate = parent / f"{stem} ({index})"
        if not next_candidate.exists():
            return next_candidate
        index += 1


def _file_content_digest(path: str | Path) -> str:
    candidate = Path(path).expanduser()
    digest = hashlib.sha256()
    with candidate.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _same_patient_existing_folder(candidate: Path, primary_path: str | Path) -> bool:
    """Reuse only a proven same episode; exact content is the strongest proof."""
    if not candidate.exists() or not candidate.is_dir():
        return False
    try:
        from desktop_patient_folder import build_patient_folder_info
        source_info = build_patient_folder_info(primary_path)
        source_fio = " ".join(source_info.fio.casefold().replace("ё", "е").split())
        source_date = source_info.admission_date.strip()
        source_digest = _file_content_digest(primary_path)
        for doc in candidate.iterdir():
            if not doc.is_file() or doc.suffix.lower() not in _ALLOWED_PRIMARY_SUFFIXES:
                continue
            try:
                existing_digest = _file_content_digest(doc)
                if existing_digest == source_digest:
                    return True
                info = build_patient_folder_info(doc)
            except Exception as exc:
                record_soft_exception("desktop_intake.same_patient_existing_document", exc, detail=str(doc))
                continue
            fio = " ".join(info.fio.casefold().replace("ё", "е").split())
            existing_date = info.admission_date.strip()
            if source_fio and fio and fio != source_fio:
                continue
            if source_date and existing_date and source_fio and fio and source_date == existing_date:
                return True
    except Exception as exc:
        record_soft_exception("desktop_intake.same_patient_folder", exc, detail=str(candidate))
    return False


def safe_patient_subfolder(folder: str | Path, primary_path: str | Path, folder_name: str | None = None) -> Path:
    if folder_name is None:
        try:
            from desktop_patient_folder import build_patient_folder_info
            folder_name = build_patient_folder_info(primary_path).folder_name
        except Exception as exc:
            record_soft_exception("desktop_intake.patient_folder_info", exc, detail=str(primary_path))
            folder_name = ""
    name = safe_filename((folder_name or Path(primary_path).stem)).strip(" .") or "Пациент"
    candidate = Path(folder).expanduser() / name
    if _same_patient_existing_folder(candidate, primary_path):
        return candidate
    return _available_dir(candidate)


def _read_intake_docx_text(path: Path, *, context: str) -> str | None:
    """Return readable Word text; legacy DOC is converted only when Word exists."""
    try:
        from medical_docx_xml_fragments import ensure_docx_compatible
        readable = ensure_docx_compatible(path, label="первичный документ")
        return extract_docx_text(readable)[:12000]
    except Exception as exc:
        record_soft_exception(context, exc, detail=str(path))
        return None


def scan_primary_candidates(folder: str | Path, seen_signatures: set[str]) -> tuple[DesktopCandidate, ...]:
    root = Path(folder).expanduser()
    if not root.exists() or not root.is_dir():
        return ()
    primary_candidates: list[tuple[int, DesktopCandidate]] = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or not _is_supported_intake_document_name(path):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size <= 0 or time.time() - stat.st_mtime < PRIMARY_FILE_QUIET_SECONDS:
            continue
        doc_text = _read_intake_docx_text(path, context="desktop_intake.scan_primary_candidate_score")
        if doc_text is None:
            continue
        try:
            after = path.stat()
        except OSError:
            continue
        if (after.st_mtime_ns, after.st_size) != (stat.st_mtime_ns, stat.st_size):
            continue
        score = primary_document_score(doc_text)
        if score < 5:
            continue
        key = signature_key(path, stat.st_mtime_ns, stat.st_size)
        if key in seen_signatures:
            continue
        primary_candidates.append((score, DesktopCandidate(path, (stat.st_mtime_ns, stat.st_size))))
    ordered = sorted(
        primary_candidates,
        key=lambda item: (-item[0], item[1].signature[0], item[1].path.name.lower()),
    )
    return tuple(candidate for _score, candidate in ordered)


def is_likely_primary_document(path: str | Path) -> bool:
    candidate = Path(path).expanduser()
    if _is_ignored_candidate_name(candidate):
        return False
    if candidate.suffix.lower() not in _ALLOWED_PRIMARY_SUFFIXES or not candidate.exists():
        return False
    text = _read_intake_docx_text(candidate, context="desktop_intake.likely_primary_extract")
    return text is not None and primary_document_score(text) >= 5


def prepare_patient_work_folder(
    folder: str | Path,
    primary_path: str | Path,
    folder_name: str | None = None,
    *,
    keep_source: bool = False,
) -> tuple[Path, Path]:
    """Create/reuse the patient folder and atomically place the primary Word file there."""
    source = Path(primary_path).expanduser()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Не найден первичный документ для папки пациента: {source}")
    patient_dir = safe_patient_subfolder(folder, source, folder_name=folder_name)
    patient_dir.mkdir(parents=True, exist_ok=True)
    source_digest = _file_content_digest(source)
    for existing in patient_dir.iterdir():
        if not existing.is_file() or existing.suffix.lower() not in _ALLOWED_PRIMARY_SUFFIXES:
            continue
        try:
            if _file_content_digest(existing) == source_digest:
                if not keep_source:
                    try:
                        same_path = source.resolve() == existing.resolve()
                    except OSError:
                        same_path = source.absolute() == existing.absolute()
                    if not same_path:
                        try:
                            source.unlink()
                        except FileNotFoundError as missing_exc:
                            record_soft_exception(
                                "desktop_intake.dedup_source_already_missing",
                                missing_exc,
                                detail=str(source),
                            )
                        except OSError as unlink_exc:
                            raise RuntimeError(
                                "Первичный документ уже есть в папке пациента, но исходный файл не удалось удалить. "
                                "Перенос не завершён; закройте файл и повторите."
                            ) from unlink_exc
                return patient_dir, existing
        except OSError:
            continue
    target = available_path(patient_dir / source.name)
    if keep_source:
        try:
            shutil.copy2(str(source), str(target))
            return patient_dir, target
        except Exception as copy_exc:
            with suppress(Exception):
                if target.exists():
                    target.unlink()
            with suppress(Exception):
                if patient_dir.exists() and not any(patient_dir.iterdir()):
                    patient_dir.rmdir()
            raise RuntimeError(
                "Не удалось подготовить копию первичного документа в папке пациента.\n"
                f"Исходный файл: {source}\nПапка пациента: {patient_dir}\nОшибка: {copy_exc}"
            ) from copy_exc
    try:
        moved = Path(shutil.move(str(source), str(target)))
    except Exception as move_exc:
        try:
            shutil.copy2(str(source), str(target))
            try:
                source.unlink()
            except Exception as unlink_exc:
                with suppress(Exception):
                    target.unlink()
                with suppress(Exception):
                    if patient_dir.exists() and not any(patient_dir.iterdir()):
                        patient_dir.rmdir()
                raise RuntimeError(
                    "Копия первичного документа создана, но исходный файл не удалось удалить. "
                    "Перенос отменён без дублирования файла."
                ) from unlink_exc
            moved = target
        except Exception as copy_exc:
            with suppress(Exception):
                if target.exists():
                    target.unlink()
            with suppress(Exception):
                if patient_dir.exists() and not any(patient_dir.iterdir()):
                    patient_dir.rmdir()
            raise RuntimeError(
                "Не удалось перенести первичный документ в папку пациента.\n"
                f"Исходный файл: {source}\nПапка пациента: {patient_dir}\n"
                f"Ошибка переноса: {move_exc}\nОшибка копирования: {copy_exc}"
            ) from copy_exc
    return patient_dir, moved


def signature_key(path: str | Path, mtime_ns: int, size: int) -> str:
    candidate = Path(path)
    try:
        resolved = str(candidate.resolve())
    except OSError:
        resolved = str(candidate)
    content_digest = ""
    try:
        if candidate.exists() and candidate.is_file():
            content_digest = _file_content_digest(candidate)
    except OSError as exc:
        record_soft_exception("desktop_intake.signature_content", exc, detail=str(candidate))
    raw = f"{resolved}|{mtime_ns}|{size}|{content_digest}"
    return hashlib.sha256(raw.encode("utf-8", errors="surrogatepass")).hexdigest()


def mark_seen(seen_signatures: set[str], candidate: DesktopCandidate) -> None:
    seen_signatures.add(signature_key(candidate.path, candidate.signature[0], candidate.signature[1]))


def assert_desktop_intake_lock() -> None:
    if DESKTOP_INTAKE_LOCK_VERSION != "v1.15":
        raise AssertionError("Desktop intake lock changed unexpectedly")
    if DESKTOP_INTAKE_REQUIRES_RUNNING_APP:
        raise AssertionError("Desktop intake must support background activation")
    if not DESKTOP_INTAKE_BACKGROUND_AGENT_SUPPORTED:
        raise AssertionError("Desktop intake background agent contract is missing")
    if not DESKTOP_INTAKE_SCANS_TOP_LEVEL_ONLY:
        raise AssertionError("Desktop intake must scan top-level only")
    if not DESKTOP_INTAKE_VALIDATES_PRIMARY_DOCUMENT_ROLE:
        raise AssertionError("Desktop intake must keep role checks")
    if not DESKTOP_INTAKE_TOP_LEVEL_DOCX_DROP_STARTS_APP:
        raise AssertionError("Dropping a supported primary Word file must activate intake")
    if not DESKTOP_INTAKE_CREATES_PATIENT_FOLDER_AFTER_SELECTION:
        raise AssertionError("Desktop intake must not create empty patient folders before selection")
    if not DESKTOP_INTAKE_MOVES_PRIMARY_INTO_PATIENT_FOLDER:
        raise AssertionError("Processed primary must leave watched top level")
    if not DESKTOP_INTAKE_PATIENT_FOLDER_USES_PRIMARY_DATA:
        raise AssertionError("Patient folder must use primary data")
    if not DESKTOP_INTAKE_REASKS_ON_FEATURE_UPGRADE:
        raise AssertionError("Setup prompt must be versioned")
    if not DESKTOP_INTAKE_IGNORES_WORD_TEMP_FILES or not DESKTOP_INTAKE_IGNORES_HIDDEN_DOT_FILES:
        raise AssertionError("Temporary/hidden Word files must stay ignored")
    if not DESKTOP_INTAKE_REUSES_EXISTING_CASE_INSENSITIVE_FOLDER:
        raise AssertionError("Existing intake folder must be reused case-insensitively")
    if not DESKTOP_INTAKE_USES_ROLE_SCORE_CLASSIFIER or not DESKTOP_INTAKE_PRIORITY_USES_ROLE_SCORE:
        raise AssertionError("Desktop intake must prioritize the strongest primary candidate")
    if not DESKTOP_INTAKE_EXACT_CONTENT_DEDUP_PRECEDES_METADATA:
        raise AssertionError("Exact-content retry must outrank incomplete parsed metadata")
    if not DESKTOP_INTAKE_SUPPORTS_SAME_WORD_FORMATS_AS_MANUAL_FLOW:
        raise AssertionError("Desktop intake and manual Word input formats diverged")
    if not DESKTOP_INTAKE_PERSISTS_BACKGROUND_AGENT_READINESS:
        raise AssertionError("Closed-app watcher readiness must be persisted separately")
    if not _is_supported_intake_document_name(Path("Первичный осмотр.docx")):
        raise AssertionError("DOCX must be accepted")
    if not _is_supported_intake_document_name(Path("Первичный осмотр.docm")):
        raise AssertionError("DOCM must be accepted")
    if not _is_supported_intake_document_name(Path("Первичный осмотр.doc")):
        raise AssertionError("Legacy DOC must follow manual-input support when Word conversion is available")
    if _is_supported_intake_document_name(Path("~$Первичный осмотр.docx")):
        raise AssertionError("Word lock files must be ignored")
    if _is_supported_intake_document_name(Path("notes.txt")):
        raise AssertionError("Non-Word files must be ignored")
    if normalize_intake_settings({"enabled": "false", "asked": "нет"})["enabled"]:
        raise AssertionError("String false must not enable desktop intake")
    if not should_prompt_intake_setup({}):
        raise AssertionError("Clean settings must show setup prompt")
    if not should_prompt_intake_setup({"asked": True, "enabled": False, "prompt_version": "v2"}):
        raise AssertionError("Old setup settings must be re-asked")
    if should_prompt_intake_setup({"asked": True, "enabled": False, "prompt_version": DESKTOP_INTAKE_SETUP_PROMPT_VERSION}):
        raise AssertionError("Current explicit No must not nag")
    if primary_document_score("Выписка после госпитализации. Рекомендации.") >= 7:
        raise AssertionError("Generic discharge text must not trigger intake")
    if len(signature_key("/tmp/Иванов.docx", 1, 2)) != 64:
        raise AssertionError("Desktop intake signatures must be hashed")
