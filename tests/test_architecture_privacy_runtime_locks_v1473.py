from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def test_soft_exception_diagnostics_are_redacted() -> None:
    import diagnostic_logging as d

    text = d.redact_diagnostic_text(r"C:\Users\Пользователь\Desktop\Выписанные пациенты\Иванов_Иван_Комиссионный.docx 12.05.2026 история болезни №123")
    assert "C:" not in text
    assert "Иванов" not in text
    assert "12.05.2026" not in text
    assert "123" not in text
    assert "<path>" in text or "<file>" in text


def test_doctor_action_journal_does_not_store_raw_patient_identifiers(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from doctor_action_journal import append_doctor_action

    class Review:
        warnings = ["warn"]
        selected_outputs = ["выписной"]

        def value(self, key: str) -> str:
            return {
                "output_fio": "Иванов Иван Иванович",
                "case_number": "12345",
                "admission_date": "01.02.2026",
                "diagnosis": "F00 Тестовый диагноз",
            }.get(key, "")

    path = append_doctor_action(
        output_dir=tmp_path / "patient",
        action="Созданы документы Иванов Иван Иванович",
        details={"path": r"C:\Users\Пользователь\Desktop\Иванов.docx", "diagnosis": "F00 Тест"},
        review=Review(),
        created_files=[tmp_path / "Иванов_выписной.docx"],
        errors=[r"Ошибка C:\Users\Пользователь\Иванов.docx 01.02.2026"],
    )
    assert path is not None
    text = Path(path).read_text(encoding="utf-8")
    assert "Иванов" not in text
    assert "12345" not in text
    assert "01.02.2026" not in text
    assert "Иванов_выписной" not in text
    assert "created_files" not in text
    jsonl = path.with_name("doctor_action_journal.jsonl")
    payload = json.loads(jsonl.read_text(encoding="utf-8").splitlines()[-1])
    assert "created_file_count" in payload
    assert "created_files" not in payload
    assert "patient_ref" in payload["review"]


def test_desktop_intake_pending_state_is_pathless(monkeypatch) -> None:
    import desktop_intake_agent as agent

    pending = agent._pending_from_state({"pending": {"path": r"C:\Users\Пользователь\Иванов.docx", "signature": "a" * 64, "launched_at": "0"}})
    assert pending == {"signature": "a" * 64, "launched_at": 0.0}
    assert "path" not in pending


def test_desktop_intake_pending_resolves_by_signature(monkeypatch, tmp_path) -> None:
    import desktop_intake_agent as agent

    seen: set[str] = set()
    pending = {"pending": {"signature": "b" * 64, "launched_at": "0"}}
    monkeypatch.setattr(agent, "_signature_present_in_folder", lambda folder, signature: False)
    resolved, changed = agent._resolve_pending_state(pending, seen, tmp_path)
    assert resolved == {}
    assert changed is True
    assert "b" * 64 in seen


def test_architecture_privacy_runtime_gates() -> None:
    import architecture_contracts as contracts

    assert contracts.ARCHITECTURE_CONTRACT_LOCK_VERSION == "v2.4"
    contracts.assert_soft_diagnostics_are_privacy_safe()
    contracts.assert_doctor_action_journal_is_privacy_safe()
    contracts.assert_desktop_agent_pending_state_is_pathless()
