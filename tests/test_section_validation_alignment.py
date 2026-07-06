from __future__ import annotations

from epistemic_case_mapper.map_briefing_section_rewrite import _section_rewrite_issues


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
