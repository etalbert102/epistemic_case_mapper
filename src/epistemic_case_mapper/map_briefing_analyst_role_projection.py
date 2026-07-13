from __future__ import annotations

from typing import Any


FOREGROUND_MEMO_USES = {
    "load_bearing_primary_support",
    "load_bearing_counterweight",
    "quantitative_anchor",
    "scope_or_applicability",
    "decision_crux",
    "mechanism_or_context",
}

MEMO_READY_ROLE_BY_ANALYST_USE = {
    "load_bearing_primary_support": "strongest_support",
    "load_bearing_counterweight": "strongest_counterweight",
    "quantitative_anchor": "quantitative_anchor",
    "scope_or_applicability": "scope_boundary",
    "decision_crux": "decision_crux",
    "mechanism_or_context": "mechanism_or_explanation",
    "background_only": "context_only",
    "needs_human_or_model_review": "uncertain_role",
}

SECTION_BY_MEMO_USE = {
    "load_bearing_primary_support": "primary_reasoning_chain",
    "load_bearing_counterweight": "main_counterweights",
    "decision_crux": "decision_cruxes",
    "scope_or_applicability": "scope_and_applicability",
    "quantitative_anchor": "quantitative_anchors",
    "mechanism_or_context": "background_context",
    "background_only": "background_context",
    "needs_human_or_model_review": "background_context",
}


def project_group_role(group: dict[str, Any], memo_role: str) -> dict[str, Any]:
    original = str(group.get("source_memo_role") or group.get("memo_role") or "").strip()
    if memo_role == original:
        return dict(group)
    return {**group, "memo_role": memo_role, "source_memo_role": original}


def memo_ready_role_for_group(group: dict[str, Any]) -> str:
    return MEMO_READY_ROLE_BY_ANALYST_USE.get(effective_memo_role(group), "uncertain_role")


def effective_memo_role(group: dict[str, Any]) -> str:
    memo_role = str(group.get("memo_role") or "").strip()
    relation = str(group.get("answer_relation") or "").strip()
    effect = str(group.get("effect_on_final_answer") or "").strip().lower()
    if relation == "supports_answer" or effect.startswith("supports current_best_answer") or effect == "rebuts alternative":
        if memo_role in {"quantitative_anchor", "decision_crux", "mechanism_or_context"}:
            return memo_role
        return "load_bearing_primary_support"
    if relation == "bounds_scope" or effect.startswith("bounds current_best_answer"):
        return "scope_or_applicability"
    if relation == "identifies_crux" or effect == "explains tension":
        return "decision_crux"
    if relation == "challenges_answer" or effect.startswith(("weakens current_best_answer", "overturns current_best_answer")):
        return "load_bearing_counterweight"
    if relation == "contextualizes_answer" or effect == "background":
        if memo_role in {"load_bearing_primary_support", "load_bearing_counterweight"}:
            return "mechanism_or_context"
        return memo_role if memo_role in SECTION_BY_MEMO_USE else "mechanism_or_context"
    return memo_role if memo_role in SECTION_BY_MEMO_USE else "needs_human_or_model_review"
