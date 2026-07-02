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
    }.get(relation_type, 1.0)

