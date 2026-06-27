"""Production release gate for MedicalDiaryAutofill.

Runs the checks that must be green before a source archive or Windows EXE is
published. The script deliberately uses only the standard library so it can run
before optional dev dependencies are installed.
"""

from __future__ import annotations

from diagnostic_logging import record_soft_exception
import ast
import compileall
import os
import shutil
import subprocess
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIRED_FILES = [
    "main.py",
    "medical_documents.py",
    "diary_filler.py",
    "printer_support.py",
    "icd10_f.py",
    "embedded_templates.py",
    "requirements.txt",
    "requirements_build.txt",
    "README.md",
    "BASELINE_VERSION.txt",
    "USER_BEHAVIOR_CONTRACT.md",
    "CHANGELOG.md",
    "BASELINE_MANIFEST.json",
    "REGRESSION_CONTOUR.md",
    "REGRESSION_MATRIX.md",
    "tools/run_regression_contour.py",
    "tests/test_regression_contour_baseline_v1486.py",
    "tests/test_production_interaction_matrix_v1487.py",
    "FIX_REPORT.md",
    "version_info.txt",
    "LAUNCH_CHECKLIST.md",
    "PROD_READY_AUDIT_REPORT.md",
    "prod_audit.py",
    "dnd_contract_check.py",
    "performance_check.py",
    "architecture_contracts.py",
    "project_auditor.py",
    "project_auditor_models.py",
    "project_auditor_files.py",
    "project_auditor_imports.py",
    "project_auditor_rules.py",
    "project_auditor_dependencies.py",
    "project_auditor_reports.py",
    "smoke_project_auditor.py",
    "smoke_technical_debt_cleanup.py",
    "smoke_stress_hardening.py",
    "smoke_universal_hardening.py",
    "smoke_auditor_layer.py",
    "smoke_split_entrypoints.py",
    "error_taxonomy.py",
    "doctor_action_journal.py",
    "smoke_points_5_11.py",
    "auditor_models.py",
    "auditor_template.py",
    "auditor_profile.py",
    "auditor_runtime.py",
    "auditor_layer.py",
    "universal_fields.py",
    "universal_profiles.py",
    "universal_scanner.py",
    "universal_template_engine.py",
    "universal_generation.py",
    "universal_profile_builder.py",
    "regulatory_section_registry.py",
    "regulatory_specialty_overlays.py",
    "regulatory_document_roles.py",
    "regulatory_document_classifier.py",
    "regulatory_advisory_policy.py",
    "regulatory_template_advisor.py",
    "regulatory_caucasus_aliases.py",
    "medical_language_catalog.py",
    "medical_language_detector.py",
    "i18n_strings.py",
    "medical_orthography_rules.py",
    "medical_orthography.py",
    "language_preferences.py",
    "personal_document_buttons.py",
    "smoke_desktop_diary_workflow.py",
    "desktop_intake_mixin.py",
    "desktop_intake.py",
    "desktop_intake_agent.py",
    "desktop_intake_agent.pyw",
    "install_background_watcher.bat",
    "uninstall_background_watcher.bat",
    "desktop_patient_folder.py",
    "medical_admission_resolver.py",
    "universal_diary_generation.py",
    "universal_diary_templates.py",
    "diary_schedule.py",
    ".github/workflows/windows-build.yml",
    ".gitattributes",
]
FORBIDDEN_DIR_NAMES = {"__pycache__", "build", "dist", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".vscode", ".idea"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".spec", ".bak", ".tmp", ".log"}
IGNORED_DIR_NAMES = {".git", ".venv", "venv", ".venv_build", ".venv_runtime", "release"}


def _project_python_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(ROOT.glob("*.py"))
        if path.name != Path(__file__).name
    )


def _print_step(title: str) -> None:
    print(f"\n== {title} ==")


def _run(cmd: list[str], *, timeout: int = 120) -> None:
    print("$ " + " ".join(cmd), flush=True)
    try:
        env = dict(os.environ)
        env.setdefault("CI", "1")
        env.setdefault("MEDICAL_AUTOFILL_DISABLE_AUTOSTART", "1")
        subprocess.run(cmd, cwd=ROOT, timeout=timeout, check=True, env=env)
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"Command timed out after {timeout}s: {' '.join(cmd)}") from exc



def _remove_generated_outputs() -> None:
    for child in ROOT.iterdir():
        if child.is_dir() and (child.name.startswith("test_run") or child.name.endswith("_run") or child.name in {".pytest_cache", ".ruff_cache", ".mypy_cache", ".medical_diary_autofill_data"}):
            shutil.rmtree(child, ignore_errors=True)
    for pycache in ROOT.rglob("__pycache__"):
        if any(part in IGNORED_DIR_NAMES for part in pycache.relative_to(ROOT).parts):
            continue
        shutil.rmtree(pycache, ignore_errors=True)
    for pattern in ("*.log", "ОТЧЁТ_*.txt", "coverage.xml", ".coverage"):
        for item in ROOT.glob(pattern):
            try:
                item.unlink()
            except OSError as exc:
                record_soft_exception("release_check:129", exc)


def _assert_required_files() -> None:
    missing = [name for name in REQUIRED_FILES if not (ROOT / name).exists()]
    if missing:
        raise SystemExit("Missing required files: " + ", ".join(missing))


def _assert_archive_hygiene() -> None:
    bad: list[str] = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        parts = set(rel.parts)
        if parts & IGNORED_DIR_NAMES:
            continue
        if any(part.startswith("test_run") or part.endswith("_run") for part in rel.parts):
            bad.append(str(rel))
            continue
        if path.is_dir() and path.name in FORBIDDEN_DIR_NAMES:
            bad.append(str(rel))
        if path.is_file() and path.suffix.lower() in FORBIDDEN_SUFFIXES:
            bad.append(str(rel))
        if path.is_file() and path.name in {".DS_Store", "Thumbs.db", "startup_error.log", "coverage.xml", ".coverage"}:
            bad.append(str(rel))
        if path.is_file() and path.name.startswith("FIX_REPORT_v") and path.suffix.lower() == ".md":
            bad.append(str(rel))
        if path.is_file() and path.name.startswith("ОТЧЁТ_") and path.suffix.lower() == ".txt":
            bad.append(str(rel))
    if bad:
        raise SystemExit("Forbidden generated artifacts found:\n" + "\n".join(sorted(bad)))




def _assert_smoke_entrypoints_contract() -> None:
    smoke_test = (ROOT / "smoke_test.py").read_text(encoding="utf-8", errors="replace")
    smoke_combined = (ROOT / "smoke_test_combined.py").read_text(encoding="utf-8", errors="replace")
    required_smoke_test = ["from smoke_combined_runner import run", 'if __name__ == "__main__":', "run()"]
    missing = [snippet for snippet in required_smoke_test if snippet not in smoke_test]
    if missing:
        raise SystemExit("smoke_test.py is not an executable smoke entrypoint: " + ", ".join(missing))
    for snippet in ["from smoke_combined_runner import run", 'if __name__ == "__main__":', "run()"]:
        if snippet not in smoke_combined:
            raise SystemExit(f"smoke_test_combined.py misses smoke entrypoint snippet: {snippet}")
    runner = (ROOT / "smoke_combined_runner.py").read_text(encoding="utf-8", errors="replace")
    for snippet in ["def build_namespace_before", "_SMOKE_COMBINED_RUNNER_ACTIVE", "PARTS = ("]:
        if snippet not in runner:
            raise SystemExit(f"smoke_combined_runner.py misses split-entrypoint support: {snippet}")
    for part in (
        "smoke_combined_part02_ui_parser_regressions.py",
        "smoke_combined_part03_medical_parser_manual.py",
        "smoke_combined_part04_medical_generation.py",
        "smoke_combined_part05_diary_basic_templates.py",
        "smoke_combined_part06_diary_columns_settings.py",
    ):
        source = (ROOT / part).read_text(encoding="utf-8", errors="replace")
        if "build_namespace_before" not in source or "_SMOKE_COMBINED_RUNNER_ACTIVE" not in source:
            raise SystemExit(f"{part} is not executable as a standalone smoke entrypoint")


CI_SMOKE_SUITE = (
    "smoke_test.py",
    "smoke_test_combined.py",
    "smoke_desktop_diary_workflow.py",
    "smoke_universal_hardening.py",
    "smoke_stress_hardening.py",
    "smoke_auditor_layer.py",
    "smoke_project_auditor.py",
    "smoke_technical_debt_cleanup.py",
    "smoke_split_entrypoints.py",
    "smoke_followup_regressions.py",
    "smoke_quality_modernization.py",
    "smoke_points_5_11.py",
    "smoke_user_reported_regressions.py",
    "smoke_full_patient_replay.py",
)

REGRESSION_CONTOUR_COMMAND = "python tools/run_regression_contour.py"


def _assert_full_smoke_suite_is_wired() -> None:
    build = (ROOT / "build_exe_windows.bat").read_text(encoding="utf-8", errors="replace")
    workflow = (ROOT / ".github/workflows/windows-build.yml").read_text(encoding="utf-8", errors="replace")
    missing_build = [script for script in CI_SMOKE_SUITE if script not in build]
    missing_workflow = [script for script in CI_SMOKE_SUITE if script not in workflow]
    if missing_build:
        raise SystemExit("build_exe_windows.bat does not run CI smoke suite: " + ", ".join(missing_build))
    if missing_workflow:
        raise SystemExit("GitHub Actions workflow does not run CI smoke suite: " + ", ".join(missing_workflow))


def _assert_settings_contract() -> None:
    source = _project_python_source()
    required_snippets = [
        "def _settings_payload_for_disk",
        "os.replace(tmp_path, self._settings_path)",
        "settings.broken.",
        "Production-контракт",
    ]
    missing = [snippet for snippet in required_snippets if snippet not in source]
    if missing:
        raise SystemExit("Settings persistence contract is incomplete: " + ", ".join(missing))


def _assert_build_contract() -> None:
    build = (ROOT / "build_exe_windows.bat").read_text(encoding="utf-8", errors="replace")
    workflow = (ROOT / ".github/workflows/windows-build.yml").read_text(encoding="utf-8")
    for snippet in ["release_check.py", "version_info.txt", "--noupx", "MedicalDiaryAutofill.exe"]:
        if snippet not in build:
            raise SystemExit(f"build_exe_windows.bat misses production snippet: {snippet}")
    release_zip = (ROOT / "make_release_zip.py").read_text(encoding="utf-8")
    for snippet in ['".spec"', '".DS_Store"', '"Thumbs.db"', '".vscode"', '".idea"']:
        if snippet not in release_zip:
            raise SystemExit(f"make_release_zip.py misses archive hygiene snippet: {snippet}")
    for snippet in [
        "permissions:",
        "contents: read",
        "concurrency:",
        "cancel-in-progress: true",
        "timeout-minutes:",
        "release_check.py",
        "Upload source release artifact",
        "Upload EXE artifact",
        "headless-tests",
        "python -m pytest tests",
        "python tools/run_regression_contour.py",
        "--cov=medical_parser",
        "Upload coverage artifact",
        "python -m ruff check .",
        "python -m mypy --config-file pyproject.toml",
        "--cov=error_taxonomy",
        "--cov=doctor_action_journal",
    ]:
        if snippet not in workflow:
            raise SystemExit(f"GitHub Actions workflow misses production snippet: {snippet}")
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8", errors="replace")
    for snippet in ["*.py text eol=lf", "*.bat text eol=crlf", "*.docx binary", "*.zip binary"]:
        if snippet not in attrs:
            raise SystemExit(f".gitattributes misses repository hygiene snippet: {snippet}")


def _assert_ui_selected_state_contract() -> None:
    source = _project_python_source()
    required_snippets = [
        "def _redraw_selection_controls",
        "Выбранное состояние без чекбокса/галочки",
        "Выбранное состояние без грубой заливки и без галочки",
        "Галочки на выбранных кнопках намеренно не рисуем",
        "нажатые кнопки получают лёгкий цветовой градиент",
        "При фактическом нажатии большая кнопка получает лёгкий",
        "или нажмите здесь, чтобы выбрать файл",
        "selected=lambda: bool(self.status_files)",
        'selected=lambda: bool(self.diary_files or getattr(self, "diary_template_dir", ""))',
        "persistent selected state",
    ]
    missing = [snippet for snippet in required_snippets if snippet not in source]
    if missing:
        raise SystemExit("UI selected-state contract is incomplete: " + ", ".join(missing))




def _assert_tk_widget_padding_contract() -> None:
    """Tk widget constructors accept single screen distances for padx/pady.

    Geometry managers such as .grid/.pack may use 2-tuples for asymmetric
    padding, but widget constructor options may not.  A tuple in tk.Label(...,
    pady=(14, 2)) becomes the Tcl value "14 2" and crashes the dialog with
    "bad screen distance" before the doctor can add personal templates.
    """
    widget_constructors = {
        "Label",
        "Button",
        "Frame",
        "Entry",
        "Text",
        "Canvas",
        "Checkbutton",
        "Radiobutton",
        "Combobox",
    }
    violations: list[str] = []
    for path in sorted(ROOT.glob("*.py")):
        if path.name == Path(__file__).name:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            raise SystemExit(f"Cannot parse {path.name}: {exc}") from exc
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr not in widget_constructors:
                continue
            if not isinstance(func.value, ast.Name) or func.value.id not in {"tk", "ttk"}:
                continue
            for keyword in node.keywords:
                if keyword.arg in {"padx", "pady"} and isinstance(keyword.value, ast.Tuple):
                    violations.append(f"{path.name}:{node.lineno} {func.value.id}.{func.attr} {keyword.arg}=tuple")
    if violations:
        raise SystemExit("Tk widget constructor padding must be a single screen distance:\n" + "\n".join(violations))




def _assert_no_local_import_cycles() -> None:
    """Release gate: local Python modules must not form cyclic imports."""
    module_names = {path.stem for path in ROOT.glob("*.py") if path.name != "__init__.py"}
    graph: dict[str, set[str]] = {name: set() for name in module_names}
    for path in sorted(ROOT.glob("*.py")):
        if path.name == "__init__.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            raise SystemExit(f"Cannot parse {path.name}: {exc}") from exc
        source = path.stem
        for node in ast.walk(tree):
            target = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_name = alias.name.split(".", 1)[0]
                    if root_name in module_names:
                        graph[source].add(root_name)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                root_name = node.module.split(".", 1)[0]
                if root_name in module_names:
                    graph[source].add(root_name)
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    cycles: list[tuple[str, ...]] = []

    def strongconnect(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for neighbor in graph[node]:
            if neighbor == node:
                cycles.append((node, node))
                continue
            if neighbor not in indices:
                strongconnect(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[neighbor])
        if lowlinks[node] == indices[node]:
            component: list[str] = []
            while True:
                item = stack.pop()
                on_stack.remove(item)
                component.append(item)
                if item == node:
                    break
            if len(component) > 1:
                cycles.append(tuple(sorted(component)))

    for name in sorted(module_names):
        if name not in indices:
            strongconnect(name)
    if cycles:
        formatted = [" -> ".join(component) for component in sorted(set(cycles))]
        raise SystemExit("Local import cycles found:\n" + "\n".join(formatted))

def _assert_startup_state_contract() -> None:
    from app_initialization import AppInitializationMixin

    globals_map = AppInitializationMixin._init_medical_output_state.__globals__
    required_globals = ["DOCUMENT_ORDER", "DIARY_KIND"]
    missing = [name for name in required_globals if name not in globals_map]
    if missing:
        raise SystemExit("Startup app-state contract is incomplete: " + ", ".join(missing))
    if "discharge" not in tuple(globals_map["DOCUMENT_ORDER"]):
        raise SystemExit("Startup DOCUMENT_ORDER contract is invalid")

def _assert_icd10_catalog_contract() -> None:
    from icd10_f import assert_icd10_full_catalog_lock, search_icd10_f, format_diagnosis
    from icd10_f_search import assert_icd10_diagnosis_normalizer_lock
    from medical_language_catalog import SUPPORTED_LANGUAGE_IDS
    assert_icd10_full_catalog_lock()
    assert_icd10_diagnosis_normalizer_lock()
    for code in ("A00-B99", "F00-F99", "K00-K93", "S00-T98", "Z00-Z99", "U00-U99"):
        if not any(item.code == code for item in search_icd10_f(code, limit=20)):
            raise SystemExit(f"ICD-10 full catalog is missing section: {code}")
    for lang in SUPPORTED_LANGUAGE_IDS:
        if lang == "auto":
            continue
        sample = search_icd10_f("K35", limit=1, language_id=lang)
        if not sample or not format_diagnosis(sample[0], language_id=lang):
            raise SystemExit(f"ICD-10 language contract failed for: {lang}")


def _assert_followup_p0_regression_contract() -> None:
    """Locks for the post-audit P0 regressions reported by the user."""
    desktop = (ROOT / "desktop_intake_mixin.py").read_text(encoding="utf-8")
    if 'for kind in ["discharge", "primary", "commission"' in desktop:
        raise SystemExit("Desktop-intake popup must show only doctor-created block-03 buttons, not legacy built-ins")
    if "custom_documents_for_main_ui" not in desktop or "Отметьте хотя бы одну кнопку из блока 03" not in desktop:
        raise SystemExit("Desktop-intake block-03 list contract is missing")
    if "_ensure_patient_folder_naming_configured" not in desktop:
        raise SystemExit("Desktop-intake must ask folder naming before moving/creating patient folders")

    orchestrator = (ROOT / "actions_creation_orchestrator.py").read_text(encoding="utf-8")
    if "doctor_confirmed" not in orchestrator or "_ensure_patient_folder_naming_configured" not in orchestrator:
        raise SystemExit("Patient subfolder naming confirmation contract is missing")

    fields_core = (ROOT / "dialog_fields_core.py").read_text(encoding="utf-8")
    if "_validate_and_normalize" not in fields_core or "Проверьте поле:" not in fields_core:
        raise SystemExit("Popup validation must keep the window open and point to the invalid field")

    chrome = (ROOT / "window_chrome_mixin.py").read_text(encoding="utf-8")
    if 'sys.platform.startswith("win")' not in chrome or "overrideredirect(False)" not in chrome:
        raise SystemExit("Windows restore contract must keep native shell frame instead of frameless minimize trap")


def _assert_architecture_contracts() -> None:
    from architecture_contracts import assert_architecture_contracts
    assert_architecture_contracts()
    print("ARCHITECTURE CONTRACTS OK")


def _assert_prod_audit_contract() -> None:
    from prod_audit import main as prod_audit_main
    prod_audit_main()


def _assert_dnd_contract() -> None:
    from dnd_contract_check import main as dnd_contract_main
    dnd_contract_main()


def _assert_performance_contract() -> None:
    # Avoid a nested subprocess chain (release_check -> performance_check -> python -c),
    # which made the gate harder to diagnose when startup import probing stalled.
    # performance_check.py still remains executable standalone; here we reuse its
    # exact probe code and run one isolated child process with a bounded timeout.
    from performance_check import startup_import_probe_code

    _run([sys.executable, "-c", startup_import_probe_code()], timeout=45)


def _assert_sick_leave_popup_contract() -> None:
    source = _project_python_source()
    required_snippets = [
        "def _should_prompt_discharge_sick_leave_number",
        "return discharge_selected and sick_selected and number_missing",
        "Номер ЛН относится только к документу «Выписной эпикриз»",
        "Number popup must not open from the sick-leave Yes button",
    ]
    missing = [snippet for snippet in required_snippets if snippet not in source and snippet not in (ROOT / "smoke_test_combined.py").read_text(encoding="utf-8")]
    if missing:
        raise SystemExit("Sick-leave popup contract is incomplete: " + ", ".join(missing))

def _assert_layout_balance_contract() -> None:
    source = _project_python_source()
    required_snippets = [
        'heights = {"01": 214, "02": 100, "03": 142, "04": 130}',
        'блок 03 увеличен под реальные кнопки врача',
        'Единые боковые отступы у всех блоков',
        'files.grid_columnconfigure(0, minsize=self._px(190, 128))',
        'files.grid_columnconfigure(2, minsize=self._px(146, 104))',
        'field_height = self._px(36 if self._compact_ui else 40, 26)',
    ]
    missing = [snippet for snippet in required_snippets if snippet not in source]
    if missing:
        raise SystemExit("Layout balance contract is incomplete: " + ", ".join(missing))


def _assert_discharge_date_contract() -> None:
    source = _project_python_source()
    required_snippets = [
        "def _ensure_discharge_date",
        "def _prompt_discharge_date",
        'title="Дата выписки"',
        "она подставляется в выписной эпикриз",
        "ДДММГГГГ, ДДММГГ или коротко ДМГГ",
        'parse_date("10052026")',
        'parse_date("1126")',
        'parse_full_date("11062026")',
        'parse_full_date("1126")',
        'primary_drop_hint_label',
        'drop.grid_propagate(False)',
        'drop_height = self._px(96 if self._compact_ui else 106, 78)',
        'self.primary_drop_hint_label.config(text="", fg=FIELD)',
        'строка статуса не меняет высоту',
        'def _on_discharge_date_field_commit',
    ]
    missing = [snippet for snippet in required_snippets if snippet not in source]
    if missing:
        raise SystemExit("Discharge-date contract is incomplete: " + ", ".join(missing))



def _assert_audit_hardening_contract() -> None:
    source = _project_python_source()
    required_snippets = [
        "def _truncate_label_text",
        "single_line=self._compact_ui",
        "def _select_default_printer_sync",
        "_printer_refresh_in_progress",
        "Встроенных медицинских шаблонов нет",
        "from datetime import date",
        r"\d{4,8}",
    ]
    missing = [snippet for snippet in required_snippets if snippet not in source]
    if missing:
        raise SystemExit("Audit-hardening contract is incomplete: " + ", ".join(missing))
    diary_dates = (ROOT / "diary_table_dates.py").read_text(encoding="utf-8", errors="replace")
    if "def cell_int" in diary_dates or "def should_remove_holiday" in diary_dates:
        raise SystemExit("diary_table_dates.py reintroduced duplicated numeric helpers")


def _assert_universal_profile_contract() -> None:
    source = _project_python_source()
    required_snippets = [
        "class FieldRegistry",
        "procedure.anesthesia",
        "class DocumentPack",
        "def required_field_ids",
        "class DocumentScanResult",
        "def review_rows",
        "def merge_scan_results",
        "def scan_docx",
        "def learn_rule_from_selection",
        "def _open_universal_document_mapper",
        "Запомнить выделение как правило",
        "Добавить DOCX-шаблон в профиль",
        "current_builtin_documents",
        "class TemplateValidationResult",
        "def validate_template",
        "def render_template_to_docx",
        "def export_document_pack_zip",
        "def attach_template_to_pack",
        "class PackReadinessReport",
        "def analyze_pack_readiness",
        "def render_documents_from_pack",
        "class SpecialtyPreset",
        "def create_pack_from_preset",
        "def ingest_templates_into_pack",
        "def build_profile_from_sources_and_templates",
        "def profile_setup_checklist",
        "def scan_many_docx",
        "Импортировать medpack",
        "Отчёт готовности кнопок",
        "Создать custom DOCX",
        "Мастер профиля / checklist",
        "def _iter_docx_paragraphs",
        "bool(self.placeholders)",
        "doc_data[\"template\"] = arcname.as_posix()",
        "Неизвестный документ профиля",
        "Папка результата указывает на файл",
        '"\\\\" in normalized',
        "total_size > 100 * 1024 * 1024",
        "button_specs = [",
        "class DocumentRole",
        "def classify_docx",
        "def advise_template",
        "REGULATORY_SOFT_ADVISORY_LOCK_VERSION",
        "Нет, не буду, делай как есть",
        "Подсказки по приказам",
        "def _prompt_regulatory_completion_values",
        "Сохранить введённые дополнения",
        "COMPLETION_POPUP_LOCK_VERSION",
        "COMPLETION_VALUES_ARE_OPTIONAL = True",
        "CUSTOM_DOCUMENT_KIND_PREFIX",
        "custom_profile:",
        "def assert_dynamic_medpack_button_lock",
        "def custom_documents_for_main_ui",
        "def patient_data_to_case",
        "def _create_custom_documents_impl",
        "Документы из профиля врача",
        "FIRST_RUN_CREATE_BUTTON_LABEL = \"Создать свои кнопки\"",
        "BLOCK03_EMPTY_STATE_HAS_ONLY_CREATE_BUTTON = True",
        "def assert_block03_first_run_contract",
        "def _open_first_run_create_buttons_popup",
        "open_template_setup_center(self, first_run=True)",
        "command=self._open_first_run_create_buttons_popup",
        "def _source_portable_data_root",
        "MEDICAL_AUTOFILL_PORTABLE_SOURCE_DATA",
        "MEDICAL_AUTOFILL_DISABLE_AUTOSTART",
        "DESKTOP_INTAKE_AGENT_AUTOSTART_IS_DISABLED_IN_CI",
        "DESKTOP_INTAKE_AGENT_LOGGING_IS_DISABLED_IN_CI",
        ".medical_diary_autofill_data",
        "Выбрать Word-шаблоны и создать кнопки",
        "Проверьте названия кнопок перед созданием",
        "def review_template_button_names",
        "TEMPLATE_BUTTON_CREATION_REQUIRES_DOCTOR_CONFIRMATION",
        "doctor_review_table",
        "def selected_custom_docs",
        "CAUCASUS_ALIAS_LOCK_VERSION",
        "assert_caucasus_alias_lock",
        "assert_language_catalog_lock",
        "assert_language_detection_lock",
        "assert_i18n_strings_lock",
        "assert_orthography_medical_safe_lock",
        "Հիվանդության պատմություն",
        "სამედიცინო ბარათი",
        "Xəstəlik tarixi",
        "COMPLETION_POPUP_TITLE = \"Дополнить документ\"",
        "ARCHITECTURE_CONTRACT_LOCK_VERSION",
        "def assert_architecture_contracts",
        "def completion_inputs_for_missing_fields",
        "def unique_document_id_for_pack",
        "output_language=output_language",
        "spellcheck_enabled=spellcheck_enabled",
        "AUDITOR_LAYER_LOCK_VERSION",
        "def audit_profile",
        "def audit_profile_and_case",
        "AUDITOR_LAYER_IS_NOT_SECOND_ENGINE = True",
        "smoke_auditor_layer.py",
        "Layer file budget",
        "Этому пациенту писать дневники ежедневно или ежечасно?",
        "def render_diary_documents_from_pack",
        "def infer_diary_schedule_from_docx",
        "DIARY_MANUAL_DAY_INPUT_MIN_COUNT = 10",
        "DIARY_SCHEDULE_DOCTOR_CONFIRMATION_REQUIRED",
        "def safe_patient_subfolder",
        "def scan_primary_candidates",
        'DESKTOP_INTAKE_FOLDER_NAME = "Выписанные пациенты"',
    ]
    missing = [snippet for snippet in required_snippets if snippet not in source]
    if missing:
        raise SystemExit("Universal profile contract is incomplete: " + ", ".join(missing))
    if "\ndef import_profile()" in source or "\ndef readiness_report()" in source or "\ndef render_custom_documents()" in source:
        raise SystemExit("Universal mapper callbacks escaped method scope")
    if "Дополнить документ" + " мягкими пунктами" in source:
        raise SystemExit("Completion popup title regressed to soft-points wording")



def _assert_visual_scanner_contract() -> None:
    source = _project_python_source()
    required_snippets = [
        "def open_visual_scanner_dialog",
        "Цветной сканер внутри программы",
        "Сканер Word: открыть и взять выделение",
        "def open_external_word_selection_scanner_dialog",
        "external_word_scanner_enabled",
        "external_word_clipboard_selection",
        "visual_color_marks",
        "visual_scanner_enabled",
        "replace_selection_with_placeholder",
        "insert_placeholder_after_selection",
        "{{field.id}}",
        "source_extraction",
        "template_replace",
        "template_insert_after",
        "Цветной сканер: выделите фрагмент",
    ]
    missing = [snippet for snippet in required_snippets if snippet not in source]
    if missing:
        raise SystemExit("Visual color scanner contract is incomplete: " + ", ".join(missing))


def _assert_labs_block_contract() -> None:
    source = _project_python_source()
    required_snippets = [
        "LABS_FIELD_ID = \"labs.results\"",
        "class LabsBlock",
        "def extract_labs_from_file",
        "def open_labs_selection_scanner",
        "Без анализов",
        "Ввести анализы",
        "Загрузить файл",
        "Сканер мышкой",
        "Выделите мышкой блок с анализами",
        "labs_text_var",
        "labs_without_var",
        "labs.date_policy",
        "{{labs.results}}",
        "{{АНАЛИЗЫ}}",
        "field_id=\"labs.results\"",
        "data.labs_text = labs_block.text",
    ]
    missing = [snippet for snippet in required_snippets if snippet not in source]
    if missing:
        raise SystemExit("Labs block contract is incomplete: " + ", ".join(missing))

def _assert_project_code_auditor_contract() -> None:
    source = _project_python_source()
    required_snippets = [
        "PROJECT_AUDITOR_LOCK_VERSION",
        "def audit_project",
        "def assert_project_auditor_lock",
        "PROJECT_AUDITOR_IS_PROJECT_SCANNER = True",
        "PROJECT_AUDITOR_HAS_NO_UI_DEPENDENCY = True",
        "PROJECT_AUDITOR_CI_FAILS_ON_ERRORS_ONLY = True",
        "PROJECT_AUDITOR_DETECTS_CYCLES = True",
        "PROJECT_AUDITOR_CORE_IS_UI_FREE = True",
        "PROJECT_AUDITOR_RULES_ARE_EXPLICIT = True",
        "PROJECT_AUDITOR_NO_LLM_REQUIRED = True",
        "PROJECT_AUDITOR_DOES_NOT_IMPORT_THIRD_PARTY = True",
        "smoke_project_auditor.py",
        "smoke_technical_debt_cleanup.py",
        "smoke_stress_hardening.py",
        "smoke_split_entrypoints.py",
            "PROJECT_AUDITOR_WARNINGS_MUST_STAY_ZERO = True",
    ]
    missing = [item for item in required_snippets if item not in source]
    if missing:
        raise SystemExit("Project code auditor contract is incomplete: " + ", ".join(missing))



def _assert_strict_regression_contour_contract() -> None:
    contour = (ROOT / "REGRESSION_CONTOUR.md").read_text(encoding="utf-8", errors="replace")
    matrix = (ROOT / "REGRESSION_MATRIX.md").read_text(encoding="utf-8", errors="replace")
    runner = (ROOT / "tools" / "run_regression_contour.py").read_text(encoding="utf-8", errors="replace")
    workflow = (ROOT / ".github/workflows/windows-build.yml").read_text(encoding="utf-8", errors="replace")
    build = (ROOT / "build_exe_windows.bat").read_text(encoding="utf-8", errors="replace")
    tests = (ROOT / "tests" / "test_regression_contour_baseline_v1486.py").read_text(encoding="utf-8", errors="replace")
    required = [
        (contour, REGRESSION_CONTOUR_COMMAND, "regression contour command must be documented"),
        (contour, "doctor-owned DOCX/DOCM templates", "regression contour must protect doctor-owned templates"),
        (contour, "popup/UI values", "regression contour must protect popup/UI final priority"),
        (matrix, "Block 03 buttons", "regression matrix must map button behavior"),
        (matrix, "Popup values", "regression matrix must map popup-to-DOCX behavior"),
        (matrix, "Folder naming", "regression matrix must map folder naming"),
        (runner, "tests/test_regression_contour_baseline_v1486.py", "runner must execute the baseline contour test"),
        (runner, "tests/test_production_interaction_matrix_v1487.py", "runner must execute the production interaction matrix"),
        (runner, "smoke_followup_regressions.py", "runner must execute follow-up live-regression smoke"),
        (runner, "smoke_full_patient_replay.py", "runner must execute full patient replay"),
        (workflow, REGRESSION_CONTOUR_COMMAND, "GitHub Actions must run the strict regression contour"),
        (build, REGRESSION_CONTOUR_COMMAND, "Windows build must run the strict regression contour"),
        (tests, "test_full_doctor_regression_replay_from_template_to_output", "tests must include full doctor replay"),
    ]
    missing = [message for source, snippet, message in required if snippet not in source]
    if missing:
        raise SystemExit("Strict regression contour contract is incomplete: " + ", ".join(missing))
    _run([sys.executable, "-m", "pytest", "-q", "tests/test_regression_contour_baseline_v1486.py", "tests/test_production_interaction_matrix_v1487.py"], timeout=240)


def main() -> None:
    os.chdir(ROOT)
    os.environ.setdefault("CI", "1")
    os.environ.setdefault("MEDICAL_AUTOFILL_DISABLE_AUTOSTART", "1")
    _remove_generated_outputs()

    _print_step("Required files")
    _assert_required_files()

    _print_step("Python compileall")
    if not compileall.compile_dir(str(ROOT), quiet=1, maxlevels=10):
        raise SystemExit("compileall failed")

    _print_step("Smoke entrypoints")
    _assert_smoke_entrypoints_contract()

    _print_step("ICD-10 catalog contract")
    _assert_icd10_catalog_contract()

    _print_step("Performance contract")
    # Run startup-import performance before smoke/prod checks. Those checks can
    # import document-heavy modules by design; the performance probe itself must
    # stay a clean isolated startup measurement.
    _assert_performance_contract()

    _print_step("Architecture contracts")
    _assert_architecture_contracts()

    _print_step("Stress hardening contract")
    # Run the heaviest smoke before any in-process Tk/docx smoke imports.  This
    # avoids inheriting helper threads/handles that can make subprocess spawning
    # nondeterministic on some platforms.
    _run([sys.executable, "smoke_stress_hardening.py"], timeout=180)
    from smoke_stress_hardening import assert_stress_hardening_lock
    assert_stress_hardening_lock()
    print("STRESS HARDENING CONTRACT OK")

    _print_step("Project code auditor contract")
    # The full project auditor is still wired through prod/CI, but it is not
    # imported before the heavy in-process smoke suite: importing the audit AST
    # scanner first can perturb docx/Tk smoke teardown on some platforms.
    _assert_project_code_auditor_contract()
    from smoke_technical_debt_cleanup import assert_technical_debt_cleanup_lock
    assert_technical_debt_cleanup_lock()

    _print_step("Smoke test contract")
    # release_check.py verifies smoke entrypoints and CI/build wiring. The heavy
    # DOCX smoke files are executed by CI/build as fresh processes and can also
    # be run manually one-by-one for diagnostics.
    _assert_smoke_entrypoints_contract()
    _assert_full_smoke_suite_is_wired()
    # The legacy combined smoke remains wired into build/CI and can be run
    # manually as ``python smoke_test_combined.py``.  release_check runs the
    # focused product hardening smokes to avoid hanging on platform helper
    # teardown in source archives after heavy Tk/docx probes.
    os.environ["CI"] = "1"
    runpy.run_path(str(ROOT / "smoke_user_reported_regressions.py"), run_name="__release_smoke_user__")
    from smoke_points_5_11 import main as points_5_11_smoke_main
    points_5_11_smoke_main()
    from smoke_quality_modernization import main as quality_modernization_smoke_main
    quality_modernization_smoke_main()
    from smoke_full_patient_replay import main as full_patient_replay_smoke_main
    full_patient_replay_smoke_main()
    print("SMOKE TEST CONTRACT OK")

    _print_step("Desktop intake and diary schedule contract")
    # Run the behavioral desktop smoke here too.  Standalone release_check.py
    # must catch parser/table/patient-folder regressions even when a developer
    # forgets to run the build script first.
    from smoke_desktop_diary_workflow import main as desktop_diary_smoke_main
    desktop_diary_smoke_main()
    from desktop_intake import assert_desktop_intake_lock
    from desktop_intake_agent import assert_desktop_intake_agent_lock
    from desktop_patient_folder import assert_desktop_patient_folder_lock
    from medical_admission_resolver import assert_admission_resolver_lock
    from diary_schedule import assert_diary_schedule_lock
    from universal_diary_generation import assert_universal_diary_generation_lock
    from universal_diary_templates import assert_universal_diary_template_lock
    assert_desktop_intake_lock()
    assert_desktop_intake_agent_lock()
    assert_desktop_patient_folder_lock()
    assert_admission_resolver_lock()
    assert_diary_schedule_lock()
    assert_universal_diary_generation_lock()
    assert_universal_diary_template_lock()
    print("DESKTOP DIARY CONTRACT OK")

    _print_step("Auditor layer contract")
    # The full auditor-layer smoke has already run above; this section keeps the lock explicit.
    from auditor_layer import assert_auditor_layer_lock
    assert_auditor_layer_lock()

    _print_step("Production audit")
    _assert_prod_audit_contract()

    _print_step("Drag-and-drop contract")
    _assert_dnd_contract()

    _print_step("Startup state contract")
    _assert_startup_state_contract()
    _assert_no_local_import_cycles()

    _print_step("Strict regression contour")
    _assert_strict_regression_contour_contract()

    _print_step("Production contracts")
    _assert_settings_contract()
    _assert_build_contract()
    _assert_ui_selected_state_contract()
    _assert_sick_leave_popup_contract()
    _assert_discharge_date_contract()
    _assert_layout_balance_contract()
    _assert_tk_widget_padding_contract()
    _assert_audit_hardening_contract()
    _assert_universal_profile_contract()
    from layout_checklist import assert_block03_first_run_contract
    assert_block03_first_run_contract()
    from layout_checklist import assert_template_button_review_contract
    assert_template_button_review_contract()
    _assert_labs_block_contract()
    _assert_visual_scanner_contract()
    _assert_followup_p0_regression_contract()
    from installation_diagnostics import assert_installation_diagnostics_lock
    from diary_creation_wizard import assert_diary_creation_wizard_lock
    assert_installation_diagnostics_lock()
    assert_diary_creation_wizard_lock()

    _print_step("Cleanup and archive hygiene")
    _remove_generated_outputs()
    _assert_archive_hygiene()

    print("\nRELEASE CHECK OK")


if __name__ == "__main__":
    main()
    # The release gate is a disposable process.  Some smoke probes can leave
    # platform helper handles alive even after all assertions have completed.
    # Hard-exit only after a fully successful gate so CI never hangs on teardown.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
