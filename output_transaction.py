"""Transactional commit for one patient output set.

Renderers write only into a private staging directory.  The patient's real
folder is modified only after every selected output has completed successfully.
If commit fails, newly moved files are removed and overwritten originals are
restored from their transaction backups.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
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
    _final_existed: bool = field(default=False, init=False)
    _created_dirs: list[Path] = field(default_factory=list, init=False)

    def begin(self) -> Path:
        final = Path(self.final_dir).expanduser()
        self.final_dir = final
        self._final_existed = final.exists()
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
        committed: list[Path] = []
        mapping: dict[Path, Path] = {}
        try:
            # Back up all user-approved collisions, including older numbered
            # variants detected by the duplicate policy, as one rollback unit.
            for original in self.overwrite_paths:
                original = Path(original)
                if not original.exists():
                    continue
                backup = self._backup_path(original)
                original.rename(backup)
                backups.append((original, backup))

            for source, target in targets:
                self._ensure_target_parent(target.parent)
                os.replace(source, target)
                committed.append(target)
                mapping[source] = target

            shutil.rmtree(stage, ignore_errors=True)
            self.stage_dir = None
            self._created_dirs = []
            return mapping
        except Exception:
            for target in reversed(committed):
                try:
                    target.unlink()
                except OSError as cleanup_exc:
                    record_soft_exception("output_transaction.remove_partial_commit", cleanup_exc, detail=str(target))
            for original, backup in reversed(backups):
                try:
                    if original.exists():
                        original.unlink()
                    backup.rename(original)
                except OSError as restore_exc:
                    record_soft_exception("output_transaction.restore_backup", restore_exc, detail=str(original))
            self._remove_empty_created_dirs()
            raise
