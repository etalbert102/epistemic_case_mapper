from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing_section_retry import retry_section_prompt
from epistemic_case_mapper.map_briefing_section_rewrite import _section_rewrite_prompt


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

