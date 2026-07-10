from __future__ import annotations

from epistemic_case_mapper.map_briefing_analyst_evidence_ledger import build_analyst_map_evidence_ledger
from epistemic_case_mapper.model_backends import ModelBackendResult
from epistemic_case_mapper.staged_semantic_decision_edges import (
    ROLE_BACKGROUND,
    ROLE_COMPARATOR,
    ROLE_MECHANISM,
    ROLE_OUTCOME,
    ROLE_SCOPE,
    build_decision_edge_relation_inputs,
    decision_edge_quality_report,
    prepare_claim_decision_edge_roles,
    infer_decision_edge_role,
    low_confidence_decision_edge_reason,
    propose_decision_edge_candidates,
)
from epistemic_case_mapper.staged_semantic_relation_backfill import finalize_sparse_relation_graph
from types import SimpleNamespace


def test_decision_edge_role_inference_is_structural_not_extraction_role_bound() -> None:
    outcome = _claim("c001", "The intervention was not associated with higher hospitalization risk.", importance="critical")
    mechanism = _claim("c002", "The intervention increased a biomarker that may be a surrogate marker of harm.")
    scope = _claim("c003", "The finding applies only to adults in the target population.")
    comparator = _claim("c004", "Replacing the intervention with the alternative was associated with higher risk.")
    background = _claim("c005", "The source provides historical context.", default_use="appendix", relevance="background")

    assert infer_decision_edge_role(outcome)[0] == ROLE_OUTCOME
    assert infer_decision_edge_role(mechanism)[0] == ROLE_MECHANISM
    assert infer_decision_edge_role(scope)[0] == ROLE_SCOPE
    assert infer_decision_edge_role(comparator)[0] == ROLE_COMPARATOR
    assert infer_decision_edge_role(background)[0] == ROLE_BACKGROUND


def test_decision_edge_candidates_prioritize_decision_contracts_and_drop_background() -> None:
    claims = [
        _claim("c001", "Moderate exposure was not associated with cardiovascular events.", importance="critical"),
        _claim("c002", "Higher exposure was associated with increased cardiovascular events.", importance="critical"),
        _claim("c003", "The finding applies only to the high-risk subgroup."),
        _claim("c004", "The exposure increased a biomarker that may proxy long-term harm."),
        _claim("c005", "Appendix-only history of the field.", default_use="appendix", relevance="background"),
    ]

    pairs, report = propose_decision_edge_candidates(claims, max_pairs=4)
    endpoint_ids = {packet[side]["claim_id"] for packet in pairs for side in ("left", "right")}
    contracts = {packet["decision_edge_contract"] for packet in pairs}

    assert "c005" not in endpoint_ids
    assert "outcome_disagreement" in contracts
    assert {"scope_bounds_outcome", "mechanism_to_outcome"} & contracts
    assert report["selected_pair_count"] <= 4
    assert report["eligible_role_counts"].get(ROLE_BACKGROUND, 0) == 0


def test_decision_edge_relation_inputs_cap_model_pair_budget() -> None:
    claims = [
        _claim(f"c{index:03d}", f"Finding {index} was associated with the decision-relevant outcome.", importance="high")
        for index in range(40)
    ]

    pairs, role_report, candidate_report = build_decision_edge_relation_inputs(claims, requested_max_pairs=48)

    assert len(pairs) <= 18
    assert role_report["claim_count"] == 40
    assert candidate_report["effective_max_pairs"] == 18


def test_decision_edge_candidates_respect_prepared_model_roles() -> None:
    claims = [
        {**_claim("c001", "Use of the intervention was associated with lower hospitalization risk."), "decision_edge_role": ROLE_OUTCOME, "decision_edge_role_confidence": "high"},
        {**_claim("c002", "The same sentence mentions replacement by an alternative."), "decision_edge_role": ROLE_COMPARATOR, "decision_edge_role_confidence": "high"},
    ]

    pairs, report = propose_decision_edge_candidates(claims, max_pairs=4)

    assert pairs
    assert pairs[0]["decision_edge_contract"] == "comparator_contextualizes_outcome"
    assert report["eligible_role_counts"][ROLE_COMPARATOR] == 1


def test_model_role_prep_uses_valid_model_roles_and_reports_disagreement() -> None:
    claims = [
        _claim("c001", "The study population included only high-risk adults."),
        _claim("c002", "Changing the comparator changed the interpretation of risk."),
        _claim("c003", "The intervention was associated with lower cardiovascular events."),
    ]

    def fake_backend(*_args, **_kwargs) -> ModelBackendResult:
        return ModelBackendResult(
            text='{"roles": ['
            '{"claim_id": "c001", "decision_edge_role": "scope_or_subgroup_boundary", "role_confidence": "high", "rationale": "Population boundary."},'
            '{"claim_id": "c002", "decision_edge_role": "comparator_or_substitution", "role_confidence": "medium", "rationale": "Comparator changes interpretation."},'
            '{"claim_id": "c003", "decision_edge_role": "mechanism_or_biomarker", "role_confidence": "high", "rationale": "The model treats this as mechanistic prep."},'
            '{"claim_id": "c999", "decision_edge_role": "not_a_role", "role_confidence": "high", "rationale": "Invalid."}'
            "]}",
            backend="command:fake",
        )

    prepared, report = prepare_claim_decision_edge_roles(
        claims,
        backend="command:fake",
        backend_timeout=5,
        backend_retries=0,
        decision_question="What should we recommend?",
        run_backend=fake_backend,
    )

    by_id = {claim["claim_id"]: claim for claim in prepared}
    assert by_id["c001"]["decision_edge_role"] == ROLE_SCOPE
    assert by_id["c001"]["decision_edge_role_source"] == "model"
    assert by_id["c002"]["decision_edge_role"] == ROLE_COMPARATOR
    assert by_id["c003"]["decision_edge_role"] == ROLE_MECHANISM
    assert by_id["c003"]["decision_edge_role_source"] == "model"
    assert report["accepted_model_role_count"] == 3
    assert report["fallback_claim_count"] == 0
    assert {row["reason"] for row in report["invalid_model_rows"]} == {"unknown_claim_id"}
    assert report["model_deterministic_disagreements"]


def test_model_role_prep_skips_prompt_backend() -> None:
    claims = [_claim("c001", "The intervention was associated with lower cardiovascular events.")]

    prepared, report = prepare_claim_decision_edge_roles(
        claims,
        backend="prompt",
        backend_timeout=5,
        backend_retries=0,
        decision_question="What should we recommend?",
    )

    assert prepared[0]["decision_edge_role_source"] == "deterministic_fallback"
    assert report["status"] == "skipped_prompt_backend"


def test_low_confidence_decision_edges_are_warning_only_not_accepted() -> None:
    relation = {
        "relation_confidence": "low",
        "relation_contract": {"why_decision_relevant": "It changes the scope."},
    }
    packet = {"decision_edge_contract": "scope_bounds_outcome"}

    assert low_confidence_decision_edge_reason(relation, packet) == "low_confidence_decision_edge"


def test_decision_edge_quality_report_records_accepted_and_rejected_edges() -> None:
    packet = {
        "pair_id": "pair_001",
        "decision_edge_contract": "outcome_disagreement",
        "left": {"claim_id": "c001"},
        "right": {"claim_id": "c002"},
    }
    accepted = [
        {
            "relation_id": "r001",
            "relation_type": "in_tension_with",
            "relation_confidence": "medium",
            "source_claim": "c001",
            "target_claim": "c002",
            "candidate_pair": {"pair_id": "pair_001"},
            "relation_contract": {"why_decision_relevant": "It is the central tension."},
        }
    ]

    report = decision_edge_quality_report(pair_packets=[packet], accepted=accepted, rejected=[{"reason": "no_relation"}])

    assert report["accepted_relation_count"] == 1
    assert report["accepted_edges"][0]["decision_edge_contract"] == "outcome_disagreement"
    assert report["rejection_reason_counts"] == {"no_relation": 1}


def test_sparse_relation_finalize_can_disable_deterministic_backfill() -> None:
    accepted, rejected, relation_index = finalize_sparse_relation_graph(
        accepted=[],
        rejected=[],
        pair_packets=[
            {
                "pair_id": "pair_001",
                "left": {"claim_id": "c001", "claim": "A finding was associated with lower risk."},
                "right": {"claim_id": "c002", "claim": "A finding was associated with higher risk."},
                "candidate_score": 10,
            }
        ],
        permitted_types={"in_tension_with", "supports"},
        region=SimpleNamespace(id_prefix="demo"),
        relation_index=1,
        seen=set(),
        allow_deterministic_fallback=False,
    )

    assert accepted == []
    assert rejected == []
    assert relation_index == 1


def test_analyst_ledger_exposes_accepted_relations_as_decision_edge_rows() -> None:
    candidate_map = {
        "claims": [
            _claim("c001", "Moderate exposure was not associated with cardiovascular events.", source_id="s1"),
            _claim("c002", "Higher exposure was associated with increased cardiovascular events.", source_id="s2"),
        ],
        "relations": [
            {
                "relation_id": "r001",
                "source_claim": "c001",
                "target_claim": "c002",
                "relation_type": "in_tension_with",
                "rationale": "The findings point in different directions for the same outcome.",
                "relation_confidence": "medium",
                "relation_contract": {
                    "why_decision_relevant": "This is the core evidence conflict.",
                    "failure_condition": "The populations are not comparable.",
                },
            }
        ],
    }

    ledger = build_analyst_map_evidence_ledger(candidate_map, {"source_display_names": {"s1": "Source 1", "s2": "Source 2"}}, question="What should we do?")
    relation_rows = [row for row in ledger["rows"] if row.get("input_kind") == "candidate_decision_edge"]

    assert len(relation_rows) == 1
    assert relation_rows[0]["relation_id"] == "r001"
    assert relation_rows[0]["current_role"] == "load_bearing_counterweight"
    assert "core evidence conflict" in relation_rows[0]["why_it_matters"]


def _claim(
    claim_id: str,
    claim: str,
    *,
    source_id: str = "source",
    importance: str = "high",
    default_use: str = "main_map",
    relevance: str = "direct",
) -> dict[str, object]:
    return {
        "claim_id": claim_id,
        "claim": claim,
        "source_id": source_id,
        "source_span": "lines 1-1",
        "excerpt": claim,
        "source_quote": claim,
        "entailed_by_excerpt": "yes",
        "role": "source_claim",
        "decision_importance_level": importance,
        "default_use": default_use,
        "question_relevance": relevance,
    }
