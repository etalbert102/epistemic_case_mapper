from __future__ import annotations

from typing import Any


def adapt_decision_model_to_frame(decision_model: dict[str, Any], decision_frame: dict[str, Any]) -> dict[str, Any]:
    if decision_frame.get("frame_type") != "representation_decision":
        return decision_model
    adapted = {**decision_model}
    default_answer = dict(decision_model.get("default_answer", {}) if isinstance(decision_model.get("default_answer"), dict) else {})
    default_answer.update(
        {
            "classification": "representation_with_named_disagreement_and_scope_limits",
            "plain_language_instruction": str(decision_frame.get("direct_answer", "")).strip()
            or "Represent the evidence as a scoped map with explicit disagreement and source-role boundaries.",
            "why_this_frame": (
                "The question asks how to represent an evidence slice, so the load-bearing output is a map of "
                "disagreement, source roles, and scope limits rather than a one-sided recommendation."
            ),
        }
    )
    adapted["default_answer"] = default_answer
    adapted["practical_recommendations"] = _dedupe(
        [
            "Use the packet to inspect which claims carry the representation, which claims bound it, and which tensions remain live.",
            "Keep adjudication outcomes, participant postmortems, forecasts, and later methodological critiques in separate evidence roles.",
            "Convert the mapped slice into a full-case conclusion only after adding the missing source families.",
            *[
                item
                for item in _string_list(decision_model.get("practical_recommendations"))
                if not _representation_inherited_recommendation_is_generic(item)
            ],
        ]
    )[:7]
    adapted["prose_requirements"] = [
        "Start by answering how the evidence should be represented.",
        "Name the disagreement or distinction the map preserves.",
        "Separate representation guidance from any underlying factual adjudication.",
        "Keep scope limits and missing evidence visible.",
    ]
    return adapted


def section_policy_for_frame(decision_frame: dict[str, Any]) -> dict[str, str]:
    if decision_frame.get("frame_type") == "representation_decision":
        return {
            "main_support": "Evidence supporting the recommended representation of the source packet.",
            "conflicting_evidence": "Evidence that creates live disagreement or tension within that representation.",
            "scope_limits": "Boundaries on what the represented slice can and cannot show.",
            "method_limits": "Measurement validity, source limitations, adjudication limits, and evidence-quality limits.",
        }
    return {
        "main_support": "Evidence supporting the bottom-line answer or low-concern/default recommendation.",
        "conflicting_evidence": "Evidence for harm, contrary findings, or tensions with the bottom line.",
        "scope_limits": "Subgroup, dose, population, endpoint, transfer, and conditional limits.",
        "method_limits": "Measurement validity, source limitations, guideline/practical implementation limits, and abstract-only/full-text limits.",
    }


def _representation_inherited_recommendation_is_generic(item: str) -> bool:
    lowered = item.lower()
    return any(
        marker in lowered
        for marker in (
            "low-concern",
            "default as neutral",
            "mapped benefits",
            "practical decision",
            "recommendation changes",
        )
    )


def _string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
