from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.model_schemas import ArgumentEvidenceItem, ArgumentModelOutput


def build_argument_model(
    candidate_map: dict[str, Any],
    quality_report: dict[str, Any],
    scaffold: dict[str, Any],
    *,
    question: str,
) -> dict[str, Any]:
    resolved_question = str(question or candidate_map.get("question") or "Decision question not specified.").strip()
    claim_lookup = {str(claim.get("claim_id", "")): claim for claim in _claims(candidate_map)}
    relation_lookup = {str(relation.get("relation_id", "")): relation for relation in _relations(candidate_map)}
    decision_model = _dict(scaffold.get("decision_model"))
    deterministic_answer = _proposed_answer(scaffold, decision_model)
    model = ArgumentModelOutput(
        decision_question=resolved_question,
        proposed_answer=deterministic_answer,
        confidence=_confidence(scaffold, quality_report),
        confidence_reasons=_confidence_reasons(scaffold, quality_report),
        strongest_support=_support_items(scaffold, claim_lookup),
        strongest_counterarguments=_counter_items(scaffold, decision_model, claim_lookup),
        evidence_weights=_evidence_weight_items(scaffold, claim_lookup),
        quantitative_anchors=_quantity_items(scaffold),
        scope_boundaries=_scope_items(scaffold, decision_model, claim_lookup),
        cruxes=_crux_items(scaffold, candidate_map, claim_lookup, relation_lookup),
        missing_evidence=_missing_items(scaffold),
        known_failure_modes=_failure_mode_items(scaffold, quality_report),
        audit={
            "method": "deterministic_argument_model_from_briefing_scaffold_v1",
            "claim_count": len(claim_lookup),
            "relation_count": len(relation_lookup),
            "quantity_count": _dict(scaffold.get("quantity_ledger")).get("quantity_count", 0),
            "map_quality_status": quality_report.get("status", "unknown"),
            "map_sufficiency_status": _dict(scaffold.get("map_sufficiency_report")).get("status", "unknown"),
        },
    )
    return model.model_dump()


def _proposed_answer(scaffold: dict[str, Any], decision_model: dict[str, Any]) -> str:
    synthesis = _dict(scaffold.get("decision_synthesis_model"))
    for key in ("bottom_line", "answer", "decision_read"):
        value = str(synthesis.get(key, "")).strip()
        if value:
            return _first_sentence(value)
    default = _dict(decision_model.get("default_answer"))
    instruction = str(default.get("plain_language_instruction", "")).strip()
    if instruction and not instruction.lower().startswith(("state ", "do not ", "phrase ")):
        return _first_sentence(instruction)
    classification = str(default.get("classification", "mixed_or_context_dependent")).replace("_", " ")
    return f"The current map supports a {classification} answer frame."


def _confidence(scaffold: dict[str, Any], quality_report: dict[str, Any]) -> str:
    value = str(scaffold.get("confidence_cap") or _confidence_cap(quality_report) or "medium").lower()
    return value if value in {"low", "medium", "high"} else "medium"


def _confidence_reasons(scaffold: dict[str, Any], quality_report: dict[str, Any]) -> list[str]:
    reasons = [f"Map quality status: {quality_report.get('status', 'unknown')}."]
    sufficiency = _dict(scaffold.get("map_sufficiency_report"))
    if sufficiency.get("status"):
        reasons.append(f"Map sufficiency status: {sufficiency['status']}.")
    for issue in quality_report.get("issues", []) if isinstance(quality_report.get("issues"), list) else []:
        if isinstance(issue, dict):
            message = str(issue.get("message") or issue.get("issue_type") or "").strip()
            if message:
                reasons.append(message)
    return _dedupe(reasons)[:5]


def _support_items(scaffold: dict[str, Any], claim_lookup: dict[str, dict[str, Any]]) -> list[ArgumentEvidenceItem]:
    rows = _top_section_rows(scaffold, "main_support")
    return [_item_from_evidence_row(row, claim_lookup, why="This is high-priority support for the current answer.") for row in rows[:5]]


def _counter_items(
    scaffold: dict[str, Any],
    decision_model: dict[str, Any],
    claim_lookup: dict[str, dict[str, Any]],
) -> list[ArgumentEvidenceItem]:
    items = [_item_from_evidence_row(row, claim_lookup, why="This limits or challenges the current answer.") for row in _top_section_rows(scaffold, "conflicting_evidence")[:5]]
    for row in decision_model.get("strongest_counterarguments", []) if isinstance(decision_model.get("strongest_counterarguments"), list) else []:
        if isinstance(row, dict):
            claim_ids = _claim_ids_from_cluster(row, claim_lookup)
            if claim_ids:
                items.append(
                    ArgumentEvidenceItem(
                        statement=str(row.get("proposition", "")).strip() or _claim_text(claim_ids[0], claim_lookup),
                        why_it_matters=f"Counterargument weight: {row.get('evidence_weight', 'medium')}.",
                        evidence_type=_evidence_type_from_text(str(row)),
                        endpoint_type=_endpoint_type_from_text(str(row)),
                        weight=_weight(str(row.get("evidence_weight", "medium"))),
                        claim_ids=claim_ids,
                        source_ids=_source_ids(claim_ids, claim_lookup),
                    )
                )
    return _dedupe_items(items)[:5]


def _evidence_weight_items(scaffold: dict[str, Any], claim_lookup: dict[str, dict[str, Any]]) -> list[ArgumentEvidenceItem]:
    ledger = _dict(scaffold.get("evidence_weighting_ledger"))
    rows = [row for row in ledger.get("all_evidence", []) if isinstance(row, dict)]
    rows = [row for row in rows if _row_argument_eligible(row)]
    rows = sorted(rows, key=_argument_row_rank)
    return [_item_from_evidence_row(row, claim_lookup, why="Selected by evidence-weighting ledger.") for row in rows[:8]]


def _quantity_items(scaffold: dict[str, Any]) -> list[ArgumentEvidenceItem]:
    cards = [card for card in scaffold.get("quantitative_evidence_cards", []) if isinstance(card, dict)]
    items: list[ArgumentEvidenceItem] = []
    for card in cards[:8]:
        claim_id = str(card.get("claim_id", "")).strip()
        quantities = [str(value) for value in card.get("key_quantities", []) if str(value).strip()]
        statement = str(card.get("claim") or card.get("interpretation_hint") or "; ".join(quantities)).strip()
        items.append(
            ArgumentEvidenceItem(
                statement=statement,
                why_it_matters=str(card.get("interpretation_hint", "")) or "Quantitative anchor for the main memo.",
                evidence_type=str(card.get("evidence_use", "quantitative_context")),
                endpoint_type=_endpoint_type_from_text(" ".join([statement, str(card.get("evidence_use", ""))])),
                weight="high" if card.get("effect_estimates") and card.get("uncertainty_intervals") else "medium",
                source_ids=[],
                claim_ids=[claim_id] if claim_id else [],
                relation_ids=[str(card.get("relation_id"))] if str(card.get("relation_id", "")).strip() else [],
                quantity_ids=[str(card.get("card_id", ""))] if str(card.get("card_id", "")).strip() else [],
                quantities=quantities,
            )
        )
    return _dedupe_items(items)[:8]


def _scope_items(
    scaffold: dict[str, Any],
    decision_model: dict[str, Any],
    claim_lookup: dict[str, dict[str, Any]],
) -> list[ArgumentEvidenceItem]:
    items = [_item_from_evidence_row(row, claim_lookup, why="This bounds where the answer applies.") for row in _top_section_rows(scaffold, "scope_limits")[:6]]
    for key, label in (("holds_for", "Holds for"), ("does_not_hold_for", "Does not hold for")):
        for value in decision_model.get(key, []) if isinstance(decision_model.get(key), list) else []:
            text = str(value).strip()
            claim_ids = _claim_ids_from_text(text, claim_lookup)
            if text and claim_ids:
                items.append(
                    ArgumentEvidenceItem(
                        statement=f"{label}: {text}",
                        why_it_matters="Scope boundary from the decision model.",
                        evidence_type=_evidence_type_from_text(text),
                        endpoint_type=_endpoint_type_from_text(text),
                        claim_ids=claim_ids,
                        source_ids=_source_ids(claim_ids, claim_lookup),
                    )
                )
    return _dedupe_items(items)[:8]


def _crux_items(
    scaffold: dict[str, Any],
    candidate_map: dict[str, Any],
    claim_lookup: dict[str, dict[str, Any]],
    relation_lookup: dict[str, dict[str, Any]],
) -> list[ArgumentEvidenceItem]:
    items: list[ArgumentEvidenceItem] = []
    for relation_id, relation in relation_lookup.items():
        relation_type = str(relation.get("relation_type", ""))
        if relation_type not in {"crux_for", "in_tension_with", "challenges", "depends_on"}:
            continue
        claim_ids = _dedupe([str(relation.get("source_claim", "")), str(relation.get("target_claim", ""))])
        items.append(
            ArgumentEvidenceItem(
                statement=str(relation.get("rationale", "")).strip() or relation_type.replace("_", " "),
                why_it_matters=f"Relation type: {relation_type}.",
                evidence_type="relation_crux",
                endpoint_type=_endpoint_type_from_text(str(relation)),
                weight=_weight(str(relation.get("relation_confidence") or relation.get("confidence") or "medium")),
                claim_ids=[claim_id for claim_id in claim_ids if claim_id in claim_lookup],
                relation_ids=[relation_id],
                source_ids=_source_ids(claim_ids, claim_lookup),
            )
        )
    for crux in scaffold.get("refined_cruxes", {}).get("cruxes", []) if isinstance(scaffold.get("refined_cruxes"), dict) else []:
        if isinstance(crux, dict):
            claim_ids = [claim_id for claim_id in crux.get("supporting_claim_ids", []) if str(claim_id) in claim_lookup]
            relation_ids = [relation_id for relation_id in crux.get("relation_ids", []) if str(relation_id) in relation_lookup]
            if claim_ids or relation_ids:
                items.append(
                    ArgumentEvidenceItem(
                        statement=str(crux.get("crux", "")).strip(),
                        why_it_matters=str(crux.get("why_it_matters", "")).strip(),
                        evidence_type="decision_crux",
                        endpoint_type=_endpoint_type_from_text(str(crux)),
                        claim_ids=[str(claim_id) for claim_id in claim_ids],
                        relation_ids=[str(relation_id) for relation_id in relation_ids],
                        source_ids=_source_ids([str(claim_id) for claim_id in claim_ids], claim_lookup),
                    )
                )
    return _dedupe_items(items)[:8]


def _missing_items(scaffold: dict[str, Any]) -> list[ArgumentEvidenceItem]:
    report = _dict(scaffold.get("map_sufficiency_report"))
    items: list[ArgumentEvidenceItem] = []
    for slot in report.get("missing_expected_decision_slots", []) if isinstance(report.get("missing_expected_decision_slots"), list) else []:
        items.append(ArgumentEvidenceItem(statement=f"Missing decision slot: {str(slot).replace('_', ' ')}.", why_it_matters="The memo should not fill this by inference.", evidence_type="missing_slot", weight="low"))
    for family in report.get("missing_expected_evidence_families", []) if isinstance(report.get("missing_expected_evidence_families"), list) else []:
        items.append(ArgumentEvidenceItem(statement=f"Missing evidence family: {str(family).replace('_', ' ')}.", why_it_matters="The memo should not imply this evidence was assessed.", evidence_type="missing_evidence_family", weight="low"))
    return _dedupe_items(items)[:6]


def _failure_mode_items(scaffold: dict[str, Any], quality_report: dict[str, Any]) -> list[ArgumentEvidenceItem]:
    items: list[ArgumentEvidenceItem] = []
    for issue in quality_report.get("issues", []) if isinstance(quality_report.get("issues"), list) else []:
        if isinstance(issue, dict):
            statement = str(issue.get("message") or issue.get("issue_type") or "").strip()
            if statement:
                items.append(ArgumentEvidenceItem(statement=statement, why_it_matters="Map quality issue.", evidence_type="quality_issue", weight="low"))
    for obligation in _dict(scaffold.get("map_sufficiency_report")).get("output_obligations", []) if isinstance(_dict(scaffold.get("map_sufficiency_report")).get("output_obligations"), list) else []:
        if isinstance(obligation, dict) and obligation.get("kind") == "missing_slot":
            items.append(ArgumentEvidenceItem(statement=str(obligation.get("message", "")).strip(), why_it_matters="Required output caveat.", evidence_type="output_obligation", weight="low"))
    return _dedupe_items(items)[:6]


def _top_section_rows(scaffold: dict[str, Any], section: str) -> list[dict[str, Any]]:
    ledger = _dict(scaffold.get("evidence_weighting_ledger"))
    rows_by_section = _dict(ledger.get("top_evidence_by_section"))
    rows = rows_by_section.get(section, [])
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and _row_argument_eligible(row)]


def _row_argument_eligible(row: dict[str, Any]) -> bool:
    if row.get("appendix_only"):
        return False
    eligibility = row.get("eligibility", {}) if isinstance(row.get("eligibility"), dict) else {}
    if str(eligibility.get("noise_severity", "")) == "high":
        return False
    return int(row.get("decision_relevance_score", 0) or 0) >= 3


def _argument_row_rank(row: dict[str, Any]) -> tuple[int, int, int, str]:
    return (
        0 if row.get("top_line_eligible") else 1,
        -int(row.get("score", 0)),
        -int(row.get("decision_relevance_score", 0) or 0),
        str(row.get("claim_id", "")),
    )


def _item_from_evidence_row(row: dict[str, Any], claim_lookup: dict[str, dict[str, Any]], *, why: str) -> ArgumentEvidenceItem:
    claim_id = str(row.get("claim_id", "")).strip()
    claim_ids = [claim_id] if claim_id in claim_lookup else _claim_ids_from_text(str(row.get("claim", "")), claim_lookup)
    statement = str(row.get("claim", "")).strip() or (claim_ids and _claim_text(claim_ids[0], claim_lookup)) or "Mapped evidence item."
    text = " ".join([statement, str(row.get("source", "")), str(row.get("evidence_family", ""))])
    return ArgumentEvidenceItem(
        statement=statement,
        why_it_matters=why,
        evidence_type=str(row.get("evidence_family") or _evidence_type_from_text(text)),
        endpoint_type=_endpoint_type_from_text(text),
        weight=_weight(str(row.get("weight", "medium"))),
        source_ids=_source_ids(claim_ids, claim_lookup),
        claim_ids=claim_ids,
        limitations=_row_limitations(row),
    )


def _claim_ids_from_cluster(row: dict[str, Any], claim_lookup: dict[str, dict[str, Any]]) -> list[str]:
    claim_ids: list[str] = []
    for claim in row.get("representative_claims", []) if isinstance(row.get("representative_claims"), list) else []:
        if isinstance(claim, dict):
            claim_id = str(claim.get("claim_id", "")).strip()
            if claim_id in claim_lookup:
                claim_ids.append(claim_id)
    return _dedupe(claim_ids)


def _claim_ids_from_text(text: str, claim_lookup: dict[str, dict[str, Any]]) -> list[str]:
    normalized = _normalize(text)
    matches: list[str] = []
    for claim_id, claim in claim_lookup.items():
        claim_text = _normalize(str(claim.get("claim") or claim.get("text") or ""))
        if claim_text and (claim_text in normalized or normalized in claim_text):
            matches.append(claim_id)
    return _dedupe(matches)


def _source_ids(claim_ids: list[str], claim_lookup: dict[str, dict[str, Any]]) -> list[str]:
    return _dedupe([str(claim_lookup.get(claim_id, {}).get("source_id", "")).strip() for claim_id in claim_ids])


def _claim_text(claim_id: str, claim_lookup: dict[str, dict[str, Any]]) -> str:
    claim = claim_lookup.get(claim_id, {})
    return str(claim.get("claim") or claim.get("text") or "").strip()


def _row_limitations(row: dict[str, Any]) -> list[str]:
    limitations: list[str] = []
    if str(row.get("weight", "")).lower() == "low":
        limitations.append("Low-weight evidence row.")
    if row.get("is_fallback"):
        limitations.append("Deterministic fallback row.")
    return limitations[:5]


def _evidence_type_from_text(text: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in ("randomized", "randomised", " rct", " trial")):
        return "rct_or_intervention"
    if any(marker in lowered for marker in ("meta-analysis", "systematic review", "scoping review", "overview")):
        return "evidence_synthesis"
    if any(marker in lowered for marker in ("cohort", "observational", "case-control", "survey")):
        return "cohort_or_observational"
    if any(marker in lowered for marker in ("guideline", "advisory", "recommendation")):
        return "guideline_or_recommendation"
    if any(marker in lowered for marker in ("mechanism", "biomarker", "concentration", "pathway")):
        return "mechanism_or_biomarker"
    return "general_evidence"


def _endpoint_type_from_text(text: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in ("mortality", "death", "event", "cardiovascular", "stroke", "failure rate", "outcome")):
        return "hard_or_decision_relevant_outcome"
    if any(marker in lowered for marker in ("biomarker", "concentration", "marker", "surrogate")):
        return "biomarker_or_surrogate"
    if any(marker in lowered for marker in ("dose", "threshold", "per day", "per week", "duration")):
        return "dose_or_exposure"
    if any(marker in lowered for marker in ("cost", "feasible", "implementation", "capacity", "workflow")):
        return "implementation"
    return "unspecified"


def _weight(value: str) -> str:
    lowered = value.lower()
    return lowered if lowered in {"low", "medium", "high"} else "medium"


def _first_sentence(text: str, max_chars: int = 280) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    match = re.search(r"(?<=[.!?])\s+", compact)
    first = compact[: match.start()].strip() if match else compact
    return first if len(first) <= max_chars else first[: max_chars - 3].rstrip(" ,.;") + "..."


def _normalize(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _claims(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    claims = candidate_map.get("claims", [])
    return [claim for claim in claims if isinstance(claim, dict)] if isinstance(claims, list) else []


def _relations(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    relations = candidate_map.get("relations", [])
    return [relation for relation in relations if isinstance(relation, dict)] if isinstance(relations, list) else []


def _confidence_cap(quality_report: dict[str, Any]) -> str:
    status = str(quality_report.get("status", "")).lower()
    score = int(quality_report.get("score", 0) or 0)
    issues = quality_report.get("issues", [])
    if status in {"thin", "limited", "not_usable"} or score < 70:
        return "low"
    if any(isinstance(issue, dict) and str(issue.get("severity", "")).lower() in {"risk", "error", "critical"} for issue in issues if isinstance(issues, list)):
        return "medium"
    return "high" if score >= 90 else "medium"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def _dedupe_items(items: list[ArgumentEvidenceItem]) -> list[ArgumentEvidenceItem]:
    seen: set[str] = set()
    result: list[ArgumentEvidenceItem] = []
    for item in items:
        key = _normalize(item.statement)
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result
