from __future__ import annotations

from epistemic_case_mapper.decision_frame import build_decision_frame, refine_crux_contract


def test_decision_frame_detects_process_evaluation_without_domain_specific_case_terms() -> None:
    candidate_map = {
        "claims": [
            {"claim_id": "c1", "claim": "The debate format rewarded memorized detail over calibrated reasoning."},
            {"claim_id": "c2", "claim": "The judges did not receive ongoing feedback on probability estimates."},
        ]
    }
    frame = build_decision_frame(candidate_map, {"all_evidence": []}, {"status": "usable_with_review"}, question="What should this debate result be used for?")

    assert frame["frame_type"] == "process_or_method_evaluation"
    assert "process" in frame["direct_answer"].lower()
    assert "neutral adjudication" in frame["direct_answer"].lower()


def test_refined_cruxes_replace_generic_placeholders_and_ellipsis() -> None:
    candidate_map = {
        "claims": [
            {"claim_id": "c1", "claim": "The debate format rewarded memorized detail over calibrated reasoning."},
            {"claim_id": "c2", "claim": "The result was presented as a broad adjudication of the underlying dispute."},
        ]
    }
    crux_contract = {
        "crux_count": 1,
        "cruxes": [
            {
                "crux": "Decision-changing condition",
                "relation_type": "challenges",
                "source_claim": "c1",
                "target_claim": "c2",
                "why_it_matters": "Claim B critiques Claim A.",
                "current_read": "The current packet treats this condition as relevant to the recommendation.",
                "would_change_if": "New evidence showed the condition did not materially affect the decision.",
            }
        ],
    }

    refined = refine_crux_contract(crux_contract, candidate_map)
    row = refined["cruxes"][0]

    assert "Decision-changing condition" not in row["crux"]
    assert "..." not in row["crux"]
    assert "Claim B" not in row["why_it_matters"]
    assert "current packet treats this condition" not in row["current_read"]
