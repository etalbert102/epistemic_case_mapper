from __future__ import annotations

from typing import Iterable

import networkx as nx
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


STOPWORDS = set(ENGLISH_STOP_WORDS) | {
    "claim",
    "claims",
    "evidence",
    "source",
    "sources",
}


def tfidf_near_duplicate_pairs(
    texts: list[str],
    ids: list[str],
    *,
    threshold: float = 0.74,
) -> list[tuple[str, str, float]]:
    if len(texts) != len(ids):
        raise ValueError("texts and ids must have the same length")
    if len(texts) < 2:
        return []
    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words=list(STOPWORDS),
        ngram_range=(1, 2),
        min_df=1,
        norm="l2",
    )
    try:
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        return []
    similarities = cosine_similarity(matrix)
    pairs: list[tuple[str, str, float]] = []
    for left_index in range(len(texts)):
        for right_index in range(left_index + 1, len(texts)):
            score = float(similarities[left_index, right_index])
            if score >= threshold:
                pairs.append((ids[left_index], ids[right_index], round(score, 4)))
    return pairs


def tfidf_pair_similarities(
    texts: list[str],
    ids: list[str],
) -> dict[tuple[str, str], float]:
    if len(texts) != len(ids):
        raise ValueError("texts and ids must have the same length")
    if len(texts) < 2:
        return {}
    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words=list(STOPWORDS),
        ngram_range=(1, 2),
        min_df=1,
        norm="l2",
    )
    try:
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        return {}
    similarities = cosine_similarity(matrix)
    pairs: dict[tuple[str, str], float] = {}
    for left_index in range(len(texts)):
        for right_index in range(left_index + 1, len(texts)):
            score = float(similarities[left_index, right_index])
            left_id, right_id = sorted((ids[left_index], ids[right_index]))
            pairs[(left_id, right_id)] = round(score, 4)
    return pairs


def diverse_ranked_edges(
    node_ids: list[str],
    scored_edges: list[tuple[str, str, float, str]],
    *,
    limit: int,
) -> list[tuple[str, str, float, str]]:
    if limit <= 0:
        return []
    ranked = sorted(scored_edges, key=lambda item: (-item[2], item[0], item[1], item[3]))
    selected: list[tuple[str, str, float, str]] = []
    selected_keys: set[tuple[str, str]] = set()
    touched: set[str] = set()
    while len(selected) < limit:
        candidates = [edge for edge in ranked if _edge_key(edge) not in selected_keys]
        if not candidates:
            break
        edge = max(candidates, key=lambda item: (_new_endpoint_count(item, touched), item[2], item[0], item[1]))
        if _new_endpoint_count(edge, touched) == 0:
            break
        _append_edge(edge, selected, selected_keys, touched)
    for edge in ranked:
        if len(selected) >= limit:
            break
        if _edge_key(edge) not in selected_keys:
            _append_edge(edge, selected, selected_keys, touched)
    for node_id in node_ids:
        if len(selected) >= limit:
            break
        if node_id in touched:
            continue
        for edge in ranked:
            if node_id in edge[:2] and _edge_key(edge) not in selected_keys:
                _append_edge(edge, selected, selected_keys, touched)
                break
    return selected


def _append_edge(
    edge: tuple[str, str, float, str],
    selected: list[tuple[str, str, float, str]],
    selected_keys: set[tuple[str, str]],
    touched: set[str],
) -> None:
    key = _edge_key(edge)
    if key in selected_keys:
        return
    selected.append(edge)
    selected_keys.add(key)
    touched.update(key)


def _edge_key(edge: tuple[str, str, float, str]) -> tuple[str, str]:
    left, right = edge[:2]
    return tuple(sorted((left, right)))


def _new_endpoint_count(edge: tuple[str, str, float, str], touched: set[str]) -> int:
    left, right = edge[:2]
    return int(left not in touched) + int(right not in touched)


def weighted_pagerank(
    node_ids: Iterable[str],
    edges: Iterable[tuple[str, str, float]],
    *,
    damping: float = 0.85,
    iterations: int = 100,
) -> dict[str, float]:
    graph = nx.Graph()
    graph.add_nodes_from(node for node in node_ids if node)
    for left, right, weight in edges:
        if not left or not right or left == right:
            continue
        edge_weight = max(float(weight), 0.0)
        if edge_weight <= 0:
            continue
        previous = graph[left][right]["weight"] if graph.has_edge(left, right) else 0.0
        graph.add_edge(left, right, weight=previous + edge_weight)
    if not graph.nodes:
        return {}
    ranks = nx.pagerank(graph, alpha=damping, max_iter=iterations, weight="weight")
    return {node: round(float(score), 6) for node, score in ranks.items()}


def relation_edge_weight(relation_type: str) -> float:
    return {
        "crux_for": 3.0,
        "in_tension_with": 2.6,
        "challenges": 2.4,
        "depends_on": 2.2,
        "refines": 1.4,
        "supports": 1.2,
        "similar_to": 0.8,
        "contextualizes": 0.7,
    }.get(relation_type, 1.0)
