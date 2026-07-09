from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_packet_sufficiency import packet_quantity_retention


def build_packet_coverage_report(
    candidate_pool: list[dict[str, Any]],
    bundles: list[dict[str, Any]],
    retain_ledger: list[dict[str, Any]],
    source_trail: list[dict[str, Any]],
) -> dict[str, Any]:
    retained_ids = _retained_candidate_ids(bundles)
    high_priority_omitted = [
        row
        for row in candidate_pool
        if _candidate_priority(row) >= 7
        and row.get("candidate_card_id")
        and str(row.get("candidate_card_id")) not in retained_ids
        and "appendix" not in str(row.get("inclusion_recommendation", "")).lower()
    ]
    source_bottom_line_candidates = [
        row for row in candidate_pool if str(row.get("pretrim_kind")) == "source_bottom_line" and row.get("candidate_card_id")
    ]
    omitted_source_bottom_lines = [
        row for row in source_bottom_line_candidates if str(row.get("candidate_card_id")) not in retained_ids
    ]
    low_fit_primary = [row for row in bundles if _low_question_fit_primary_bundle(row)]
    return {
        "candidate_pool_count": len(candidate_pool),
        "evidence_bundle_count": len(bundles),
        "must_retain_count": len(retain_ledger),
        "high_priority_omitted_count": len(high_priority_omitted),
        "source_bottom_line_candidate_count": len(source_bottom_line_candidates),
        "source_bottom_line_retained_count": len(source_bottom_line_candidates) - len(omitted_source_bottom_lines),
        "omitted_source_bottom_line_ids": [str(row.get("candidate_card_id")) for row in omitted_source_bottom_lines[:20]],
        "source_label_missing_count": sum(1 for row in source_trail if not row.get("source_label")),
        "low_question_fit_primary_bundle_count": len(low_fit_primary),
        "low_question_fit_primary_bundle_ids": [str(row.get("bundle_id")) for row in low_fit_primary[:20]],
        "quantity_missing_count": len(packet_quantity_retention({"must_retain_ledger": retain_ledger}, candidate_pool)["missing_top_quantities"]),
        "warnings": _dedupe(
            [
                *(["high_priority_omitted_after_trimming"] if high_priority_omitted else []),
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


def _candidate_priority(row: dict[str, Any]) -> int:
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
