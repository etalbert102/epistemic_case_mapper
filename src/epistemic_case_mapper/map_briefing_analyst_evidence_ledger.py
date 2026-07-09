from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


def build_analyst_evidence_ledger(
    packet: dict[str, Any],
    *,
    memo_warning_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a stable evidence inventory for later analyst adjudication."""

    packet = packet if isinstance(packet, dict) else {}
    warning_packet = memo_warning_packet if isinstance(memo_warning_packet, dict) else _dict(packet.get("memo_warning_packet"))
    rows = [
        *_bundle_rows(packet),
        *_warning_rows(warning_packet),
        *_review_context_omission_rows(packet),
        *_top_quantity_rows(packet),
    ]
    rows = _dedupe_rows(rows)
    return {
        "schema_id": "analyst_evidence_ledger_v1",
        "method": "stable_inventory_for_llm_adjudicated_packet_construction",
        "decision_question": str(packet.get("decision_question") or "").strip(),
        "row_count": len(rows),
        "summary": _summary(rows),
        "coverage_checks": _coverage_checks(packet, warning_packet, rows),
        "rows": rows,
    }


def _bundle_rows(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, bundle in enumerate(_list(packet.get("evidence_bundles"))):
        if not isinstance(bundle, dict):
            continue
        bundle_id = str(bundle.get("bundle_id") or f"bundle_{index + 1:03d}")
        rows.append(
            _drop_empty(
                {
                    "evidence_item_id": f"bundle:{bundle_id}",
                    "input_kind": "retained_bundle",
                    "current_packet_location": "decision_briefing_packet.evidence_bundles",
                    "bundle_id": bundle_id,
                    "candidate_card_ids": _string_list(bundle.get("candidate_card_ids")),
                    "source_ids": _string_list(bundle.get("source_ids")),
                    "source_labels": _string_list(bundle.get("source_labels")),
                    "claim_ids": _string_list(bundle.get("claim_ids")),
                    "relation_ids": _string_list(bundle.get("relation_ids")),
                    "quantity_ids": _string_list(bundle.get("quantity_ids")),
                    "quantity_values": _string_list(bundle.get("quantity_values")),
                    "claim": _short_text(str(bundle.get("claim") or ""), 520),
                    "source_excerpt": _short_text(str(bundle.get("source_excerpt") or ""), 520),
                    "current_role": str(bundle.get("decision_role") or ""),
                    "current_priority": _priority_from_bundle(bundle),
                    "current_weight": bundle.get("weight"),
                    "quality": bundle.get("quality"),
                    "directionality": bundle.get("directionality"),
                    "why_it_matters": _short_text(str(bundle.get("why_it_matters") or ""), 260),
                    "existing_warning_codes": _bundle_warning_codes(bundle),
                }
            )
        )
    return rows


def _warning_rows(warning_packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, warning in enumerate(_list(warning_packet.get("warnings"))):
        if not isinstance(warning, dict):
            continue
        warning_id = str(warning.get("warning_id") or f"memo_warning_{index + 1:03d}")
        rows.append(
            _drop_empty(
                {
                    "evidence_item_id": f"warning:{warning_id}",
                    "input_kind": "memo_warning",
                    "current_packet_location": "memo_warning_packet.warnings",
                    "warning_id": warning_id,
                    "source_ids": _string_list(warning.get("source_ids")),
                    "source_labels": _string_list(warning.get("source_labels")),
                    "quantity_values": _string_list(warning.get("quantity_values")),
                    "claim": _short_text(str(warning.get("claim") or ""), 520),
                    "current_role": str(warning.get("decision_role") or ""),
                    "current_priority": _priority_from_warning(warning),
                    "existing_warning_codes": [str(warning.get("warning_type") or "memo_warning")],
                    "warning_severity": warning.get("severity"),
                    "expected_memo_action": warning.get("expected_memo_action"),
                }
            )
        )
    return rows


def _review_context_omission_rows(packet: dict[str, Any]) -> list[dict[str, Any]]:
    coverage = _dict(packet.get("coverage_report"))
    rows = []
    for index, row in enumerate(_list(coverage.get("truly_lost_review_context"))):
        if not isinstance(row, dict):
            continue
        candidate_id = str(row.get("candidate_card_id") or f"review_context_{index + 1:03d}")
        rows.append(
            _drop_empty(
                {
                    "evidence_item_id": f"omission:{candidate_id}",
                    "input_kind": "review_worthy_omission",
                    "current_packet_location": "coverage_report.truly_lost_review_context",
                    "candidate_card_id": candidate_id,
                    "source_ids": _string_list(row.get("source_ids")),
                    "quantity_values": _string_list(row.get("quantity_values")),
                    "claim": _short_text(str(row.get("claim") or ""), 520),
                    "current_role": str(row.get("decision_role") or ""),
                    "current_priority": int(row.get("priority", 7) or 7),
                    "existing_warning_codes": ["review_worthy_omitted_after_trimming"],
                    "warning_severity": row.get("omission_severity"),
                    "downgrade_candidate": True,
                }
            )
        )
    return rows


def _top_quantity_rows(packet: dict[str, Any]) -> list[dict[str, Any]]:
    graph = _dict(packet.get("source_evidence_graph"))
    rows = []
    for node in _list(graph.get("nodes")):
        if not isinstance(node, dict) or node.get("node_type") != "quantity" or not node.get("top_anchor"):
            continue
        node_id = str(node.get("node_id") or node.get("id") or "")
        quantity = str(node.get("quantity") or "").strip()
        if not node_id and not quantity:
            continue
        rows.append(
            _drop_empty(
                {
                    "evidence_item_id": f"quantity:{node_id or quantity}",
                    "input_kind": "top_quantity_anchor",
                    "current_packet_location": "source_evidence_graph.nodes",
                    "source_ids": _string_list(node.get("source_ids")),
                    "source_labels": _string_list(node.get("source_labels")),
                    "claim_ids": _string_list(node.get("claim_ids")),
                    "quantity_values": _string_list(quantity),
                    "quantity_type": node.get("quantity_type"),
                    "claim": _short_text(str(node.get("claim") or quantity), 520),
                    "current_role": "quantitative_anchor",
                    "current_priority": int(node.get("relevance_score", 8) or 8),
                    "existing_warning_codes": ["top_quantity_anchor"],
                }
            )
        )
    return rows


def _coverage_checks(packet: dict[str, Any], warning_packet: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    row_locations = {str(row.get("current_packet_location")) for row in rows}
    bundle_count = len([row for row in _list(packet.get("evidence_bundles")) if isinstance(row, dict)])
    warning_count = len([row for row in _list(warning_packet.get("warnings")) if isinstance(row, dict)])
    top_quantity_count = len([row for row in rows if row.get("input_kind") == "top_quantity_anchor"])
    return {
        "retained_bundle_count": bundle_count,
        "retained_bundle_rows": sum(1 for row in rows if row.get("input_kind") == "retained_bundle"),
        "memo_warning_count": warning_count,
        "memo_warning_rows": sum(1 for row in rows if row.get("input_kind") == "memo_warning"),
        "top_quantity_anchor_rows": top_quantity_count,
        "locations_present": sorted(row_locations),
        "warnings": _dedupe(
            [
                *(["bundle_row_count_mismatch"] if bundle_count != sum(1 for row in rows if row.get("input_kind") == "retained_bundle") else []),
                *(["memo_warning_row_count_mismatch"] if warning_count != sum(1 for row in rows if row.get("input_kind") == "memo_warning") else []),
                *(["no_retained_bundle_rows"] if bundle_count and not any(row.get("input_kind") == "retained_bundle" for row in rows) else []),
            ]
        ),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "input_kind_counts": _counts(str(row.get("input_kind") or "unknown") for row in rows),
        "role_counts": _counts(str(row.get("current_role") or "unknown") for row in rows),
        "warning_row_count": sum(1 for row in rows if row.get("existing_warning_codes")),
        "quantity_row_count": sum(1 for row in rows if row.get("quantity_values")),
        "source_grounded_row_count": sum(1 for row in rows if row.get("source_ids") or row.get("source_labels")),
        "high_priority_row_count": sum(1 for row in rows if int(row.get("current_priority", 0) or 0) >= 8),
    }


def _priority_from_bundle(bundle: dict[str, Any]) -> int:
    weight = str(bundle.get("weight") or "").lower()
    if weight == "critical":
        return 10
    if weight == "high":
        return 9
    if weight == "medium":
        return 7
    if weight == "low":
        return 4
    try:
        return int(bundle.get("decision_relevance_score", 6) or 6)
    except (TypeError, ValueError):
        return 6


def _priority_from_warning(warning: dict[str, Any]) -> int:
    severity = str(warning.get("severity") or "").lower()
    if severity == "critical":
        return 10
    if severity == "moderate":
        return 8
    return 7


def _bundle_warning_codes(bundle: dict[str, Any]) -> list[str]:
    return _dedupe(
        [
            *_string_list(bundle.get("warning_codes")),
            *_string_list(bundle.get("warnings")),
            *_string_list(_dict(bundle.get("decision_relevance_assessment")).get("warnings")),
        ]
    )


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for row in rows:
        row_id = str(row.get("evidence_item_id") or "").strip()
        if not row_id or row_id in seen:
            continue
        seen.add(row_id)
        result.append(row)
    return result


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}
