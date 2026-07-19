from __future__ import annotations

from collections import Counter
from typing import Any


LOW_VALUE_RELATION_TYPES = {"none", "similar_to", "related", "mentions"}
VALUABLE_RELATION_TYPES = {"supports", "challenges", "in_tension_with", "depends_on", "crux_for", "bounds", "refines"}


def build_relation_value_report(candidate_map: dict[str, Any]) -> dict[str, Any]:
    claims = _claims(candidate_map)
    relations = _relations(candidate_map)
    claim_ids = {claim_id for claim in claims if (claim_id := _claim_id(claim))}
    type_counts = Counter(_relation_type(row) for row in relations)
    endpoint_report = _endpoint_report(relations, claim_ids)
    connected_claim_ids = {
        claim_id
        for relation in relations
        for claim_id in (_source_id(relation, claim_ids), _target_id(relation, claim_ids))
        if claim_id
    }
    grounded = [row for row in relations if _relation_has_rationale(row)]
    valuable = [row for row in relations if _relation_type(row) in VALUABLE_RELATION_TYPES]
    issues = _issues(
        claim_count=len(claims),
        relation_count=len(relations),
        connected_claim_count=len(connected_claim_ids),
        type_counts=type_counts,
        grounded_count=len(grounded),
        valuable_count=len(valuable),
        connectivity_status=endpoint_report["connectivity_status"],
    )
    return {
        "schema_id": "relation_value_report_v1",
        "status": "warning" if issues else "useful",
        "claim_count": len(claims),
        "relation_count": len(relations),
        "connected_claim_count": len(connected_claim_ids),
        "connected_claim_fraction": round(len(connected_claim_ids) / len(claims), 3) if claims else 0.0,
        "connectivity_status": endpoint_report["connectivity_status"],
        "missing_endpoint_relation_count": endpoint_report["missing_endpoint_relation_count"],
        "endpoint_field_coverage": endpoint_report["endpoint_field_coverage"],
        "relation_type_counts": dict(sorted(type_counts.items())),
        "valuable_relation_count": len(valuable),
        "valuable_relation_fraction": round(len(valuable) / len(relations), 3) if relations else 0.0,
        "grounded_relation_count": len(grounded),
        "grounded_relation_fraction": round(len(grounded) / len(relations), 3) if relations else 0.0,
        "issues": issues,
    }


def _issues(
    *,
    claim_count: int,
    relation_count: int,
    connected_claim_count: int,
    type_counts: Counter[str],
    grounded_count: int,
    valuable_count: int,
    connectivity_status: str,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if claim_count and relation_count < max(3, claim_count // 12):
        issues.append({"issue_type": "sparse_relation_graph", "severity": "warning"})
    if connectivity_status == "not_computable_missing_endpoint_ids":
        issues.append({"issue_type": "relation_connectivity_not_computable", "severity": "warning"})
    elif relation_count and connected_claim_count / max(1, claim_count) < 0.15:
        issues.append({"issue_type": "low_claim_connectivity", "severity": "warning"})
    low_value_count = sum(type_counts.get(kind, 0) for kind in LOW_VALUE_RELATION_TYPES)
    if relation_count and low_value_count / relation_count > 0.5:
        issues.append({"issue_type": "low_value_relation_type_dominance", "severity": "warning"})
    if relation_count and valuable_count / relation_count < 0.5:
        issues.append({"issue_type": "few_decision_relevant_relation_types", "severity": "warning"})
    if relation_count and grounded_count / relation_count < 0.7:
        issues.append({"issue_type": "weak_relation_rationales", "severity": "warning"})
    return issues


def _claims(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    claims = candidate_map.get("claims", [])
    return [row for row in claims if isinstance(row, dict)] if isinstance(claims, list) else []


def _relations(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    relations = candidate_map.get("relations", [])
    return [row for row in relations if isinstance(row, dict)] if isinstance(relations, list) else []


def _claim_id(row: dict[str, Any]) -> str:
    return str(row.get("claim_id") or row.get("id") or "").strip()


def _relation_type(row: dict[str, Any]) -> str:
    return str(row.get("relation_type") or row.get("type") or "").strip() or "unknown"


def _source_id(row: dict[str, Any], claim_ids: set[str]) -> str:
    return _endpoint_id(row, ("source_claim_id", "claim_a_id", "from", "source", "source_claim"), claim_ids)


def _target_id(row: dict[str, Any], claim_ids: set[str]) -> str:
    return _endpoint_id(row, ("target_claim_id", "claim_b_id", "to", "target", "target_claim"), claim_ids)


def _endpoint_id(row: dict[str, Any], keys: tuple[str, ...], claim_ids: set[str]) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if not value:
            continue
        if key in {"source_claim", "target_claim"} and claim_ids and value not in claim_ids:
            continue
        return value
    return ""


def _endpoint_report(relations: list[dict[str, Any]], claim_ids: set[str]) -> dict[str, Any]:
    missing = [row for row in relations if not (_source_id(row, claim_ids) and _target_id(row, claim_ids))]
    if not relations:
        status = "no_relations"
    elif missing:
        status = "not_computable_missing_endpoint_ids"
    else:
        status = "computed"
    return {
        "connectivity_status": status,
        "missing_endpoint_relation_count": len(missing),
        "endpoint_field_coverage": round((len(relations) - len(missing)) / len(relations), 3) if relations else 0.0,
    }


def _relation_has_rationale(row: dict[str, Any]) -> bool:
    text = " ".join(
        str(row.get(key) or "").strip()
        for key in ("rationale", "explanation", "because", "source_claim_support_excerpt", "target_claim_support_excerpt")
    )
    return len(text.split()) >= 6
