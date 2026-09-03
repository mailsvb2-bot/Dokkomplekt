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

    @classmethod
    def _move_no_replace(cls, source: Path, target: Path) -> None:
        """Move one file while atomically refusing an existing destination.

        Windows ``os.rename`` is no-clobber. POSIX ``rename`` is not, so on
        POSIX we create a hard link first (which is atomic and fails with
        ``EEXIST``), then remove the staging name. If removing the staging name
        fails, cleanup atomically claims the public target before checking its
        fingerprint; it never unlinks a pathname that another process may have
        replaced meanwhile. Stage and final paths are siblings on the same
        filesystem by construction.
        """
        if os.name == "nt":
            os.rename(source, target)
            return
        expected_signature = cls._owned_file_signature(source)
        os.link(source, target, follow_symlinks=False)
        try:
            source.unlink()
        except Exception:
            claim = cls._claim_current_path(target)
            if claim is not None:
                claim_dir, claimed = claim
                try:
                    if cls._matches_owned_signature(claimed, expected_signature):
                        claimed.unlink()
                    else:
                        restored = cls._restore_claimed_no_clobber(claimed, target)
                        record_soft_exception(
                            "output_transaction.no_replace_link_cleanup_conflict",
                            RuntimeError(
                                "Target changed while cleaning up a failed POSIX link-move; "
                                + ("foreign target restored." if restored else f"foreign target preserved at {claimed}.")
                            ),
                            detail=str(target),
                        )
                finally:
                    try:
                        claim_dir.rmdir()
                    except OSError as cleanup_exc:
                        if not claimed.exists():
                            record_soft_exception(
                                "output_transaction.no_replace_claim_dir_cleanup",
                                cleanup_exc,
                                detail=str(claim_dir),
                            )
            raise

    @staticmethod
    def _claim_current_path(path: Path) -> tuple[Path, Path] | None:
        """Atomically move the current public name into a private directory.

        Rollback must never perform ``check(path); unlink(path)`` because another
        process can replace the public name between those two operations.  A
        freshly-created private directory gives ``os.rename`` a guaranteed empty
        destination so we can inspect/delete the claimed object without racing
        against changes to the public target name.
        """
        for _attempt in range(100):
            claim_dir = path.parent / f".dokkomplekt-rollback-claim-{uuid.uuid4().hex}"
            try:
                claim_dir.mkdir(exist_ok=False)
            except FileExistsError:
                continue
            claimed = claim_dir / path.name
            try:
                os.rename(path, claimed)
            except FileNotFoundError:
                claim_dir.rmdir()
                return None
            except Exception:
                try:
                    claim_dir.rmdir()
                except OSError as cleanup_exc:
                    record_soft_exception(
                        "output_transaction.claim_dir_cleanup",
                        cleanup_exc,
                        detail=str(claim_dir),
                    )
                raise
            return claim_dir, claimed
        raise FileExistsError(f"Не удалось создать приватное имя rollback для: {path}")

    @staticmethod
    def _restore_claimed_no_clobber(claimed: Path, original: Path) -> bool:
        """Restore a claimed foreign file without replacing a new public file."""
        try:
            if os.name == "nt":
                os.rename(claimed, original)
            else:
                os.link(claimed, original, follow_symlinks=False)
                try:
                    claimed.unlink()
                except OSError as unlink_exc:
                    # Both names still point to the same preserved data.  Keep
                    # the private copy and surface a rollback conflict instead
                    # of deleting either name.
                    record_soft_exception(
                        "output_transaction.restore_claimed_unlink",
                        unlink_exc,
                        detail=f"original={original}; claimed={claimed}",
                    )
                    return False
        except FileExistsError:
            return False
        return True

    @classmethod
    def _remove_owned_committed(cls, path: Path, signature: tuple[int, int, str]) -> bool:
        claim = cls._claim_current_path(path)
        if claim is None:
            return True
        claim_dir, claimed = claim
        try:
            if cls._matches_owned_signature(claimed, signature):
                claimed.unlink()
                return True

            restored = cls._restore_claimed_no_clobber(claimed, path)
            record_soft_exception(
                "output_transaction.concurrent_commit_change",
                RuntimeError(
                    "Committed target changed concurrently; the foreign file was "
                    + ("restored to its public name." if restored else f"preserved at {claimed} because the public name is occupied.")
                ),
                detail=str(path),
            )
            return False
        finally:
            try:
                claim_dir.rmdir()
            except OSError as cleanup_exc:
                # If a conflict keeps ``claimed`` in the private directory, the
                # directory itself is the preservation container and must stay.
                if not claimed.exists():
                    record_soft_exception(
                        "output_transaction.claim_dir_cleanup_after_rollback",
                        cleanup_exc,
                        detail=str(claim_dir),
                    )

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

    def validate_reported_files(self, reported_files) -> tuple[Path, ...]:
        if self.stage_dir is None or not self.stage_dir.exists():
            raise RuntimeError("Output transaction has not been started.")
        stage = self.stage_dir.resolve()
        validated: list[Path] = []
        for raw in reported_files:
            candidate = Path(raw)
            if not candidate.exists() or not candidate.is_file():
                raise FileNotFoundError(f"Генератор сообщил о файле, которого нет: {candidate}")
            resolved = candidate.resolve()
            try:
                resolved.relative_to(stage)
            except ValueError as exc:
                raise RuntimeError(f"Генератор попытался выдать файл вне staging-транзакции: {candidate}") from exc
            validated.append(candidate)
        if not validated:
            raise RuntimeError("Генератор не сообщил ни одного итогового файла.")
        return tuple(dict.fromkeys(validated))

    @staticmethod
    def _allowed_ancillary_file(path: Path) -> bool:
        name = path.name.casefold()
        return path.suffix.casefold() == ".txt" and ("report" in name or "отч" in name)

    def commit(self, *, expected_files=None) -> dict[Path, Path]:
        if self.stage_dir is None or not self.stage_dir.exists():
            raise RuntimeError("Output transaction has not been started.")
        stage = self.stage_dir
        files = sorted((p for p in stage.rglob("*") if p.is_file()), key=lambda p: str(p.relative_to(stage)).casefold())
        if not files:
            raise RuntimeError("Output transaction contains no files to commit.")
        if expected_files is not None:
            expected = {self._path_key(path) for path in self.validate_reported_files(expected_files)}
            unexpected = [
                path for path in files
                if self._path_key(path) not in expected and not self._allowed_ancillary_file(path)
            ]
            if unexpected:
                raise RuntimeError(
                    "Staging содержит неучтённые файлы; комплект не опубликован: "
                    + ", ".join(path.name for path in unexpected[:10])
                )

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
