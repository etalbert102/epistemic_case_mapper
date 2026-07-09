from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_omission_priority import (
    candidate_priority,
    omitted_candidate_row,
    omitted_evidence_severity,
)
from epistemic_case_mapper.map_briefing_packet_sufficiency import build_quantity_obligation_ledger


def build_packet_coverage_report(
    candidate_pool: list[dict[str, Any]],
    bundles: list[dict[str, Any]],
    retain_ledger: list[dict[str, Any]],
    source_trail: list[dict[str, Any]],
) -> dict[str, Any]:
    retained_ids = _retained_candidate_ids(bundles)
    review_worthy_omitted = [
        row
        for row in candidate_pool
        if candidate_priority(row) >= 7
        and row.get("candidate_card_id")
        and str(row.get("candidate_card_id")) not in retained_ids
        and "appendix" not in str(row.get("inclusion_recommendation", "")).lower()
    ]
    represented_omissions = [
        _omission_representation(row, bundles)
        for row in review_worthy_omitted
    ]
    represented_omissions = [row for row in represented_omissions if row.get("represented")]
    truly_lost_omissions = [
        row
        for row in review_worthy_omitted
        if not any(item.get("candidate_card_id") == str(row.get("candidate_card_id")) for item in represented_omissions)
    ]
    decision_critical_lost = [row for row in truly_lost_omissions if omitted_evidence_severity(row) == "decision_critical"]
    moderate_context_lost = [row for row in truly_lost_omissions if omitted_evidence_severity(row) == "moderate_context"]
    review_context_lost = [row for row in truly_lost_omissions if omitted_evidence_severity(row) == "review_worthy_context"]
    source_bottom_line_candidates = [
        row for row in candidate_pool if str(row.get("pretrim_kind")) == "source_bottom_line" and row.get("candidate_card_id")
    ]
    omitted_source_bottom_lines = [
        row for row in source_bottom_line_candidates if str(row.get("candidate_card_id")) not in retained_ids
    ]
    low_fit_primary = [row for row in bundles if _low_question_fit_primary_bundle(row)]
    quantity_ledger = build_quantity_obligation_ledger({"evidence_bundles": bundles, "must_retain_ledger": retain_ledger}, candidate_pool)
    return {
        "candidate_pool_count": len(candidate_pool),
        "evidence_bundle_count": len(bundles),
        "must_retain_count": len(retain_ledger),
        "review_worthy_omitted_count": len(review_worthy_omitted),
        "represented_elsewhere_count": len(represented_omissions),
        "truly_lost_review_worthy_count": len(truly_lost_omissions),
        "truly_lost_decision_critical_count": len(decision_critical_lost),
        "truly_lost_moderate_context_count": len(moderate_context_lost),
        "truly_lost_review_context_count": len(review_context_lost),
        "represented_elsewhere": represented_omissions[:20],
        "truly_lost_decision_critical": [omitted_candidate_row(row) for row in decision_critical_lost[:20]],
        "truly_lost_moderate_context": [omitted_candidate_row(row) for row in moderate_context_lost[:20]],
        "truly_lost_review_context": [omitted_candidate_row(row) for row in review_context_lost[:20]],
        "high_priority_omitted_count": len(review_worthy_omitted),
        "high_priority_represented_elsewhere_count": len(represented_omissions),
        "high_priority_truly_lost_count": len(truly_lost_omissions),
        "high_priority_represented_elsewhere": represented_omissions[:20],
        "high_priority_truly_lost_ids": [str(row.get("candidate_card_id")) for row in truly_lost_omissions[:20]],
        "source_bottom_line_candidate_count": len(source_bottom_line_candidates),
        "source_bottom_line_retained_count": len(source_bottom_line_candidates) - len(omitted_source_bottom_lines),
        "omitted_source_bottom_line_ids": [str(row.get("candidate_card_id")) for row in omitted_source_bottom_lines[:20]],
        "source_label_missing_count": sum(1 for row in source_trail if not row.get("source_label")),
        "low_question_fit_primary_bundle_count": len(low_fit_primary),
        "low_question_fit_primary_bundle_ids": [str(row.get("bundle_id")) for row in low_fit_primary[:20]],
        "quantity_missing_count": quantity_ledger["missing_count"],
        "quantity_obligation_count": quantity_ledger["obligation_count"],
        "warnings": _dedupe(
            [
                *(["review_worthy_omitted_after_trimming"] if review_worthy_omitted else []),
                *(["decision_critical_evidence_lost_after_trimming"] if decision_critical_lost else []),
                *(["moderate_context_evidence_lost_after_trimming"] if moderate_context_lost else []),
                *(["source_bottom_lines_omitted_after_trimming"] if omitted_source_bottom_lines else []),
                *(["primary_bundles_low_question_fit"] if low_fit_primary else []),
                *(["no_must_retain_items"] if not retain_ledger else []),
                *(["no_evidence_bundles"] if not bundles else []),
            ]
        ),
    }


def _low_question_fit_primary_bundle(bundle: dict[str, Any]) -> bool:
    if str(bundle.get("decision_role") or "") not in {"strongest_support", "counterweight", "quantitative_anchor", "decision_crux"}:
        return False
    assessment = bundle.get("decision_relevance_assessment") if isinstance(bundle.get("decision_relevance_assessment"), dict) else {}
    return str(assessment.get("question_relevance_status") or "") == "low_question_overlap"


def _retained_candidate_ids(bundles: list[dict[str, Any]]) -> set[str]:
    return {
        card_id
        for bundle in bundles
        for card_id in _string_list(bundle.get("candidate_card_ids"))
        if card_id
    }


def _omission_representation(row: dict[str, Any], bundles: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_id = str(row.get("candidate_card_id", ""))
    for bundle in bundles:
        reason = _representation_reason(row, bundle)
        if reason:
            return {
                "candidate_card_id": candidate_id,
                "represented": True,
                "representing_bundle_id": bundle.get("bundle_id"),
                "reason": reason,
            }
    return {"candidate_card_id": candidate_id, "represented": False}


def _representation_reason(row: dict[str, Any], bundle: dict[str, Any]) -> str:
    if _overlap(row, bundle, "claim_ids"):
        return "shared_claim_id"
    if _overlap(row, bundle, "source_card_ids"):
        return "shared_source_card_id"
    if _overlap(row, bundle, "quantity_values"):
        return "shared_quantity_value"
    row_sources = set(_string_list(row.get("source_ids")))
    bundle_sources = set(_string_list(bundle.get("source_ids")))
    if row_sources and row_sources & bundle_sources and _normalized_claim_overlap(row, bundle) >= 4:
        return "shared_source_and_claim_terms"
    return ""


def _overlap(left: dict[str, Any], right: dict[str, Any], key: str) -> bool:
    return bool(set(_string_list(left.get(key))) & set(_string_list(right.get(key))))


def _normalized_claim_overlap(row: dict[str, Any], bundle: dict[str, Any]) -> int:
    left = {token for token in str(row.get("claim", "")).lower().split() if len(token) > 4}
    right = {token for token in str(bundle.get("claim", "")).lower().split() if len(token) > 4}
    return len(left & right)
def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
