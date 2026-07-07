from __future__ import annotations

from pathlib import Path

from epistemic_case_mapper.deterministic_semantic_audit import (
    render_semantic_audit_markdown,
    scan_deterministic_semantic_decisions,
)


def test_semantic_audit_flags_count_based_missing_assertions(tmp_path: Path) -> None:
    module = tmp_path / "semantic_gate.py"
    module.write_text(
        "\n".join(
            [
                "def check(role_counts):",
                "    if role_counts.get('challenges', 0) == 0:",
                "        missing_source_categories.append('counterweight_evidence')",
            ]
        )
    )

    findings = scan_deterministic_semantic_decisions([module])
    markdown = render_semantic_audit_markdown(findings, repo_root=tmp_path)

    assert any(finding.category == "hard_missing_from_count" for finding in findings)
    assert "semantic_gate.py" in markdown
    assert "Findings" in markdown


def test_semantic_audit_skips_schema_and_reporting_references(tmp_path: Path) -> None:
    module = tmp_path / "schema_refs.py"
    module.write_text(
        "\n".join(
            [
                "from other import profile_vocabulary",
                "class Report:",
                "    missing_source_categories: list[str] = Field(default_factory=list)",
                "payload = {",
                "    'missing_expected_decision_slots': missing_expected_slots,",
                "    'decision_concepts': concepts,",
                "}",
            ]
        )
    )

    findings = scan_deterministic_semantic_decisions([module])

    assert findings == []
