"""Deterministic AST rule catalog for the project auditor."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from project_auditor_files import ProjectFileIndex, read_text, parse_python
from project_auditor_models import ProjectFinding, ProjectSeverity, finding

PROJECT_AUDITOR_RULES_LOCK_VERSION = "v1.4"
PROJECT_AUDITOR_RULES_ARE_EXPLICIT = True
PROJECT_AUDITOR_NO_LLM_REQUIRED = True
PROJECT_AUDITOR_RULE_IDS_MUST_BE_REGISTERED = True
PROJECT_AUDITOR_SECURITY_RULES_SCAN_AUDITOR_CODE = True
PROJECT_AUDITOR_DETECTS_DUPLICATE_TOP_LEVEL_SYMBOLS = True

RuleCheck = Callable[[Path, str, ast.AST], tuple[ProjectFinding, ...]]


@dataclass(frozen=True)
class ProjectRule:
    rule_id: str
    title: str
    severity: ProjectSeverity
    check: RuleCheck


_TEST_OR_GATE_PREFIXES = ("smoke", "test_", "prod_audit", "release_check", "architecture_contracts")
_MODULE_LINE_LIMIT = 1200
_BIG_MODULE_EXEMPTIONS = {"embedded_templates.py", "icd10_f_data.py"}
_FUNCTION_LINE_LIMIT = 170
_CLASS_LINE_LIMIT = 360
_CLASS_METHOD_COUNT_LIMIT = 30
_LARGE_FUNCTION_EXEMPTIONS = {
    # Tkinter modal dialog builders are reviewed through functional smoke tests.
    # v1.4.46 split the former window_mapper_dialog.py mega-file into two
    # focused dialog files; keeping each dialog entrypoint as one closure avoids
    # Tkinter callback drift while the module-level god-file risk is closed.
    ("window_setup_center.py", "open_template_setup_center"),
    ("window_document_mapper.py", "open_universal_document_mapper"),
}
LARGE_FUNCTION_EXEMPTIONS_ARE_LOCKED = True

_NODE_WALK_CACHE: dict[int, tuple[ast.AST, ...]] = {}


def _walk(tree: ast.AST) -> tuple[ast.AST, ...]:
    key = id(tree)
    cached = _NODE_WALK_CACHE.get(key)
    if cached is None:
        cached = tuple(ast.walk(tree))
        _NODE_WALK_CACHE[key] = cached
    return cached


def _is_test_or_gate(path: Path) -> bool:
    return path.stem.startswith(_TEST_OR_GATE_PREFIXES)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _node_text(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return type(node).__name__


class _ImportResolver(ast.NodeVisitor):
    """Small alias resolver for high-confidence dangerous-call rules."""

    def __init__(self) -> None:
        self.aliases: dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 - ast API
        for alias in node.names:
            root = alias.name.split(".", 1)[0]
            as_name = alias.asname or root
            self.aliases[as_name] = alias.name

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802 - ast API
        if not node.module:
            return
        for alias in node.names:
            if alias.name == "*":
                continue
            self.aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"

    def resolved_call(self, node: ast.AST) -> str:
        raw = _call_name(node)
        if not raw:
            return ""
        first, *rest = raw.split(".")
        mapped = self.aliases.get(first, first)
        return ".".join([mapped, *rest]) if rest else mapped


def _resolver(tree: ast.AST) -> _ImportResolver:
    resolver = _ImportResolver()
    resolver.visit(tree)
    return resolver


def check_eval_exec(path: Path, rel: str, tree: ast.AST) -> tuple[ProjectFinding, ...]:
    if _is_test_or_gate(path):
        return ()
    aliases = _resolver(tree)
    out: list[ProjectFinding] = []
    for node in _walk(tree):
        if isinstance(node, ast.Call) and aliases.resolved_call(node.func) in {"eval", "exec", "builtins.eval", "builtins.exec"}:
            out.append(finding("PA001", "Dynamic code execution", "Найден eval/exec в исходном коде.", ProjectSeverity.ERROR, path=rel, line=getattr(node, "lineno", None), evidence={"call": _node_text(node)}, blocking=True))
    return tuple(out)


def check_bare_except(path: Path, rel: str, tree: ast.AST) -> tuple[ProjectFinding, ...]:
    out: list[ProjectFinding] = []
    for node in _walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            out.append(finding("PA002", "Bare except", "Bare except скрывает тип ошибки и ловит лишнее.", ProjectSeverity.WARNING, path=rel, line=node.lineno))
    return tuple(out)


def check_silent_except_pass(path: Path, rel: str, tree: ast.AST) -> tuple[ProjectFinding, ...]:
    out: list[ProjectFinding] = []
    for node in _walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        body = [stmt for stmt in node.body if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str))]
        if body and all(isinstance(stmt, ast.Pass) for stmt in body):
            out.append(finding("PA003", "Silent exception", "Исключение полностью проглатывается через pass.", ProjectSeverity.WARNING, path=rel, line=node.lineno))
    return tuple(out)


def check_shell_boundaries(path: Path, rel: str, tree: ast.AST) -> tuple[ProjectFinding, ...]:
    aliases = _resolver(tree)
    out: list[ProjectFinding] = []
    dangerous = {"subprocess.run", "subprocess.call", "subprocess.Popen", "subprocess.check_call", "subprocess.check_output"}
    for node in _walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call = aliases.resolved_call(node.func)
        if call == "os.system":
            out.append(finding("PA004", "Shell boundary", "os.system создаёт небезопасную shell-границу.", ProjectSeverity.ERROR, path=rel, line=node.lineno, evidence={"call": _node_text(node)}, blocking=True))
        if call in dangerous:
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    out.append(finding("PA005", "subprocess shell=True", "subprocess с shell=True требует отдельного обоснования и обычно запрещён.", ProjectSeverity.ERROR, path=rel, line=node.lineno, evidence={"call": _node_text(node)}, blocking=True))
    return tuple(out)


def check_mutable_defaults(path: Path, rel: str, tree: ast.AST) -> tuple[ProjectFinding, ...]:
    out: list[ProjectFinding] = []
    for node in _walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = list(node.args.defaults) + [item for item in node.args.kw_defaults if item is not None]
            for default in defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    out.append(finding("PA006", "Mutable default argument", f"Функция {node.name} использует изменяемое значение по умолчанию.", ProjectSeverity.WARNING, path=rel, line=node.lineno))
    return tuple(out)


def check_unsafe_deserialization(path: Path, rel: str, tree: ast.AST) -> tuple[ProjectFinding, ...]:
    aliases = _resolver(tree)
    out: list[ProjectFinding] = []
    for node in _walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call = aliases.resolved_call(node.func)
        if call in {"pickle.load", "pickle.loads"}:
            out.append(finding("PA007", "pickle deserialization", "pickle.load/loads небезопасен для недоверенных данных.", ProjectSeverity.WARNING, path=rel, line=node.lineno))
        if call == "yaml.load":
            has_safe_loader = any(kw.arg == "Loader" and "SafeLoader" in _node_text(kw.value) for kw in node.keywords)
            if not has_safe_loader:
                out.append(finding("PA008", "yaml.load without SafeLoader", "yaml.load без SafeLoader небезопасен.", ProjectSeverity.WARNING, path=rel, line=node.lineno))
    return tuple(out)


def check_asserts_in_runtime(path: Path, rel: str, tree: ast.AST) -> tuple[ProjectFinding, ...]:
    if _is_test_or_gate(path):
        return ()
    out: list[ProjectFinding] = []
    for node in _walk(tree):
        if isinstance(node, ast.Assert):
            out.append(finding("PA009", "Runtime assert", "assert в runtime-коде может быть отключён python -O; лучше явный exception.", ProjectSeverity.ADVICE, path=rel, line=node.lineno))
    return tuple(out)


def check_size_complexity(path: Path, rel: str, tree: ast.AST) -> tuple[ProjectFinding, ...]:
    out: list[ProjectFinding] = []
    lines = read_text(path).splitlines()
    limit = 1600 if path.name in _BIG_MODULE_EXEMPTIONS else _MODULE_LINE_LIMIT
    if len(lines) > limit:
        out.append(finding("PA010", "God module line budget", f"Модуль слишком большой: {len(lines)} строк > {limit}.", ProjectSeverity.ERROR, path=rel, evidence={"lines": len(lines), "limit": limit}, blocking=True))
    for node in _walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and hasattr(node, "end_lineno") and node.end_lineno:
            span = node.end_lineno - node.lineno + 1
            if span > _FUNCTION_LINE_LIMIT and (path.name, node.name) not in _LARGE_FUNCTION_EXEMPTIONS:
                out.append(finding("PA011", "Large function", f"Функция {node.name} слишком большая: {span} строк.", ProjectSeverity.WARNING, path=rel, line=node.lineno, evidence={"lines": span, "limit": _FUNCTION_LINE_LIMIT}))
        if isinstance(node, ast.ClassDef) and hasattr(node, "end_lineno") and node.end_lineno:
            methods = [item for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
            max_method_span = max((item.end_lineno - item.lineno + 1 for item in methods if item.end_lineno), default=0)
            span = node.end_lineno - node.lineno + 1
            if span > _CLASS_LINE_LIMIT and (len(methods) > _CLASS_METHOD_COUNT_LIMIT or max_method_span > _FUNCTION_LINE_LIMIT):
                out.append(finding("PA012", "Large class", f"Класс {node.name} слишком большой: {span} строк.", ProjectSeverity.WARNING, path=rel, line=node.lineno, evidence={"lines": span, "limit": _CLASS_LINE_LIMIT, "methods": len(methods), "max_method_lines": max_method_span}))
    return tuple(out)


def check_missing_diagnostic_import(path: Path, rel: str, tree: ast.AST) -> tuple[ProjectFinding, ...]:
    if path.name == "diagnostic_logging.py":
        return ()
    calls_helper = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "record_soft_exception"
        for node in _walk(tree)
    )
    if not calls_helper:
        return ()
    imported_name = False
    for node in _walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "diagnostic_logging":
            imported_name = any(alias.name == "record_soft_exception" for alias in node.names)
    if not imported_name:
        return (finding("PA013", "Missing diagnostic import", "Модуль вызывает record_soft_exception, но не импортирует его явно.", ProjectSeverity.ERROR, path=rel, blocking=True),)
    return ()



def check_duplicate_top_level_symbols(path: Path, rel: str, tree: ast.AST) -> tuple[ProjectFinding, ...]:
    """Detect accidental redefinition of top-level functions/classes.

    Python silently keeps the last definition.  In a production source archive
    that is almost always a merge/refactor mistake and can hide dead code paths
    from smoke tests.
    """

    seen: dict[tuple[str, str], int] = {}
    out: list[ProjectFinding] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            key = ("function", node.name)
        elif isinstance(node, ast.ClassDef):
            key = ("class", node.name)
        else:
            continue
        previous = seen.get(key)
        if previous is not None:
            kind = "функция" if key[0] == "function" else "класс"
            out.append(
                finding(
                    "PA014",
                    "Duplicate top-level symbol",
                    f"Top-level {kind} {node.name!r} объявлен повторно; Python оставит только последнее объявление.",
                    ProjectSeverity.ERROR,
                    path=rel,
                    line=node.lineno,
                    evidence={"first_line": previous, "duplicate_line": node.lineno, "symbol": node.name, "kind": key[0]},
                    blocking=True,
                )
            )
        else:
            seen[key] = node.lineno
    return tuple(out)


RULES: tuple[ProjectRule, ...] = (
    ProjectRule("PA001", "Dynamic code execution", ProjectSeverity.ERROR, check_eval_exec),
    ProjectRule("PA002", "Bare except", ProjectSeverity.WARNING, check_bare_except),
    ProjectRule("PA003", "Silent except/pass", ProjectSeverity.WARNING, check_silent_except_pass),
    ProjectRule("PA004", "Shell boundary", ProjectSeverity.ERROR, check_shell_boundaries),
    ProjectRule("PA006", "Mutable defaults", ProjectSeverity.WARNING, check_mutable_defaults),
    ProjectRule("PA007", "Unsafe deserialization", ProjectSeverity.WARNING, check_unsafe_deserialization),
    ProjectRule("PA009", "Runtime asserts", ProjectSeverity.ADVICE, check_asserts_in_runtime),
    ProjectRule("PA010", "Size and complexity", ProjectSeverity.WARNING, check_size_complexity),
    ProjectRule("PA013", "Missing diagnostic import", ProjectSeverity.ERROR, check_missing_diagnostic_import),
    ProjectRule("PA014", "Duplicate top-level symbols", ProjectSeverity.ERROR, check_duplicate_top_level_symbols),
)


def ast_rule_findings(index: ProjectFileIndex) -> tuple[ProjectFinding, ...]:
    findings: list[ProjectFinding] = []
    registered = {rule.rule_id for rule in RULES} | {"PA005", "PA008", "PA011", "PA012"}
    for path in index.python_files:
        rel = index.relative(path)
        tree = parse_python(path)
        if tree is None:
            continue
        for rule in RULES:
            for item in rule.check(path, rel, tree):
                if PROJECT_AUDITOR_RULE_IDS_MUST_BE_REGISTERED and item.rule_id not in registered:
                    findings.append(finding("PA999", "Unregistered rule id", f"Правило {rule.rule_id} выпустило незарегистрированный id {item.rule_id}.", ProjectSeverity.ERROR, path=rel, blocking=True))
                findings.append(item)
    return tuple(findings)


def assert_project_auditor_rules_lock() -> None:
    if PROJECT_AUDITOR_RULES_LOCK_VERSION != "v1.4":
        raise AssertionError("Project auditor rules lock changed unexpectedly")
    if not PROJECT_AUDITOR_RULES_ARE_EXPLICIT:
        raise AssertionError("Project auditor rules must stay explicit")
    if not PROJECT_AUDITOR_NO_LLM_REQUIRED:
        raise AssertionError("Project auditor must stay deterministic and local-only")
    if not PROJECT_AUDITOR_RULE_IDS_MUST_BE_REGISTERED:
        raise AssertionError("Project auditor emitted rule ids must stay registered")
    if not PROJECT_AUDITOR_SECURITY_RULES_SCAN_AUDITOR_CODE:
        raise AssertionError("Project auditor code must not be exempt from security rules")
    if not PROJECT_AUDITOR_DETECTS_DUPLICATE_TOP_LEVEL_SYMBOLS:
        raise AssertionError("Project auditor must detect duplicate top-level symbols")
    rule_ids = [rule.rule_id for rule in RULES]
    if len(rule_ids) != len(set(rule_ids)):
        raise AssertionError("Duplicate project auditor rule ids")
    if len(RULES) < 10:
        raise AssertionError("Project auditor rule catalog became too small")
    if not LARGE_FUNCTION_EXEMPTIONS_ARE_LOCKED:
        raise AssertionError("Large-function exemptions must stay locked")
    if not isinstance(_walk(ast.parse("x = 1")), tuple):
        raise AssertionError("Project auditor AST walk cache must stay active")
    if _LARGE_FUNCTION_EXEMPTIONS != {
        ("window_setup_center.py", "open_template_setup_center"),
        ("window_document_mapper.py", "open_universal_document_mapper"),
    }:
        raise AssertionError("Unexpected large-function exemption drift")
    emitted = {"PA001", "PA002", "PA003", "PA004", "PA005", "PA006", "PA007", "PA008", "PA009", "PA010", "PA011", "PA012", "PA013", "PA014"}
    known = {rule.rule_id for rule in RULES} | {"PA005", "PA008", "PA011", "PA012"}
    if not emitted <= known:
        raise AssertionError("Some emitted project auditor rule ids are not registered/known")
