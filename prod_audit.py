"""Production-readiness audit for MedicalDiaryAutofill.

The audit is intentionally standard-library only. It is meant to run in CI and
on a developer machine before GitHub upload, EXE publishing, or paid-traffic
launch. It checks architecture hygiene, release metadata, import graph safety,
and the absence of known dust files from the over-split refactor wave.
"""

from __future__ import annotations

import ast
import importlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET_VERSION = "1.4.89"
TARGET_VERSION_LABEL = "v1.4.89_release_gate_runtime_isolation_SOURCE"
MAX_PYTHON_FILES = 200  # hard ceiling; detailed layer budget lives in architecture_contracts.py
MAX_TINY_PYTHON_FILES = 25

# These files existed only as one-purpose micro-mixins after the aggressive
# split wave. Keeping them would reintroduce architectural dust.
FORBIDDEN_DUST_FILES = {
    "ui_title_pills.py",
    "ui_neon_buttons.py",
    "ui_field_canvases.py",
    "ui_output_fields.py",
    "ui_medical_fields.py",
    "ui_sick_leave_field.py",
    "layout_action_bar_build.py",
    "layout_action_bar_tiles.py",
    "layout_action_bar_selection.py",
    "layout_checklist_build.py",
    "layout_checklist_tile.py",
    "layout_checklist_icons.py",
    "dnd_setup.py",
    "dnd_file_handler.py",
    "diagnosis_autocomplete.py",
    "diagnosis_popup.py",
    "diagnosis_selector.py",
    "files_output_state.py",
    "files_primary.py",
    "files_diary_templates.py",
    "files_printers.py",
    "dialog_expert_shared_work.py",
    "dialog_expert_sick_leave.py",
    "dialog_assigned_treatment.py",
    "dialog_commission_details.py",
    "dialog_rvk_details.py",
    "dialog_vk_mse_details.py",
    "dialog_sick_leave_vk_details.py",
    "dialog_primary_document_type.py",
    "diary_template_file_detection.py",
    "diary_template_folder_scan.py",
    "diary_template_dirs.py",
    "diary_template_finder.py",
    "diary_template_admission.py",
    "diary_template_auto_select.py",
    "window_build.py",
    "window_metrics.py",
    "window_style.py",
    "window_shortcuts.py",
    "window_chrome.py",
    "window_header.py",
    "window_patient_card.py",
    "app_init_entrypoint.py",
    "app_state_core.py",
    "app_state_patient.py",
    "app_state_documents.py",
    "app_state_diaries.py",
    "app_state_runtime.py",
    "app_window_bootstrap.py",
}

# Old iteration reports are useful during a chat, but they are release noise in
# a GitHub/prod archive. Keep one final report and release notes instead.
FORBIDDEN_ITERATION_REPORTS = {
    "MAIN_SPLIT_REPORT.md",
    "FULL_SPLIT_REPORT.md",
    "DEEP_SPLIT_REPORT.md",
    "FINE_SPLIT_REPORT.md",
    "FINAL_SPLIT_REPORT.md",
    "PRODUCTION_REPORT.md",
}

PUBLIC_ENTRYPOINTS = {
    "main.py",
    "medical_documents.py",
    "diary_filler.py",
    "printer_support.py",
    "icd10_f.py",
    "smoke_test.py",
    "smoke_test_combined.py",
}


def _fail(message: str) -> None:
    raise SystemExit(message)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="replace")


def _read_many(*paths: str) -> str:
    return "\n".join(_read(path) for path in paths)


def _python_files() -> list[Path]:
    return sorted(ROOT.glob("*.py"), key=lambda p: p.name.lower())


def _target_version_tuple_literal() -> str:
    try:
        parts = [int(part) for part in TARGET_VERSION.split(".")]
    except ValueError as exc:
        _fail(f"TARGET_VERSION must contain numeric dot-separated parts: {TARGET_VERSION}")
    if len(parts) != 3:
        _fail(f"TARGET_VERSION must be MAJOR.MINOR.PATCH: {TARGET_VERSION}")
    return f"({parts[0]}, {parts[1]}, {parts[2]}, 0)"


def _assert_version_sync() -> None:
    pyproject = _read("pyproject.toml")
    app_config = _read("app_config.py")
    version_info = _read("version_info.txt")
    readme = _read("README.md")
    release_notes = _read("RELEASE_NOTES.md")
    tuple_literal = _target_version_tuple_literal()

    checks = {
        "pyproject.toml version": f'version = "{TARGET_VERSION}"' in pyproject,
        "app_config APP_VERSION": TARGET_VERSION_LABEL in app_config,
        "version_info label": TARGET_VERSION_LABEL in version_info,
        "version_info file tuple": f"filevers={tuple_literal}" in version_info,
        "version_info product tuple": f"prodvers={tuple_literal}" in version_info,
        "README version": TARGET_VERSION_LABEL in readme,
        "RELEASE_NOTES top version": release_notes.lstrip().startswith(f"# Release notes — {TARGET_VERSION_LABEL}"),
    }
    missing = [name for name, ok in checks.items() if not ok]
    if missing:
        _fail("Version metadata is not synchronized: " + ", ".join(missing))


def _assert_architecture_hygiene() -> None:
    py_files = _python_files()
    names = {p.name for p in py_files}
    dust = sorted(names & FORBIDDEN_DUST_FILES)
    if dust:
        _fail("Architectural dust files are present:\n" + "\n".join(dust))

    old_reports = sorted(p.name for p in ROOT.glob("*.md") if p.name in FORBIDDEN_ITERATION_REPORTS)
    versioned_fix_reports = sorted(p.name for p in ROOT.glob("FIX_REPORT_v*.md"))
    if old_reports:
        _fail("Old split iteration reports must not ship in production archive:\n" + "\n".join(old_reports))
    if versioned_fix_reports:
        _fail("Old versioned FIX_REPORT files must not ship in production archive:\n" + "\n".join(versioned_fix_reports))

    if len(py_files) > MAX_PYTHON_FILES:
        _fail(f"Too many Python files after dust collapse: {len(py_files)} > {MAX_PYTHON_FILES}")

    tiny_files = []
    for path in py_files:
        if path.name in PUBLIC_ENTRYPOINTS:
            continue
        line_count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        if line_count <= 20:
            tiny_files.append(path.name)
    if len(tiny_files) > MAX_TINY_PYTHON_FILES:
        _fail("Too many tiny non-entrypoint Python files:\n" + "\n".join(tiny_files))


def _local_import_graph() -> dict[str, set[str]]:
    local_modules = {p.stem for p in _python_files()}
    graph: dict[str, set[str]] = {p.stem: set() for p in _python_files()}
    for path in _python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            _fail(f"Syntax error in {path.name}: {exc}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in local_modules:
                        graph[path.stem].add(root)
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                if root in local_modules:
                    graph[path.stem].add(root)
    return graph


def _assert_no_import_cycles() -> None:
    graph = _local_import_graph()
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def dfs(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            idx = stack.index(node) if node in stack else 0
            cycle = stack[idx:] + [node]
            _fail("Local import cycle detected: " + " -> ".join(cycle))
        visiting.add(node)
        stack.append(node)
        for child in sorted(graph.get(node, ())):
            dfs(child)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        dfs(node)


def _assert_no_deleted_module_references() -> None:
    deleted_stems = {Path(name).stem for name in FORBIDDEN_DUST_FILES}
    bad: list[str] = []
    for path in _python_files():
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            _fail(f"Syntax error in {path.name}: {exc}")
        for node in ast.walk(tree):
            imported = None
            if isinstance(node, ast.ImportFrom) and node.module:
                imported = node.module.split(".", 1)[0]
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in deleted_stems:
                        bad.append(f"{path.name}:{node.lineno}: import {root}")
                continue
            if imported in deleted_stems:
                bad.append(f"{path.name}:{node.lineno}: from {imported} import ...")
        # Guard against static Python references like OldMixin.some_static_method after collapse.
        # String literals are intentionally ignored: Windows/PowerShell terms such as
        # ``WindowStyle`` are legitimate command text and must not fail the audit.
        python_names: set[str] = set()
        for ast_node in ast.walk(tree):
            if isinstance(ast_node, ast.Name):
                python_names.add(ast_node.id)
            elif isinstance(ast_node, ast.Attribute):
                python_names.add(ast_node.attr)
        for stem in deleted_stems:
            camel = "".join(part.capitalize() for part in stem.split("_"))
            if camel in python_names:
                bad.append(f"{path.name}: stale class/static reference {camel}")
    if bad:
        _fail("References to deleted dust modules/classes found:\n" + "\n".join(sorted(bad)))






def _assert_public_modules_importable() -> None:
    bad: list[str] = []
    for stem in ["main", "app", "app_initialization", "medical_documents", "diary_filler", "printer_support", "icd10_f"]:
        try:
            importlib.import_module(stem)
        except Exception as exc:  # pragma: no cover - report clarity
            bad.append(f"{stem}: {type(exc).__name__}: {exc}")
    if bad:
        _fail("Public/runtime modules are not importable:\n" + "\n".join(bad))


def _assert_smoke_entrypoint_contract() -> None:
    smoke_test = _read("smoke_test.py")
    smoke_combined = _read("smoke_test_combined.py")
    for file_name, source in [("smoke_test.py", smoke_test), ("smoke_test_combined.py", smoke_combined)]:
        for snippet in ["from smoke_combined_runner import run", 'if __name__ == "__main__":', "run()"]:
            if snippet not in source:
                _fail(f"{file_name} is not an executable smoke entrypoint; missing: {snippet}")


def _assert_release_zip_excludes_generated_runs() -> None:
    source = _read("make_release_zip.py")
    required = [
        'part.startswith("test_run")',
        'part.endswith("_run")',
        'for part in rel.parts',
    ]
    missing = [snippet for snippet in required if snippet not in source]
    if missing:
        _fail("make_release_zip.py can leak generated run folders; missing: " + ", ".join(missing))

def _assert_startup_state_contract() -> None:
    """Catch startup-only globals that compileall/smoke tests can miss headlessly."""
    module = importlib.import_module("app_initialization")
    globals_map = module.AppInitializationMixin._init_medical_output_state.__globals__
    required_globals = ["DOCUMENT_ORDER", "DIARY_KIND"]
    missing = [name for name in required_globals if name not in globals_map]
    if missing:
        _fail("Startup app-state globals are missing: " + ", ".join(missing))
    document_order = globals_map["DOCUMENT_ORDER"]
    if not document_order or "discharge" not in document_order:
        _fail("Startup DOCUMENT_ORDER contract is invalid")

def _assert_dnd_contract() -> None:
    required = [
        "dnd_contract_check.py",
        "dnd_mixin.py",
        "startup.py",
        "layout_sources.py",
    ]
    missing = [name for name in required if not (ROOT / name).exists()]
    if missing:
        _fail("Missing drag-and-drop contract files: " + ", ".join(missing))
    dnd = _read("dnd_mixin.py")
    for snippet in ["from tkinterdnd2 import DND_FILES", "drop_target_register(DND_FILES)", 'dnd_bind("<<Drop>>", self._on_drop_event)', "_parse_drop_event_data"]:
        if snippet not in dnd:
            _fail(f"Drag-and-drop runtime contract misses: {snippet}")

def _assert_discharge_date_contract() -> None:
    source = "\n".join(_read(path.name) for path in sorted(ROOT.glob("*.py")) if path.name not in {"prod_audit.py"})
    for snippet in ["def _ensure_discharge_date", "def _prompt_discharge_date", 'title="Дата выписки"', "ДДММГГГГ, ДДММГГ или коротко ДМГГ"]:
        if snippet not in source:
            _fail(f"Discharge-date popup contract misses: {snippet}")

    from medical_documents import parse_date
    from diary_filler import parse_full_date
    if parse_date("10052026").strftime("%d.%m.%Y") != "10.05.2026":
        _fail("medical compact date parser is broken")
    if parse_date("1126").strftime("%d.%m.%Y") != "01.01.2026":
        _fail("medical short compact date parser is broken")
    if parse_full_date("100526").strftime("%d.%m.%Y") != "10.05.2026":
        _fail("diary compact date parser is broken")
    if parse_full_date("1126").strftime("%d.%m.%Y") != "01.01.2026":
        _fail("diary short compact date parser is broken")




def _assert_dialog_runtime_globals_contract() -> None:
    """Catch Tkinter callback NameError regressions in dialog methods.

    compileall and import checks are not enough: a missing global inside a
    callback only explodes after the user clicks a button. This guard checks
    the concrete globals used by the discharge-date and hospital-popup paths.
    """
    import dialog_expert

    cls = dialog_expert.DialogExpertMixin
    required_by_method = {
        "_prompt_expert_anamnesis_details": ["parse_date"],
        "_ensure_discharge_date": ["parse_date"],
        "_prompt_discharge_date": ["parse_date"],
        "_prompt_assigned_treatment_if_needed": ["parse_date", "sanitize_diagnosis"],
    }
    missing: list[str] = []
    for method_name, names in required_by_method.items():
        globals_map = getattr(cls, method_name).__globals__
        for name in names:
            if name not in globals_map:
                missing.append(f"{method_name}: {name}")
    if missing:
        _fail("Dialog runtime globals are missing: " + ", ".join(missing))



def _assert_treatment_popup_contract() -> None:
    """Guard missing-treatment popup workflow for block 03 medical tiles."""
    from medical_service import MedicalDocumentService

    parser = MedicalDocumentService().parser
    no_marker = parser.parse_text("""
Первичный осмотр
Ф.И.О.: Иванов Иван Иванович
Год рождения: 1990
За время лечения состояние без динамики.
Диагноз: K35.8 тест
""")
    has_marker = parser.parse_text("""
Первичный осмотр
Ф.И.О.: Иванов Иван Иванович
Год рождения: 1990
Назначенное лечение терапия по схеме.
Диагноз: K35.8 тест
""")
    if no_marker.has_treatment_section:
        _fail("Prose phrase 'за время лечения' must not count as a treatment section")
    if not has_marker.has_treatment_section or has_marker.treatment_plan != "терапия по схеме.":
        _fail("Explicit 'Назначенное лечение' marker without colon must be parsed as treatment")

    layout_action_bar = _read("layout_action_bar.py")
    orchestrator = _read_many("actions_creation_orchestrator.py", "actions_creation_preflight.py", "actions_creation_foldering.py", "actions_creation_maintenance.py", "actions_creation_batch.py", "actions_creation_execution.py")
    details = _read("dialog_document_details.py")
    required_pairs = [
        (layout_action_bar, "kind != DIARY_KIND", "diary tile must be excluded from treatment popup guard"),
        (layout_action_bar, "_prompt_common_output_requirements", "block 03 medical tiles must call merged common popup guard"),
        (orchestrator, "_prompt_common_output_requirements", "create flow must enforce merged common popup guard"),
        (details, "_primary_has_treatment_section", "dialog layer must inspect full primary parser flag"),
        (details, '"Номер истории болезни", self._case_number_popup_default()', "medical popups must show shared case number"),
        (details, "def _store_case_number_value", "dialog layer must store shared case number once"),
        (details, 'fields.append("case_number")', "missing-treatment popup must include shared case-number field"),
    ]
    missing = [message for source, snippet, message in required_pairs if snippet not in source]
    if missing:
        _fail("Treatment popup contract is incomplete:\n" + "\n".join(missing))

    from medical_text_utils import sanitize_case_number_candidate
    from medical_parser import MedicalTextParser

    parser = MedicalTextParser()
    spillover = parser.parse_text("""
Первичный осмотр
История болезни №
Ф.И.О.
Михайлов Николай Иванович
Диагноз: K35.8 тест
""")
    if spillover.case_number:
        _fail("Patient FIO must not be parsed as case/history number")
    if sanitize_case_number_candidate("Михайлов Николай Иванович", patient_name="Михайлов Николай Иванович"):
        _fail("Popup default guard must reject patient FIO as case/history number")


def _assert_audit_hardening_contract() -> None:
    """Guard the bug fixes from the v1.3.3 deep audit."""
    numbers = _read("diary_table_numbers.py")
    dates = _read("diary_table_dates.py")
    files = _read("files_mixin.py")
    dnd = _read("dnd_mixin.py")
    diagnosis = _read("diagnosis_widget.py")
    dialog_popup = _read("dialog_fields_popup.py")
    title_finder = _read("medical_docx_title_finder.py")
    templates = _read("actions_template_checks.py")
    orchestrator = _read_many("actions_creation_orchestrator.py", "actions_creation_preflight.py", "actions_creation_foldering.py", "actions_creation_maintenance.py", "actions_creation_batch.py", "actions_creation_execution.py")
    app_init = _read("app_initialization.py")
    actions_diary = _read("actions_diary_flow.py")

    required_pairs = [
        (numbers, "from datetime import date", "diary_table_numbers.py must import date for public type hints"),
        (dates, "from diary_table_columns import find_day_column", "diary_table_dates.py must stay a small date detector"),
        (files, "def _truncate_label_text", "FilesMixin must truncate long UI labels"),
        (files, "single_line: bool = False", "FilesMixin._short_file_list must support single-line labels"),
        (dnd, "_update_diary_text_label(success=True)", "DnD status labels must go through the compact diary-text label updater"),
        (diagnosis, "if not query:\n            self._hide_diagnosis_popup()", "diagnosis field must not search ICD-10 on empty input"),
        (dialog_popup, "if not query:\n            self.hide()", "dialog diagnosis popup must not search ICD-10 on empty input"),
        (title_finder, r"\d{4,8}", "title date finder must support compact dates in isolated title-neighbor rows"),
        (templates, "Встроенных медицинских шаблонов нет", "template check must stay doctor-owned and not require bundled templates"),
        (orchestrator, "_select_default_printer_sync", "print flow must not rely on asynchronous refresh_printers before printing"),
        (app_init, "_printer_refresh_in_progress", "printer discovery needs a concurrency guard"),
        (actions_diary, "_auto_select_diary_text_by_diagnosis(ask_folder=False)", "diary creation must retry diagnosis-based diary text autoselect before warning"),
        (_read("diary_text_selection.py"), "_COMMON_DIARY_NAME_WORDS", "diary text matching must ignore technical filename words like дневники/ВЭ"),
        (_read("diary_text_selection.py"), "surgical", "diary text matching must use neutral medical semantic bridges"),
        (_read("regulatory_specialty_overlays.py"), "expert_commission", "default overlays must stay neutral and commission-aware"),
        (_read_many("window_mixin.py", "window_core_mixin.py", "window_header_mixin.py", "window_mapper_dialog.py", "window_completion_dialog.py", "window_universal_dialogs_mixin.py"), "Нижняя служебная строка убрана", "bottom service/status line must stay hidden"),
    ]
    missing = [message for source, snippet, message in required_pairs if snippet not in source]
    if missing:
        _fail("Audit-hardening contract is incomplete:\n" + "\n".join(missing))
    if "def cell_int" in dates or "def should_remove_holiday" in dates:
        _fail("diary_table_dates.py reintroduced duplicated numeric helpers")
    window = _read_many("window_mixin.py", "window_core_mixin.py", "window_header_mixin.py", "window_mapper_dialog.py", "window_setup_center.py", "window_document_mapper.py", "window_completion_dialog.py", "window_universal_dialogs_mixin.py")
    if "status_bar.pack" in window or "_status_bar_ready_icon" in window:
        _fail("Visible bottom status/service line was reintroduced")
    if "Дата поступления / конс. тел." in window or "конс. тел." in window:
        _fail("Main screen block 01 must show only: Дата поступления")
    if "Дата поступления" not in window:
        _fail("Main screen block 01 admission-date label is missing")
    overlays = _read("regulatory_specialty_overlays.py")
    if '_overlay("psy' + 'chiatry"' in overlays or '"Псих' + 'иатрия"' in overlays:
        _fail("Default specialty overlays must not reintroduce narrow-profile UI defaults")
    diary_selector = _read("diary_text_selection.py")
    if "oligo" + "phrenia" in diary_selector or "psycho" + "pathy" in diary_selector:
        _fail("Diary text selector must stay neutral and not hardcode narrow-profile semantic bridges")

def _assert_release_documents() -> None:
    required = [
        "README.md",
        "BASELINE_VERSION.txt",
        "USER_BEHAVIOR_CONTRACT.md",
        "CHANGELOG.md",
        "BASELINE_MANIFEST.json",
        "REGRESSION_CONTOUR.md",
        "REGRESSION_MATRIX.md",
        "RELEASE_NOTES.md",
        "FIX_REPORT.md",
        "PROD_READY_AUDIT_REPORT.md",
        "LAUNCH_CHECKLIST.md",
        ".github/workflows/windows-build.yml",
        "build_exe_windows.bat",
        "tools/run_regression_contour.py",
        "tests/test_regression_contour_baseline_v1486.py",
    "tests/test_production_interaction_matrix_v1487.py",
        ".gitattributes",
    ]
    missing = [name for name in required if not (ROOT / name).exists()]
    if missing:
        _fail("Missing release documents/files: " + ", ".join(missing))

    readme = _read("README.md")
    for snippet in ["локально", "готовый `MedicalDiaryAutofill.exe`", "Python, pip и зависимости", "Проверки перед релизом"]:
        if snippet not in readme:
            _fail(f"README misses production snippet: {snippet}")

    baseline = _read("BASELINE_VERSION.txt")
    behavior = _read("USER_BEHAVIOR_CONTRACT.md")
    changelog = _read("CHANGELOG.md")
    manifest = _read("BASELINE_MANIFEST.json")
    contour = _read("REGRESSION_CONTOUR.md")
    matrix = _read("REGRESSION_MATRIX.md")
    regression_runner = _read("tools/run_regression_contour.py")
    baseline_required = [
        (baseline, TARGET_VERSION_LABEL, "baseline version label"),
        (baseline, "doctor-owned constructor", "baseline doctor-owned constructor rule"),
        (behavior, "Block 03", "behavior contract block-03 section"),
        (behavior, "Popup behavior", "behavior contract popup section"),
        (behavior, "Folder naming behavior", "behavior contract folder naming section"),
        (behavior, "Scanner output must not overwrite", "behavior contract UI priority rule"),
        (changelog, TARGET_VERSION_LABEL, "changelog baseline entry"),
        (manifest, '"version_label": "' + TARGET_VERSION_LABEL + '"', "baseline manifest version label"),
        (contour, "python tools/run_regression_contour.py", "strict regression contour command"),
        (contour, "doctor-owned DOCX/DOCM templates", "strict regression contour doctor-owned rule"),
        (matrix, "Popup values", "regression matrix popup row"),
        (matrix, "Folder naming", "regression matrix folder naming row"),
        (regression_runner, "STRICT REGRESSION CONTOUR OK", "regression contour runner success marker"),
    ]
    missing_baseline = [message for source, snippet, message in baseline_required if snippet not in source]
    if missing_baseline:
        _fail("Baseline release contract is incomplete: " + ", ".join(missing_baseline))



def _assert_quality_100_contract() -> None:
    """Guard the final production-quality hardening layer."""
    service = _read("medical_service.py")
    diary_batch = _read("diary_batch.py")
    orchestrator = _read_many("actions_creation_orchestrator.py", "actions_creation_preflight.py", "actions_creation_foldering.py", "actions_creation_maintenance.py", "actions_creation_batch.py", "actions_creation_execution.py")
    layout = _read("layout_action_bar.py")
    stress_smoke = _read("smoke_stress_hardening.py")
    medical_paths = _read("medical_paths.py")
    make_zip = _read("make_release_zip.py")
    workflow = _read(".github/workflows/windows-build.yml")
    attrs = _read(".gitattributes")
    required_pairs = [
        (service, "def _resolve_output_dir", "medical service must validate output directory before mkdir/render"),
        (service, "label_to_kind", "medical service must accept visible UI labels at public boundary"),
        (service, "Папка результата указывает на файл", "medical service must reject output_dir pointing to a file"),
        (service, "def create_documents_batch", "medical batch generation must be a real backend function"),
        (service, "def save_batch_generation_report", "medical batch generation must save a readable report"),
        (orchestrator, "def batch_generate_documents_dialog", "batch generation must be exposed in the UI, not only backend scaffold"),
        (orchestrator, "def _read_update_manifest", "version check must read an update manifest, not be a placeholder popup"),
        (layout, 'text="Пакет"', "block 04 must expose the batch button"),
        (stress_smoke, "create_documents_batch", "smoke suite must exercise real batch generation"),
        (stress_smoke, "_read_update_manifest", "smoke suite must exercise real update-manifest reading"),
        (diary_batch, "seen: set[Path]", "diary input DOCX list must dedupe repeated files"),
        (diary_batch, "def _resolve_output_dir", "diary batch must validate output directory before copying templates"),
        (diary_batch, "Пустой путь к файлу", "diary batch must reject blank file paths clearly"),
        (diary_batch, "return True", "open_folder must report whether folder opening really started"),
        (medical_paths, "validate=True", "embedded template base64 must be validated strictly"),
        (medical_paths, ".tmp", "embedded template cache refresh must be atomic"),
        (make_zip, "def _assert_clean_archive", "release ZIP must verify itself before publishing"),
        (workflow, "permissions:", "GitHub Actions must run with explicit least-privilege permissions"),
        (workflow, "concurrency:", "GitHub Actions must avoid stale concurrent release builds"),
        (workflow, "timeout-minutes:", "GitHub Actions must not hang indefinitely"),
        (attrs, "*.py text eol=lf", "repository must prevent Windows CRLF churn for Python sources"),
        (attrs, "*.docx binary", "repository must mark Office templates as binary"),
    ]
    missing = [message for source, snippet, message in required_pairs if snippet not in source]
    if missing:
        _fail("100/100 quality contract is incomplete:\n" + "\n".join(missing))


def _assert_universal_profile_contract() -> None:
    """Guard the first universal document-pack foundation."""
    fields = _read("universal_fields.py")
    profiles = _read("universal_profiles.py")
    scanner = _read("universal_scanner.py")
    template_engine = _read("universal_template_engine.py")
    generation = _read("universal_generation.py")
    builder = _read("universal_profile_builder.py")
    regulatory_roles = _read("regulatory_document_roles.py")
    regulatory_classifier = _read("regulatory_document_classifier.py")
    regulatory_advisor = _read("regulatory_template_advisor.py")
    regulatory_policy = _read("regulatory_advisory_policy.py")
    regulatory_sections = _read("regulatory_section_registry.py")
    regulatory_overlays = _read("regulatory_specialty_overlays.py")
    regulatory_completion = _read("regulatory_completion_blocks.py")
    regulatory_caucasus = _read("regulatory_caucasus_aliases.py")
    language_catalog = _read("medical_language_catalog.py")
    language_detector = _read("medical_language_detector.py")
    i18n_strings = _read("i18n_strings.py")
    orthography = _read("medical_orthography.py")
    language_preferences = _read("language_preferences.py")
    personal_buttons = _read("personal_document_buttons.py")
    main_documents = _read("universal_main_documents.py")
    case_adapter = _read("universal_case_adapter.py")
    universal_actions = _read("actions_universal_flow.py")
    layout = _read("layout_checklist.py")
    selection = _read("actions_selection.py")
    orchestrator = _read_many("actions_creation_orchestrator.py", "actions_creation_preflight.py", "actions_creation_foldering.py", "actions_creation_maintenance.py", "actions_creation_batch.py", "actions_creation_execution.py")
    window = _read_many("window_mixin.py", "window_core_mixin.py", "window_header_mixin.py", "window_mapper_dialog.py", "window_setup_center.py", "window_document_mapper.py", "window_completion_dialog.py", "window_universal_dialogs_mixin.py")
    smoke = "\n".join(_read(path.name) for path in sorted(ROOT.glob("smoke_combined_part*.py")))
    required_pairs = [
        (fields, "class FieldRegistry", "universal fields registry is missing"),
        (fields, "patient.snils", "SNILS semantic field must be available"),
        (fields, "custom.*", "custom field policy must be documented"),
        (fields, "procedure.anesthesia", "specialty fields for surgery/therapy must be present"),
        (profiles, "class DocumentPack", "DocumentPack model is missing"),
        (profiles, "def required_field_ids", "DocumentPack must expose aggregate required fields"),
        (profiles, "Пустой профиль: врач добавляет свои Word-шаблоны всех документов", "default profile must start empty and doctor-owned"),
        (profiles, "save_document_pack", "DocumentPack persistence is missing"),
        (scanner, "class DocumentScanResult", "scanner result model is missing"),
        (scanner, "def review_rows", "scanner must expose doctor review rows"),
        (scanner, "def merge_scan_results", "scanner must support several source examples"),
        (scanner, "def scan_docx", "DOCX scanner entrypoint is missing"),
        (scanner, "def learn_rule_from_selection", "manual field-rule learning is missing"),
        (template_engine, "class TemplateValidationResult", "template validation model is missing"),
        (template_engine, "def validate_template", "custom template validation is missing"),
        (template_engine, "def render_template_to_docx", "custom DOCX renderer is missing"),
        (template_engine, "def export_document_pack_zip", "medpack export is missing"),
        (template_engine, "def attach_template_to_pack", "custom templates must be copied into profile-owned storage"),
        (generation, "class PackReadinessReport", "universal readiness report is missing"),
        (generation, "def analyze_pack_readiness", "pack readiness analysis is missing"),
        (generation, "def render_documents_from_pack", "custom pack generation is missing"),
        (builder, "class SpecialtyPreset", "universal specialty presets are missing"),
        (builder, "def create_pack_from_preset", "profile builder must create packs from specialty presets"),
        (builder, "def ingest_templates_into_pack", "profile builder must batch-attach doctor templates"),
        (builder, "def build_profile_from_sources_and_templates", "profile builder must support end-to-end setup from examples and templates"),
        (builder, "def profile_setup_checklist", "profile builder must provide a doctor/support checklist"),
        (scanner, "def scan_many_docx", "scanner must support training on several source examples"),
        (scanner, "section[", "scanner must include header/footer story blocks"),
        (generation, "Неизвестный документ профиля", "custom generation must not silently ignore unknown selected document ids"),
        (generation, "Папка результата указывает на файл", "custom generation must reject output_dir pointing to a file"),
        (template_engine, "def _iter_docx_paragraphs", "universal renderer must scan body/table/header/footer paragraphs"),
        (template_engine, "bool(self.placeholders)", "templates without placeholders must be blocked"),
        (template_engine, 'doc_data["template"] = arcname.as_posix()', "medpack export must not leak absolute template paths"),
        (template_engine, '"\\\\" in normalized', "medpack import must reject backslash paths"),
        (template_engine, "total_size > 100 * 1024 * 1024", "medpack import must guard oversized archives"),
        (window, "def _open_universal_document_mapper", "UI mapper entrypoint is missing"),
        (window, "Запомнить выделение как правило", "UI must let doctor save a manual extraction rule"),
        (window, "Добавить DOCX-шаблон в профиль", "UI must let doctor add a custom DOCX template"),
        (window, "Импортировать medpack", "UI must import portable medpacks"),
        (window, "Отчёт готовности кнопок", "UI must show dynamic-button readiness"),
        (window, "Создать custom DOCX", "UI must render profile custom DOCX from the scanned case"),
        (window, "Мастер профиля / checklist", "UI must expose profile builder checklist"),
        (smoke, "scan_docx(nav", "smoke suite must exercise universal scanner"),
        (smoke, "learn_rule_from_selection", "smoke suite must exercise manual selection learning"),
        (smoke, "render_template_to_docx", "smoke suite must exercise custom template rendering"),
        (smoke, "attach_template_to_pack", "smoke suite must exercise profile-owned template copy"),
        (smoke, "analyze_pack_readiness", "smoke suite must exercise readiness analysis"),
        (smoke, "render_documents_from_pack", "smoke suite must exercise custom pack generation"),
        (smoke, "build_profile_from_sources_and_templates", "smoke suite must exercise profile builder end-to-end"),
        (smoke, "create_pack_from_preset", "smoke suite must exercise specialty presets"),
        (smoke, "scan_many_docx", "smoke suite must exercise multi-source scanner"),
        (regulatory_roles, "class DocumentRole", "regulatory document roles are missing"),
        (regulatory_sections, "class RegulatorySectionRegistry", "regulatory section registry is missing"),
        (regulatory_overlays, "class SpecialtyOverlay", "regulatory specialty overlays are missing"),
        (regulatory_classifier, "def classify_docx", "regulatory DOCX classifier is missing"),
        (regulatory_advisor, "def advise_template", "regulatory template advisor is missing"),
        (regulatory_advisor, "should_block_generation", "regulatory advice must expose non-blocking policy"),
        (regulatory_policy, "REGULATORY_SOFT_ADVISORY_LOCK_VERSION", "regulatory soft-advisory lock is missing"),
        (regulatory_policy, "ADVISORY_IS_NEVER_BLOCKING = True", "regulatory advice must remain non-blocking"),
        (regulatory_policy, "Нет, не буду, делай как есть", "doctor decline button text must be locked"),
        (window, "Подсказки по приказам", "UI must expose soft regulatory advice"),
        (window, "Буду дополнять", "UI must offer completion flow"),
        (window, "Нет, не буду, делай как есть", "UI must let doctor continue as-is"),
        (window, "def _prompt_regulatory_completion_values", "accepted soft advice must open a completion-values popup"),
        (window, "Сохранить введённые дополнения", "completion popup must let doctor save optional values"),
        (window, "_refresh_custom_profile_tiles", "profile updates must refresh dynamic block-03 buttons"),
        (regulatory_completion, "COMPLETION_POPUP_LOCK_VERSION", "completion popup lock is missing"),
        (regulatory_completion, "COMPLETION_VALUES_ARE_OPTIONAL = True", "completion values must remain optional"),
        (regulatory_completion, "def completion_inputs_from_advice", "soft suggestions must become concrete completion inputs"),
        (regulatory_completion, "def apply_completion_values", "soft completion values must merge into PatientCase"),
        (regulatory_caucasus, "CAUCASUS_ALIAS_LOCK_VERSION", "Caucasus alias lock is missing"),
        (regulatory_caucasus, "armenia", "Caucasus aliases must include Armenia"),
        (regulatory_caucasus, "georgia", "Caucasus aliases must include Georgia"),
        (regulatory_caucasus, "azerbaijan", "Caucasus aliases must include Azerbaijan"),
        (regulatory_caucasus, "Հիվանդության պատմություն", "Armenian inpatient record marker is missing"),
        (regulatory_caucasus, "სამედიცინო ბარათი", "Georgian medical-card marker is missing"),
        (regulatory_caucasus, "Xəstəlik tarixi", "Azerbaijani case-history marker is missing"),
        (language_catalog, "LANGUAGE_CATALOG_LOCK_VERSION", "language catalog lock is missing"),
        (language_catalog, "SUPPORTED_LANGUAGE_IDS", "supported language ids are missing"),
        (language_detector, "def detect_text_language", "document language detector is missing"),
        (language_detector, "def detect_docx_language", "DOCX language detector is missing"),
        (i18n_strings, "def tr", "UI translation helper is missing"),
        (orthography, "ORTHOGRAPHY_MEDICAL_SAFE_LOCK_VERSION", "medical-safe orthography lock is missing"),
        (orthography, "ORTHOGRAPHY_IS_CONSERVATIVE = True", "orthography must stay conservative"),
        (orthography, "{{patient.fio}}", "orthography lock must protect placeholders"),
        (personal_buttons, "PERSONAL_DOCUMENT_BUTTON_LOCK_VERSION", "personal document button lock is missing"),
        (personal_buttons, "BUTTON_LABEL_IS_PROFILE_DATA = True", "button labels must be persisted as profile data"),
        (personal_buttons, "localized_role_label", "localized role labels for regular document buttons are missing"),
        (personal_buttons, "operation_protocol", "operation protocol must have a role-aware button label"),
        (template_engine, "button_label_source", "DocumentTemplateSpec must persist button label source"),
        (window, "Создать кнопку документа", "UI must let the doctor create a persistent regular document button"),
        (language_preferences, "LanguagePreferences", "language preferences model is missing"),
        (window, "def _open_language_settings", "UI language settings dialog is missing"),
        (window, "def _effective_output_language", "output language resolver is missing"),
        (template_engine, "correct_case_values", "custom renderer must run orthography pipeline under the hood"),
        (regulatory_completion, "COMPLETION_POPUP_TITLE = \"Дополнить документ\"", "completion popup title must be doctor-respectful"),
        (main_documents, 'CUSTOM_DOCUMENT_KIND_PREFIX = "custom_profile:"', "dynamic medpack buttons need a reserved namespace"),
        (main_documents, "def assert_dynamic_medpack_button_lock", "dynamic medpack button lock is missing"),
        (main_documents, "def custom_documents_for_main_ui", "main UI must expose profile-owned custom templates"),
        (case_adapter, "def patient_data_to_case", "old PatientData must adapt to universal PatientCase"),
        (universal_actions, "def _create_custom_documents_impl", "main creation flow must render selected custom profile documents"),
        (layout, "FIRST_RUN_CREATE_BUTTON_LABEL", "block 03 must start as an empty doctor-owned constructor"),
        (selection, "def selected_custom_docs", "selection layer must return custom document ids"),
        (orchestrator, "selected_custom = self.selected_custom_docs()", "creation orchestrator must include custom selections"),
        (smoke, "advise_template", "smoke suite must exercise regulatory template advice"),
        (smoke, "assert_soft_advisory_lock", "smoke suite must lock non-blocking advisory policy"),
        (smoke, "classify_docx", "smoke suite must exercise document role classifier"),
        (smoke, "assert_dynamic_medpack_button_lock", "smoke suite must lock dynamic medpack namespace"),
        (smoke, "completion_inputs_from_advice", "smoke suite must exercise soft-completion popup inputs"),
        (smoke, "assert_caucasus_alias_lock", "smoke suite must lock Caucasus regional aliases"),
        (smoke, "assert_language_catalog_lock", "smoke suite must lock language catalog"),
        (smoke, "assert_language_detection_lock", "smoke suite must lock language detector"),
        (smoke, "assert_i18n_strings_lock", "smoke suite must lock i18n strings"),
        (smoke, "assert_orthography_medical_safe_lock", "smoke suite must lock safe orthography"),
        (smoke, "Հիվանդության պատմություն", "smoke suite must exercise Armenian document markers"),
        (smoke, "სამედიცინო ბარათი", "smoke suite must exercise Georgian document markers"),
        (smoke, "Xəstəlik tarixi", "smoke suite must exercise Azerbaijani document markers"),
        (smoke, "patient_data_to_case", "smoke suite must exercise PatientData to PatientCase adapter"),
    ]
    missing = [message for source, snippet, message in required_pairs if snippet not in source]
    if missing:
        _fail("Universal profile contract is incomplete:\n" + "\n".join(missing))
    # The universal mapper UI previously compiled but placed import/render buttons
    # inside an exception branch and leaked helper functions to module scope.
    # Guard this exact class of Tkinter callback regressions.
    if "\ndef import_profile()" in window or "\ndef readiness_report()" in window or "\ndef render_custom_documents()" in window:
        _fail("Universal mapper callbacks escaped the mapper dialog surface scope")
    if 'except Exception as exc:' not in window or 'messagebox.showerror("Custom DOCX"' not in window:
        _fail("Universal custom render error branch is missing")
    custom_error_pos = window.find('messagebox.showerror("Custom DOCX"')
    button_pos = window.find("button_specs = [")
    if custom_error_pos == -1 or button_pos == -1 or button_pos < custom_error_pos:
        _fail("Universal mapper buttons must be created after callback definitions, not inside an error branch")


def _assert_doctor_owned_constructor_contract() -> None:
    """Block user-facing return of bundled medical templates."""
    embedded = _read("embedded_templates.py")
    profiles = _read("universal_profiles.py")
    layout = _read("layout_checklist.py")
    mapper = _read_many("window_mapper_dialog.py", "window_setup_center.py", "window_document_mapper.py")
    orchestrator = _read_many("actions_creation_orchestrator.py", "actions_creation_preflight.py", "actions_creation_foldering.py", "actions_creation_maintenance.py", "actions_creation_batch.py", "actions_creation_execution.py")
    folder = _read("desktop_patient_folder.py")
    readme = _read("README.md")
    fix = _read("FIX_REPORT.md")
    checklist = _read("LAUNCH_CHECKLIST.md")
    app_config = _read("app_config.py")

    required = [
        (embedded, "TEMPLATE_B64: dict[str, str] = {}", "embedded template storage must be empty"),
        (profiles, "documents=()", "default document pack must have no seeded medical documents"),
        (profiles, "current_builtin_documents", "legacy compatibility hook must remain explicit"),
        (profiles, "returns no medical documents", "current_builtin_documents must document the empty result"),
        (layout, "FIRST_RUN_CREATE_BUTTON_LABEL = \"Создать свои кнопки\"", "block 03 empty-state must show the first-run create-buttons CTA"),
        (layout, "BLOCK03_EMPTY_STATE_HAS_ONLY_CREATE_BUTTON = True", "block 03 empty-state must hide all other buttons before setup"),
        (layout, "command=self._open_first_run_create_buttons_popup", "block 03 must route first-run CTA to template upload popup"),
        (mapper, "Выбрать Word-шаблоны и создать кнопки", "template setup must support 10-second batch recognition"),
        (mapper, "Как называть сохранённую папку?", "template setup must lead into patient-folder naming"),
        (orchestrator, "def configure_patient_folder_naming_dialog", "folder naming dialog must exist"),
        (folder, "FOLDER_NAMING_OPTIONS", "folder naming options must be locked in code"),
        (folder, "Иванов И.И. 06.06.26", "folder naming lock must verify short discharge-date example"),
        (app_config, TARGET_VERSION_LABEL, "app version must reflect architecture/pytest quality modernization release"),
    ]
    missing = [message for source, snippet, message in required if snippet not in source]
    if missing:
        _fail("Doctor-owned constructor contract is incomplete:\n" + "\n".join(missing))

    docs = "\n".join([readme, fix, checklist]).casefold()
    forbidden = [
        "создание выбранных медицинских документов по встроенным шаблонам",
        "встроенные шаблоны хранятся",
        "текущий рабочий психиатрический комплект сохран",
        "create_documents_batch() создаёт реальные встроенные",
    ]
    leaked = [phrase for phrase in forbidden if phrase in docs]
    if leaked:
        _fail("User-facing docs still promise bundled medical templates:\n" + "\n".join(leaked))



def _assert_v141_production_cleanup_contract() -> None:
    orchestrator = _read_many("actions_creation_orchestrator.py", "actions_creation_preflight.py", "actions_creation_foldering.py", "actions_creation_maintenance.py", "actions_creation_batch.py", "actions_creation_execution.py")
    completion = _read("window_completion_dialog.py")
    fields = _read("universal_fields.py")
    main_docs = _read("universal_main_documents.py")
    expert = _read("dialog_expert.py")
    diary = _read("diary_text_selection.py")
    primary = _read("medical_renderer_primary.py")
    commission = _read("medical_renderer_commission.py")
    special = _read("medical_renderer_special.py")
    rvk_dialog = _read("dialog_document_details.py")

    forbidden_pairs = [
        (orchestrator, "Продолжить без заполненного обязательного поля", "required preflight popup must not allow bypassing mandatory fields"),
        (completion, "Продолжить без заполненного обязательного поля", "regulatory required popup must not allow bypassing mandatory fields"),
        (diary, "asthenia", "diary matching must not contain narrow legacy semantic bridge"),
        (diary, "астен", "diary matching must not contain narrow legacy Russian bridge"),
        (primary, "Можар", "primary renderer must not contain personal doctor names"),
        (primary + commission + special, "Н. Новгород", "renderers must not fabricate a city/address fallback"),
        (commission, "На учёте у психиатров:", "admission referral output label must be neutral"),
        (rvk_dialog, "Ленинский", "RVK popup must not contain locality-specific hardcoded choices"),
        (rvk_dialog, "Канавинский", "RVK popup must not contain locality-specific hardcoded choices"),
        (rvk_dialog, "Сормовский", "RVK popup must not contain locality-specific hardcoded choices"),
    ]
    leaked = [message for source, snippet, message in forbidden_pairs if snippet in source]
    if leaked:
        _fail("Production cleanup contract leaked forbidden content:\n" + "\n".join(leaked))

    required_pairs = [
        (orchestrator, "return False", "required preflight popup must be able to block generation"),
        (orchestrator, "Дата выписки не может быть раньше даты поступления", "required discharge date must be range-validated inside the popup"),
        (completion, "Пустыми их оставлять нельзя", "required regulatory popup must be strict"),
        (fields, "_FIELD_ID_ALIASES", "semantic field aliases must be centralized"),
        (fields, '"treatment.summary": "treatment.plan"', "legacy treatment.summary placeholder must canonicalize to treatment.plan"),
        (fields, '"case_number": "case.number"', "case_number placeholder must canonicalize to case.number"),
        (main_docs, "normalize_field_id(raw)", "custom required fields must use canonical semantic ids"),
        (expert, "_active_custom_requirement_flags", "custom discharge role must participate in sick-leave number popup chain"),
        (primary, "Первичный осмотр\"", "primary header must be neutral"),
        (commission, "Профильное наблюдение:", "legacy source marker must render to neutral profile observation label"),
        (rvk_dialog, "Военкомат / организация направления", "RVK popup must allow neutral manual organization input"),
    ]
    missing = [message for source, snippet, message in required_pairs if snippet not in source]
    if missing:
        _fail("Production cleanup contract is incomplete:\n" + "\n".join(missing))



def _assert_no_shell_desktop_intake_contract() -> None:
    app_init = _read("app_initialization.py")
    printer_discovery = _read("printer_discovery.py")
    printer_jobs = _read("printer_jobs.py")
    uninstall = _read("uninstall_background_watcher.bat").casefold()
    if "refresh_printers(silent=True)" in app_init:
        _fail("Desktop-intake startup must not auto-scan printers")
    if "_bootstrap_printer_field_without_shell_scan" not in app_init:
        _fail("Startup must bootstrap printer field without shell scan")
    for path, source in (("printer_discovery.py", printer_discovery), ("printer_jobs.py", printer_jobs)):
        low = source.casefold()
        forbidden = ["powershell", "get-ciminstance", "wscript.network", "import subprocess", "subprocess.run", "subprocess.popen"]
        leaked = [item for item in forbidden if item in low]
        if leaked:
            _fail(f"{path} still contains shell-based printer fallback: {', '.join(leaked)}")
    if "powershell" in uninstall:
        _fail("Watcher uninstaller must not use PowerShell")

def _assert_architecture_contracts() -> None:
    try:
        from architecture_contracts import assert_architecture_contracts

        assert_architecture_contracts()
    except Exception as exc:
        _fail(f"Architecture contracts failed: {exc}")


def main() -> None:
    _assert_version_sync()
    _assert_architecture_hygiene()
    _assert_no_import_cycles()
    _assert_architecture_contracts()
    _assert_no_deleted_module_references()
    _assert_public_modules_importable()
    _assert_startup_state_contract()
    _assert_smoke_entrypoint_contract()
    _assert_release_zip_excludes_generated_runs()
    _assert_dnd_contract()
    _assert_discharge_date_contract()
    _assert_dialog_runtime_globals_contract()
    _assert_treatment_popup_contract()
    _assert_audit_hardening_contract()
    _assert_release_documents()
    _assert_doctor_owned_constructor_contract()
    _assert_universal_profile_contract()
    _assert_no_shell_desktop_intake_contract()
    _assert_quality_100_contract()
    print("PROD AUDIT OK")


if __name__ == "__main__":
    main()
