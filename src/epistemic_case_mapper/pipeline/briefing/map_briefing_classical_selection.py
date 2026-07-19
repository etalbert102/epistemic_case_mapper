from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from epistemic_case_mapper.classical_ml import relation_edge_weight, tfidf_near_duplicate_pairs, weighted_pagerank


def build_classical_evidence_selection_report(
    candidate_map: dict[str, Any],
    scaffold: dict[str, Any],
    *,
    question: str,
) -> dict[str, Any]:
    claims = _claims(candidate_map)
    cards = _candidate_cards(scaffold)
    centrality = _claim_centrality(candidate_map, claims)
    duplicate_pairs = _duplicate_pairs(claims)
    clusters = _duplicate_clusters(duplicate_pairs)
    relevance = _claim_question_relevance(claims, question)
    coverage = _coverage_balance(scaffold, cards)
    quantity_outliers = _quantity_outliers(scaffold)
    features = _selection_features(
        cards=cards,
        relevance=relevance,
        centrality=centrality,
        clusters=clusters,
        coverage=coverage,
        quantity_outliers=quantity_outliers,
    )
    return {
        "schema_id": "classical_evidence_selection_report_v1",
        "method": "tfidf_relevance_duplicate_clusters_weighted_graph_centrality_coverage_quantity_outliers",
        "claim_cluster_report": {
            "schema_id": "claim_cluster_report_v1",
            "duplicate_pair_count": len(duplicate_pairs),
            "duplicate_pairs": [
                {"left": left, "right": right, "score": score}
                for left, right, score in duplicate_pairs[:80]
            ],
            "clusters": _cluster_rows(clusters),
        },
        "evidence_centrality_report": {
            "schema_id": "evidence_centrality_report_v1",
            "claim_scores": centrality,
            "top_claim_ids": [claim_id for claim_id, _score in sorted(centrality.items(), key=lambda item: (-item[1], item[0]))[:20]],
        },
        "coverage_balance_report": coverage,
        "quantity_outlier_report": quantity_outliers,
        "selection_features": features,
        "issues": _classical_selection_issues(cards, centrality, coverage),
    }


def _claims(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    return [claim for claim in candidate_map.get("claims", []) if isinstance(claim, dict)] if isinstance(candidate_map.get("claims"), list) else []


def _candidate_cards(scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    report = scaffold.get("candidate_evidence_cards", {}) if isinstance(scaffold.get("candidate_evidence_cards"), dict) else {}
    return [card for card in report.get("cards", []) if isinstance(card, dict)] if isinstance(report.get("cards"), list) else []


def _claim_centrality(candidate_map: dict[str, Any], claims: list[dict[str, Any]]) -> dict[str, float]:
    claim_ids = [str(claim.get("claim_id", "")).strip() for claim in claims if str(claim.get("claim_id", "")).strip()]
    edges = []
    for relation in candidate_map.get("relations", []) if isinstance(candidate_map.get("relations"), list) else []:
        if not isinstance(relation, dict):
            continue
        left = str(relation.get("source_claim") or relation.get("from") or "").strip()
        right = str(relation.get("target_claim") or relation.get("to") or "").strip()
        relation_type = str(relation.get("relation_type", "")).strip()
        if left and right:
            edges.append((left, right, relation_edge_weight(relation_type)))
    return weighted_pagerank(claim_ids, edges) if edges else {claim_id: 0.0 for claim_id in claim_ids}


def _duplicate_pairs(claims: list[dict[str, Any]]) -> list[tuple[str, str, float]]:
    ids = [str(claim.get("claim_id", "")).strip() for claim in claims]
    texts = [str(claim.get("claim") or claim.get("text") or "").strip() for claim in claims]
    rows = [(claim_id, text) for claim_id, text in zip(ids, texts, strict=False) if claim_id and text]
    pairs = {
        tuple(sorted((left, right))): score
        for left, right, score in tfidf_near_duplicate_pairs([text for _claim_id, text in rows], [claim_id for claim_id, _text in rows], threshold=0.48)
    }
    for left_index, (left_id, left_text) in enumerate(rows):
        for right_id, right_text in rows[left_index + 1:]:
            score = _normalized_token_overlap(left_text, right_text)
            if score >= 0.62:
                key = tuple(sorted((left_id, right_id)))
                pairs[key] = max(pairs.get(key, 0.0), score)
    return [(left, right, round(score, 4)) for (left, right), score in sorted(pairs.items())]


def _duplicate_clusters(pairs: list[tuple[str, str, float]]) -> dict[str, str]:
    parent: dict[str, str] = {}
    for left, right, _score in pairs:
        _union(parent, left, right)
    return {claim_id: _find(parent, claim_id) for pair in pairs for claim_id in pair[:2]}


def _claim_question_relevance(claims: list[dict[str, Any]], question: str) -> dict[str, float]:
    rows = [
        (str(claim.get("claim_id", "")).strip(), str(claim.get("claim") or claim.get("text") or "").strip())
        for claim in claims
    ]
    rows = [(claim_id, text) for claim_id, text in rows if claim_id and text]
    if not rows or not question.strip():
        return {claim_id: 0.0 for claim_id, _text in rows}
    vectorizer = TfidfVectorizer(stop_words=list(set(ENGLISH_STOP_WORDS)), ngram_range=(1, 2), min_df=1)
    try:
        matrix = vectorizer.fit_transform([question, *[text for _claim_id, text in rows]])
    except ValueError:
        return {claim_id: 0.0 for claim_id, _text in rows}
    sims = cosine_similarity(matrix[0], matrix[1:]).flatten()
    return {claim_id: round(float(score), 4) for (claim_id, _text), score in zip(rows, sims, strict=False)}


def _coverage_balance(scaffold: dict[str, Any], cards: list[dict[str, Any]]) -> dict[str, Any]:
    ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    rows = [row for row in ledger.get("all_evidence", []) if isinstance(row, dict)] if isinstance(ledger.get("all_evidence"), list) else []
    source_counts = Counter(source for card in cards for source in _string_list(card.get("source_ids")))
    family_counts = Counter(str(row.get("evidence_family", "unknown")) for row in rows)
    concept_counts = Counter(concept for row in rows for concept in _string_list(row.get("decision_concepts")))
    return {
        "schema_id": "coverage_balance_report_v1",
        "source_counts": dict(sorted(source_counts.items())),
        "evidence_family_counts": dict(sorted(family_counts.items())),
        "decision_concept_counts": dict(sorted(concept_counts.items())),
        "single_source_warning": len(source_counts) == 1 and sum(source_counts.values()) > 1,
        "missing_major_dimensions": _missing_major_dimensions(family_counts, concept_counts),
    }


def _quantity_outliers(scaffold: dict[str, Any]) -> dict[str, Any]:
    ledger = scaffold.get("quantity_ledger", {}) if isinstance(scaffold.get("quantity_ledger"), dict) else {}
    quantities = []
    for row in ledger.get("quantities", []) if isinstance(ledger.get("quantities"), list) else []:
        if isinstance(row, dict):
            quantities.append(str(row.get("normalized") or row.get("value") or row.get("quantity") or "").strip())
    counts = Counter(quantity for quantity in quantities if quantity)
    outliers = [{"quantity": quantity, "count": count} for quantity, count in sorted(counts.items()) if count == 1]
    return {
        "schema_id": "quantity_outlier_report_v1",
        "quantity_count": len(quantities),
        "unique_quantity_count": len(counts),
        "outlier_count": len(outliers),
        "outliers": outliers[:40],
    }


def _selection_features(
    *,
    cards: list[dict[str, Any]],
    relevance: dict[str, float],
    centrality: dict[str, float],
    clusters: dict[str, str],
    coverage: dict[str, Any],
    quantity_outliers: dict[str, Any],
) -> list[dict[str, Any]]:
    outlier_values = {str(row.get("quantity")) for row in quantity_outliers.get("outliers", []) if isinstance(row, dict)}
    features = []
    for card in cards:
        claim_ids = _string_list(card.get("claim_ids"))
        centrality_score = max((centrality.get(claim_id, 0.0) for claim_id in claim_ids), default=0.0)
        relevance_score = max((relevance.get(claim_id, 0.0) for claim_id in claim_ids), default=0.0)
        quantity_values = _string_list(card.get("quantity_values"))
        features.append(
            {
                "candidate_card_id": card.get("candidate_card_id"),
                "claim_ids": claim_ids,
                "source_ids": _string_list(card.get("source_ids")),
                "role": card.get("role"),
                "question_relevance_score": relevance_score,
                "graph_centrality_score": centrality_score,
                "duplicate_cluster_ids": sorted({clusters[claim_id] for claim_id in claim_ids if claim_id in clusters}),
                "quantity_outlier_values": [value for value in quantity_values if value in outlier_values],
                "coverage_contribution": _coverage_contribution(card, coverage),
                "advisory_rank_score": _advisory_rank_score(card, relevance_score, centrality_score),
            }
        )
    return sorted(features, key=lambda row: (-float(row["advisory_rank_score"]), str(row.get("candidate_card_id", ""))))


def _coverage_contribution(card: dict[str, Any], coverage: dict[str, Any]) -> dict[str, int]:
    source_ids = _string_list(card.get("source_ids"))
    source_counts = coverage.get("source_counts", {}) if isinstance(coverage.get("source_counts"), dict) else {}
    return {"rare_source_count": sum(1 for source_id in source_ids if int(source_counts.get(source_id, 0)) <= 1)}


def _advisory_rank_score(card: dict[str, Any], relevance_score: float, centrality_score: float) -> float:
    decision_score = int(card.get("decision_relevance_score", 0) or 0) / 10
    quality_bonus = {"usable": 0.12, "weak": -0.04, "indirect": -0.08, "unknown": -0.02}.get(str(card.get("quality", "")), 0.0)
    appendix_penalty = -0.3 if card.get("inclusion_recommendation") == "appendix_only" else 0.0
    return round(decision_score + relevance_score + centrality_score + quality_bonus + appendix_penalty, 4)


def _missing_major_dimensions(family_counts: Counter[str], concept_counts: Counter[str]) -> list[str]:
    missing = []
    if not any("cohort" in family or "outcome" in family for family in family_counts):
        missing.append("direct_or_observational_outcome_family")
    if not any("mechanism" in concept or "surrogate" in concept for concept in concept_counts):
        missing.append("mechanism_or_proxy_concepts")
    if not any("comparator" in concept or "substitution" in concept for concept in concept_counts):
        missing.append("comparator_or_substitution_concepts")
    return missing


def _classical_selection_issues(cards: list[dict[str, Any]], centrality: dict[str, float], coverage: dict[str, Any]) -> list[str]:
    issues = []
    if not cards:
        issues.append("no_candidate_cards_for_classical_selection")
    if not any(score > 0 for score in centrality.values()) and len(centrality) > 1:
        issues.append("no_relation_centrality_signal")
    if coverage.get("single_source_warning"):
        issues.append("candidate_pool_uses_single_source")
    return issues


def _cluster_rows(clusters: dict[str, str]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for claim_id, cluster_id in clusters.items():
        grouped[cluster_id].append(claim_id)
    return [
        {"cluster_id": cluster_id, "claim_ids": sorted(claim_ids)}
        for cluster_id, claim_ids in sorted(grouped.items())
        if len(claim_ids) > 1
    ]


def _find(parent: dict[str, str], item: str) -> str:
    parent.setdefault(item, item)
    if parent[item] != item:
        parent[item] = _find(parent, parent[item])
    return parent[item]


def _union(parent: dict[str, str], left: str, right: str) -> None:
    root_left, root_right = _find(parent, left), _find(parent, right)
    if root_left != root_right:
        parent[max(root_left, root_right)] = min(root_left, root_right)


def _normalized_token_overlap(left: str, right: str) -> float:
    left_terms = _normalized_terms(left)
    right_terms = _normalized_terms(right)
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / max(1, min(len(left_terms), len(right_terms)))


def _normalized_terms(text: str) -> set[str]:
    terms = set()
    for term in re.findall(r"[a-z0-9]+", text.lower()):
        if len(term) < 4 or term in ENGLISH_STOP_WORDS:
            continue
        terms.add(_light_stem(term))
    return terms


def _light_stem(term: str) -> str:
    for suffix in ("ing", "ized", "ised", "ed", "es", "s"):
        if len(term) > len(suffix) + 3 and term.endswith(suffix):
            return term[: -len(suffix)]
    return term


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
