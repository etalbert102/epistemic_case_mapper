from __future__ import annotations

from typing import Any


def build_evidence_answer_matrix(
    *,
    candidate_answer_set: dict[str, Any],
    decision_obligation_graph: dict[str, Any],
    source_evidence_graph: dict[str, Any],
) -> dict[str, Any]:
    answers = _candidate_answers(candidate_answer_set)
    obligations = _obligations(decision_obligation_graph)
    rows: list[dict[str, Any]] = []
    evidence_nodes = [
        node
        for node in source_evidence_graph.get("nodes", [])
        if isinstance(node, dict) and node.get("node_type") in {"claim", "quantity", "quantity_card", "source_bottom_line"}
    ]
    for node in evidence_nodes:
        for answer in _matched_answers(node, answers):
            rows.append(_matrix_row(len(rows) + 1, node, answer, obligations))
    return {
        "schema_id": "evidence_answer_matrix_v1",
        "method": "deterministic_source_graph_to_candidate_answer_matrix_report_only",
        "rows": rows,
        "row_count": len(rows),
        "candidate_answer_ids": [str(answer.get("candidate_answer_id")) for answer in answers if answer.get("candidate_answer_id")],
        "quality_report": _quality_report(rows),
        "warnings": _warnings(rows, answers, evidence_nodes),
    }


def _matrix_row(index: int, node: dict[str, Any], answer: dict[str, Any], obligations: list[dict[str, Any]]) -> dict[str, Any]:
    role, basis = _role_for_node_answer(node, answer)
    obligation_ids = _obligation_ids(role, answer, obligations)
    quality = _quality_label(node)
    return {
        "matrix_row_id": f"eam_{index:04d}",
        "evidence_node_id": node.get("node_id"),
        "evidence_node_type": node.get("node_type"),
        "candidate_answer_id": answer.get("candidate_answer_id"),
        "obligation_ids": obligation_ids,
        "evidence_role": role,
        "role_basis": basis,
        "directionality": _directionality(role),
        "salience": _salience(node),
        "evidential_strength": _strength(node, quality),
        "evidence_quality": quality,
        "uncertainty": _uncertainty(node, quality),
        "quantity_values": _quantity_values(node),
        "source_ids": _string_list(node.get("source_ids")),
        "source_labels": _string_list(node.get("source_labels")),
        "claim_ids": _string_list(node.get("claim_id")) + _string_list(node.get("claim_ids")),
        "summary": _summary_text(node),
        "status": "report_only",
    }


def _matched_answers(node: dict[str, Any], answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not answers:
        return []
    text = _node_text(node)
    matched = []
    for answer in answers:
        answer_id = str(answer.get("candidate_answer_id", ""))
        stance = str(answer.get("stance", ""))
        if answer_id in {"subgroup_or_scope_dependent", "depends_on_comparator"} and _has_scope_text(text):
            matched.append(answer)
        elif answer_id == "meaningfully_harmful" and any(term in text for term in ("increase", "higher", "harm", "risk")):
            matched.append(answer)
        elif answer_id == "beneficial" and any(term in text for term in ("benefit", "protective", "lower", "inverse")):
            matched.append(answer)
        elif answer_id == "neutral_or_not_meaningfully_harmful" and any(term in text for term in ("not associated", "neutral", "no evidence", "not increased")):
            matched.append(answer)
        elif stance in {"supports_proposition", "challenges_proposition", "uncertain"}:
            matched.append(answer)
    return matched[:3] or answers[:1]


def _role_for_node_answer(node: dict[str, Any], answer: dict[str, Any]) -> tuple[str, str]:
    text = _node_text(node)
    answer_id = str(answer.get("candidate_answer_id", ""))
    if node.get("node_type") in {"quantity", "quantity_card"}:
        return "quantitative_anchor", "node_type_quantity"
    if answer_id in {"subgroup_or_scope_dependent", "depends_on_comparator"} and _has_scope_text(text):
        return "scope_boundary", "candidate_answer_scope_match"
    if any(term in text for term in ("failed", "however", "except", "higher", "increase", "risk")) and answer_id in {
        "neutral_or_not_meaningfully_harmful",
        "beneficial",
        "yes_or_favor",
    }:
        return "counterevidence", "textual_challenge_signal"
    return "answer_support", "deterministic_text_answer_match"


def _obligation_ids(role: str, answer: dict[str, Any], obligations: list[dict[str, Any]]) -> list[str]:
    answer_id = str(answer.get("candidate_answer_id", ""))
    role_to_obligation = {
        "answer_support": "answer_support",
        "counterevidence": "counterevidence",
        "quantitative_anchor": "quantitative_anchor",
        "scope_boundary": "scope_boundary",
    }
    target_type = role_to_obligation.get(role)
    ids = []
    for obligation in obligations:
        if target_type and obligation.get("obligation_type") != target_type:
            continue
        candidate_ids = _string_list(obligation.get("candidate_answer_ids"))
        if candidate_ids and answer_id not in candidate_ids:
            continue
        ids.append(str(obligation.get("obligation_id")))
    return [item for item in ids if item][:6]


def _quality_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    unknown = [row for row in rows if row.get("evidence_quality") == "unknown"]
    return {
        "schema_id": "evidence_answer_matrix_quality_report_v1",
        "row_count": len(rows),
        "quality_unknown_count": len(unknown),
        "quality_unknown_row_ids": [str(row.get("matrix_row_id")) for row in unknown[:20]],
        "salience_strength_quality_separated": True,
    }


def _warnings(rows: list[dict[str, Any]], answers: list[dict[str, Any]], evidence_nodes: list[dict[str, Any]]) -> list[str]:
    warnings = []
    if answers and not rows:
        warnings.append("no_matrix_rows")
    if evidence_nodes and not rows:
        warnings.append("evidence_nodes_unmapped")
    if any(row.get("evidence_quality") == "unknown" for row in rows):
        warnings.append("evidence_quality_unknown")
    return warnings


def _candidate_answers(candidate_answer_set: dict[str, Any]) -> list[dict[str, Any]]:
    rows = candidate_answer_set.get("candidate_answers", []) if isinstance(candidate_answer_set.get("candidate_answers"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _obligations(decision_obligation_graph: dict[str, Any]) -> list[dict[str, Any]]:
    rows = decision_obligation_graph.get("obligations", []) if isinstance(decision_obligation_graph.get("obligations"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _quality_label(node: dict[str, Any]) -> str:
    quality = str(node.get("quality") or "").strip().lower()
    return quality if quality else "unknown"


def _salience(node: dict[str, Any]) -> str:
    if node.get("node_type") in {"quantity", "quantity_card"}:
        return "high"
    try:
        score = int(node.get("decision_relevance_score", 0) or 0)
    except (TypeError, ValueError):
        score = 0
    if score >= 8:
        return "high"
    if score >= 5:
        return "medium"
    return "low"


def _strength(node: dict[str, Any], quality: str) -> str:
    if quality in {"weak", "indirect"}:
        return "weak"
    if node.get("node_type") in {"quantity", "quantity_card"}:
        return "estimate"
    return "not_assessed"


def _uncertainty(node: dict[str, Any], quality: str) -> str:
    if quality == "unknown":
        return "evidence quality not assessed"
    if node.get("node_type") in {"quantity", "quantity_card"}:
        return "interpret with source design and interval context"
    return "not specified"


def _directionality(role: str) -> str:
    return {
        "answer_support": "supports",
        "counterevidence": "challenges_or_limits",
        "quantitative_anchor": "quantifies",
        "scope_boundary": "bounds",
    }.get(role, "contextualizes")


def _quantity_values(node: dict[str, Any]) -> list[str]:
    return _string_list(node.get("quantity")) + _string_list(node.get("quantities")) + _string_list(node.get("quantity_values"))


def _summary_text(node: dict[str, Any]) -> str:
    for key in ("claim", "excerpt", "context", "quantity"):
        text = str(node.get(key, "")).strip()
        if text:
            return text[:360]
    return str(node.get("node_id", ""))


def _node_text(node: dict[str, Any]) -> str:
    return " ".join(str(node.get(key, "")) for key in ("claim", "excerpt", "context", "quantity", "role")).lower()


def _has_scope_text(text: str) -> bool:
    return any(term in text for term in ("scope", "boundary", "limit", "population", "subgroup", "dose", "comparator", "applies"))


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []
