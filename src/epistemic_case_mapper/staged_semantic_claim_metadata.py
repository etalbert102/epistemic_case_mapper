from __future__ import annotations

from typing import Any


def claims_with_relation_role_metadata(
    claims: list[dict[str, Any]],
    prepared_relation_claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    prepared_by_id = {
        str(claim.get("claim_id", "")): claim
        for claim in prepared_relation_claims
        if str(claim.get("claim_id", "")).strip()
    }
    enriched: list[dict[str, Any]] = []
    metadata_keys = (
        "decision_edge_role",
        "decision_edge_role_confidence",
        "decision_edge_role_source",
        "decision_edge_role_reasons",
        "decision_edge_role_deterministic",
        "decision_edge_role_deterministic_confidence",
        "decision_edge_role_deterministic_reasons",
    )
    for claim in claims:
        row = dict(claim)
        prepared = prepared_by_id.get(str(claim.get("claim_id", "")))
        if prepared:
            for key in metadata_keys:
                if key in prepared:
                    row[key] = prepared[key]
            row["map_relation_role"] = prepared.get("decision_edge_role")
        else:
            row.setdefault("map_relation_role", "not_relation_eligible")
        enriched.append(row)
    return enriched
