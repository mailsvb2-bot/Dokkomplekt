from __future__ import annotations

from pathlib import Path

import pytest


def test_target_created_after_preflight_is_never_overwritten(monkeypatch, tmp_path: Path) -> None:
    import output_transaction as module
    from output_transaction import OutputTransaction

    final = tmp_path / "patient"
    tx = OutputTransaction(final)
    stage = tx.begin()
    (stage / "a.docx").write_text("OURS", encoding="utf-8")
    real_move = module.OutputTransaction._move_no_replace

    def create_foreign_then_move(src: Path, dst: Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("FOREIGN", encoding="utf-8")
        real_move(src, dst)

    monkeypatch.setattr(module.OutputTransaction, "_move_no_replace", staticmethod(create_foreign_then_move))
    with pytest.raises(FileExistsError):
        tx.commit()
    assert (final / "a.docx").read_text(encoding="utf-8") == "FOREIGN"
    assert (stage / "a.docx").read_text(encoding="utf-8") == "OURS"


def test_rollback_preserves_concurrently_modified_committed_target(monkeypatch, tmp_path: Path) -> None:
    import output_transaction as module
    from output_transaction import OutputTransaction

    final = tmp_path / "patient"
    final.mkdir()
    old = final / "a.docx"
    old.write_text("OLD", encoding="utf-8")
    tx = OutputTransaction(final, overwrite_paths=(old,))
    stage = tx.begin()
    (stage / "a.docx").write_text("NEW-A", encoding="utf-8")
    (stage / "b.docx").write_text("NEW-B", encoding="utf-8")
    real_move = module.OutputTransaction._move_no_replace
    calls = {"n": 0}

    def fail_after_foreign_edit(src: Path, dst: Path) -> None:
        calls["n"] += 1
        if calls["n"] == 3:
            # a.docx is already our committed target. Another process edits it
            # before the second target fails; rollback must not delete that edit.
            (final / "a.docx").write_text("FOREIGN-EDIT", encoding="utf-8")
            raise OSError("simulated second-target failure")
        real_move(src, dst)

    monkeypatch.setattr(module.OutputTransaction, "_move_no_replace", staticmethod(fail_after_foreign_edit))
    with pytest.raises(RuntimeError, match="параллельного изменения"):
        tx.commit()
    assert (final / "a.docx").read_text(encoding="utf-8") == "FOREIGN-EDIT"
    backups = list(final.glob("a_backup_*.docx"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "OLD"
    assert not (final / "b.docx").exists()


def test_overwrite_target_recreated_after_backup_is_preserved(monkeypatch, tmp_path: Path) -> None:
    import output_transaction as module
    from output_transaction import OutputTransaction

    final = tmp_path / "patient"
    final.mkdir()
    old = final / "a.docx"
    old.write_text("OLD", encoding="utf-8")
    tx = OutputTransaction(final, overwrite_paths=(old,))
    stage = tx.begin()
    (stage / "a.docx").write_text("NEW", encoding="utf-8")
    real_move = module.OutputTransaction._move_no_replace
    calls = {"n": 0}

    def recreate_after_backup(src: Path, dst: Path) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            dst.write_text("FOREIGN-REPLACEMENT", encoding="utf-8")
        real_move(src, dst)

    monkeypatch.setattr(module.OutputTransaction, "_move_no_replace", staticmethod(recreate_after_backup))
    with pytest.raises(RuntimeError, match="параллельного изменения"):
        tx.commit()
    assert old.read_text(encoding="utf-8") == "FOREIGN-REPLACEMENT"
    backups = list(final.glob("a_backup_*.docx"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "OLD"


def test_rollback_claim_survives_public_name_swap_after_ownership_check(monkeypatch, tmp_path: Path) -> None:
    from output_transaction import OutputTransaction

    final = tmp_path / "patient"
    final.mkdir()
    target = final / "a.docx"
    target.write_text("OURS", encoding="utf-8")
    signature = OutputTransaction._owned_file_signature(target)
    real_match = OutputTransaction._matches_owned_signature.__func__

    def create_foreign_after_claim(cls, claimed: Path, expected) -> bool:
        matched = real_match(cls, claimed, expected)
        # The public name is free after the atomic claim. A concurrent writer
        # recreates it before rollback deletes the object it already claimed.
        target.write_text("FOREIGN", encoding="utf-8")
        return matched

    monkeypatch.setattr(OutputTransaction, "_matches_owned_signature", classmethod(create_foreign_after_claim))
    assert OutputTransaction._remove_owned_committed(target, signature) is True
    assert target.read_text(encoding="utf-8") == "FOREIGN"
    assert not list(final.glob(".dokkomplekt-rollback-claim-*"))
