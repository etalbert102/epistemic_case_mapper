from __future__ import annotations

from epistemic_case_mapper.map_briefing_validation import validate_briefing_against_scaffold
from epistemic_case_mapper.map_briefing_section_rewrite import _section_rewrite_issues
from epistemic_case_mapper.map_briefing_section_prompt_contract import model_facing_section_markdown


def test_section_validation_uses_curated_owned_cards_before_legacy_required_evidence() -> None:
    contract = {
        "requires_confidence": False,
        "required_evidence": [
            {
                "slot": "Comparator or substitution",
                "claim": "Comparator evidence for whole-food exposure versus replacement option: whole or.",
                "source": "structured option comparison",
                "anchor_terms": ["comparator", "replacement"],
            }
        ],
        "required_gaps": [],
        "required_cruxes": [],
        "required_main_memo_obligations": [],
        "has_obligations": True,
        "model_section_packet": {
            "owned_evidence": [
                {
                    "claim": "Data above the ordinary exposure level remain sparse.",
                    "source": "Source",
                    "intended_role": "scope",
                    "quantity_values": [],
                }
            ]
        },
    }
    section = {
        "title": "Practical Scope and Exceptions",
        "markdown": "## Practical Scope and Exceptions\n\nData above the ordinary exposure level remain sparse.",
    }

    issues = _section_rewrite_issues(section["markdown"], section, contract)

    assert not any("Comparator evidence" in issue for issue in issues)


def test_section_validation_tolerates_single_cross_section_reuse() -> None:
    contract = {
        "requires_confidence": False,
        "required_evidence": [],
        "required_gaps": [],
        "required_cruxes": [],
        "required_main_memo_obligations": [],
        "has_obligations": False,
        "owned_elsewhere_evidence": [
            {
                "claim": "Daily option use was not associated with worse outcomes when context changed.",
                "source": "Outcome Study",
                "anchor_terms": ["daily", "option", "associated", "worse", "outcomes"],
                "reference_policy": {
                    "owner_section": "Practical Scope and Exceptions",
                    "reference_style": "do_not_repeat",
                },
            }
        ],
    }
    section = {
        "title": "Why This Read",
        "markdown": "## Why This Read\n\nDaily option use was not associated with worse outcomes when context changed.",
    }

    assert _section_rewrite_issues(section["markdown"], section, contract) == []


def test_section_validation_rejects_unsupported_quantity_drift() -> None:
    contract = {
        "requires_confidence": False,
        "required_evidence": [
            {
                "slot": "Outcome evidence",
                "claim": "The pilot reduced processing delays by 12%.",
                "source": "Pilot Study",
                "anchor_terms": ["pilot", "processing", "delays"],
            }
        ],
        "required_gaps": [],
        "required_cruxes": [],
        "required_main_memo_obligations": [],
        "has_obligations": True,
        "model_section_packet": {},
    }
    original = {
        "title": "Evidence Carrying the Conclusion",
        "markdown": "## Evidence Carrying the Conclusion\n\nThe pilot reduced processing delays by 12% (Pilot Study).",
    }
    rewritten = "## Evidence Carrying the Conclusion\n\nThe pilot reduced processing delays by 47% (Pilot Study)."

    issues = _section_rewrite_issues(rewritten, original, contract)

    assert any("unsupported quantity `47%`" in issue for issue in issues)


def test_section_validation_rejects_unsupported_source_label_drift() -> None:
    contract = {
        "requires_confidence": False,
        "required_evidence": [
            {
                "slot": "Outcome evidence",
                "claim": "The pilot reduced processing delays by 12%.",
                "source": "Pilot Study",
                "anchor_terms": ["pilot", "processing", "delays"],
            }
        ],
        "required_gaps": [],
        "required_cruxes": [],
        "required_main_memo_obligations": [],
        "has_obligations": True,
        "model_section_packet": {},
    }
    original = {
        "title": "Evidence Carrying the Conclusion",
        "markdown": "## Evidence Carrying the Conclusion\n\nThe pilot reduced processing delays by 12% (Pilot Study).",
    }
    rewritten = (
        "## Evidence Carrying the Conclusion\n\n"
        "The pilot reduced processing delays by 12% (Pilot Study), and the PROSPERITY Trial confirms the same pattern."
    )

    issues = _section_rewrite_issues(rewritten, original, contract)

    assert any("unsupported source label `PROSPERITY Trial`" in issue for issue in issues)


def test_section_validation_rejects_unsupported_citation_like_label() -> None:
    contract = {
        "requires_confidence": False,
        "required_evidence": [
            {
                "slot": "Outcome evidence",
                "claim": "The cohort found no increase in events.",
                "source": "Cardiovascular Outcomes Review",
                "anchor_terms": ["cohort", "events"],
            }
        ],
        "required_gaps": [],
        "required_cruxes": [],
        "required_main_memo_obligations": [],
        "has_obligations": True,
        "model_section_packet": {},
    }
    original = {
        "title": "Evidence Carrying the Conclusion",
        "markdown": "## Evidence Carrying the Conclusion\n\nThe cohort found no increase in events (Cardiovascular Outcomes Review).",
    }
    rewritten = "## Evidence Carrying the Conclusion\n\nThe cohort found no increase in events (Missing A 2023)."

    issues = _section_rewrite_issues(rewritten, original, contract)

    assert any("unsupported source label `Missing A 2023`" in issue for issue in issues)


def test_section_validation_flags_contradictory_statistical_language() -> None:
    contract = {
        "requires_confidence": False,
        "required_evidence": [
            {
                "slot": "Biomarker evidence",
                "claim": "The biomarker comparison was not statistically significant.",
                "source": "Trial Review",
                "anchor_terms": ["biomarker", "comparison"],
            }
        ],
        "required_gaps": [],
        "required_cruxes": [],
        "required_main_memo_obligations": [],
        "has_obligations": True,
        "model_section_packet": {},
    }
    original = {
        "title": "Evidence Carrying the Conclusion",
        "markdown": "## Evidence Carrying the Conclusion\n\nThe biomarker comparison was not statistically significant (Trial Review).",
    }
    rewritten = "## Evidence Carrying the Conclusion\n\nThe biomarker comparison was not statistically significant (p=0.00) (Trial Review)."

    issues = _section_rewrite_issues(rewritten, original, contract)

    assert any("contradictory statistical-significance language" in issue for issue in issues)


def test_whole_briefing_validation_reports_possible_evidence_drift() -> None:
    scaffold = {
        "source_display_names": {"pilot": "Pilot Study"},
        "evidence_weighting_ledger": {
            "all_evidence": [
                {
                    "claim_id": "c001",
                    "claim": "The pilot reduced processing delays by 12%.",
                    "source": "Pilot Study",
                    "section": "main_support",
                }
            ]
        },
    }
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The pilot reduced processing delays by 12%.",
                "source_id": "pilot",
            }
        ],
        "relations": [],
    }
    rendered = """## Decision Brief

The PROSPERITY Trial shows the pilot reduced delays by 47%.

## Why This Read

The unsupported trial result drives the answer.

## Evidence Roles

Main support: Pilot Study.
"""

    report = validate_briefing_against_scaffold(rendered, scaffold, candidate_map)

    assert any(issue["issue_type"] == "possible_evidence_drift" for issue in report["issues"])


def test_whole_briefing_validation_flags_not_synthesis_ready_context() -> None:
    report = validate_briefing_against_scaffold(
        "## Decision Brief\n\nUse the mapped answer.\n\n## Evidence Roles\n\n### Main Support\n\n- Evidence.",
        {"section_context_acceptance_status": "not_synthesis_ready"},
        {"claims": [], "relations": []},
    )

    assert report["status"] == "fails_contract"
    assert any(issue["issue_type"] == "section_context_not_synthesis_ready" for issue in report["issues"])


def test_whole_briefing_validation_flags_gap_boilerplate_outside_limits() -> None:
    report = validate_briefing_against_scaffold(
        "## Decision Brief\n\nUse it.\n\n## Why This Read\n\nThe current source packet does not establish a default population.\n\n## Evidence Roles\n\n### Main Support\n\n- Evidence.",
        {},
        {"claims": [], "relations": []},
    )

    assert any(issue["issue_type"] == "gap_boilerplate_in_main_analysis" for issue in report["issues"])


def test_whole_briefing_validation_flags_raw_source_card_ids() -> None:
    report = validate_briefing_against_scaffold(
        "## Decision Brief\n\nUse it.\n\n## Why This Read\n\nThe effect is anchored to sc0002.\n\n## Evidence Roles\n\n### Main Support\n\n- Evidence.",
        {},
        {"claims": [], "relations": []},
    )

    assert any(issue["issue_type"] == "reader_unfriendly_map_identifier" for issue in report["issues"])


def test_model_facing_non_limits_sections_remove_gap_boilerplate() -> None:
    markdown = (
        "## Why This Read\n\n"
        "The positive evidence carries the default read. "
        "The current source packet does not establish a default population; do not fill that gap by inference."
    )

    prompt_markdown = model_facing_section_markdown(markdown, {"heading": "Why This Read"})

    assert "does not establish" not in prompt_markdown
    assert "positive evidence" in prompt_markdown
