from __future__ import annotations

import pytest
from pydantic import ValidationError

from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_adjudication_v2 import (
    AnalystAdjudicationResponseV2,
    EvidenceAdjudicationResponseRowV2,
    adapt_analyst_adjudication_v2,
    analyst_adjudication_response_schema_v2,
    build_analyst_adjudication_prompt_v2,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_schemas import AnalystAdjudication


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
    assert "primary support/supports only when the row strengthens" in prompt
    assert "scope_or_applicability/bounds_scope" in prompt
    assert "Option A reduced downstream losses" in prompt
    assert "benefit_signal" in prompt
    assert '"priority"' in prompt
    assert '"guardrail"' in prompt
    assert "decision_contribution" not in prompt
    assert "quantity_takeaway" not in prompt
    assert "source_weight_note" not in prompt
    assert "if_omitted" not in prompt


def test_v2_adapter_restores_ledger_owned_fields_and_legacy_surface() -> None:
    ledger = _ledger()
    compact = {
        "rows": [
            {
                "evidence_item_id": "bundle:one",
                "memo_use": "load_bearing_primary_support",
                "answer_relation": "supports_answer",
                "priority": "core",
                "reason": "Direct outcome evidence changes the answer.",
                "guardrail": "Keep the bounded-cost condition.",
            }
        ]
    }

    canonical = adapt_analyst_adjudication_v2(compact, ledger)
    parsed = AnalystAdjudication.model_validate(canonical)
    row = parsed.rows[0]

    assert canonical["schema_id"] == "analyst_adjudication_v1"
    assert row.source_ids == ["s1"]
    assert row.quantity_values == ["12%"]
    assert row.effect_on_final_answer == "supports current_best_answer"
    assert row.rationale == row.decision_contribution == "Direct outcome evidence changes the answer."
    assert row.key_qualifier == row.misuse_warning == "Keep the bounded-cost condition."


def test_v2_adapter_assigns_global_rank_independent_of_response_order() -> None:
    ledger = _ledger()
    ledger["rows"] = [
        {**ledger["rows"][0], "evidence_item_id": "later-core", "current_priority": 9},
        {**ledger["rows"][0], "evidence_item_id": "context", "current_priority": 1},
        {**ledger["rows"][0], "evidence_item_id": "earlier-core", "current_priority": 2},
    ]
    rows = [
        {
            "evidence_item_id": "context",
            "memo_use": "mechanism_or_context",
            "answer_relation": "contextualizes_answer",
            "priority": "context",
            "reason": "Context only.",
        },
        {
            "evidence_item_id": "later-core",
            "memo_use": "load_bearing_primary_support",
            "answer_relation": "supports_answer",
            "priority": "core",
            "reason": "Core but lower ledger priority.",
        },
        {
            "evidence_item_id": "earlier-core",
            "memo_use": "load_bearing_counterweight",
            "answer_relation": "challenges_answer",
            "priority": "core",
            "reason": "Core and higher ledger priority.",
        },
    ]

    first = adapt_analyst_adjudication_v2({"rows": rows}, ledger)
    second = adapt_analyst_adjudication_v2({"rows": list(reversed(rows))}, ledger)

    first_ranks = {row["evidence_item_id"]: row["importance_rank"] for row in first["rows"]}
    second_ranks = {row["evidence_item_id"]: row["importance_rank"] for row in second["rows"]}
    assert first_ranks == second_ranks == {"later-core": 2, "context": 3, "earlier-core": 1}


def test_v2_adapter_rejects_missing_and_unknown_ids() -> None:
    compact = {
        "rows": [
            {
                "evidence_item_id": "unknown",
                "memo_use": "background_only",
                "answer_relation": "uncertain_relation",
                "priority": "context",
                "reason": "Unknown fixture row.",
            }
        ]
    }

    with pytest.raises(ValueError, match="missing_evidence_item_ids=.*bundle:one.*unknown_evidence_item_ids=.*unknown"):
        adapt_analyst_adjudication_v2(compact, _ledger())
