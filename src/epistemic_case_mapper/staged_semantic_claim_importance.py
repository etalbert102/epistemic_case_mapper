from __future__ import annotations

import re
from typing import Any


def question_fit_from_relevance(question_relevance: str, scope_flags: list[str]) -> dict[str, Any]:
    if question_relevance == "direct":
        status = "match"
    elif question_relevance in {"indirect", "scope_limit"}:
        status = "partial"
    elif question_relevance == "background":
        status = "weak"
    else:
        status = "uncertain"
    mismatch_flags = [flag for flag in scope_flags if flag != "none"]
    return {
        "schema_id": "claim_question_fit_from_extraction_v1",
        "status": status,
        "source": "model_question_relevance_with_deterministic_scope_flags",
        "scope_mismatch_flags": mismatch_flags,
    }


def normalized_decision_importance(
    proposal: dict[str, Any],
    *,
    claim_text: str,
    excerpt: str,
    question_relevance: str,
    scope_flags: list[str],
) -> dict[str, Any]:
    model_level = _normalized_importance_level(proposal.get("decision_importance") or proposal.get("importance"))
    model_function = _derived_decision_function(question_relevance=question_relevance, scope_flags=scope_flags)
    default_use = _derived_default_use(model_level=model_level, question_relevance=question_relevance)
    calibrated_level, calibration_reasons = _calibrated_importance_level(
        model_level=model_level,
        decision_function=model_function,
        default_use=default_use,
        claim_text=claim_text,
        excerpt=excerpt,
        question_relevance=question_relevance,
        scope_flags=scope_flags,
    )
    if default_use == "main_map" and calibrated_level not in {"critical", "high"}:
        default_use = "supporting_map"
    if default_use == "exclude_unless_gap" and calibrated_level in {"critical", "high"}:
        default_use = "supporting_map"
    rationale = _compact_metadata_text(proposal.get("importance_rationale") or proposal.get("relevance_rationale"))
    return {
        "schema_id": "claim_decision_importance_v1",
        "model_level": model_level,
        "calibrated_level": calibrated_level,
        "decision_function": model_function,
        "default_use": default_use,
        "rationale": rationale,
        "calibration_reasons": calibration_reasons,
    }


def _normalized_importance_level(value: Any) -> str:
    level = str(value or "").strip().lower()
    if level in {"critical", "high", "medium", "low"}:
        return level
    return "medium"


def _derived_decision_function(*, question_relevance: str, scope_flags: list[str]) -> str:
    if "mechanism_only" in scope_flags:
        return "mechanism"
    if question_relevance == "scope_limit" or any(flag != "none" for flag in scope_flags):
        return "scope_boundary"
    if question_relevance in {"direct", "indirect"}:
        return "answer_bearing"
    if question_relevance == "unspecified":
        return "unclassified_evidence"
    return "background_context"


def _derived_default_use(*, model_level: str, question_relevance: str) -> str:
    if question_relevance == "unspecified":
        return "supporting_map" if model_level in {"low", "medium"} else "main_map"
    if question_relevance == "background":
        return "appendix" if model_level in {"low", "medium"} else "supporting_map"
    if model_level in {"critical", "high"}:
        return "main_map"
    if model_level == "medium":
        return "supporting_map"
    return "appendix"


def _calibrated_importance_level(
    *,
    model_level: str,
    decision_function: str,
    default_use: str,
    claim_text: str,
    excerpt: str,
    question_relevance: str,
    scope_flags: list[str],
) -> tuple[str, list[str]]:
    text = _normalize_text(f"{claim_text} {excerpt}")
    reasons: list[str] = []
    score = {"low": 0, "medium": 1, "high": 2, "critical": 2}.get(model_level, 1)
    if question_relevance == "direct":
        score += 1
        reasons.append("direct_question_relevance")
    elif question_relevance == "indirect":
        reasons.append("indirect_question_relevance")
    elif question_relevance == "scope_limit":
        score += 1
        reasons.append("scope_limit_question_relevance")
    elif question_relevance == "background":
        score -= 1
        reasons.append("weak_question_relevance")
    elif question_relevance == "unspecified":
        reasons.append("unclassified_question_relevance")
    else:
        score -= 1
        reasons.append("unknown_question_relevance")
    if decision_function in {"answer_bearing", "crux", "scope_boundary", "confounder_or_bias", "implementation_constraint", "source_quality_caveat"}:
        score += 1
        reasons.append(f"decision_function:{decision_function}")
    if default_use == "appendix":
        score -= 1
        reasons.append("model_default_appendix")
    elif default_use == "exclude_unless_gap":
        score -= 2
        reasons.append("model_default_exclude_unless_gap")
    if _has_importance_signal(text):
        score += 1
        reasons.append("evidence_signal")
    if _has_quantity_signal(text):
        score += 1
        reasons.append("quantity_signal")
    if _non_evidence_text_reason(text):
        score -= 2
        reasons.append("non_evidence_text_signal")
    if "administrative_context" in scope_flags:
        score -= 1
        reasons.append("administrative_context")
    if question_relevance == "background":
        score = min(score, 1)
        reasons.append("question_relevance_cap")
    if default_use in {"appendix", "exclude_unless_gap"}:
        score = min(score, 1)
        reasons.append("default_use_cap")
    if score >= 6 and _critical_importance_allowed(text=text, decision_function=decision_function, question_relevance=question_relevance, scope_flags=scope_flags):
        return "critical", reasons
    if score >= 3:
        return "high", reasons
    if score >= 1:
        return "medium", reasons
    return "low", reasons


def _has_importance_signal(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:risk|effect|outcome|association|recommend|recommended|guideline|compared|depends|uncertain|confidence|evidence|limit|bias|causal|population|subgroup|endpoint|mechanism)\b",
            text,
        )
    )


def _has_quantity_signal(text: str) -> bool:
    return bool(re.search(r"\d|%|\b(?:ci|confidence interval|ratio|rate|risk ratio|hazard ratio|odds ratio)\b", text))


def _critical_importance_allowed(
    *,
    text: str,
    decision_function: str,
    question_relevance: str,
    scope_flags: list[str],
) -> bool:
    if decision_function == "crux":
        return True
    if decision_function in {"source_quality_caveat", "confounder_or_bias"}:
        return True
    if decision_function in {"scope_boundary", "implementation_constraint"} and question_relevance == "scope_limit":
        return True
    if any(flag in scope_flags for flag in ("target_population_mismatch", "outcome_mismatch", "intervention_or_exposure_mismatch")):
        return True
    return bool(
        re.search(
            r"\b(?:would change|turns on|hinges|critical|decisive|fully accounted|non-significant when adjusted|cannot establish causal|does not establish causal|highly heterogeneous)\b",
            text,
        )
    )


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


def _content_terms(text: str) -> set[str]:
    stopwords = {
        "about",
        "after",
        "again",
        "against",
        "between",
        "claim",
        "claims",
        "could",
        "does",
        "evidence",
        "from",
        "have",
        "into",
        "more",
        "risk",
        "source",
        "study",
        "than",
        "that",
        "their",
        "there",
        "these",
        "this",
        "with",
        "would",
    }
    return {token for token in re.findall(r"[a-z][a-z0-9_-]{2,}", text.lower()) if token not in stopwords}


def _compact_metadata_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:240]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).lower()).strip()
