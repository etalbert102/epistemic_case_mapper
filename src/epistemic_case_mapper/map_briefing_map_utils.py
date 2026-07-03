from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from epistemic_case_mapper.classical_ml import (
    relation_edge_weight,
    tfidf_near_duplicate_pairs,
    weighted_pagerank,
)
from epistemic_case_mapper.config_profiles import (
    DEFAULT_PROFILE_ID,
    infer_profile_id_from_text,
    profile_vocabulary,
)
from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.model_backends import run_model_backend

def expand_reader_map_references(text: str, candidate_map: dict[str, Any]) -> str:
    claim_lookup = _claim_alias_lookup(candidate_map)
    relation_lookup = _relation_alias_lookup(candidate_map, claim_lookup)
    expanded = text
    expanded = re.sub(
        r"\s*\(([cCrR]\d{3,})\)",
        lambda match: "" if match.group(1).lower() in {key.lower() for key in (*claim_lookup, *relation_lookup)} else match.group(0),
        expanded,
    )
    expanded = _expand_claim_sentence_references(expanded, claim_lookup)
    expanded = _expand_relation_sentence_references(expanded, relation_lookup)
    expanded = re.sub(
        r"\b[Cc]laim\s+([A-Za-z0-9_\-]*_?c\d{3,})\b",
        lambda match: _claim_reference_phrase(match.group(1), claim_lookup),
        expanded,
    )
    expanded = re.sub(
        r"\b[Rr]elation\s+([A-Za-z0-9_\-]*_?r\d{3,})\b",
        lambda match: _relation_reference_phrase(match.group(1), relation_lookup),
        expanded,
    )
    expanded = re.sub(
        r"`?([A-Za-z0-9_\-]+_c\d{3,}|[cC]\d{3,})`?",
        lambda match: claim_lookup.get(match.group(1)) or claim_lookup.get(match.group(1).lower()) or match.group(0),
        expanded,
    )
    expanded = re.sub(
        r"`?([A-Za-z0-9_\-]+_r\d{3,}|[rR]\d{3,})`?",
        lambda match: relation_lookup.get(match.group(1)) or relation_lookup.get(match.group(1).lower()) or match.group(0),
        expanded,
    )
    return re.sub(r"\s+", " ", expanded) if "\n" not in expanded else "\n".join(
        re.sub(r"[ \t]+", " ", line).rstrip() for line in expanded.splitlines()
    )

def _expand_payload_reader_references(value: Any, candidate_map: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return expand_reader_map_references(value, candidate_map)
    if isinstance(value, list):
        return [_expand_payload_reader_references(item, candidate_map) for item in value]
    if isinstance(value, dict):
        return {
            key: item if key in _STRUCTURED_ID_FIELDS else _expand_payload_reader_references(item, candidate_map)
            for key, item in value.items()
        }
    return value


_STRUCTURED_ID_FIELDS = {
    "claim_id",
    "claim_ids",
    "relation_id",
    "relation_ids",
    "source_claim",
    "target_claim",
    "pair_id",
}

def _claim_alias_lookup(candidate_map: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for claim in _claims(candidate_map):
        claim_id = str(claim.get("claim_id", "")).strip()
        claim_text = str(claim.get("claim") or claim.get("text") or "").strip()
        if not claim_id or not claim_text:
            continue
        aliases = {claim_id}
        suffix = claim_id.rsplit("_", 1)[-1]
        if re.fullmatch(r"c\d{3,}", suffix):
            aliases.update({suffix, suffix.upper()})
        for alias in aliases:
            lookup[alias] = claim_text
            lookup[alias.lower()] = claim_text
    return lookup

def _relation_alias_lookup(candidate_map: dict[str, Any], claim_lookup: dict[str, str]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for relation in _relations(candidate_map):
        relation_id = str(relation.get("relation_id", "")).strip()
        relation_text = str(relation.get("rationale", "")).strip()
        if not relation_text:
            left = claim_lookup.get(str(relation.get("source_claim", "")).lower(), "")
            right = claim_lookup.get(str(relation.get("target_claim", "")).lower(), "")
            relation_type = str(relation.get("relation_type", "")).replace("_", " ")
            relation_text = " ".join(part for part in (left, relation_type, right) if part)
        if not relation_id or not relation_text:
            continue
        relation_text = expand_reader_map_references(relation_text, {"claims": _claims(candidate_map), "relations": []})
        aliases = {relation_id}
        suffix = relation_id.rsplit("_", 1)[-1]
        if re.fullmatch(r"r\d{3,}", suffix):
            aliases.update({suffix, suffix.upper()})
        for alias in aliases:
            lookup[alias] = relation_text
            lookup[alias.lower()] = relation_text
    return lookup

def _expand_claim_sentence_references(text: str, claim_lookup: dict[str, str]) -> str:
    verbs = (
        "acts",
        "challenges",
        "clarifies",
        "creates",
        "defines",
        "establishes",
        "expands",
        "introduces",
        "limits",
        "provides",
        "qualifies",
        "questions",
        "refines",
        "reinforces",
        "specifies",
        "supports",
    )
    verb_pattern = "|".join(verbs)
    return re.sub(
        rf"\b[Cc]laim\s+([A-Za-z0-9_\-]*_?c\d{{3,}})\s+({verb_pattern})([^.\n]*)(\.)?",
        lambda match: _claim_sentence_replacement(match, claim_lookup),
        text,
    )

def _claim_sentence_replacement(match: re.Match[str], claim_lookup: dict[str, str]) -> str:
    claim = claim_lookup.get(match.group(1)) or claim_lookup.get(match.group(1).lower())
    if not claim:
        return match.group(0)
    verb = match.group(2)
    rest = match.group(3).strip()
    ending = match.group(4) or "."
    return f"{claim}. This {verb}{(' ' + rest) if rest else ''}{ending}"

def _expand_relation_sentence_references(text: str, relation_lookup: dict[str, str]) -> str:
    return re.sub(
        r"\b[Rr]elation\s+([A-Za-z0-9_\-]*_?r\d{3,})\s+(matters|is important|is central|is load-bearing)\b",
        lambda match: f"{_relation_reference_phrase(match.group(1), relation_lookup)} {match.group(2)}",
        text,
    )

def _claim_reference_phrase(alias: str, claim_lookup: dict[str, str]) -> str:
    claim = claim_lookup.get(alias) or claim_lookup.get(alias.lower())
    return claim if claim else f"Claim {alias}"

def _relation_reference_phrase(alias: str, relation_lookup: dict[str, str]) -> str:
    relation = relation_lookup.get(alias) or relation_lookup.get(alias.lower())
    return relation if relation else f"Relation {alias}"

def prioritize_map_for_briefing(
    candidate_map: dict[str, Any],
    *,
    quality_report: dict[str, Any],
    max_claims: int = 18,
) -> tuple[dict[str, Any], dict[str, Any]]:
    claims = _claims(candidate_map)
    relations = _relations(candidate_map)
    if max_claims < 1:
        raise ValueError("max_claims must be positive")
    centrality = claim_graph_centrality(claims, relations)
    duplicate_pairs = tfidf_near_duplicate_pairs(
        [str(claim.get("claim", "") or claim.get("text", "")) for claim in claims],
        [str(claim.get("claim_id", "")) for claim in claims],
        threshold=0.35,
    )
    source_lookup = build_source_display_lookup(candidate_map)
    present_families = _claim_family_order(claims, source_lookup)
    present_concepts = _claim_concept_order(claims)
    present_obligatory_concepts = _obligatory_coverage_concepts(present_concepts)
    if len(claims) <= max_claims:
        return dict(candidate_map), {
            "schema_id": "map_prioritization_report_v1",
            "changed": False,
            "reason": "claim_count_within_budget",
            "ranking_method": "role_priority_plus_weighted_pagerank_with_family_and_concept_report",
            "claim_count": len(claims),
            "max_claims": max_claims,
            "kept_claim_ids": [claim.get("claim_id") for claim in claims],
            "dropped_claim_ids": [],
            "duplicate_claim_pairs": _duplicate_pair_rows(duplicate_pairs),
            "centrality_scores": centrality,
            "present_evidence_families": present_families,
            "kept_evidence_families": present_families,
            "family_coverage_preserved": True,
            "present_decision_concepts": present_concepts,
            "kept_decision_concepts": present_concepts,
            "obligatory_present_decision_concepts": present_obligatory_concepts,
            "obligatory_kept_decision_concepts": present_obligatory_concepts,
            "concept_coverage_preserved": True,
        }
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicate_lookup = _duplicate_lookup(duplicate_pairs)
    for source_id in _source_order(claims):
        source_claims = [claim for claim in claims if claim.get("source_id") == source_id]
        if not source_claims:
            continue
        best = sorted(source_claims, key=lambda claim: _claim_rank(claim, centrality))[0]
        claim_id = str(best.get("claim_id"))
        kept.append(best)
        seen.add(claim_id)
    ranked_claims = sorted(claims, key=lambda item: _claim_rank(item, centrality))
    _fill_family_budget(kept, seen, claims, centrality, duplicate_lookup, source_lookup, max_claims)
    _fill_concept_budget(kept, seen, claims, centrality, duplicate_lookup, max_claims)
    _fill_claim_budget(kept, seen, ranked_claims, duplicate_lookup, max_claims, allow_duplicates=False)
    _fill_claim_budget(kept, seen, ranked_claims, duplicate_lookup, max_claims, allow_duplicates=True)
    kept_ids = {str(claim.get("claim_id")) for claim in kept}
    kept_relations = [
        relation
        for relation in relations
        if str(relation.get("source_claim")) in kept_ids and str(relation.get("target_claim")) in kept_ids
    ]
    prioritized = dict(candidate_map)
    prioritized["claims"] = kept
    prioritized["relations"] = kept_relations
    dropped = [str(claim.get("claim_id")) for claim in claims if str(claim.get("claim_id")) not in kept_ids]
    kept_concepts = _claim_concept_order(kept)
    kept_obligatory_concepts = _obligatory_coverage_concepts(kept_concepts)
    return prioritized, {
        "schema_id": "map_prioritization_report_v1",
        "changed": True,
        "reason": "claim_count_exceeded_briefing_budget",
        "ranking_method": "source_coverage_family_concept_coverage_then_role_priority_weighted_pagerank_with_tfidf_duplicate_suppression",
        "quality_status": quality_report.get("status"),
        "claim_count": len(claims),
        "max_claims": max_claims,
        "kept_claim_ids": [str(claim.get("claim_id")) for claim in kept],
        "dropped_claim_ids": dropped,
        "duplicate_claim_pairs": _duplicate_pair_rows(duplicate_pairs),
        "centrality_scores": centrality,
        "source_coverage_preserved": _source_order(claims) == _source_order(kept),
        "present_evidence_families": present_families,
        "kept_evidence_families": _claim_family_order(kept, source_lookup),
        "family_coverage_preserved": set(present_families).issubset(set(_claim_family_order(kept, source_lookup))),
        "present_decision_concepts": present_concepts,
        "kept_decision_concepts": kept_concepts,
        "obligatory_present_decision_concepts": present_obligatory_concepts,
        "obligatory_kept_decision_concepts": kept_obligatory_concepts,
        "concept_coverage_preserved": set(present_obligatory_concepts).issubset(set(kept_obligatory_concepts)),
        "relation_count": len(relations),
        "kept_relation_count": len(kept_relations),
    }

def adaptive_briefing_claim_budget(
    candidate_map: dict[str, Any],
    quality_report: dict[str, Any] | None = None,
    *,
    requested_max_claims: int | None = 0,
) -> int:
    if requested_max_claims and requested_max_claims > 0:
        return requested_max_claims
    if requested_max_claims is not None and requested_max_claims < 0:
        raise ValueError("requested_max_claims must be nonnegative")
    claims = _claims(candidate_map)
    claim_count = len(claims)
    if claim_count <= 1:
        return max(1, claim_count)
    source_lookup = build_source_display_lookup(candidate_map)
    source_count = len(_source_order(claims))
    family_count = len(_claim_family_order(claims, source_lookup))
    concept_count = len(_obligatory_coverage_concepts(_claim_concept_order(claims)))
    base = 28
    source_target = source_count * 3
    family_target = family_count * 6
    concept_target = concept_count * 5
    claim_fraction_target = 0
    if claim_count >= 120:
        claim_fraction_target = round(claim_count * 0.45)
    elif claim_count >= 70:
        claim_fraction_target = round(claim_count * 0.38)
    target = max(base, source_target, family_target, concept_target, claim_fraction_target)
    if quality_report and str(quality_report.get("status", "")) in {"needs_repair", "review_recommended"}:
        target = max(target, concept_target + family_count * 4)
    cap = 90
    return max(1, min(claim_count, target, cap))

def claim_graph_centrality(claims: list[dict[str, Any]], relations: list[dict[str, Any]]) -> dict[str, float]:
    claim_ids = [str(claim.get("claim_id", "")) for claim in claims]
    edges = [
        (
            str(relation.get("source_claim", "")),
            str(relation.get("target_claim", "")),
            relation_edge_weight(str(relation.get("relation_type", ""))),
        )
        for relation in relations
    ]
    return weighted_pagerank(claim_ids, edges)

def generated_map_erosion_audit(candidate_map: dict[str, Any]) -> dict[str, Any]:
    claims = _claims(candidate_map)
    relations = _relations(candidate_map)
    claim_lookup = {str(claim.get("claim_id")): claim for claim in claims}
    items: list[dict[str, Any]] = []
    for claim in claims:
        role = str(claim.get("role", "other"))
        if role not in {"crux", "scope_limit", "implementation_constraint"}:
            continue
        items.append(
            {
                "audit_id": f"audit_{len(items) + 1:03d}",
                "item_type": "claim",
                "item_id": claim.get("claim_id"),
                "issue_type": "must_preserve_decision_relevant_claim",
                "source_ids": [claim.get("source_id")],
                "reader_anchor": _claim_reader_text(claim, {}),
                "coverage_terms": _content_terms(str(claim.get("claim", "")))[:8],
            }
        )
    for relation in relations:
        relation_type = str(relation.get("relation_type", ""))
        if relation_type not in {"crux_for", "in_tension_with", "challenges", "depends_on"}:
            continue
        source = claim_lookup.get(str(relation.get("source_claim")), {})
        target = claim_lookup.get(str(relation.get("target_claim")), {})
        items.append(
            {
                "audit_id": f"audit_{len(items) + 1:03d}",
                "item_type": "relation",
                "item_id": relation.get("relation_id"),
                "issue_type": "must_preserve_relation_not_just_claims",
                "source_ids": sorted({str(source.get("source_id", "")), str(target.get("source_id", ""))} - {""}),
                "reader_anchor": _relation_reader_text(relation, claim_lookup, {}),
                "coverage_terms": _content_terms(str(relation.get("rationale", "")))[:8],
            }
        )
    return {"schema_id": "generated_map_erosion_audit_v1", "items": items}

def calibrate_confidence(model_confidence: str, quality_report: dict[str, Any]) -> dict[str, Any]:
    normalized = model_confidence.strip().lower() if isinstance(model_confidence, str) else "not specified"
    if normalized not in CONFIDENCE_ORDER:
        normalized = "medium"
    cap = confidence_cap(quality_report)
    calibrated = normalized if CONFIDENCE_ORDER[normalized] <= CONFIDENCE_ORDER[cap] else cap
    reasons = [f"model_confidence={model_confidence or 'not specified'}", f"quality_status={quality_report.get('status', 'unknown')}"]
    issues = [issue for issue in quality_report.get("issues", []) if isinstance(issue, dict)]
    if any(issue.get("severity") == "fail" for issue in issues):
        reasons.append("fail_issue_caps_confidence_at_low")
    elif any(issue.get("severity") == "risk" for issue in issues):
        reasons.append("risk_issue_caps_high_confidence")
    if quality_report.get("status") in {"needs_repair", "review_recommended"}:
        reasons.append("quality_status_caps_confidence")
    return {"calibrated_confidence": calibrated, "confidence_cap": cap, "reasons": reasons}

def confidence_cap(quality_report: dict[str, Any]) -> str:
    status = str(quality_report.get("status", "unknown"))
    issues = [issue for issue in quality_report.get("issues", []) if isinstance(issue, dict)]
    if status == "needs_repair" or any(issue.get("severity") == "fail" for issue in issues):
        return "low"
    if status == "review_recommended" or any(issue.get("severity") == "risk" for issue in issues):
        return "medium"
    return "high"

def build_source_display_lookup(
    candidate_map: dict[str, Any],
    *,
    source_titles: dict[str, str] | None = None,
) -> dict[str, str]:
    lookup = {
        source_id: polish_source_display_name(title)
        for source_id, title in dict(source_titles or {}).items()
    }
    for source_id in candidate_map.get("sources", []):
        if isinstance(source_id, str) and source_id not in lookup:
            lookup[source_id] = display_source_name(source_id)
    for claim in _claims(candidate_map):
        source_id = claim.get("source_id")
        if isinstance(source_id, str) and source_id not in lookup:
            lookup[source_id] = display_source_name(source_id)
    return lookup

def display_source_name(source_id: str) -> str:
    words = re.split(r"[_\-\s]+", source_id.strip())
    vocabulary = profile_vocabulary(infer_profile_id_from_text(str(source_id), fallback_profile_id=DEFAULT_PROFILE_ID))
    acronyms = _vocabulary_string_dict(vocabulary, "display_acronyms")
    titled = []
    for word in words:
        lower = word.lower()
        if not word:
            continue
        if lower in acronyms:
            titled.append(acronyms[lower])
        elif re.fullmatch(r"\d{2,4}", word):
            titled.append(word)
        else:
            titled.append(word[:1].upper() + word[1:])
    return " ".join(titled) or source_id

def polish_source_display_name(title: str) -> str:
    words = str(title).split()
    if not words:
        return str(title)
    vocabulary = profile_vocabulary(infer_profile_id_from_text(str(title), fallback_profile_id=DEFAULT_PROFILE_ID))
    acronyms = _vocabulary_string_dict(vocabulary, "display_acronyms")
    polished = []
    for word in words:
        stripped = word.strip()
        lower = re.sub(r"[^A-Za-z0-9.]", "", stripped).lower()
        replacement = acronyms.get(lower)
        if replacement:
            polished.append(re.sub(re.escape(stripped), replacement, word))
        else:
            polished.append(word)
    return " ".join(polished)

def replace_source_ids(text: str, source_lookup: dict[str, str]) -> str:
    cleaned = text
    for source_id, display in sorted(source_lookup.items(), key=lambda item: len(item[0]), reverse=True):
        cleaned = re.sub(rf"(?<![A-Za-z0-9_\-]){re.escape(source_id)}(?![A-Za-z0-9_\-])", display, cleaned)
    return cleaned

def _resolve(repo_root: Path, path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = repo_root / resolved
    return resolved

def _claims(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    return [claim for claim in candidate_map.get("claims", []) if isinstance(claim, dict)]

def _relations(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    return [relation for relation in candidate_map.get("relations", []) if isinstance(relation, dict)]

def _claim_rank(claim: dict[str, Any], centrality: dict[str, float]) -> tuple[int, int, int, float, str]:
    claim_id = str(claim.get("claim_id", ""))
    return (
        ROLE_PRIORITY.get(str(claim.get("role", "other")), ROLE_PRIORITY["other"]),
        int(_claim_noise_profile(claim).get("penalty", 0)),
        -len(_claim_concepts(claim)),
        -centrality.get(claim_id, 0.0),
        claim_id,
    )

def _fill_claim_budget(
    kept: list[dict[str, Any]],
    seen: set[str],
    ranked_claims: list[dict[str, Any]],
    duplicate_lookup: dict[str, set[str]],
    max_claims: int,
    *,
    allow_duplicates: bool,
) -> None:
    for claim in ranked_claims:
        claim_id = str(claim.get("claim_id"))
        if claim_id in seen:
            continue
        if not allow_duplicates and duplicate_lookup.get(claim_id, set()) & seen:
            continue
        if len(kept) >= max_claims:
            break
        kept.append(claim)
        seen.add(claim_id)

def _fill_family_budget(
    kept: list[dict[str, Any]],
    seen: set[str],
    claims: list[dict[str, Any]],
    centrality: dict[str, float],
    duplicate_lookup: dict[str, set[str]],
    source_lookup: dict[str, str],
    max_claims: int,
) -> None:
    kept_families = set(_claim_family_order(kept, source_lookup))
    for family in _claim_family_order(claims, source_lookup):
        if len(kept) >= max_claims:
            break
        if family in kept_families:
            continue
        candidates = [
            claim for claim in claims
            if _evidence_family_for_claim(claim, _claim_evidence_section(claim), source_lookup) == family
            and str(claim.get("claim_id")) not in seen
        ]
        if not candidates:
            continue
        best_candidates = [
            claim for claim in sorted(candidates, key=lambda item: _claim_rank(item, centrality))
            if not (duplicate_lookup.get(str(claim.get("claim_id")), set()) & seen)
        ]
        best = best_candidates[0] if best_candidates else sorted(candidates, key=lambda item: _claim_rank(item, centrality))[0]
        claim_id = str(best.get("claim_id"))
        kept.append(best)
        seen.add(claim_id)
        kept_families.add(family)

def _fill_concept_budget(
    kept: list[dict[str, Any]],
    seen: set[str],
    claims: list[dict[str, Any]],
    centrality: dict[str, float],
    duplicate_lookup: dict[str, set[str]],
    max_claims: int,
) -> None:
    kept_concepts = set(_claim_concept_order(kept))
    for concept in _claim_concept_order(claims):
        if len(kept) >= max_claims:
            break
        if concept in kept_concepts:
            continue
        candidates = [
            claim for claim in claims
            if concept in _claim_concepts(claim)
            and str(claim.get("claim_id")) not in seen
            and str(_claim_noise_profile(claim).get("kind")) not in {"boilerplate_disclosure", "publisher_or_license_boilerplate"}
        ]
        if not candidates:
            continue
        best_candidates = [
            claim for claim in sorted(candidates, key=lambda item: _claim_rank(item, centrality))
            if not (duplicate_lookup.get(str(claim.get("claim_id")), set()) & seen)
        ]
        best = best_candidates[0] if best_candidates else sorted(candidates, key=lambda item: _claim_rank(item, centrality))[0]
        claim_id = str(best.get("claim_id"))
        kept.append(best)
        seen.add(claim_id)
        kept_concepts.update(_claim_concepts(best))

def _claim_family_order(claims: list[dict[str, Any]], source_lookup: dict[str, str]) -> list[str]:
    ordered: list[str] = []
    for claim in claims:
        family = _evidence_family_for_claim(claim, _claim_evidence_section(claim), source_lookup)
        if family not in ordered:
            ordered.append(family)
    return ordered

def _claim_concept_order(claims: list[dict[str, Any]]) -> list[str]:
    rows = [{"concepts": _claim_concepts(claim)} for claim in claims]
    return _ordered_concepts(rows)

def _duplicate_lookup(pairs: list[tuple[str, str, float]]) -> dict[str, set[str]]:
    lookup: dict[str, set[str]] = {}
    for left, right, _score in pairs:
        lookup.setdefault(left, set()).add(right)
        lookup.setdefault(right, set()).add(left)
    return lookup

def _duplicate_pair_rows(pairs: list[tuple[str, str, float]]) -> list[dict[str, Any]]:
    return [{"left": left, "right": right, "score": score} for left, right, score in pairs]

def _source_order(claims: list[dict[str, Any]]) -> list[str]:
    ordered: list[str] = []
    for claim in claims:
        source_id = str(claim.get("source_id", ""))
        if source_id and source_id not in ordered:
            ordered.append(source_id)
    return ordered

def _quality_brief(quality_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": quality_report.get("status"),
        "score": quality_report.get("score"),
        "summary": quality_report.get("summary", {}),
        "issues": quality_report.get("issues", []),
    }

def _claim_reader_text(claim: dict[str, Any], source_lookup: dict[str, str]) -> str:
    raw_text = str(claim.get("claim") or claim.get("text") or "").strip()
    text = _reader_safe_claim_text(raw_text, claim)
    source_id = str(claim.get("source_id", "")).strip()
    source = source_lookup.get(source_id, display_source_name(source_id)) if source_id else ""
    if source:
        return f"{text} ({source})"
    return text

def _reader_safe_claim_text(text: str, claim: dict[str, Any]) -> str:
    noise = _claim_noise_profile({**claim, "claim": text})
    kind = str(noise.get("kind", "none"))
    if kind == "boilerplate_disclosure":
        return "The source contains extensive funding or conflict-of-interest disclosures that should be treated as source context rather than substantive outcome evidence."
    if kind == "publisher_or_license_boilerplate":
        return "The source contains publisher, license, or metadata boilerplate that should not be treated as substantive evidence."
    if len(text) > 700:
        return _short_claim_fragment(text, max_chars=320)
    return text

def _relation_reader_text(
    relation: dict[str, Any],
    claim_lookup: dict[str, dict[str, Any]],
    source_lookup: dict[str, str],
) -> str:
    source_claim = claim_lookup.get(str(relation.get("source_claim")), {})
    target_claim = claim_lookup.get(str(relation.get("target_claim")), {})
    rationale = str(relation.get("rationale", "")).strip()
    relation_type = str(relation.get("relation_type", "")).strip()
    if rationale:
        return rationale
    left = _claim_reader_text(source_claim, source_lookup)
    right = _claim_reader_text(target_claim, source_lookup)
    if left and right and relation_type:
        return f"{left} {relation_type} {right}"
    return " ".join(part for part in (left, relation_type, right) if part)

def _claim_evidence_section(claim: dict[str, Any]) -> str:
    role = str(claim.get("role", "other"))
    text = _claim_text_bundle(claim)
    if _looks_like_concern_evidence(text):
        return "conflicting_evidence"
    if _looks_like_support_evidence(text):
        return "main_support"
    if role == "conclusion_support":
        return "main_support"
    if role in {
        "measurement_validity",
        "implementation_constraint",
        "cost_feasibility",
        "compliance_burden",
        "background",
    }:
        return "method_limits"
    if _looks_like_method_or_source_limit(text):
        return "method_limits"
    if role in {
        "scope_limit",
        "external_validity",
        "residual_risk",
        "operational_constraint",
        "jurisdictional_constraint",
    }:
        return "scope_limits"
    if _looks_like_scope_or_subgroup(text):
        return "scope_limits"
    if role == "crux":
        return "scope_limits"
    return "main_support"

def _relation_evidence_section(
    relation: dict[str, Any],
    claim_lookup: dict[str, dict[str, Any]],
) -> str | None:
    relation_type = str(relation.get("relation_type", ""))
    if relation_type in {"challenges", "in_tension_with"}:
        return "conflicting_evidence"
    if relation_type in {"depends_on", "refines"}:
        return "scope_limits"
    if relation_type == "supports":
        source = claim_lookup.get(str(relation.get("source_claim")), {})
        target = claim_lookup.get(str(relation.get("target_claim")), {})
        combined = " ".join((_claim_text_bundle(source), _claim_text_bundle(target), str(relation.get("rationale", ""))))
        return "conflicting_evidence" if _looks_like_concern_evidence(combined) else "main_support"
    if relation_type == "crux_for":
        return "scope_limits"
    return None

def _relation_crux_reason(relation_type: str) -> str:
    return {
        "crux_for": "This relation marks a claim that would change the bottom-line answer.",
        "depends_on": "This relation identifies a condition that gates whether the recommendation holds.",
        "in_tension_with": "This relation preserves a tension that the final answer should not flatten.",
        "challenges": "This relation names counterevidence that could weaken the bottom-line answer.",
    }.get(relation_type, "This relation changes how strongly the mapped conclusion can be used.")

def _claim_text_bundle(claim: dict[str, Any]) -> str:
    return " ".join(
        str(claim.get(key, "") or "")
        for key in ("claim", "text", "excerpt", "source_span", "role")
    ).lower()

def _looks_like_concern_evidence(text: str, *, vocabulary: dict[str, Any] | None = None) -> bool:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    negated_low_concern = _vocabulary_marker_list(vocabulary, "concern_negated_markers")
    if any(marker in normalized for marker in negated_low_concern):
        if not any(marker in normalized for marker in _vocabulary_marker_list(vocabulary, "concern_contrast_markers")):
            return False
    return any(marker in normalized for marker in _vocabulary_marker_list(vocabulary, "concern_markers"))

def _looks_like_support_evidence(text: str, *, vocabulary: dict[str, Any] | None = None) -> bool:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    return any(marker in normalized for marker in _vocabulary_marker_list(vocabulary, "support_markers"))

def _looks_like_scope_or_subgroup(text: str, *, vocabulary: dict[str, Any] | None = None) -> bool:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    return any(marker in normalized for marker in _vocabulary_marker_list(vocabulary, "scope_or_subgroup_markers"))

def _looks_like_method_or_source_limit(text: str) -> bool:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    return any(marker in normalized for marker in _vocabulary_marker_list(None, "method_or_source_limit_markers"))

def _clean_payload_reader_language(value: Any) -> Any:
    if isinstance(value, str):
        return _clean_reader_relation_placeholders(value)
    if isinstance(value, list):
        return [_clean_payload_reader_language(item) for item in value]
    if isinstance(value, dict):
        return {key: _clean_payload_reader_language(item) for key, item in value.items()}
    return value

def _sanitize_evidence_role_sections(roles: dict[str, list[str]]) -> dict[str, list[str]]:
    sanitized = {key: list(roles.get(key, [])) for key in ("main_support", "conflicting_evidence", "scope_limits", "method_limits")}
    moved_to_conflict: list[str] = []
    for source_key in ("main_support", "scope_limits", "method_limits"):
        kept: list[str] = []
        for item in sanitized[source_key]:
            if _should_move_to_conflicting_evidence(item, source_key):
                moved_to_conflict.append(item)
            else:
                kept.append(item)
        sanitized[source_key] = kept
    sanitized["conflicting_evidence"] = _dedupe([*sanitized["conflicting_evidence"], *moved_to_conflict])
    return {key: _dedupe(value)[:8] for key, value in sanitized.items()}

def _should_move_to_conflicting_evidence(item: str, source_key: str) -> bool:
    if not _looks_like_concern_evidence(item):
        return False
    if source_key == "main_support":
        return True
    if source_key == "scope_limits":
        return not _looks_like_scope_or_subgroup(item)
    if source_key == "method_limits":
        return not _looks_like_method_or_source_limit(item)
    return False

def _apply_briefing_contract_lint(payload: dict[str, Any], scaffold: dict[str, Any]) -> dict[str, Any]:
    contract = scaffold.get("briefing_contract", {})
    if not isinstance(contract, dict):
        return payload
    active_lints = {
        str(item.get("lint_id"))
        for item in contract.get("overstatement_lint", [])
        if isinstance(item, dict)
    }
    if not active_lints:
        return payload
    repaired = dict(payload)
    for key in ("decision_brief", "synthesis"):
        if isinstance(repaired.get(key), str):
            repaired[key] = _lint_reader_overstatements(str(repaired[key]), active_lints)
    for key in ("decision_implications", "stress_caveats", "audit_trail"):
        if isinstance(repaired.get(key), list):
            repaired[key] = [
                _lint_reader_overstatements(str(item), active_lints)
                for item in repaired[key]
            ]
    evidence_roles = repaired.get("evidence_roles")
    if isinstance(evidence_roles, dict):
        repaired["evidence_roles"] = {
            role_key: [
                _lint_reader_overstatements(str(item), active_lints)
                for item in _string_list(items)
            ]
            for role_key, items in evidence_roles.items()
        }
    return repaired

def _apply_decision_model_lint(payload: dict[str, Any], scaffold: dict[str, Any]) -> dict[str, Any]:
    decision_model = scaffold.get("decision_model", {})
    if not isinstance(decision_model, dict):
        return payload
    default_answer = decision_model.get("default_answer", {})
    if not isinstance(default_answer, dict):
        return payload
    classification = str(default_answer.get("classification", ""))
    if classification != "neutral_or_low_concern_under_stated_conditions":
        return payload
    repaired = dict(payload)
    for key in ("decision_brief", "synthesis"):
        if isinstance(repaired.get(key), str):
            repaired[key] = _lint_neutral_default_benefit_framing(str(repaired[key]))
    for key in ("decision_implications", "stress_caveats"):
        if isinstance(repaired.get(key), list):
            repaired[key] = [_lint_neutral_default_benefit_framing(str(item)) for item in repaired[key]]
    evidence_roles = repaired.get("evidence_roles")
    if isinstance(evidence_roles, dict):
        repaired["evidence_roles"] = {
            role_key: [_lint_neutral_default_benefit_framing(str(item)) for item in _string_list(items)]
            for role_key, items in evidence_roles.items()
        }
    return repaired

def _lint_neutral_default_benefit_framing(text: str) -> str:
    cleaned = text
    cleaned = re.sub(
        r"\b(is|are|was|were) associated with potentially lower ([A-Za-z \-]*risk)\b",
        r"\1 best read as neutral or low-concern for \2 under the stated conditions",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\bpotentially lower ([A-Za-z \-]*risk)\b",
        r"neutral or low-concern \1 under the stated conditions",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\bprotective\b",
        "lower-concern in the scoped evidence",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\bbeneficial default\b",
        "neutral or low-concern default",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned



# Explicit cross-module dependencies for compatibility facade removal.
from epistemic_case_mapper.map_briefing_decision_model import (
    _claim_concepts,
    _claim_noise_profile,
    _evidence_family_for_claim,
    _short_claim_fragment,
)
from epistemic_case_mapper.map_briefing_evidence_tables import _obligatory_coverage_concepts, _ordered_concepts
from epistemic_case_mapper.map_briefing_pipeline import CONFIDENCE_ORDER, ROLE_PRIORITY
from epistemic_case_mapper.map_briefing_reader_contracts import _vocabulary_marker_list, _vocabulary_string_dict
from epistemic_case_mapper.map_briefing_validation import (
    _clean_reader_relation_placeholders,
    _content_terms,
    _dedupe,
    _lint_reader_overstatements,
    _string_list,
)
