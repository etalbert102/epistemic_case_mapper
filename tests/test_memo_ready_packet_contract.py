from __future__ import annotations

from epistemic_case_mapper.map_briefing_analytical_balance_contract import build_analytical_balance_contract
from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_memo_ready_finalization import build_memo_ready_packet_retention_report
from epistemic_case_mapper.map_briefing_memo_ready_packet import (
    build_memo_ready_packet_synthesis_prompt,
    build_quality_synthesis_packet_bundle,
)

from test_decision_briefing_packet import _scaffold


def test_memo_ready_packet_includes_general_decision_synthesis_contract() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    contract = packet["decision_synthesis_contract"]

    assert contract["schema_id"] == "decision_synthesis_contract_v1"
    assert "best-supported answer or action stance" in contract["stance_task"]
    assert "strongest evidence" in contract["counterweight_task"]
    assert "subgroups, contexts, or assumptions" in contract["scope_task"]
    assert contract["answer_spine_to_use"]
    assert contract["strongest_support_to_weigh"]
    assert contract["strongest_counterweights_to_weigh"]
    assert contract["quantitative_anchors_to_interpret"]
    assert "egg" not in str(contract).lower()


def test_memo_ready_synthesis_prompt_uses_contract_as_flexible_guidance() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    prompt = build_memo_ready_packet_synthesis_prompt(packet)

    assert "writer model context" in prompt
    assert "writer_model_context_v1" in prompt
    assert "The writer model context is the complete model-visible evidence and judgment record" in prompt
    assert "Weigh support against counterweights and scope boundaries" in prompt
    assert "quantity_anchors" in prompt


def test_memo_ready_prompt_without_evidence_items_does_not_dump_raw_packet() -> None:
    packet = {
        "decision_question": "Should option A be adopted?",
        "decision_synthesis_contract": {"schema_id": "decision_synthesis_contract_v1"},
        "memo_warning_packet": {"warnings": [{"claim": "Raw warning should not be dumped."}]},
    }

    prompt = build_memo_ready_packet_synthesis_prompt(packet)

    assert "synthesis prompt unavailable" in prompt
    assert "Raw warning should not be dumped" not in prompt
    assert "decision_synthesis_contract" not in prompt


def test_analytical_balance_contract_promotes_high_rank_counterweight_without_domain_terms() -> None:
    packet = _balance_packet()

    contract = build_analytical_balance_contract(packet)
    required = contract["required_balance_cards"]

    assert contract["schema_id"] == "analytical_balance_contract_v1"
    assert required[0]["role"] == "strongest_counterweight"
    assert required[0]["statement"] == "Option A increased serious implementation failures in one study."
    assert "RR 1.19" in required[0]["surface_numbers"]
    assert "egg" not in str(contract).lower()


def test_synthesis_prompt_exposes_analytical_balance_contract_as_source_ids() -> None:
    prompt = build_memo_ready_packet_synthesis_prompt(_balance_packet())

    assert "analytical_balance_contract" in prompt
    assert '"source_id": "risk_study"' in prompt
    assert "Risk Study" not in prompt
    assert "source_labels" not in prompt


def test_retention_warns_when_required_balance_counterweight_is_missing() -> None:
    report = build_memo_ready_packet_retention_report(
        "Support Study found Option A improved the main outcome by 20%.",
        _balance_packet(),
    )

    assert report["status"] == "warning"
    assert report["missing_analytical_balance_count"] == 1
    assert report["issues"][0]["issue_type"] == "missing_analytical_balance_card"
    assert report["issues"][0]["role"] == "strongest_counterweight"


def test_retention_accepts_required_balance_counterweight_when_weighed() -> None:
    memo = (
        "Support Study found Option A improved the main outcome by 20%. "
        "Risk Study is the main counterweight: Option A increased serious implementation failures, "
        "with RR 1.19, so this weakens and bounds the default answer."
    )

    report = build_memo_ready_packet_retention_report(memo, _balance_packet())

    assert report["status"] == "ready"
    assert report["missing_analytical_balance_count"] == 0


def _balance_packet() -> dict:
    return {
        "decision_question": "Should option A be adopted?",
        "answer_spine": {"default_read": "Option A is supported but bounded."},
        "source_trail": [
            {"source_id": "support_study", "source_label": "Support Study"},
            {"source_id": "risk_study", "source_label": "Risk Study"},
        ],
        "evidence_items": [
            {
                "item_id": "support",
                "must_use": True,
                "obligation_level": "must_include",
                "role": "strongest_support",
                "importance_rank": 1,
                "reader_claim": "Option A improved the main outcome.",
                "source_label": "Support Study",
                "source_labels": ["Support Study"],
                "quantities": [{"value": "20%", "interpretation": "main outcome improvement"}],
            },
            {
                "item_id": "counter",
                "must_use": False,
                "obligation_level": "should_include",
                "role": "strongest_counterweight",
                "answer_relation": "challenges_answer",
                "memo_function": "counterweight",
                "importance_rank": 2,
                "reader_claim": "Option A increased serious implementation failures in one study.",
                "decision_relevance": "Provides a challenge estimate, RR 1.19, that may bound adoption.",
                "source_label": "Risk Study",
                "source_labels": ["Risk Study"],
            },
            {
                "item_id": "minor_context",
                "must_use": False,
                "obligation_level": "should_include",
                "role": "context_only",
                "importance_rank": 80,
                "reader_claim": "Option A has a long implementation history.",
                "source_label": "Support Study",
                "source_labels": ["Support Study"],
            },
        ],
    }
