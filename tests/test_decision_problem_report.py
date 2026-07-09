from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_decision_problem import (
    build_candidate_answer_set,
    build_decision_problem_report,
)

from test_decision_briefing_packet import _scaffold


def test_decision_problem_report_detects_facets_and_candidate_answers() -> None:
    question = (
        "For generally healthy adults, should eggs be treated as meaningfully harmful, "
        "neutral, or beneficial in dietary advice, especially with respect to cardiovascular risk?"
    )

    report = build_decision_problem_report(_scaffold(), question=question)
    answers = build_candidate_answer_set(_scaffold(), question=question)

    facets = {row["facet"] for row in report["facets"]}
    answer_ids = {row["candidate_answer_id"] for row in answers["candidate_answers"]}

    assert "empirical_effect_or_association" in facets
    assert "risk_assessment" in facets
    assert {"meaningfully_harmful", "neutral_or_not_meaningfully_harmful", "beneficial"} <= answer_ids
    assert report["schema_id"] == "decision_problem_report_v1"
    assert answers["schema_id"] == "candidate_answer_set_v1"


def test_decision_packet_embeds_report_only_decision_model_artifacts() -> None:
    result = build_decision_briefing_packet_bundle(
        _scaffold(),
        question="Should the city adopt option A for flood protection?",
    )
    packet = result["decision_briefing_packet"]

    assert result["decision_problem_report"]["schema_id"] == "decision_problem_report_v1"
    assert result["candidate_answer_set"]["schema_id"] == "candidate_answer_set_v1"
    assert packet["decision_problem_report"] == result["decision_problem_report"]
    assert packet["candidate_answer_set"] == result["candidate_answer_set"]
    assert packet["evidence_bundles"]
