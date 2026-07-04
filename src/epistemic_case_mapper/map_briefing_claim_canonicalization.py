from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from epistemic_case_mapper.classical_ml import tfidf_near_duplicate_pairs


ROLE_PRIORITY = {
    "crux": 0,
    "scope_limit": 1,
    "external_validity": 1,
    "measurement_validity": 1,
    "implementation_constraint": 2,
    "cost_feasibility": 2,
    "conclusion_support": 3,
    "background": 4,
    "other": 5,
}


def canonicalize_claims_for_briefing(candidate_map: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    claims = [claim for claim in candidate_map.get("claims", []) if isinstance(claim, dict)]
    relations = [relation for relation in candidate_map.get("relations", []) if isinstance(relation, dict)]
    fragment_rows = [_fragment_row(claim) for claim in claims]
    severe_fragment_ids = {
        row["claim_id"]
        for row in fragment_rows
        if row["severity"] == "drop" and row["claim_id"]
    }
    duplicate_pairs = tfidf_near_duplicate_pairs(
        [_canonical_text(str(claim.get("claim") or claim.get("text") or "")) for claim in claims if str(claim.get("claim_id", "")).strip()],
        [str(claim.get("claim_id", "")).strip() for claim in claims if str(claim.get("claim_id", "")).strip()],
        threshold=0.62,
    )
    duplicate_groups = _duplicate_groups(duplicate_pairs, severe_fragment_ids)
    representative_for: dict[str, str] = {claim_id: claim_id for claim_id in _claim_ids(claims)}
    duplicate_group_rows = []
    claim_lookup = {str(claim.get("claim_id")): claim for claim in claims}
    for group in duplicate_groups:
        representative = _representative_claim_id(group, claim_lookup, severe_fragment_ids)
        for claim_id in group:
            representative_for[claim_id] = representative
        duplicate_group_rows.append(
            {
                "representative_claim_id": representative,
                "merged_claim_ids": [claim_id for claim_id in group if claim_id != representative],
                "all_claim_ids": group,
            }
        )
    kept_claims = []
    dropped_ids: set[str] = set(severe_fragment_ids)
    for claim in claims:
        claim_id = str(claim.get("claim_id", "")).strip()
        if not claim_id or claim_id in severe_fragment_ids:
            continue
        if representative_for.get(claim_id, claim_id) != claim_id:
            dropped_ids.add(claim_id)
            continue
        merged_ids = [other_id for other_id, rep_id in representative_for.items() if rep_id == claim_id and other_id != claim_id]
        kept_claims.append(_with_canonical_metadata(claim, merged_ids, claim_lookup))
    relation_result = _canonicalize_relations(relations, representative_for, severe_fragment_ids)
    canonicalized = dict(candidate_map)
    canonicalized["claims"] = kept_claims
    canonicalized["relations"] = relation_result["relations"]
    report = {
        "schema_id": "claim_canonicalization_report_v1",
        "changed": len(kept_claims) != len(claims) or relation_result["rewritten_relation_count"] > 0,
        "original_claim_count": len(claims),
        "canonical_claim_count": len(kept_claims),
        "dropped_fragment_claim_ids": sorted(severe_fragment_ids),
        "fragment_claims": fragment_rows,
        "duplicate_claim_pairs": [
            {"left": left, "right": right, "score": score}
            for left, right, score in duplicate_pairs
        ],
        "merged_duplicate_groups": duplicate_group_rows,
        "claim_id_rewrites": {
            claim_id: rep_id
            for claim_id, rep_id in sorted(representative_for.items())
            if claim_id != rep_id
        },
        "original_relation_count": len(relations),
        "canonical_relation_count": len(relation_result["relations"]),
        "rewritten_relation_count": relation_result["rewritten_relation_count"],
        "dropped_relation_ids": relation_result["dropped_relation_ids"],
    }
    return canonicalized, report


def _claim_ids(claims: list[dict[str, Any]]) -> list[str]:
    return [str(claim.get("claim_id", "")).strip() for claim in claims if str(claim.get("claim_id", "")).strip()]


def _fragment_row(claim: dict[str, Any]) -> dict[str, Any]:
    claim_id = str(claim.get("claim_id", "")).strip()
    text = str(claim.get("claim") or claim.get("text") or "").strip()
    markers = _fragment_markers(text)
    severity = "drop" if markers and _low_information_fragment(text) else "warn" if markers else "none"
    return {"claim_id": claim_id, "severity": severity, "markers": markers}


def _fragment_markers(text: str) -> list[str]:
    lowered = text.lower()
    markers = []
    for marker in ("...", "no. (%)", "pmcid:", "[google scholar]", "respectively. in", "copyright", "all rights reserved"):
        if marker in lowered:
            markers.append(marker)
    if re.match(r"^[,;:)\]]", text):
        markers.append("starts_with_punctuation")
    if re.match(r"^[a-z][a-z-]{0,15}\s", text) and len(_content_terms(text)) < 6:
        markers.append("lowercase_fragment_start")
    return markers


def _low_information_fragment(text: str) -> bool:
    terms = _content_terms(text)
    if len(terms) < 5:
        return True
    lowered = text.lower()
    if any(marker in lowered for marker in ("pmcid:", "[google scholar]", "copyright", "all rights reserved")):
        return True
    if "..." in text and len(terms) < 8:
        return True
    if "respectively. in" in lowered and len(terms) < 9:
        return True
    return False


def _duplicate_groups(pairs: list[tuple[str, str, float]], dropped_ids: set[str]) -> list[list[str]]:
    parent: dict[str, str] = {}

    def find(item: str) -> str:
        parent.setdefault(item, item)
        if parent[item] != item:
            parent[item] = find(parent[item])
        return parent[item]

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left, right, _score in pairs:
        if left in dropped_ids or right in dropped_ids:
            continue
        union(left, right)
    groups: dict[str, list[str]] = defaultdict(list)
    for claim_id in parent:
        groups[find(claim_id)].append(claim_id)
    return [sorted(group) for group in groups.values() if len(group) > 1]


def _representative_claim_id(group: list[str], claim_lookup: dict[str, dict[str, Any]], dropped_ids: set[str]) -> str:
    candidates = [claim_lookup[claim_id] for claim_id in group if claim_id in claim_lookup and claim_id not in dropped_ids]
    return str(min(candidates, key=_representative_rank).get("claim_id"))


def _representative_rank(claim: dict[str, Any]) -> tuple[int, int, int, str]:
    text = str(claim.get("claim") or claim.get("text") or "")
    return (
        ROLE_PRIORITY.get(str(claim.get("role", "other")), ROLE_PRIORITY["other"]),
        0 if _has_number(text) else 1,
        -len(_content_terms(text)),
        str(claim.get("claim_id", "")),
    )


def _with_canonical_metadata(claim: dict[str, Any], merged_ids: list[str], claim_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not merged_ids:
        return dict(claim)
    merged_sources = {
        str(claim_lookup.get(claim_id, {}).get("source_id", "")).strip()
        for claim_id in [str(claim.get("claim_id", "")), *merged_ids]
    } - {""}
    return {
        **claim,
        "canonicalized_from_claim_ids": [str(claim.get("claim_id", "")), *merged_ids],
        "merged_duplicate_claim_ids": merged_ids,
        "canonical_source_ids": sorted(merged_sources),
    }


def _canonicalize_relations(relations: list[dict[str, Any]], representative_for: dict[str, str], dropped_ids: set[str]) -> dict[str, Any]:
    kept = []
    seen: set[tuple[str, str, str]] = set()
    rewritten_count = 0
    dropped_relation_ids = []
    for relation in relations:
        source = str(relation.get("source_claim", "")).strip()
        target = str(relation.get("target_claim", "")).strip()
        relation_id = str(relation.get("relation_id", "")).strip()
        if source in dropped_ids or target in dropped_ids:
            dropped_relation_ids.append(relation_id)
            continue
        new_source = representative_for.get(source, source)
        new_target = representative_for.get(target, target)
        if new_source == new_target:
            dropped_relation_ids.append(relation_id)
            continue
        key = (new_source, new_target, str(relation.get("relation_type", "")))
        if key in seen:
            dropped_relation_ids.append(relation_id)
            continue
        seen.add(key)
        updated = dict(relation)
        if new_source != source or new_target != target:
            updated["source_claim"] = new_source
            updated["target_claim"] = new_target
            updated["canonicalized_from_relation_id"] = relation_id
            rewritten_count += 1
        kept.append(updated)
    return {"relations": kept, "rewritten_relation_count": rewritten_count, "dropped_relation_ids": dropped_relation_ids}


def _canonical_text(text: str) -> str:
    cleaned = re.sub(r"\([^)]*(?:CI|confidence interval|p\s*[<=>])[^)]*\)", " ", text, flags=re.I)
    cleaned = re.sub(r"\b\d+(?:\.\d+)?\b", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned.lower()).strip()


def _content_terms(text: str) -> list[str]:
    stop = {"the", "and", "that", "with", "from", "this", "these", "those", "were", "was", "are", "for", "into", "than"}
    return [term for term in re.findall(r"[a-z0-9]{3,}", text.lower()) if term not in stop]


def _has_number(text: str) -> bool:
    return bool(re.search(r"\b\d|%|\bHR\b|\bRR\b|\bCI\b", text, flags=re.I))
