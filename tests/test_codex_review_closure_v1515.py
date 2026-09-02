from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest


def test_output_transaction_rollback_preserves_concurrent_foreign_file(monkeypatch, tmp_path: Path) -> None:
    import output_transaction as module
    from output_transaction import OutputTransaction

    final = tmp_path / "patient"
    tx = OutputTransaction(final)
    stage = tx.begin()
    (stage / "a.docx").write_text("A", encoding="utf-8")
    (stage / "b.docx").write_text("B", encoding="utf-8")
    real_move = module.OutputTransaction._move_no_replace
    calls = {"count": 0}

    def fail_after_concurrent_write(src, dst):
        calls["count"] += 1
        if calls["count"] == 1:
            real_move(src, dst)
            (final / "foreign.txt").write_text("FOREIGN", encoding="utf-8")
            return None
        raise OSError("simulated commit failure")

    monkeypatch.setattr(module.OutputTransaction, "_move_no_replace", staticmethod(fail_after_concurrent_write))
    with pytest.raises(OSError, match="simulated"):
        tx.commit()
    assert (final / "foreign.txt").read_text(encoding="utf-8") == "FOREIGN"
    assert not (final / "a.docx").exists()
    assert not (final / "b.docx").exists()


def test_reused_staged_primary_removes_source_for_move_semantics(tmp_path: Path) -> None:
    from desktop_intake import prepare_patient_work_folder

    root = tmp_path / "intake"
    root.mkdir()
    source = root / "primary.docx"
    source.write_bytes(b"same-primary")
    patient = root / "Patient"
    patient.mkdir()
    staged = patient / "already.docx"
    staged.write_bytes(b"same-primary")

    patient_dir, reused = prepare_patient_work_folder(root, source, folder_name="Patient", keep_source=False)
    assert patient_dir == patient
    assert reused == staged
    assert not source.exists()
    assert staged.read_bytes() == b"same-primary"


def test_medpack_export_rejects_non_word_zip_named_docx(tmp_path: Path) -> None:
    from universal_profiles import DocumentPack, DocumentTemplateSpec
    from universal_template_engine import export_document_pack_zip

    profile = tmp_path / "profile"
    templates = profile / "templates"
    templates.mkdir(parents=True)
    fake = templates / "fake.docx"
    with zipfile.ZipFile(fake, "w") as zf:
        zf.writestr("not-word.txt", "fake")
    pack = DocumentPack(pack_id="x", name="x", documents=(
        DocumentTemplateSpec(id="fake", button_label="Fake", template="templates/fake.docx"),
    ))
    target = tmp_path / "bad.medpack.zip"
    with pytest.raises(ValueError, match="нельзя экспортировать"):
        export_document_pack_zip(pack, target, template_base_dir=profile)
    assert not target.exists()


def test_desktop_intake_choices_expose_broken_template_as_unavailable(tmp_path: Path) -> None:
    from desktop_intake_choices import profile_choices_for_desktop_intake
    from universal_profiles import DocumentPack, DocumentTemplateSpec

    pack = DocumentPack(pack_id="x", name="x", documents=(
        DocumentTemplateSpec(id="mine", button_label="Мой документ", template="templates/missing.docx"),
    ))
    choices = profile_choices_for_desktop_intake(pack, base_dir=tmp_path)
    assert len(choices) == 1
    assert choices[0].available is False
    assert "не найден" in choices[0].problem.lower()


def test_desktop_intake_popup_disables_unavailable_profile_choices() -> None:
    source = Path("desktop_intake_mixin.py").read_text(encoding="utf-8")
    assert 'state="normal" if available else "disabled"' in source
    assert "problem or 'Word-шаблон недоступен'" in source
    assert "if available:" in source and "local_vars[kind] = var" in source
