from __future__ import annotations

from copy import deepcopy
from typing import Any


def candidate_priority(row: dict[str, Any]) -> int:
    try:
        score = int(row.get("decision_relevance_score", 0) or 0)
    except (TypeError, ValueError):
        score = 0
    if row.get("quantity_values"):
        score += 1
    if row.get("decision_role") in {"counterweight", "quantitative_anchor"}:
        score += 1
    if not row.get("source_grounded"):
        score -= 2
    return max(0, min(10, score))


def omitted_evidence_severity(row: dict[str, Any]) -> str:
    """Classify omitted rows for review without claiming semantic certainty."""

    priority = candidate_priority(row)
    role = str(row.get("decision_role") or "")
    recommendation = str(row.get("inclusion_recommendation") or "").lower()
    fit_statuses = {str(item).lower() for item in _string_list(row.get("map_question_fit_statuses"))}
    narrower = "narrower_than_question" in fit_statuses
    main_text = "main" in recommendation
    decision_role = role in {"strongest_support", "counterweight", "decision_crux", "quantitative_anchor"}
    always_decision_relevant_role = role in {"counterweight", "decision_crux", "quantitative_anchor"}
    if priority >= 9 and not narrower and (always_decision_relevant_role or (main_text and decision_role)):
        return "decision_critical"
    if priority >= 8 or role == "scope_boundary":
        return "moderate_context"
    return "review_worthy_context"


def omitted_candidate_row(row: dict[str, Any], *, reason: str = "review-worthy candidate was not retained after packet role budgets") -> dict[str, Any]:
    return _drop_empty(
        {
            "pool_id": row.get("pool_id"),
            "candidate_card_id": row.get("candidate_card_id"),
            "decision_role": row.get("decision_role"),
            "priority": candidate_priority(row),
            "omission_severity": omitted_evidence_severity(row),
            "inclusion_recommendation": row.get("inclusion_recommendation"),
            "question_fit_statuses": _string_list(row.get("map_question_fit_statuses"))[:5],
            "source_ids": _string_list(row.get("source_ids"))[:5],
            "quantity_values": _string_list(row.get("quantity_values"))[:5],
            "claim": _short_text(str(row.get("claim", "")), 220),
            "reason": reason,
        }
    )


def preserve_omissions_with_recomputed_quantities(
    pre_sufficiency: dict[str, Any],
    recomputed: dict[str, Any],
) -> dict[str, Any]:
    merged = deepcopy(pre_sufficiency)
    for key in ("quantity_retention", "quantity_obligation_ledger"):
        merged[key] = recomputed.get(key, merged.get(key))
    issues = _dedupe(
        [
            *[str(issue) for issue in merged.get("issues", []) if str(issue)],
            *[
                str(issue)
                for issue in recomputed.get("issues", [])
                if str(issue) in {"top_quantities_missing_from_must_retain"}
            ],
        ]
    )
    merged["issues"] = issues
    merged["status"] = "not_sufficient_for_synthesis" if _hard_failure(issues) else "usable_with_warnings" if issues else "ready"
    return merged


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _short_text(text: str, limit: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}


def _hard_failure(issues: list[str]) -> bool:
    return "counterweights_not_preserved" in issues and "missing_available_roles" in issues


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
