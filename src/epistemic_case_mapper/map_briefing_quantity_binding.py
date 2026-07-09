from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    list_value as _list,
    quantity_direction as _quantity_direction,
    quantity_type as _quantity_type,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_quantity_tuples import (
    is_effect_or_interval as _is_effect_or_interval,
    quantity_tuples as _quantity_tuples,
    tuple_for_quantity as _tuple_for_quantity,
    unsafe_quantity_pairings as _unsafe_quantity_pairings,
)


def build_quantity_binding_report(packet: dict[str, Any], clusters: dict[str, Any]) -> dict[str, Any]:
    bindings = []
    unbound = []
    unsafe_pairings = []
    for cluster in _clusters(clusters):
        quantities = _string_list(cluster.get("quantity_values"))
        if not quantities:
            continue
        if not cluster.get("representative_claim") or not cluster.get("source_labels"):
            unbound.append(
                {
                    "cluster_id": cluster.get("cluster_id"),
                    "quantity_values": quantities,
                    "reason": "missing_claim_or_source_label",
                }
            )
            continue
        parsed = [_quantity_object(quantity, cluster) for quantity in quantities]
        quantity_tuples = _quantity_tuples(cluster, quantities)
        cluster_unsafe_pairings = _unsafe_quantity_pairings(cluster, parsed, quantity_tuples)
        unsafe_pairings.extend(cluster_unsafe_pairings)
        bindings.append(
            {
                "cluster_id": cluster.get("cluster_id"),
                "bundle_ids": _string_list(cluster.get("bundle_ids")),
                "claim_ids": _string_list(cluster.get("claim_ids")),
                "source_ids": _string_list(cluster.get("source_ids")),
                "source_labels": _string_list(cluster.get("source_labels")),
                "reader_claim": cluster.get("representative_claim"),
                "quantities": parsed,
                "quantity_tuples": quantity_tuples,
                "unsafe_quantity_pairings": cluster_unsafe_pairings,
                "binding_confidence": "high" if parsed else "low",
            }
        )
    total = len(bindings) + len(unbound)
    return {
        "schema_id": "quantity_binding_report_v1",
        "method": "bind_bundle_quantities_to_claim_source_and_interpretation",
        "binding_count": len(bindings),
        "unbound_quantity_group_count": len(unbound),
        "safe_binding_rate": round(len(bindings) / total, 3) if total else 1.0,
        "bindings": bindings,
        "unbound_quantities": unbound,
        "unsafe_quantity_pairings": unsafe_pairings,
        "unsafe_quantity_pairing_count": len(unsafe_pairings),
    }


def _quantity_object(quantity: str, cluster: dict[str, Any]) -> dict[str, str]:
    quantity = str(quantity).strip()
    obj = {
        "value": quantity,
        "quantity_type": _quantity_type([quantity]),
        "direction": _quantity_direction(quantity, str(cluster.get("representative_claim") or "")),
        "interpretation": _quantity_interpretation(quantity, cluster),
    }
    tuple_row = _tuple_for_quantity(quantity, _quantity_tuples(cluster, _string_list(cluster.get("quantity_values"))))
    if tuple_row:
        obj["tuple_id"] = str(tuple_row.get("tuple_id") or "")
        obj["tuple_label"] = str(tuple_row.get("label") or "")
    elif _is_effect_or_interval(quantity):
        obj["binding_warning"] = "not_locally_paired_in_source_excerpt"
        obj["interpretation"] = "source quantity; do not pair with another estimate or interval unless a local tuple says to"
    return obj


def _quantity_interpretation(quantity: str, cluster: dict[str, Any]) -> str:
    claim = str(cluster.get("representative_claim") or "")
    role = _memo_ready_role(str(cluster.get("source_decision_role") or ""))
    if "ci" in quantity.lower() or "confidence interval" in quantity.lower():
        return "uncertainty interval for the associated estimate"
    if role == "strongest_counterweight":
        return "quantifies evidence that weakens or qualifies the default read"
    if role == "scope_boundary":
        return "quantifies a boundary or applicability condition"
    if role == "quantitative_anchor":
        return "load-bearing numerical anchor for the decision"
    if any(term in claim.lower() for term in ("reduced", "lower", "decreased")):
        return "quantifies a lower or reduced outcome in the source claim"
    if any(term in claim.lower() for term in ("increased", "higher", "greater")):
        return "quantifies a higher or increased outcome in the source claim"
    return "quantifies the associated source-backed claim"


def _memo_ready_role(role: str) -> str:
    role = str(role or "").strip()
    return {
        "strongest_support": "strongest_support",
        "counterweight": "strongest_counterweight",
        "scope_boundary": "scope_boundary",
        "decision_crux": "decision_crux",
        "quantitative_anchor": "quantitative_anchor",
        "mechanism": "mechanism_or_explanation",
        "context": "context_only",
    }.get(role, "uncertain_role")


def _clusters(clusters: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _list(clusters.get("clusters")) if isinstance(row, dict)]
