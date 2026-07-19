from __future__ import annotations

from typing import Any


def build_decision_obligation_graph(
    *,
    question: str,
    decision_problem_report: dict[str, Any],
    candidate_answer_set: dict[str, Any],
    source_evidence_graph: dict[str, Any],
) -> dict[str, Any]:
    obligations: list[dict[str, Any]] = []
    answers = _candidate_answers(candidate_answer_set)
    facets = [str(row.get("facet")) for row in decision_problem_report.get("facets", []) if isinstance(row, dict)]
    quantity_nodes = _nodes_of_type(source_evidence_graph, "quantity")
    quality_unknown = _quality_unknown_nodes(source_evidence_graph)
    scope_available = _has_scope_signal(source_evidence_graph, facets)
    for answer in answers:
        answer_id = str(answer.get("candidate_answer_id", "")).strip()
        if not answer_id:
            continue
        obligations.append(
            _obligation(
                len(obligations) + 1,
                "answer_support",
                candidate_answer_ids=[answer_id],
                rationale=f"Represent evidence bearing on candidate answer: {answer.get('label', answer_id)}.",
                expected_evidence_features=["source_grounded_claim", "directionality"],
            )
        )
        obligations.append(
            _obligation(
                len(obligations) + 1,
                "counterevidence",
                candidate_answer_ids=[answer_id],
                rationale=f"Represent evidence that challenges or limits candidate answer: {answer.get('label', answer_id)}.",
                expected_evidence_features=["source_grounded_claim", "challenge_or_limit"],
            )
        )
    if quantity_nodes:
        obligations.append(
            _obligation(
                len(obligations) + 1,
                "quantitative_anchor",
                evidence_node_ids=[node["node_id"] for node in quantity_nodes[:12]],
                rationale="Preserve exact quantitative anchors that may carry the decision read.",
                expected_evidence_features=["exact_quantity", "source_lineage", "claim_linkage"],
                requiredness="required_if_available",
            )
        )
    if scope_available:
        obligations.append(
            _obligation(
                len(obligations) + 1,
                "scope_boundary",
                rationale="Represent population, dose, comparator, endpoint, or applicability boundaries.",
                expected_evidence_features=["scope_or_limit", "affected_candidate_answer"],
                requiredness="required_if_available",
            )
        )
    if quality_unknown:
        obligations.append(
            _obligation(
                len(obligations) + 1,
                "source_quality_caution",
                evidence_node_ids=[node["node_id"] for node in quality_unknown[:20]],
                rationale="Name evidence-quality uncertainty instead of treating unknown quality as strong evidence.",
                expected_evidence_features=["quality_status", "source_lineage"],
                requiredness="warn_if_missing",
            )
        )
    if not obligations:
        obligations.append(
            _obligation(
                1,
                "named_gap",
                rationale="No grounded obligations could be inferred from the current question and source graph.",
                expected_evidence_features=["gap_statement"],
                requiredness="required",
            )
        )
    return {
        "schema_id": "decision_obligation_graph_v1",
        "method": "deterministic_candidate_answer_source_graph_obligation_seed_report_only",
        "decision_question": question,
        "obligations": obligations,
        "obligation_count": len(obligations),
        "candidate_answer_ids": [str(answer.get("candidate_answer_id")) for answer in answers if answer.get("candidate_answer_id")],
        "warnings": _warnings(obligations, answers),
    }


def _obligation(
    index: int,
    obligation_type: str,
    *,
    rationale: str,
    expected_evidence_features: list[str],
    candidate_answer_ids: list[str] | None = None,
    evidence_node_ids: list[str] | None = None,
    requiredness: str = "required",
) -> dict[str, Any]:
    return {
        "obligation_id": f"obl_{index:03d}",
        "obligation_type": obligation_type,
        "requiredness": requiredness,
        "candidate_answer_ids": candidate_answer_ids or [],
        "evidence_node_ids": evidence_node_ids or [],
        "rationale": rationale,
        "expected_evidence_features": expected_evidence_features,
        "status": "report_only",
    }


def _candidate_answers(candidate_answer_set: dict[str, Any]) -> list[dict[str, Any]]:
    rows = candidate_answer_set.get("candidate_answers", []) if isinstance(candidate_answer_set.get("candidate_answers"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _nodes_of_type(graph: dict[str, Any], node_type: str) -> list[dict[str, Any]]:
    return [node for node in graph.get("nodes", []) if isinstance(node, dict) and node.get("node_type") == node_type]


def _quality_unknown_nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        node
        for node in graph.get("nodes", [])
        if isinstance(node, dict)
        and node.get("node_type") in {"claim", "source_card", "quantity_card"}
        and str(node.get("quality", "unknown")).lower() in {"", "unknown", "not_assessed_in_minimal_slice"}
    ]


def _has_scope_signal(graph: dict[str, Any], facets: list[str]) -> bool:
    if "risk_assessment" in facets or "empirical_effect_or_association" in facets:
        return True
    for node in graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else []:
        text = " ".join(str(node.get(key, "")) for key in ("claim", "excerpt", "context", "role")).lower()
        if any(term in text for term in ("scope", "boundary", "limit", "population", "subgroup", "dose", "comparator")):
            return True
    return False


def _warnings(obligations: list[dict[str, Any]], answers: list[dict[str, Any]]) -> list[str]:
    warnings = []
    if not answers:
        warnings.append("no_candidate_answers")
    if not any(row.get("obligation_type") == "quantitative_anchor" for row in obligations):
        warnings.append("no_quantitative_obligation")
    return warnings
