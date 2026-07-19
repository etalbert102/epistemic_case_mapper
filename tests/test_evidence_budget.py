from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_evidence_budget import build_evidence_budget_bundle


def test_evidence_budget_accounts_for_foreground_background_and_sources() -> None:
    ledger = {
        "decision_question": "Should option A be preferred?",
        "rows": [
            {"evidence_item_id": "claim:support", "source_ids": ["src001"], "quantity_values": ["20 percent"]},
            {"evidence_item_id": "claim:context", "source_ids": ["src002"], "quantity_values": []},
            {"evidence_item_id": "claim:off_question", "source_ids": ["src003"], "quantity_values": []},
        ],
    }
    model = {
        "schema_id": "analyst_decision_model_v2",
        "decision_question": "Should option A be preferred?",
        "active_evidence_universe": {
            "full_reasoning_evidence_item_ids": ["claim:support", "claim:context"],
            "routed_away_evidence_item_ids": ["claim:off_question"],
            "source_ids": ["src001", "src002"],
        },
        "evidence_groups": [
            {
                "group_id": "support",
                "memo_role": "load_bearing_primary_support",
                "covered_evidence_item_ids": ["claim:support"],
                "rationale": "It drives the answer.",
            }
        ],
        "evidence_dispositions": [
            {"evidence_item_id": "claim:support", "disposition": "foreground", "group_id": "support"},
            {"evidence_item_id": "claim:context", "disposition": "background", "group_id": ""},
            {"evidence_item_id": "claim:off_question", "disposition": "not_decision_relevant", "group_id": ""},
        ],
    }

    bundle = build_evidence_budget_bundle(analyst_decision_model=model, ledger=ledger)

    assert bundle["evidence_accounting_report"]["status"] == "ready"
    assert bundle["foreground_evidence_report"]["foreground_evidence_item_ids"] == ["claim:support"]
    assert bundle["evidence_budget"]["appendix_or_background_evidence_item_ids"] == ["claim:context"]
    assert bundle["evidence_universe"]["active_source_ids"] == ["src001", "src002"]
    assert bundle["evidence_universe"]["omitted_source_ids"] == ["src003"]
    assert bundle["active_cited_source_report"]["foreground_source_ids"] == ["src001"]
