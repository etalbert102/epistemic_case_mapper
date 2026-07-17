from __future__ import annotations

import pytest
from pydantic import ValidationError

from epistemic_case_mapper.map_briefing_analyst_schemas import (
    AnalystAdjudication,
    AnalystAnswerFrame,
    AnalystDecisionModel,
    AnalystSynthesisPacket,
    build_analyst_adjudication_parse_report,
    build_analyst_decision_model_parse_report,
)


def _ledger() -> dict:
    return {
        "schema_id": "analyst_evidence_ledger_v1",
        "rows": [
            {"evidence_item_id": "bundle:one"},
            {"evidence_item_id": "warning:two"},
        ],
    }


def _valid_payload() -> dict:
    return {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": "Should option A be adopted?",
        "rows": [
            {
                "evidence_item_id": "bundle:one",
                "memo_use": "load_bearing_primary_support",
                "importance_rank": 1,
                "rationale": "Direct support for the answer.",
            },
            {
                "evidence_item_id": "warning:two",
                "memo_use": "load_bearing_counterweight",
                "importance_rank": 2,
                "rationale": "Important limitation.",
            },
        ],
    }


def test_analyst_adjudication_schema_accepts_valid_rows() -> None:
    parsed = AnalystAdjudication.model_validate(_valid_payload())
    report = build_analyst_adjudication_parse_report(_valid_payload(), _ledger())

    assert parsed.rows[0].memo_use == "load_bearing_primary_support"
    assert parsed.rows[0].answer_relation == "uncertain_relation"
    assert report["status"] == "ready"
    assert report["valid"] is True


def test_analyst_adjudication_schema_accepts_answer_relation_aliases() -> None:
    payload = _valid_payload()
    payload["rows"][0]["answer_relation"] = "supports bottom line"
    payload["rows"][1]["answer_relation"] = "scope"

    parsed = AnalystAdjudication.model_validate(payload)

    assert parsed.rows[0].answer_relation == "supports_answer"
    assert parsed.rows[1].answer_relation == "bounds_scope"


def test_analyst_adjudication_schema_normalizes_nullable_downgrade_reason() -> None:
    payload = _valid_payload()
    payload["rows"][0]["downgrade_reason"] = None

    parsed = AnalystAdjudication.model_validate(payload)

    assert parsed.rows[0].downgrade_reason == ""


def test_analyst_adjudication_schema_rejects_invalid_memo_use() -> None:
    payload = _valid_payload()
    payload["rows"][0]["memo_use"] = "strong_vibes"

    with pytest.raises(ValidationError):
        AnalystAdjudication.model_validate(payload)

    report = build_analyst_adjudication_parse_report(payload, _ledger())
    assert report["status"] == "invalid_schema"


def test_analyst_adjudication_parse_report_flags_missing_and_unknown_rows() -> None:
    payload = _valid_payload()
    payload["rows"] = [
        {
            "evidence_item_id": "bundle:one",
            "memo_use": "load_bearing_primary_support",
            "importance_rank": 1,
            "rationale": "Direct support for the answer.",
        },
        {
            "evidence_item_id": "bundle:unknown",
            "memo_use": "background_only",
            "importance_rank": 8,
            "rationale": "Context.",
        },
    ]

    report = build_analyst_adjudication_parse_report(payload, _ledger())

    assert report["status"] == "warning"
    assert report["missing_evidence_item_ids"] == ["warning:two"]
    assert report["unknown_evidence_item_ids"] == ["bundle:unknown"]


def test_analyst_adjudication_parse_report_flags_invalid_covered_by_target() -> None:
    payload = _valid_payload()
    payload["rows"][1]["memo_use"] = "covered_by_group"
    payload["rows"][1]["covered_by"] = ["group:missing"]

    report = build_analyst_adjudication_parse_report(payload, _ledger())

    assert report["status"] == "warning"
    assert report["invalid_covered_by"] == ["group:missing"]


def test_analyst_adjudication_parse_report_normalizes_safe_model_aliases() -> None:
    payload = _valid_payload()
    payload["rows"][1]["memo_use"] = "covered_by"
    payload["rows"][1]["covered_by"] = ["bundle:one"]

    report = build_analyst_adjudication_parse_report(payload, _ledger())
    parsed = AnalystAdjudication.model_validate(
        {
            **payload,
            "rows": [
                payload["rows"][0],
                {**payload["rows"][1], "memo_use": "covered_by_group"},
            ],
        }
    )

    assert report["status"] == "ready"
    assert parsed.rows[1].memo_use == "covered_by_group"


def test_answer_frame_requires_direct_supported_answer() -> None:
    parsed = AnalystAnswerFrame.model_validate(
        {
            "decision_question": "Should option A be adopted?",
            "direct_answer": "Adopt option A only if maintenance funding is protected.",
            "confidence": "medium",
            "why_this_read": "The strongest support is conditional and the counterweight is maintenance-sensitive.",
            "supporting_evidence_item_ids": ["bundle:one"],
        }
    )

    assert parsed.schema_id == "analyst_answer_frame_v1"
    assert parsed.supporting_evidence_item_ids == ["bundle:one"]


def test_answer_frame_accepts_explicit_bluf_hierarchy() -> None:
    parsed = AnalystAnswerFrame.model_validate(
        {
            "decision_question": "Should option A be adopted?",
            "direct_answer": "Adopt option A in the main case; however, boundary cases need review.",
            "primary_answer": "Adopt option A in the main case.",
            "secondary_detail": "Boundary cases need review.",
            "secondary_detail_type": "scope_boundary",
            "confidence": "medium",
            "why_this_read": "The support is strong inside scope.",
        }
    )

    assert parsed.primary_answer == "Adopt option A in the main case."
    assert parsed.secondary_detail_type == "scope_boundary"


def test_synthesis_packet_schema_accepts_compact_reasoning_packet() -> None:
    parsed = AnalystSynthesisPacket.model_validate(
        {
            "decision_question": "Should option A be adopted?",
            "bottom_line": "Adopt option A only under the protected-funding condition.",
            "primary_reasoning_chain": [
                {
                    "group_id": "group_support",
                    "proposition": "Outcome evidence supports option A.",
                    "memo_role": "load_bearing_primary_support",
                    "covered_evidence_item_ids": ["bundle:one"],
                    "rationale": "This is the main evidence for the answer.",
                }
            ],
            "main_counterweights": [],
        }
    )

    assert parsed.schema_id == "analyst_synthesis_packet_v1"
    assert parsed.primary_reasoning_chain[0].covered_evidence_item_ids == ["bundle:one"]


def test_analyst_decision_model_parse_report_accepts_global_groups() -> None:
    payload = {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A only with the risk condition; however, high-risk settings need separate review.",
        "primary_answer": "Adopt option A only with the risk condition.",
        "secondary_detail": "High-risk settings need separate review.",
        "secondary_detail_type": "scope_boundary",
        "full_direct_answer": "Adopt option A only with the risk condition; however, high-risk settings need separate review.",
        "confidence": "medium",
        "overall_rationale": "Support is strong but the warning bounds the answer.",
        "evidence_groups": [
            {
                "group_id": "support_group",
                "proposition": "Outcome evidence supports option A.",
                "memo_role": "load_bearing_primary_support",
                "importance_rank": 1,
                "covered_evidence_item_ids": ["bundle:one"],
                "rationale": "Main support.",
                "evidence_strength": "moderate",
                "answer_impact": "Supports adoption.",
                "uncertainty_type": "none",
            },
            {
                "group_id": "risk_group",
                "proposition": "The warning limits unconditional adoption.",
                "memo_role": "load_bearing_counterweight",
                "importance_rank": 2,
                "covered_evidence_item_ids": ["warning:two"],
                "rationale": "Main limiting evidence.",
            },
        ],
        "evidence_dispositions": [
            {"evidence_item_id": "bundle:one", "disposition": "foreground", "group_id": "support_group"},
            {"evidence_item_id": "warning:two", "disposition": "foreground", "group_id": "risk_group"},
        ],
        "quantitative_anchors": [],
        "what_would_change_the_answer": ["More direct implementation-risk evidence."],
        "argument_plan": [],
        "decision_logic": {"bounded_bottom_line": "Adopt option A only with the risk condition."},
    }

    parsed = AnalystDecisionModel.model_validate(payload)
    report = build_analyst_decision_model_parse_report(payload, _ledger())

    assert parsed.evidence_groups[0].memo_role == "load_bearing_primary_support"
    assert parsed.primary_answer == "Adopt option A only with the risk condition."
    assert parsed.secondary_detail_type == "scope_boundary"
    assert report["status"] == "warning"
    assert "missing_practical_implications" in report["issues"]
    assert report["valid"] is True
    assert report["covered_evidence_item_count"] == 2


def test_analyst_decision_model_parse_report_rejects_unknown_evidence_ids() -> None:
    payload = {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A.",
        "overall_rationale": "The group uses an unknown row.",
        "evidence_groups": [
            {
                "group_id": "support_group",
                "proposition": "Unknown evidence supports option A.",
                "memo_role": "load_bearing_primary_support",
                "covered_evidence_item_ids": ["bundle:missing"],
                "rationale": "Unknown.",
            },
        ],
    }

    report = build_analyst_decision_model_parse_report(payload, _ledger())

    assert report["valid"] is False
    assert report["unknown_evidence_item_ids"] == ["bundle:missing"]


def test_analyst_decision_model_parse_report_warns_on_unknown_exception_dispositions() -> None:
    payload = {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A with the warning condition.",
        "overall_rationale": "Known evidence is grouped; an unknown exception disposition should be diagnostic only.",
        "evidence_groups": [
            {
                "group_id": "support_group",
                "proposition": "Known evidence supports option A.",
                "memo_role": "load_bearing_primary_support",
                "covered_evidence_item_ids": ["bundle:one"],
                "rationale": "Known support.",
            },
        ],
        "evidence_dispositions": [
            {"evidence_item_id": "coarse:unknown", "disposition": "background_only", "rationale": "Coarse model alias."},
        ],
    }

    report = build_analyst_decision_model_parse_report(payload, _ledger())

    assert report["valid"] is True
    assert report["status"] == "warning"
    assert report["unknown_disposition_ids"] == ["coarse:unknown"]


def test_analyst_decision_model_parse_report_normalizes_none_group_alias() -> None:
    payload = {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A with review.",
        "overall_rationale": "Known evidence is grouped; background rows can have no group.",
        "evidence_groups": [
            {
                "group_id": "support_group",
                "proposition": "Known evidence supports option A.",
                "memo_role": "load_bearing_primary_support",
                "covered_evidence_item_ids": ["bundle:one"],
                "rationale": "Known support.",
            },
        ],
        "evidence_dispositions": [
            {"evidence_item_id": "warning:two", "disposition": "background", "group_id": "none", "rationale": "Not foreground."},
        ],
    }

    parsed = AnalystDecisionModel.model_validate(payload)
    report = build_analyst_decision_model_parse_report(payload, _ledger())

    assert parsed.evidence_dispositions[0].group_id == ""
    assert "invalid_disposition_group_ids" not in report["issues"]


def test_analyst_decision_model_normalizes_group_memo_relevance_alias() -> None:
    payload = {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A with scope limits.",
        "overall_rationale": "The scope evidence bounds the answer.",
        "evidence_groups": [
            {
                "group_id": "scope_group",
                "proposition": "The answer is bounded by applicability.",
                "memo_relevance": "scope_or_applicability",
                "covered_evidence_item_ids": ["bundle:one"],
                "rationale": "Scope matters.",
            },
        ],
    }

    parsed = AnalystDecisionModel.model_validate(payload)
    report = build_analyst_decision_model_parse_report(payload, _ledger())

    assert parsed.evidence_groups[0].memo_role == "scope_or_applicability"
    assert report["valid"] is True
    assert "invalid_schema" not in report["issues"]


def test_analyst_decision_model_clears_role_label_disposition_group_ids() -> None:
    payload = {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A with scope limits.",
        "overall_rationale": "The support group covers the main row.",
        "evidence_groups": [
            {
                "group_id": "support_group",
                "proposition": "Known evidence supports option A.",
                "memo_role": "load_bearing_primary_support",
                "covered_evidence_item_ids": ["bundle:one"],
                "rationale": "Known support.",
            },
        ],
        "evidence_dispositions": [
            {
                "evidence_item_id": "warning:two",
                "disposition": "background",
                "group_id": "scope_or_applicability",
                "rationale": "Model confused group id with memo role.",
            },
        ],
    }

    parsed = AnalystDecisionModel.model_validate(payload)
    report = build_analyst_decision_model_parse_report(payload, _ledger())

    assert parsed.evidence_dispositions[0].group_id == ""
    assert report["valid"] is True
    assert "invalid_disposition_group_ids" not in report["issues"]


def test_analyst_decision_model_parse_report_counts_grouped_rows_as_accounted() -> None:
    payload = {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A.",
        "overall_rationale": "The known rows are covered by a foreground group.",
        "evidence_groups": [
            {
                "group_id": "support_group",
                "proposition": "Known evidence supports option A.",
                "memo_role": "load_bearing_primary_support",
                "covered_evidence_item_ids": ["bundle:one", "warning:two"],
                "rationale": "Both rows are used by the group.",
            },
        ],
        "evidence_dispositions": [],
    }

    report = build_analyst_decision_model_parse_report(payload, _ledger())

    assert report["missing_accounting_ids"] == []
    assert "missing_dispositions" not in report["issues"]
    assert report["status"] == "warning"
    assert "missing_bounded_bottom_line" in report["issues"]
    assert "missing_practical_implications" in report["issues"]


def test_analyst_decision_model_parse_report_warns_on_ungrouped_retention_obligations() -> None:
    ledger = {
        "schema_id": "analyst_evidence_ledger_v1",
        "rows": [
            {"evidence_item_id": "claim:quantity", "quantity_values": ["25% reduction"], "current_role": "load_bearing_primary_support"},
            {"evidence_item_id": "claim:risk", "current_role": "load_bearing_counterweight"},
            {"evidence_item_id": "claim:ordinary", "current_role": "mechanism_or_context"},
        ],
    }
    payload = {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A only with the risk bounded.",
        "overall_rationale": "The ordinary mechanism is grouped but key obligations are only dispositioned.",
        "evidence_groups": [
            {
                "group_id": "ordinary_group",
                "proposition": "The mechanism provides context.",
                "memo_role": "mechanism_or_context",
                "covered_evidence_item_ids": ["claim:ordinary"],
                "rationale": "Context.",
            },
        ],
        "evidence_dispositions": [
            {"evidence_item_id": "claim:quantity", "disposition": "background", "rationale": "Not foregrounded."},
            {"evidence_item_id": "claim:risk", "disposition": "background", "rationale": "Not foregrounded."},
        ],
    }

    report = build_analyst_decision_model_parse_report(payload, ledger)

    assert report["valid"] is True
    assert report["missing_accounting_ids"] == []
    assert report["obligation_omissions"]["ungrouped_quantitative_anchor_ids"] == ["claim:quantity"]
    assert report["obligation_omissions"]["ungrouped_counterweight_ids"] == ["claim:risk"]
    assert "quantitative_anchor_not_grouped" in report["issues"]
    assert "counterweight_not_grouped" in report["issues"]


def test_analyst_decision_model_parse_report_accepts_model_facing_retention_obligations() -> None:
    payload = {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": "Should option A be adopted?",
        "direct_answer": "Adopt option A.",
        "overall_rationale": "The model omitted the adjudicated crux.",
        "evidence_groups": [
            {
                "group_id": "support_group",
                "proposition": "Known evidence supports option A.",
                "memo_role": "load_bearing_primary_support",
                "covered_evidence_item_ids": ["bundle:one"],
                "rationale": "Known support.",
            },
        ],
        "evidence_dispositions": [{"evidence_item_id": "warning:two", "disposition": "background"}],
    }
    obligations = {
        "cruxes": [
            {"evidence_item_id": "warning:two", "claim": "This warning would change the answer."},
        ],
    }

    report = build_analyst_decision_model_parse_report(payload, _ledger(), retention_obligations=obligations)

    assert report["obligation_omissions"]["ungrouped_crux_ids"] == ["warning:two"]
    assert "crux_not_grouped" in report["issues"]
