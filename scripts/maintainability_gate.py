from __future__ import annotations

import argparse
import ast
import importlib
import json
import pkgutil
import re
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GateFinding:
    issue: str
    path: str
    line: int
    detail: str


@dataclass(frozen=True)
class GateCheck:
    name: str
    ok: bool
    details: list[str]
    findings: list[GateFinding] | None = None


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_policy(root: Path) -> dict[str, Any]:
    path = root / "maintainability_policy.toml"
    if not path.exists():
        raise FileNotFoundError(f"missing maintainability policy: {path}")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def compile_check(root: Path, policy: dict[str, Any]) -> GateCheck:
    paths = [
        *policy["validation"].get("source_roots", []),
        *policy["validation"].get("test_roots", []),
        *policy["validation"].get("script_roots", []),
    ]
    return _run_command("compile", [sys.executable, "-m", "compileall", "-q", *paths], root=root)


def pytest_check(root: Path) -> GateCheck:
    return _run_command("pytest", [sys.executable, "-m", "pytest", "-q"], root=root)


def import_sweep_check(root: Path, policy: dict[str, Any]) -> GateCheck:
    src_path = root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    package_name = str(policy["validation"]["python_package"])
    try:
        package = importlib.import_module(package_name)
    except Exception as exc:
        return GateCheck("import_sweep", False, [f"failed to import {package_name}: {exc}"])

    failures: list[str] = []
    for module in pkgutil.walk_packages(package.__path__, prefix=f"{package_name}."):
        try:
            importlib.import_module(module.name)
        except Exception as exc:
            failures.append(f"{module.name}: {exc}")
    return GateCheck(
        "import_sweep",
        not failures,
        failures or [f"imported {package_name} modules successfully"],
    )


def static_maintainability_check(root: Path, policy: dict[str, Any]) -> GateCheck:
    thresholds = policy["thresholds"]
    allowlist = policy.get("allowlist", {})
    long_file_allowlist = set(allowlist.get("long_files", []))
    long_function_allowlist = set(allowlist.get("long_functions", []))
    branchy_function_allowlist = set(allowlist.get("branchy_functions", []))
    findings: list[GateFinding] = []
    visible_debt: list[str] = []
    for path in _python_files(root, policy):
        relative = _rel(root, path)
        text = path.read_text(encoding="utf-8")
        line_count = len(text.splitlines())
        file_limit = _file_line_limit(relative, thresholds)
        if line_count > file_limit:
            detail = f"file has {line_count} lines; limit is {file_limit}"
            if relative in long_file_allowlist:
                visible_debt.append(f"allowlisted {relative}: {detail}")
            else:
                findings.append(GateFinding("long_file", relative, 1, detail))
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            findings.append(GateFinding("syntax_error", relative, int(exc.lineno or 1), str(exc)))
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            symbol = f"{relative}::{node.name}"
            line_count = int(node.end_lineno or node.lineno) - int(node.lineno) + 1
            branch_count = _branch_node_count(node)
            if line_count > int(thresholds["max_function_lines"]):
                detail = f"function has {line_count} lines; limit is {thresholds['max_function_lines']}"
                if symbol in long_function_allowlist:
                    visible_debt.append(f"allowlisted {symbol}: {detail}")
                else:
                    findings.append(GateFinding("long_function", relative, int(node.lineno), f"{symbol}: {detail}"))
            if branch_count > int(thresholds["max_branch_nodes"]):
                detail = f"function has {branch_count} branch nodes; limit is {thresholds['max_branch_nodes']}"
                if symbol in branchy_function_allowlist:
                    visible_debt.append(f"allowlisted {symbol}: {detail}")
                else:
                    findings.append(GateFinding("branchy_function", relative, int(node.lineno), f"{symbol}: {detail}"))
    details = [finding.detail for finding in findings[:20]] or [f"inspected Python files", *visible_debt[:20]]
    return GateCheck("static_maintainability", not findings, details, findings)


def domain_vocabulary_isolation_check(root: Path, policy: dict[str, Any]) -> GateCheck:
    config = dict(policy.get("domain_vocabulary", {}))
    terms = [str(term).lower() for term in config.get("terms", []) if str(term).strip()]
    allowed_paths = set(str(path) for path in config.get("allowed_paths", []))
    allowed_literals = set(str(item) for item in config.get("allowed_literals", []))
    findings: list[GateFinding] = []
    for path in _domain_scan_files(root, policy):
        relative = _rel(root, path)
        if relative in allowed_paths:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            findings.append(GateFinding("syntax_error", relative, int(exc.lineno or 1), str(exc)))
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            literal = node.value
            if _domain_literal_allowed(literal, allowed_literals):
                continue
            matched = _matched_domain_terms(literal, terms)
            if not matched:
                continue
            findings.append(
                GateFinding(
                    issue="domain_vocabulary_in_generic_code",
                    path=relative,
                    line=int(getattr(node, "lineno", 1)),
                    detail=(
                        f"{relative}:{getattr(node, 'lineno', 1)} contains domain term(s) "
                        f"{', '.join(matched)} outside configured vocabulary paths"
                    ),
                )
            )
    details = [finding.detail for finding in findings[:30]] or [
        "domain vocabulary is isolated to configured profile/test/documentation locations"
    ]
    return GateCheck("domain_vocabulary_isolation", not findings, details, findings)


def design_debt_check(root: Path, policy: dict[str, Any]) -> GateCheck:
    findings: list[GateFinding] = []
    for path in _source_python_files(root, policy):
        relative = _rel(root, path)
        if re.search(r"_impl_\d+\.py$", path.name):
            findings.append(
                GateFinding(
                    "numbered_implementation_shard",
                    relative,
                    1,
                    f"{relative} uses a numbered shard name instead of a domain-owned module name",
                )
            )
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            findings.append(GateFinding("syntax_error", relative, int(exc.lineno or 1), str(exc)))
            continue
        findings.extend(_script_boundary_findings(relative, tree))
        findings.extend(_dynamic_namespace_findings(relative, tree))
    details = [finding.detail for finding in findings[:30]] or [
        "package modules use named files, explicit imports, and no script-boundary imports"
    ]
    return GateCheck("design_debt", not findings, details, findings)


def _domain_literal_allowed(literal: str, allowed_literals: set[str]) -> bool:
    if literal in allowed_literals:
        return True
    return "_" in literal and bool(re.fullmatch(r"[A-Za-z0-9_]+", literal))


def _matched_domain_terms(literal: str, terms: list[str]) -> list[str]:
    lowered = literal.lower()
    matched: list[str] = []
    for term in terms:
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lowered):
            matched.append(term)
    return matched


def _domain_scan_files(root: Path, policy: dict[str, Any]) -> list[Path]:
    config = dict(policy.get("domain_vocabulary", {}))
    roots = config.get("protected_roots") or policy["validation"].get("source_roots", [])
    files: list[Path] = []
    for path_root in roots:
        full_root = root / str(path_root)
        if full_root.is_file() and full_root.suffix == ".py":
            files.append(full_root)
        elif full_root.is_dir():
            files.extend(full_root.rglob("*.py"))
    return _filter_python_files(files)


def _source_python_files(root: Path, policy: dict[str, Any]) -> list[Path]:
    files: list[Path] = []
    for path_root in policy["validation"].get("source_roots", []):
        full_root = root / str(path_root)
        if full_root.is_file() and full_root.suffix == ".py":
            files.append(full_root)
        elif full_root.is_dir():
            files.extend(full_root.rglob("*.py"))
    return _filter_python_files(files)


def _script_boundary_findings(relative: str, tree: ast.AST) -> list[GateFinding]:
    findings: list[GateFinding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "scripts" or module.startswith("scripts.") or module.startswith("run_"):
                findings.append(
                    GateFinding(
                        "package_imports_script",
                        relative,
                        int(node.lineno),
                        f"{relative}:{node.lineno} imports executable script module {module!r}",
                    )
                )
        if isinstance(node, ast.Call) and _is_sys_path_insert_call(node):
            findings.append(
                GateFinding(
                    "package_mutates_sys_path",
                    relative,
                    int(getattr(node, "lineno", 1)),
                    f"{relative}:{getattr(node, 'lineno', 1)} mutates sys.path inside package code",
                )
            )
    return findings


def _is_sys_path_insert_call(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in {"insert", "append"}
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "path"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "sys"
    )


def _dynamic_namespace_findings(relative: str, tree: ast.AST) -> list[GateFinding]:
    findings: list[GateFinding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "importlib":
            imported = {alias.name for alias in node.names}
            if "import_module" in imported:
                findings.append(
                    GateFinding(
                        "dynamic_module_facade",
                        relative,
                        int(node.lineno),
                        f"{relative}:{node.lineno} imports import_module; use explicit package imports instead",
                    )
                )
        if isinstance(node, ast.Call) and _is_namespace_update_call(node):
            findings.append(
                GateFinding(
                    "dynamic_namespace_update",
                    relative,
                    int(getattr(node, "lineno", 1)),
                    f"{relative}:{getattr(node, 'lineno', 1)} updates globals/module namespaces dynamically",
                )
            )
    return findings


def _is_namespace_update_call(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "update":
        return False
    if isinstance(func.value, ast.Call) and isinstance(func.value.func, ast.Name) and func.value.func.id == "globals":
        return True
    return (
        isinstance(func.value, ast.Attribute)
        and func.value.attr == "__dict__"
    )


def _python_files(root: Path, policy: dict[str, Any]) -> list[Path]:
    files: list[Path] = []
    roots = [
        *policy["validation"].get("source_roots", []),
        *policy["validation"].get("test_roots", []),
        *policy["validation"].get("script_roots", []),
    ]
    for path_root in roots:
        full_root = root / str(path_root)
        if full_root.is_file() and full_root.suffix == ".py":
            files.append(full_root)
        elif full_root.is_dir():
            files.extend(full_root.rglob("*.py"))
    return _filter_python_files(files)


def _filter_python_files(files: list[Path]) -> list[Path]:
    ignored_parts = {".venv", "__pycache__", ".pytest_cache", ".mypy_cache"}
    return sorted(path for path in files if not any(part in ignored_parts for part in path.parts))


def _file_line_limit(relative: str, thresholds: dict[str, Any]) -> int:
    if relative.startswith("tests/"):
        return int(thresholds["max_test_file_lines"])
    if relative.startswith("scripts/"):
        return int(thresholds["max_script_file_lines"])
    return int(thresholds["max_source_file_lines"])


def _branch_node_count(node: ast.AST) -> int:
    branch_types = (
        ast.BoolOp,
        ast.ExceptHandler,
        ast.For,
        ast.AsyncFor,
        ast.If,
        ast.IfExp,
        ast.Match,
        ast.Try,
        ast.While,
    )
    return sum(isinstance(child, branch_types) for child in ast.walk(node))


def _run_command(name: str, command: list[str], *, root: Path) -> GateCheck:
    completed = subprocess.run(
        command,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    details = [line for line in completed.stdout.splitlines() if line.strip()]
    if completed.returncode != 0:
        details.insert(0, f"command failed with exit code {completed.returncode}: {' '.join(command)}")
    return GateCheck(name, completed.returncode == 0, details[-40:])


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _print_report(checks: list[GateCheck]) -> None:
    for check in checks:
        status = "OK" if check.ok else "FAIL"
        print(f"[{status}] {check.name}")
        for detail in check.details[:20]:
            print(f"  - {detail}")


def _write_json_report(root: Path, checks: list[GateCheck], output_path: str | None) -> None:
    if not output_path:
        return
    path = root / output_path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "passed": all(check.ok for check in checks),
        "checks": [asdict(check) for check in checks],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the epistemic-case-mapper maintainability gate.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip pytest; useful inside larger validation pipelines.")
    parser.add_argument("--json-output", help="Write a JSON gate report to this repo-relative path.")
    args = parser.parse_args(argv)

    root = repo_root()
    policy = load_policy(root)
    checks = [
        compile_check(root, policy),
        import_sweep_check(root, policy),
        static_maintainability_check(root, policy),
        domain_vocabulary_isolation_check(root, policy),
        design_debt_check(root, policy),
    ]
    if not args.skip_tests:
        checks.append(pytest_check(root))

    _print_report(checks)
    _write_json_report(root, checks, args.json_output)
    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
