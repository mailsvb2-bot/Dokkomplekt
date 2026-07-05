from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding='utf-8', newline='')


def replace(path: str, old: str, new: str) -> None:
    text = read(path)
    if old not in text:
        if new in text:
            return
        raise RuntimeError(f'missing pattern in {path}: {old[:80]!r}')
    if False:
        raise RuntimeError(f'missing pattern in {path}: {old[:80]!r}')
    write(path, text.replace(old, new, 1))


def replace_all(path: str, old: str, new: str) -> None:
    text = read(path)
    if old not in text:
        return
    write(path, text.replace(old, new))


def regex_replace(path: str, pattern: str, repl: str) -> None:
    text = read(path)
    if repl in text:
        return
    new, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f'missing regex in {path}: {pattern[:80]!r}')
    write(path, new)


def patch_desktop_intake() -> None:
    replace('desktop_intake.py', 'DESKTOP_INTAKE_LOCK_VERSION = "v1.12"', 'DESKTOP_INTAKE_LOCK_VERSION = "v1.13"')
    replace('desktop_intake.py', 'DESKTOP_INTAKE_SETUP_PROMPT_VERSION = "v3-first-launch-required"', 'DESKTOP_INTAKE_SETUP_PROMPT_VERSION = "v4-intake-patient-folder-confirm"')
    replace('desktop_intake.py', 'DESKTOP_INTAKE_REJECTS_UNREADABLE_DOCX_FALLBACKS = True\n', 'DESKTOP_INTAKE_REJECTS_UNREADABLE_DOCX_FALLBACKS = True\nDESKTOP_INTAKE_REASKS_AFTER_FOLDER_NAMING_REGRESSION = True\n')
    replace('desktop_intake.py', 'if DESKTOP_INTAKE_LOCK_VERSION != "v1.12":', 'if DESKTOP_INTAKE_LOCK_VERSION != "v1.13":')
    replace('desktop_intake.py', '    if not DESKTOP_INTAKE_REJECTS_UNREADABLE_DOCX_FALLBACKS:\n        raise AssertionError("Desktop intake must not launch on unreadable/corrupt DOCX files")\n', '    if not DESKTOP_INTAKE_REJECTS_UNREADABLE_DOCX_FALLBACKS:\n        raise AssertionError("Desktop intake must not launch on unreadable/corrupt DOCX files")\n    if not DESKTOP_INTAKE_REASKS_AFTER_FOLDER_NAMING_REGRESSION:\n        raise AssertionError("Desktop intake must re-ask after folder-naming regression builds")\n')

    replace('desktop_intake_agent.py', 'AGENT_VERSION = "v1.8"', 'AGENT_VERSION = "v1.9"')
    replace('desktop_intake_agent.py', 'DESKTOP_INTAKE_AGENT_RESPECTS_ACTIVE_GUI_LOCK = True\n', 'DESKTOP_INTAKE_AGENT_RESPECTS_ACTIVE_GUI_LOCK = True\nDESKTOP_INTAKE_AGENT_REASKS_OLD_DISABLED_SETTINGS = True\n')
    replace('desktop_intake_agent.py', 'if AGENT_VERSION != "v1.8":', 'if AGENT_VERSION != "v1.9":')
    replace('desktop_intake_agent.py', '    if not DESKTOP_INTAKE_AGENT_RESPECTS_ACTIVE_GUI_LOCK:\n        raise AssertionError("Desktop intake agent must respect active foreground GUI lock")\n', '    if not DESKTOP_INTAKE_AGENT_RESPECTS_ACTIVE_GUI_LOCK:\n        raise AssertionError("Desktop intake agent must respect active foreground GUI lock")\n    if not DESKTOP_INTAKE_AGENT_REASKS_OLD_DISABLED_SETTINGS:\n        raise AssertionError("Desktop intake agent must allow upgraded setup prompts after old disabled settings")\n')

    replace('actions_creation_maintenance.py', 'def _ensure_patient_folder_naming_configured(self) -> bool:', 'def _ensure_patient_folder_naming_configured(self, *, force: bool = False) -> bool:')
    replace('actions_creation_maintenance.py', 'if current.get("doctor_confirmed") and current.get("schema_version") == FOLDER_NAMING_SCHEMA_VERSION:', 'if not force and current.get("doctor_confirmed") and current.get("schema_version") == FOLDER_NAMING_SCHEMA_VERSION:')
    replace('desktop_intake_mixin.py', 'self._ensure_patient_folder_naming_configured():', 'self._ensure_patient_folder_naming_configured(force=True):')


def patch_diaries() -> None:
    replace('diary_text_selection.py', '_ICD_CODE_RE = re.compile(r"(?<![A-Za-zА-Яа-я0-9])([A-ZА-Я])\\s*(\\d{1,3})(?:[.,]\\s*(\\d+))?(?![A-Za-zА-Яа-я0-9])", re.IGNORECASE)\n', '_ICD_CODE_RE = re.compile(r"(?<![A-Za-zА-Яа-я0-9])([A-ZА-Я])\\s*(\\d{1,3})(?:[.,]\\s*(\\d+))?(?![A-Za-zА-Яа-я0-9])", re.IGNORECASE)\nMIN_AUTO_DIARY_MATCH_SCORE = 70\n')
    replace('diary_text_selection.py', 'if score <= 0:', 'if score < MIN_AUTO_DIARY_MATCH_SCORE:')

    regex_replace('files_mixin.py', r'\n\s*# Doctor-owned deployments often keep exactly one neutral DOCX.*?record_soft_exception\("files_mixin\.diary_text_fallback", exc, detail=str\(folder\)\)', '''
                # Do not silently take the only/nearest DOCX: diary texts are diagnosis-specific.
                try:
                    candidates = iter_diary_text_docx_files(folder, max_depth=1)
                    scored = [
                        (diary_diagnosis_match_score(diagnosis, path.stem), path.name.lower(), path)
                        for path in candidates
                    ]
                    scored = [item for item in scored if item[0] >= 70]
                    if scored:
                        found = sorted(scored, key=lambda item: (-item[0], item[1]))[0][2]
                        fallback_reason = "по строгому совпадению диагноза"
                except Exception as exc:
                    record_soft_exception("files_mixin.diary_text_fallback", exc, detail=str(folder))''')

    replace('diary_batch.py', 'from medical_calendar import is_non_working_day, next_working_day', 'from medical_calendar import next_working_day')
    replace_all('diary_batch.py', '        adjusted = next_working_day(planned, used=result)\n        if discharge_date is not None and adjusted > discharge_date:\n            break\n        result.append(adjusted)', '        result.append(planned)')
    replace_all('diary_batch.py', '        adjusted = next_working_day(planned, used=result)\n        if discharge_date_value is not None and adjusted > discharge_date_value:\n            break\n        result.append(adjusted)', '        result.append(planned)')
    replace('diary_batch.py', "f\"Психический статус: {data.profile_status or 'без существенной динамики'}.\",", "f\"Профильный статус: {data.profile_status or 'без существенной динамики'}.\",")
    replace_all('diary_batch.py', '        if is_non_working_day(moment.date()):\n            continue\n', '')
    replace('diary_batch.py', 'final_date = next_working_day(discharge_date_value, used=normalized_dates) if is_non_working_day(discharge_date_value) else discharge_date_value', 'final_date = discharge_date_value')

def patch_discharge_route() -> None:
    text = read('actions_creation_execution.py')
    if '_route_legacy_medical_selection_to_profile_docs' in text:
        return
    marker = '    def _run_creation_jobs(self, selected_medical: list[str], selected_diaries: bool, selected_custom: list[str]) -> tuple[list[Path], list[Path], object | None, list[str]]:\n'
    methods = r'''
    def _profile_document_matches_builtin_kind(self, document: object, kind: str) -> bool:
        """Return True when a doctor-owned profile doc replaces a legacy button."""
        try:
            from universal_main_documents import custom_requirement_flags_for_documents
            flags = custom_requirement_flags_for_documents((document,))
        except Exception as exc:
            record_soft_exception("actions_creation_execution.profile_doc_flags", exc, detail=str(kind))
            flags = {}
        signature = " ".join(
            str(getattr(document, attr, "") or "")
            for attr in ("id", "role_id", "category", "button_label", "template", "description")
        ).lower().replace("ё", "е").replace("_", " ")
        if kind == "discharge":
            return bool(flags.get("discharge")) or ("выпис" in signature and "эпикриз" in signature)
        if kind == "rvk":
            return bool(flags.get("rvk")) or "рвк" in signature or "военком" in signature
        if kind == "commission":
            return bool(flags.get("commission")) or "комис" in signature or "совмест" in signature
        if kind == "vk_mse":
            return bool(flags.get("vk_mse")) or "мсэ" in signature or "мсек" in signature
        if kind == "sick_leave_vk":
            return bool(flags.get("sick_leave_vk")) or ("больнич" in signature and ("вк" in signature or "комис" in signature))
        if kind == "admission_doctor_referral":
            return "приемн" in signature or "приёмн" in signature or "госпитализац" in signature
        if kind == "primary":
            return "первич" in signature and "осмотр" in signature
        return False

    def _route_legacy_medical_selection_to_profile_docs(self, selected_medical: list[str], selected_custom: list[str]) -> tuple[list[str], list[str]]:
        """Prefer doctor-owned templates over the disabled legacy fixed backend."""
        if not selected_medical:
            return selected_medical, selected_custom
        try:
            pack = self._load_or_create_universal_pack()
        except Exception as exc:
            record_soft_exception("actions_creation_execution.load_profile_for_medical_route", exc)
            return selected_medical, selected_custom
        routed: list[str] = []
        remaining: list[str] = []
        for kind in selected_medical:
            matched = [
                str(getattr(document, "id", "") or "").strip()
                for document in tuple(getattr(pack, "documents", ()) or ())
                if self._profile_document_matches_builtin_kind(document, kind)
            ]
            matched = [item for item in matched if item]
            if matched:
                routed.extend(matched)
                self._log(f"\nℹ Кнопка «{kind}» создана через doctor-owned шаблон профиля, не через старый fixed-template backend.\n")
            else:
                remaining.append(kind)
        return remaining, list(dict.fromkeys([*selected_custom, *routed]))

'''
    if marker not in text:
        raise RuntimeError('run creation marker not found')
    text = text.replace(marker, methods + marker, 1)
    text = text.replace('        try:\n            if selected_medical:', '        try:\n            selected_medical, selected_custom = self._route_legacy_medical_selection_to_profile_docs(selected_medical, selected_custom)\n            if selected_medical:', 1)
    write('actions_creation_execution.py', text)


def patch_contracts_and_tests() -> None:
    replace('architecture_contracts.py', '"agent_lock_v17": \'AGENT_VERSION = "v1.8"\' in agent,', '"agent_lock_v18": \'AGENT_VERSION = "v1.9"\' in agent,')
    replace('tools/run_regression_contour.py', '"tests/test_native_license_security_v1499.py",', '"tests/test_native_license_security_v1499.py",\n        "tests/test_desktop_intake_patient_chain_v1502.py",')
    replace('tests/test_startup_vbs_encoding_v1472.py', 'desktop_intake_agent.AGENT_VERSION == "v1.8"', 'desktop_intake_agent.AGENT_VERSION == "v1.9"')
    replace('tests/test_intake_agent_update_handoff_v1494x.py', 'The v1.8 handoff fixes this:', 'The v1.9 handoff fixes this:')
    replace('tests/test_diary_user_emulation_matrix_v1497.py', 'from diary_batch import _calendar_text_diary_dates, _dynamic_epicrisis_base_date, dynamic_epicrisis_dates, is_non_working_day', 'from diary_batch import _calendar_text_diary_dates, _dynamic_epicrisis_base_date, dynamic_epicrisis_dates')
    replace('tests/test_diary_user_emulation_matrix_v1497.py', '    check(all(not is_non_working_day(item) for item in clinical_dates), "clinical skips weekends and holidays")\n    check(clinical_dates[:4] == (date(2026, 6, 5), date(2026, 6, 8), date(2026, 6, 9), date(2026, 6, 11)), "clinical working dates")', '    check(clinical_dates[:4] == (date(2026, 6, 5), date(2026, 6, 6), date(2026, 6, 7), date(2026, 6, 11)), "clinical exact program dates")')
    replace('tests/test_diary_filler_donor_parity_v1490.py', 'from diary_batch import default_observation_diary_dates, fill_diary_batch, is_non_working_day', 'from diary_batch import default_observation_diary_dates, fill_diary_batch')
    replace('tests/test_diary_filler_donor_parity_v1490.py', 'def test_default_diary_calendar_skips_weekends_and_fixed_holidays() -> None:', 'def test_default_diary_calendar_preserves_program_offsets_without_workday_shift() -> None:')
    replace('tests/test_diary_filler_donor_parity_v1490.py', '    assert all(not is_non_working_day(item) for item in dates)\n    assert dates[0] >= date(2026, 1, 12)', '    assert dates[:4] == (date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 8))')
    new_test = ROOT / 'tests' / 'test_desktop_intake_patient_chain_v1502.py'
    if not new_test.exists():
        new_test.write_text('''from __future__ import annotations\n\nfrom datetime import date\nimport inspect\n\n\ndef test_v1502_intake_diary_and_discharge_contracts():\n    import desktop_intake\n    import desktop_intake_agent\n    from desktop_intake_mixin import DesktopIntakeMixin\n    from diary_batch import _calendar_text_diary_dates, _split_regular_and_final_text_diary_dates\n\n    assert desktop_intake.DESKTOP_INTAKE_SETUP_PROMPT_VERSION == "v4-intake-patient-folder-confirm"\n    assert desktop_intake.DESKTOP_INTAKE_REASKS_AFTER_FOLDER_NAMING_REGRESSION is True\n    assert desktop_intake_agent.AGENT_VERSION == "v1.9"\n    assert desktop_intake_agent.DESKTOP_INTAKE_AGENT_REASKS_OLD_DISABLED_SETTINGS is True\n    assert "_ensure_patient_folder_naming_configured(force=True)" in inspect.getsource(DesktopIntakeMixin._open_desktop_intake_popup)\n    assert _calendar_text_diary_dates(date(2026, 7, 3), None, limit=3, day_offsets=(1, 2, 3)) == (date(2026, 7, 4), date(2026, 7, 5), date(2026, 7, 6))\n    regular, final_date = _split_regular_and_final_text_diary_dates((date(2026, 7, 4), date(2026, 7, 5)), discharge_date_value=date(2026, 7, 5), force_final_diary=True)\n    assert regular == (date(2026, 7, 4),)\n    assert final_date == date(2026, 7, 5)\n\n\ndef test_v1502_discharge_button_route_exists():\n    from actions_creation_execution import ActionsCreationExecutionMixin\n    assert hasattr(ActionsCreationExecutionMixin, "_route_legacy_medical_selection_to_profile_docs")\n''', encoding='utf-8')


def main() -> None:
    patch_desktop_intake()
    patch_diaries()
    patch_discharge_route()
    patch_contracts_and_tests()
    print('v1502 hotfix applied or already present')


if __name__ == '__main__':
    main()
