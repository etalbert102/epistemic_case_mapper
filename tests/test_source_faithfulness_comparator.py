from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_packet import build_analyst_packet_bundle
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_faithfulness import (
    repair_adjudication_source_faithfulness,
    source_faithfulness_warnings,
)


def _packet() -> dict:
    return {
        "decision_question": "Should option A be treated as neutral?",
        "answer_frame": {"default_answer": "Treat option A as neutral under stated conditions.", "confidence": "medium"},
        "source_trail": [{"source_id": "s1", "source_label": "Comparator Study"}],
    }


def _comparator_ledger() -> dict:
    return {
        "schema_id": "analyst_evidence_ledger_v1",
        "decision_question": "Should option A be treated as neutral?",
        "stable_final_answer_frame": {
            "schema_id": "stable_final_answer_frame_v1",
            "decision_question": "Should option A be treated as neutral?",
            "answer_status": "provisional",
            "current_best_answer": "Treat option A as neutral under stated conditions.",
            "selected_answer_option_id": "neutral",
        },
        "rows": [
            {
                "evidence_item_id": "claim:comparator",
                "input_kind": "retained_map_claim",
                "source_ids": ["s1"],
                "source_labels": ["Comparator Study"],
                "claim": "Replacing option A with option B was associated with a higher adverse-event rate.",
                "natural_bottom_line": "Option B looked worse than option A in a replacement analysis.",
                "claim_context": {
                    "population": "eligible adults",
                    "exposure_or_option": "replacing option A with option B",
                    "outcome_or_endpoint": "adverse-event rate",
                    "evidence_design": "replacement analysis",
                    "stated_scope": ["replacement analysis"],
                    "stated_limitations": ["not a direct estimate of option A's standalone effect"],
                },
                "claim_quantities": [
                    {
                        "value": "hazard ratio 1.15",
                        "local_interpretation": "Hazard ratio for replacing option A with option B",
                        "source_quote": "higher adverse-event rate when option A was replaced with option B",
                    }
                ],
                "quantity_values": ["hazard ratio 1.15"],
            }
        ],
    }


def _bad_adjudication() -> dict:
    return {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": "Should option A be treated as neutral?",
        "rows": [
            {
                "evidence_item_id": "claim:comparator",
                "memo_use": "load_bearing_primary_support",
                "answer_relation": "supports_answer",
                "target_answer_option": "neutral",
                "effect_on_final_answer": "supports current_best_answer",
                "importance_rank": 1,
                "rationale": "Treats the comparator result as direct support for a neutral answer.",
                "source_ids": ["s1"],
                "quantity_values": ["hazard ratio 1.15"],
            }
        ],
    }


def test_source_faithfulness_repairs_comparator_evidence_used_as_direct_support() -> None:
    repaired, report = repair_adjudication_source_faithfulness(_comparator_ledger(), _bad_adjudication())
    row = repaired["rows"][0]

    assert report["status"] == "repaired"
    assert report["warnings_before"][0]["warning"] == "comparator_substitution_claim_used_as_direct_answer_support"
    assert row["memo_use"] == "mechanism_or_context"
    assert row["answer_relation"] == "contextualizes_answer"
    assert "Comparator/substitution context" in row["decision_contribution"]
    assert "direct effect of the target option" in row["misuse_warning"]
    assert "comparator or substitution contrast" in row["quantity_takeaway"]
    assert source_faithfulness_warnings(_comparator_ledger(), repaired) == []


def test_analyst_packet_aligns_bad_decision_model_group_with_comparator_repair() -> None:
    repaired, _ = repair_adjudication_source_faithfulness(_comparator_ledger(), _bad_adjudication())
    decision_model = {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": "Should option A be treated as neutral?",
        "direct_answer": "Treat option A as neutral under stated conditions.",
        "confidence": "medium",
        "overall_rationale": "Fixture.",
        "evidence_groups": [
            {
                "group_id": "bad_direct_support",
                "proposition": "Option A is neutral because the comparator result had hazard ratio 1.15.",
                "memo_role": "load_bearing_primary_support",
                "answer_relation": "supports_answer",
                "effect_on_final_answer": "supports current_best_answer",
                "covered_evidence_item_ids": ["claim:comparator"],
                "importance_rank": 1,
                "rationale": "Support-shaped model output.",
            }
        ],
        "evidence_dispositions": [],
    }

    result = build_analyst_packet_bundle(
        packet=_packet(),
        ledger=_comparator_ledger(),
        adjudication=repaired,
        decision_model=decision_model,
    )
    synthesis = result["analyst_synthesis_packet"]
    alignment = result["analyst_packet_quality_report"]["group_accounting"]["adjudication_role_alignment"]

    assert not synthesis["primary_reasoning_chain"]
    assert synthesis["background_context"][0]["memo_role"] == "mechanism_or_context"
    assert "Comparator/substitution context" in synthesis["background_context"][0]["proposition"]
    assert alignment["aligned_groups"][0]["to_memo_role"] == "mechanism_or_context"
