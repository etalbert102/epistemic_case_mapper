from __future__ import annotations

import re
from collections import Counter
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_omission_priority import (
    candidate_priority,
    omitted_candidate_row,
)


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
    review_worthy_omitted_rows = [
        row
        for row in candidate_pool
        if candidate_priority(row) >= 7
        and row.get("candidate_card_id")
        and str(row.get("candidate_card_id")) not in retained_ids
        and "appendix" not in str(row.get("inclusion_recommendation", "")).lower()
    ]
    truly_lost_omitted_rows = [
        row for row in review_worthy_omitted_rows if not _omission_represented(row, bundles)
    ]
    review_worthy_omitted = [omitted_candidate_row(row) for row in review_worthy_omitted_rows]
    truly_lost_omitted = [omitted_candidate_row(row) for row in truly_lost_omitted_rows]
    decision_critical_omitted = [
        row for row in truly_lost_omitted if row.get("omission_severity") == "decision_critical"
    ]
    moderate_context_omitted = [
        row for row in truly_lost_omitted if row.get("omission_severity") == "moderate_context"
    ]
    role_coverage = _role_coverage(candidate_pool, bundles)
    quantity_retention = _quantity_retention(packet, candidate_pool)
    quantity_obligations = build_quantity_obligation_ledger(packet, candidate_pool)
    source_diversity = _source_diversity(packet, candidate_pool)
    source_bottom_lines = _source_bottom_line_retention(candidate_pool, bundles)
    counterweight = _counterweight_preservation(candidate_pool, bundles)
    directionality = _directionality_consistency(bundles)
    grounding = _source_grounding_precedence(bundles)
    compression = _compression_loss(candidate_pool, bundles)
    weak = _unsupported_or_weakly_anchored_bundles(bundles)
    over_merge = _over_merge_risk(bundles)
    issues = [
        *(["decision_critical_omitted_evidence"] if decision_critical_omitted else []),
        *(["moderate_context_omitted_evidence"] if moderate_context_omitted else []),
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
        "review_worthy_omitted_evidence": review_worthy_omitted[:30],
        "truly_lost_omitted_evidence": truly_lost_omitted[:30],
        "decision_critical_omitted_evidence": decision_critical_omitted[:30],
        "moderate_context_omitted_evidence": moderate_context_omitted[:30],
        "high_priority_omitted_evidence": review_worthy_omitted[:30],
        "role_coverage": role_coverage,
        "quantity_retention": quantity_retention,
        "quantity_obligation_ledger": quantity_obligations,
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


def build_quantity_obligation_ledger(packet: dict[str, Any], candidate_pool: list[dict[str, Any]]) -> dict[str, Any]:
    top_quantities = _top_quantity_obligations(candidate_pool)
    retained_bundle_quantities = {
        _norm(quantity)
        for bundle in packet.get("evidence_bundles", [])
        if isinstance(bundle, dict)
        for quantity in _string_list(bundle.get("quantity_values"))
    }
    retained_terms = _must_retain_terms(packet)
    obligations = []
    for row in top_quantities:
        quantity_norm = _norm(str(row.get("quantity", "")))
        obligations.append(
            {
                **row,
                "retained_in_evidence_bundles": quantity_norm in retained_bundle_quantities,
                "retained_in_must_retain": quantity_norm in retained_terms,
                "status": "retained" if quantity_norm in retained_terms else "missing_from_must_retain",
            }
        )
    missing = [row for row in obligations if row["status"] != "retained"]
    return {
        "schema_id": "quantity_obligation_ledger_v1",
        "obligation_count": len(obligations),
        "retained_count": len(obligations) - len(missing),
        "missing_count": len(missing),
        "obligations": obligations,
        "missing_quantities": [str(row.get("quantity")) for row in missing],
    }


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
    ledger = build_quantity_obligation_ledger(packet, candidate_pool)
    top = [str(row.get("quantity")) for row in ledger["obligations"]]
    missing = ledger["missing_quantities"]
    return {
        "top_quantities": top,
        "retained_top_quantities": [quantity for quantity in top if quantity not in missing],
        "missing_top_quantities": missing,
    }


def _top_quantity_obligations(candidate_pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in sorted(candidate_pool, key=_candidate_rank):
        if row.get("decision_role") != "quantitative_anchor":
            continue
        for quantity in _string_list(row.get("quantity_values")):
            quantity_norm = _norm(quantity)
            if not quantity or quantity_norm in seen:
                continue
            seen.add(quantity_norm)
            rows.append(
                _drop_empty(
                    {
                        "quantity": quantity,
                        "candidate_card_id": row.get("candidate_card_id"),
                        "pool_id": row.get("pool_id"),
                        "claim_ids": _string_list(row.get("claim_ids"))[:8],
                        "source_ids": _string_list(row.get("source_ids"))[:8],
                        "source_labels": _string_list(row.get("source_labels"))[:4],
                        "claim": _short_text(str(row.get("claim", "")), 220),
                    }
                )
            )
        if len(rows) >= 12:
            break
    return rows


def _must_retain_terms(packet: dict[str, Any]) -> set[str]:
    return {
        _norm(term)
        for row in packet.get("must_retain_ledger", [])
        if isinstance(row, dict)
        for term in _string_list(row.get("required_terms")) + _string_list(row.get("statement"))
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
        if str(row.get("pool_id")) in retained_pool_ids or candidate_priority(row) < 7:
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
    return (role_rank, -candidate_priority(row), grounded, str(row.get("pool_id", "")))


def _omission_represented(row: dict[str, Any], bundles: list[dict[str, Any]]) -> bool:
    return any(_representation_reason(row, bundle) for bundle in bundles)


def _representation_reason(row: dict[str, Any], bundle: dict[str, Any]) -> str:
    if _overlap(row, bundle, "claim_ids"):
        return "shared_claim_id"
    if _overlap(row, bundle, "source_card_ids"):
        return "shared_source_card_id"
    if _overlap(row, bundle, "quantity_values"):
        return "shared_quantity_value"
    row_sources = set(_string_list(row.get("source_ids")))
    bundle_sources = set(_string_list(bundle.get("source_ids")))
    if row_sources and row_sources & bundle_sources and _normalized_claim_overlap(row, bundle) >= 4:
        return "shared_source_and_claim_terms"
    return ""


def _overlap(left: dict[str, Any], right: dict[str, Any], key: str) -> bool:
    return bool(set(_string_list(left.get(key))) & set(_string_list(right.get(key))))


def _normalized_claim_overlap(row: dict[str, Any], bundle: dict[str, Any]) -> int:
    left = {token for token in str(row.get("claim", "")).lower().split() if len(token) > 4}
    right = {token for token in str(bundle.get("claim", "")).lower().split() if len(token) > 4}
    return len(left & right)


def _retained_candidate_ids(bundles: list[dict[str, Any]]) -> set[str]:
    return {
        card_id
        for bundle in bundles
        for card_id in _string_list(bundle.get("candidate_card_ids"))
        if card_id
    }


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
