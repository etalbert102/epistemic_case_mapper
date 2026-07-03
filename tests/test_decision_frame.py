from __future__ import annotations

from epistemic_case_mapper.decision_frame import build_decision_frame, question_quality_report, refine_crux_contract
from epistemic_case_mapper.map_briefing_pipeline import briefing_scaffold, build_map_briefing_prompt


def test_question_quality_blocks_missing_and_placeholder_questions() -> None:
    missing = question_quality_report("")
    placeholder = question_quality_report("What decision-relevant read does the evidence map support?")

    assert missing["status"] == "blocked"
    assert missing["issues"][0]["issue_type"] == "missing_question"
    assert placeholder["status"] == "blocked"
    assert placeholder["issues"][0]["issue_type"] == "generic_placeholder_question"


def test_decision_frame_answers_representation_question_directly() -> None:
    candidate_map = {
        "claims": [
            {"claim_id": "c1", "claim": "One source favors explanation A while another preserves strong disagreement."},
            {"claim_id": "c2", "claim": "A flat synthesis would collapse the disagreement into one bottom line."},
        ]
    }
    question = "How should a narrow slice of evidence be represented without flattening disagreement?"

    frame = build_decision_frame(candidate_map, {"all_evidence": []}, {"status": "usable"}, question=question)

    assert frame["frame_type"] == "representation_decision"
    assert "Represent a narrow slice of evidence" in frame["direct_answer"]
    assert "preserves disagreement" in frame["direct_answer"]
    assert "preserves flattening" not in frame["direct_answer"]


def test_representation_scaffold_does_not_use_low_concern_answer_frame() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c1",
                "claim": "One source favors explanation A while another preserves strong disagreement.",
                "source_id": "s1",
                "role": "conclusion_support",
            }
        ],
        "relations": [],
    }
    question = "How should a narrow slice of evidence be represented without flattening disagreement?"

    scaffold = briefing_scaffold(candidate_map, {"status": "usable", "score": 90}, {"s1": "Source 1"}, {"items": []}, question=question)
    default_answer = scaffold["decision_model"]["default_answer"]

    assert default_answer["classification"] == "representation_with_named_disagreement_and_scope_limits"
    assert "low-concern" not in default_answer["plain_language_instruction"]
    assert "low-concern" not in scaffold["section_policy"]["main_support"]

    prompt = build_map_briefing_prompt(
        candidate_map=candidate_map,
        quality_report={"status": "usable", "score": 90},
        question=question,
        source_lookup={"s1": "Source 1"},
        erosion_audit={"items": []},
        scaffold=scaffold,
    )
    assert "low-concern" not in prompt
    assert "representation_with_named_disagreement_and_scope_limits" in prompt


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


def test_decision_frame_treats_should_questions_as_action_decisions_before_adjudication() -> None:
    candidate_map = {
        "claims": [
            {"claim_id": "c1", "claim": "The evidence is mixed but supports a conditional practical answer."},
        ]
    }
    question = "Given the provided evidence, should generally healthy adults treat moderate exposure as acceptable?"

    frame = build_decision_frame(candidate_map, {"all_evidence": []}, {"status": "usable_with_review"}, question=question)

    assert frame["frame_type"] == "action_or_policy_decision"
    assert "implementation constraints" in frame["direct_answer"]
    assert "scoped contribution to the adjudication" not in frame["direct_answer"]


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
