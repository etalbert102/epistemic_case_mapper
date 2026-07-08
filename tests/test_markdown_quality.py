from __future__ import annotations

from epistemic_case_mapper.map_briefing_final_memo_diagnosis import build_memo_final_diagnosis, diagnosis_improved
from epistemic_case_mapper.map_briefing_markdown_quality import (
    extraction_debris_issues,
    markdown_structure_issues,
    repair_markdown_structure,
)
from epistemic_case_mapper.map_briefing_reader_polish import briefing_reader_polish_report


def test_repair_markdown_structure_splits_collapsed_headings_and_bullets() -> None:
    memo = "## Decision Brief **Decision question:** Q ## Sources - Study A - Study B"

    repaired = repair_markdown_structure(memo)

    assert "## Decision Brief\n\n**Decision question:** Q" in repaired
    assert "\n\n## Sources" in repaired
    assert "\n- Study A" in repaired
    assert "\n- Study B" in repaired
    assert markdown_structure_issues(repaired) == []


def test_markdown_structure_issues_detect_collapsed_output() -> None:
    original = "## Decision Brief\n\nA.\n\n## Evidence Trail\n\nB.\n\n## Sources\n\n- S"
    damaged = "## Decision Brief\n\n" + "word " * 500 + "## Sources - S"

    issues = markdown_structure_issues(damaged, original=original)

    assert "repair dropped most Markdown section headings" in issues
    assert "repair contains inline Markdown headings" in issues
    assert "repair contains collapsed overlong Markdown lines" in issues


def test_extraction_debris_issues_detect_reader_facing_source_fragments() -> None:
    memo = "eTable 14 reported a subgroup. Results were truncated... doi: 10.1000/example [PubMed]"

    issues = extraction_debris_issues(memo)

    assert "memo contains table or figure caption fragments" in issues
    assert "memo contains ellipsis-truncated extraction fragments" in issues
    assert "memo contains DOI reference debris" in issues
    assert "memo contains reference-list debris" in issues


def test_final_diagnosis_counts_structure_and_debris_issues() -> None:
    memo = "## Decision Brief\n\n" + "word " * 500 + "## Sources eTable 2. doi: 10.1000/example"

    diagnosis = build_memo_final_diagnosis(memo)

    assert diagnosis["metrics"]["markdown_structure_issue_count"] >= 1
    assert diagnosis["metrics"]["extraction_debris_issue_count"] >= 1
    assert any(issue["kind"] == "markdown_structure" for issue in diagnosis["prose"]["issues"])
    assert any(issue["kind"] == "extraction_debris" for issue in diagnosis["prose"]["issues"])


def test_diagnosis_improved_rewards_structure_and_debris_cleanup() -> None:
    before = build_memo_final_diagnosis(
        "## Decision Brief\n\n" + "word " * 500 + "## Sources eTable 2. doi: 10.1000/example"
    )
    after = build_memo_final_diagnosis("## Decision Brief\n\nA clear answer.\n\n## Sources\n\n- Study A")

    assert diagnosis_improved(before, after, pass_name="prose")


def test_reader_polish_report_surfaces_structure_and_debris_warnings() -> None:
    rendered = "## Decision Brief\n\n" + "word " * 500 + "## Sources eTable 2. doi: 10.1000/example"

    report = briefing_reader_polish_report(rendered, {})
    issue_types = {issue["issue_type"] for issue in report["issues"]}

    assert "markdown_structure" in issue_types
    assert "extraction_debris" in issue_types


def test_reader_polish_report_does_not_treat_source_urls_as_fragments() -> None:
    rendered = """## Decision Brief

A clear answer.

## Sources

- [Study A](https://pmc.ncbi.nlm.nih.gov/articles/PMC7400894/)
"""

    report = briefing_reader_polish_report(rendered, {})
    issue_types = {issue["issue_type"] for issue in report["issues"]}

    assert "truncated_fragment" not in issue_types


def test_final_diagnosis_ignores_confidence_metadata_as_dense_paragraph() -> None:
    memo = "## Decision Brief\n\nA clear answer.\n\n**Confidence:** " + ("medium " * 80)

    diagnosis = build_memo_final_diagnosis(memo)

    assert diagnosis["metrics"]["dense_paragraph_count"] == 0
