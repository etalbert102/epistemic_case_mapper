from __future__ import annotations

import pytest
from pydantic import ValidationError

from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication_v2 import (
    AnalystAdjudicationResponseV2,
    EvidenceAdjudicationResponseRowV2,
    analyst_adjudication_response_schema_v2,
    build_analyst_adjudication_prompt_v2,
)


def _ledger() -> dict:
    return {
        "decision_question": "Should option A be adopted?",
        "stable_final_answer_frame": {
            "answer_status": "provisional",
            "current_best_answer": "Adopt option A when cost exposure is bounded.",
        },
        "rows": [
            {
                "evidence_item_id": "bundle:one",
                "input_kind": "retained_bundle",
                "current_role": "strongest_support",
                "current_priority": 4,
                "source_ids": ["s1"],
                "quantity_values": ["12%"],
                "claim": "Option A reduced losses by 12%.",
                "source_bottom_lines": [
                    {
                        "source_id": "s1",
                        "source_bottom_line": "Option A reduced downstream losses.",
                        "polarity_signal": "benefit_signal",
                    }
                ],
                "source_bottom_line_signals": ["benefit_signal"],
            }
        ],
    }


def test_v2_response_row_has_five_required_and_two_optional_fields() -> None:
    schema = analyst_adjudication_response_schema_v2()
    row_schema = schema["$defs"]["EvidenceAdjudicationResponseRowV2"]

    assert set(EvidenceAdjudicationResponseRowV2.model_fields) == {
        "evidence_item_id",
        "memo_use",
        "answer_relation",
        "priority",
        "reason",
        "guardrail",
        "target_answer_option",
    }
    assert set(row_schema["required"]) == {
        "evidence_item_id",
        "memo_use",
        "answer_relation",
        "priority",
        "reason",
    }
    assert "covered_by_group" not in str(schema)


def test_v2_response_rejects_duplicate_ids_and_extra_fields() -> None:
    row = {
        "evidence_item_id": "bundle:one",
        "memo_use": "load_bearing_primary_support",
        "answer_relation": "supports_answer",
        "priority": "core",
        "reason": "Direct outcome evidence.",
    }
    with pytest.raises(ValidationError, match="unique"):
        AnalystAdjudicationResponseV2.model_validate({"rows": [row, row]})
    with pytest.raises(ValidationError, match="extra_forbidden"):
        AnalystAdjudicationResponseV2.model_validate({"rows": [{**row, "source_ids": ["s1"]}]})


def test_v2_prompt_is_compact_but_preserves_decision_and_source_context() -> None:
    prompt = build_analyst_adjudication_prompt_v2(_ledger())

    assert "bundle:one" in prompt
    assert "current_best_answer" in prompt
    assert "Option A reduced downstream losses" in prompt
    assert "benefit_signal" in prompt
    assert '"priority"' in prompt
    assert '"guardrail"' in prompt
    assert "decision_contribution" not in prompt
    assert "quantity_takeaway" not in prompt
    assert "source_weight_note" not in prompt
    assert "if_omitted" not in prompt
