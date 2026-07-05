"""Intake-agent update handoff regression tests.

Updating the EXE used to leave the stale background agent in charge until
reboot: it held the singleton lock, the freshly installed agent exited with
"already running", and a dropped primary document launched the OLD executable
path — either nothing started (old exe deleted) or yesterday's build opened.

The v1.9 handoff fixes this: every install records the current agent identity
and GUI launch command; a running agent retires when a newer install takes
over, and any surviving agent launches the GUI recorded by the latest install.
"""
from __future__ import annotations

from pathlib import Path

import desktop_intake_agent as agent


def _isolate(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(agent, "_data_root", lambda: tmp_path)


def test_owner_agent_is_not_retired(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(agent, "_current_agent_identity", lambda: "/install/A/app.exe")
    agent._write_agent_handoff(["/install/A/app.exe"])
    assert agent._agent_is_retired() is False


def test_stale_agent_retires_after_new_install(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    # New install (B) writes the handoff.
    monkeypatch.setattr(agent, "_current_agent_identity", lambda: "/install/B/app.exe")
    agent._write_agent_handoff(["/install/B/app.exe"])
    # The old agent (A) must notice and retire.
    monkeypatch.setattr(agent, "_current_agent_identity", lambda: "/install/A/app.exe")
    assert agent._agent_is_retired() is True
    # The new agent stays.
    monkeypatch.setattr(agent, "_current_agent_identity", lambda: "/install/B/app.exe")
    assert agent._agent_is_retired() is False


def test_launch_command_prefers_handoff_target(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    target = tmp_path / "new_app.exe"
    target.write_text("stub")
    monkeypatch.setattr(agent, "_current_agent_identity", lambda: str(target))
    agent._write_agent_handoff([str(target)])
    assert agent._launch_command() == [str(target)]


def test_launch_command_falls_back_when_handoff_target_missing(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    missing = tmp_path / "deleted_app.exe"
    monkeypatch.setattr(agent, "_current_agent_identity", lambda: str(missing))
    agent._write_agent_handoff([str(missing)])
    native = ["/usr/bin/python3", "main.py"]
    monkeypatch.setattr(agent, "_native_launch_command", lambda: native)
    assert agent._launch_command() == native


def test_missing_handoff_means_no_retirement(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(agent, "_current_agent_identity", lambda: "/anything")
    assert agent._agent_is_retired() is False


def test_agent_contract_lock_includes_handoff():
    assert agent.DESKTOP_INTAKE_AGENT_SUPPORTS_UPDATE_HANDOFF is True
    agent.assert_desktop_intake_agent_lock()
