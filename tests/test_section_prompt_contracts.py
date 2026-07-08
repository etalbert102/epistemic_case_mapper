from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing_section_retry import retry_section_prompt
from epistemic_case_mapper.map_briefing_section_repair_prompt import section_repair_prompt
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


def test_section_prompt_requires_visible_evidence_weighting() -> None:
    section = {
        "title": "Evidence Carrying the Conclusion",
        "markdown": "## Evidence Carrying the Conclusion\n\nThe evidence points toward a bounded answer.",
    }
    contract = {
        "heading": "Evidence Carrying the Conclusion",
        "_section_synthesis_scaffold": {
            "section_projection_packets": {
                "sections": [
                    {
                        "section": "Evidence Carrying the Conclusion",
                        "section_thesis": "Show what carries and weakens the conclusion.",
                        "decision_move": "Identify load-bearing evidence and its limits.",
                        "context_status": "ready",
                        "owned_evidence": [
                            {
                                "candidate_card_id": "ec1",
                                "spine_field_id": "strongest_support_1",
                                "claim": "The intervention was associated with lower event rates in observational data.",
                                "source": "Cohort Review",
                                "intended_role": "support",
                                "quality": "indirect",
                                "limitations": ["role_inferred_from_claim_text"],
                                "use": "This section may explain this evidence fully.",
                            }
                        ],
                    }
                ]
            }
        },
        "required_evidence": [],
        "evidence_references": [],
        "owned_elsewhere_evidence": [],
        "required_gaps": [],
        "required_cruxes": [],
        "required_main_memo_obligations": [],
        "section_synthesis_packet": {},
        "has_obligations": True,
    }

    prompt = _section_rewrite_prompt(section, contract, previous_title="Why This Read", next_title="Scope")

    assert "Apply evidence-weight discipline" in prompt
    assert "which inputs are indirect, weak, role-inferred" in prompt
    assert "Do not turn low-weight or indirect evidence into broad practical advice" in prompt
    assert "include one listed search term exactly" in prompt
    assert "Do not invent or abbreviate citation labels" in prompt
    assert "ec1 is indirect evidence" in prompt
    assert "ec1 has inferred evidence role" in prompt
    assert "section_use_projections" in prompt
    assert "section_use_guidance" in prompt
    assert "what distinct value this section adds" in prompt


def test_model_packet_projects_reused_evidence_into_section_specific_uses() -> None:
    claim = "The pilot reduced application delays by 18 percent in a before-after evaluation."
    base_scaffold = {
        "section_context_decision_packets": {
            "sections": [
                {
                    "section": "Why This Read",
                    "section_thesis": "Explain why the pilot result supports the default read.",
                    "context_status": "ready",
                    "owned_evidence": [
                        {
                            "candidate_card_id": "ec-delay",
                            "claim": claim,
                            "source": "Evaluation Report",
                            "intended_role": "support",
                            "quantity_values": ["18 percent"],
                        }
                    ],
                },
                {
                    "section": "Practical Read",
                    "section_thesis": "Translate the pilot result into bounded practical implications.",
                    "context_status": "ready",
                    "owned_evidence": [
                        {
                            "candidate_card_id": "ec-delay",
                            "claim": claim,
                            "source": "Evaluation Report",
                            "intended_role": "support",
                            "quantity_values": ["18 percent"],
                        }
                    ],
                },
            ]
        }
    }
    why_contract = {
        "heading": "Why This Read",
        "_section_synthesis_scaffold": base_scaffold,
        "required_evidence": [],
        "evidence_references": [],
        "owned_elsewhere_evidence": [],
        "required_gaps": [],
        "required_cruxes": [],
        "required_main_memo_obligations": [],
        "section_synthesis_packet": {},
    }
    practical_contract = {**why_contract, "heading": "Practical Read"}

    why_packet = model_facing_section_contract(why_contract)["model_section_packet"]
    practical_packet = model_facing_section_contract(practical_contract)["model_section_packet"]

    assert why_packet["section_use_projections"][0]["section_use"] == "reasoning_support"
    assert practical_packet["section_use_projections"][0]["section_use"] == "practical_implication"
    assert "reasoning path" in why_packet["section_use_guidance"]
    assert "decision implications" in practical_packet["section_use_guidance"]
    assert why_packet["section_use_projections"][0]["expected_section_value"] != practical_packet["section_use_projections"][0]["expected_section_value"]


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
    assert "section repeated source detail without adding this section's distinct analytic value" in prompt
    assert "scope_boundary_02" in prompt
    assert "required obligation search terms" in prompt
    assert "Do not invent or abbreviate parenthetical source labels" in prompt
    assert "Return regular Markdown only" in prompt
    assert "Do not use JSON" in prompt


def test_retry_prompt_can_include_rejected_section_for_correction() -> None:
    prompt = retry_section_prompt(
        "Base prompt",
        ["Practical Read drifts into unsupported implementation advice"],
        attempt=2,
        rejected_section="## Practical Read\n\nMonitor implementation broadly.",
    )

    assert "Rejected section to correct:" in prompt
    assert "## Practical Read\n\nMonitor implementation broadly." in prompt
    assert "Correct the rejected section instead of starting over" in prompt


def test_practical_read_repair_prompt_gives_positive_non_advice_shape() -> None:
    prompt = section_repair_prompt(
        {"title": "Practical Read", "markdown": "## Practical Read\n\nDraft."},
        {
            "heading": "Practical Read",
            "required_evidence": [],
            "evidence_references": [],
            "owned_elsewhere_evidence": [],
            "required_gaps": [],
            "required_cruxes": [],
            "required_main_memo_obligations": [],
            "section_synthesis_packet": {},
        },
        "## Practical Read\n\nPractical considerations include monitoring implementation.",
        [
            "Practical Read drifts into unsupported implementation advice",
            "Practical Read uses generic considerations without a non-inference boundary",
        ],
    )

    assert "Evidence supports treating" in prompt
    assert "Do not use the phrase practical considerations" in prompt
    assert "Do not use imperative advice verbs" in prompt


def test_model_facing_validation_uses_curated_owned_evidence() -> None:
    contract = {
        "heading": "Practical Scope and Exceptions",
        "_section_synthesis_scaffold": {
            "section_context_decision_packets": {
                "sections": [
                    {
                        "section": "Practical Scope and Exceptions",
                        "section_thesis": "Name where the answer travels.",
                        "context_status": "ready",
                        "owned_evidence": [
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


def test_model_packet_allows_reused_cards_when_they_can_support_section_value() -> None:
    conflicting_claim = "Each additional 0.5 egg per day was associated with higher incident cardiovascular disease risk."
    local_claim = "Use the result as a practical boundary rather than as evidence of benefit."
    contract = {
        "heading": "Practical Read",
        "_section_synthesis_scaffold": {
            "section_context_decision_packets": {
                "sections": [
                    {
                        "section": "Practical Read",
                        "section_thesis": "Translate the 0.5 egg per day risk estimate into practical advice.",
                        "context_status": "ready",
                        "owned_evidence": [
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

    assert [row["candidate_card_id"] for row in owned] == ["ec-risk", "ec-local"]
    assert "ec-risk" in model_contract["model_section_packet"]["section_reasoning_contract"].get("owned_card_ids", [])
    assert conflicting_claim in serialized
    assert "0.5 egg per day" in model_contract["model_section_packet"].get("section_thesis", "")


def test_model_packet_allows_reference_cards_when_section_can_add_reasoning_value() -> None:
    referenced_claim = "The trial reduced events by 18 percent in the primary endpoint."
    contract = {
        "heading": "Why This Read",
        "_section_synthesis_scaffold": {
            "section_context_decision_packets": {
                "sections": [
                    {
                        "section": "Why This Read",
                        "section_thesis": "Explain the reasoning path from the trial result.",
                        "context_status": "ready",
                        "owned_evidence": [
                            {
                                "candidate_card_id": "ec-trial",
                                "claim_ids": ["c-trial"],
                                "claim": referenced_claim,
                                "source": "Trial Report",
                                "intended_role": "support",
                            }
                        ],
                    }
                ]
            }
        },
        "required_evidence": [],
        "evidence_references": [
            {
                "candidate_card_id": "ec-trial",
                "claim_ids": ["c-trial"],
                "slot": "support",
                "owner_section": "Evidence Carrying the Conclusion",
                "reference_style": "short_reference",
                "allowed": True,
                "role_summary": "primary endpoint support",
            }
        ],
        "owned_elsewhere_evidence": [],
        "required_gaps": [],
        "required_cruxes": [],
        "required_main_memo_obligations": [],
        "section_synthesis_packet": {},
    }

    model_contract = model_facing_section_contract(contract)
    packet = model_contract["model_section_packet"]

    assert packet["owned_evidence"][0]["candidate_card_id"] == "ec-trial"
    assert packet["reference_only_evidence"][0]["owner_section"] == "Evidence Carrying the Conclusion"
    assert referenced_claim in json.dumps(model_contract)


def test_model_packet_prefers_evidence_role_working_set_when_present() -> None:
    contract = {
        "heading": "Practical Scope and Exceptions",
        "_section_synthesis_scaffold": {
            "section_evidence_working_sets": {
                "sections": [
                    {
                        "section": "Practical Scope and Exceptions",
                        "primary_evidence": [
                            {
                                "candidate_card_id": "ec-support",
                                "claim": "The program reduced avoidable delays in the observed sites.",
                                "source": "Operations evaluation",
                                "section_use": "State the load-bearing observed-site finding.",
                                "evidence_role": "load_bearing",
                            }
                        ],
                        "boundary_evidence": [
                            {
                                "candidate_card_id": "ec-boundary",
                                "claim": "The evidence does not show whether smaller offices can staff the same process.",
                                "source": "Implementation memo",
                                "section_use": "Bound the finding to offices with enough staffing.",
                                "evidence_role": "boundary",
                            }
                        ],
                        "contextual_evidence": [
                            {
                                "candidate_card_id": "ec-context",
                                "claim": "The implementation period included central technical support.",
                                "source": "Rollout report",
                                "section_use": "Briefly contextualize implementation support.",
                                "evidence_role": "contextual",
                            }
                        ],
                        "do_not_use_evidence": [
                            {
                                "candidate_card_id": "ec-off-question",
                                "claim": "A separate dashboard project improved staff satisfaction.",
                                "source": "Staff survey",
                                "evidence_role": "do_not_use",
                            }
                        ],
                        "budget_report": {"primary_available": 1, "primary_included": 1},
                    }
                ]
            },
            "section_context_decision_packets": {
                "sections": [
                    {
                        "section": "Practical Scope and Exceptions",
                        "owned_evidence": [
                            {
                                "candidate_card_id": "ec-legacy",
                                "claim": "Legacy evidence should not win when a working set is present.",
                            }
                        ],
                    }
                ]
            },
        },
        "required_evidence": [],
        "evidence_references": [],
        "owned_elsewhere_evidence": [],
        "required_gaps": [],
        "required_cruxes": [],
        "required_main_memo_obligations": [],
        "section_synthesis_packet": {},
    }

    model_contract = model_facing_section_contract(contract)
    packet = model_contract["model_section_packet"]

    assert packet["primary_evidence"][0]["candidate_card_id"] == "ec-support"
    assert packet["boundary_evidence"][0]["candidate_card_id"] == "ec-boundary"
    assert packet["reference_only_evidence"][0]["candidate_card_id"] == "ec-context"
    assert packet["do_not_use_cards"] == ["ec-off-question"]
    assert [row["candidate_card_id"] for row in packet["owned_evidence"]] == ["ec-support", "ec-boundary"]
    assert "ec-legacy" not in json.dumps(packet)


def test_section_rewrite_prompt_treats_role_groups_as_primary_context() -> None:
    section = {
        "title": "Practical Scope and Exceptions",
        "markdown": "## Practical Scope and Exceptions\n\nThe deterministic draft names the scope.",
    }
    contract = {
        "heading": "Practical Scope and Exceptions",
        "_section_synthesis_scaffold": {
            "section_evidence_working_sets": {
                "sections": [
                    {
                        "section": "Practical Scope and Exceptions",
                        "primary_evidence": [
                            {
                                "candidate_card_id": "ec-support",
                                "claim": "The program reduced delay in observed offices.",
                                "evidence_role": "load_bearing",
                            }
                        ],
                        "boundary_evidence": [
                            {
                                "candidate_card_id": "ec-boundary",
                                "claim": "Smaller offices were not observed.",
                                "evidence_role": "boundary",
                            }
                        ],
                    }
                ]
            }
        },
        "required_evidence": [],
        "evidence_references": [],
        "owned_elsewhere_evidence": [],
        "required_gaps": [],
        "required_cruxes": [],
        "required_main_memo_obligations": [],
        "section_synthesis_packet": {},
    }

    prompt = _section_rewrite_prompt(section, contract, previous_title="Practical Read", next_title="Decision Cruxes")

    assert "primary_evidence as the load-bearing working set" in prompt
    assert "boundary_evidence to define where the answer does and does not travel" in prompt
    assert "owned_evidence only as the compatibility view" in prompt
    assert "ec-boundary" in prompt
