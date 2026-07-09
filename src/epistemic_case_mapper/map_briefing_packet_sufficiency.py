from __future__ import annotations

import re
from collections import Counter
from typing import Any


ROLE_ORDER = (
    "strongest_support",
    "counterweight",
    "scope_boundary",
    "decision_crux",
    "quantitative_anchor",
    "mechanism",
    "context",
)


def build_packet_sufficiency_report(packet: dict[str, Any], *, candidate_pool: list[dict[str, Any]]) -> dict[str, Any]:
    bundles = [row for row in packet.get("evidence_bundles", []) if isinstance(row, dict)]
    retained_ids = _retained_candidate_ids(bundles)
    high_priority_omitted = [
        _omitted_candidate_row(row)
        for row in candidate_pool
        if _candidate_priority(row) >= 7
        and row.get("candidate_card_id")
        and str(row.get("candidate_card_id")) not in retained_ids
        and "appendix" not in str(row.get("inclusion_recommendation", "")).lower()
    ]
    role_coverage = _role_coverage(candidate_pool, bundles)
    quantity_retention = _quantity_retention(packet, candidate_pool)
    source_diversity = _source_diversity(packet, candidate_pool)
    source_bottom_lines = _source_bottom_line_retention(candidate_pool, bundles)
    counterweight = _counterweight_preservation(candidate_pool, bundles)
    directionality = _directionality_consistency(bundles)
    grounding = _source_grounding_precedence(bundles)
    compression = _compression_loss(candidate_pool, bundles)
    weak = _unsupported_or_weakly_anchored_bundles(bundles)
    over_merge = _over_merge_risk(bundles)
    issues = [
        *(["high_priority_omitted_evidence"] if high_priority_omitted else []),
        *(["missing_available_roles"] if role_coverage["missing_available_roles"] else []),
        *(["top_quantities_missing_from_must_retain"] if quantity_retention["missing_top_quantities"] else []),
        *(["counterweights_not_preserved"] if not counterweight["preserved"] and counterweight["available_count"] else []),
        *(["directionality_warnings"] if directionality["warnings"] else []),
        *(["source_grounding_warnings"] if grounding["warnings"] else []),
        *(["source_bottom_lines_missing"] if source_bottom_lines["missing_source_bottom_line_ids"] else []),
        *(["compression_loss"] if compression["loss_rows"] else []),
        *(["weakly_anchored_bundles"] if weak["bundle_ids"] else []),
        *(["over_merge_risk"] if over_merge["rows"] else []),
    ]
    status = "not_sufficient_for_synthesis" if _hard_sufficiency_failure(issues, packet) else "usable_with_warnings" if issues else "ready"
    return {
        "schema_id": "packet_sufficiency_report_v1",
        "status": status,
        "method": "pre_synthesis_packet_role_quantity_source_and_compression_checks",
        "high_priority_omitted_evidence": high_priority_omitted[:30],
        "role_coverage": role_coverage,
        "quantity_retention": quantity_retention,
        "source_diversity": source_diversity,
        "source_bottom_line_retention": source_bottom_lines,
        "counterweight_preservation": counterweight,
        "directionality_consistency": directionality,
        "source_grounding_precedence": grounding,
        "compression_loss": compression,
        "unsupported_or_weakly_anchored_bundles": weak,
        "over_merge_risk": over_merge,
        "issues": issues,
    }


def packet_quantity_retention(packet: dict[str, Any], candidate_pool: list[dict[str, Any]]) -> dict[str, Any]:
    return _quantity_retention(packet, candidate_pool)


def _role_coverage(candidate_pool: list[dict[str, Any]], bundles: list[dict[str, Any]]) -> dict[str, Any]:
    available = sorted({str(row.get("decision_role")) for row in candidate_pool if row.get("decision_role")})
    retained = sorted({str(row.get("decision_role")) for row in bundles if row.get("decision_role")})
    required_if_available = [role for role in ROLE_ORDER if role in available]
    missing = [role for role in required_if_available if role not in retained]
    return {
        "available_roles": available,
        "retained_roles": retained,
        "missing_available_roles": missing,
        "available_counts": dict(Counter(str(row.get("decision_role")) for row in candidate_pool if row.get("decision_role"))),
        "retained_counts": dict(Counter(str(row.get("decision_role")) for row in bundles if row.get("decision_role"))),
    }


def _quantity_retention(packet: dict[str, Any], candidate_pool: list[dict[str, Any]]) -> dict[str, Any]:
    retain_terms = {
        _norm(term)
        for row in packet.get("must_retain_ledger", [])
        if isinstance(row, dict)
        for term in _string_list(row.get("required_terms")) + _string_list(row.get("statement"))
    }
    top = []
    for row in sorted(candidate_pool, key=_candidate_rank):
        if row.get("decision_role") != "quantitative_anchor":
            continue
        for quantity in _string_list(row.get("quantity_values")):
            if quantity and quantity not in top:
                top.append(quantity)
        if len(top) >= 12:
            break
    missing = [quantity for quantity in top if _norm(quantity) not in retain_terms]
    return {
        "top_quantities": top,
        "retained_top_quantities": [quantity for quantity in top if quantity not in missing],
        "missing_top_quantities": missing,
    }


def _source_diversity(packet: dict[str, Any], candidate_pool: list[dict[str, Any]]) -> dict[str, Any]:
    retained = {
        source
        for bundle in packet.get("evidence_bundles", [])
        if isinstance(bundle, dict)
        for source in _string_list(bundle.get("source_ids"))
    }
    available = {source for row in candidate_pool for source in _string_list(row.get("source_ids"))}
    return {
        "available_source_count": len(available),
        "retained_source_count": len(retained),
        "retained_fraction": round(len(retained) / len(available), 3) if available else 1.0,
        "retained_source_ids": sorted(retained)[:30],
    }


def _source_bottom_line_retention(candidate_pool: list[dict[str, Any]], bundles: list[dict[str, Any]]) -> dict[str, Any]:
    available = [
        row
        for row in candidate_pool
        if str(row.get("pretrim_kind")) == "source_bottom_line" and row.get("candidate_card_id")
    ]
    retained_ids = {
        card_id
        for bundle in bundles
        for card_id in _string_list(bundle.get("candidate_card_ids"))
    }
    missing = [
        {
            "candidate_card_id": row.get("candidate_card_id"),
            "source_ids": _string_list(row.get("source_ids")),
            "source_labels": _string_list(row.get("source_labels")),
            "decision_role": row.get("decision_role"),
            "claim": _short_text(str(row.get("claim", "")), 180),
        }
        for row in available
        if str(row.get("candidate_card_id")) not in retained_ids
    ]
    return {
        "available_count": len(available),
        "retained_count": len(available) - len(missing),
        "missing_count": len(missing),
        "missing_source_bottom_line_ids": [str(row.get("candidate_card_id")) for row in missing],
        "missing_rows": missing[:20],
    }


def _counterweight_preservation(candidate_pool: list[dict[str, Any]], bundles: list[dict[str, Any]]) -> dict[str, Any]:
    available = [row for row in candidate_pool if row.get("decision_role") == "counterweight"]
    retained = [row for row in bundles if row.get("decision_role") == "counterweight"]
    return {
        "available_count": len(available),
        "retained_count": len(retained),
        "preserved": not available or bool(retained),
    }


def _directionality_consistency(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    warnings = []
    for bundle in bundles:
        role = str(bundle.get("decision_role", ""))
        direction = str(bundle.get("directionality", ""))
        if role == "counterweight" and direction not in {"challenges", "in_tension", "bounds"}:
            warnings.append({"bundle_id": bundle.get("bundle_id"), "issue": "counterweight_without_challenge_direction"})
        if role == "scope_boundary" and direction not in {"bounds", "scopes"}:
            warnings.append({"bundle_id": bundle.get("bundle_id"), "issue": "scope_boundary_without_scope_direction"})
    return {"warnings": warnings[:20]}


def _source_grounding_precedence(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    warnings = [
        {"bundle_id": row.get("bundle_id"), "issue": "bundle_without_source_grounding"}
        for row in bundles
        if not row.get("source_grounded") and str(row.get("decision_role")) in {"strongest_support", "counterweight", "quantitative_anchor"}
    ]
    return {"warnings": warnings[:20]}


def _compression_loss(candidate_pool: list[dict[str, Any]], bundles: list[dict[str, Any]]) -> dict[str, Any]:
    retained_pool_ids = {str(row.get("pretrim_pool_id")) for row in bundles if row.get("pretrim_pool_id")}
    retained_quantities = {q for row in bundles for q in _string_list(row.get("quantity_values"))}
    retained_sources = {s for row in bundles for s in _string_list(row.get("source_ids"))}
    loss_rows = []
    for row in candidate_pool:
        if str(row.get("pool_id")) in retained_pool_ids or _candidate_priority(row) < 7:
            continue
        unique_quantities = [q for q in _string_list(row.get("quantity_values")) if q not in retained_quantities]
        unique_sources = [s for s in _string_list(row.get("source_ids")) if s not in retained_sources]
        if unique_quantities or unique_sources:
            loss_rows.append(
                _drop_empty(
                    {
                        "pool_id": row.get("pool_id"),
                        "candidate_card_id": row.get("candidate_card_id"),
                        "decision_role": row.get("decision_role"),
                        "unique_quantities": unique_quantities[:5],
                        "unique_source_ids": unique_sources[:5],
                        "claim": _short_text(str(row.get("claim", "")), 180),
                    }
                )
            )
    return {"loss_rows": loss_rows[:30], "loss_count": len(loss_rows)}


def _unsupported_or_weakly_anchored_bundles(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [
        str(row.get("bundle_id"))
        for row in bundles
        if not row.get("source_grounded")
        or not _string_list(row.get("source_ids"))
    ]
    return {"bundle_ids": ids[:30], "count": len(ids)}


def _over_merge_risk(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for bundle in bundles:
        source_count = len(_string_list(bundle.get("source_ids")))
        role = str(bundle.get("decision_role", ""))
        if source_count >= 4 and role in {"strongest_support", "counterweight", "scope_boundary"}:
            rows.append({"bundle_id": bundle.get("bundle_id"), "source_count": source_count, "issue": "many_sources_in_single_bundle"})
    return {"rows": rows[:20], "count": len(rows)}


def _hard_sufficiency_failure(issues: list[str], packet: dict[str, Any]) -> bool:
    if not packet.get("evidence_bundles") or not packet.get("must_retain_ledger"):
        return True
    return "counterweights_not_preserved" in issues and "missing_available_roles" in issues


def _candidate_rank(row: dict[str, Any]) -> tuple[int, int, int, str]:
    role_rank = {
        "quantitative_anchor": 0,
        "counterweight": 1,
        "strongest_support": 2,
        "scope_boundary": 3,
        "decision_crux": 4,
        "mechanism": 5,
        "context": 6,
    }.get(str(row.get("decision_role", "")), 7)
    grounded = 0 if row.get("source_grounded") else 1
    return (role_rank, -_candidate_priority(row), grounded, str(row.get("pool_id", "")))


def _candidate_priority(row: dict[str, Any]) -> int:
    try:
        score = int(row.get("decision_relevance_score", 0) or 0)
    except (TypeError, ValueError):
        score = 0
    if row.get("quantity_values"):
        score += 1
    if row.get("decision_role") in {"counterweight", "quantitative_anchor"}:
        score += 1
    if not row.get("source_grounded"):
        score -= 2
    return max(0, min(10, score))


def _retained_candidate_ids(bundles: list[dict[str, Any]]) -> set[str]:
    return {
        card_id
        for bundle in bundles
        for card_id in _string_list(bundle.get("candidate_card_ids"))
        if card_id
    }


def _omitted_candidate_row(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "pool_id": row.get("pool_id"),
            "candidate_card_id": row.get("candidate_card_id"),
            "decision_role": row.get("decision_role"),
            "priority": _candidate_priority(row),
            "source_ids": _string_list(row.get("source_ids"))[:5],
            "quantity_values": _string_list(row.get("quantity_values"))[:5],
            "claim": _short_text(str(row.get("claim", "")), 220),
            "reason": "high-priority candidate was not retained after packet role budgets",
        }
    )


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", [], {}, None)}


def _short_text(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9.]+", " ", str(text).lower()).strip()
