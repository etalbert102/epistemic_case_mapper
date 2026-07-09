from __future__ import annotations

from typing import Any


def attach_label_audit(claim: dict[str, Any]) -> dict[str, Any]:
    audit = claim_label_audit(claim)
    claim["label_audit"] = audit
    warnings = claim.setdefault("validation_warnings", [])
    if isinstance(warnings, list):
        for warning in audit["warnings"]:
            if warning not in warnings:
                warnings.append(warning)
    return audit


def claim_label_audit(claim: dict[str, Any]) -> dict[str, Any]:
    model_role = _clean_label(claim.get("role"))
    model_relevance = _clean_label(claim.get("question_relevance"))
    model_importance = _importance_level(claim)
    model_default_use = _default_use(claim)
    decision_function = _clean_label(_decision_function(claim))
    source_card_role = _clean_label(_source_card_role(claim))
    deterministic_reason = _deterministic_relevance_reason(claim)
    score = _base_score(
        role=model_role,
        relevance=model_relevance,
        importance=model_importance,
        default_use=model_default_use,
        decision_function=decision_function,
        source_card_role=source_card_role,
    )
    score += _warning_score_adjustment(deterministic_reason, decision_function, source_card_role)
    score = max(0, min(100, score))
    bucket = _bucket(score, deterministic_reason)
    routing_default_use = {"core": "main_map", "supporting": "supporting_map", "appendix": "appendix"}[bucket]
    routing_importance = _routing_importance(score)
    routing_role = _routing_role(
        model_role=model_role,
        bucket=bucket,
        deterministic_reason=deterministic_reason,
        source_card_role=source_card_role,
        decision_function=decision_function,
    )
    warnings = _label_warnings(
        bucket=bucket,
        model_role=model_role,
        model_relevance=model_relevance,
        model_importance=model_importance,
        model_default_use=model_default_use,
        deterministic_reason=deterministic_reason,
        source_card_role=source_card_role,
    )
    return {
        "schema_id": "claim_label_audit_v1",
        "method": "deterministic_label_routing_v1",
        "core_decision_priority": score,
        "synthesis_bucket": bucket,
        "routing_role": routing_role,
        "routing_importance_level": routing_importance,
        "routing_default_use": routing_default_use,
        "warnings": warnings,
        "model_labels": {
            "role": model_role,
            "question_relevance": model_relevance,
            "decision_importance_level": model_importance,
            "decision_function": decision_function,
            "default_use": model_default_use,
            "source_card_role": source_card_role,
        },
        "deterministic_relevance_reason": deterministic_reason,
    }


def label_audit_warning_counts(claims: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for claim in claims:
        audit = claim.get("label_audit") if isinstance(claim.get("label_audit"), dict) else {}
        for warning in audit.get("warnings", []):
            counts[str(warning)] = counts.get(str(warning), 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def label_audit_bucket_counts(claims: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for claim in claims:
        audit = claim.get("label_audit") if isinstance(claim.get("label_audit"), dict) else {}
        bucket = str(audit.get("synthesis_bucket", "unknown"))
        counts[bucket] = counts.get(bucket, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def _base_score(
    *,
    role: str,
    relevance: str,
    importance: str,
    default_use: str,
    decision_function: str,
    source_card_role: str,
) -> int:
    score = {"critical": 82, "high": 68, "medium": 46, "low": 22}.get(importance, 40)
    score += {
        "crux": 12,
        "conclusion_support": 8,
        "scope_limit": 7,
        "implementation_constraint": 4,
        "background": -12,
        "other": -8,
    }.get(role, 0)
    score += {"direct": 10, "scope_limit": 7, "indirect": -4, "background": -14, "irrelevant": -35}.get(relevance, -5)
    score += {"main_map": 8, "supporting_map": 0, "appendix": -18, "exclude_unless_gap": -35}.get(default_use, -4)
    if decision_function in {"crux", "answer_bearing", "scope_boundary", "source_quality_caveat"}:
        score += 6
    elif decision_function in {"mechanism", "confounder_or_bias", "implementation_constraint"}:
        score += 3
    elif decision_function == "background_context":
        score -= 8
    if source_card_role == "main_finding":
        score += 5
    elif source_card_role in {"scope_limit", "source_quality_caveat", "counterfinding"}:
        score += 4
    elif source_card_role == "guidance_context":
        score -= 8
    return score


def _warning_score_adjustment(reason: str, decision_function: str, source_card_role: str) -> int:
    if not reason:
        return 0
    if reason == "question_administrative_context":
        return -60
    if reason == "question_population_mismatch":
        if source_card_role in {"scope_limit", "source_quality_caveat"} or decision_function in {"scope_boundary", "source_quality_caveat"}:
            return -6
        return -40
    if reason == "question_outcome_mismatch":
        if source_card_role in {"mechanism", "source_quality_caveat"} or decision_function in {"mechanism", "confounder_or_bias"}:
            return -8
        return -44
    return -20


def _bucket(score: int, deterministic_reason: str) -> str:
    if deterministic_reason == "question_administrative_context":
        return "appendix"
    if deterministic_reason and score >= 42:
        return "supporting"
    if score >= 74:
        return "core"
    if score >= 42:
        return "supporting"
    return "appendix"


def _routing_importance(score: int) -> str:
    if score >= 85:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 38:
        return "medium"
    return "low"


def _routing_role(
    *,
    model_role: str,
    bucket: str,
    deterministic_reason: str,
    source_card_role: str,
    decision_function: str,
) -> str:
    if bucket == "appendix" and model_role == "conclusion_support":
        return "background"
    if deterministic_reason and model_role == "conclusion_support" and source_card_role in {"mechanism", "source_quality_caveat"}:
        return "scope_limit"
    if decision_function in {"scope_boundary", "source_quality_caveat", "confounder_or_bias"}:
        return "scope_limit"
    return model_role or "other"


def _label_warnings(
    *,
    bucket: str,
    model_role: str,
    model_relevance: str,
    model_importance: str,
    model_default_use: str,
    deterministic_reason: str,
    source_card_role: str,
) -> list[str]:
    warnings: list[str] = []
    if deterministic_reason:
        warnings.append(f"deterministic_relevance:{deterministic_reason}")
    if deterministic_reason and model_relevance == "direct":
        warnings.append("model_direct_with_deterministic_warning")
    if deterministic_reason and model_importance in {"critical", "high"}:
        warnings.append("model_high_importance_with_deterministic_warning")
    if model_default_use == "main_map" and bucket != "core":
        warnings.append("model_main_map_demoted_by_audit")
    if model_role == "conclusion_support" and bucket == "appendix":
        warnings.append("model_conclusion_support_routed_to_appendix")
    if source_card_role == "guidance_context" and model_relevance == "direct":
        warnings.append("guidance_context_labeled_direct")
    if source_card_role == "main_finding" and bucket == "appendix":
        warnings.append("main_finding_routed_to_appendix")
    return warnings


def _importance_level(claim: dict[str, Any]) -> str:
    importance = claim.get("decision_importance") if isinstance(claim.get("decision_importance"), dict) else {}
    return _clean_label(importance.get("calibrated_level") or claim.get("decision_importance_level") or claim.get("importance"))


def _decision_function(claim: dict[str, Any]) -> str:
    importance = claim.get("decision_importance") if isinstance(claim.get("decision_importance"), dict) else {}
    return _clean_label(importance.get("decision_function") or claim.get("decision_function"))


def _default_use(claim: dict[str, Any]) -> str:
    importance = claim.get("decision_importance") if isinstance(claim.get("decision_importance"), dict) else {}
    return _clean_label(importance.get("default_use") or claim.get("default_use"))


def _source_card_role(claim: dict[str, Any]) -> str:
    card = claim.get("whole_doc_source_card") if isinstance(claim.get("whole_doc_source_card"), dict) else {}
    return _clean_label(card.get("source_card_role"))


def _deterministic_relevance_reason(claim: dict[str, Any]) -> str:
    validation = claim.get("deterministic_relevance_validation") if isinstance(claim.get("deterministic_relevance_validation"), dict) else {}
    return _clean_label(validation.get("reason"))


def _clean_label(value: Any) -> str:
    return str(value or "").strip().lower()
