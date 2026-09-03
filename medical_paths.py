"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

from contextlib import contextmanager
from diagnostic_logging import record_soft_exception
import base64
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Mapping, Optional

from medical_constants import TEMPLATE_FILES

_EMBEDDED_TEMPLATE_CACHE: dict[str, Path | None] = {}
_BUNDLED_TEMPLATE_CACHE: dict[str, Path] = {}


def app_dir() -> Path:
    """Папка программы с учётом PyInstaller onefile."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def template_dir() -> Path:
    return app_dir() / "templates"


def embedded_template_path(filename: str) -> Optional[Path]:
    """Вернуть временный путь к DOCX-шаблону из embedded base64 storage.

    Base64 decoding is cached because one creation run may ask for the same
    bundled template several times through validation and rendering paths.
    """
    if filename in _EMBEDDED_TEMPLATE_CACHE:
        return _EMBEDDED_TEMPLATE_CACHE[filename]
    try:
        from embedded_templates import TEMPLATE_B64
    except Exception as exc:
        record_soft_exception("medical_paths.embedded_templates_import", exc, detail=filename)
        _EMBEDDED_TEMPLATE_CACHE[filename] = None
        return None
    raw = TEMPLATE_B64.get(filename)
    if not raw:
        _EMBEDDED_TEMPLATE_CACHE[filename] = None
        return None

    data = base64.b64decode(raw.encode("ascii") if isinstance(raw, str) else raw, validate=True)
    cache_dir = Path(tempfile.gettempdir()) / "medical_diary_autofill_templates"
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / filename
    # Never trust an already-present temp file blindly: a previous crashed run
    # can leave a truncated DOCX in %TEMP%, and PyInstaller onefile runs reuse
    # this folder between launches. Validate the expected size and replace
    # atomically when needed.
    if not out.exists() or out.stat().st_size != len(data):
        atomic_write_bytes(out, data)
    _EMBEDDED_TEMPLATE_CACHE[filename] = out
    return out


def bundled_template_path(kind: str) -> Path:
    cached = _BUNDLED_TEMPLATE_CACHE.get(kind)
    if cached is not None and cached.exists():
        return cached
    try:
        filename = TEMPLATE_FILES[kind]
    except KeyError as exc:
        raise KeyError(f"Неизвестный тип документа: {kind}") from exc
    physical = template_dir() / filename
    if physical.exists():
        _BUNDLED_TEMPLATE_CACHE[kind] = physical
        return physical
    embedded = embedded_template_path(filename)
    result = embedded or physical
    if result.exists():
        _BUNDLED_TEMPLATE_CACHE[kind] = result
    return result


def atomic_write_bytes(path: str | Path, data: bytes) -> Path:
    """Durably publish bytes with unique temp storage and one target-scoped writer lock."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    publish_lock = target.with_name(f".{target.name}.write.lock")
    with interprocess_file_lock(publish_lock, timeout_seconds=10.0, stale_seconds=120.0):
        fd, raw_tmp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
        tmp = Path(raw_tmp)
        raw_fd_open = True
        try:
            handle = os.fdopen(fd, "wb")
            raw_fd_open = False
            with handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
            return target
        except Exception as exc:
            if raw_fd_open:
                try:
                    os.close(fd)
                except OSError as close_exc:
                    record_soft_exception("medical_paths.atomic_write_close_fd", close_exc, detail=str(target))
            try:
                tmp.unlink()
            except OSError as cleanup_exc:
                record_soft_exception("medical_paths.atomic_write_temp_cleanup", cleanup_exc, detail=str(tmp))
            raise exc


def atomic_write_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> Path:
    return atomic_write_bytes(path, str(text).encode(encoding))


def atomic_write_json(path: str | Path, payload: Mapping[str, Any], *, sort_keys: bool = False) -> Path:
    return atomic_write_text(
        path,
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=sort_keys) + "\n",
    )


def prune_old_files(directory: str | Path, *, pattern: str, keep: int) -> tuple[Path, ...]:
    """Keep the newest ``keep`` regular files matching pattern; return removed paths."""
    root = Path(directory)
    if keep < 1 or not root.exists():
        return ()
    candidates = [item for item in root.glob(pattern) if item.is_file()]
    candidates.sort(key=lambda item: (item.stat().st_mtime_ns, item.name), reverse=True)
    removed: list[Path] = []
    for item in candidates[keep:]:
        try:
            item.unlink()
            removed.append(item)
        except OSError:
            continue
    return tuple(removed)


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_owner(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


@contextmanager
def interprocess_file_lock(
    path: str | Path,
    *,
    timeout_seconds: float = 10.0,
    stale_seconds: float = 120.0,
):
    """Acquire an O_EXCL lock file and release only the token we created."""
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    deadline = time.monotonic() + max(0.1, float(timeout_seconds))
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            payload = json.dumps({"pid": os.getpid(), "token": token, "created_at": time.time()}).encode("utf-8")
            os.write(fd, payload)
            os.fsync(fd)
        except FileExistsError:
            owner = _read_owner(lock_path)
            try:
                age = max(0.0, time.time() - lock_path.stat().st_mtime)
            except OSError:
                age = 0.0
            owner_pid = int(owner.get("pid") or 0) if str(owner.get("pid") or "").lstrip("-").isdigit() else 0
            if age >= stale_seconds and not _pid_is_running(owner_pid):
                try:
                    lock_path.unlink()
                    continue
                except OSError as stale_cleanup_exc:
                    record_soft_exception("medical_paths.stale_lock_cleanup", stale_cleanup_exc, detail=str(lock_path))
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Не удалось получить блокировку состояния: {lock_path}")
            time.sleep(0.025)
    try:
        yield
    finally:
        try:
            if fd is not None:
                os.close(fd)
        finally:
            owner = _read_owner(lock_path)
            if str(owner.get("token") or "") == token:
                try:
                    lock_path.unlink()
                except OSError as release_exc:
                    record_soft_exception("medical_paths.lock_release", release_exc, detail=str(lock_path))
