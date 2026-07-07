from __future__ import annotations

from epistemic_case_mapper.map_briefing_section_role_quality import (
    section_role_quality_issues,
    section_role_quality_report,
)
from epistemic_case_mapper.map_briefing_section_structure import section_structure_issues


def test_practical_read_flags_unsupported_advice_drift() -> None:
    markdown = """## Practical Read

The evidence suggests a nuanced practical application. Monitor the rollout closely and optimize implementation across teams.
"""

    issues = section_role_quality_issues(markdown, {"heading": "Practical Read"})

    assert any("vague analyst phrase" in issue for issue in issues)
    assert "Practical Read drifts into unsupported implementation advice" in issues


def test_evidence_section_flags_generic_opening_and_missing_weighting() -> None:
    markdown = """## Evidence Carrying the Conclusion

The evidence mix matters because direct outcomes, intervention evidence, mechanisms, and proxies answer different parts of the decision.
"""
    contract = {
        "heading": "Evidence Carrying the Conclusion",
        "model_section_packet": {"owned_evidence": [{"claim": "The option improved the primary outcome."}]},
    }

    issues = section_role_quality_issues(markdown, contract)

    assert "Evidence Carrying opens with generic evidence-mix language" in issues


def test_evidence_section_flags_missing_weighting_when_owned_evidence_exists() -> None:
    markdown = """## Evidence Carrying the Conclusion

The available material describes several parts of the case and should be considered together.
"""
    contract = {
        "heading": "Evidence Carrying the Conclusion",
        "model_section_packet": {"owned_evidence": [{"claim": "The option improved the primary outcome."}]},
    }

    issues = section_role_quality_issues(markdown, contract)

    assert "Evidence Carrying section does not distinguish support, counterweight, or evidence limits" in issues


def test_section_structure_includes_role_quality_gate() -> None:
    markdown = """## Why This Read

Explain why the support, tensions, and scope limits produce this read.
"""

    issues = section_structure_issues(markdown, {"heading": "Why This Read", "has_obligations": True})

    assert "Why This Read contains scaffold instructions instead of reasoning" in issues


def test_section_role_quality_report_is_section_specific() -> None:
    memo = """## Decision Brief

Use the option as a bounded default.

## Practical Read

It is important to note that teams should monitor and optimize implementation.
"""

    report = section_role_quality_report(memo)

    assert report["status"] == "warning"
    assert any(issue["section"] == "Practical Read" for issue in report["issues"])
