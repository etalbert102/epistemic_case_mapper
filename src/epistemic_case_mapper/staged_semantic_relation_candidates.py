from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.classical_ml import diverse_ranked_edges, tfidf_pair_similarities

MIN_RELATION_CANDIDATE_SCORE = 4.0


def _candidate_relation_pairs(claims: list[dict[str, Any]], max_pairs: int) -> list[dict[str, Any]]:
    usable_claims = _prioritized_relation_claim_pool([claim for claim in claims if _usable_relation_claim(claim)], max_pairs=max_pairs)
    if len(usable_claims) < 2 and len(claims) <= 5:
        usable_claims = _tiny_map_relation_claim_pool(claims, max_pairs=max_pairs)
    if len(usable_claims) < 2:
        return []
    claim_lookup = {str(claim.get("claim_id", "")): claim for claim in usable_claims if claim.get("claim_id")}
    claim_order = {str(claim.get("claim_id", "")): index for index, claim in enumerate(claims)}
    tfidf_scores = _claim_tfidf_scores(usable_claims)
    common_terms = _common_relation_terms(usable_claims)
    scored: list[tuple[str, str, float, str]] = []
    for left_index, left in enumerate(usable_claims):
        for right_index, right in enumerate(usable_claims):
            if left_index >= right_index:
                continue
            score, reason = _pair_score(left, right, tfidf_scores, common_terms=common_terms)
            if score < MIN_RELATION_CANDIDATE_SCORE:
                continue
            scored.append((left["claim_id"], right["claim_id"], score, reason))
    selected = diverse_ranked_edges(
        [claim_id for claim_id in claim_order if claim_id],
        scored,
        limit=max_pairs,
    )
    packets = []
    ordered = sorted(selected, key=lambda item: (claim_order.get(item[0], 9999), claim_order.get(item[1], 9999)))
    for index, (left_id, right_id, score, reason) in enumerate(ordered, start=1):
        packets.append(
            {
                "pair_id": f"pair_{index:03d}",
                "left": claim_lookup[left_id],
                "right": claim_lookup[right_id],
                "candidate_score": score,
                "candidate_reason": reason,
            }
        )
    return packets


def _relation_pair_budget(claims: list[dict[str, Any]], requested_max_pairs: int) -> int:
    if requested_max_pairs < 12:
        return max(0, requested_max_pairs)
    eligible_count = sum(1 for claim in claims if _usable_relation_claim(claim))
    if eligible_count < 2:
        if len(claims) <= 5 and len(_tiny_map_relation_claim_pool(claims, max_pairs=requested_max_pairs)) >= 2:
            return requested_max_pairs
        return 0
    adaptive_floor = max(24, min(48, eligible_count * 2, max(12, len(claims) // 3)))
    return max(requested_max_pairs, adaptive_floor)


def _relation_batch_count(max_relation_pairs: int, relation_batch_size: int, claims: list[dict[str, Any]]) -> int:
    if len(claims) < 2:
        return 0
    pair_count = len(_candidate_relation_pairs(claims, max_relation_pairs))
    if pair_count == 0:
        return 0
    safe_batch_size = min(relation_batch_size, 4)
    return (pair_count + safe_batch_size - 1) // safe_batch_size


def _relation_candidate_pool_report(
    claims: list[dict[str, Any]],
    pair_packets: list[dict[str, Any]],
    *,
    requested_max_pairs: int,
    effective_max_pairs: int,
) -> dict[str, Any]:
    rejected_endpoints: list[dict[str, Any]] = []
    eligible_claims: list[dict[str, Any]] = []
    for claim in claims:
        reason = _relation_endpoint_rejection_reason(claim)
        if reason:
            rejected_endpoints.append(
                {
                    "claim_id": claim.get("claim_id"),
                    "source_id": claim.get("source_id"),
                    "role": claim.get("role"),
                    "reason": reason,
                    "claim": str(claim.get("claim", ""))[:240],
                }
            )
        else:
            eligible_claims.append(claim)
    selected_ids = {
        str(packet[side].get("claim_id", ""))
        for packet in pair_packets
        for side in ("left", "right")
        if isinstance(packet.get(side), dict)
    }
    return {
        "schema_id": "relation_candidate_pool_report_v1",
        "claim_count": len(claims),
        "eligible_endpoint_count": len(eligible_claims),
        "rejected_endpoint_count": len(rejected_endpoints),
        "requested_max_pairs": requested_max_pairs,
        "effective_max_pairs": effective_max_pairs,
        "selected_pair_count": len(pair_packets),
        "selected_endpoint_count": len(selected_ids),
        "eligible_role_counts": _count_values(str(claim.get("role", "unknown")) for claim in eligible_claims),
        "rejected_endpoint_reason_counts": _count_values(str(row.get("reason", "")) for row in rejected_endpoints),
        "selected_candidate_reason_counts": _candidate_reason_counts(pair_packets),
        "selected_pairs": [_candidate_pair_telemetry(packet) for packet in pair_packets],
        "rejected_endpoint_examples": rejected_endpoints[:30],
    }


def _count_values(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _candidate_reason_counts(pair_packets: list[dict[str, Any]]) -> dict[str, int]:
    reasons: list[str] = []
    for packet in pair_packets:
        reasons.extend(part for part in str(packet.get("candidate_reason", "")).split("+") if part)
    return _count_values(reasons)


def _candidate_pair_telemetry(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "pair_id": packet.get("pair_id"),
        "candidate_score": packet.get("candidate_score"),
        "candidate_reason": packet.get("candidate_reason"),
        "left": _candidate_endpoint_telemetry(packet.get("left", {})),
        "right": _candidate_endpoint_telemetry(packet.get("right", {})),
    }


def _candidate_endpoint_telemetry(claim: Any) -> dict[str, Any]:
    if not isinstance(claim, dict):
        return {}
    eligibility = claim.get("eligibility") if isinstance(claim.get("eligibility"), dict) else {}
    noise = claim.get("noise") if isinstance(claim.get("noise"), dict) else {}
    return {
        "claim_id": claim.get("claim_id"),
        "source_id": claim.get("source_id"),
        "role": claim.get("role"),
        "question_fit": _question_fit_status(claim),
        "appendix_only": bool(claim.get("appendix_only") or eligibility.get("appendix_only")),
        "noise_kind": noise.get("kind", "none"),
        "claim": str(claim.get("claim", ""))[:180],
    }


def _prioritized_relation_claim_pool(claims: list[dict[str, Any]], *, max_pairs: int) -> list[dict[str, Any]]:
    if len(claims) <= 2:
        return claims
    pool_limit = max(12, min(48, max(max_pairs * 2, 30)))
    ranked = sorted(claims, key=_relation_endpoint_rank)
    by_source: dict[str, dict[str, Any]] = {}
    for claim in ranked:
        source_id = str(claim.get("source_id", ""))
        if source_id and source_id not in by_source:
            by_source[source_id] = claim
    selected: list[dict[str, Any]] = list(by_source.values())[: min(len(by_source), pool_limit)]
    selected_ids = {str(claim.get("claim_id", "")) for claim in selected}
    for claim in ranked:
        if len(selected) >= pool_limit:
            break
        claim_id = str(claim.get("claim_id", ""))
        if claim_id in selected_ids:
            continue
        selected.append(claim)
        selected_ids.add(claim_id)
    return selected


def _tiny_map_relation_claim_pool(claims: list[dict[str, Any]], *, max_pairs: int) -> list[dict[str, Any]]:
    relaxed = [
        claim
        for claim in claims
        if _relation_endpoint_rejection_reason(claim) in {"", "too_short_without_decision_role", "low_content_fragment"}
        and not _hard_relation_endpoint_rejection_reason(claim)
    ]
    return _prioritized_relation_claim_pool(relaxed, max_pairs=max_pairs)


def _relation_endpoint_rank(claim: dict[str, Any]) -> tuple[int, int, int, int, int, str]:
    return (
        -_relation_endpoint_priority(claim),
        _relation_endpoint_rejection_penalty(claim),
        -len(_content_terms(str(claim.get("claim", "")))),
        len(str(claim.get("claim", ""))),
        str(claim.get("source_id", "")),
        str(claim.get("claim_id", "")),
    )


def _relation_endpoint_priority(claim: dict[str, Any]) -> int:
    role = str(claim.get("role", ""))
    role_scores = {
        "crux": 14,
        "conclusion_support": 11,
        "scope_limit": 10,
        "measurement_validity": 9,
        "external_validity": 9,
        "implementation_constraint": 8,
        "background": 2,
        "other": 0,
    }
    text = _normalize_text(f"{claim.get('claim', '')} {claim.get('excerpt', '')}")
    score = role_scores.get(role, 4)
    if _question_fit_status(claim) in {"match", "partial"}:
        score += 4
    if _has_support_signal(text) or _has_limit_or_challenge_signal(text):
        score += 3
    if re.search(r"\b(?:risk|effect|outcome|association|recommend|compared|depends|uncertain|confidence|evidence)\b", text):
        score += 2
    if re.search(r"\d|%|\bci\b|\bratio\b|\brate\b", text):
        score += 1
    return score


def _relation_endpoint_rejection_penalty(claim: dict[str, Any]) -> int:
    reason = _relation_endpoint_rejection_reason(claim)
    return 1 if reason else 0


def _usable_relation_claim(claim: dict[str, Any]) -> bool:
    return not _relation_endpoint_rejection_reason(claim)


def _relation_endpoint_rejection_reason(claim: dict[str, Any]) -> str:
    text = re.sub(r"\s+", " ", str(claim.get("claim", "") or claim.get("excerpt", ""))).strip()
    lowered = text.lower()
    role = str(claim.get("role", ""))
    eligibility = claim.get("eligibility") if isinstance(claim.get("eligibility"), dict) else {}
    noise = claim.get("noise") if isinstance(claim.get("noise"), dict) else {}
    noise_kind = str(noise.get("kind", "none"))
    if claim.get("appendix_only") or eligibility.get("appendix_only"):
        return "appendix_only"
    if noise_kind not in {"", "none"} and str(noise.get("severity", "high")) in {"medium", "high"}:
        return f"noise:{noise_kind}"
    if _question_fit_status(claim) == "mismatch":
        return "question_fit_mismatch"
    if len(text) < 18 and role not in {"crux", "conclusion_support", "scope_limit", "implementation_constraint"}:
        return "too_short_without_decision_role"
    non_evidence_reason = _non_evidence_text_reason(text)
    if _looks_like_relation_reference_or_boilerplate(text) or (
        non_evidence_reason and not _allow_low_signal_relation_endpoint(text, non_evidence_reason, role)
    ):
        return non_evidence_reason or "reference_or_boilerplate"
    if any(marker in lowered for marker in ("[google scholar]", "privacy policy", "nutrition policy", "no. (%)", "pmcid:", "copyright")):
        return "metadata_or_table_fragment"
    if _looks_like_css_or_markup(text):
        return "css_or_markup"
    if _looks_like_title_or_heading(text):
        return "title_or_heading"
    if (
        re.fullmatch(r"[\w\s,./()%+-]+", text)
        and len(_content_terms(text)) <= 3
        and not _allow_low_signal_relation_endpoint(text, "low_content_fragment", role)
    ):
        return "low_content_fragment"
    if re.fullmatch(r"(?:pooled\s+)?(?:relative\s+)?risk\s*\(?95%?\s*ci\)?", lowered):
        return "table_header_fragment"
    return ""


def _hard_relation_endpoint_rejection_reason(claim: dict[str, Any]) -> str:
    text = re.sub(r"\s+", " ", str(claim.get("claim", "") or claim.get("excerpt", ""))).strip()
    lowered = text.lower()
    eligibility = claim.get("eligibility") if isinstance(claim.get("eligibility"), dict) else {}
    noise = claim.get("noise") if isinstance(claim.get("noise"), dict) else {}
    if claim.get("appendix_only") or eligibility.get("appendix_only"):
        return "appendix_only"
    if str(noise.get("kind", "none")) not in {"", "none"} and str(noise.get("severity", "high")) in {"medium", "high"}:
        return "noise"
    if _question_fit_status(claim) == "mismatch":
        return "question_fit_mismatch"
    if any(marker in lowered for marker in ("[google scholar]", "privacy policy", "nutrition policy", "no. (%)", "pmcid:", "copyright")):
        return "metadata_or_table_fragment"
    if _looks_like_relation_reference_or_boilerplate(text) or _looks_like_css_or_markup(text) or _looks_like_title_or_heading(text):
        return "non_evidence_endpoint"
    return ""


def _allow_low_signal_relation_endpoint(text: str, reason: str, role: str) -> bool:
    if role not in {"crux", "conclusion_support", "scope_limit", "implementation_constraint", "measurement_validity", "external_validity"}:
        return False
    if reason not in {"low_content_fragment", "too_short_without_evidence_signal", "list_heading_or_index_term"}:
        return False
    lowered = text.lower()
    if any(marker in lowered for marker in ("policy", "publication types", "no. (%)", "pmid", "doi", "privacy", "copyright")):
        return False
    return len(text.strip()) >= 18


def _question_fit_status(claim: dict[str, Any]) -> str:
    question_fit = claim.get("question_fit") if isinstance(claim.get("question_fit"), dict) else {}
    eligibility = claim.get("eligibility") if isinstance(claim.get("eligibility"), dict) else {}
    if not question_fit and isinstance(eligibility.get("question_fit"), dict):
        question_fit = eligibility["question_fit"]
    return str(question_fit.get("status", "")).strip().lower()


def _looks_like_title_or_heading(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip()
    lowered = compact.lower()
    if lowered in {"publication types", "article information", "references", "abstract", "methods", "results"}:
        return True
    if ":" in compact and len(compact) <= 180 and not _has_evidence_predicate(lowered):
        return True
    titlecase_terms = sum(1 for token in re.findall(r"\b[A-Z][a-z]{2,}\b", compact))
    if titlecase_terms >= 4 and len(compact) <= 160 and not _has_evidence_predicate(lowered):
        return True
    return False


def _looks_like_css_or_markup(text: str) -> bool:
    compact = text.strip()
    if re.search(r"\.[A-Za-z0-9_-]+\s*\{", compact):
        return True
    if compact.count("{") + compact.count("}") >= 2 and re.search(r"\b(?:fill|stroke|font|width|height|color)\s*:", compact.lower()):
        return True
    if re.search(r"</?[a-z][^>]*>", compact.lower()):
        return True
    return False


def _claim_tfidf_scores(claims: list[dict[str, Any]]) -> dict[tuple[str, str], float]:
    ids = [str(claim.get("claim_id", "")) for claim in claims]
    texts = [_claim_pair_text(claim) for claim in claims]
    return tfidf_pair_similarities(texts, ids)


def _claim_pair_text(claim: dict[str, Any]) -> str:
    return " ".join(str(claim.get(key, "")) for key in ("claim", "excerpt", "role", "source_id"))


def _pair_score(
    left: dict[str, Any],
    right: dict[str, Any],
    tfidf_scores: dict[tuple[str, str], float] | None = None,
    common_terms: set[str] | None = None,
) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []
    if left.get("source_id") != right.get("source_id"):
        score += 3
        reasons.append("cross_source")
    left_role = str(left.get("role", ""))
    right_role = str(right.get("role", ""))
    role_reason, role_score = _role_pair_priority(left_role, right_role)
    if role_score:
        score += role_score
        reasons.append(role_reason)
    if "crux" in {left_role, right_role}:
        score += 4
        reasons.append("crux_pair")
    if {left_role, right_role} & {"scope_limit", "implementation_constraint"}:
        score += 3
        reasons.append("scope_or_implementation_pair")
    if {left_role, right_role} & {"conclusion_support"}:
        score += 2
        reasons.append("support_pair")
    left_text = _normalize_text(f"{left.get('claim', '')} {left.get('excerpt', '')}")
    right_text = _normalize_text(f"{right.get('claim', '')} {right.get('excerpt', '')}")
    if _looks_like_tension(left_text, right_text):
        score += 6
        reasons.append("support_limit_tension")
    semantic_score = _semantic_pair_score(left, right, tfidf_scores or {})
    if semantic_score > 0:
        score += min(4.0, semantic_score * 5.0)
        reasons.append("tfidf_semantic_similarity")
    shared_terms = _content_terms(str(left.get("claim", ""))) & _content_terms(str(right.get("claim", "")))
    if shared_terms:
        score += min(3, len(shared_terms))
        reasons.append("shared_terms")
    population_penalty = _population_scope_mismatch_penalty(left_text, right_text)
    if population_penalty:
        score -= population_penalty
        reasons.append("population_scope_mismatch")
    if left.get("source_id") == right.get("source_id") and left_role == right_role == "conclusion_support":
        score -= 15
        reasons.append("same_source_support_pair_penalty")
    if left_role == right_role == "conclusion_support" and not _salient_shared_terms(left, right, common_terms=common_terms):
        score -= 12
        reasons.append("weak_support_pair_overlap")
    return score, "+".join(reasons) or "low_signal"


def _semantic_pair_score(
    left: dict[str, Any],
    right: dict[str, Any],
    tfidf_scores: dict[tuple[str, str], float],
) -> float:
    left_id, right_id = sorted((str(left.get("claim_id", "")), str(right.get("claim_id", ""))))
    return float(tfidf_scores.get((left_id, right_id), 0.0))


def _role_pair_priority(left_role: str, right_role: str) -> tuple[str, int]:
    roles = {left_role, right_role}
    if "scope_limit" in roles and roles & {"conclusion_support", "crux"}:
        return "scope_limit_bounds_decision_claim", 8
    if "implementation_constraint" in roles and roles & {"conclusion_support", "crux"}:
        return "implementation_constraint_conditions_decision_claim", 8
    if "measurement_validity" in roles and roles & {"conclusion_support", "crux"}:
        return "measurement_limit_bears_on_decision_claim", 7
    if "external_validity" in roles and roles & {"conclusion_support", "crux"}:
        return "external_validity_bounds_decision_claim", 7
    if "crux" in roles and roles - {"background", "other"}:
        return "crux_connected_to_substantive_claim", 7
    return "", 0


def _looks_like_relation_reference_or_boilerplate(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"\bdoi\b|\bpmid\b|\bgoogle scholar\b|\bcrossref\b", lowered):
        return True
    if lowered.count("received ") >= 2 and len(lowered) > 400:
        return True
    return False


def _non_evidence_text_reason(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip(" -•*\t\r\n")
    lowered = compact.lower()
    if not compact:
        return "blank"
    if re.search(r"\b(?:doi|pmid|pmcid|issn|isbn|pubmed|crossref|google scholar|linkout|substances)\b", lowered):
        return "reference_or_metadata"
    if re.search(r"\b(?:privacy|cookie|copyright|terms of use|linking|whistleblower|conflict of interest|editorial guidelines|accessibility)\s+policy\b", lowered):
        return "navigation_or_policy_boilerplate"
    if re.search(r"\b(?:official website|https:// ensures|advanced search|email alerts|save citation|share this article)\b", lowered):
        return "site_navigation_or_security_boilerplate"
    if re.fullmatch(r"(?:[a-z][a-z\s/-]{2,40}\*?\s*){1,4}", lowered) and not _has_evidence_predicate(lowered):
        return "list_heading_or_index_term"
    if len(compact) < 18 and not re.search(r"\d|%|\b(risk|effect|recommend|should|found|showed)\b", lowered):
        return "too_short_without_evidence_signal"
    if lowered.count(";") + lowered.count(",") >= 7 and not _has_evidence_predicate(lowered):
        return "list_without_predicate"
    if re.fullmatch(r"[\w\s,./()%+\-*]+", compact) and len(_content_terms(compact)) <= 3 and not _has_evidence_predicate(lowered):
        return "low_content_fragment"
    return ""


def _has_evidence_predicate(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:is|are|was|were|found|showed|reported|associated|increased|decreased|reduced|lower|higher|recommend|recommended|should|must|may|can|depends|compared)\b",
            text,
        )
    )


def _looks_like_tension(left_text: str, right_text: str) -> bool:
    return (
        _has_support_signal(left_text) and _has_limit_or_challenge_signal(right_text)
    ) or (
        _has_support_signal(right_text) and _has_limit_or_challenge_signal(left_text)
    )


def _has_support_signal(text: str) -> bool:
    return any(marker in text for marker in ("support", "benefit", "improve", "reduce", "favor", "works", "effective", "associated with"))


def _has_limit_or_challenge_signal(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "limit",
            "uncertain",
            "not",
            "cannot",
            "does not",
            "failed",
            "challenge",
            "weaken",
            "scope",
            "only when",
            "depends",
        )
    )


def _population_scope_mismatch_penalty(left_text: str, right_text: str) -> int:
    left_categories = _population_scope_categories(left_text)
    right_categories = _population_scope_categories(right_text)
    if not left_categories and not right_categories:
        return 0
    if "child" in left_categories ^ right_categories:
        return 30
    if not left_categories or not right_categories or left_categories == right_categories:
        return 0
    return 4


def _population_scope_categories(text: str) -> set[str]:
    categories: set[str] = set()
    if re.search(r"\b(?:infant|infants|toddler|toddlers|child|children|adolescent|adolescents|pediatric|paediatric)\b", text):
        categories.add("child")
    if re.search(r"\b(?:adult|adults|men|women|older adults|participants|cohort)\b", text):
        categories.add("adult_or_general")
    if re.search(r"\b(?:pregnant|pregnancy|lactating)\b", text):
        categories.add("pregnancy")
    if re.search(r"\b(?:diabetes|diabetic|high-risk|high risk|baseline risk|subgroup)\b", text):
        categories.add("risk_subgroup")
    return categories


def _common_relation_terms(claims: list[dict[str, Any]]) -> set[str]:
    counts: dict[str, int] = {}
    for claim in claims:
        for term in _content_terms(str(claim.get("claim", ""))):
            counts[term] = counts.get(term, 0) + 1
    if len(claims) < 8:
        return set()
    threshold = max(4, len(claims) // 8)
    return {term for term, count in counts.items() if count >= threshold}


def _salient_shared_terms(left: dict[str, Any], right: dict[str, Any], *, common_terms: set[str] | None = None) -> set[str]:
    generic = {
        "associated",
        "association",
        "claim",
        "consumption",
        "disease",
        "effect",
        "effects",
        "evidence",
        "food",
        "foods",
        "health",
        "higher",
        "intake",
        "lower",
        "reported",
        "risk",
        "study",
        "studies",
    }
    generic.update(common_terms or set())
    return (
        _content_terms(str(left.get("claim", ""))) - generic
    ) & (
        _content_terms(str(right.get("claim", ""))) - generic
    )


def _content_terms(text: str) -> set[str]:
    stopwords = {
        "about",
        "after",
        "also",
        "and",
        "are",
        "but",
        "for",
        "from",
        "has",
        "have",
        "into",
        "not",
        "that",
        "the",
        "their",
        "this",
        "with",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]{4,}", text.lower())
        if token not in stopwords
    }


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()
