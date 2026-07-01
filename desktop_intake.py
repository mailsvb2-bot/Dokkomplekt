"""Desktop intake folder helpers.

The feature is intentionally local and polling-based: while the application is
running, a doctor may drop a primary DOCX into the desktop folder and the app
will offer document creation into a patient subfolder.
"""

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

DESKTOP_INTAKE_LOCK_VERSION = "v1.12"
DESKTOP_INTAKE_SETUP_PROMPT_VERSION = "v3-first-launch-required"
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
_ALLOWED_PRIMARY_SUFFIXES = {".docx", ".docm"}
_PRIMARY_MARKERS = (
    "первичный осмотр",
    "первинний огляд",
    "осмотр врача приёмного покоя",
    "осмотр врача приемного покоя",
    "приёмного покоя",
    "приемного покоя",
    "направление на госпитализацию",
    "госпитализац",
    "поступает",
    "поступил",
    "admission",
    "hospitalization",
)
_EXCLUDED_DOCUMENT_MARKERS = (
    "выписной эпикриз",
    "переводной эпикриз",
    "протокол операции",
    "операционный протокол",
    "информированное согласие",
    "консультационное заключение",
)


def primary_document_score(text: str) -> int:
    """Score whether DOCX text is a primary intake source.

    A single generic word like «госпитализация» is not enough: it appears in
    discharge summaries, consents and operation documents too.  The watcher is
    intentionally conservative and requires either a strong primary title or a
    combination of patient/admission/diagnosis markers.
    """

    low = (text or "").lower().replace("ё", "е")
    if not low.strip():
        return 0
    negative = 0
    for marker in _EXCLUDED_DOCUMENT_MARKERS:
        if marker in low:
            negative += 5
    score = 0
    strong_markers = (
        "первичный осмотр",
        "первинний огляд",
        "осмотр врача приемного покоя",
        "осмотр врача приёмного покоя",
        "направление на госпитализацию",
    )
    score += 6 * sum(1 for marker in strong_markers if marker in low)
    identity_markers = ("ф.и.о", "фио", "фамилия имя отчество", "пациент", "больной", "больная", "история болезни", "номер истории")
    admission_markers = ("дата поступления", "дата госпитализации", "поступил", "поступила", "поступает", "госпитализирован", "госпитализирована")
    clinical_markers = ("диагноз", "жалобы", "анамнез", "объективный статус", "соматический статус", "план лечения")
    score += 2 * sum(1 for marker in identity_markers if marker in low)
    score += 3 * sum(1 for marker in admission_markers if marker in low)
    score += 1 * sum(1 for marker in clinical_markers if marker in low)
    if "госпитализац" in low and not any(marker in low for marker in admission_markers + strong_markers):
        score -= 2
    return max(0, score - negative)


@dataclass(frozen=True)
class DesktopCandidate:
    path: Path
    signature: tuple[int, int]


def _desktop_from_windows_registry() -> Path | None:
    """Read the authoritative Windows Desktop location when available.

    OneDrive redirection is stored by Explorer in ``User Shell Folders``.
    Environment-variable heuristics are useful as a fallback, but the registry
    value is the closest stdlib-only source of truth for a real Windows user.
    """

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
    return None


def desktop_path() -> Path:
    """Return the user's real Desktop folder as safely as possible.

    On Windows the Desktop is often redirected to OneDrive.  The strongest
    signal is Explorer's registry setting; if it is unavailable, OneDrive
    Desktop candidates are preferred before ``USERPROFILE/Desktop`` so a stale
    local Desktop folder does not steal the first-launch intake prompt.
    """

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

    # Prefer redirected/cloud desktops before the ordinary user profile.
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
    """Return the folder path that the setup dialog should offer.

    Saved settings can come from an older broken build where the prompt was not
    reliably shown.  For a new prompt we must not blindly reuse a stale path:
    the question says «на рабочем столе», so missing/invalid saved paths are
    re-resolved against the current real Desktop/OneDrive Desktop.  An existing
    previously created intake folder is still reused to avoid duplicates.
    """

    if saved_folder:
        try:
            candidate = Path(saved_folder).expanduser()
            if candidate.exists() and candidate.is_dir() and candidate.name.casefold() == DESKTOP_INTAKE_FOLDER_NAME.casefold():
                return candidate
        except Exception as exc:
            record_soft_exception("desktop_intake.prompt_intake_folder.saved_folder", exc, detail=str(saved_folder))
    return default_intake_folder()


def _existing_intake_folder_on_desktop() -> Path | None:
    """Return an existing intake folder regardless of case/old spelling.

    Earlier versions created ``выписанные пациенты`` in lowercase.  On Windows
    that is the same folder for most users, but on case-sensitive filesystems and
    in tests we must not silently create a duplicate capitalized folder.
    """

    root = desktop_path()
    target = DESKTOP_INTAKE_FOLDER_NAME.casefold()
    try:
        for child in root.iterdir():
            if child.is_dir() and child.name.casefold() == target:
                return child
    except Exception as exc:
        record_soft_exception("desktop_intake.existing_intake_folder_on_desktop", exc, detail=str(root))
        return None
    return None



def _is_ignored_candidate_name(path: str | Path) -> bool:
    name = Path(path).name
    return name.startswith("~$") or name.startswith(".")


def _is_supported_intake_document_name(path: str | Path) -> bool:
    candidate = Path(path)
    return candidate.suffix.lower() in _ALLOWED_PRIMARY_SUFFIXES and not _is_ignored_candidate_name(candidate)


def _setting_bool(value: object) -> bool:
    """Normalize legacy JSON booleans stored as strings.

    Older/manual settings may contain values like ``"false"`` or ``"нет"``.
    Python's ``bool("false")`` is True, which could accidentally enable the
    desktop watcher and suppress the first-launch prompt.
    """

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
    """Return True only for the canonical watched folder name.

    The startup watcher must never silently scan an arbitrary saved directory
    such as the whole Desktop after a corrupted/legacy settings file.
    """
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
        "folder": folder,
        "prompt_version": prompt_version,
        "seen_signatures": tuple(dict.fromkeys(seen[-300:])),
    }


def should_prompt_intake_setup(settings: Mapping[str, object] | None) -> bool:
    """Whether startup must ask about the intake folder.

    This prompt is a user-visible startup contract, not a cosmetic preference.
    Old builds could leave ``prompt_version=v2`` in settings without reliably
    showing the question to the doctor.  Therefore the current v3 prompt is
    deliberately considered a new mandatory setup checkpoint.

    Rules:
    * clean profile => ask;
    * old/no prompt version => ask;
    * v2 or any non-current prompt version => ask;
    * enabled=True but folder is missing => ask instead of silently recreating;
    * current explicit No => do not ask again until the next prompt version.
    """

    normalized = normalize_intake_settings(settings)
    folder = Path(str(normalized["folder"])).expanduser()
    enabled = bool(normalized["enabled"])
    asked = bool(normalized["asked"])
    prompt_version = str(normalized.get("prompt_version", "") or "")
    folder_ready = folder.exists() and folder.is_dir() and is_desktop_intake_folder_path(folder)
    if enabled and folder_ready and prompt_version == DESKTOP_INTAKE_SETUP_PROMPT_VERSION:
        return False
    if not asked:
        return True
    if prompt_version != DESKTOP_INTAKE_SETUP_PROMPT_VERSION:
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


def safe_patient_subfolder(folder: str | Path, primary_path: str | Path, folder_name: str | None = None) -> Path:
    if folder_name is None:
        try:
            from desktop_patient_folder import build_patient_folder_info
            folder_name = build_patient_folder_info(primary_path).folder_name
        except Exception as exc:
            record_soft_exception("desktop_intake.patient_folder_info", exc, detail=str(primary_path))
            folder_name = ""
    name = safe_filename((folder_name or Path(primary_path).stem)).strip(" .") or "Пациент"
    return _available_dir(Path(folder).expanduser() / name)


def scan_primary_candidates(folder: str | Path, seen_signatures: set[str]) -> tuple[DesktopCandidate, ...]:
    """Return top-level intake candidates with primary-source priority.

    Dedicated folder semantics are intentionally two-stage:
    * any stable top-level DOCX/DOCM is a launch intent when the file is not
      clearly a generated/discharge document;
    * when a clearly primary source is present, it wins. If that primary source
      is already marked as seen, neighbouring generated documents must not
      become a new launch candidate.
    """
    root = Path(folder).expanduser()
    if not root.exists() or not root.is_dir():
        return ()

    fallback_candidates: list[DesktopCandidate] = []
    primary_candidates: list[tuple[int, DesktopCandidate]] = []
    clear_primary_present = False

    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or not _is_supported_intake_document_name(path):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size <= 0:
            continue
        if time.time() - stat.st_mtime < 1.2:
            continue

        try:
            doc_text = extract_docx_text(path)[:12000]
        except Exception as exc:
            record_soft_exception("desktop_intake.scan_primary_candidate_score", exc, detail=str(path))
            doc_text = ""
        score = primary_document_score(doc_text)
        is_clear_primary = score >= 5
        if is_clear_primary:
            clear_primary_present = True

        key = signature_key(path, stat.st_mtime_ns, stat.st_size)
        if key in seen_signatures:
            continue

        candidate = DesktopCandidate(path, (stat.st_mtime_ns, stat.st_size))
        if is_clear_primary:
            primary_candidates.append((score, candidate))
            continue

        low_text = doc_text.lower().replace("ё", "е")
        if any(marker in low_text for marker in _EXCLUDED_DOCUMENT_MARKERS):
            continue
        fallback_candidates.append(candidate)

    if clear_primary_present:
        ordered = sorted(primary_candidates, key=lambda item: (-item[0], item[1].path.name.lower()))
        return tuple(candidate for _score, candidate in ordered)

    return tuple(fallback_candidates)


def is_likely_primary_document(path: str | Path) -> bool:
    """Return True only for intake source documents, not generated templates.

    This classifier is intentionally kept for diagnostics and manual role checks.
    It is no longer a hard launch gate for the dedicated intake folder: the
    watched folder itself is the doctor's explicit signal to start the workflow.
    """

    candidate = Path(path).expanduser()
    if _is_ignored_candidate_name(candidate):
        return False
    if candidate.suffix.lower() not in _ALLOWED_PRIMARY_SUFFIXES or not candidate.exists():
        return False
    try:
        text = extract_docx_text(candidate)[:12000]
    except Exception as exc:
        record_soft_exception("desktop_intake.likely_primary_extract", exc, detail=str(candidate))
        return False
    # The watched folder is a deliberate doctor action: a DOCX dropped into
    # «Выписанные пациенты» should not be ignored merely because the hospital
    # template lacks a literal title «Первичный осмотр».  Negative document
    # markers are still subtracted by primary_document_score().
    return primary_document_score(text) >= 5


def prepare_patient_work_folder(folder: str | Path, primary_path: str | Path, folder_name: str | None = None) -> tuple[Path, Path]:
    """Create a patient subfolder and move the dropped primary document into it.

    Moving the source DOCX out of the watched top-level folder prevents the same
    file from re-triggering on the next application start.  If moving across
    filesystems fails, copy+unlink is attempted by shutil.move.
    """

    source = Path(primary_path).expanduser()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Не найден первичный документ для папки пациента: {source}")
    patient_dir = safe_patient_subfolder(folder, source, folder_name=folder_name)
    patient_dir.mkdir(parents=True, exist_ok=False)
    target = available_path(patient_dir / source.name)
    try:
        moved = Path(shutil.move(str(source), str(target)))
    except Exception as move_exc:
        # If Explorer/Word temporarily locks the source, still copy the primary
        # into the patient folder and use that copy as the active source.  If the
        # copy also fails, stop loudly: otherwise the UI would promise a patient
        # folder while generation still depends on the top-level intake folder.
        try:
            shutil.copy2(str(source), str(target))
            moved = target
            try:
                source.unlink()
            except Exception as unlink_exc:
                # A locked Word/Explorer file may survive copy fallback. Generation
                # still uses the patient-folder copy, but diagnostics must show why
                # the top-level duplicate could not be removed.
                record_soft_exception("desktop_intake.copy_fallback_unlink_source", unlink_exc, detail=str(source))
        except Exception as copy_exc:
            with suppress(Exception):
                if target.exists():
                    target.unlink()
            with suppress(Exception):
                if patient_dir.exists() and not any(patient_dir.iterdir()):
                    patient_dir.rmdir()
            raise RuntimeError(
                "Не удалось перенести первичный документ в папку пациента.\n"
                f"Исходный файл: {source}\n"
                f"Папка пациента: {patient_dir}\n"
                f"Ошибка переноса: {move_exc}\n"
                f"Ошибка копирования: {copy_exc}"
            ) from copy_exc
    return patient_dir, moved


def signature_key(path: str | Path, mtime_ns: int, size: int) -> str:
    try:
        resolved = str(Path(path).resolve())
    except OSError:
        resolved = str(Path(path))
    raw = f"{resolved}|{mtime_ns}|{size}"
    return hashlib.sha256(raw.encode("utf-8", errors="surrogatepass")).hexdigest()


def mark_seen(seen_signatures: set[str], candidate: DesktopCandidate) -> None:
    seen_signatures.add(signature_key(candidate.path, candidate.signature[0], candidate.signature[1]))


def assert_desktop_intake_lock() -> None:
    """Implement the assert_desktop_intake_lock workflow with validation, UI state updates and diagnostics."""
    if DESKTOP_INTAKE_LOCK_VERSION != "v1.12":
        raise AssertionError("Desktop intake lock changed unexpectedly")
    if DESKTOP_INTAKE_REQUIRES_RUNNING_APP:
        raise AssertionError("Desktop intake must support activation through the optional background agent")
    if not DESKTOP_INTAKE_BACKGROUND_AGENT_SUPPORTED:
        raise AssertionError("Desktop intake background agent contract is missing")
    if not DESKTOP_INTAKE_SCANS_TOP_LEVEL_ONLY:
        raise AssertionError("Desktop intake must scan top-level folder only to avoid output loops")
    if not DESKTOP_INTAKE_VALIDATES_PRIMARY_DOCUMENT_ROLE:
        raise AssertionError("Desktop intake must keep primary-document role checks available")
    if not DESKTOP_INTAKE_TOP_LEVEL_DOCX_DROP_STARTS_APP:
        raise AssertionError("Dropping DOCX/DOCM into the dedicated intake folder must start the app")
    if not DESKTOP_INTAKE_CREATES_PATIENT_FOLDER_AFTER_SELECTION:
        raise AssertionError("Desktop intake must not create empty patient folders before doctor selection")
    if not DESKTOP_INTAKE_MOVES_PRIMARY_INTO_PATIENT_FOLDER:
        raise AssertionError("Desktop intake must move processed primary files out of the watched top-level folder when possible")
    if not DESKTOP_INTAKE_PATIENT_FOLDER_USES_PRIMARY_DATA:
        raise AssertionError("Desktop intake patient folders must use patient/admission data when available")
    if not DESKTOP_INTAKE_REASKS_ON_FEATURE_UPGRADE:
        raise AssertionError("Desktop intake prompt must be versioned so old declined settings do not hide new functionality")
    if not DESKTOP_INTAKE_IGNORES_WORD_TEMP_FILES:
        raise AssertionError("Desktop intake must ignore temporary Word files")
    if not DESKTOP_INTAKE_REUSES_EXISTING_CASE_INSENSITIVE_FOLDER:
        raise AssertionError("Desktop intake must reuse existing differently-cased intake folders")
    if not DESKTOP_INTAKE_USES_ROLE_SCORE_CLASSIFIER:
        raise AssertionError("Desktop intake must use scored primary-document classification")
    if not DESKTOP_INTAKE_COPY_FALLBACK_RETURNS_PATIENT_COPY:
        raise AssertionError("Desktop intake move fallback must return the patient-folder copy when copy succeeds")
    if not DESKTOP_INTAKE_DOES_NOT_TRUST_GENERIC_HOSPITALIZATION_WORD:
        raise AssertionError("Desktop intake must not trust generic hospitalization words alone")
    if not DESKTOP_INTAKE_SEEN_SIGNATURES_ARE_HASHED:
        raise AssertionError("Desktop intake seen signatures must not store patient filenames as raw keys")
    if not DESKTOP_INTAKE_SEEN_SIGNATURES_ARE_PERSISTABLE:
        raise AssertionError("Desktop intake seen signatures must be persistable across restarts")
    if not DESKTOP_INTAKE_USES_WINDOWS_DESKTOP_REGISTRY:
        raise AssertionError("Desktop intake must use Windows registry Desktop location when available")
    if not DESKTOP_INTAKE_MOVE_FAILURE_IS_VISIBLE:
        raise AssertionError("Desktop intake move/copy failure must be visible instead of silently falling back")
    if not DESKTOP_INTAKE_NORMALIZES_LEGACY_BOOL_STRINGS:
        raise AssertionError("Desktop intake settings must normalize legacy string booleans")
    if not DESKTOP_INTAKE_FIRST_LAUNCH_PROMPT_IS_MANDATORY:
        raise AssertionError("Desktop intake setup question must be mandatory on clean first launch")
    if not DESKTOP_INTAKE_REASKS_OLD_V2_PROMPT_SETTINGS:
        raise AssertionError("Desktop intake must re-ask old v2 prompt settings after the broken release")
    if not DESKTOP_INTAKE_MISSING_ENABLED_FOLDER_REASKS:
        raise AssertionError("Desktop intake must re-ask when enabled settings point to a missing folder")
    if not DESKTOP_INTAKE_IGNORES_HIDDEN_DOT_FILES:
        raise AssertionError("Desktop intake must ignore hidden dot files")
    if not DESKTOP_INTAKE_COPY_FALLBACK_TRIES_TO_UNLINK_SOURCE:
        raise AssertionError("Desktop intake copy fallback must try to remove the top-level source")
    if not _is_ignored_candidate_name(Path(".hidden.docx")) or not _is_ignored_candidate_name(Path("~$temp.docx")):
        raise AssertionError("Desktop intake ignored-file predicate is broken")
    if not _is_supported_intake_document_name(Path("Первичный осмотр.docx")):
        raise AssertionError("Desktop intake must accept a top-level DOCX as launch intent")
    if not _is_supported_intake_document_name(Path("Первичный осмотр.docm")):
        raise AssertionError("Desktop intake must accept a top-level DOCM as launch intent")
    if _is_supported_intake_document_name(Path("~$Первичный осмотр.docx")):
        raise AssertionError("Desktop intake must not launch on Word temporary lock files")
    if _is_supported_intake_document_name(Path("notes.txt")):
        raise AssertionError("Desktop intake must ignore non-Word files")
    if normalize_intake_settings({"enabled": "false", "asked": "нет"})["enabled"]:
        raise AssertionError("String false must not enable desktop intake")
    if not should_prompt_intake_setup({}):
        raise AssertionError("Clean settings must show the desktop intake setup prompt")
    if not should_prompt_intake_setup({"asked": True, "enabled": False, "prompt_version": "v2"}):
        raise AssertionError("Old v2 prompt settings must be re-asked in the fixed build")
    if should_prompt_intake_setup({"asked": True, "enabled": False, "prompt_version": DESKTOP_INTAKE_SETUP_PROMPT_VERSION}):
        raise AssertionError("Current explicit No must not nag on every launch")
    if primary_document_score("Выписка после госпитализации. Рекомендации.") >= 7:
        raise AssertionError("Generic discharge/hospitalization text must not trigger desktop intake")
    if len(signature_key("/tmp/Иванов.docx", 1, 2)) != 64:
        raise AssertionError("Desktop intake signatures must be hashed")
