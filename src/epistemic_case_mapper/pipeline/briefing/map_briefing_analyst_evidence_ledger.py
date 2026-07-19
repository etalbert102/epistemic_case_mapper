from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_residual_quantities import (
    likely_residual_quantity,
    quantity_covered_by_text,
    quantity_signature,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_appraisal import appraisal_for_sources
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_claim_context import source_context_fields as _source_context_fields
from epistemic_case_mapper.pipeline.documents.evidence_bundles import normalize_assertion_bundles
from epistemic_case_mapper.pipeline.map.staged_semantic_claim_quantities import claim_quantity_values, normalize_claim_quantity_rows


def build_analyst_evidence_ledger(
    packet: dict[str, Any],
    *,
    memo_warning_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a stable evidence inventory for later analyst adjudication."""

    packet = packet if isinstance(packet, dict) else {}
    warning_packet = memo_warning_packet if isinstance(memo_warning_packet, dict) else _dict(packet.get("memo_warning_packet"))
    rows = [
        *_bundle_rows(packet),
        *_warning_rows(warning_packet),
        *_review_context_omission_rows(packet),
        *_top_quantity_rows(packet),
    ]
    rows = _dedupe_rows(rows)
    return {
        "schema_id": "analyst_evidence_ledger_v1",
        "method": "stable_inventory_for_llm_adjudicated_packet_construction",
        "decision_question": str(packet.get("decision_question") or "").strip(),
        "stable_final_answer_frame": _stable_final_answer_frame(packet, question=str(packet.get("decision_question") or "")),
        "row_count": len(rows),
        "summary": _summary(rows),
        "coverage_checks": _coverage_checks(packet, warning_packet, rows),
        "rows": rows,
    }


def build_analyst_map_evidence_ledger(
    candidate_map: dict[str, Any],
    scaffold: dict[str, Any],
    *,
    question: str,
    memo_warning_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an analyst ledger from the retained claim map instead of a trimmed packet."""

    candidate_map = candidate_map if isinstance(candidate_map, dict) else {}
    scaffold = scaffold if isinstance(scaffold, dict) else {}
    warning_packet = memo_warning_packet if isinstance(memo_warning_packet, dict) else {}
    relation_lookup = _claim_relation_context(candidate_map)
    source_labels = _source_labels_from_scaffold(scaffold)
    source_appraisal_report = _dict(scaffold.get("source_appraisal_report"))
    quantity_lookup = _quantity_lookup(scaffold)
    rows = [
        _claim_row(
            claim,
            index=index,
            relation_context=relation_lookup.get(str(claim.get("claim_id") or ""), []),
            source_labels=source_labels,
            source_appraisal_report=source_appraisal_report,
            quantity_lookup=quantity_lookup,
        )
        for index, claim in enumerate(_list(candidate_map.get("claims")), start=1)
        if isinstance(claim, dict) and str(claim.get("claim_id") or "").strip()
    ]
    rows.extend(_decision_edge_rows(candidate_map, source_labels=source_labels, source_appraisal_report=source_appraisal_report))
    rows.extend(_warning_rows(warning_packet))
    rows = _dedupe_rows(rows)
    packet = _dict(scaffold.get("decision_briefing_packet"))
    return {
        "schema_id": "analyst_evidence_ledger_v1",
        "method": "retained_claim_map_inventory_for_llm_adjudicated_packet_construction",
        "decision_question": str(question or scaffold.get("question") or "").strip(),
        "stable_final_answer_frame": _stable_final_answer_frame(packet, question=str(question or scaffold.get("question") or "")),
        "row_count": len(rows),
        "summary": _summary(rows),
        "coverage_checks": _map_coverage_checks(candidate_map, warning_packet, rows),
        "rows": rows,
    }


def _claim_row(
    claim: dict[str, Any],
    *,
    index: int,
    relation_context: list[dict[str, Any]],
    source_labels: dict[str, str],
    source_appraisal_report: dict[str, Any],
    quantity_lookup: dict[str, list[str]],
) -> dict[str, Any]:
    claim_id = str(claim.get("claim_id") or f"claim_{index:03d}")
    source_ids = _dedupe([str(claim.get("source_id") or ""), *_string_list(claim.get("supporting_sources"))])
    labels = [source_labels.get(source_id, source_id) for source_id in source_ids if source_id]
    source_appraisal = appraisal_for_sources(source_appraisal_report, [*source_ids, *labels])
    claim_quantities = _claim_bound_quantities(claim)
    assertion_bundles = _claim_assertion_bundles(claim, claim_quantities=claim_quantities, source_ids=source_ids)
    claim_bound_values = _dedupe([*claim_quantity_values(claim_quantities), *_string_list(claim.get("quantity_values"))])
    residual_values = _residual_quantity_values(claim, claim_bound_values=claim_bound_values, quantity_lookup=quantity_lookup.get(claim_id, []))
    residual_candidates = _residual_quantity_candidates(claim, residual_values)
    quantity_values = _dedupe([*claim_bound_values, *residual_candidates])
    source_bottom_lines = _source_bottom_lines_for_claim(claim)
    source_bottom_line_signals = _source_bottom_line_signals(source_bottom_lines)
    source_context = _source_context_fields(_dict(claim.get("whole_doc_source_card")), [])
    return _drop_empty(
        {
            "evidence_item_id": f"claim:{claim_id}",
            "input_kind": "retained_map_claim",
            "current_packet_location": "generated_map.claims",
            "claim_id": claim_id,
            "source_ids": source_ids,
            "source_labels": labels,
            "source_appraisal": source_appraisal,
            "source_use_warnings": _string_list(source_appraisal.get("source_use_warnings")),
            "allowed_wording": source_appraisal.get("allowed_wording"),
            "claim": _short_text(str(claim.get("claim") or ""), 520),
            "source_excerpt": _short_text(str(claim.get("source_quote") or claim.get("excerpt") or ""), 520),
            "source_bottom_lines": source_bottom_lines,
            "source_bottom_line_signals": source_bottom_line_signals,
            **source_context,
            "current_role": _claim_current_role(claim),
            "current_priority": _priority_from_claim(claim),
            "quality": _dict(claim.get("source_alignment")).get("status") or claim.get("entailed_by_excerpt"),
            "directionality": claim.get("question_relevance"),
            "quantity_values": quantity_values,
            "claim_quantities": claim_quantities,
            "assertion_bundles": assertion_bundles,
            "evidence_bundle_ids": [
                str(row.get("evidence_bundle_id") or "")
                for row in assertion_bundles
                if isinstance(row, dict) and str(row.get("evidence_bundle_id") or "").strip()
            ],
            "claim_bound_quantity_values": claim_bound_values,
            "residual_quantity_values": residual_values,
            "residual_quantity_candidate_values": residual_candidates,
            "why_it_matters": _short_text(str(claim.get("importance_rationale") or claim.get("relevance_rationale") or ""), 260),
            "relation_ids": [str(row.get("relation_id") or "") for row in relation_context if row.get("relation_id")],
            "relation_context": relation_context[:8],
            "existing_warning_codes": _claim_warning_codes(claim),
        }
    )


def _claim_bound_quantities(claim: dict[str, Any]) -> list[dict[str, Any]]:
    source_card = _dict(claim.get("whole_doc_source_card"))
    rows = [
        *_list(claim.get("claim_quantities")),
        *_list(source_card.get("claim_quantities")),
    ]
    source_ids = _dedupe([str(claim.get("source_id") or ""), *_string_list(claim.get("supporting_sources"))])
    if rows:
        return normalize_claim_quantity_rows(
            rows,
            claim_id=str(claim.get("claim_id") or ""),
            source_id=source_ids[0] if source_ids else "",
            source_span=str(claim.get("source_span") or ""),
            source_quote=str(claim.get("source_quote") or claim.get("excerpt") or ""),
            claim_text=str(claim.get("claim") or ""),
        )
    return normalize_claim_quantity_rows(
        _string_list(claim.get("quantity_values")),
        claim_id=str(claim.get("claim_id") or ""),
        source_id=source_ids[0] if source_ids else "",
        source_span=str(claim.get("source_span") or ""),
        source_quote=str(claim.get("source_quote") or claim.get("excerpt") or ""),
        claim_text=str(claim.get("claim") or ""),
    )


def _claim_assertion_bundles(
    claim: dict[str, Any],
    *,
    claim_quantities: list[dict[str, Any]],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    source_card = _dict(claim.get("whole_doc_source_card"))
    for bundle in [
        *_list(claim.get("assertion_bundles")),
        *_list(source_card.get("assertion_bundles")),
        *[
            nested
            for quantity in claim_quantities
            if isinstance(quantity, dict)
            for nested in _list(quantity.get("assertion_bundles"))
        ],
    ]:
        if not isinstance(bundle, dict):
            continue
        bundle_id = str(bundle.get("evidence_bundle_id") or "").strip()
        if bundle_id and bundle_id not in seen:
            seen.add(bundle_id)
            rows.append(bundle)
    if rows:
        return rows
    return normalize_assertion_bundles(
        claim_quantities,
        claim_id=str(claim.get("claim_id") or ""),
        source_id=source_ids[0] if source_ids else str(claim.get("source_id") or ""),
        source_span=str(claim.get("source_span") or ""),
        source_quote=str(claim.get("source_quote") or claim.get("excerpt") or ""),
        claim_text=str(claim.get("claim") or ""),
    )


def _residual_quantity_values(
    claim: dict[str, Any],
    *,
    claim_bound_values: list[str],
    quantity_lookup: list[str],
) -> list[str]:
    source_card = _dict(claim.get("whole_doc_source_card"))
    covered = {quantity_signature(value) for value in claim_bound_values}
    claim_text = str(claim.get("claim") or "")
    rows = []
    for value in [*_string_list(source_card.get("quantities")), *_string_list(quantity_lookup)]:
        signature = quantity_signature(value)
        if not signature or signature in covered:
            continue
        if quantity_covered_by_text(value, claim_text):
            continue
        rows.append(value)
    return _dedupe(rows)


def _residual_quantity_candidates(claim: dict[str, Any], residual_values: list[str]) -> list[str]:
    context = " ".join(
        [
            str(claim.get("claim") or ""),
            str(claim.get("importance_rationale") or ""),
            str(claim.get("relevance_rationale") or ""),
            str(claim.get("decision_function") or ""),
        ]
    )
    return _dedupe([value for value in residual_values if likely_residual_quantity(value, context_text=context)])


def _claim_relation_context(candidate_map: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    context: dict[str, list[dict[str, Any]]] = {}
    claim_lookup = {
        str(claim.get("claim_id") or ""): claim
        for claim in _list(candidate_map.get("claims"))
        if isinstance(claim, dict)
    }
    for relation in _list(candidate_map.get("relations")):
        if not isinstance(relation, dict):
            continue
        left = str(relation.get("source_claim") or "")
        right = str(relation.get("target_claim") or "")
        row = {
            "relation_id": relation.get("relation_id"),
            "relation_type": relation.get("relation_type"),
            "relation_confidence": relation.get("relation_confidence"),
            "relation_contract": _relation_contract_summary(relation),
            "candidate_pair": _candidate_pair_summary(relation),
            "other_claim_id": "",
            "other_claim": "",
            "rationale": _short_text(str(relation.get("rationale") or ""), 220),
        }
        if left:
            context.setdefault(left, []).append({**row, **_other_claim_context(right, claim_lookup.get(right, {}))})
        if right:
            context.setdefault(right, []).append({**row, **_other_claim_context(left, claim_lookup.get(left, {}))})
    return context


def _other_claim_context(claim_id: str, claim: dict[str, Any]) -> dict[str, Any]:
    source_bottom_lines = _source_bottom_lines_for_claim(claim)
    return _drop_empty(
        {
            "other_claim_id": claim_id,
            "other_claim": _short_text(str(claim.get("claim") or ""), 180),
            "other_source_bottom_lines": source_bottom_lines,
            "other_source_bottom_line_signals": _source_bottom_line_signals(source_bottom_lines),
        }
    )


def _decision_edge_rows(
    candidate_map: dict[str, Any],
    *,
    source_labels: dict[str, str],
    source_appraisal_report: dict[str, Any],
) -> list[dict[str, Any]]:
    claim_lookup = {
        str(claim.get("claim_id") or ""): claim
        for claim in _list(candidate_map.get("claims"))
        if isinstance(claim, dict)
    }
    rows: list[dict[str, Any]] = []
    for relation in _list(candidate_map.get("relations")):
        if not isinstance(relation, dict):
            continue
        relation_id = str(relation.get("relation_id") or "").strip()
        if not relation_id:
            continue
        source_claim_id = str(relation.get("source_claim") or "").strip()
        target_claim_id = str(relation.get("target_claim") or "").strip()
        source_claim = claim_lookup.get(source_claim_id, {})
        target_claim = claim_lookup.get(target_claim_id, {})
        source_ids = _dedupe(
            [
                str(source_claim.get("source_id") or ""),
                str(target_claim.get("source_id") or ""),
            ]
        )
        labels = [source_labels.get(source_id, source_id) for source_id in source_ids if source_id]
        source_appraisal = appraisal_for_sources(source_appraisal_report, [*source_ids, *labels])
        contract = relation.get("relation_contract") if isinstance(relation.get("relation_contract"), dict) else {}
        candidate_pair = _candidate_pair_summary(relation)
        source_bottom_lines = _dedupe_source_bottom_lines(
            [*_source_bottom_lines_for_claim(source_claim), *_source_bottom_lines_for_claim(target_claim)]
        )
        endpoint_claims = _endpoint_claims_for_relation(source_claim_id, source_claim, target_claim_id, target_claim)
        rows.append(
            _drop_empty(
                {
                    "evidence_item_id": f"relation:{relation_id}",
                    "input_kind": "candidate_decision_edge",
                    "current_packet_location": "generated_map.relations",
                    "relation_id": relation_id,
                    "claim_ids": _dedupe([source_claim_id, target_claim_id]),
                    "source_ids": source_ids,
                    "source_labels": labels,
                    "source_appraisal": source_appraisal,
                    "source_use_warnings": _string_list(source_appraisal.get("source_use_warnings")),
                    "allowed_wording": source_appraisal.get("allowed_wording"),
                    "claim": _short_text(_decision_edge_statement(relation, source_claim, target_claim), 620),
                    "source_excerpt": _short_text(_decision_edge_excerpt(source_claim, target_claim), 620),
                    "source_bottom_lines": source_bottom_lines,
                    "source_bottom_line_signals": _source_bottom_line_signals(source_bottom_lines),
                    "current_role": _relation_current_role(str(relation.get("relation_type") or "")),
                    "relation_semantic_role": str(relation.get("relation_type") or ""),
                    "relation_contract": _relation_contract_summary(relation),
                    "candidate_pair": candidate_pair,
                    "endpoint_claims": endpoint_claims,
                    "relation_endpoint_answer_matrix": _relation_endpoint_answer_matrix(
                        relation,
                        endpoint_claims,
                    ),
                    "current_priority": _relation_priority(relation),
                    "current_weight": str(relation.get("relation_confidence") or "medium"),
                    "quality": str(relation.get("relation_provenance") or "model_classified"),
                    "directionality": str(relation.get("relation_type") or ""),
                    "why_it_matters": _short_text(str(contract.get("why_decision_relevant") or relation.get("why_decision_relevant") or relation.get("rationale") or ""), 320),
                    "failure_condition": _short_text(str(contract.get("failure_condition") or relation.get("failure_condition") or ""), 260),
                    "existing_warning_codes": _relation_warning_codes(relation),
                }
            )
        )
    return rows


def _relation_contract_summary(relation: dict[str, Any]) -> dict[str, str]:
    contract = relation.get("relation_contract") if isinstance(relation.get("relation_contract"), dict) else {}
    return _drop_empty(
        {
            "edge_basis": str(contract.get("edge_basis") or ""),
            "source_anchor_a": _short_text(str(contract.get("source_anchor_a") or ""), 180),
            "source_anchor_b": _short_text(str(contract.get("source_anchor_b") or ""), 180),
            "why_decision_relevant": _short_text(str(contract.get("why_decision_relevant") or ""), 240),
            "failure_condition": _short_text(str(contract.get("failure_condition") or ""), 220),
        }
    )


def _candidate_pair_summary(relation: dict[str, Any]) -> dict[str, Any]:
    pair = relation.get("candidate_pair") if isinstance(relation.get("candidate_pair"), dict) else {}
    intent = pair.get("pair_intent") if isinstance(pair.get("pair_intent"), dict) else {}
    return _drop_empty(
        {
            "pair_id": str(pair.get("pair_id") or ""),
            "score": pair.get("score"),
            "reason": _short_text(str(pair.get("reason") or ""), 220),
            "decision_edge_contract": str(pair.get("decision_edge_contract") or ""),
            "pair_intent": _drop_empty(
                {
                    "intent": str(intent.get("intent") or ""),
                    "allowed_relation_types": _string_list(intent.get("allowed_relation_types")),
                }
            ),
        }
    )


def _endpoint_claims_for_relation(
    source_claim_id: str,
    source_claim: dict[str, Any],
    target_claim_id: str,
    target_claim: dict[str, Any],
) -> list[dict[str, str]]:
    return [
        _endpoint_claim_summary("source", source_claim_id, source_claim),
        _endpoint_claim_summary("target", target_claim_id, target_claim),
    ]


def _endpoint_claim_summary(endpoint: str, claim_id: str, claim: dict[str, Any]) -> dict[str, Any]:
    source_bottom_lines = _source_bottom_lines_for_claim(claim)
    return _drop_empty(
        {
            "endpoint": endpoint,
            "claim_id": claim_id,
            "source_ids": _dedupe([str(claim.get("source_id") or ""), *_string_list(claim.get("supporting_sources"))]),
            "decision_edge_role": str(claim.get("decision_edge_role") or claim.get("map_relation_role") or ""),
            "decision_function": str(claim.get("decision_function") or ""),
            "question_relevance": str(claim.get("question_relevance") or ""),
            "claim": _short_text(str(claim.get("claim") or ""), 220),
            "source_bottom_lines": source_bottom_lines,
            "source_bottom_line_signals": _source_bottom_line_signals(source_bottom_lines),
        }
    )


def _relation_endpoint_answer_matrix(relation: dict[str, Any], endpoint_claims: list[dict[str, Any]]) -> dict[str, Any]:
    signals = _dedupe(
        [
            signal
            for endpoint in endpoint_claims
            for signal in _string_list(endpoint.get("source_bottom_line_signals"))
        ]
    )
    return _drop_empty(
        {
            "schema_id": "relation_endpoint_answer_matrix_v1",
            "relation_id": str(relation.get("relation_id") or ""),
            "relation_semantic_role": str(relation.get("relation_type") or ""),
            "endpoint_count": len(endpoint_claims),
            "endpoint_signal_summary": _endpoint_signal_summary(signals),
            "endpoints": [
                _drop_empty(
                    {
                        "endpoint": str(endpoint.get("endpoint") or ""),
                        "claim_id": str(endpoint.get("claim_id") or ""),
                        "source_ids": _string_list(endpoint.get("source_ids")),
                        "decision_edge_role": str(endpoint.get("decision_edge_role") or ""),
                        "source_bottom_line_signals": _string_list(endpoint.get("source_bottom_line_signals")),
                        "source_bottom_lines": _list(endpoint.get("source_bottom_lines"))[:2],
                    }
                )
                for endpoint in endpoint_claims
                if isinstance(endpoint, dict)
            ],
        }
    )


def _endpoint_signal_summary(signals: list[str]) -> str:
    signal_set = set(signals)
    if "increased_harm_or_risk_signal" in signal_set and (
        {"no_clear_association_signal", "reduced_harm_or_risk_signal", "benefit_signal"} & signal_set
    ):
        return "mixed_endpoint_polarity"
    if len(signal_set) > 1:
        return "multiple_endpoint_signals"
    return signals[0] if signals else ""


def _decision_edge_statement(relation: dict[str, Any], source_claim: dict[str, Any], target_claim: dict[str, Any]) -> str:
    relation_type = str(relation.get("relation_type") or "relates_to").replace("_", " ")
    rationale = str(relation.get("rationale") or "").strip()
    left = str(source_claim.get("claim") or relation.get("source_claim") or "").strip()
    right = str(target_claim.get("claim") or relation.get("target_claim") or "").strip()
    if rationale:
        return f"{relation_type}: {rationale}"
    return " ".join(part for part in (left, relation_type, right) if part)


def _decision_edge_excerpt(source_claim: dict[str, Any], target_claim: dict[str, Any]) -> str:
    left = str(source_claim.get("source_quote") or source_claim.get("excerpt") or "").strip()
    right = str(target_claim.get("source_quote") or target_claim.get("excerpt") or "").strip()
    return " | ".join(part for part in (_short_text(left, 280), _short_text(right, 280)) if part)


def _source_bottom_lines_for_claim(claim: dict[str, Any]) -> list[dict[str, str]]:
    source_id = str(claim.get("source_id") or "").strip()
    source_card = _dict(claim.get("whole_doc_source_card"))
    bottom_line = str(claim.get("source_bottom_line") or source_card.get("source_bottom_line") or "").strip()
    if not bottom_line:
        return []
    return [
        _drop_empty(
            {
                "source_id": source_id,
                "source_bottom_line": _short_text(bottom_line, 420),
                "polarity_signal": _source_bottom_line_signal(bottom_line),
            }
        )
    ]


def _bundle_source_bottom_lines(bundle: dict[str, Any]) -> list[dict[str, str]]:
    bottom_lines = []
    for row in _list(bundle.get("source_bottom_lines")):
        if isinstance(row, dict):
            line = str(row.get("source_bottom_line") or row.get("bottom_line") or row.get("claim") or "").strip()
            if line:
                bottom_lines.append(
                    _drop_empty(
                        {
                            "source_id": str(row.get("source_id") or ""),
                            "source_bottom_line": _short_text(line, 420),
                            "polarity_signal": _source_bottom_line_signal(line),
                        }
                    )
                )
        elif str(row).strip():
            line = str(row).strip()
            bottom_lines.append({"source_bottom_line": _short_text(line, 420), "polarity_signal": _source_bottom_line_signal(line)})
    line = str(bundle.get("source_bottom_line") or "").strip()
    if line:
        source_ids = _string_list(bundle.get("source_ids"))
        bottom_lines.append(
            _drop_empty(
                {
                    "source_id": source_ids[0] if source_ids else "",
                    "source_bottom_line": _short_text(line, 420),
                    "polarity_signal": _source_bottom_line_signal(line),
                }
            )
        )
    return _dedupe_source_bottom_lines(bottom_lines)


def _dedupe_source_bottom_lines(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    deduped = []
    for row in rows:
        source_id = str(row.get("source_id") or "")
        bottom_line = str(row.get("source_bottom_line") or "")
        key = (source_id, bottom_line)
        if not bottom_line or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped[:6]


def _source_bottom_line_signals(rows: list[dict[str, str]]) -> list[str]:
    return _dedupe([str(row.get("polarity_signal") or "") for row in rows if row.get("polarity_signal")])


def _source_bottom_line_signal(text: str) -> str:
    lowered = str(text or "").lower()
    harm_terms = r"(risk|harm|mortality|death|adverse|failure|loss|complication|cardiovascular|cvd|disease)"
    if "no significant association" in lowered or "not associated" in lowered or "no clear association" in lowered:
        return "no_clear_association_signal"
    if "associated with" in lowered and any(term in lowered for term in ("higher", "increased", "greater", "elevated", "worse")):
        return "increased_harm_or_risk_signal"
    if re.search(rf"\b(higher|increased|greater|elevated|worse|raises|worsens)\b.{0,80}\b{harm_terms}\b", lowered):
        return "increased_harm_or_risk_signal"
    if re.search(rf"\b(lower|reduced|decreased|less|improved|fewer)\b.{0,80}\b{harm_terms}\b", lowered):
        return "reduced_harm_or_risk_signal"
    if any(term in lowered for term in ("beneficial", "benefit", "improved outcome", "supports adoption", "supports the intervention")):
        return "benefit_signal"
    if any(term in lowered for term in ("mixed", "heterogeneous", "depends", "conditional", "uncertain")):
        return "mixed_or_conditional_signal"
    return ""


def _relation_current_role(relation_type: str) -> str:
    if relation_type in {"in_tension_with", "challenges"}:
        return "load_bearing_counterweight"
    if relation_type in {"depends_on", "refines"}:
        return "scope_or_applicability"
    if relation_type == "crux_for":
        return "decision_crux"
    if relation_type == "supports":
        return "load_bearing_primary_support"
    if relation_type == "contextualizes":
        return "mechanism_or_context"
    return "mechanism_or_context"


def _relation_priority(relation: dict[str, Any]) -> int:
    relation_type = str(relation.get("relation_type") or "")
    confidence = str(relation.get("relation_confidence") or "").lower()
    score = {
        "crux_for": 10,
        "in_tension_with": 9,
        "challenges": 9,
        "depends_on": 8,
        "refines": 7,
        "supports": 7,
        "contextualizes": 4,
        "similar_to": 3,
    }.get(relation_type, 5)
    if confidence == "high":
        score += 1
    elif confidence == "low":
        score -= 2
    return max(1, min(10, score))


def _relation_warning_codes(relation: dict[str, Any]) -> list[str]:
    warnings = []
    if str(relation.get("relation_confidence") or "").lower() == "low":
        warnings.append("low_confidence_relation")
    if relation.get("requires_review"):
        warnings.append("requires_relation_review")
    if not str(relation.get("rationale") or "").strip():
        warnings.append("missing_relation_rationale")
    return warnings


def _source_labels_from_scaffold(scaffold: dict[str, Any]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for key in ("source_titles", "source_display_names", "source_citation_labels"):
        value = scaffold.get(key)
        if isinstance(value, dict):
            labels.update({str(source_id): str(label) for source_id, label in value.items() if str(source_id).strip() and str(label).strip()})
    for source in _list(scaffold.get("source_trail")):
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id") or source.get("id") or "")
        label = str(source.get("source_label") or source.get("display_label") or source.get("title") or "")
        if source_id and label:
            labels[source_id] = label
    return labels


def _quantity_lookup(scaffold: dict[str, Any]) -> dict[str, list[str]]:
    lookup: dict[str, list[str]] = {}
    ledger = _dict(scaffold.get("quantity_ledger"))
    for row in _list(ledger.get("quantities")):
        if not isinstance(row, dict):
            continue
        claim_id = str(row.get("claim_id") or "").strip()
        quantity = str(row.get("quantity_text") or row.get("quantity") or "").strip()
        if claim_id and quantity:
            lookup.setdefault(claim_id, []).append(quantity)
    return {claim_id: _dedupe(values) for claim_id, values in lookup.items()}


def _claim_current_role(claim: dict[str, Any]) -> str:
    warnings = set(_claim_warning_codes(claim))
    if warnings & {"question_population_mismatch", "question_outcome_mismatch", "question_intervention_mismatch"}:
        decision_function = str(claim.get("decision_function") or "").strip()
        if decision_function in {"scope_boundary", "source_quality_caveat", "confounder_or_bias"}:
            return decision_function
        return "background"
    if "question_scope_mismatch" in warnings:
        return "scope_boundary"
    decision_function = str(claim.get("decision_function") or "").strip()
    if decision_function and decision_function != "unclassified_evidence":
        return decision_function
    for key in ("role", "relation_triage_bucket", "default_use", "decision_function"):
        value = str(claim.get(key) or "").strip()
        if value:
            return value
    return "map_claim"


def _priority_from_claim(claim: dict[str, Any]) -> int:
    if set(_claim_warning_codes(claim)) & {"question_population_mismatch", "question_outcome_mismatch", "question_intervention_mismatch"}:
        return 4
    level = str(claim.get("decision_importance_level") or claim.get("importance") or "").lower()
    if level == "critical":
        return 10
    if level == "high":
        return 9
    if level == "medium":
        return 7
    if level == "low":
        return 4
    default_use = str(claim.get("default_use") or "").lower()
    if default_use == "main_map":
        return 8
    if default_use == "supporting_map":
        return 6
    return 5


def _claim_warning_codes(claim: dict[str, Any]) -> list[str]:
    audit = _dict(claim.get("label_audit"))
    relevance = _dict(claim.get("deterministic_relevance_validation"))
    return _dedupe(
        [
            *_string_list(claim.get("validation_warnings")),
            *_string_list(audit.get("warnings")),
            str(relevance.get("reason") or ""),
        ]
    )


def _map_coverage_checks(candidate_map: dict[str, Any], warning_packet: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    claim_count = len([claim for claim in _list(candidate_map.get("claims")) if isinstance(claim, dict)])
    claim_row_count = sum(1 for row in rows if row.get("input_kind") == "retained_map_claim")
    warning_count = len([row for row in _list(warning_packet.get("warnings")) if isinstance(row, dict)])
    return {
        "retained_map_claim_count": claim_count,
        "retained_map_claim_rows": claim_row_count,
        "memo_warning_count": warning_count,
        "memo_warning_rows": sum(1 for row in rows if row.get("input_kind") == "memo_warning"),
        "warnings": _dedupe(
            [
                *(["claim_row_count_mismatch"] if claim_count != claim_row_count else []),
                *(["no_retained_map_claim_rows"] if claim_count and not claim_row_count else []),
            ]
        ),
    }


def _bundle_rows(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, bundle in enumerate(_list(packet.get("evidence_bundles"))):
        if not isinstance(bundle, dict):
            continue
        bundle_id = str(bundle.get("bundle_id") or f"bundle_{index + 1:03d}")
        source_bottom_lines = _bundle_source_bottom_lines(bundle)
        rows.append(
            _drop_empty(
                {
                    "evidence_item_id": f"bundle:{bundle_id}",
                    "input_kind": "retained_bundle",
                    "current_packet_location": "decision_briefing_packet.evidence_bundles",
                    "bundle_id": bundle_id,
                    "candidate_card_ids": _string_list(bundle.get("candidate_card_ids")),
                    "source_ids": _string_list(bundle.get("source_ids")),
                    "source_labels": _string_list(bundle.get("source_labels")),
                    "claim_ids": _string_list(bundle.get("claim_ids")),
                    "relation_ids": _string_list(bundle.get("relation_ids")),
                    "quantity_ids": _string_list(bundle.get("quantity_ids")),
                    "quantity_values": _string_list(bundle.get("quantity_values")),
                    "claim": _short_text(str(bundle.get("claim") or ""), 520),
                    "source_excerpt": _short_text(str(bundle.get("source_excerpt") or ""), 520),
                    "source_bottom_lines": source_bottom_lines,
                    "source_bottom_line_signals": _source_bottom_line_signals(source_bottom_lines),
                    "current_role": str(bundle.get("decision_role") or ""),
                    "current_priority": _priority_from_bundle(bundle),
                    "current_weight": bundle.get("weight"),
                    "quality": bundle.get("quality"),
                    "source_appraisal": bundle.get("source_appraisal"),
                    "source_use_warnings": _string_list(bundle.get("source_use_warnings")),
                    "allowed_wording": bundle.get("allowed_wording"),
                    "directionality": bundle.get("directionality"),
                    "why_it_matters": _short_text(str(bundle.get("why_it_matters") or ""), 260),
                    "existing_warning_codes": _bundle_warning_codes(bundle),
                }
            )
        )
    return rows


def _warning_rows(warning_packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, warning in enumerate(_list(warning_packet.get("warnings"))):
        if not isinstance(warning, dict):
            continue
        warning_id = str(warning.get("warning_id") or f"memo_warning_{index + 1:03d}")
        rows.append(
            _drop_empty(
                {
                    "evidence_item_id": f"warning:{warning_id}",
                    "input_kind": "memo_warning",
                    "current_packet_location": "memo_warning_packet.warnings",
                    "warning_id": warning_id,
                    "source_ids": _string_list(warning.get("source_ids")),
                    "source_labels": _string_list(warning.get("source_labels")),
                    "quantity_values": _string_list(warning.get("quantity_values")),
                    "claim": _short_text(str(warning.get("claim") or ""), 520),
                    "current_role": str(warning.get("decision_role") or ""),
                    "current_priority": _priority_from_warning(warning),
                    "existing_warning_codes": [str(warning.get("warning_type") or "memo_warning")],
                    "warning_severity": warning.get("severity"),
                    "expected_memo_action": warning.get("expected_memo_action"),
                }
            )
        )
    return rows


def _review_context_omission_rows(packet: dict[str, Any]) -> list[dict[str, Any]]:
    coverage = _dict(packet.get("coverage_report"))
    rows = []
    for index, row in enumerate(_list(coverage.get("truly_lost_review_context"))):
        if not isinstance(row, dict):
            continue
        candidate_id = str(row.get("candidate_card_id") or f"review_context_{index + 1:03d}")
        rows.append(
            _drop_empty(
                {
                    "evidence_item_id": f"omission:{candidate_id}",
                    "input_kind": "review_worthy_omission",
                    "current_packet_location": "coverage_report.truly_lost_review_context",
                    "candidate_card_id": candidate_id,
                    "source_ids": _string_list(row.get("source_ids")),
                    "quantity_values": _string_list(row.get("quantity_values")),
                    "claim": _short_text(str(row.get("claim") or ""), 520),
                    "current_role": str(row.get("decision_role") or ""),
                    "current_priority": int(row.get("priority", 7) or 7),
                    "existing_warning_codes": ["review_worthy_omitted_after_trimming"],
                    "warning_severity": row.get("omission_severity"),
                    "downgrade_candidate": True,
                }
            )
        )
    return rows


def _top_quantity_rows(packet: dict[str, Any]) -> list[dict[str, Any]]:
    graph = _dict(packet.get("source_evidence_graph"))
    rows = []
    for node in _list(graph.get("nodes")):
        if not isinstance(node, dict) or node.get("node_type") != "quantity" or not node.get("top_anchor"):
            continue
        node_id = str(node.get("node_id") or node.get("id") or "")
        quantity = str(node.get("quantity") or "").strip()
        if not node_id and not quantity:
            continue
        rows.append(
            _drop_empty(
                {
                    "evidence_item_id": f"quantity:{node_id or quantity}",
                    "input_kind": "top_quantity_anchor",
                    "current_packet_location": "source_evidence_graph.nodes",
                    "source_ids": _string_list(node.get("source_ids")),
                    "source_labels": _string_list(node.get("source_labels")),
                    "claim_ids": _string_list(node.get("claim_ids")),
                    "quantity_values": _string_list(quantity),
                    "quantity_type": node.get("quantity_type"),
                    "claim": _short_text(str(node.get("claim") or quantity), 520),
                    "current_role": "quantitative_anchor",
                    "current_priority": int(node.get("relevance_score", 8) or 8),
                    "existing_warning_codes": ["top_quantity_anchor"],
                }
            )
        )
    return rows


def _coverage_checks(packet: dict[str, Any], warning_packet: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    row_locations = {str(row.get("current_packet_location")) for row in rows}
    bundle_count = len([row for row in _list(packet.get("evidence_bundles")) if isinstance(row, dict)])
    warning_count = len([row for row in _list(warning_packet.get("warnings")) if isinstance(row, dict)])
    top_quantity_count = len([row for row in rows if row.get("input_kind") == "top_quantity_anchor"])
    return {
        "retained_bundle_count": bundle_count,
        "retained_bundle_rows": sum(1 for row in rows if row.get("input_kind") == "retained_bundle"),
        "memo_warning_count": warning_count,
        "memo_warning_rows": sum(1 for row in rows if row.get("input_kind") == "memo_warning"),
        "top_quantity_anchor_rows": top_quantity_count,
        "locations_present": sorted(row_locations),
        "warnings": _dedupe(
            [
                *(["bundle_row_count_mismatch"] if bundle_count != sum(1 for row in rows if row.get("input_kind") == "retained_bundle") else []),
                *(["memo_warning_row_count_mismatch"] if warning_count != sum(1 for row in rows if row.get("input_kind") == "memo_warning") else []),
                *(["no_retained_bundle_rows"] if bundle_count and not any(row.get("input_kind") == "retained_bundle" for row in rows) else []),
            ]
        ),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "input_kind_counts": _counts(str(row.get("input_kind") or "unknown") for row in rows),
        "role_counts": _counts(str(row.get("current_role") or "unknown") for row in rows),
        "warning_row_count": sum(1 for row in rows if row.get("existing_warning_codes")),
        "quantity_row_count": sum(1 for row in rows if row.get("quantity_values")),
        "source_grounded_row_count": sum(1 for row in rows if row.get("source_ids") or row.get("source_labels")),
        "high_priority_row_count": sum(1 for row in rows if int(row.get("current_priority", 0) or 0) >= 8),
    }


def _priority_from_bundle(bundle: dict[str, Any]) -> int:
    weight = str(bundle.get("weight") or "").lower()
    if weight == "critical":
        return 10
    if weight == "high":
        return 9
    if weight == "medium":
        return 7
    if weight == "low":
        return 4
    try:
        return int(bundle.get("decision_relevance_score", 6) or 6)
    except (TypeError, ValueError):
        return 6


def _priority_from_warning(warning: dict[str, Any]) -> int:
    severity = str(warning.get("severity") or "").lower()
    if severity == "critical":
        return 10
    if severity == "moderate":
        return 8
    return 7


def _bundle_warning_codes(bundle: dict[str, Any]) -> list[str]:
    return _dedupe(
        [
            *_string_list(bundle.get("warning_codes")),
            *_string_list(bundle.get("warnings")),
            *_string_list(_dict(bundle.get("decision_relevance_assessment")).get("warnings")),
        ]
    )


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for row in rows:
        row_id = str(row.get("evidence_item_id") or "").strip()
        if not row_id or row_id in seen:
            continue
        seen.add(row_id)
        result.append(row)
    return result


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _stable_final_answer_frame(packet: dict[str, Any], *, question: str) -> dict[str, Any]:
    answer_frame = _dict(packet.get("answer_frame"))
    answer_spine = _dict(packet.get("answer_spine"))
    candidate_answer_set = _dict(packet.get("candidate_answer_set"))
    live_options = _live_answer_options(candidate_answer_set)
    direct_answer = str(
        answer_frame.get("default_answer")
        or answer_frame.get("direct_answer")
        or answer_spine.get("default_read")
        or answer_spine.get("bounded_answer")
        or ""
    ).strip()
    selected_answer_option_id = str(
        answer_frame.get("selected_answer_option_id")
        or answer_frame.get("candidate_answer_id")
        or answer_spine.get("selected_answer_option_id")
        or answer_spine.get("candidate_answer_id")
        or ""
    ).strip()
    answer_status = _answer_status(
        answer_frame=answer_frame,
        answer_spine=answer_spine,
        current_best_answer=direct_answer,
        selected_answer_option_id=selected_answer_option_id,
        live_answer_options=live_options,
    )
    frame = _drop_empty(
        {
            "schema_id": "stable_final_answer_frame_v1",
            "decision_question": str(question or packet.get("decision_question") or "").strip(),
            "answer_status": answer_status,
            "current_best_answer": _short_text(direct_answer, 700),
            "selected_answer_option_id": selected_answer_option_id,
            "classification": str(answer_frame.get("classification") or "").strip(),
            "confidence": str(answer_frame.get("confidence") or packet.get("confidence") or "").strip(),
            "live_answer_options": live_options,
            "candidate_answer_options": live_options,
            "conditions_or_scope_clauses": _conditions_or_scope_clauses(answer_frame, answer_spine),
            "classification_target_policy": _classification_target_policy(answer_status, current_best_answer=direct_answer),
            "classification_rule": _classification_rule(answer_status, current_best_answer=direct_answer),
        }
    )
    return frame


def _live_answer_options(candidate_answer_set: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _drop_empty(
            {
                "candidate_answer_id": row.get("candidate_answer_id") or row.get("answer_id"),
                "answer": _short_text(str(row.get("answer") or row.get("label") or row.get("claim") or ""), 220),
                "stance": str(row.get("stance") or "").strip(),
                "status": str(row.get("status") or "").strip(),
                "basis": str(row.get("basis") or "").strip(),
            }
        )
        for row in _list(candidate_answer_set.get("candidate_answers"))
        if isinstance(row, dict)
    ][:8]


def _answer_status(
    *,
    answer_frame: dict[str, Any],
    answer_spine: dict[str, Any],
    current_best_answer: str,
    selected_answer_option_id: str,
    live_answer_options: list[dict[str, Any]],
) -> str:
    explicit = str(answer_frame.get("answer_status") or answer_spine.get("answer_status") or "").strip().lower()
    if explicit in {"selected", "provisional", "unresolved", "multi_option"}:
        return explicit
    if selected_answer_option_id:
        return "selected"
    if current_best_answer:
        return "provisional"
    if len(live_answer_options) > 1:
        return "multi_option"
    return "unresolved"


def _conditions_or_scope_clauses(answer_frame: dict[str, Any], answer_spine: dict[str, Any]) -> list[str]:
    return _dedupe(
        [
            *_string_list(answer_frame.get("conditions_or_scope_clauses")),
            *_string_list(answer_frame.get("scope")),
            *_string_list(answer_frame.get("main_uncertainty")),
            *_string_list(answer_spine.get("conditions_or_scope_clauses")),
            *_string_list(answer_spine.get("scope_boundaries")),
        ]
    )[:8]


def _classification_target_policy(answer_status: str, *, current_best_answer: str) -> str:
    if answer_status == "selected":
        return "Classify relative to selected_answer_option_id and current_best_answer; use target_answer_option for the named option affected."
    if answer_status == "provisional" and current_best_answer:
        return "Classify relative to the provisional current_best_answer, while preserving which live answer option or condition the evidence bears on."
    if answer_status == "multi_option":
        return "No single answer is selected; classify evidence by the live answer option, condition, or crux it bears on instead of forcing support or challenge to a final answer."
    return "No stable answer is selected; use uncertain_relation or contextualizes_answer unless evidence clearly bears on a named live option, condition, or crux."


def _classification_rule(answer_status: str, *, current_best_answer: str) -> str:
    if answer_status in {"selected", "provisional"} and current_best_answer:
        return (
            "Classify relative to current_best_answer. challenges_answer means the row weakens, overturns, "
            "or materially lowers confidence in current_best_answer; evidence that argues against a rejected or feared "
            "alternative usually supports or contextualizes current_best_answer instead."
        )
    return (
        "Because no final answer is selected, classify evidence by the live option, condition, or crux it affects. "
        "Use target_answer_option to name that target; challenges_answer means weakening that named target."
    )


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}
