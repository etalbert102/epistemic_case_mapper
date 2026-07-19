from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_section_ownership import repeated_owned_evidence_issues


def test_section_ownership_allows_repeated_evidence_with_section_value() -> None:
    row = {
        "slot": "hard-outcome support",
        "claim": "The pilot reduced permit review time by 34 percent without increasing error rates.",
        "source": "Evaluation",
        "anchor_terms": ["pilot", "reduced", "permit", "review", "34", "error"],
        "reference_policy": {
            "owner_section": "Evidence Carrying the Conclusion",
            "reference_style": "do_not_repeat",
            "allowed": False,
        },
    }
    contract = {"owned_elsewhere_evidence": [row], "required_evidence": []}

    assert not repeated_owned_evidence_issues(
        "Why This Read",
        (
            "## Why This Read\n\n"
            "The pilot reduced permit review time by 34 percent without increasing error rates, "
            "which explains why the default read can be operationally bounded."
        ),
        contract,
    )
