from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_length_policy import executive_length_policy
from epistemic_case_mapper.pipeline.briefing.map_briefing_reader_polish import briefing_reader_polish_report


def test_complex_cases_get_larger_executive_word_budget() -> None:
    executive = _executive(words_per_section=260)
    scaffold = _complex_scaffold()

    policy = executive_length_policy(executive, scaffold)

    assert policy["executive_word_count"] > 1500
    assert policy["executive_word_budget"] > 2000
    assert not any(issue["issue_type"] == "executive_brief_too_long_for_complexity" for issue in policy["issues"])


def test_opening_decision_brief_still_has_front_door_budget() -> None:
    executive = _executive(decision_words=260, words_per_section=40)
    policy = executive_length_policy(executive, _complex_scaffold())

    assert any(issue["issue_type"] == "opening_decision_brief_too_long" for issue in policy["issues"])


def test_reader_polish_report_uses_complexity_adjusted_length_warning() -> None:
    rendered = _executive(words_per_section=260) + "\n\n## Evidence Appendix\n\n## Evidence Roles\n\nDetails.\n\n## Evidence by Decision Lever\n\nDetails."
    report = briefing_reader_polish_report(rendered, _complex_scaffold())
    issue_types = {issue["issue_type"] for issue in report["issues"]}

    assert report["executive_word_count"] > 1500
    assert report["executive_word_budget"] > 2000
    assert "executive_brief_too_long" not in issue_types
    assert "executive_brief_too_long_for_complexity" not in issue_types


def _executive(*, words_per_section: int, decision_words: int = 90) -> str:
    return "\n\n".join(
        [
            "## Decision Brief\n\n" + _words(decision_words),
            "## Practical Read\n\n" + _words(words_per_section),
            "## Why This Read\n\n" + _words(words_per_section),
            "## Evidence Carrying the Conclusion\n\n" + _words(words_per_section),
            "## Practical Scope and Exceptions\n\n" + _words(words_per_section),
            "## Decision Cruxes\n\n" + _words(words_per_section),
            "## Limits of the Current Map\n\n" + _words(words_per_section),
        ]
    )


def _words(count: int) -> str:
    return " ".join(f"word{i}" for i in range(count)) + "."


def _complex_scaffold() -> dict:
    return {
        "source_display_names": {f"s{i}": f"Source {i}" for i in range(12)},
        "decision_synthesis_model": {"cruxes": [{"crux": f"Crux {i}"} for i in range(5)]},
        "coverage_balance_report": {
            "evidence_family_counts": {
                "cohort": 3,
                "rct": 2,
                "guideline": 2,
                "mechanism": 1,
                "subgroup": 1,
                "comparator": 1,
            }
        },
        "canonical_decision_spine": {
            "strongest_counterevidence": [{"field_id": f"c{i}"} for i in range(4)],
            "missing_decision_slots": [{"field_id": "missing_comparator"}],
        },
    }
