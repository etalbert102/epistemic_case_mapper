from __future__ import annotations

from collections import Counter
from typing import Any


CORE_USES = {"main_map", "main", "core", "answer"}
SUPPORTING_USES = {"supporting_map", "supporting", "context", "mechanism"}
APPENDIX_USES = {"appendix", "background", "source_context", "discard"}
HIGH_IMPORTANCE = {"high", "critical", "load_bearing"}
MEDIUM_IMPORTANCE = {"medium", "moderate"}
LOW_IMPORTANCE = {"low", "minimal", "none"}
DIRECT_RELEVANCE = {"direct", "high", "directly_relevant"}
INDIRECT_RELEVANCE = {"indirect", "partial", "supporting", "contextual"}
LOW_RELEVANCE = {"low", "none", "off_question", "not_relevant", "irrelevant"}
QUESTION_MISMATCH_REASONS = {
    "question_outcome_mismatch",
    "question_population_mismatch",
    "question_intervention_mismatch",
    "question_setting_mismatch",
    "question_scope_mismatch",
}


def triage_claims_for_relation_building(
    claims: list[dict[str, Any]],
    *,
    minimum_relation_claims: int = 2,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Annotate claims and return the subset that should enter relation extraction.

    The triage is deliberately deterministic over model-provided labels and
    validation warnings. It may route a claim away from relation extraction, but
    it preserves every claim in the returned full claim list and emits a report
    so semantic exclusions are inspectable.
    """
    triaged = [_annotate_claim(claim) for claim in claims]
    eligible = [claim for claim in triaged if claim.get("relation_building_eligible") is True]
    fallback_used = False
    fallback_claim_ids: list[str] = []
    if len(eligible) < minimum_relation_claims and len(triaged) >= minimum_relation_claims:
        fallback_used = True
        selected_ids = {str(claim.get("claim_id", "")) for claim in eligible}
        for claim in sorted(triaged, key=_relation_priority_key):
            claim_id = str(claim.get("claim_id", ""))
            if claim_id in selected_ids:
                continue
            claim["relation_building_eligible"] = True
            claim["relation_triage_reasons"] = [
                *_list_of_strings(claim.get("relation_triage_reasons")),
                "minimum_relation_claim_floor",
            ]
            fallback_claim_ids.append(claim_id)
            eligible.append(claim)
            selected_ids.add(claim_id)
            if len(eligible) >= minimum_relation_claims:
                break
    report = _triage_report(triaged, eligible, fallback_used=fallback_used, fallback_claim_ids=fallback_claim_ids)
    return triaged, eligible, report


def _annotate_claim(claim: dict[str, Any]) -> dict[str, Any]:
    annotated = dict(claim)
    bucket, eligible, reasons = _triage_bucket(claim)
    annotated["relation_triage_bucket"] = bucket
    annotated["relation_building_eligible"] = eligible
    annotated["relation_triage_reasons"] = reasons
    return annotated


def _triage_bucket(claim: dict[str, Any]) -> tuple[str, bool, list[str]]:
    labels = _claim_labels(claim)
    mismatch_reasons = labels["mismatch_reasons"]
    reasons: list[str] = []
    if mismatch_reasons:
        reasons.append("question_mismatch:" + ",".join(sorted(mismatch_reasons)))
    if labels["bucket"] == "core" or labels["routing_use"] in CORE_USES or labels["default_use"] in CORE_USES:
        reasons.append("core_label")
    if labels["relevance"] in DIRECT_RELEVANCE:
        reasons.append("direct_relevance")
    if labels["importance"] in HIGH_IMPORTANCE:
        reasons.append("high_importance")
    if labels["bucket"] == "supporting" or labels["routing_use"] in SUPPORTING_USES or labels["default_use"] in SUPPORTING_USES:
        reasons.append("supporting_label")
    if labels["relevance"] in INDIRECT_RELEVANCE:
        reasons.append("indirect_relevance")
    if labels["importance"] in MEDIUM_IMPORTANCE:
        reasons.append("medium_importance")
    if labels["bucket"] == "appendix" or labels["routing_use"] in APPENDIX_USES or labels["default_use"] in APPENDIX_USES:
        reasons.append("appendix_label")
    if labels["relevance"] in LOW_RELEVANCE or labels["importance"] in LOW_IMPORTANCE:
        reasons.append("low_relevance_or_importance")

    if _is_question_mismatch_appendix(labels):
        return "excluded_from_relation_building", False, reasons or ["off_question_appendix"]
    if _has_core_signal(labels):
        return "core", True, reasons or ["core_signal"]
    if _has_supporting_signal(labels):
        return "supporting", True, reasons or ["supporting_signal"]
    if labels["relevance"] in LOW_RELEVANCE or labels["default_use"] in APPENDIX_USES or labels["bucket"] == "appendix":
        return "appendix", False, reasons or ["appendix_signal"]
    return "supporting", True, reasons or ["default_relation_eligible"]


def _claim_labels(claim: dict[str, Any]) -> dict[str, Any]:
    audit = claim.get("label_audit") if isinstance(claim.get("label_audit"), dict) else {}
    relevance_validation = (
        claim.get("deterministic_relevance_validation")
        if isinstance(claim.get("deterministic_relevance_validation"), dict)
        else {}
    )
    validation_warnings = set(_list_of_strings(claim.get("validation_warnings")))
    audit_warnings = set(_list_of_strings(audit.get("warnings")))
    relevance_reason = str(relevance_validation.get("reason", "")).strip().lower()
    mismatch_reasons = {
        reason
        for reason in [*validation_warnings, *audit_warnings, relevance_reason]
        if reason in QUESTION_MISMATCH_REASONS
    }
    return {
        "bucket": str(audit.get("synthesis_bucket") or "").strip().lower(),
        "routing_use": str(audit.get("routing_default_use") or "").strip().lower(),
        "relevance": str(claim.get("question_relevance") or "").strip().lower(),
        "importance": str(claim.get("decision_importance_level") or "").strip().lower(),
        "default_use": str(claim.get("default_use") or "").strip().lower(),
        "decision_function": str(claim.get("decision_function") or "").strip().lower(),
        "mismatch_reasons": mismatch_reasons,
    }


def _is_question_mismatch_appendix(labels: dict[str, Any]) -> bool:
    if not labels["mismatch_reasons"]:
        return False
    low_route = (
        labels["bucket"] == "appendix"
        or labels["routing_use"] in APPENDIX_USES
        or labels["default_use"] in APPENDIX_USES
        or labels["relevance"] in LOW_RELEVANCE
    )
    return bool(low_route and labels["importance"] not in HIGH_IMPORTANCE)


def _has_core_signal(labels: dict[str, Any]) -> bool:
    return (
        labels["bucket"] == "core"
        or labels["routing_use"] in CORE_USES
        or labels["default_use"] in CORE_USES
        or (labels["relevance"] in DIRECT_RELEVANCE and labels["importance"] in HIGH_IMPORTANCE)
    )


def _has_supporting_signal(labels: dict[str, Any]) -> bool:
    return (
        labels["bucket"] == "supporting"
        or labels["routing_use"] in SUPPORTING_USES
        or labels["default_use"] in SUPPORTING_USES
        or labels["relevance"] in INDIRECT_RELEVANCE
        or labels["importance"] in MEDIUM_IMPORTANCE
        or labels["decision_function"] in {"mechanism", "scope", "context", "counterweight", "constraint"}
    )


def _relation_priority_key(claim: dict[str, Any]) -> tuple[int, str]:
    labels = _claim_labels(claim)
    score = 0
    if labels["importance"] in HIGH_IMPORTANCE:
        score -= 30
    elif labels["importance"] in MEDIUM_IMPORTANCE:
        score -= 15
    if labels["relevance"] in DIRECT_RELEVANCE:
        score -= 20
    elif labels["relevance"] in INDIRECT_RELEVANCE:
        score -= 10
    if labels["bucket"] == "core" or labels["default_use"] in CORE_USES:
        score -= 20
    elif labels["bucket"] == "supporting" or labels["default_use"] in SUPPORTING_USES:
        score -= 10
    if labels["mismatch_reasons"]:
        score += 25
    return score, str(claim.get("claim_id", ""))


def _triage_report(
    triaged: list[dict[str, Any]],
    eligible: list[dict[str, Any]],
    *,
    fallback_used: bool,
    fallback_claim_ids: list[str],
) -> dict[str, Any]:
    bucket_counts = Counter(str(claim.get("relation_triage_bucket", "unknown")) for claim in triaged)
    eligible_ids = [str(claim.get("claim_id", "")) for claim in eligible if str(claim.get("claim_id", "")).strip()]
    excluded = [
        {
            "claim_id": claim.get("claim_id"),
            "source_id": claim.get("source_id"),
            "claim": claim.get("claim"),
            "bucket": claim.get("relation_triage_bucket"),
            "reasons": claim.get("relation_triage_reasons", []),
            "question_relevance": claim.get("question_relevance"),
            "decision_importance_level": claim.get("decision_importance_level"),
            "default_use": claim.get("default_use"),
            "label_audit": claim.get("label_audit", {}),
        }
        for claim in triaged
        if claim.get("relation_building_eligible") is not True
    ]
    return {
        "schema_id": "claim_relation_triage_report_v1",
        "method": "deterministic_routing_over_model_claim_labels",
        "input_claim_count": len(triaged),
        "eligible_claim_count": len(eligible),
        "excluded_claim_count": len(excluded),
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "eligible_claim_ids": eligible_ids,
        "excluded_claims": excluded,
        "fallback_used": fallback_used,
        "fallback_claim_ids": fallback_claim_ids,
    }


def _list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip().lower() for item in value if str(item).strip()]
