from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_analytical_balance_contract import build_analytical_balance_contract
from epistemic_case_mapper.map_briefing_argument_spine import build_evidence_weighted_argument_spine
from epistemic_case_mapper.map_briefing_balanced_answer_frame import build_balanced_answer_frame, build_bluf_contract
from epistemic_case_mapper.map_briefing_canonical_reconciliation import reconcile_packet_evidence_items, reconcile_writer_interface
from epistemic_case_mapper.map_briefing_canonical_quality_report import build_canonical_decision_writer_packet_quality_report
from epistemic_case_mapper.map_briefing_claim_calibration import calibrate_claim_for_writer, calibrate_text_for_writer
from epistemic_case_mapper.map_briefing_decision_argument_contract import build_decision_argument_contract
from epistemic_case_mapper.map_briefing_evidence_language_contracts import build_evidence_language_contracts
from epistemic_case_mapper.map_briefing_memo_obligations import required_memo_obligations
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    norm as _norm,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_reader_evidence_roles import reader_evidence_role, source_weight_lane
from epistemic_case_mapper.map_briefing_reader_judgment_packet import build_reader_judgment_packet
from epistemic_case_mapper.map_briefing_source_identity import (
    project_sources_to_ids_for_model,
    source_id_registry_for_model,
)
from epistemic_case_mapper.map_briefing_source_hierarchy_projection import (
    source_hierarchy_lane_index,
    source_hierarchy_match_for_row,
)
from epistemic_case_mapper.map_briefing_source_weight_judgments import (
    build_source_weight_judgment_bundle,
    build_source_weight_judgment_report,
)
from epistemic_case_mapper.map_briefing_source_weighting_contract import (
    build_source_weighting_contract,
    build_source_weighting_flow_audit,
)
from epistemic_case_mapper.map_briefing_reader_language import project_reader_language_for_model
from epistemic_case_mapper.map_briefing_writer_decision_interface import build_writer_decision_interface

def build_canonical_decision_writer_packet(
    memo_ready_packet: dict[str, Any],
    *,
    writer_interface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile existing analyst judgments into the single synthesis handoff."""

    packet = memo_ready_packet if isinstance(memo_ready_packet, dict) else {}
    interface = (
        writer_interface
        if isinstance(writer_interface, dict) and writer_interface.get("schema_id") == "writer_decision_interface_v1"
        else build_writer_decision_interface(packet)
    )
    source_trail = _list(packet.get("source_trail"))
    source_weight_bundle = _source_weight_bundle(packet, interface, source_trail)
    skeleton = _decision_brief_skeleton(interface)
    weighted_frame = _source_weighted_answer_frame(packet, interface)
    counterweights = _counterweight_dispositions(interface)
    scope_boundaries = _scope_boundaries(interface)
    analyst_frame = _analyst_reasoning_frame(packet, interface)
    inventory = _organized_evidence_inventory(packet, interface)
    initial_balanced_frame = build_balanced_answer_frame(
        skeleton=skeleton,
        analyst_reasoning_frame=analyst_frame,
        source_weighted_answer_frame=weighted_frame,
        organized_evidence_inventory=inventory,
        counterweight_dispositions=counterweights,
        scope_boundaries=scope_boundaries,
    )
    interface = reconcile_writer_interface(interface, packet, initial_balanced_frame)
    packet = reconcile_packet_evidence_items(packet, interface)
    skeleton = _decision_brief_skeleton(interface)
    analyst_frame = _analyst_reasoning_frame(packet, interface)
    source_weight_bundle = _source_weight_bundle(packet, interface, source_trail)
    weighted_frame = _source_weighted_answer_frame(packet, interface)
    counterweights = _counterweight_dispositions(interface)
    scope_boundaries = _scope_boundaries(interface)
    priority = _priority_evidence(interface)
    inventory = _organized_evidence_inventory(packet, interface)
    mandatory_checklist = _mandatory_retention_checklist(packet, interface)
    language_contracts = build_evidence_language_contracts(packet, interface)
    balanced_frame = build_balanced_answer_frame(
        skeleton=skeleton,
        analyst_reasoning_frame=analyst_frame,
        source_weighted_answer_frame=weighted_frame,
        organized_evidence_inventory=inventory,
        counterweight_dispositions=counterweights,
        scope_boundaries=scope_boundaries,
    )
    argument_spine = build_evidence_weighted_argument_spine(
        skeleton=skeleton,
        decision_question=packet.get("decision_question"),
        source_weighted_frame=weighted_frame,
        counterweights=counterweights,
        scope_boundaries=scope_boundaries,
        source_weight_judgments=source_weight_bundle["source_weight_judgments"],
        mandatory_retention_checklist=mandatory_checklist,
    )
    canonical = {
        "schema_id": "canonical_decision_writer_packet_v1",
        "decision_question": packet.get("decision_question"),
        "decision_brief_skeleton": skeleton,
        "decision_answer_classification": _decision_answer_classification(packet),
        "analyst_decision_spine": _dict(interface.get("analyst_decision_spine")),
        "analyst_reasoning_frame": analyst_frame,
        "balanced_answer_frame": balanced_frame,
        "bluf_contract": build_bluf_contract(skeleton=skeleton, balanced_answer_frame=balanced_frame),
        "source_weighted_answer_frame": weighted_frame,
        "evidence_weighted_argument_spine": argument_spine,
        "priority_evidence": priority,
        "organized_evidence_inventory": inventory,
        "counterweight_dispositions": counterweights,
        "scope_boundaries": scope_boundaries,
        "decision_cruxes": _decision_cruxes(interface),
        "source_weight_judgments": source_weight_bundle["source_weight_judgments"],
        "source_weight_judgment_report": source_weight_bundle["source_weight_judgment_report"],
        "source_hierarchy": _dict(packet.get("analyst_source_hierarchy")),
        "source_hierarchy_report": _dict(packet.get("analyst_source_hierarchy_report")),
        "source_weight_notes": _source_weight_notes(interface),
        "evidence_language_contracts": language_contracts,
        "mandatory_retention_checklist": mandatory_checklist,
        "memo_obligation_contract": _memo_obligation_contract(packet, mandatory_checklist),
        "citation_registry": _citation_registry(source_trail),
    }
    canonical["reader_judgment_packet"] = build_reader_judgment_packet(canonical)
    canonical = project_reader_language_for_model(project_sources_to_ids_for_model(canonical, source_trail))
    canonical["decision_argument_contract"] = build_decision_argument_contract(canonical)
    canonical["decision_argument_contract_report"] = _dict(canonical["decision_argument_contract"].get("report"))
    canonical["source_weighting_contract"] = build_source_weighting_contract(canonical)
    canonical["source_weighting_flow_audit"] = build_source_weighting_flow_audit(canonical)
    canonical["quality_report"] = build_canonical_decision_writer_packet_quality_report(canonical)
    return canonical


def _source_weight_bundle(packet: dict[str, Any], interface: dict[str, Any], source_trail: list[Any]) -> dict[str, Any]:
    analyst_judgments = [row for row in _list(packet.get("analyst_source_weight_judgments")) if isinstance(row, dict)]
    if analyst_judgments:
        return {
            "source_weight_judgments": analyst_judgments,
            "source_weight_judgment_report": build_source_weight_judgment_report(analyst_judgments, source_trail),
        }
    bundle = build_source_weight_judgment_bundle(interface, source_trail)
    report = dict(bundle.get("source_weight_judgment_report", {}))
    warnings = _dedupe(
        [
            *_string_list(report.get("warnings")),
            "analyst_source_weight_judgments_missing_projected_from_writer_roles",
        ]
    )
    report.update(
        {
            "status": "warning",
            "warnings": warnings,
            "fallback_used": True,
            "fallback_reason": "analyst_source_weight_judgments_missing",
        }
    )
    return {**bundle, "source_weight_judgment_report": report}


def _decision_brief_skeleton(interface: dict[str, Any]) -> dict[str, Any]:
    answer_frame = _dict(interface.get("answer_frame"))
    practical_cards = _list(interface.get("practical_implication_cards"))
    counterweights = _counterweight_dispositions(interface)
    scope = _scope_boundaries(interface)
    cruxes = _decision_cruxes(interface)
    most_important_quantity = _most_important_quantity(interface)
    return _drop_empty(
        {
            "direct_answer": _calibrated_short(answer_frame.get("direct_answer") or interface.get("bottom_line"), limit=520),
            "primary_answer": _calibrated_short(answer_frame.get("primary_answer"), limit=520),
            "secondary_detail": _calibrated_short(answer_frame.get("secondary_detail"), limit=420),
            "secondary_detail_type": answer_frame.get("secondary_detail_type"),
            "full_direct_answer": _calibrated_short(answer_frame.get("full_direct_answer"), limit=700),
            "scope": _calibrated_short(answer_frame.get("scope_note") or answer_frame.get("scoping_policy"), limit=520),
            "confidence": answer_frame.get("confidence") or interface.get("confidence"),
            "confidence_basis": _calibrated_short(answer_frame.get("confidence_basis"), limit=520),
            "main_reason": _calibrated_short(answer_frame.get("main_support"), limit=520),
            "most_important_quantity": most_important_quantity,
            "strongest_counterweight": _calibrated_short(answer_frame.get("main_counterweight"), limit=520),
            "counterweight_disposition": counterweights[0].get("disposition") if counterweights else "",
            "exceptions": [_calibrated_short(row.get("statement") or row.get("claim"), row, limit=300) for row in scope[:4] if isinstance(row, dict)],
            "decision_crux": _calibrated_short(_first_text(cruxes, keys=("statement", "claim")), limit=420),
            "practical_implication": _calibrated_short(_first_text(practical_cards, keys=("statement",)), limit=520),
        }
    )


def _decision_answer_classification(packet: dict[str, Any]) -> dict[str, Any]:
    contract = build_analytical_balance_contract(packet)
    classification = _dict(contract.get("answer_classification"))
    return _drop_empty(
        {
            "decision_question": classification.get("decision_question") or packet.get("decision_question"),
            "current_answer_state": _short_text(classification.get("current_answer_state"), 900),
            "question_options": _string_list(classification.get("question_options")),
            "answer_shape": classification.get("answer_shape"),
            "writing_job": _short_text(classification.get("writing_job"), 520),
        }
    )


def _priority_evidence(interface: dict[str, Any]) -> list[dict[str, Any]]:
    roles = {"strongest_support", "quantitative_anchor", "strongest_counterweight", "scope_boundary", "decision_crux"}
    rows = [_evidence_row(row) for row in _list(interface.get("decision_evidence_table")) if isinstance(row, dict) and row.get("role") in roles]
    return _dedupe_rows(rows, "item_id")[:18]


def _source_weighted_answer_frame(packet: dict[str, Any], interface: dict[str, Any]) -> dict[str, Any]:
    hierarchy_index = source_hierarchy_lane_index(_dict(packet.get("analyst_source_hierarchy")))
    source_identity_trail = _list(interface.get("_source_identity_trail")) or _list(packet.get("source_trail")) or _list(interface.get("source_trail"))
    rows = [
        row
        for row in sorted(
            _list(interface.get("decision_evidence_table")),
            key=lambda item: (_inventory_sort_rank(item) if isinstance(item, dict) else 100, str(_dict(item).get("item_id") or "")),
        )
        if isinstance(row, dict)
    ]
    lanes: dict[str, list[dict[str, Any]]] = {}
    for raw_row in rows:
        row = project_sources_to_ids_for_model(raw_row, source_identity_trail) if source_identity_trail else raw_row
        hierarchy_match = source_hierarchy_match_for_row(row, hierarchy_index)
        lane = str(hierarchy_match.get("canonical_lane") or "") or source_weight_lane(row)
        lanes.setdefault(lane, []).append(_source_weighted_evidence_row(row, lane=lane, hierarchy_match=hierarchy_match))

    capped_lanes = {
        lane: _dedupe_rows(lane_rows, "item_id")[: _source_weight_lane_cap(lane)]
        for lane, lane_rows in lanes.items()
        if lane_rows
    }
    return _drop_empty(
        {
            "schema_id": "source_weighted_answer_frame_v1",
            "weighting_thesis": (
                "Use primary answer drivers for the main answer; use calibrators, counterweights, cruxes, and scope limiters "
                "to explain confidence and boundaries; use context-only material for framing rather than independent confirmation."
            ),
            "required_weighting_moves": [
                "Explain what class of evidence carries the main answer before discussing limiting evidence.",
                "Use quantitative or interpretive calibrators to explain magnitude, mechanism, or plausibility without replacing outcome evidence.",
                "Use counterweights and cruxes to state what would weaken, overturn, or require narrower wording for the answer.",
                "Use scope limiters to define where the answer stops applying.",
                "Use context-only sources only for application or interpretation unless upstream analysis gives them a stronger role.",
            ],
            "lanes": capped_lanes,
        }
    )


def _source_weighted_evidence_row(
    row: dict[str, Any],
    *,
    lane: str,
    hierarchy_match: dict[str, Any] | None = None,
) -> dict[str, Any]:
    calibrated = _calibrated_claim_row(row)
    reader_role = reader_evidence_role(row)
    hierarchy_match = hierarchy_match if isinstance(hierarchy_match, dict) else {}
    return _drop_empty(
        {
            "item_id": row.get("item_id"),
            "source_weight_role": lane,
            "source_weight_basis": "analyst_source_hierarchy" if hierarchy_match else "writer_role_projection",
            "reader_evidence_role": reader_role,
            "upstream_role": row.get("role"),
            "answer_relation": row.get("answer_relation"),
            "memo_function": row.get("memo_function"),
            "claim": _short_text(calibrated.get("claim"), 620),
            "source_ids": _string_list(row.get("source_ids")),
            "source_labels": _string_list(row.get("source_labels")),
            "quantities": _brief_quantities(row),
            "key_source_facts": _key_source_facts(row),
            "why_this_weight": _source_weight_reason(row, lane, hierarchy_match=hierarchy_match),
            "decision_relevance": _calibrated_short(row.get("decision_relevance") or row.get("include_reason"), row, limit=520),
            "source_appraisal_note": _short_text(row.get("source_appraisal_note") or _source_appraisal_note(row), 360),
            "not_enough_for": _string_list(row.get("source_use_warnings") or _dict(row.get("source_appraisal")).get("source_use_warnings"))[:4],
            "importance_rank": row.get("importance_rank"),
        }
    )


def _source_weight_lane_cap(lane: str) -> int:
    caps = {
        "primary_answer_drivers": 8,
        "quantitative_or_interpretive_calibrators": 8,
        "counterweights_or_tensions": 8,
        "scope_limiters": 8,
        "decision_cruxes": 6,
        "context_only": 6,
        "excluded_from_answer": 4,
    }
    return caps.get(lane, 6)


def _source_weight_reason(row: dict[str, Any], lane: str, *, hierarchy_match: dict[str, Any] | None = None) -> str:
    hierarchy_match = hierarchy_match if isinstance(hierarchy_match, dict) else {}
    if hierarchy_match:
        parts = [f"Positioned as {lane.replace('_', ' ')} because the analyst source hierarchy assigns this evidence to {str(hierarchy_match.get('hierarchy_lane') or '').replace('_', ' ')}"]
        if hierarchy_match.get("rationale"):
            parts.append(str(hierarchy_match.get("rationale")))
        return _short_text("; ".join(parts) + ".", 420)
    role = str(row.get("role") or "").strip() or "unspecified"
    relation = str(row.get("answer_relation") or "").strip()
    function = str(row.get("memo_function") or "").strip()
    appraisal = _dict(row.get("source_appraisal"))
    directness = str(appraisal.get("decision_directness") or "").strip()
    parts = [f"Positioned as {lane.replace('_', ' ')} because upstream role is {role}"]
    if relation:
        parts.append(f"answer relation is {relation}")
    if function:
        parts.append(f"memo function is {function}")
    if directness and directness != "unknown":
        parts.append(f"source directness is {directness}")
    return _short_text("; ".join(parts) + ".", 420)


def _analyst_reasoning_frame(packet: dict[str, Any], interface: dict[str, Any]) -> dict[str, Any]:
    spine = _dict(packet.get("answer_spine"))
    logic = _dict(packet.get("analyst_decision_logic"))
    excluded_claims = _excluded_inventory_claims(packet)
    return _drop_empty(
        {
            "bottom_line": _calibrated_short(_strip_excluded_claims(interface.get("bottom_line") or spine.get("default_read"), excluded_claims), limit=900),
            "why_this_answer": _calibrated_short(_strip_excluded_claims(spine.get("why_this_read"), excluded_claims), limit=1200),
            "confidence": spine.get("confidence") or interface.get("confidence"),
            "confidence_reasons": [
                _calibrated_short(cleaned, limit=700)
                for row in _string_list(spine.get("confidence_reasons"))
                if (cleaned := _strip_excluded_claims(row, excluded_claims))
            ],
            "support_summary": _calibrated_short(_strip_excluded_claims(logic.get("support_summary"), excluded_claims), limit=700),
            "counterweight_weighting": _calibrated_short(_strip_excluded_claims(logic.get("counterweight_weighting"), excluded_claims), limit=700),
            "scope_boundaries": [
                _calibrated_short(cleaned, limit=420)
                for row in _string_list(logic.get("scope_boundaries"))
                if (cleaned := _strip_excluded_claims(row, excluded_claims))
            ],
            "reconciled_cruxes": [
                _calibrated_short(cleaned, limit=520)
                for row in _string_list(logic.get("reconciled_cruxes"))
                if (cleaned := _strip_excluded_claims(row, excluded_claims))
            ],
            "practical_implications": [
                _calibrated_short(cleaned, limit=520)
                for row in _string_list(logic.get("practical_implications"))
                if (cleaned := _strip_excluded_claims(row, excluded_claims))
            ],
            "do_not_overstate": [
                _calibrated_short(cleaned, limit=420)
                for row in _string_list(logic.get("do_not_overstate"))
                if (cleaned := _strip_excluded_claims(row, excluded_claims))
            ],
            "argument_steps": _argument_steps(packet),
            "reasoning_hierarchy": _dict(interface.get("reasoning_hierarchy")),
            "use_policy": [
                "Use priority_evidence for attention and ordering.",
                "Use organized_evidence_inventory as the complete memo-facing evidence record.",
                "Use analyst_reasoning_frame to preserve how upstream analysis says evidence should change the answer.",
            ],
        }
    )


def _argument_steps(packet: dict[str, Any]) -> list[dict[str, Any]]:
    steps = []
    for index, row in enumerate(_list(packet.get("analyst_argument_plan") or _dict(packet.get("writer_packet")).get("argument_plan")), start=1):
        if not isinstance(row, dict):
            continue
        steps.append(
            _drop_empty(
                {
                    "step_id": row.get("step_id") or f"step_{index:03d}",
                    "writing_goal": _calibrated_short(row.get("writing_goal"), limit=360),
                    "required_points": [_calibrated_short(point, limit=520) for point in _string_list(row.get("required_points"))],
                    "evidence_item_ids": _string_list(row.get("evidence_item_ids")),
                    "transition": _calibrated_short(row.get("transition_from_previous"), limit=260),
                }
            )
        )
    return steps[:12]


def _organized_evidence_inventory(packet: dict[str, Any], interface: dict[str, Any]) -> dict[str, Any]:
    items = [_inventory_row(row) for row in _list(packet.get("evidence_items")) if isinstance(row, dict) and _is_memo_facing_inventory_item(row)]
    if not items:
        items = [_inventory_row(row) for row in _list(interface.get("decision_evidence_table")) if isinstance(row, dict)]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in sorted(items, key=lambda item: (_inventory_sort_rank(item), str(item.get("item_id") or ""))):
        lane = _inventory_lane(row)
        grouped.setdefault(lane, []).append(row)
    return {
        "schema_id": "organized_evidence_inventory_v1",
        "organization_policy": [
            "This is the complete memo-facing evidence inventory, organized for synthesis rather than filtered for brevity.",
            "Explicitly optional or off-question material is excluded from synthesis context even when retained elsewhere for audit.",
            "Priority evidence should receive attention first, but non-priority inventory items may supply practical framing, comparators, scope, or interpretive context.",
            "Items with role context_only should remain contextual unless they clarify how to apply or interpret the answer.",
        ],
        "item_count": len(items),
        "lanes": grouped,
    }


def _inventory_row(row: dict[str, Any]) -> dict[str, Any]:
    calibrated = _calibrated_claim_row(row)
    reader_role = reader_evidence_role(row)
    return _drop_empty(
        {
            "item_id": row.get("item_id"),
            "role": row.get("role"),
            "reader_evidence_role": reader_role,
            "answer_relation": row.get("answer_relation"),
            "memo_function": row.get("memo_function"),
            "obligation_level": row.get("obligation_level"),
            "claim": _short_text(calibrated.get("claim"), 760),
            "original_claim": _short_text(row.get("original_claim") or calibrated.get("original_claim"), 760),
            "claim_calibration_notes": _dedupe([*_string_list(row.get("claim_calibration_notes")), *_string_list(calibrated.get("calibration_notes"))]),
            "not_allowed_terms": _dedupe([*_string_list(row.get("not_allowed_terms")), *_string_list(calibrated.get("not_allowed_terms"))]),
            "source_labels": _string_list(row.get("source_labels")) or _string_list(row.get("source_label")),
            "source_ids": _string_list(row.get("source_ids")),
            "quantities": _brief_quantities(row),
            "key_source_facts": _key_source_facts(row),
            "decision_relevance": _calibrated_short(row.get("decision_relevance") or row.get("include_reason"), row, limit=760),
            "caveat": _calibrated_short(row.get("caveat"), row, limit=420),
            "source_appraisal_note": _short_text(row.get("source_appraisal_note") or _source_appraisal_note(row), 420),
            "source_excerpts": _source_excerpt_rows(row),
            "importance_rank": row.get("importance_rank"),
            "source_memo_role": row.get("source_memo_role"),
        }
    )


def _is_memo_facing_inventory_item(row: dict[str, Any]) -> bool:
    obligation = str(row.get("obligation_level") or "").strip().lower()
    role = str(row.get("role") or "").strip().lower()
    relation = str(row.get("answer_relation") or "").strip().lower()
    if obligation in {"optional_context", "off_question", "not_relevant"}:
        return False
    if role in {"off_question", "excluded"}:
        return False
    if relation in {"off_question", "not_relevant"}:
        return False
    return True


def _excluded_inventory_claims(packet: dict[str, Any]) -> list[str]:
    return _dedupe(
        str(row.get("reader_claim") or row.get("claim") or "").strip()
        for row in _list(packet.get("evidence_items"))
        if isinstance(row, dict) and not _is_memo_facing_inventory_item(row)
    )


def _strip_excluded_claims(value: Any, excluded_claims: list[str]) -> str:
    text = str(value or "").strip()
    if not text or not excluded_claims:
        return text
    for claim in excluded_claims:
        if claim:
            text = text.replace(claim, "").strip()
    return " ".join(text.split())


def _source_excerpt_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
    excerpts = []
    for excerpt in _list(row.get("source_excerpts")):
        if not isinstance(excerpt, dict):
            continue
        text = str(excerpt.get("source_excerpt") or excerpt.get("excerpt") or "").strip()
        if not text:
            continue
        excerpts.append(
            _drop_empty(
                {
                    "source_ids": _string_list(excerpt.get("source_ids")) or _string_list(row.get("source_ids")),
                    "source_labels": _string_list(excerpt.get("source_labels")) or _string_list(row.get("source_labels")),
                    "excerpt": _short_text(text, 900),
                }
            )
        )
    return excerpts[:3]


def _key_source_facts(row: dict[str, Any]) -> list[dict[str, Any]]:
    facts = []
    for fact in _list(row.get("key_source_facts"))[:10]:
        if not isinstance(fact, dict):
            continue
        facts.append(
            _drop_empty(
                {
                    "fact_type": fact.get("fact_type"),
                    "text": _short_text(fact.get("text"), 420),
                    "source_ids": _string_list(fact.get("source_ids")) or _string_list(row.get("source_ids")),
                    "quantity_values": _string_list(fact.get("quantity_values"))[:6],
                    "decision_use": _short_text(fact.get("decision_use"), 280),
                    "evidence_item_ids": _string_list(fact.get("evidence_item_ids"))[:8],
                }
            )
        )
    return facts


def _source_appraisal_note(row: dict[str, Any]) -> str:
    appraisal = _dict(row.get("source_appraisal"))
    parts = []
    directness = str(appraisal.get("decision_directness") or "").strip()
    if directness and directness != "unknown":
        parts.append(f"directness: {directness}")
    recommended = ", ".join(_string_list(appraisal.get("recommended_uses"))[:3])
    if recommended:
        parts.append(f"use: {recommended}")
    warnings = ", ".join(_string_list(row.get("source_use_warnings") or appraisal.get("source_use_warnings"))[:3])
    if warnings:
        parts.append(f"caveats: {warnings}")
    wording = _dict(row.get("allowed_wording") or appraisal.get("allowed_wording"))
    qualifiers = ", ".join(_string_list(wording.get("must_qualify_with"))[:3])
    if qualifiers:
        parts.append(f"wording: {qualifiers}")
    return _short_text("; ".join(parts), 420)


def _inventory_lane(row: dict[str, Any]) -> str:
    reader_role = reader_evidence_role(row)
    if reader_role == "main_answer_evidence":
        return "answer_support"
    if reader_role == "effect_size_or_mechanism":
        return "interpretive_context"
    if reader_role == "true_counterweight":
        return "limiting_evidence"
    if reader_role == "scope_boundary":
        return "scope_and_applicability"
    if reader_role == "decision_crux":
        return "decision_cruxes"
    role = str(row.get("role") or "").strip()
    relation = str(row.get("answer_relation") or "").strip()
    function = str(row.get("memo_function") or "").strip()
    if role in {"strongest_support", "quantitative_anchor"} or relation == "supports_answer" or function == "answer_anchor":
        return "answer_support"
    if role == "strongest_counterweight" or relation == "challenges_answer" or function == "counterweight":
        return "limiting_evidence"
    if role == "scope_boundary" or relation == "bounds_scope" or function == "scope_boundary":
        return "scope_and_applicability"
    if role == "decision_crux" or relation == "identifies_crux" or function == "crux":
        return "decision_cruxes"
    return "interpretive_context"


def _inventory_sort_rank(row: dict[str, Any]) -> int:
    try:
        return int(row.get("importance_rank") or 100)
    except (TypeError, ValueError):
        return 100


def _inventory_items(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    lanes = _dict(inventory.get("lanes"))
    for lane_rows in lanes.values():
        rows.extend(row for row in _list(lane_rows) if isinstance(row, dict))
    return rows


def _evidence_row(row: dict[str, Any]) -> dict[str, Any]:
    calibrated = _calibrated_claim_row(row)
    return _drop_empty(
        {
            "item_id": row.get("item_id"),
            "role": row.get("role"),
            "reader_evidence_role": reader_evidence_role(row),
            "answer_relation": row.get("answer_relation"),
            "memo_function": row.get("memo_function"),
            "claim": _short_text(calibrated.get("claim"), 520),
            "original_claim": _short_text(row.get("original_claim") or calibrated.get("original_claim"), 520),
            "claim_calibration_notes": _dedupe([*_string_list(row.get("claim_calibration_notes")), *_string_list(calibrated.get("calibration_notes"))]),
            "not_allowed_terms": _dedupe([*_string_list(row.get("not_allowed_terms")), *_string_list(calibrated.get("not_allowed_terms"))]),
            "source_labels": _string_list(row.get("source_labels")),
            "quantities": _brief_quantities(row),
            "decision_relevance": _calibrated_short(row.get("decision_relevance"), row, limit=420),
            "source_appraisal_note": _short_text(row.get("source_appraisal_note"), 260),
            "importance_rank": row.get("importance_rank"),
        }
    )


def _counterweight_dispositions(interface: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    counterweights = _list(interface.get("counterweights_and_disposition")) or [
        row for row in _list(interface.get("decision_evidence_table")) if isinstance(row, dict) and row.get("role") == "strongest_counterweight"
    ]
    for row in counterweights:
        if not isinstance(row, dict):
            continue
        if reader_evidence_role(row) == "effect_size_or_mechanism":
            continue
        disposition = _normalized_counterweight_disposition(row)
        rows.append(
            _drop_empty(
                {
                    "item_id": row.get("item_id"),
                    "claim": _short_text(_calibrated_claim_row(row).get("claim"), 520),
                    "disposition": disposition,
                    "disposition_rationale": _calibrated_short(row.get("disposition_rationale") or row.get("decision_relevance"), row, limit=420),
                    "source_labels": _string_list(row.get("source_labels")),
                    "quantities": _brief_quantities(row),
                    "uncertainty": "uncertain" if disposition == "creates_unresolved_crux" else "",
                }
            )
        )
    return _dedupe_rows(rows, "item_id")[:8]


def _normalized_counterweight_disposition(row: dict[str, Any]) -> str:
    text = " ".join(
        str(value or "")
        for value in [
            row.get("disposition"),
            row.get("answer_relation"),
            row.get("memo_function"),
            row.get("disposition_rationale"),
            row.get("decision_relevance"),
        ]
    ).lower()
    if "if they do not overturn" in text or "does not overturn" in text or "do not overturn" in text:
        return "bounds_answer"
    if "overturns" in text or "overturned" in text or "overturns_answer" in text:
        return "overturns_answer"
    if "dose" in text:
        return "bounds_dose"
    if "population" in text or "subgroup" in text or "individual" in text:
        return "bounds_population"
    if "endpoint" in text or "outcome" in text:
        return "bounds_endpoint"
    if "mechanism" in text or "explain" in text:
        return "explains_mechanism"
    if "bound" in text or "scope" in text or "limit" in text:
        return "weakens_confidence"
    if "challenge" in text or "counterweight" in text or "risk" in text:
        return "weakens_confidence"
    return "creates_unresolved_crux"


def _scope_boundaries(interface: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    contract = _dict(interface.get("decision_boundary_source_contract"))
    for row in _list(contract.get("boundary_obligations")):
        if not isinstance(row, dict) or row.get("boundary_type") == "counterweight_boundary":
            continue
        rows.append(
            _drop_empty(
                {
                    "boundary_id": row.get("boundary_id"),
                    "boundary_type": row.get("boundary_type"),
                    "statement": _calibrated_short(row.get("statement"), row, limit=420),
                    "writing_job": row.get("writing_job"),
                    "source_labels": _string_list(row.get("source_labels")),
                    "quantities": _list(row.get("quantities")),
                    "evidence_item_ids": _string_list(row.get("evidence_item_ids")),
                }
            )
        )
    if rows:
        return rows[:10]
    return [
        _evidence_row(row)
        for row in _list(interface.get("decision_evidence_table"))
        if isinstance(row, dict) and row.get("role") == "scope_boundary"
    ][:10]


def _decision_cruxes(interface: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _evidence_row(row)
        for row in _list(interface.get("decision_evidence_table"))
        if isinstance(row, dict) and row.get("role") == "decision_crux"
    ][:8]


def _source_weight_notes(interface: dict[str, Any]) -> list[dict[str, Any]]:
    source_cards = {
        _source_key(row): row
        for row in _list(_dict(interface.get("decision_boundary_source_contract")).get("source_use_cards"))
        if isinstance(row, dict)
    }
    notes = []
    for row in _list(interface.get("source_appraisal_summary")):
        if not isinstance(row, dict):
            continue
        source_key = _source_key(row)
        card = source_cards.get(source_key, {})
        note = _drop_empty(
            {
                "source_labels": _string_list(row.get("source_labels")),
                "decision_directness": row.get("decision_directness") or "unspecified",
                "useful_for": _string_list(card.get("use_for") or row.get("recommended_uses")),
                "not_enough_for": _string_list(row.get("source_use_warnings") or row.get("interpretation_caveats")),
                "key_claims": _string_list(card.get("key_claims"))[:3],
                "key_quantities": _string_list(card.get("key_quantities"))[:5],
                "evidence_item_ids": _string_list(card.get("evidence_item_ids"))[:8],
            }
        )
        if note.get("source_labels"):
            notes.append(note)
    return _dedupe_rows(notes, "source_labels")[:16]


def _informative_source_weight_note(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    if str(row.get("decision_directness") or "").strip() not in {"", "unknown", "unspecified"}:
        return True
    return bool(
        _list(row.get("useful_for"))
        or _list(row.get("not_enough_for"))
        or _list(row.get("key_claims"))
        or _list(row.get("key_quantities"))
    )


def _mandatory_retention_checklist(packet: dict[str, Any], interface: dict[str, Any]) -> list[dict[str, Any]]:
    obligations = required_memo_obligations(packet)
    if obligations:
        evidence_by_id = _interface_evidence_by_id(interface)
        rows = []
        for row in obligations[:24]:
            if not isinstance(row, dict):
                continue
            checklist_row = _mandatory_obligation_row(row, evidence_by_id=evidence_by_id)
            if checklist_row:
                rows.append(checklist_row)
        return rows
    return [
        _mandatory_evidence_row(row)
        for row in _list(interface.get("decision_evidence_table"))
        if isinstance(row, dict) and str(row.get("obligation_level") or "") == "must_include"
    ][:24]


def _mandatory_obligation_row(row: dict[str, Any], *, evidence_by_id: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    evidence_by_id = evidence_by_id or {}
    evidence_ids = _string_list(row.get("evidence_item_ids"))
    evidence = next((evidence_by_id[evidence_id] for evidence_id in evidence_ids if evidence_id in evidence_by_id), {})
    if evidence and evidence.get("overstatement_conflict"):
        return {}
    statement = str(row.get("statement") or "")
    calibrated = calibrate_claim_for_writer(statement, evidence) if evidence else {"claim": statement}
    return _drop_empty(
        {
            "obligation_id": row.get("obligation_id"),
            "obligation_type": row.get("obligation_type"),
            "role": row.get("role"),
            "statement": _short_text(calibrated.get("claim"), 520),
            "original_statement": _short_text(calibrated.get("original_claim"), 520),
            "claim_calibration_notes": _string_list(calibrated.get("calibration_notes")),
            "prose_instruction": _short_text(row.get("prose_instruction"), 360),
            "source_labels": _string_list(row.get("source_labels")),
            "source_ids": _dedupe([*_string_list(row.get("source_ids")), *_string_list(evidence.get("source_ids"))]),
            "quantities": _brief_quantities(evidence or row),
            "evidence_item_ids": evidence_ids,
            "why_it_matters": _short_text(row.get("why_it_matters"), 360),
            "acceptable_expression": row.get("acceptable_expression") if isinstance(row.get("acceptable_expression"), dict) else {},
        }
    )


def _interface_evidence_by_id(interface: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = {}
    for row in _list(interface.get("decision_evidence_table")):
        if isinstance(row, dict) and row.get("item_id"):
            rows[str(row.get("item_id"))] = row
    return rows


def _mandatory_evidence_row(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "item_id": row.get("item_id"),
            "role": row.get("role"),
            "statement": _short_text(_calibrated_claim_row(row).get("claim"), 520),
            "source_labels": _string_list(row.get("source_labels")),
            "source_ids": _string_list(row.get("source_ids")),
            "quantities": _brief_quantities(row),
        }
    )


def _memo_obligation_contract(packet: dict[str, Any], mandatory_checklist: list[dict[str, Any]]) -> dict[str, Any]:
    raw_obligations = required_memo_obligations(packet)
    source_rows = raw_obligations if raw_obligations else mandatory_checklist
    obligations = []
    for index, row in enumerate(source_rows[:24], start=1):
        if not isinstance(row, dict):
            continue
        obligations.append(
            _drop_empty(
                {
                    "obligation_id": row.get("obligation_id") or row.get("item_id") or f"memo_obligation_{index:03d}",
                    "role": row.get("role") or row.get("obligation_type"),
                    "required": True,
                    "claim_to_preserve": _short_text(row.get("audit_claim") or row.get("statement") or row.get("claim"), 620),
                    "writing_job": _short_text(row.get("prose_instruction"), 360),
                    "why_it_matters": _short_text(row.get("why_it_matters"), 360),
                    "source_ids": _string_list(row.get("source_ids")),
                    "source_labels": _string_list(row.get("source_labels")),
                    "quantities": _brief_quantities(row),
                    "evidence_item_ids": _string_list(row.get("evidence_item_ids")),
                    "acceptable_expression": row.get("acceptable_expression")
                    if isinstance(row.get("acceptable_expression"), dict)
                    else _acceptable_expression_from_checklist(row),
                }
            )
        )
    return {
        "schema_id": "memo_obligation_contract_v1",
        "method": "canonical_required_obligations_from_memo_obligation_packet",
        "required_count": len(obligations),
        "obligations": obligations,
        "writer_use": [
            "Represent each required obligation as natural analysis in the section where it belongs.",
            "Keep listed source IDs and quantities attached to the claim they support.",
            "Use the acceptable_expression fields as the validation contract for faithful compression.",
        ],
    }


def _acceptable_expression_from_checklist(row: dict[str, Any]) -> dict[str, Any]:
    quantities = _brief_quantities(row)
    return _drop_empty(
        {
            "must_attach_to_claim": True,
            "required_source_ids": _string_list(row.get("source_ids")),
            "required_quantity_values": [str(quantity.get("value") or "").strip() for quantity in quantities if str(quantity.get("value") or "").strip()],
            "semantic_job": row.get("prose_instruction"),
            "claim_to_preserve": row.get("statement") or row.get("claim"),
        }
    )


def _citation_registry(source_trail: list[Any]) -> list[dict[str, Any]]:
    registry = source_id_registry_for_model(source_trail)
    source_by_id = {str(source.get("source_id") or source.get("source_label") or ""): source for source in source_trail if isinstance(source, dict)}
    rows = []
    for row in registry:
        source = source_by_id.get(str(row.get("source_id") or ""), {})
        rows.append(
            _drop_empty(
                {
                    "source_id": row.get("source_id"),
                    "source_label": source.get("source_label"),
                    "source_url": source.get("source_url"),
                }
            )
        )
    return rows


def _most_important_quantity(interface: dict[str, Any]) -> str:
    for row in _list(interface.get("quantity_anchors")):
        if isinstance(row, dict) and str(row.get("value") or "").strip():
            interpretation = calibrate_text_for_writer(str(row.get("interpretation") or "").strip())
            return f"{row.get('value')}: {interpretation}" if interpretation else str(row.get("value"))
    for row in _list(interface.get("decision_evidence_table")):
        quantities = _brief_quantities(row) if isinstance(row, dict) else []
        if quantities:
            first = quantities[0]
            interpretation = calibrate_text_for_writer(str(first.get("interpretation") or "").strip())
            return f"{first.get('value')}: {interpretation}" if interpretation else str(first.get("value"))
    return ""


def _brief_quantities(row: dict[str, Any]) -> list[dict[str, Any]]:
    quantities = []
    for quantity in _list(row.get("quantities")):
        if not isinstance(quantity, dict):
            continue
        value = str(quantity.get("value") or "").strip()
        if not value:
            continue
        quantities.append(
            _drop_empty(
                {
                    "value": value,
                    "evidence_bundle_id": str(quantity.get("evidence_bundle_id") or "").strip(),
                    "assertion_bundle": quantity.get("assertion_bundle") if isinstance(quantity.get("assertion_bundle"), dict) else {},
                    "interpretation": _calibrated_short(quantity.get("interpretation"), row, limit=220),
                    "quantity_role": quantity.get("quantity_role"),
                    "statistic_type": quantity.get("statistic_type") or _dict(quantity.get("assertion_bundle")).get("statistic_type"),
                    "endpoint": quantity.get("endpoint") or quantity.get("measures") or _dict(quantity.get("assertion_bundle")).get("endpoint"),
                    "population": quantity.get("population") or _dict(quantity.get("assertion_bundle")).get("population"),
                    "exposure_or_comparator": quantity.get("exposure_or_comparator") or _dict(quantity.get("assertion_bundle")).get("exposure_or_comparator"),
                    "interval": quantity.get("interval") or _dict(quantity.get("assertion_bundle")).get("interval"),
                    "allowed_inference": quantity.get("allowed_inference") or _dict(quantity.get("assertion_bundle")).get("allowed_inference"),
                    "forbidden_inference": quantity.get("forbidden_inference") or _dict(quantity.get("assertion_bundle")).get("forbidden_inference"),
                    "source_labels": _string_list(quantity.get("source_labels")),
                    "source_ids": _string_list(quantity.get("source_ids")) or _string_list(_dict(quantity.get("assertion_bundle")).get("source_ids")),
                    "quantity_id": str(quantity.get("quantity_id") or "").strip(),
                    "source_evidence_item_id": str(quantity.get("source_evidence_item_id") or "").strip(),
                    "memo_use": str(quantity.get("memo_use") or "").strip(),
                    "must_retain": bool(quantity.get("must_retain")) if "must_retain" in quantity else None,
                    "analyst_quantity_relevance": quantity.get("analyst_quantity_relevance") if isinstance(quantity.get("analyst_quantity_relevance"), dict) else {},
                }
            )
        )
    return quantities[:6]


def _source_ids(row: dict[str, Any]) -> list[str]:
    return _dedupe([*_string_list(row.get("source_ids")), str(row.get("source_id") or "").strip()])


def _checklist_row_requires_source(row: dict[str, Any]) -> bool:
    role = str(row.get("role") or "").strip().lower()
    if role.endswith("writer_guidance") or role in {"writer_guidance", "critique_writer_guidance"}:
        return False
    if _list(row.get("evidence_item_ids")) or _list(row.get("quantities")):
        return True
    if str(row.get("obligation_type") or "").strip():
        return True
    return bool(str(row.get("claim") or row.get("statement") or "").strip())


def _source_key(row: dict[str, Any]) -> str:
    return "|".join(_norm(label) for label in _string_list(row.get("source_labels")))


def _first_text(rows: list[Any], *, keys: tuple[str, ...]) -> str:
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in keys:
            text = str(row.get(key) or "").strip()
            if text:
                return text
    return ""


def _dedupe_rows(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        raw = row.get(key)
        marker = tuple(raw) if isinstance(raw, list) else str(raw or "")
        if not marker or marker in seen:
            continue
        seen.add(marker)
        deduped.append(row)
    return deduped


def _calibrated_claim_row(row: dict[str, Any]) -> dict[str, Any]:
    claim = str(row.get("reader_claim") or row.get("claim") or row.get("statement") or "").strip()
    if not claim:
        return {"claim": ""}
    return calibrate_claim_for_writer(claim, row)


def _calibrated_short(value: Any, evidence: dict[str, Any] | None = None, *, limit: int) -> str:
    return _short_text(calibrate_text_for_writer(str(value or ""), evidence or {}), limit)


def _looks_generic(value: Any) -> bool:
    text = _norm(str(value or ""))
    return text in {"state the default answer", "answer the decision question", "not specified"} or len(text.split()) < 5


def _looks_truncated_or_scaffolded(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    return (
        text.endswith("...")
        or text.endswith("…")
        or "{'classification'" in text
        or "use the grouped evidence to answer" in lowered
        or "state the default" in lowered
    )


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}
