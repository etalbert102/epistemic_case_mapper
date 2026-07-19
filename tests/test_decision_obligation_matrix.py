from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_obligations import build_decision_obligation_graph
from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_problem import (
    build_candidate_answer_set,
    build_decision_problem_report,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_evidence_answer_matrix import build_evidence_answer_matrix
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_evidence_graph import build_source_evidence_graph

from test_decision_briefing_packet import _scaffold


def test_decision_obligation_graph_seeds_answer_quantity_and_quality_obligations() -> None:
    scaffold = _scaffold()
    question = "Should the city adopt option A for flood protection?"
    problem = build_decision_problem_report(scaffold, question=question)
    answers = build_candidate_answer_set(scaffold, question=question)
    source_graph = build_source_evidence_graph(scaffold)

    graph = build_decision_obligation_graph(
        question=question,
        decision_problem_report=problem,
        candidate_answer_set=answers,
        source_evidence_graph=source_graph,
    )
    obligation_types = {row["obligation_type"] for row in graph["obligations"]}

    assert graph["schema_id"] == "decision_obligation_graph_v1"
    assert {"answer_support", "counterevidence", "quantitative_anchor", "source_quality_caution"} <= obligation_types
    assert all(row["obligation_id"].startswith("obl_") for row in graph["obligations"])


def test_evidence_answer_matrix_preserves_role_quality_and_quantity_fields() -> None:
    scaffold = _scaffold()
    question = "Should the city adopt option A for flood protection?"
    problem = build_decision_problem_report(scaffold, question=question)
    answers = build_candidate_answer_set(scaffold, question=question)
    source_graph = build_source_evidence_graph(scaffold)
    obligations = build_decision_obligation_graph(
        question=question,
        decision_problem_report=problem,
        candidate_answer_set=answers,
        source_evidence_graph=source_graph,
    )

    matrix = build_evidence_answer_matrix(
        candidate_answer_set=answers,
        decision_obligation_graph=obligations,
        source_evidence_graph=source_graph,
    )
    quantity_rows = [row for row in matrix["rows"] if row["evidence_role"] == "quantitative_anchor"]

    assert matrix["schema_id"] == "evidence_answer_matrix_v1"
    assert matrix["quality_report"]["salience_strength_quality_separated"] is True
    assert quantity_rows
    assert any("25%" in row.get("quantity_values", []) for row in quantity_rows)
    assert all("salience" in row and "evidential_strength" in row and "evidence_quality" in row and "uncertainty" in row for row in matrix["rows"])


def test_decision_packet_embeds_obligation_graph_and_evidence_answer_matrix() -> None:
    result = build_decision_briefing_packet_bundle(
        _scaffold(),
        question="Should the city adopt option A for flood protection?",
    )
    packet = result["decision_briefing_packet"]

    assert result["decision_obligation_graph"]["schema_id"] == "decision_obligation_graph_v1"
    assert result["evidence_answer_matrix"]["schema_id"] == "evidence_answer_matrix_v1"
    assert result["evidence_answer_matrix_quality_report"]["schema_id"] == "evidence_answer_matrix_quality_report_v1"
    assert packet["decision_obligation_graph"] == result["decision_obligation_graph"]
    assert packet["evidence_answer_matrix"] == result["evidence_answer_matrix"]
    assert packet["evidence_answer_matrix_quality_report"] == result["evidence_answer_matrix_quality_report"]
