"""Production-readiness audit for MedicalDiaryAutofill."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET_VERSION = "1.4.91"
TARGET_VERSION_LABEL = "v1.4.91_audit_hardening"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8", errors="replace")


def _fail(message: str) -> None:
    raise SystemExit(message)


def _target_version_tuple_literal() -> str:
    try:
        major, minor, patch = (int(part) for part in TARGET_VERSION.split("."))
    except ValueError:
        _fail(f"TARGET_VERSION must contain numeric dot-separated parts: {TARGET_VERSION}")
    return f"({major}, {minor}, {patch}, 0)"


def _assert_release_metadata() -> None:
    expected_tuple = _target_version_tuple_literal()
    checks = {
        "pyproject.toml version": f'version = "{TARGET_VERSION}"' in _read("pyproject.toml"),
        "app_config version label": TARGET_VERSION_LABEL in _read("app_config.py"),
        "version_info file tuple": f"filevers={expected_tuple}" in _read("version_info.txt"),
        "version_info product tuple": f"prodvers={expected_tuple}" in _read("version_info.txt"),
        "version_info label": TARGET_VERSION_LABEL in _read("version_info.txt"),
        "baseline label": TARGET_VERSION_LABEL in _read("BASELINE_VERSION.txt"),
        "README label": TARGET_VERSION_LABEL in _read("README.md"),
        "release notes label": _read("RELEASE_NOTES.md").lstrip().startswith(f"# Release notes — {TARGET_VERSION_LABEL}"),
    }
    missing = [name for name, ok in checks.items() if not ok]
    if missing:
        _fail("Release metadata is inconsistent:\n" + "\n".join(missing))


def _assert_doctor_owned_templates() -> None:
    embedded = _read("embedded_templates.py")
    profiles = _read("universal_profiles.py")
    checks = {
        "embedded template storage must be empty": "TEMPLATE_B64: dict[str, str] = {}" in embedded,
        "default pack must be empty": "documents=()" in profiles,
        "empty builtins hook must remain explicit": "current_builtin_documents" in profiles and "returns no medical documents" in profiles,
    }
    missing = [name for name, ok in checks.items() if not ok]
    if missing:
        _fail("Doctor-owned template contract is incomplete:\n" + "\n".join(missing))


def _assert_neutral_diary_matching() -> None:
    diary = _read("diary_text_selection.py").casefold()
    required = {
        "technical filename words are ignored": "_common_diary_name_words" in diary,
        "ICD matching is generic": "def _icd_match_keys" in diary,
        "forbidden-bridge sentinel exists": "def _has_forbidden_narrow_diary_bridge" in diary,
        "diagnosis matching score exists": "def diary_diagnosis_match_score" in diary,
    }
    missing = [name for name, ok in required.items() if not ok]
    if missing:
        _fail("Neutral diary matching contract is incomplete:\n" + "\n".join(missing))
    forbidden = (
        "legacy_cognitive",
        "legacy_asthenic",
        "legacy_affective",
        "legacy_organic",
        "legacy_behavioral",
        "asthenia",
        "олигофрен",
        "психопат",
        "астен",
    )
    present = [token for token in forbidden if token in diary]
    if present:
        _fail("Diary matching contains forbidden narrow bridges:\n" + "\n".join(present))


def _assert_neutral_profile_contract() -> None:
    models = _read("medical_models.py")
    preview = _read("medical_preview.py")
    primary = _read("medical_renderer_primary.py")
    adapter = _read("universal_case_adapter.py")
    markers = _read("medical_markers.py")
    required = {
        "canonical profile observation field": "profile_observation" in models,
        "canonical profile status field": "profile_status" in models,
        "preview uses canonical profile status": "data.profile_status" in preview,
        "primary renderer uses canonical profile observation": "data.profile_observation" in primary,
        "primary renderer uses canonical profile status": "data.profile_status" in primary,
        "universal case uses neutral status.specialty": '"status.specialty"' in adapter,
        "markers use neutral profile status": "Профильный статус" in markers,
    }
    missing = [name for name, ok in required.items() if not ok]
    if missing:
        _fail("Neutral profile contract is incomplete:\n" + "\n".join(missing))


def _assert_no_personal_leaks() -> None:
    runtime_sources = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in ROOT.glob("*.py")
        if path.name != "prod_audit.py"
    )
    present = [token for token in ("Можар",) if token in runtime_sources]
    if present:
        _fail("Production source contains personal hardcoded leftovers:\n" + "\n".join(present))


def main() -> None:
    _assert_release_metadata()
    _assert_doctor_owned_templates()
    _assert_neutral_diary_matching()
    _assert_neutral_profile_contract()
    _assert_no_personal_leaks()
    print("PROD AUDIT OK")


if __name__ == "__main__":
    main()
