"""Architecture locks for production hardening.

This gate is intentionally stdlib-only.  It protects the project against the
same regressions that are easy to reintroduce when the universal/profile layer
grows: cycles, UI dependencies leaking into core modules, god modules and dust
micro-modules.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARCHITECTURE_CONTRACT_LOCK_VERSION = "v2.4"
# No blind "150 files" ceiling. The project is allowed to grow when a new
# product layer has a clear responsibility, tests and locks. What is forbidden
# is uncontrolled growth: import cycles, UI leakage into core, god modules and
# lots of tiny one-purpose dust files. Budget v1.3 raises the explicit ceiling
# from 182 to 200 because the former limit was fully consumed; the extra room is
# reserved for documented split-out dialog/action modules and tests, not drift.
# The auditor layer has its own smoke: smoke_auditor_layer.py.
TOTAL_PYTHON_FILE_BUDGET = 200
MAX_GENERAL_MODULE_LINES = 1200
MAX_BIG_MODULE_LINES = 1600
MAX_TINY_NON_ENTRYPOINT_FILES = 25
LAYER_FILE_BUDGETS = {
    "auditor": 20,
    "universal_regulatory_language": 42,
    "ui_actions": 50,
    "domain_medical_diary": 74,
    "release_quality": 40,
    "misc": 24,
}

BIG_MODULE_EXEMPTIONS = {
    "embedded_templates.py",
    "icd10_f_data.py",
}
TINY_FILE_EXEMPTIONS = {
    "main.py",
    "medical_documents.py",
    "diary_filler.py",
    "printer_support.py",
    "icd10_f.py",
    "smoke_test.py",
    "smoke_test_combined.py",
    "smoke_project_auditor.py",
}
CORE_PREFIXES = (
    "universal_",
    "regulatory_",
    "medical_language_",
    "medical_orthography",
    "personal_document_buttons",
    "auditor_",
    "project_auditor",
)
UI_OR_ACTION_PREFIXES = ("window_", "layout_", "dialog_", "actions_")
FORBIDDEN_CORE_IMPORT_ROOTS = {
    "tkinter",
    "PyQt5",
    "PySide6",
    "customtkinter",
    "window_mixin",
    "layout_mixin",
    "dialogs_mixin",
    "actions_mixin",
}

CENTRAL_DESKTOP_OPEN_BOUNDARY_ALLOWED_FILES = {
    "printer_platform.py",      # one audited open-file/open-folder helper
    "printer_jobs.py",          # Windows print verb, not general opening
    "desktop_intake_agent.py",  # hidden background agent launcher
}


WILDCARD_IMPORT_ALLOWED_FILES = {
    "medical_documents.py",  # compatibility facade for the old public medical API
    "diary_filler.py",       # compatibility facade for the old public diary API
}

UI_SHELL_IMPORT_FORBIDDEN_PREFIXES = (
    "actions_",
    "dialog_",
    "dnd_",
    "files_",
    "layout_",
    "settings_",
    "ui_",
    "window_",
)
UI_SHELL_IMPORT_FORBIDDEN_FILES = {
    "desktop_intake_mixin.py",
    "diagnosis_widget.py",
}

DOMAIN_APP_CONFIG_FORBIDDEN_PREFIXES = (
    "diary_",
    "medical_",
    "universal_",
    "regulatory_",
    "auditor_",
    "project_auditor",
)
DOMAIN_APP_CONFIG_ALLOWED_FILES = {
    "app_config.py",
    "architecture_contracts.py",
    "prod_audit.py",
    "release_check.py",
}
PRIMARY_PATH_DIRECT_READ_ALLOWED_FILES = {
    "files_mixin.py",               # owner of block-01 selection and file dialogs
    "layout_sources.py",            # visual drop-zone rendering only
    "medical_primary_document_state.py",
}

SEMANTIC_DATE_DIRECT_READ_ALLOWED_FILES = {
    "dialog_dates.py",              # owner of manual date field commit/normalization
}

TECHNICAL_REPORT_FILENAMES = (
    "custom_profile_generation_report.txt",
    "custom_generation_report.txt",
    "ОТЧЁТ_создание_документов.txt",
    "ОТЧЁТ_дневники.txt",
)

SEMANTIC_DATE_DIRECT_READ_MARKERS = (
    "admission_date_var.get",
    "discharge_date_var.get",
    "commission_date_var.get",
    "vk_date_var.get",
    "vk_protocol_date_var.get",
    "sick_leave_vk_date_var.get",
    "sick_leave_vk_protocol_date_var.get",
    "sick_leave_vk_commission_date_var.get",
    "expert_sick_leave_from_var.get",
    "labs_explicit_date_var.get",
)


def python_files() -> tuple[Path, ...]:
    return tuple(sorted(ROOT.glob("*.py"), key=lambda item: item.name.lower()))


def local_import_graph() -> dict[str, set[str]]:
    local_modules = {path.stem for path in python_files()}
    graph: dict[str, set[str]] = {path.stem: set() for path in python_files()}
    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
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


def assert_no_import_cycles() -> None:
    graph = local_import_graph()
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def dfs(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            start = stack.index(node) if node in stack else 0
            raise AssertionError("Local import cycle detected: " + " -> ".join([*stack[start:], node]))
        visiting.add(node)
        stack.append(node)
        for child in sorted(graph.get(node, ())):
            dfs(child)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        dfs(node)


def _module_import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def assert_core_layers_do_not_import_ui() -> None:
    bad: list[str] = []
    for path in python_files():
        stem = path.stem
        if not (stem.startswith(CORE_PREFIXES) or stem in CORE_PREFIXES):
            continue
        roots = _module_import_roots(path)
        forbidden = sorted(root for root in roots if root in FORBIDDEN_CORE_IMPORT_ROOTS or root.startswith(UI_OR_ACTION_PREFIXES))
        if forbidden:
            bad.append(f"{path.name}: {', '.join(forbidden)}")
    if bad:
        raise AssertionError("Core/universal/regulatory modules must not import UI/action layers:\n" + "\n".join(bad))


def module_layer(path: Path) -> str:
    name = path.name
    stem = path.stem
    if stem.startswith("auditor_") or stem.startswith("project_auditor") or stem == "auditor_layer":
        return "auditor"
    if stem.startswith(("universal_", "regulatory_", "medical_language_", "medical_orthography")) or stem in {"personal_document_buttons", "i18n_strings", "language_preferences"}:
        return "universal_regulatory_language"
    if stem.startswith(("window_", "layout_", "dialog_", "actions_", "files_", "dnd_", "widgets_", "settings_", "diagnosis_")) or stem in {"app", "app_initialization"}:
        return "ui_actions"
    if stem.startswith(("medical_", "diary_", "icd10")) or stem in {"embedded_templates", "printer_support", "medical_documents"}:
        return "domain_medical_diary"
    if stem.startswith(("smoke", "prod_audit", "release_check", "performance", "dnd_contract", "architecture_contracts", "make_release")):
        return "release_quality"
    return "misc"


def layer_file_counts() -> dict[str, int]:
    counts = {layer: 0 for layer in LAYER_FILE_BUDGETS}
    for path in python_files():
        layer = module_layer(path)
        counts[layer] = counts.get(layer, 0) + 1
    return counts


def assert_layer_file_budget() -> None:
    files = python_files()
    if len(files) > TOTAL_PYTHON_FILE_BUDGET:
        raise AssertionError(f"Too many Python files: {len(files)} > {TOTAL_PYTHON_FILE_BUDGET}")
    counts = layer_file_counts()
    over = [f"{layer}: {count} > {LAYER_FILE_BUDGETS[layer]}" for layer, count in sorted(counts.items()) if count > LAYER_FILE_BUDGETS.get(layer, 999)]
    if over:
        raise AssertionError("Layer file budget exceeded:\n" + "\n".join(over))


def assert_no_god_modules_or_dust() -> None:
    assert_layer_file_budget()
    files = python_files()
    oversized: list[str] = []
    tiny: list[str] = []
    for path in files:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        limit = MAX_BIG_MODULE_LINES if path.name in BIG_MODULE_EXEMPTIONS else MAX_GENERAL_MODULE_LINES
        if len(lines) > limit:
            oversized.append(f"{path.name}: {len(lines)} > {limit}")
        if path.name not in TINY_FILE_EXEMPTIONS and len(lines) <= 20:
            tiny.append(path.name)
    if oversized:
        raise AssertionError("God-module line budget exceeded:\n" + "\n".join(oversized))
    if len(tiny) > MAX_TINY_NON_ENTRYPOINT_FILES:
        raise AssertionError("Too many tiny dust modules:\n" + "\n".join(tiny))


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def assert_desktop_open_boundary_is_centralized() -> None:
    """Keep all user-visible file/folder opening behind one audited helper."""

    bad: list[str] = []
    for path in python_files():
        if path.name.startswith(("smoke", "test_")) or path.name in {"prod_audit.py", "release_check.py", "project_auditor_rules.py", "architecture_contracts.py"}:
            continue
        if path.name in CENTRAL_DESKTOP_OPEN_BOUNDARY_ALLOWED_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        snippets: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call = _call_name(node.func)
            if call in {"os.startfile", "subprocess.Popen"}:
                snippets.append(call)
        if snippets:
            bad.append(f"{path.name}: {', '.join(sorted(set(snippets)))}")
    if bad:
        raise AssertionError("Desktop open/launch boundary must be centralized in printer_platform.py:\n" + "\n".join(bad))



def assert_no_wildcard_imports_outside_facades() -> None:
    """Keep hidden namespace coupling out of implementation modules.

    Public compatibility facades may re-export old APIs, but production
    implementation files must import the names they use explicitly.  This
    prevents app_config/domain drift where a module silently starts depending
    on unrelated UI or runtime constants.
    """

    bad: list[str] = []
    for path in python_files():
        if path.name in WILDCARD_IMPORT_ALLOWED_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
                bad.append(f"{path.name}:{node.lineno} from {node.module or ''} import *")
    if bad:
        raise AssertionError("Wildcard imports are allowed only in public compatibility facades:\n" + "\n".join(bad))


def assert_ui_layers_do_not_import_subprocess() -> None:
    """Do not let UI/action code regain ad-hoc process launch paths."""

    bad: list[str] = []
    for path in python_files():
        name = path.name
        if name.startswith(("smoke", "test_")) or name in {"prod_audit.py", "release_check.py", "performance_check.py", "architecture_contracts.py"}:
            continue
        if name in CENTRAL_DESKTOP_OPEN_BOUNDARY_ALLOWED_FILES:
            continue
        is_ui = name.startswith(UI_SHELL_IMPORT_FORBIDDEN_PREFIXES) or name in UI_SHELL_IMPORT_FORBIDDEN_FILES
        if not is_ui:
            continue
        roots = _module_import_roots(path)
        if "subprocess" in roots:
            bad.append(name)
    if bad:
        raise AssertionError("UI/action layers must not import subprocess; use audited platform/service boundaries:\n" + "\n".join(sorted(bad)))

def assert_domain_modules_do_not_import_app_config() -> None:
    """Keep domain/discovery/generation modules independent from UI config.

    ``app_config`` contains colors, window title and UI-facing defaults.  Domain
    code must import semantic constants from medical_constants/diary_constants
    instead, otherwise changing a style/config file can unexpectedly affect
    document parsing or diary discovery.
    """

    bad: list[str] = []
    for path in python_files():
        name = path.name
        stem = path.stem
        if name.startswith(("smoke", "test_")) or name in DOMAIN_APP_CONFIG_ALLOWED_FILES:
            continue
        if not stem.startswith(DOMAIN_APP_CONFIG_FORBIDDEN_PREFIXES):
            continue
        roots = _module_import_roots(path)
        if "app_config" in roots:
            bad.append(name)
    if bad:
        raise AssertionError("Domain modules must not import app_config; use domain constants instead:\n" + "\n".join(sorted(bad)))


def assert_primary_path_resolver_contract() -> None:
    """Prevent recurrence of the 'UI shows selected DOCX but creation sees none' bug.

    Creation/dialog/discovery code must use selected_primary_document_path*() so
    runtime attrs, visual drop-zone state and navigation_path_var are synced.
    Only the file chooser owner and visual layout are allowed to read the raw
    StringVar directly.
    """

    bad: list[str] = []
    for path in python_files():
        name = path.name
        if name.startswith(("smoke", "test_")) or name in PRIMARY_PATH_DIRECT_READ_ALLOWED_FILES:
            continue
        if not (name.startswith(("actions_", "dialog_", "diary_template_"))):
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        if "navigation_path_var.get" in source:
            bad.append(name)
    if bad:
        raise AssertionError("Creation/dialog code must use medical_primary_document_state resolver instead of raw navigation_path_var.get():\n" + "\n".join(sorted(bad)))


def assert_semantic_dates_use_central_resolver() -> None:
    """Keep patient dates behind medical_date_state in all non-owner modules.

    Date regressions were caused by popups, diaries, custom documents and
    legacy flows reading different Tk variables directly.  Only dialog_dates.py
    may read the raw discharge field while committing manual UI input.  Every
    other module must use current_semantic_date()/apply_semantic_date() so
    conflict checks, normalization and doctor-confirmed values stay consistent.
    """

    bad: list[str] = []
    for path in python_files():
        name = path.name
        if name.startswith(("smoke", "test_")) or name in {"prod_audit.py", "release_check.py", "project_auditor_rules.py", "architecture_contracts.py"}:
            continue
        if name in SEMANTIC_DATE_DIRECT_READ_ALLOWED_FILES:
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        markers = sorted(marker for marker in SEMANTIC_DATE_DIRECT_READ_MARKERS if marker in source)
        if markers:
            bad.append(f"{name}: {', '.join(markers)}")
    if bad:
        raise AssertionError("Patient-level dates must use medical_date_state resolver instead of raw Tk StringVar.get():\n" + "\n".join(bad))



def _decorator_names(node: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def assert_annotated_contract_models_are_constructible() -> None:
    """Keep Result/Info/Data contracts as real dataclasses or explicit classes.

    A bare class with only type annotations has no generated ``__init__``.  That
    exact regression makes runtime paths fail with ``TypeError: X() takes no
    arguments`` while static import/compile checks stay green.  Contract models
    that are instantiated by UI/service code must either be dataclasses or define
    their own constructor.
    """

    endings = ("Result", "Info", "Config", "Settings", "Data")
    bad: list[str] = []
    for path in python_files():
        if path.name.startswith(("smoke", "test_")) or path.name in {"architecture_contracts.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not node.name.endswith(endings):
                continue
            has_annotations = any(isinstance(item, ast.AnnAssign) for item in node.body)
            if not has_annotations:
                continue
            has_init = any(isinstance(item, ast.FunctionDef) and item.name == "__init__" for item in node.body)
            is_dataclass = "dataclass" in _decorator_names(node)
            if not has_init and not is_dataclass:
                bad.append(f"{path.name}:{node.lineno} class {node.name}")
    if bad:
        raise AssertionError(
            "Annotated contract models must be dataclasses or define __init__; "
            "otherwise runtime instantiation fails after import checks pass:\n" + "\n".join(sorted(bad))
        )


def assert_patient_folders_do_not_receive_technical_reports() -> None:
    """Keep patient output folders clean from TXT diagnostics.

    Doctors expect «Выписанные пациенты/<пациент>» to contain only the medical
    DOCX/DOCM files selected in block 03.  Technical reports may exist, but only
    through medical_formatting.technical_report_path()/history_dir(), which routes
    them to the app-data history area instead of the patient subfolder.
    """

    bad: list[str] = []
    for path in python_files():
        name = path.name
        if name.startswith(("smoke", "test_")) or name in {"architecture_contracts.py", "actions_reports.py"}:
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        if not any(filename in source for filename in TECHNICAL_REPORT_FILENAMES):
            continue
        if "technical_report_path(" not in source and "history_dir(" not in source:
            bad.append(name)
        for filename in TECHNICAL_REPORT_FILENAMES:
            if f'/ "{filename}"' in source and "technical_report_path(" not in source and "history_dir(" not in source:
                bad.append(f"{name}: direct path join for {filename}")
    if bad:
        raise AssertionError(
            "Patient/output folders must not receive technical report TXT files; "
            "route them through medical_formatting.technical_report_path()/history_dir():\n"
            + "\n".join(sorted(set(bad)))
        )


def assert_technical_reports_are_privacy_safe() -> None:
    """Technical history must not silently duplicate patient identifiers.

    Doctors may keep patient-named folders and DOCX files, but app-data support
    logs/reports are a different boundary.  They must store pseudonymous refs,
    counts and redacted errors rather than raw FIO, case numbers, dates, paths or
    generated filenames.  UI messages can still show doctor-facing paths during
    the active operation.
    """

    service = (ROOT / "medical_service.py").read_text(encoding="utf-8", errors="replace")
    universal = (ROOT / "universal_generation.py").read_text(encoding="utf-8", errors="replace")
    reports = (ROOT / "actions_reports.py").read_text(encoding="utf-8", errors="replace")
    batch = (ROOT / "actions_creation_batch.py").read_text(encoding="utf-8", errors="replace")
    privacy = (ROOT / "medical_formatting.py").read_text(encoding="utf-8", errors="replace")

    required = {
        "medical_service.save_batch_generation_report": "result.technical_report()" in service,
        "universal_generation.save_generation_report": "result.technical_report()" in universal,
        "actions_reports.patient_ref": '"patient_ref"' in reports,
        "actions_reports.no_raw_patient_key": '"patient":' not in reports and '"fio_in_documents"' not in reports,
        "actions_reports.no_raw_created_files_key": '"created_files"' not in reports,
        "actions_reports.redacted_errors": "errors_redacted" in reports and "redact_technical_text" in reports,
        "custom_batch_split_display_and_technical": "display_lines" in batch and "technical_lines" in batch,
        "custom_batch_redacts_technical_errors": "redact_technical_text" in batch and "technical_ref" in batch,
        "technical_privacy_lock": "assert_technical_privacy_lock" in privacy,
    }
    missing = [name for name, ok in required.items() if not ok]
    if missing:
        raise AssertionError("Technical reports/history must be privacy-safe and redacted:\n" + "\n".join(missing))



def assert_diary_reports_are_technical_and_redacted() -> None:
    """Diary diagnostics must not be written into patient folders or contain PII."""

    diary = (ROOT / "diary_batch.py").read_text(encoding="utf-8", errors="replace")
    required = {
        "diary_report_uses_technical_path": 'technical_report_path(result_dir, "ОТЧЁТ_дневники.txt")' in diary,
        "diary_report_no_result_dir_join": 'result_dir / "ОТЧЁТ_дневники.txt"' not in diary,
        "diary_report_has_patient_ref": "technical_ref(patient_filename" in diary,
        "diary_report_redacts_free_text": "redact_technical_text" in diary,
        "diary_report_no_patient_line": "Пациент / имя файлов" not in diary and "ФИО для определения рода" not in diary,
    }
    missing = [name for name, ok in required.items() if not ok]
    if missing:
        raise AssertionError("Diary technical report must be outside patient folders and privacy-safe:\n" + "\n".join(missing))


def assert_startup_vbs_uses_wsh_safe_encoding() -> None:
    """Prevent the Windows boot-time VBS 'invalid character' regression.

    WScript/VBScript on real Windows machines may reject UTF-8-BOM scripts with
    line 1 / char 1 / 800A0408.  The Startup VBS must therefore be written by
    Python in UTF-16 with BOM, and the BAT installer must call that writer rather
    than echoing a VBS file manually.
    """

    agent = (ROOT / "desktop_intake_agent.py").read_text(encoding="utf-8", errors="replace")
    bat = (ROOT / "install_background_watcher.bat").read_text(encoding="utf-8", errors="replace")
    required = {
        "agent_writes_utf16_vbs": 'encoding="utf-16"' in agent,
        "agent_does_not_write_utf8_sig_vbs": 'script_path.write_text(script, encoding="utf-8-sig")' not in agent,
        "agent_has_utf16_lock_flag": "DESKTOP_INTAKE_AGENT_STARTUP_SCRIPT_IS_UTF16 = True" in agent,
        "agent_has_no_utf8_bom_lock_flag": "DESKTOP_INTAKE_AGENT_STARTUP_SCRIPT_HAS_NO_UTF8_BOM = True" in agent,
        "main_supports_install_cli": '"--install-intake-agent"' in (ROOT / "main.py").read_text(encoding="utf-8", errors="replace"),
        "bat_uses_python_writer_not_echo_vbs": "--install-autostart" in bat and "echo Set shell" not in bat and "echo shell.Run" not in bat,
    }
    missing = [name for name, ok in required.items() if not ok]
    if missing:
        raise AssertionError("Startup VBS must be WSH-safe UTF-16 and installed through the audited Python writer:\n" + "\n".join(missing))




def assert_release_version_metadata_is_consistent() -> None:
    """Release labels and Windows binary tuples must move together.

    v1.4.74 exposed a dangerous false-green gate: the human-facing label was
    bumped, but ``version_info.txt`` still shipped the previous EXE tuple and
    prod_audit.py accidentally accepted that old tuple.  This lock derives the
    expected numeric tuple from pyproject.toml instead of hardcoding a previous
    release number in yet another place.
    """

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8", errors="replace")
    app_config = (ROOT / "app_config.py").read_text(encoding="utf-8", errors="replace")
    version_info = (ROOT / "version_info.txt").read_text(encoding="utf-8", errors="replace")
    prod_audit = (ROOT / "prod_audit.py").read_text(encoding="utf-8", errors="replace")
    match = re.search(r'^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"\s*$', pyproject, flags=re.MULTILINE)
    if not match:
        raise AssertionError("pyproject.toml must expose a numeric MAJOR.MINOR.PATCH version")
    major, minor, patch = (int(part) for part in match.groups())
    version = f"{major}.{minor}.{patch}"
    tuple_literal = f"({major}, {minor}, {patch}, 0)"
    label_prefix = f"v{version}_"
    required = {
        "app_config label prefix": label_prefix in app_config,
        "version_info file tuple": f"filevers={tuple_literal}" in version_info,
        "version_info product tuple": f"prodvers={tuple_literal}" in version_info,
        "version_info label prefix": label_prefix in version_info,
        "prod_audit target version": f'TARGET_VERSION = "{version}"' in prod_audit,
        "prod_audit derives tuple": "def _target_version_tuple_literal" in prod_audit,
        "prod_audit no stale fixed filevers": "filevers=(1, 4, 73, 0)" not in prod_audit,
        "prod_audit no stale fixed prodvers": "prodvers=(1, 4, 73, 0)" not in prod_audit,
    }
    missing = [name for name, ok in required.items() if not ok]
    if missing:
        raise AssertionError("Release version metadata must be synchronized and derived:\n" + "\n".join(missing))

def assert_soft_diagnostics_are_privacy_safe() -> None:
    diagnostics = (ROOT / "diagnostic_logging.py").read_text(encoding="utf-8", errors="replace")
    required = {
        "diagnostic_lock_v12": 'DIAGNOSTIC_LOGGING_LOCK_VERSION = "v1.2"' in diagnostics,
        "diagnostic_redactor": "def redact_diagnostic_text" in diagnostics,
        "diagnostic_no_raw_exc_info": "exc_info=exc_info" not in diagnostics,
        "diagnostic_safe_traceback": "def _safe_traceback" in diagnostics,
        "diagnostic_detail_redacted": "safe_detail = redact_diagnostic_text" in diagnostics,
    }
    missing = [name for name, ok in required.items() if not ok]
    if missing:
        raise AssertionError("Soft diagnostics must redact paths/patient data and avoid raw exc_info tracebacks:\n" + "\n".join(missing))


def assert_doctor_action_journal_is_privacy_safe() -> None:
    journal = (ROOT / "doctor_action_journal.py").read_text(encoding="utf-8", errors="replace")
    required = {
        "journal_lock_v13": 'DOCTOR_ACTION_JOURNAL_LOCK_VERSION = "v1.3"' in journal,
        "journal_uses_technical_ref": "technical_ref(" in journal,
        "journal_redacts_details": "redact_technical_text" in journal,
        "journal_counts_created_files": '"created_file_count"' in journal,
        "journal_no_created_files_payload": '"created_files":' not in journal,
        "journal_no_output_fio_payload": 'result["output_fio"]' not in journal and 'result["case_number"]' not in journal,
    }
    missing = [name for name, ok in required.items() if not ok]
    if missing:
        raise AssertionError("Doctor action journal must be privacy-safe support metadata, not a patient ledger:\n" + "\n".join(missing))


def assert_desktop_agent_pending_state_is_pathless() -> None:
    agent = (ROOT / "desktop_intake_agent.py").read_text(encoding="utf-8", errors="replace")
    required = {
        "agent_lock_v17": 'AGENT_VERSION = "v1.7"' in agent,
        "agent_pathless_flag": "DESKTOP_INTAKE_AGENT_STATE_IS_PATHLESS = True" in agent,
        "agent_redacted_log_flag": "DESKTOP_INTAKE_AGENT_LOGS_ARE_REDACTED = True" in agent,
        "agent_no_pending_path_write": '"path": str(candidate.path)' not in agent,
        "agent_no_pending_path_read": 'pending["path"]' not in agent,
        "agent_no_raw_candidate_name_log": "candidate.path.name" not in agent,
        "agent_signature_probe": "_signature_present_in_folder" in agent,
    }
    missing = [name for name, ok in required.items() if not ok]
    if missing:
        raise AssertionError("Desktop intake agent pending state/logs must not store patient paths or filenames:\n" + "\n".join(missing))

def assert_architecture_contracts() -> None:
    if ARCHITECTURE_CONTRACT_LOCK_VERSION != "v2.4":
        raise AssertionError("Architecture contract lock changed unexpectedly")
    assert_no_import_cycles()
    assert_core_layers_do_not_import_ui()
    assert_no_god_modules_or_dust()
    assert_no_wildcard_imports_outside_facades()
    assert_ui_layers_do_not_import_subprocess()
    assert_domain_modules_do_not_import_app_config()
    assert_primary_path_resolver_contract()
    assert_semantic_dates_use_central_resolver()
    assert_annotated_contract_models_are_constructible()
    assert_patient_folders_do_not_receive_technical_reports()
    assert_technical_reports_are_privacy_safe()
    assert_diary_reports_are_technical_and_redacted()
    assert_startup_vbs_uses_wsh_safe_encoding()
    assert_release_version_metadata_is_consistent()
    assert_soft_diagnostics_are_privacy_safe()
    assert_doctor_action_journal_is_privacy_safe()
    assert_desktop_agent_pending_state_is_pathless()
    assert_desktop_open_boundary_is_centralized()


if __name__ == "__main__":
    assert_architecture_contracts()
    print("ARCHITECTURE CONTRACTS OK")
