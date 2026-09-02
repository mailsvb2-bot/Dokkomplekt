from __future__ import annotations

import os
import time
from pathlib import Path


def test_agent_singleton_lock_rejects_reused_live_pid_identity(monkeypatch, tmp_path: Path) -> None:
    import desktop_intake_agent as agent

    lock = tmp_path / "agent.lock"
    lock.write_text("pid=4242\nversion=x\nprocess_started=win:old\ntoken=" + "a" * 32 + "\n", encoding="utf-8")
    monkeypatch.setattr(agent, "_pid_is_running", lambda pid: pid == 4242)
    monkeypatch.setattr(agent, "_process_start_identity", lambda pid: "win:new" if pid == 4242 else "")
    assert agent._lock_is_stale(lock) is True


def test_legacy_agent_lock_live_pid_has_bounded_stale_grace(monkeypatch, tmp_path: Path) -> None:
    import desktop_intake_agent as agent

    lock = tmp_path / "agent.lock"
    lock.write_text("pid=4242\nversion=x\ntoken=" + "a" * 32 + "\n", encoding="utf-8")
    stale_time = time.time() - agent.LOCK_STALE_SECONDS - 5.0
    os.utime(lock, (stale_time, stale_time))
    monkeypatch.setattr(agent, "_pid_is_running", lambda pid: pid == 4242)
    monkeypatch.setattr(agent, "_process_start_identity", lambda pid: "")
    assert agent._lock_is_stale(lock) is True


def test_fresh_legacy_agent_lock_still_protects_running_agent(monkeypatch, tmp_path: Path) -> None:
    import desktop_intake_agent as agent

    lock = tmp_path / "agent.lock"
    lock.write_text("pid=4242\nversion=x\ntoken=" + "a" * 32 + "\n", encoding="utf-8")
    monkeypatch.setattr(agent, "_pid_is_running", lambda pid: pid == 4242)
    monkeypatch.setattr(agent, "_process_start_identity", lambda pid: "")
    assert agent._lock_is_stale(lock) is False


def test_acquired_agent_lock_persists_process_start_identity(monkeypatch, tmp_path: Path) -> None:
    import desktop_intake_agent as agent

    lock = tmp_path / "agent.lock"
    monkeypatch.setattr(agent, "_lock_path", lambda: lock)
    monkeypatch.setattr(agent, "_process_start_identity", lambda pid: "proc:test-owner" if pid == os.getpid() else "")
    fd = agent._acquire_agent_lock()
    assert fd is not None
    assert agent._lock_owner_process_identity(lock) == "proc:test-owner"
    token = agent._lock_owner_token(lock)
    assert token
    agent._release_agent_lock(fd, lock, token)
    assert not lock.exists()
