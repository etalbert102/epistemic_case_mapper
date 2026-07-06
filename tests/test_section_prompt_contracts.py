from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing_section_retry import retry_section_prompt
from epistemic_case_mapper.map_briefing_section_rewrite import _section_rewrite_prompt
from epistemic_case_mapper.map_briefing_section_prompt_contract import model_facing_section_contract


def test_section_prompt_hides_owned_elsewhere_full_claims() -> None:
    forbidden_claim = "The pilot reduced permit review time by 34 percent without increasing error rates."
    section = {
        "title": "Why This Read",
        "markdown": f"## Why This Read\n\n{forbidden_claim}",
    }
    contract = {
        "heading": "Why This Read",
        "required_evidence": [],
        "evidence_references": [],
        "owned_elsewhere_evidence": [
            {
                "slot": "hard-outcome support",
                "claim": forbidden_claim,
                "source": "Evaluation",
                "anchor_terms": ["pilot", "reduced", "permit", "review", "34", "error"],
                "reference_policy": {
                    "owner_section": "Evidence Carrying the Conclusion",
                    "reference_style": "do_not_repeat",
                    "allowed": False,
                },
            }
        ],
        "required_gaps": [],
        "required_cruxes": [],
        "required_main_memo_obligations": [],
        "section_synthesis_packet": {
            "load_bearing_claims": [
                {"claim": "Capacity remains the operational boundary.", "source": "Ops"}
            ]
        },
    }

    prompt = _section_rewrite_prompt(section, contract, previous_title="Practical Read", next_title="Evidence Carrying")

    contract_text = prompt.split("Section contract:\n", 1)[1].split("\n\nThe section below", 1)[0]
    section_text = prompt.split("Section to rewrite:\n", 1)[1]
    model_contract = json.loads(contract_text)
    assert forbidden_claim not in contract_text
    assert "owned_elsewhere_evidence" not in model_contract
    assert "prohibited_repetition" not in model_contract.get("model_section_packet", {})
    assert "reference_policy_summary" not in model_contract.get("validation_obligations", {})
    assert forbidden_claim not in section_text
    assert "## Why This Read" in section_text
    assert "analyst producing decision-ready analysis" in prompt
    assert "not to mechanically restate the packet" in prompt
    assert "Return only the rewritten section as regular Markdown" in prompt
    assert "Do not wrap the answer in JSON" in prompt
    assert "Return only valid JSON" not in prompt
    assert "Do not mention this evidence here" not in contract_text


def test_retry_prompt_sanitizes_rejected_claim_text() -> None:
    forbidden_claim = "Associations between egg consumption and CVD mortality were not significant after adjustment."

    prompt = retry_section_prompt(
        "Base prompt",
        [
            f"section repeats evidence owned by Evidence Carrying the Conclusion: {forbidden_claim}",
            "section dropped required main-memo obligation: scope_boundary_02 The impact of egg consumption on lipid profiles appears greater.",
        ],
        attempt=2,
    )

    assert forbidden_claim not in prompt
    assert "lipid profiles appears greater" not in prompt
    assert "section used evidence assigned outside this section" in prompt
    assert "scope_boundary_02" in prompt
    assert "Return regular Markdown only" in prompt
    assert "Do not use JSON" in prompt


def test_model_facing_validation_uses_curated_owned_evidence() -> None:
    contract = {
        "heading": "Practical Scope and Exceptions",
        "_section_synthesis_scaffold": {
            "section_reasoning_cards": {
                "sections": [
                    {
                        "section": "Practical Scope and Exceptions",
                        "section_thesis": "Name where the answer travels.",
                        "context_status": "ready",
                        "owned_cards": [
                            {
                                "candidate_card_id": "ec0001",
                                "claim": "Data above the ordinary exposure level remain sparse.",
                                "source": "Source",
                                "intended_role": "scope",
                                "reason_for_inclusion": "This card bounds the practical scope.",
                            }
                        ],
                    }
                ]
            }
        },
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
        "section_synthesis_packet": {},
    }

    model_contract = model_facing_section_contract(contract)
    model_owned = model_contract["model_section_packet"]["owned_evidence"]

    assert model_owned[0]["claim"] == "Data above the ordinary exposure level remain sparse."
    assert "required_evidence" not in model_contract.get("validation_obligations", {})
    assert "Comparator evidence" not in json.dumps(model_contract)


def test_model_packet_filters_curated_owned_cards_through_validator_ownership() -> None:
    conflicting_claim = "Each additional 0.5 egg per day was associated with higher incident cardiovascular disease risk."
    local_claim = "Use the result as a practical boundary rather than as evidence of benefit."
    contract = {
        "heading": "Practical Read",
        "_section_synthesis_scaffold": {
            "section_reasoning_cards": {
                "sections": [
                    {
                        "section": "Practical Read",
                        "section_thesis": "Translate the 0.5 egg per day risk estimate into practical advice.",
                        "context_status": "ready",
                        "owned_cards": [
                            {
                                "candidate_card_id": "ec-risk",
                                "claim_ids": ["c-risk"],
                                "claim": conflicting_claim,
                                "source": "JAMA cohort",
                                "intended_role": "support",
                                "reason_for_inclusion": "The curated context assigned this to Practical Read.",
                            },
                            {
                                "candidate_card_id": "ec-local",
                                "claim": local_claim,
                                "source": "Synthesis",
                                "intended_role": "practical implication",
                                "reason_for_inclusion": "This card states the local decision implication.",
                            },
                        ],
                    }
                ]
            }
        },
        "required_evidence": [],
        "evidence_references": [],
        "owned_elsewhere_evidence": [
            {
                "candidate_card_id": "ec-risk",
                "claim_ids": ["c-risk"],
                "claim": conflicting_claim,
                "source": "JAMA cohort",
                "reference_policy": {
                    "owner_section": "Evidence Carrying the Conclusion",
                    "reference_style": "do_not_repeat",
                    "allowed": False,
                },
            }
        ],
        "required_gaps": [],
        "required_cruxes": [],
        "required_main_memo_obligations": [],
        "section_synthesis_packet": {},
    }

    model_contract = model_facing_section_contract(contract)
    serialized = json.dumps(model_contract)
    owned = model_contract["model_section_packet"]["owned_evidence"]

    assert [row["candidate_card_id"] for row in owned] == ["ec-local"]
    assert "ec-risk" not in model_contract["model_section_packet"]["section_reasoning_contract"].get("owned_card_ids", [])
    assert conflicting_claim not in serialized
    assert "0.5 egg per day" not in model_contract["model_section_packet"].get("section_thesis", "")
