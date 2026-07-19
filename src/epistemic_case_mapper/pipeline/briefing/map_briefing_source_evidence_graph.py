from __future__ import annotations

import re
from typing import Any


def build_source_evidence_graph(scaffold: dict[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for source_id, label in _source_display_names(scaffold).items():
        nodes.append(_node(f"source:{source_id}", "source", source_id=source_id, label=label))
    _add_source_cards(scaffold, nodes, edges)
    _add_candidate_claims(scaffold, nodes, edges)
    _add_quantity_cards(scaffold, nodes, edges)
    _add_source_bottom_lines(scaffold, nodes, edges)
    nodes = _dedupe_nodes(nodes)
    edges = _dedupe_edges(edges)
    return {
        "schema_id": "source_evidence_graph_v1",
        "method": "deterministic_source_claim_quantity_lineage_graph",
        "nodes": nodes,
        "edges": edges,
        "summary": _summary(nodes, edges),
        "warnings": _warnings(nodes),
    }


def _add_source_cards(scaffold: dict[str, Any], nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    for card in _cards(scaffold.get("source_evidence_cards")):
        card_id = str(card.get("source_card_id", "")).strip()
        if not card_id:
            continue
        source_ids = _string_list(card.get("source_id")) + _string_list(card.get("source_ids"))
        nodes.append(
            _node(
                f"source_card:{card_id}",
                "source_card",
                source_card_id=card_id,
                source_ids=_dedupe(source_ids),
                excerpt=_short_text(str(card.get("source_quote_or_excerpt") or card.get("excerpt") or ""), 360),
                quantity_values=_string_list(card.get("quantity_values")),
                quality=_quality_from_card(card),
            )
        )
        for source_id in source_ids:
            edges.append(_edge(f"source:{source_id}", f"source_card:{card_id}", "source_has_card"))
        for claim_id in _string_list(card.get("claim_ids")):
            edges.append(_edge(f"source_card:{card_id}", f"claim:{claim_id}", "card_supports_claim"))


def _add_candidate_claims(scaffold: dict[str, Any], nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    for card in _cards(scaffold.get("candidate_evidence_cards")):
        claim_ids = _string_list(card.get("claim_ids")) or _string_list(card.get("candidate_card_id"))
        if not claim_ids:
            continue
        candidate_id = str(card.get("candidate_card_id", "")).strip()
        source_ids = _string_list(card.get("source_ids"))
        for claim_id in claim_ids:
            nodes.append(
                _node(
                    f"claim:{claim_id}",
                    "claim",
                    claim_id=claim_id,
                    candidate_card_id=candidate_id,
                    source_ids=source_ids,
                    claim=_short_text(str(card.get("claim", "")), 520),
                    role=card.get("role"),
                    evidence_roles=_string_list(card.get("evidence_roles")),
                    decision_relevance_score=card.get("decision_relevance_score"),
                    quality=card.get("quality") or "unknown",
                )
            )
            for source_id in source_ids:
                edges.append(_edge(f"source:{source_id}", f"claim:{claim_id}", "source_has_claim"))
            for source_card_id in _string_list(card.get("source_card_ids")):
                edges.append(_edge(f"source_card:{source_card_id}", f"claim:{claim_id}", "card_supports_claim"))
            for quantity in _string_list(card.get("quantity_values")):
                quantity_id = _quantity_node_id(claim_id, quantity)
                nodes.append(_node(quantity_id, "quantity", quantity=quantity, claim_ids=[claim_id], source_ids=source_ids))
                edges.append(_edge(f"claim:{claim_id}", quantity_id, "claim_has_quantity"))


def _add_quantity_cards(scaffold: dict[str, Any], nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    ledger = scaffold.get("quantity_ledger") if isinstance(scaffold.get("quantity_ledger"), dict) else {}
    for card in ledger.get("evidence_cards", []) if isinstance(ledger.get("evidence_cards"), list) else []:
        if not isinstance(card, dict):
            continue
        card_id = str(card.get("card_id") or card.get("quantity_id") or "").strip()
        claim_id = str(card.get("claim_id", "")).strip()
        source_ids = _string_list(card.get("source_id")) + _string_list(card.get("source_ids"))
        quantities = _dedupe([*_string_list(card.get("key_quantities")), *_string_list(card.get("effect_estimates"))])
        if card_id:
            nodes.append(
                _node(
                    f"quantity_card:{card_id}",
                    "quantity_card",
                    quantity_card_id=card_id,
                    claim_ids=[claim_id] if claim_id else [],
                    source_ids=_dedupe(source_ids),
                    quantities=quantities,
                    claim=_short_text(str(card.get("claim", "")), 420),
                    context=_short_text(str(card.get("context", "")), 420),
                    quality=card.get("evidence_use") or "unknown",
                )
            )
        if claim_id and card_id:
            edges.append(_edge(f"claim:{claim_id}", f"quantity_card:{card_id}", "claim_has_quantity_card"))
        for quantity in quantities:
            quantity_id = _quantity_node_id(claim_id or card_id, quantity)
            nodes.append(_node(quantity_id, "quantity", quantity=quantity, claim_ids=[claim_id] if claim_id else [], source_ids=_dedupe(source_ids)))
            if card_id:
                edges.append(_edge(f"quantity_card:{card_id}", quantity_id, "quantity_card_has_value"))
            if claim_id:
                edges.append(_edge(f"claim:{claim_id}", quantity_id, "claim_has_quantity"))
    for row in ledger.get("top_quantitative_anchors", []) if isinstance(ledger.get("top_quantitative_anchors"), list) else []:
        if not isinstance(row, dict):
            continue
        quantity = str(row.get("quantity_text") or row.get("quantity") or "").strip()
        claim_id = str(row.get("claim_id", "")).strip()
        if not quantity:
            continue
        quantity_id = _quantity_node_id(claim_id or "top_anchor", quantity)
        nodes.append(
            _node(
                quantity_id,
                "quantity",
                quantity=quantity,
                claim_ids=[claim_id] if claim_id else [],
                source_labels=_string_list(row.get("source")),
                quantity_type=row.get("quantity_type"),
                relevance_score=row.get("relevance_score"),
                top_anchor=True,
            )
        )
        if claim_id:
            edges.append(_edge(f"claim:{claim_id}", quantity_id, "claim_has_top_quantity"))


def _add_source_bottom_lines(scaffold: dict[str, Any], nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    report = scaffold.get("source_bottom_line_cards") if isinstance(scaffold.get("source_bottom_line_cards"), dict) else {}
    for index, card in enumerate(report.get("cards", []) if isinstance(report.get("cards"), list) else []):
        if not isinstance(card, dict):
            continue
        card_id = str(card.get("card_id") or card.get("source_bottom_line_card_id") or f"source_bottom_line_{index:03d}")
        source_ids = _string_list(card.get("source_id")) + _string_list(card.get("source_ids"))
        nodes.append(
            _node(
                f"source_bottom_line:{card_id}",
                "source_bottom_line",
                source_bottom_line_id=card_id,
                source_ids=_dedupe(source_ids),
                claim=_short_text(str(card.get("claim") or card.get("bottom_line") or card.get("summary") or ""), 520),
                quality=card.get("quality") or "source_summary",
            )
        )
        for source_id in source_ids:
            edges.append(_edge(f"source:{source_id}", f"source_bottom_line:{card_id}", "source_has_bottom_line"))


def _source_display_names(scaffold: dict[str, Any]) -> dict[str, str]:
    display = scaffold.get("source_display_names") if isinstance(scaffold.get("source_display_names"), dict) else {}
    citation = scaffold.get("source_citation_labels") if isinstance(scaffold.get("source_citation_labels"), dict) else {}
    ids: dict[str, str] = {}
    for source_id, label in {**display, **citation}.items():
        source_key = str(source_id).strip()
        if source_key:
            ids[source_key] = str(label or source_id).strip()
    for card in _cards(scaffold.get("source_evidence_cards")) + _cards(scaffold.get("candidate_evidence_cards")):
        for source_id in _string_list(card.get("source_id")) + _string_list(card.get("source_ids")):
            ids.setdefault(source_id, source_id)
    return ids


def _node(node_id: str, node_type: str, **fields: Any) -> dict[str, Any]:
    return _drop_empty({"node_id": node_id, "node_type": node_type, **fields})


def _edge(source_node_id: str, target_node_id: str, edge_type: str) -> dict[str, Any]:
    return {"source_node_id": source_node_id, "target_node_id": target_node_id, "edge_type": edge_type}


def _summary(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for node in nodes:
        node_type = str(node.get("node_type", "unknown"))
        counts[node_type] = counts.get(node_type, 0) + 1
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_type_counts": counts,
        "quantity_node_count": counts.get("quantity", 0),
        "source_node_count": counts.get("source", 0),
        "claim_node_count": counts.get("claim", 0),
    }


def _warnings(nodes: list[dict[str, Any]]) -> list[str]:
    warnings = []
    if not any(node.get("node_type") == "source" for node in nodes):
        warnings.append("no_source_nodes")
    if not any(node.get("node_type") == "claim" for node in nodes):
        warnings.append("no_claim_nodes")
    if not any(node.get("node_type") == "quantity" for node in nodes):
        warnings.append("no_quantity_nodes")
    if any(node.get("node_type") in {"claim", "quantity_card"} and not node.get("quality") for node in nodes):
        warnings.append("quality_metadata_missing")
    return warnings


def _quality_from_card(card: dict[str, Any]) -> str:
    return str(card.get("quality") or card.get("evidence_quality") or card.get("evidence_use") or "unknown")


def _quantity_node_id(owner_id: str, quantity: str) -> str:
    normalized = re.sub(r"[^a-z0-9.]+", "_", quantity.lower()).strip("_")[:60] or "quantity"
    owner = re.sub(r"[^a-zA-Z0-9_]+", "_", owner_id).strip("_") or "unknown"
    return f"quantity:{owner}:{normalized}"


def _dedupe_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for node in nodes:
        node_id = str(node.get("node_id", "")).strip()
        if not node_id:
            continue
        if node_id not in merged:
            merged[node_id] = dict(node)
            continue
        merged[node_id] = _merge_node(merged[node_id], node)
    return list(merged.values())


def _merge_node(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if value in ("", [], {}, None):
            continue
        if key not in merged or merged[key] in ("", [], {}, None):
            merged[key] = value
        elif isinstance(merged[key], list):
            merged[key] = _dedupe([*merged[key], *_string_list(value)])
    return merged


def _dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for edge in edges:
        key = (edge.get("source_node_id"), edge.get("target_node_id"), edge.get("edge_type"))
        if key in seen:
            continue
        seen.add(key)
        result.append(edge)
    return result


def _cards(report: Any) -> list[dict[str, Any]]:
    data = report if isinstance(report, dict) else {}
    return [card for card in data.get("cards", []) if isinstance(card, dict)]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", [], {}, None)}


def _short_text(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."
