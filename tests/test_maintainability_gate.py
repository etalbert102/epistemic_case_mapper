from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.maintainability_gate import (  # noqa: E402
    _branch_node_count,
    design_debt_check,
    domain_vocabulary_isolation_check,
    load_policy,
    static_maintainability_check,
)


def test_maintainability_policy_loads_domain_vocabulary_guard() -> None:
    policy = load_policy(ROOT)

    assert "src/epistemic_case_mapper/config_profiles.py" in policy["domain_vocabulary"]["allowed_paths"]
    assert "hepa" in policy["domain_vocabulary"]["terms"]


def test_static_maintainability_gate_passes_current_policy() -> None:
    policy = load_policy(ROOT)
    result = static_maintainability_check(ROOT, policy)

    assert result.ok is True


def test_domain_vocabulary_isolation_gate_passes_current_policy() -> None:
    policy = load_policy(ROOT)
    result = domain_vocabulary_isolation_check(ROOT, policy)

    assert result.ok is True


def test_design_debt_gate_passes_current_policy() -> None:
    policy = load_policy(ROOT)
    result = design_debt_check(ROOT, policy)

    assert result.ok is True


def test_design_debt_gate_flags_dynamic_shard_facade(tmp_path: Path) -> None:
    module = tmp_path / "src" / "epistemic_case_mapper" / "example_impl_1.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "from importlib import import_module\n"
        "_SHARDS = [import_module('x')]\n"
        "globals().update({'x': 1})\n",
        encoding="utf-8",
    )
    policy = {
        "validation": {"source_roots": ["src/epistemic_case_mapper"], "test_roots": [], "script_roots": []},
    }

    result = design_debt_check(tmp_path, policy)

    assert result.ok is False
    assert {finding.issue for finding in result.findings or []} >= {
        "numbered_implementation_shard",
        "dynamic_module_facade",
        "dynamic_namespace_update",
    }


def test_domain_vocabulary_isolation_flags_generic_domain_literal(tmp_path: Path) -> None:
    module = tmp_path / "src" / "epistemic_case_mapper" / "generic.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "def leaked(text):\n"
        "    return 'hepa' in text.lower()\n",
        encoding="utf-8",
    )
    policy = {
        "validation": {"source_roots": ["src/epistemic_case_mapper"], "test_roots": [], "script_roots": []},
        "domain_vocabulary": {
            "protected_roots": ["src/epistemic_case_mapper"],
            "allowed_paths": ["src/epistemic_case_mapper/config_profiles.py"],
            "terms": ["hepa"],
            "allowed_literals": [],
        },
    }

    result = domain_vocabulary_isolation_check(tmp_path, policy)

    assert result.ok is False
    assert result.findings
    assert result.findings[0].issue == "domain_vocabulary_in_generic_code"


def test_branch_node_counter_counts_control_flow() -> None:
    tree = ast.parse(
        """
def sample(value):
    if value:
        for item in value:
            if item and value:
                return item
    return None
"""
    )
    function = tree.body[0]

    assert _branch_node_count(function) == 4
