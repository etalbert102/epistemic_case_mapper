from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_prompt import build_memo_ready_section_synthesis_plan
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_weighting_contract import (
    build_source_weighting_contract,
    build_source_weighting_fidelity_report,
    build_source_weighting_section_packet,
)


def test_source_weighting_contract_compiles_hierarchy_into_roles() -> None:
    contract = build_source_weighting_contract(_canonical_packet())

    roles = {row["source_id"]: row["role"] for row in contract["sources"]}
    assert roles["support_source"] == "drives_answer"
    assert roles["risk_source"] == "bounds_answer"
    assert roles["dose_source"] == "calibrates_magnitude"
    assert contract["report"]["status"] == "ready"
    assert contract["report"]["role_counts"]["drives_answer"] == 1


def test_source_weighting_section_packet_excludes_full_evidence_checklist() -> None:
    contract = build_source_weighting_contract(_canonical_packet())
    packet = build_source_weighting_section_packet(
        {
            "decision_question": "Should option A be adopted?",
            "balanced_answer_frame": {"confidence": "medium", "best_current_read": "Adopt option A within scope."},
            "source_weighting_contract": contract,
        }
    )

    assert packet["schema_id"] == "source_weighting_section_packet_v1"
    assert "evidence_context" not in packet
    assert "source_role_groups" in packet
    assert packet["validation_contract"]["roles_to_cover"] == [
        "drives_answer",
        "bounds_answer",
        "calibrates_magnitude",
    ]


def test_section_synthesis_plan_routes_source_weighting_through_contract() -> None:
    memo_ready = {
        "schema_id": "memo_ready_packet_v1",
        "decision_question": "Should option A be adopted?",
        "source_trail": [
            {"source_id": "support_source"},
            {"source_id": "risk_source"},
            {"source_id": "dose_source"},
        ],
        "evidence_items": [{"item_id": "support", "claim": "Option A improves the main outcome.", "source_ids": ["support_source"]}],
        "canonical_decision_writer_packet": _canonical_packet(),
    }

    plan = build_memo_ready_section_synthesis_plan(memo_ready)
    source_section = next(row for row in plan["sections"] if row["section_id"] == "source_weighting")
    prompt = source_section["prompt"]

    assert "### Source role contract" in prompt
    assert "### Source hierarchy lane notes" in prompt
    assert "### Required evidence points" not in prompt
    assert "support_source" in prompt
    assert "risk_source" in prompt
    assert plan["source_weighting_flow_audit"]["section_packet_has_full_evidence_context"] is False


def test_source_weighting_fidelity_flags_flattened_section() -> None:
    contract = build_source_weighting_contract(_canonical_packet())
    memo = (
        "## How to Weight the Evidence\n\n"
        "The evidence includes support findings [support_source], risk findings [risk_source], "
        "and dose guidance [dose_source].\n"
    )

    report = build_source_weighting_fidelity_report(memo, {"source_weighting_contract": contract})

    assert report["status"] == "warning"
    assert any(issue["issue_type"] == "flattened_source_weighting" for issue in report["issues"])


def _canonical_packet() -> dict:
    return {
        "schema_id": "canonical_decision_writer_packet_v1",
        "decision_question": "Should option A be adopted?",
        "citation_registry": [
            {"source_id": "support_source"},
            {"source_id": "risk_source"},
            {"source_id": "dose_source"},
        ],
        "source_hierarchy": {
            "schema_id": "source_weight_hierarchy_v1",
            "hierarchy_thesis": "Support Source carries the read; Risk Source bounds it; Dose Source calibrates use.",
            "lanes": {
                "primary_answer_drivers": [
                    {
                        "source_ids": ["support_source"],
                        "evidence_item_ids": ["support"],
                        "role": "Carry the default answer.",
                        "rationale": "Directly studies the decision-relevant outcome.",
                    }
                ],
                "counterweight_sources": [
                    {
                        "source_ids": ["risk_source"],
                        "evidence_item_ids": ["risk"],
                        "role": "Bound the default answer.",
                        "rationale": "Shows an implementation risk that narrows confidence.",
                    }
                ],
                "quantitative_calibrators": [
                    {
                        "source_ids": ["dose_source"],
                        "evidence_item_ids": ["dose"],
                        "role": "Calibrate the usable threshold.",
                        "rationale": "Gives the operating dose limit.",
                    }
                ],
            },
            "source_accounting": [
                {"source_id": "support_source", "primary_lane": "primary_answer_drivers", "rationale": "Carries the answer."},
                {"source_id": "risk_source", "primary_lane": "counterweight_sources", "rationale": "Bounds the answer."},
                {"source_id": "dose_source", "primary_lane": "quantitative_calibrators", "rationale": "Calibrates the threshold."},
            ],
        },
        "source_weight_judgments": [
            {
                "source_ids": ["support_source"],
                "main_use": "drives_answer",
                "memo_weight_sentence": "Support Source carries the default answer.",
                "why_weight_this_way": "It directly studies the main outcome.",
            },
            {
                "source_ids": ["risk_source"],
                "main_use": "bounds_answer",
                "memo_weight_sentence": "Risk Source bounds confidence in the default answer.",
                "why_weight_this_way": "It identifies the strongest limiting condition.",
            },
            {
                "source_ids": ["dose_source"],
                "main_use": "calibrates_magnitude",
                "memo_weight_sentence": "Dose Source calibrates the practical threshold.",
                "why_weight_this_way": "It gives the decision-relevant operating threshold.",
            },
        ],
        "evidence_language_contracts": [
            {
                "source_ids": ["support_source"],
                "calibration_basis": ["observational evidence"],
                "wording_rule": "Phrase as association unless causal evidence is available.",
            }
        ],
    }
