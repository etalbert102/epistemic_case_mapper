from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.classical_ml import tfidf_near_duplicate_pairs


def near_duplicate_claim_pairs(claims: list[dict[str, Any]]) -> list[tuple[str, str]]:
    ids = [str(claim.get("claim_id", "")) for claim in claims]
    texts = [str(claim.get("claim", "") or claim.get("text", "")) for claim in claims]
    claim_lookup = {str(claim.get("claim_id", "")): claim for claim in claims}
    pair_scores = {
        (left, right): score
        for left, right, score in tfidf_near_duplicate_pairs(texts, ids, threshold=0.35)
        if left and right and duplicate_pair_can_merge(claim_lookup.get(left, {}), claim_lookup.get(right, {}))
    }
    for left_index, left in enumerate(claims):
        for right in claims[left_index + 1 :]:
            pair = (str(left.get("claim_id", "")), str(right.get("claim_id", "")))
            if _text_overlap_ratio(str(left.get("claim", "")), str(right.get("claim", ""))) >= 0.78 and duplicate_pair_can_merge(left, right):
                pair_scores.setdefault(pair, 1.0)
    return list(pair_scores)


def lexically_similar_opposite_direction_pairs(claims: list[dict[str, Any]]) -> list[tuple[str, str]]:
    pairs: dict[tuple[str, str], float] = {}
    for left_index, left in enumerate(claims):
        for right in claims[left_index + 1 :]:
            left_id = str(left.get("claim_id", ""))
            right_id = str(right.get("claim_id", ""))
            if not left_id or not right_id:
                continue
            left_polarity = claim_polarity(str(left.get("claim", "")))
            right_polarity = claim_polarity(str(right.get("claim", "")))
            if "mixed" in {left_polarity, right_polarity} or left_polarity == right_polarity:
                continue
            overlap = _text_overlap_ratio(str(left.get("claim", "")), str(right.get("claim", "")))
            if overlap >= 0.74:
                pairs[(left_id, right_id)] = overlap
    return [pair for pair, _score in sorted(pairs.items(), key=lambda row: (-row[1], row[0]))]


def duplicate_pair_can_merge(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if not left or not right:
        return False
    left_polarity = claim_polarity(str(left.get("claim", "")))
    right_polarity = claim_polarity(str(right.get("claim", "")))
    if "mixed" in {left_polarity, right_polarity} and left_polarity != right_polarity:
        return False
    if left_polarity != "mixed" and right_polarity != "mixed" and left_polarity != right_polarity:
        return False
    return role_family(str(left.get("role", "other"))) == role_family(str(right.get("role", "other")))


def claim_polarity(text: str) -> str:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    positive = any(marker in normalized for marker in (" lower risk ", " reduced risk ", " no association ", " not associated ", " no adverse ", " did not have adverse ", " beneficial "))
    negative = any(marker in normalized for marker in (" higher risk ", " increased risk ", " harmful ", " adverse effect ", " adverse effects ", " mortality ", " concern "))
    if positive and not negative:
        return "positive_or_null"
    if negative and not positive:
        return "negative_or_concern"
    return "mixed"


def role_family(role: str) -> str:
    return {
        "conclusion_support": "directional",
        "crux": "crux",
        "scope_limit": "limit",
        "external_validity": "limit",
        "measurement_validity": "method",
        "implementation_constraint": "method",
        "cost_feasibility": "method",
        "background": "background",
        "other": "other",
    }.get(role, role)


def _text_overlap_ratio(left: str, right: str) -> float:
    left_terms = _content_terms(left)
    right_terms = _content_terms(right)
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / min(len(left_terms), len(right_terms))


def _content_terms(text: str) -> set[str]:
    stopwords = {"about", "after", "also", "and", "are", "but", "for", "from", "has", "have", "into", "not", "that", "the", "their", "this", "with"}
    return {token for token in re.findall(r"[a-z0-9]{3,}", text.lower()) if token not in stopwords}
