from __future__ import annotations

import pytest
from pydantic import ValidationError

from epistemic_case_mapper.map_briefing_analyst_schemas import (
    AnalystAdjudication,
    AnalystAnswerFrame,
    AnalystSynthesisPacket,
    build_analyst_adjudication_parse_report,
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
    assert report["status"] == "ready"
    assert report["valid"] is True


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
