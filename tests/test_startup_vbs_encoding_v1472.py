from pathlib import Path


def test_startup_vbs_is_utf16_and_not_utf8_bom(tmp_path, monkeypatch):
    import desktop_intake_agent

    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    script_path = desktop_intake_agent._write_startup_vbs(
        r"C:\Program Files\Python311\pythonw.exe",
        r'"C:\Program Files\MedicalDiaryAutofill\desktop_intake_agent.pyw"',
        r"C:\Program Files\MedicalDiaryAutofill",
    )

    raw = Path(script_path).read_bytes()
    assert raw.startswith(b"\xff\xfe")
    assert not raw.startswith(b"\xef\xbb\xbf")
    decoded = raw.decode("utf-16")
    assert decoded.splitlines()[0] == "On Error Resume Next"
    assert "WScript.Shell" in decoded
    assert "shell.Run" in decoded


def test_startup_vbs_contract_lock_knows_about_wsh_safe_encoding():
    import architecture_contracts
    import desktop_intake_agent

    assert desktop_intake_agent.AGENT_VERSION == "v1.7"
    assert desktop_intake_agent.DESKTOP_INTAKE_AGENT_STARTUP_SCRIPT_IS_UTF16 is True
    assert desktop_intake_agent.DESKTOP_INTAKE_AGENT_STARTUP_SCRIPT_HAS_NO_UTF8_BOM is True
    assert architecture_contracts.ARCHITECTURE_CONTRACT_LOCK_VERSION == "v2.4"
    architecture_contracts.assert_startup_vbs_uses_wsh_safe_encoding()
