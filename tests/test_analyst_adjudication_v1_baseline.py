from __future__ import annotations

import json
from pathlib import Path

from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_evidence_routing import (
    build_analyst_evidence_routing_bundle,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_schemas import (
    AnalystAdjudication,
    EvidenceAdjudicationRow,
    build_analyst_adjudication_parse_report,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_faithfulness import (
    repair_adjudication_source_faithfulness,
)


FIXTURE = Path(__file__).parent / "fixtures" / "analyst_adjudication" / "v1_baseline.json"


def _baseline() -> tuple[dict, dict]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return payload["ledger"], payload["adjudication"]


def test_v1_baseline_freezes_model_facing_row_surface() -> None:
    assert set(EvidenceAdjudicationRow.model_fields) == {
        "evidence_item_id",
        "memo_use",
        "importance_rank",
        "rationale",
        "answer_relation",
        "covered_by",
        "source_ids",
        "quantity_values",
        "target_answer_option",
        "effect_on_final_answer",
        "tension_type",
        "downgrade_reason",
        "decision_contribution",
        "use_in_reasoning",
        "key_qualifier",
        "quantity_takeaway",
        "source_weight_note",
        "misuse_warning",
        "if_omitted",
    }


def test_v1_baseline_covers_ledger_and_preserves_routing_behavior() -> None:
    ledger, adjudication = _baseline()
    parsed = AnalystAdjudication.model_validate(adjudication).model_dump()
    report = build_analyst_adjudication_parse_report(parsed, ledger)

    assert report["valid"] is True
    assert report["row_count"] == report["ledger_row_count"] == 3

    routing = build_analyst_evidence_routing_bundle(
        ledger=ledger,
        adjudication=parsed,
        adjudication_report={"status": "accepted", "accepted": True},
        adjudication_parse_report=report,
    )["analyst_evidence_routing"]
    routes = {row["evidence_item_id"]: row["route"] for row in routing["rows"]}
    assert routes == {
        "bundle:support": "full_decision_model",
        "warning:risk": "full_decision_model",
        "context:mechanism": "compact_context",
    }


def test_v1_baseline_repairs_source_polarity_conflict() -> None:
    ledger, adjudication = _baseline()
    repaired, report = repair_adjudication_source_faithfulness(ledger, adjudication)
    rows = {row["evidence_item_id"]: row for row in repaired["rows"]}

    assert report["status"] == "repaired"
    assert report["warning_count_before"] == 1
    assert report["warning_count_after"] == 0
    assert rows["warning:risk"]["memo_use"] == "load_bearing_counterweight"
    assert rows["warning:risk"]["answer_relation"] == "challenges_answer"
