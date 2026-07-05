from __future__ import annotations

import re
from collections import Counter
from typing import Any

import networkx as nx

from epistemic_case_mapper.classical_ml import relation_edge_weight


POSITIVE_RELATIONS = {"supports", "refines", "depends_on", "crux_for", "similar_to"}
TENSION_RELATIONS = {"challenges", "in_tension_with"}


def build_graph_synthesis_packet(
    candidate_map: dict[str, Any],
    evidence_ledger: dict[str, Any],
    source_lookup: dict[str, str],
) -> dict[str, Any]:
    claims = _claims(candidate_map)
    relations = _relations(candidate_map)
    graph = _claim_graph(claims, relations)
    row_lookup = _ledger_row_lookup(evidence_ledger)
    communities = _claim_communities(graph)
    metrics = _graph_metrics(graph)
    issue_clusters = _issue_clusters(graph, communities, claims, row_lookup, source_lookup)
    central_tensions = _central_tension_edges(graph, claims, row_lookup, source_lookup, metrics)
    bridge_claims = _bridge_claims(graph, claims, communities, row_lookup, source_lookup, metrics)
    load_bearing_claims = _load_bearing_claims(graph, claims, row_lookup, source_lookup, metrics)
    orphan_claims = _orphan_claims(graph, claims, row_lookup, source_lookup)
    return {
        "schema_id": "graph_synthesis_packet_v1",
        "method": "community_bridge_tension_load_bearing_graph_analysis",
        "graph_summary": {
            "claim_count": len(claims),
            "relation_count": len(relations),
            "component_count": nx.number_connected_components(graph) if graph.nodes else 0,
            "issue_cluster_count": len(issue_clusters),
            "tension_edge_count": sum(1 for _, _, data in graph.edges(data=True) if data.get("signed") == "negative"),
            "orphan_claim_count": len(orphan_claims),
        },
        "issue_clusters": issue_clusters,
        "load_bearing_claims": load_bearing_claims,
        "bridge_claims": bridge_claims,
        "central_tensions": central_tensions,
        "orphan_claims": orphan_claims,
        "synthesis_guidance": _synthesis_guidance(issue_clusters, central_tensions, bridge_claims, orphan_claims),
    }


def _claim_graph(claims: list[dict[str, Any]], relations: list[dict[str, Any]]) -> nx.Graph:
    graph = nx.Graph()
    claim_ids = {str(claim.get("claim_id", "")) for claim in claims if claim.get("claim_id")}
    for claim in claims:
        claim_id = str(claim.get("claim_id", ""))
        if claim_id:
            graph.add_node(claim_id)
    for relation in relations:
        left = str(relation.get("source_claim", ""))
        right = str(relation.get("target_claim", ""))
        if not left or not right or left == right or left not in claim_ids or right not in claim_ids:
            continue
        relation_type = str(relation.get("relation_type", ""))
        weight = relation_edge_weight(relation_type)
        signed = "negative" if relation_type in TENSION_RELATIONS else "positive"
        if graph.has_edge(left, right):
            graph[left][right]["weight"] += weight
            graph[left][right]["relations"].append(relation)
            if signed == "negative":
                graph[left][right]["signed"] = "negative"
        else:
            graph.add_edge(left, right, weight=weight, signed=signed, relations=[relation])
    return graph


def _claim_communities(graph: nx.Graph) -> dict[str, int]:
    if not graph.nodes:
        return {}
    if graph.number_of_edges() == 0:
        return {str(node): index for index, node in enumerate(sorted(graph.nodes))}
    communities = list(nx.algorithms.community.greedy_modularity_communities(graph, weight="weight"))
    community_map: dict[str, int] = {}
    for index, community in enumerate(sorted(communities, key=lambda nodes: (-len(nodes), sorted(nodes)[0]))):
        for node in community:
            community_map[str(node)] = index
    for node in graph.nodes:
        community_map.setdefault(str(node), len(community_map))
    return community_map


def _graph_metrics(graph: nx.Graph) -> dict[str, dict[str, float]]:
    if not graph.nodes:
        return {"pagerank": {}, "betweenness": {}, "degree": {}}
    pagerank = nx.pagerank(graph, alpha=0.85, weight="weight") if graph.number_of_edges() else {node: 1 / len(graph) for node in graph}
    betweenness = nx.betweenness_centrality(graph, weight="weight", normalized=True) if graph.number_of_edges() else {node: 0.0 for node in graph}
    degree = dict(graph.degree(weight="weight"))
    return {
        "pagerank": {str(node): round(float(value), 6) for node, value in pagerank.items()},
        "betweenness": {str(node): round(float(value), 6) for node, value in betweenness.items()},
        "degree": {str(node): round(float(value), 6) for node, value in degree.items()},
    }


def _issue_clusters(
    graph: nx.Graph,
    communities: dict[str, int],
    claims: list[dict[str, Any]],
    row_lookup: dict[str, dict[str, Any]],
    source_lookup: dict[str, str],
) -> list[dict[str, Any]]:
    claim_lookup = _claim_lookup(claims)
    grouped: dict[int, list[str]] = {}
    for claim_id, community_id in communities.items():
        grouped.setdefault(community_id, []).append(claim_id)
    clusters: list[dict[str, Any]] = []
    for community_id, claim_ids in grouped.items():
        ranked_ids = sorted(claim_ids, key=lambda claim_id: _cluster_claim_rank(graph, claim_id, row_lookup))
        representatives = [_claim_packet(claim_lookup[claim_id], row_lookup, source_lookup) for claim_id in ranked_ids[:4] if claim_id in claim_lookup]
        if not representatives:
            continue
        cluster_edges = _cluster_edges(graph, set(claim_ids))
        relation_mix = Counter(str(data.get("signed", "positive")) for _, _, data in cluster_edges)
        clusters.append(
            {
                "cluster_id": f"issue_{community_id + 1:03d}",
                "label": _cluster_label(representatives, row_lookup),
                "claim_ids": ranked_ids[:10],
                "claim_count": len(claim_ids),
                "relation_mix": dict(relation_mix),
                "dominant_roles": _dominant_claim_values(claim_ids, claim_lookup, "role"),
                "evidence_families": _dominant_row_values(claim_ids, row_lookup, "evidence_family"),
                "sources": _cluster_sources(ranked_ids, claim_lookup, source_lookup),
                "representative_claims": representatives,
                "synthesis_job": _cluster_synthesis_job(relation_mix),
            }
        )
    return sorted(clusters, key=lambda item: (-int(item["claim_count"]), str(item["cluster_id"])))[:8]


def _central_tension_edges(
    graph: nx.Graph,
    claims: list[dict[str, Any]],
    row_lookup: dict[str, dict[str, Any]],
    source_lookup: dict[str, str],
    metrics: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    claim_lookup = _claim_lookup(claims)
    tensions: list[dict[str, Any]] = []
    for left, right, data in graph.edges(data=True):
        if data.get("signed") != "negative":
            continue
        relation = _strongest_relation(data.get("relations", []), negative_only=True)
        left_id = str(left)
        right_id = str(right)
        if left_id not in claim_lookup or right_id not in claim_lookup:
            continue
        tensions.append(
            {
                "relation_id": relation.get("relation_id"),
                "relation_type": relation.get("relation_type"),
                "left": _claim_packet(claim_lookup[left_id], row_lookup, source_lookup),
                "right": _claim_packet(claim_lookup[right_id], row_lookup, source_lookup),
                "rationale": _clean_reader_text(str(relation.get("rationale", ""))),
                "why_it_matters": _relation_contract_field(relation, "why_decision_relevant"),
                "failure_condition": _relation_contract_field(relation, "failure_condition"),
                "graph_score": round(
                    float(data.get("weight", 0.0))
                    + metrics["pagerank"].get(left_id, 0.0)
                    + metrics["pagerank"].get(right_id, 0.0)
                    + metrics["betweenness"].get(left_id, 0.0)
                    + metrics["betweenness"].get(right_id, 0.0),
                    6,
                ),
            }
        )
    return sorted(tensions, key=lambda item: (-float(item["graph_score"]), str(item.get("relation_id", ""))))[:8]


def _bridge_claims(
    graph: nx.Graph,
    claims: list[dict[str, Any]],
    communities: dict[str, int],
    row_lookup: dict[str, dict[str, Any]],
    source_lookup: dict[str, str],
    metrics: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    claim_lookup = _claim_lookup(claims)
    bridges: list[dict[str, Any]] = []
    for claim_id, claim in claim_lookup.items():
        neighbor_clusters = {communities.get(str(neighbor)) for neighbor in graph.neighbors(claim_id)}
        neighbor_clusters.discard(None)
        if len(neighbor_clusters) < 2 and metrics["betweenness"].get(claim_id, 0.0) <= 0:
            continue
        packet = _claim_packet(claim, row_lookup, source_lookup)
        packet.update(
            {
                "connects_issue_count": len(neighbor_clusters),
                "betweenness": metrics["betweenness"].get(claim_id, 0.0),
                "pagerank": metrics["pagerank"].get(claim_id, 0.0),
                "synthesis_job": "Use this claim to explain how otherwise separate evidence lines interact.",
            }
        )
        bridges.append(packet)
    return sorted(bridges, key=lambda item: (-float(item["betweenness"]), -float(item["pagerank"]), str(item["claim_id"])))[:8]


def _load_bearing_claims(
    graph: nx.Graph,
    claims: list[dict[str, Any]],
    row_lookup: dict[str, dict[str, Any]],
    source_lookup: dict[str, str],
    metrics: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    claim_lookup = _claim_lookup(claims)
    rows: list[dict[str, Any]] = []
    for claim_id, claim in claim_lookup.items():
        if graph.degree(claim_id) == 0 and claim_id not in row_lookup:
            continue
        packet = _claim_packet(claim, row_lookup, source_lookup)
        packet.update(
            {
                "pagerank": metrics["pagerank"].get(claim_id, 0.0),
                "betweenness": metrics["betweenness"].get(claim_id, 0.0),
                "weighted_degree": metrics["degree"].get(claim_id, 0.0),
                "why_load_bearing": _load_bearing_reason(claim_id, graph, row_lookup, metrics),
            }
        )
        rows.append(packet)
    return sorted(
        rows,
        key=lambda item: (
            -float(item["pagerank"]),
            -float(item["weighted_degree"]),
            -_weight_rank(str(item.get("weight", "medium"))),
            str(item["claim_id"]),
        ),
    )[:10]


def _orphan_claims(
    graph: nx.Graph,
    claims: list[dict[str, Any]],
    row_lookup: dict[str, dict[str, Any]],
    source_lookup: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for claim in claims:
        claim_id = str(claim.get("claim_id", ""))
        if not claim_id or graph.degree(claim_id) > 0:
            continue
        packet = _claim_packet(claim, row_lookup, source_lookup)
        if packet.get("weight") == "low" and str(packet.get("role", "")) not in {"crux", "scope_limit", "implementation_constraint"}:
            continue
        packet["synthesis_job"] = "Use only as a caveat or appendix item unless it directly answers the decision question."
        rows.append(packet)
    return sorted(rows, key=lambda item: (-_weight_rank(str(item.get("weight", "medium"))), str(item["claim_id"])))[:8]


def _synthesis_guidance(
    issue_clusters: list[dict[str, Any]],
    central_tensions: list[dict[str, Any]],
    bridge_claims: list[dict[str, Any]],
    orphan_claims: list[dict[str, Any]],
) -> list[str]:
    guidance = [
        "Draft from issue clusters first; each major section should resolve one cluster or one cross-cluster tension.",
        "Use load-bearing and bridge claims for the main reasoning path, not isolated raw claim fragments.",
    ]
    if central_tensions:
        guidance.append("Make central negative edges visible as tensions, caveats, or cruxes before giving a bottom line.")
    if bridge_claims:
        guidance.append("Use bridge claims to explain why evidence families interact rather than listing them independently.")
    if orphan_claims:
        guidance.append("Keep orphan claims out of the main answer unless they are high-weight scope boundaries.")
    if issue_clusters:
        guidance.append("Do not ask the reader to infer the graph; name the issue clusters in human terms.")
    return guidance


def _claim_packet(claim: dict[str, Any], row_lookup: dict[str, dict[str, Any]], source_lookup: dict[str, str]) -> dict[str, Any]:
    claim_id = str(claim.get("claim_id", ""))
    row = row_lookup.get(claim_id, {})
    source_id = str(claim.get("source_id", ""))
    claim_text = str(row.get("claim") or claim.get("claim", ""))
    return {
        "claim_id": claim_id,
        "claim": _clean_reader_text(claim_text),
        "raw_claim": _clean_reader_text(str(row.get("raw_claim", "") or claim.get("claim", ""))),
        "atomic_evidence_card_id": row.get("atomic_evidence_card_id"),
        "source": source_lookup.get(source_id, _display_source_name(source_id)),
        "role": str(claim.get("role", "")),
        "weight": str(row.get("weight", "medium")),
        "section": str(row.get("section", "")),
        "evidence_family": str(row.get("evidence_family", "general_evidence")),
        "decision_concepts": [str(item) for item in row.get("decision_concepts", []) if isinstance(item, str)][:5],
    }


def _cluster_label(representatives: list[dict[str, Any]], row_lookup: dict[str, dict[str, Any]]) -> str:
    concept_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    terms: Counter[str] = Counter()
    for item in representatives:
        concept_counts.update(item.get("decision_concepts", []))
        role_counts.update([str(item.get("role", ""))])
        for term in _content_terms(str(item.get("claim", ""))):
            terms[term] += 1
    if concept_counts:
        return _human_label(concept_counts.most_common(1)[0][0])
    if role_counts:
        return _human_label(role_counts.most_common(1)[0][0])
    if terms:
        return " / ".join(term for term, _ in terms.most_common(3)).title()
    return "Issue Cluster"


def _cluster_synthesis_job(relation_mix: Counter[str]) -> str:
    if relation_mix.get("negative", 0):
        return "Resolve the cluster's internal tension before using it in the bottom-line answer."
    return "Compress this cluster into one proposition with source-backed scope and confidence."


def _cluster_edges(graph: nx.Graph, claim_ids: set[str]) -> list[tuple[str, str, dict[str, Any]]]:
    return [(left, right, data) for left, right, data in graph.edges(data=True) if left in claim_ids and right in claim_ids]


def _cluster_claim_rank(graph: nx.Graph, claim_id: str, row_lookup: dict[str, dict[str, Any]]) -> tuple[int, float, str]:
    row = row_lookup.get(claim_id, {})
    return (-_weight_rank(str(row.get("weight", "medium"))), -float(graph.degree(claim_id, weight="weight")), claim_id)


def _cluster_sources(claim_ids: list[str], claim_lookup: dict[str, dict[str, Any]], source_lookup: dict[str, str]) -> list[str]:
    sources: list[str] = []
    for claim_id in claim_ids:
        source_id = str(claim_lookup.get(claim_id, {}).get("source_id", ""))
        if source_id:
            sources.append(source_lookup.get(source_id, _display_source_name(source_id)))
    return sorted(set(sources))[:6]


def _dominant_claim_values(claim_ids: list[str], claim_lookup: dict[str, dict[str, Any]], key: str) -> list[str]:
    counts = Counter(str(claim_lookup.get(claim_id, {}).get(key, "")) for claim_id in claim_ids)
    return [value for value, _ in counts.most_common(4) if value]


def _dominant_row_values(claim_ids: list[str], row_lookup: dict[str, dict[str, Any]], key: str) -> list[str]:
    counts = Counter(str(row_lookup.get(claim_id, {}).get(key, "")) for claim_id in claim_ids)
    return [value for value, _ in counts.most_common(4) if value]


def _strongest_relation(relations: Any, *, negative_only: bool = False) -> dict[str, Any]:
    candidates = [relation for relation in relations if isinstance(relation, dict)] if isinstance(relations, list) else []
    if negative_only:
        candidates = [relation for relation in candidates if str(relation.get("relation_type", "")) in TENSION_RELATIONS]
    if not candidates:
        return {}
    return sorted(candidates, key=lambda relation: -relation_edge_weight(str(relation.get("relation_type", ""))))[0]


def _relation_contract_field(relation: dict[str, Any], key: str) -> str:
    contract = relation.get("relation_contract", {}) if isinstance(relation.get("relation_contract"), dict) else {}
    return _clean_reader_text(str(contract.get(key, "")))


def _load_bearing_reason(
    claim_id: str,
    graph: nx.Graph,
    row_lookup: dict[str, dict[str, Any]],
    metrics: dict[str, dict[str, float]],
) -> str:
    if metrics["betweenness"].get(claim_id, 0.0) > 0:
        return "It connects otherwise separate parts of the evidence graph."
    if graph.degree(claim_id, weight="weight") >= 3:
        return "Multiple relations depend on or point through this claim."
    if row_lookup.get(claim_id, {}).get("weight") == "high":
        return "It is high-weight evidence in the deterministic evidence ledger."
    return "It is connected enough to affect synthesis order."


def _ledger_row_lookup(evidence_ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = evidence_ledger.get("all_evidence", []) if isinstance(evidence_ledger, dict) else []
    lookup: dict[str, dict[str, Any]] = {}
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and row.get("claim_id"):
            lookup[str(row["claim_id"])] = row
    return lookup


def _claim_lookup(claims: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(claim.get("claim_id", "")): claim for claim in claims if claim.get("claim_id")}


def _claims(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    claims = candidate_map.get("claims", [])
    return [claim for claim in claims if isinstance(claim, dict)] if isinstance(claims, list) else []


def _relations(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    relations = candidate_map.get("relations", [])
    return [relation for relation in relations if isinstance(relation, dict)] if isinstance(relations, list) else []


def _weight_rank(weight: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(weight, 2)


def _display_source_name(source_id: str) -> str:
    return source_id.replace("_", " ").replace("-", " ").title() if source_id else ""


def _human_label(value: str) -> str:
    return value.replace("_", " ").replace(" or ", " / ").title()


def _clean_reader_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = re.sub(r"\bClaim [AB]\b[^.]*\.\s*", "", cleaned)
    cleaned = cleaned.replace("This relation marks", "This evidence marks")
    return cleaned[:420].rstrip(" ,;") + ("..." if len(cleaned) > 420 else "")


def _content_terms(text: str) -> list[str]:
    stop = {
        "about",
        "after",
        "because",
        "between",
        "claim",
        "evidence",
        "found",
        "should",
        "source",
        "study",
        "their",
        "there",
        "these",
        "those",
        "which",
        "would",
    }
    return [word for word in re.findall(r"[A-Za-z][A-Za-z-]{3,}", text.lower()) if word not in stop][:12]
