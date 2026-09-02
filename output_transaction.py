"""Transactional commit for one patient output set.

Renderers write only into a private staging directory.  The patient's real
folder is modified only after every selected output has completed successfully.
If commit fails, newly moved files are removed and overwritten originals are
restored from their transaction backups.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import os
from pathlib import Path
import shutil
import uuid

from diagnostic_logging import record_soft_exception


@dataclass
class OutputTransaction:
    final_dir: Path
    overwrite_paths: tuple[Path, ...] = ()
    stage_dir: Path | None = None
    _created_dirs: list[Path] = field(default_factory=list, init=False)

    def begin(self) -> Path:
        final = Path(self.final_dir).expanduser()
        self.final_dir = final
        self._created_dirs = []
        final.parent.mkdir(parents=True, exist_ok=True)
        stage = final.parent / f".dokkomplekt-staging-{uuid.uuid4().hex}"
        stage.mkdir(parents=False, exist_ok=False)
        self.stage_dir = stage
        return stage

    def rollback(self) -> None:
        if self.stage_dir is not None:
            shutil.rmtree(self.stage_dir, ignore_errors=True)
        self.stage_dir = None

    @staticmethod
    def _path_key(path: Path) -> str:
        try:
            return str(path.resolve()).casefold()
        except OSError:
            return str(path.absolute()).casefold()

    @staticmethod
    def _file_digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _owned_file_signature(cls, path: Path) -> tuple[int, int, str]:
        stat = path.stat()
        return int(stat.st_dev), int(stat.st_ino), cls._file_digest(path)

    @classmethod
    def _matches_owned_signature(cls, path: Path, signature: tuple[int, int, str]) -> bool:
        try:
            return cls._owned_file_signature(path) == signature
        except OSError:
            return False

    @staticmethod
    def _move_no_replace(source: Path, target: Path) -> None:
        """Move one file while atomically refusing an existing destination.

        Windows ``os.rename`` is no-clobber. POSIX ``rename`` is not, so on
        POSIX we create a hard link first (which is atomic and fails with
        ``EEXIST``), then remove the staging name. Stage and final paths are
        siblings on the same filesystem by construction.
        """
        if os.name == "nt":
            os.rename(source, target)
            return
        os.link(source, target, follow_symlinks=False)
        try:
            source.unlink()
        except Exception:
            try:
                target.unlink()
            except OSError as cleanup_exc:
                record_soft_exception("output_transaction.no_replace_link_cleanup", cleanup_exc, detail=str(target))
            raise

    @classmethod
    def _remove_owned_committed(cls, path: Path, signature: tuple[int, int, str]) -> bool:
        if not path.exists():
            return True
        if not cls._matches_owned_signature(path, signature):
            record_soft_exception(
                "output_transaction.concurrent_commit_change",
                RuntimeError("Committed target changed concurrently; preserving it instead of deleting it."),
                detail=str(path),
            )
            return False
        path.unlink()
        return True

    @classmethod
    def _restore_backup_no_clobber(cls, original: Path, backup: Path) -> bool:
        if not backup.exists():
            return True
        try:
            cls._move_no_replace(backup, original)
        except FileExistsError as restore_conflict:
            record_soft_exception(
                "output_transaction.restore_backup_conflict",
                restore_conflict,
                detail=f"original={original}; backup={backup}",
            )
            return False
        return True

    @classmethod
    def _move_to_unique_backup(cls, original: Path) -> Path:
        for _attempt in range(100):
            backup = cls._backup_path(original)
            try:
                cls._move_no_replace(original, backup)
                return backup
            except FileExistsError:
                continue
        raise FileExistsError(f"Не удалось атомарно зарезервировать имя резервной копии: {original}")

    def _ensure_target_parent(self, parent: Path) -> None:
        """Create target directories while recording only directories we own.

        ``exist_ok=True`` cannot distinguish our mkdir from a concurrent creator.
        Building one level at a time with ``exist_ok=False`` lets rollback remove
        only directories this transaction actually created; ``rmdir`` then
        refuses to delete a directory another process populated later.
        """
        missing: list[Path] = []
        cursor = parent
        while not cursor.exists():
            missing.append(cursor)
            cursor = cursor.parent
        for directory in reversed(missing):
            try:
                directory.mkdir(exist_ok=False)
            except FileExistsError:
                continue
            self._created_dirs.append(directory)

    def _remove_empty_created_dirs(self) -> None:
        for directory in reversed(self._created_dirs):
            try:
                directory.rmdir()
            except OSError:
                # A concurrent process may have populated a directory after we
                # created it. Never recurse into or delete such shared content.
                continue
        self._created_dirs = []

    @staticmethod
    def _backup_path(path: Path) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        candidate = path.with_name(f"{path.stem}_backup_{stamp}{path.suffix}")
        index = 2
        while candidate.exists():
            candidate = path.with_name(f"{path.stem}_backup_{stamp}_{index}{path.suffix}")
            index += 1
        return candidate

    def commit(self) -> dict[Path, Path]:
        if self.stage_dir is None or not self.stage_dir.exists():
            raise RuntimeError("Output transaction has not been started.")
        stage = self.stage_dir
        files = sorted((p for p in stage.rglob("*") if p.is_file()), key=lambda p: str(p.relative_to(stage)).casefold())
        if not files:
            raise RuntimeError("Output transaction contains no files to commit.")

        overwrite = {self._path_key(Path(p)) for p in self.overwrite_paths}
        targets = [(source, self.final_dir / source.relative_to(stage)) for source in files]
        # Collision preflight happens before the first mutation of the final dir.
        for _source, target in targets:
            if target.exists() and self._path_key(target) not in overwrite:
                raise FileExistsError(f"Новый файл неожиданно совпал с существующим и не был подтверждён для перезаписи: {target}")

        backups: list[tuple[Path, Path]] = []
        committed_owned: list[tuple[Path, tuple[int, int, str]]] = []
        mapping: dict[Path, Path] = {}
        try:
            # Back up all user-approved collisions, including older numbered
            # variants detected by the duplicate policy, as one rollback unit.
            for original in self.overwrite_paths:
                original = Path(original)
                if not original.exists():
                    continue
                backup = self._move_to_unique_backup(original)
                backups.append((original, backup))

            for source, target in targets:
                self._ensure_target_parent(target.parent)
                expected_signature = self._owned_file_signature(source)
                self._move_no_replace(source, target)
                committed_owned.append((target, expected_signature))
                mapping[source] = target

            shutil.rmtree(stage, ignore_errors=True)
            self.stage_dir = None
            self._created_dirs = []
            return mapping
        except Exception as commit_exc:
            rollback_conflicts: list[str] = []
            for target, signature in reversed(committed_owned):
                try:
                    if not self._remove_owned_committed(target, signature):
                        rollback_conflicts.append(str(target))
                except OSError as cleanup_exc:
                    rollback_conflicts.append(str(target))
                    record_soft_exception("output_transaction.remove_partial_commit", cleanup_exc, detail=str(target))
            for original, backup in reversed(backups):
                try:
                    if not self._restore_backup_no_clobber(original, backup):
                        rollback_conflicts.append(f"{original} (backup: {backup})")
                except OSError as restore_exc:
                    rollback_conflicts.append(f"{original} (backup: {backup})")
                    record_soft_exception("output_transaction.restore_backup", restore_exc, detail=str(original))
            self._remove_empty_created_dirs()
            if rollback_conflicts:
                raise RuntimeError(
                    "Сохранение отменено из-за параллельного изменения файлов. "
                    "Чужие/изменённые файлы не удалены; резервные копии прежних документов сохранены. "
                    "Конфликты: " + "; ".join(rollback_conflicts[:10])
                ) from commit_exc
            raise
