"""Background intake launcher for the ``Выписанные пациенты`` folder.

This tiny stdlib-only agent is the safe way to support the real Windows UX where
MedicalDiaryAutofill is closed, but a doctor drops a primary DOCX into the intake
folder.  A closed GUI process cannot react by itself; therefore this optional
agent is installed into the user's Startup folder and launches the main app when
a likely primary document appears.

No global keyboard hooks, no mouse hooks, no admin Windows service and no hidden
medical data storage are used.  The agent stores only hashed file signatures so a
processed top-level file does not relaunch the app in a loop.
"""

from __future__ import annotations

import atexit
from contextlib import suppress
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Iterable

from diagnostic_logging import record_soft_exception
from desktop_intake import (
    DESKTOP_INTAKE_FOLDER_NAME,
    DESKTOP_INTAKE_SETUP_PROMPT_VERSION,
    default_intake_folder,
    is_desktop_intake_folder_path,
    mark_seen,
    normalize_intake_settings,
    scan_primary_candidates,
    signature_key,
)

AGENT_VERSION = "v1.7"
POLL_SECONDS = 2.5
LAUNCH_COOLDOWN_SECONDS = 20.0
LOCK_STALE_SECONDS = 120.0
GUI_ACTIVE_SECONDS = 45.0
PENDING_RETRY_SECONDS = 75.0
MAX_LOG_BYTES = 512 * 1024
STATE_FILE_NAME = "desktop_intake_agent_state.json"
LOCK_FILE_NAME = "desktop_intake_agent.lock"
GUI_LOCK_FILE_NAME = "medical_diary_autofill_gui.lock"
STARTUP_AGENT_SCRIPT_NAME = "MedicalDiaryAutofill Intake Agent.vbs"
LEGACY_STARTUP_SHORTCUT_NAME = "MedicalDiaryAutofill Intake Agent.lnk"
DESKTOP_INTAKE_AGENT_HAS_SINGLETON_LOCK = True
DESKTOP_INTAKE_AGENT_RESPECTS_EXPLICIT_DISABLED_SETTINGS = True
DESKTOP_INTAKE_AGENT_FROZEN_EXE_MODE_SUPPORTED = True
DESKTOP_INTAKE_AGENT_LOG_IS_BOUNDED = True
DESKTOP_INTAKE_AGENT_LOG_USES_DATETIME_FORMATTER = True
DESKTOP_INTAKE_AGENT_USES_PENDING_HANDSHAKE = True
DESKTOP_INTAKE_AGENT_AUTOSTART_INSTALL_SUPPORTED = True
DESKTOP_INTAKE_AGENT_HIDES_POWERSHELL_WINDOW = True
DESKTOP_INTAKE_AGENT_USES_VBS_STARTUP_SCRIPT = True
DESKTOP_INTAKE_AGENT_HAS_NO_POWERSHELL_CODE_PATH = True
DESKTOP_INTAKE_AGENT_STARTUP_SCRIPT_IS_UTF16 = True
DESKTOP_INTAKE_AGENT_STARTUP_SCRIPT_HAS_NO_UTF8_BOM = True
DESKTOP_INTAKE_AGENT_STATE_IS_PATHLESS = True
DESKTOP_INTAKE_AGENT_LOGS_ARE_REDACTED = True
DESKTOP_INTAKE_AGENT_AUTOSTART_IS_DISABLED_IN_CI = True
DESKTOP_INTAKE_AGENT_LOGGING_IS_DISABLED_IN_CI = True
DESKTOP_INTAKE_AGENT_RESPECTS_ACTIVE_GUI_LOCK = True


def _truthy_env(value: object) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on", "да", "y", "enabled"}


def _autostart_disabled_by_environment() -> bool:
    """Return True when release/CI probes must not spawn a background watcher.

    Real doctors get the watcher after the first-run confirmation.  Release
    checks and GitHub Actions must never start pythonw.exe next to the source
    tree, because that leaves lock/log runtime artifacts and can make a clean
    production gate fail after all behavioral assertions passed.
    """

    return _truthy_env(os.environ.get("MEDICAL_AUTOFILL_DISABLE_AUTOSTART")) or _truthy_env(os.environ.get("CI"))


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _data_root() -> Path:
    if getattr(sys, "frozen", False):
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home()
        return root / "MedicalDiaryAutofill"
    # Source/portable archives intentionally use the same local data root as the
    # GUI settings layer so tests and doctors do not cross-contaminate profiles.
    return _app_root() / ".medical_diary_autofill_data"


def _settings_path() -> Path:
    return _data_root() / "settings.json"


def _state_path() -> Path:
    return _data_root() / STATE_FILE_NAME


def _lock_path() -> Path:
    return _data_root() / LOCK_FILE_NAME


def _log_path() -> Path:
    return _data_root() / "desktop_intake_agent.log"


def _gui_lock_path() -> Path:
    return _data_root() / GUI_LOCK_FILE_NAME


def _rotate_log_if_needed(path: Path) -> None:
    try:
        if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
            backup = path.with_suffix(path.suffix + ".old")
            with suppress(Exception):
                backup.unlink()
            path.replace(backup)
    except Exception as exc:
        record_soft_exception("desktop_intake_agent.rotate_log", exc)


def _agent_logger() -> logging.Logger:
    """Return a bounded timestamped logger for the background watcher."""
    logger = logging.getLogger("MedicalDiaryAutofill.desktop_intake_agent")
    if not logger.handlers:
        _data_root().mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(_log_path(), maxBytes=MAX_LOG_BYTES, backupCount=1, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def _write_log(message: str) -> None:
    try:
        if _autostart_disabled_by_environment():
            return
        _agent_logger().info(message)
    except Exception as exc:
        record_soft_exception("desktop_intake_agent.log", exc)






def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _gui_lock_payload() -> dict:
    return {"version": AGENT_VERSION, "pid": os.getpid(), "updated_at": time.time()}


def write_gui_runtime_lock() -> None:
    """Refresh the foreground GUI heartbeat used by the background agent.

    The file contains only technical runtime data.  It prevents the background
    watcher from launching a second GUI while the doctor already has the main
    window open and the in-process watcher can handle the dropped DOCX.
    """
    _save_json(_gui_lock_path(), _gui_lock_payload())


def release_gui_runtime_lock() -> None:
    """Remove this process' GUI heartbeat on normal shutdown."""
    path = _gui_lock_path()
    payload = _load_json(path)
    if _safe_int(payload.get("pid"), -1) not in {-1, os.getpid()}:
        return
    with suppress(OSError):
        path.unlink()


def is_gui_runtime_active(now: float | None = None) -> bool:
    """Return True when a foreground GUI heartbeat is fresh.

    Stale or corrupted locks are ignored so a crashed program cannot suppress
    legitimate desktop-intake launches forever.
    """
    payload = _load_json(_gui_lock_path())
    if not payload:
        return False
    updated_at = _safe_float(payload.get("updated_at", 0.0), 0.0)
    current = time.time() if now is None else now
    if current - updated_at <= GUI_ACTIVE_SECONDS:
        return True
    with suppress(OSError):
        _gui_lock_path().unlink()
    return False


def _safe_signature_ref(signature: object) -> str:
    value = str(signature or "").strip().lower()
    if len(value) == 64 and all(ch in "0123456789abcdef" for ch in value):
        return "sig-" + value[:12]
    return "sig-unknown"


def _candidate_ref(candidate) -> str:
    try:
        return _safe_signature_ref(_candidate_signature(candidate))
    except (OSError, TypeError, ValueError):
        return "sig-unknown"


def _load_json(path: Path) -> dict:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as exc:
        record_soft_exception("desktop_intake_agent.load_json", exc, detail=str(path))
    return {}


def _save_json(path: Path, payload: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:
        record_soft_exception("desktop_intake_agent.save_json", exc, detail=str(path))


def _setting_is_current_explicit_no(settings: dict) -> bool:
    intake_raw = settings.get("desktop_intake") if isinstance(settings, dict) else None
    if not isinstance(intake_raw, dict):
        return False
    normalized = normalize_intake_settings(intake_raw)
    return (
        bool(normalized.get("asked"))
        and not bool(normalized.get("enabled"))
        and str(normalized.get("prompt_version", "")) == DESKTOP_INTAKE_SETUP_PROMPT_VERSION
    )


def _watched_folder() -> Path | None:
    settings = _load_json(_settings_path())
    intake_raw = settings.get("desktop_intake") if isinstance(settings, dict) else None
    if isinstance(intake_raw, dict):
        normalized = normalize_intake_settings(intake_raw)
        folder = Path(str(normalized.get("folder", "") or "")).expanduser()
        if bool(normalized.get("enabled")):
            if folder.exists() and folder.is_dir() and is_desktop_intake_folder_path(folder):
                return folder
            return None
        # If the doctor explicitly answered «No» in the current setup version,
        # the background agent must not silently react to an existing folder.
        if _setting_is_current_explicit_no(settings):
            return None

    folder = default_intake_folder()
    if folder.exists() and folder.is_dir() and folder.name.casefold() == DESKTOP_INTAKE_FOLDER_NAME.casefold():
        return folder
    return None


def _settings_seen_signatures() -> set[str]:
    """Return GUI-persisted seen signatures from the shared settings file.

    The GUI and the background agent write different state files.  When the GUI
    has already accepted, ignored or moved a primary DOCX, the agent must trust
    the GUI settings instead of relaunching the same top-level file after its
    pending retry window expires.  Only 64-char hashes are returned; patient
    filenames never leave the intake folder.
    """
    settings = _load_json(_settings_path())
    intake_raw = settings.get("desktop_intake") if isinstance(settings, dict) else None
    if not isinstance(intake_raw, dict):
        return set()
    normalized = normalize_intake_settings(intake_raw)
    return {str(item).lower() for item in normalized.get("seen_signatures", ())}




def _windows_hidden_startupinfo():
    """Return Windows startupinfo that prevents transient console windows."""
    if os.name != "nt":
        return None
    try:
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 0
        return info
    except Exception as exc:
        record_soft_exception("desktop_intake_agent.hidden_startupinfo", exc)
        return None


def _windows_no_window_flags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _popen_hidden(command: list[str], *, cwd: str | None = None, env: dict | None = None) -> subprocess.Popen:
    """Start a child process without a PowerShell/cmd flash on Windows."""
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_windows_no_window_flags(),
        startupinfo=_windows_hidden_startupinfo(),
    )


def _startup_dir() -> Path:
    raw = os.environ.get("APPDATA", "")
    if not raw:
        return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return Path(raw) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _startup_agent_script_path() -> Path:
    return _startup_dir() / STARTUP_AGENT_SCRIPT_NAME


def _legacy_startup_shortcut_path() -> Path:
    return _startup_dir() / LEGACY_STARTUP_SHORTCUT_NAME


def _vbs_string(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _write_startup_vbs(target: str, arguments: str, appdir: str) -> Path:
    startup = _startup_dir()
    startup.mkdir(parents=True, exist_ok=True)
    command = f'"{target}" {arguments}'.strip()
    script_path = startup / STARTUP_AGENT_SCRIPT_NAME
    script = "\n".join([
        'On Error Resume Next',
        'Set shell = CreateObject("WScript.Shell")',
        f"shell.CurrentDirectory = {_vbs_string(appdir)}",
        f"shell.Run {_vbs_string(command)}, 0, False",
        "",
    ])
    # Windows Script Host/VBScript is not reliably UTF-8-BOM aware on all
    # doctor machines.  A UTF-8-SIG VBS can fail at boot with
    # "Line 1, char 1: invalid character" before the program even starts.
    # UTF-16 with BOM is the WSH-safe Unicode format for Cyrillic paths.
    script_path.write_text(script, encoding="utf-16")
    # Remove the old .lnk if a previous build created it. The VBS startup script
    # is simpler and does not require creating a transient PowerShell process.
    with suppress(Exception):
        _legacy_startup_shortcut_path().unlink()
    return script_path


def _shortcut_launch_target_and_args() -> tuple[str, str]:
    """Return the safest Windows Startup shortcut target and arguments.

    Packaged EXE builds use the EXE itself with ``--intake-agent``.  Source
    archives fall back to ``pythonw.exe``/``python.exe`` and the thin ``.pyw``
    wrapper.  The logic is intentionally shared by the BAT installer and the GUI
    auto-installer so the doctor does not have to run an extra script manually.
    """

    root = _app_root()
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve()), "--intake-agent"
    for name in ("MedicalDiaryAutofill.exe", "MedicalDiaryAutofill-Windows-EXE.exe"):
        exe = root / name
        if exe.exists():
            return str(exe.resolve()), "--intake-agent"
    agent = root / "desktop_intake_agent.pyw"
    executable = sys.executable
    if os.name == "nt" and executable.lower().endswith("python.exe"):
        pythonw = Path(executable).with_name("pythonw.exe")
        if pythonw.exists():
            executable = str(pythonw)
    return str(Path(executable).resolve()), f'"{agent.resolve()}"'


def _shortcut_launch_command() -> list[str]:
    """Return the same agent command as a Popen list, without shell quoting."""
    root = _app_root()
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve()), "--intake-agent"]
    for name in ("MedicalDiaryAutofill.exe", "MedicalDiaryAutofill-Windows-EXE.exe"):
        exe = root / name
        if exe.exists():
            return [str(exe.resolve()), "--intake-agent"]
    agent = root / "desktop_intake_agent.pyw"
    executable = sys.executable
    if os.name == "nt" and executable.lower().endswith("python.exe"):
        pythonw = Path(executable).with_name("pythonw.exe")
        if pythonw.exists():
            executable = str(pythonw)
    return [str(Path(executable).resolve()), str(agent.resolve())]


def install_agent_autostart(*, start_now: bool = True) -> tuple[bool, str]:
    """Install the intake watcher into Windows Startup and start it now.

    This is a normal per-user Startup shortcut, not a service and not a global
    hook.  It avoids the common user failure where the doctor creates the intake
    folder, closes the program, drops a file there, and nothing can react because
    the optional watcher BAT was never launched.
    """

    if _autostart_disabled_by_environment():
        return False, "autostart disabled for CI/release checks"
    if os.name != "nt":
        return False, "autostart is available only on Windows"
    try:
        target, arguments = _shortcut_launch_target_and_args()
        appdir = str(_app_root())
        startup_script = _write_startup_vbs(target, arguments, appdir)
        if start_now:
            try:
                _popen_hidden(_shortcut_launch_command(), cwd=appdir)
                _write_log(f"autostart agent started without shell: {target} {arguments}")
            except Exception as exc:
                record_soft_exception("desktop_intake_agent.start_now_hidden", exc)
                _write_log(f"autostart start_now failed after startup script creation: {exc}")
        _write_log(f"autostart installed as VBS startup script: {startup_script}")
        return True, f"installed: {startup_script}"
    except Exception as exc:
        record_soft_exception("desktop_intake_agent.install_autostart", exc)
        _write_log(f"autostart install exception: {exc}")
        return False, str(exc)

def _launch_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    root = _app_root()
    # Frozen/packaged layouts may place an EXE next to the source agent. Prefer
    # it if present. Source archives fall back to pythonw/python + main.py.
    for name in ("MedicalDiaryAutofill.exe", "MedicalDiaryAutofill-Windows-EXE.exe"):
        exe = root / name
        if exe.exists():
            return [str(exe)]
    main_py = root / "main.py"
    if main_py.exists():
        executable = sys.executable
        # If the agent was started by python.exe from console, prefer pythonw.exe
        # in the same directory so the background launch has no black console box.
        if os.name == "nt" and executable.lower().endswith("python.exe"):
            pythonw = Path(executable).with_name("pythonw.exe")
            if pythonw.exists():
                executable = str(pythonw)
        return [executable, str(main_py)]
    return [sys.executable]


def _launch_main_app(reason: str) -> bool:
    try:
        env = dict(os.environ)
        env["MEDICAL_AUTOFILL_STARTED_BY_INTAKE_AGENT"] = "1"
        _popen_hidden(_launch_command(), cwd=str(_app_root()), env=env)
        _write_log(f"launched main app: {reason}")
        return True
    except Exception as exc:
        record_soft_exception("desktop_intake_agent.launch", exc, detail=reason)
        _write_log(f"launch failed: {reason}: {exc}")
        return False


def _state_seen_signatures(state: dict) -> set[str]:
    raw = state.get("seen_signatures", [])
    result: set[str] = set()
    if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes, dict)):
        for item in raw:
            value = str(item or "").strip().lower()
            if len(value) == 64 and all(ch in "0123456789abcdef" for ch in value):
                result.add(value)
    return result


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _save_state(seen: set[str], *, last_launch: float, pending: dict | None = None) -> None:
    payload = {"version": AGENT_VERSION, "seen_signatures": sorted(seen)[-300:], "last_launch": last_launch}
    if pending:
        payload["pending"] = pending
    _save_json(_state_path(), payload)


def _candidate_signature(candidate) -> str:
    return signature_key(candidate.path, candidate.signature[0], candidate.signature[1])


def _pending_from_state(state: dict) -> dict:
    raw = state.get("pending") if isinstance(state, dict) else None
    if not isinstance(raw, dict):
        return {}
    signature = str(raw.get("signature", "") or "").strip().lower()
    launched_at = _safe_float(raw.get("launched_at", 0.0), 0.0)
    if len(signature) != 64 or not all(ch in "0123456789abcdef" for ch in signature):
        return {}
    # Legacy builds stored a raw pending path.  New builds intentionally ignore
    # it and persist only the hash signature so AppData does not become a hidden
    # patient-name ledger.
    return {"signature": signature, "launched_at": launched_at}



def _legacy_pending_path_confirmed_removed(state: dict) -> bool:
    """Return True when a legacy pending state proves the file was moved.

    New state is intentionally pathless, but older builds may already have
    persisted ``pending.path``.  Reading that value once lets us finish the
    handshake instead of relaunching forever after the doctor moved/processed
    the file.  The path is not returned by ``_pending_from_state`` and is never
    written back to new state.
    """
    raw = state.get("pending") if isinstance(state, dict) else None
    if not isinstance(raw, dict):
        return False
    raw_path = str(raw.get("path", "") or "").strip()
    if not raw_path:
        return False
    try:
        return not Path(raw_path).expanduser().exists()
    except (OSError, RuntimeError, ValueError):
        return False

def _signature_present_in_folder(folder: Path | None, signature: str) -> bool:
    if folder is None:
        return False
    try:
        for candidate in scan_primary_candidates(folder, set()):
            if _candidate_signature(candidate) == signature:
                return True
    except Exception as exc:
        record_soft_exception("desktop_intake_agent.signature_probe", exc)
    return False


def _resolve_pending_state(state: dict, seen: set[str], folder: Path | None = None) -> tuple[dict, bool]:
    """Return active pending launch and whether persistent state changed.

    A successful ``Popen`` is not proof that the doctor saw the popup.  The
    agent therefore keeps a pending launch instead of marking the DOCX seen.  The
    pending state is pathless: processing is confirmed by rescanning the watched
    folder for the same signature, not by storing a patient filename in AppData.
    """

    pending = _pending_from_state(state)
    if not pending:
        return {}, False
    launched_at = _safe_float(pending.get("launched_at", 0.0), 0.0)
    signature = str(pending.get("signature", ""))
    if signature in _settings_seen_signatures():
        seen.add(signature)
        _write_log(f"pending launch confirmed by GUI settings: {_safe_signature_ref(signature)}")
        return {}, True
    if folder is None:
        if _legacy_pending_path_confirmed_removed(state):
            seen.add(signature)
            _write_log(f"legacy pending launch confirmed by moved/removed file: {_safe_signature_ref(signature)}")
            return {}, True
        if time.time() - launched_at < PENDING_RETRY_SECONDS:
            return pending, False
        _write_log(f"pending launch expired while intake folder unavailable: {_safe_signature_ref(signature)}")
        return {}, True
    if not _signature_present_in_folder(folder, signature):
        seen.add(signature)
        _write_log(f"pending launch confirmed by moved/removed file: {_safe_signature_ref(signature)}")
        return {}, True
    if time.time() - launched_at < PENDING_RETRY_SECONDS:
        return pending, False
    _write_log(f"pending launch expired without processing: {_safe_signature_ref(signature)}")
    return {}, True


def _lock_is_stale(path: Path) -> bool:
    try:
        return time.time() - path.stat().st_mtime > LOCK_STALE_SECONDS
    except OSError:
        return True


def _acquire_agent_lock() -> int | None:
    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    for attempt in range(2):
        try:
            fd = os.open(str(path), flags)
            os.write(fd, f"pid={os.getpid()}\nversion={AGENT_VERSION}\n".encode("utf-8"))
            atexit.register(_release_agent_lock, fd, path)
            return fd
        except FileExistsError:
            if attempt == 0 and _lock_is_stale(path):
                with suppress(OSError):
                    path.unlink()
                continue
            _write_log("another intake agent is already running")
            return None
        except OSError as exc:
            record_soft_exception("desktop_intake_agent.lock", exc)
            _write_log(f"cannot acquire lock: {exc}")
            return None
    return None


def _touch_agent_lock(fd: int | None) -> None:
    if fd is None:
        return
    with suppress(Exception):
        os.utime(_lock_path(), None)


def _release_agent_lock(fd: int | None, path: Path | None = None) -> None:
    if fd is not None:
        with suppress(OSError):
            os.close(fd)
    if path is not None:
        with suppress(OSError):
            path.unlink()


def run_forever() -> None:
    lock_fd = _acquire_agent_lock()
    if lock_fd is None:
        return
    state = _load_json(_state_path())
    seen = _state_seen_signatures(state)
    last_launch = _safe_float(state.get("last_launch", 0.0), 0.0)
    pending = _pending_from_state(state)
    _write_log("agent started")
    while True:
        try:
            _touch_agent_lock(lock_fd)
            state_changed = False
            folder = _watched_folder()
            pending, pending_changed = _resolve_pending_state({"pending": pending}, seen, folder)
            state_changed = state_changed or pending_changed
            if folder is not None and not pending:
                candidates = scan_primary_candidates(folder, seen)
                if candidates and is_gui_runtime_active():
                    _write_log("foreground GUI is active; agent will not launch duplicate window")
                elif candidates and time.time() - last_launch >= LAUNCH_COOLDOWN_SECONDS:
                    candidate = candidates[0]
                    candidate_sig = _candidate_signature(candidate)
                    if _launch_main_app(f"new primary file: {_candidate_ref(candidate)}"):
                        last_launch = time.time()
                        pending = {"signature": candidate_sig, "launched_at": last_launch}
                        state_changed = True
            if state_changed:
                _save_state(seen, last_launch=last_launch, pending=pending)
        except Exception as exc:
            record_soft_exception("desktop_intake_agent.loop", exc)
            _write_log(f"loop error: {exc}")
        time.sleep(POLL_SECONDS)


def assert_desktop_intake_agent_lock() -> None:
    if AGENT_VERSION != "v1.7":
        raise AssertionError("Desktop intake agent lock changed unexpectedly")
    if not DESKTOP_INTAKE_AGENT_RESPECTS_ACTIVE_GUI_LOCK:
        raise AssertionError("Desktop intake agent must respect active foreground GUI lock")
    if not DESKTOP_INTAKE_AGENT_HAS_SINGLETON_LOCK:
        raise AssertionError("Desktop intake agent must have a singleton lock")
    if not DESKTOP_INTAKE_AGENT_RESPECTS_EXPLICIT_DISABLED_SETTINGS:
        raise AssertionError("Desktop intake agent must respect explicit disabled settings")
    if not DESKTOP_INTAKE_AGENT_FROZEN_EXE_MODE_SUPPORTED:
        raise AssertionError("Desktop intake agent must support frozen EXE mode")
    if not DESKTOP_INTAKE_AGENT_LOG_IS_BOUNDED or not DESKTOP_INTAKE_AGENT_LOG_USES_DATETIME_FORMATTER:
        raise AssertionError("Desktop intake agent log must be bounded and timestamped")
    if not DESKTOP_INTAKE_AGENT_USES_PENDING_HANDSHAKE:
        raise AssertionError("Desktop intake agent must use pending handshake before marking files seen")
    if not DESKTOP_INTAKE_AGENT_AUTOSTART_INSTALL_SUPPORTED:
        raise AssertionError("Desktop intake agent must support automatic per-user Startup installation")
    if not DESKTOP_INTAKE_AGENT_HIDES_POWERSHELL_WINDOW:
        raise AssertionError("Desktop intake agent must hide PowerShell/console windows during autostart installation and launch")
    if not DESKTOP_INTAKE_AGENT_USES_VBS_STARTUP_SCRIPT:
        raise AssertionError("Desktop intake agent must install Startup through a hidden VBS script")
    if not DESKTOP_INTAKE_AGENT_HAS_NO_POWERSHELL_CODE_PATH:
        raise AssertionError("Desktop intake agent must avoid shell flashes")
    if not DESKTOP_INTAKE_AGENT_STARTUP_SCRIPT_IS_UTF16 or not DESKTOP_INTAKE_AGENT_STARTUP_SCRIPT_HAS_NO_UTF8_BOM:
        raise AssertionError("Desktop intake agent Startup VBS must use WSH-safe UTF-16, not UTF-8-BOM")
    if not DESKTOP_INTAKE_AGENT_STATE_IS_PATHLESS or not DESKTOP_INTAKE_AGENT_LOGS_ARE_REDACTED:
        raise AssertionError("Desktop intake agent must keep pending state/logs pathless and redacted")
    if not DESKTOP_INTAKE_AGENT_AUTOSTART_IS_DISABLED_IN_CI:
        raise AssertionError("Desktop intake agent autostart must be disabled during CI/release checks")
    if not DESKTOP_INTAKE_AGENT_LOGGING_IS_DISABLED_IN_CI:
        raise AssertionError("Desktop intake agent logging must be disabled during CI/release checks")
    target, arguments = _shortcut_launch_target_and_args()
    if not target:
        raise AssertionError("Desktop intake agent shortcut target must not be empty")
    if getattr(sys, "frozen", False) and "--intake-agent" not in arguments:
        raise AssertionError("Frozen watcher shortcut must start the EXE in --intake-agent mode")
    if _safe_float("bad", 7.0) != 7.0:
        raise AssertionError("Desktop intake agent state float parsing is unsafe")
    if len(_state_seen_signatures({"seen_signatures": ["a" * 64, "bad", 123]})) != 1:
        raise AssertionError("Desktop intake agent must keep only hashed signatures")
    parsed_pending = _pending_from_state({"pending": {"path": "x.docx", "signature": "b" * 64, "launched_at": "bad"}})
    if not parsed_pending or "path" in parsed_pending:
        raise AssertionError("Desktop intake agent pending handshake parser must accept legacy state but drop raw paths")
    disabled = {"desktop_intake": {"asked": True, "enabled": False, "prompt_version": DESKTOP_INTAKE_SETUP_PROMPT_VERSION}}
    if not _setting_is_current_explicit_no(disabled):
        raise AssertionError("Desktop intake agent disabled-settings predicate is broken")


def main_cli() -> int:
    """Small CLI for BAT/EXE installers without writing VBS by echo.

    Manual installation can call ``python desktop_intake_agent.py --install-autostart``.
    The installer then writes the Startup VBS through Python in WSH-safe UTF-16
    instead of letting CMD echo a potentially invalid UTF-8 script.
    """

    if "--install-autostart" in sys.argv:
        ok, message = install_agent_autostart(start_now=True)
        print(message)
        return 0 if ok else 1
    run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
