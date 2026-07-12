from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_adaptive_outline import build_adaptive_memo_outline
from epistemic_case_mapper.map_briefing_decision_boundary_source_contract import (
    build_decision_boundary_source_contract,
    contract_quality_summary,
)
from epistemic_case_mapper.map_briefing_memo_obligations import required_memo_obligations
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_writer_guidance import compact_writer_guidance_for_model


GENERIC_JUDGMENT_PATTERNS = (
    "use counterweights to bound",
    "connect this reasoning step",
    "write directly from",
    "answer the decision question",
    "if they do not overturn",
)


def build_writer_decision_interface(memo_ready_packet: dict[str, Any]) -> dict[str, Any]:
    """Compile a memo-ready packet into the only context the writer model should see."""

    packet = memo_ready_packet if isinstance(memo_ready_packet, dict) else {}
    visible_items = _model_visible_evidence_items(packet)
    filtered_items = _filtered_evidence_items(packet, visible_items)
    obligations = required_memo_obligations(packet)
    selected_context = _selected_interpretive_context(packet, filtered_items)
    reasoning_hierarchy = _reasoning_hierarchy(packet, visible_items, filtered_items, selected_context=selected_context)
    boundary_source_contract = build_decision_boundary_source_contract(
        packet,
        visible_items,
        selected_context=selected_context,
    )
    interface = {
        "schema_id": "writer_decision_interface_v1",
        "decision_question": packet.get("decision_question"),
        "bottom_line": _bottom_line(packet, visible_items),
        "confidence": _dict(packet.get("answer_spine")).get("confidence", "not_specified"),
        "answer_frame": _answer_frame(packet, visible_items),
        "decision_evidence_table": _decision_evidence_table(visible_items),
        "rescued_context_table": _decision_evidence_table(selected_context),
        "source_appraisal_summary": _source_appraisal_summary(packet, visible_items),
        "decision_boundary_source_contract": boundary_source_contract,
        "reasoning_hierarchy": reasoning_hierarchy,
        "support_that_drives_answer": _evidence_group(visible_items, roles={"strongest_support", "quantitative_anchor"}),
        "counterweights_and_disposition": _counterweights(packet, visible_items),
        "scope_boundaries": _evidence_group(visible_items, roles={"scope_boundary"}),
        "decision_cruxes": _evidence_group(visible_items, roles={"decision_crux"}),
        "practical_implications": _practical_implications(packet, visible_items),
        "practical_implication_cards": _practical_implication_cards(packet, visible_items),
        "must_use_evidence": [_writer_evidence_item(item) for item in visible_items],
        "quantity_anchors": _quantity_anchors(visible_items),
        "critique_writer_guidance": compact_writer_guidance_for_model(_dict(packet.get("writer_guidance_packet"))),
        "source_trail": _visible_source_trail(packet, visible_items),
        "retention_checklist": _retention_checklist(obligations),
        "excluded_evidence_log": [_excluded_evidence_log_row(item) for item in filtered_items],
        "lineage_report": _lineage_report(packet, visible_items, filtered_items, obligations),
    }
    interface["adaptive_memo_outline"] = build_adaptive_memo_outline(interface)
    quality = build_writer_decision_interface_quality_report(interface)
    interface["quality_warnings"] = quality["warnings"]
    return interface


def build_writer_model_context(writer_interface: dict[str, Any]) -> dict[str, Any]:
    """Return the subset of the writer interface that belongs in synthesis prompts."""

    interface = writer_interface if isinstance(writer_interface, dict) else {}
    hierarchy = _dict(interface.get("reasoning_hierarchy"))
    context = {
        "schema_id": "writer_model_context_v1",
        "source_schema_id": interface.get("schema_id"),
        "decision_question": interface.get("decision_question"),
        "bottom_line": interface.get("bottom_line"),
        "confidence": interface.get("confidence"),
        "answer_frame": _dict(interface.get("answer_frame")),
        "decision_evidence_table": _list(interface.get("decision_evidence_table")),
        "rescued_context_table": _list(interface.get("rescued_context_table")),
        "source_appraisal_summary": _list(interface.get("source_appraisal_summary")),
        "decision_boundary_source_contract": _dict(interface.get("decision_boundary_source_contract")),
        "reasoning_hierarchy": hierarchy,
        "adaptive_memo_outline": _dict(interface.get("adaptive_memo_outline")),
        "practical_implications": _string_list(interface.get("practical_implications")),
        "practical_implication_cards": _list(interface.get("practical_implication_cards")),
        "quantity_anchors": _list(interface.get("quantity_anchors")),
        "critique_writer_guidance": _dict(interface.get("critique_writer_guidance")),
        "source_trail": _list(interface.get("source_trail")),
    }
    if not _list(hierarchy.get("reasoning_moves")):
        context.update(
            {
                "support_that_drives_answer": _list(interface.get("support_that_drives_answer")),
                "counterweights_and_disposition": _list(interface.get("counterweights_and_disposition")),
                "scope_boundaries": _list(interface.get("scope_boundaries")),
                "decision_cruxes": _list(interface.get("decision_cruxes")),
            }
        )
    return context


def build_writer_decision_interface_quality_report(interface: dict[str, Any]) -> dict[str, Any]:
    warnings = []
    if not _list(interface.get("support_that_drives_answer")):
        warnings.append("missing_support_that_drives_answer")
    if not _list(interface.get("counterweights_and_disposition")):
        warnings.append("missing_counterweights")
    if not _list(interface.get("quantity_anchors")):
        warnings.append("missing_quantity_anchors")
    if _contains_generic_judgment(_reader_facing_judgment_surface(interface)):
        warnings.append("generic_or_scaffolded_judgment_present")
    guidance = _dict(interface.get("critique_writer_guidance"))
    if guidance.get("status") == "ready" and not _list(guidance.get("guidance")):
        warnings.append("critique_guidance_empty_despite_ready_status")
    hierarchy = _dict(interface.get("reasoning_hierarchy"))
    if not _list(hierarchy.get("reasoning_moves")):
        warnings.append("missing_reasoning_hierarchy")
    contract_summary = contract_quality_summary(_dict(interface.get("decision_boundary_source_contract")))
    if contract_summary.get("status") == "warning":
        warnings.append("decision_boundary_source_contract_warning")
    if not contract_summary.get("source_card_count"):
        warnings.append("missing_source_use_cards")
    retention = _list(interface.get("retention_checklist"))
    evidence_ids = {
        evidence_id
        for item in _list(interface.get("must_use_evidence"))
        if isinstance(item, dict)
        for evidence_id in _string_list(item.get("item_id"))
    }
    missing_obligation_evidence = [
        row.get("obligation_id")
        for row in retention
        if isinstance(row, dict)
        and not any(evidence_id in evidence_ids for evidence_id in _string_list(row.get("evidence_item_ids")))
    ]
    if missing_obligation_evidence:
        warnings.append("retention_obligation_without_visible_evidence")
    source_appraisal_rows = _list(interface.get("source_appraisal_summary"))
    informative_source_appraisal_count = sum(1 for row in source_appraisal_rows if _informative_source_appraisal(row))
    if source_appraisal_rows and informative_source_appraisal_count == 0:
        warnings.append("source_appraisal_summary_uninformative")
    return {
        "schema_id": "writer_decision_interface_quality_report_v1",
        "status": "ready" if not warnings else "warning",
        "warnings": warnings,
        "must_use_evidence_count": len(_list(interface.get("must_use_evidence"))),
        "quantity_anchor_count": len(_list(interface.get("quantity_anchors"))),
        "reasoning_move_count": len(_list(hierarchy.get("reasoning_moves"))),
        "rescued_context_count": _reasoning_hierarchy_rescue_count(hierarchy),
        "excluded_evidence_count": len(_list(interface.get("excluded_evidence_log"))),
        "source_appraisal_row_count": len(source_appraisal_rows),
        "informative_source_appraisal_row_count": informative_source_appraisal_count,
        "decision_boundary_source_contract_quality": contract_summary,
        "missing_obligation_evidence": missing_obligation_evidence,
    }


def _bottom_line(packet: dict[str, Any], visible_items: list[dict[str, Any]]) -> str:
    spine = _dict(packet.get("answer_spine"))
    logic = _dict(packet.get("analyst_decision_logic"))
    for value in (spine.get("default_read"), spine.get("bounded_answer"), logic.get("bounded_bottom_line")):
        text = _clean_answer_text(value)
        if text:
            return text
    support = _first_claim(visible_items, {"strongest_support", "quantitative_anchor"})
    counter = _first_claim(visible_items, {"strongest_counterweight"})
    if support and counter:
        return f"{support} The main counterweight is: {counter}"
    return support or counter


def _answer_frame(packet: dict[str, Any], visible_items: list[dict[str, Any]]) -> dict[str, Any]:
    logic = _dict(packet.get("analyst_decision_logic"))
    scope = _sort_items([item for item in visible_items if _answer_relation(item) == "bounds_scope"])
    counterweights = _sort_items([item for item in visible_items if _answer_relation(item) == "challenges_answer"])
    cruxes = _sort_items([item for item in visible_items if _answer_relation(item) == "identifies_crux"])
    support = _sort_items([item for item in visible_items if _answer_relation(item) == "supports_answer"])
    direct_answer = _bottom_line(packet, visible_items)
    main_counterweight = _clean_answer_text(logic.get("strongest_counterweight")) or _claim_text(_first_item(counterweights))
    scope_note = _short_text("; ".join(_claim_text(item) for item in scope[:3]), 520)
    return {
        "bottom_line": direct_answer,
        "direct_answer": direct_answer,
        "confidence": _dict(packet.get("answer_spine")).get("confidence", "not_specified"),
        "confidence_basis": _confidence_basis(packet, visible_items),
        "main_support": _clean_answer_text(logic.get("support_summary")) or _claim_text(_first_item(support)),
        "main_counterweight": main_counterweight,
        "scope_note": scope_note,
        "decision_application": _decision_application_statement(direct_answer, main_counterweight, scope_note),
        "main_uncertainty": _short_text("; ".join(_claim_text(item) for item in [*counterweights[:2], *cruxes[:2]]), 520),
        "scoping_policy": "State the answer for the population, option, or use case supported by the evidence; use scope and counterweight rows to bound rather than overstate it.",
    }


def _counterweights(packet: dict[str, Any], visible_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    weighting = _dict(packet.get("analyst_decision_logic")).get("counterweight_weighting")
    rows = []
    for item in visible_items:
        if not isinstance(item, dict) or str(item.get("role") or "") != "strongest_counterweight":
            continue
        row = _writer_evidence_item(item)
        row["disposition"] = _counterweight_disposition(weighting)
        row["disposition_rationale"] = _short_text(str(weighting or ""), 320)
        rows.append(row)
    return rows


def _counterweight_disposition(weighting: Any) -> str:
    text = str(weighting or "").lower()
    if "overturn" in text or "change" in text:
        return "bounds_or_may_change"
    if "weaken" in text:
        return "weakens"
    if "bound" in text or "scope" in text or "limit" in text:
        return "bounds"
    return "requires_adjudication"


def _implication_card(implication_type: str, statement: str, item: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "implication_id": f"implication_{index:03d}",
        "implication_type": implication_type,
        "statement": _short_text(statement, 420),
        "source_labels": _source_labels(item),
        "basis_evidence_item_ids": _string_list(item.get("item_id")),
    }


def _practical_implications(packet: dict[str, Any], visible_items: list[dict[str, Any]]) -> list[str]:
    logic = _dict(packet.get("analyst_decision_logic"))
    rows = _string_list(logic.get("practical_implications"))
    if rows:
        return rows[:5]
    return [card["statement"] for card in _practical_implication_cards(packet, visible_items)[:5]]


def _practical_implication_cards(packet: dict[str, Any], visible_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    logic = _dict(packet.get("analyst_decision_logic"))
    explicit = _string_list(logic.get("practical_implications"))
    if explicit:
        return [
            {
                "implication_id": f"implication_{index:03d}",
                "implication_type": "model_supplied",
                "statement": _short_text(statement, 420),
                "source_labels": [],
                "basis_evidence_item_ids": [],
            }
            for index, statement in enumerate(explicit[:6], start=1)
        ]
    cards = []
    bottom = _bottom_line(packet, visible_items)
    support = _first_item(_sort_items([item for item in visible_items if _answer_relation(item) == "supports_answer"]))
    counter = _first_item(_sort_items([item for item in visible_items if _answer_relation(item) == "challenges_answer"]))
    scope = _first_item(_sort_items([item for item in visible_items if _answer_relation(item) == "bounds_scope"]))
    crux = _first_item(_sort_items([item for item in visible_items if _answer_relation(item) == "identifies_crux"]))
    if bottom:
        cards.append(_implication_card("default_application", bottom, support, len(cards) + 1))
    if counter:
        cards.append(_implication_card("exception_or_counterweight", f"Treat this as the main exception or caution: {_claim_text(counter)}", counter, len(cards) + 1))
    if scope:
        cards.append(_implication_card("scope_boundary", f"Bound application by this scope condition: {_claim_text(scope)}", scope, len(cards) + 1))
    if crux:
        cards.append(_implication_card("monitoring_or_crux", f"Track this crux because it could change the answer: {_claim_text(crux)}", crux, len(cards) + 1))
    return cards[:6]


def _confidence_basis(packet: dict[str, Any], visible_items: list[dict[str, Any]]) -> str:
    spine = _dict(packet.get("answer_spine"))
    logic = _dict(packet.get("analyst_decision_logic"))
    support_summary = _clean_answer_text(logic.get("support_summary"))
    main_counterweight = _clean_answer_text(logic.get("strongest_counterweight"))
    if support_summary and main_counterweight:
        return _short_text(f"Primary support: {support_summary} Main counterweight: {main_counterweight}", 420)
    if support_summary:
        return _short_text(support_summary, 420)
    candidates = [
        *_string_list(spine.get("confidence_reasons")),
        str(logic.get("counterweight_weighting") or ""),
        *re.split(r";\s+", str(spine.get("why_this_read") or "")),
    ]
    for candidate in candidates:
        text = _clean_answer_text(candidate)
        if text and not _contains_generic_judgment(text):
            return _short_text(text, 420)
    support = _first_claim(visible_items, {"strongest_support", "quantitative_anchor"})
    counter = _first_claim(visible_items, {"strongest_counterweight"})
    if support and counter:
        return _short_text(f"Support is bounded by this counterweight: {counter}", 420)
    return _short_text(support or counter, 420)


def _decision_application_statement(direct_answer: str, main_counterweight: str, scope_note: str) -> str:
    counterweight = _strip_terminal_punctuation(main_counterweight)
    scope = _strip_terminal_punctuation(scope_note)
    if main_counterweight and scope_note:
        return _short_text(
            f"Use the default answer where it applies; treat this as the main exception or caution: {counterweight}. Scope boundary: {scope}.",
            520,
        )
    if main_counterweight:
        return _short_text(f"Use the default answer while treating this as the main exception or caution: {counterweight}.", 520)
    if scope_note:
        return _short_text(f"Use the default answer within this scope boundary: {scope}.", 520)
    return _short_text(direct_answer, 520)


def _reasoning_hierarchy(
    packet: dict[str, Any],
    visible_items: list[dict[str, Any]],
    filtered_items: list[dict[str, Any]],
    *,
    selected_context: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a compact, deterministic writing hierarchy from existing model judgments."""

    selected_context = selected_context if isinstance(selected_context, list) else _selected_interpretive_context(packet, filtered_items)
    moves = [
        _reasoning_move(
            "answer_frame",
            "State the bounded answer and confidence before explaining the evidence.",
            [],
            guidance=[_bottom_line(packet, visible_items)],
        ),
        _reasoning_move(
            "primary_answer_evidence",
            "Explain the source-backed evidence that most directly supports the bounded answer.",
            _sort_items(_evidence_group(visible_items, roles={"strongest_support", "quantitative_anchor"})),
        ),
        _reasoning_move(
            "quantitative_calibration",
            "Use quantities to calibrate the size, direction, or boundary of the decision read.",
            _quantity_context_items(visible_items, selected_context),
        ),
        _reasoning_move(
            "counterweights_and_limits",
            "Give counterweights and scope boundaries their force, then explain how they bound the answer.",
            _sort_items(
                [
                    *_evidence_group(visible_items, roles={"strongest_counterweight"}),
                    *_evidence_group(visible_items, roles={"scope_boundary"}),
                ]
            ),
        ),
        _reasoning_move(
            "decision_cruxes",
            "Name the cruxes or distinctions that would most change the answer.",
            _sort_items(_evidence_group(visible_items, roles={"decision_crux"})),
        ),
        _reasoning_move(
            "interpretive_context",
            "Use context that changes how the answer should be interpreted or applied.",
            selected_context,
        ),
    ]
    return {
        "schema_id": "decision_reasoning_hierarchy_v1",
        "method": "deterministic_projection_from_existing_packet_judgments",
        "decision_question": packet.get("decision_question"),
        "bottom_line": _bottom_line(packet, visible_items),
        "confidence": _dict(packet.get("answer_spine")).get("confidence", "not_specified"),
        "reasoning_moves": [move for move in moves if move.get("guidance") or move.get("evidence_refs")],
        "projection_policy": [
            "Uses existing model-produced packet roles, obligation levels, ranks, and quantity bindings.",
            "Does not introduce a new semantic model call.",
            "Rescues should-include and quantity-bearing context for synthesis without making it mandatory retention evidence.",
        ],
    }


def _reasoning_move(
    move: str,
    writing_goal: str,
    items: list[dict[str, Any]],
    *,
    guidance: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "move": move,
        "writing_goal": writing_goal,
        "guidance": [text for text in _string_list(guidance or []) if text],
        "evidence_refs": [_evidence_ref(item) for item in items if isinstance(item, dict)],
    }


def _evidence_ref(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_id": item.get("item_id"),
        "role": item.get("role"),
        "answer_relation": _answer_relation(item),
    }


def _selected_interpretive_context(packet: dict[str, Any], filtered_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    guidance_profiles = _guidance_profiles(packet)
    candidates = [
        item
        for item in filtered_items
        if isinstance(item, dict) and _context_rescue_score(item, guidance_profiles=guidance_profiles) >= 5
    ]
    return sorted(
        candidates,
        key=lambda item: (-_context_rescue_score(item, guidance_profiles=guidance_profiles), _importance_rank(item), str(item.get("item_id") or "")),
    )[:6]


def _quantity_context_items(
    visible_items: list[dict[str, Any]],
    selected_context: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = [
        item
        for item in [*visible_items, *selected_context]
        if isinstance(item, dict) and (_list(item.get("quantities")) or _list(item.get("excluded_quantity_values")))
    ]
    return _dedupe_items(_sort_items(candidates))[:10]


def _decision_evidence_table(visible_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_writer_evidence_item(item) for item in _sort_items(visible_items)]


def _source_appraisal_summary(packet: dict[str, Any], visible_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for item in _sort_items(visible_items):
        if not isinstance(item, dict):
            continue
        appraisal = _dict(item.get("source_appraisal"))
        labels = _source_labels(item)
        key = "|".join(labels) or str(item.get("item_id") or "")
        if key in seen or not labels:
            continue
        seen.add(key)
        rows.append(
            {
                "source_labels": labels,
                "decision_directness": appraisal.get("decision_directness", "unknown"),
                "evidence_proximity": _string_list(appraisal.get("evidence_proximity"))[:4],
                "recommended_uses": _string_list(appraisal.get("recommended_uses"))[:4],
                "source_use_warnings": _string_list(item.get("source_use_warnings") or appraisal.get("source_use_warnings"))[:5],
                "interpretation_caveats": _string_list(appraisal.get("interpretation_caveats"))[:4],
                "allowed_wording": _dict(item.get("allowed_wording") or appraisal.get("allowed_wording")),
            }
        )
    return rows


def _sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [item for item in items if isinstance(item, dict)],
        key=lambda item: (
            _importance_rank(item),
            -_diagnosticity_score(item),
            str(item.get("item_id") or ""),
        ),
    )


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for item in items:
        item_id = str(item.get("item_id") or "")
        if item_id and item_id not in seen:
            seen.add(item_id)
            rows.append(item)
    return rows


def _context_rescue_score(item: dict[str, Any], *, guidance_profiles: list[dict[str, Any]]) -> int:
    guidance_overlap = _guidance_overlap(item, guidance_profiles)
    if (
        str(item.get("source_memo_role") or "") == "quantitative_anchor"
        and not _list(item.get("quantities"))
        and not guidance_overlap
    ):
        return 0
    score = 0
    if str(item.get("obligation_level") or "") == "should_include":
        score += 5
    if _list(item.get("quantities")):
        score += 3
    if _list(item.get("excluded_quantity_values")):
        score += 1
    if str(item.get("source_memo_role") or "") in {"mechanism_or_context", "quantitative_anchor"}:
        score += 1
    if str(item.get("memo_function") or "") in {"answer_anchor", "counterweight", "scope_boundary", "crux"}:
        score += 2
    if guidance_overlap:
        score += 6
    score += max(0, 3 - min(_importance_rank(item), 100) // 20)
    return score


def _guidance_profiles(packet: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = []
    guidance = _dict(packet.get("compact_writer_guidance")) or compact_writer_guidance_for_model(_dict(packet.get("writer_guidance_packet")))
    for row in _list(guidance.get("guidance")):
        if not isinstance(row, dict):
            continue
        source_labels = set(_source_labels(row))
        if not source_labels:
            continue
        terms: set[str] = set()
        for value in _string_list(row.get("validation_terms")):
            if len(value) > 3:
                terms.add(value.lower())
        for text in _string_list(row.get("instruction")) + _string_list(row.get("why_it_matters")):
            terms.update(_content_terms(text))
        if terms:
            profiles.append({"source_labels": source_labels, "terms": terms})
    return profiles


def _guidance_overlap(item: dict[str, Any], guidance_profiles: list[dict[str, Any]]) -> bool:
    if not guidance_profiles:
        return False
    item_source_labels = set(_source_labels(item))
    item_terms = _content_terms(
        " ".join(
            [
                str(item.get("reader_claim") or ""),
                str(item.get("decision_relevance") or ""),
                str(item.get("include_reason") or ""),
            ]
        )
    )
    for profile in guidance_profiles:
        if not item_source_labels.intersection(set(profile.get("source_labels", set()))):
            continue
        if len(set(profile.get("terms", set())).intersection(item_terms)) >= 3:
            return True
    return False


def _importance_rank(item: dict[str, Any]) -> int:
    try:
        return int(item.get("importance_rank") or 100)
    except (TypeError, ValueError):
        return 100


def _diagnosticity_score(item: dict[str, Any]) -> int:
    try:
        return int(_dict(item.get("decision_diagnosticity")).get("score") or 0)
    except (TypeError, ValueError):
        return 0


def _reasoning_hierarchy_rescue_count(hierarchy: dict[str, Any]) -> int:
    for move in _list(hierarchy.get("reasoning_moves")):
        if isinstance(move, dict) and move.get("move") == "interpretive_context":
            return len(_list(move.get("evidence_refs")))
    return 0


def _evidence_group(visible_items: list[dict[str, Any]], *, roles: set[str]) -> list[dict[str, Any]]:
    return [_writer_evidence_item(item) for item in visible_items if isinstance(item, dict) and str(item.get("role") or "") in roles]


def _writer_evidence_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_id": item.get("item_id"),
        "role": item.get("role"),
        "source_role": item.get("source_role"),
        "answer_relation": _answer_relation(item),
        "answer_relation_basis": item.get("answer_relation_basis"),
        "claim": item.get("reader_claim"),
        "source_labels": _source_labels(item),
        "quantities": _quantity_values(item.get("quantities")),
        "decision_relevance": _short_text(str(item.get("decision_relevance") or ""), 360),
        "caveat": _short_text(str(item.get("caveat") or ""), 260),
        "source_appraisal_note": _source_appraisal_note(item),
        "lineage": _dict(item.get("lineage")),
        "obligation_level": item.get("obligation_level"),
        "memo_function": item.get("memo_function"),
        "source_memo_role": str(item.get("source_memo_role") or "").strip(),
        "importance_rank": item.get("importance_rank"),
    }


def _answer_relation(item: dict[str, Any]) -> str:
    relation = str(item.get("answer_relation") or "").strip()
    if relation:
        return relation
    role = str(item.get("role") or "")
    return {
        "strongest_support": "supports_answer",
        "quantitative_anchor": "supports_answer",
        "strongest_counterweight": "challenges_answer",
        "scope_boundary": "bounds_scope",
        "decision_crux": "identifies_crux",
        "context_only": "contextualizes_answer",
    }.get(role, "contextualizes_answer")


def _claim_text(item: dict[str, Any]) -> str:
    return str(item.get("reader_claim") or item.get("claim") or "").strip()


def _source_appraisal_note(item: dict[str, Any]) -> str:
    appraisal = _dict(item.get("source_appraisal"))
    parts = []
    directness = str(appraisal.get("decision_directness") or "").strip()
    if directness and directness != "unknown":
        parts.append(f"directness: {directness}")
    recommended = ", ".join(_string_list(appraisal.get("recommended_uses"))[:2])
    if recommended:
        parts.append(f"use: {recommended}")
    warnings = ", ".join(_string_list(item.get("source_use_warnings") or appraisal.get("source_use_warnings"))[:3])
    if warnings:
        parts.append(f"caveats: {warnings}")
    wording = _dict(item.get("allowed_wording") or appraisal.get("allowed_wording"))
    qualifiers = ", ".join(_string_list(wording.get("must_qualify_with"))[:2])
    if qualifiers:
        parts.append(f"wording: {qualifiers}")
    return _short_text("; ".join(parts), 360)


def _quantity_anchors(visible_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in visible_items:
        if not isinstance(item, dict):
            continue
        for quantity in _list(item.get("quantities")):
            if not isinstance(quantity, dict):
                continue
            value = str(quantity.get("value") or "").strip()
            if not value:
                continue
            rows.append(
                {
                    "value": value,
                    "interpretation": str(quantity.get("interpretation") or "").strip(),
                    "source_labels": _source_labels(quantity) or _source_labels(item),
                    "evidence_item_id": item.get("item_id"),
                    "role": item.get("role"),
                }
            )
    return rows


def _visible_source_trail(packet: dict[str, Any], visible_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    visible_labels = {label for item in visible_items for label in _source_labels(item)}
    rows = []
    for source in _list(packet.get("source_trail")):
        if not isinstance(source, dict):
            continue
        label = str(source.get("source_label") or source.get("display_label") or "").strip()
        if label and label in visible_labels:
            rows.append(source)
    if rows:
        return rows
    return [{"source_label": label} for label in sorted(visible_labels)]


def _retention_checklist(obligations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for obligation in obligations:
        rows.append(
            {
                "obligation_id": obligation.get("obligation_id"),
                "obligation_type": obligation.get("obligation_type"),
                "role": obligation.get("role"),
                "statement": obligation.get("statement"),
                "prose_instruction": obligation.get("prose_instruction"),
                "source_labels": _string_list(obligation.get("source_labels")),
                "quantities": _quantity_values(obligation.get("quantities")),
                "evidence_item_ids": _string_list(obligation.get("evidence_item_ids")),
            }
        )
    return rows


def _excluded_evidence_log_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_id": item.get("item_id"),
        "role": item.get("role"),
        "source_label": item.get("source_label"),
        "obligation_level": item.get("obligation_level"),
        "must_use": bool(item.get("must_use")),
        "filter_reason": "not_marked_must_use_for_memo_synthesis",
    }


def _lineage_report(
    packet: dict[str, Any],
    visible_items: list[dict[str, Any]],
    filtered_items: list[dict[str, Any]],
    obligations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_id": "writer_decision_interface_lineage_report_v1",
        "source_packet_schema_id": packet.get("schema_id"),
        "source_packet_method": packet.get("method"),
        "original_evidence_item_count": len([item for item in _list(packet.get("evidence_items")) if isinstance(item, dict)]),
        "model_visible_evidence_item_count": len(visible_items),
        "filtered_evidence_item_count": len(filtered_items),
        "required_obligation_count": len(obligations),
        "visible_evidence_item_ids": [str(item.get("item_id") or "") for item in visible_items],
        "filtered_evidence_item_ids": [str(item.get("item_id") or "") for item in filtered_items],
        "judgment_sources": [
            "answer_spine",
            "analyst_decision_logic",
            "memo_obligations",
            "analyst_quantity_binding_report",
            "writer_guidance_packet",
        ],
    }


def _model_visible_evidence_items(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in _list(packet.get("evidence_items"))
        if isinstance(item, dict) and _evidence_item_model_visible(item)
    ]


def _filtered_evidence_items(packet: dict[str, Any], visible_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    visible_ids = {str(item.get("item_id") or "") for item in visible_items if isinstance(item, dict)}
    return [
        item
        for item in _list(packet.get("evidence_items"))
        if isinstance(item, dict) and str(item.get("item_id") or "") not in visible_ids
    ]


def _evidence_item_model_visible(item: dict[str, Any]) -> bool:
    return bool(item.get("must_use")) or str(item.get("obligation_level") or "") == "must_include"


def _contains_generic_judgment(value: Any) -> bool:
    text = str(value or "").lower()
    if any(pattern in text for pattern in GENERIC_JUDGMENT_PATTERNS):
        return True
    if isinstance(value, dict):
        return any(_contains_generic_judgment(row) for row in value.values())
    if isinstance(value, list):
        return any(_contains_generic_judgment(row) for row in value)
    return False


def _reader_facing_judgment_surface(interface: dict[str, Any]) -> dict[str, Any]:
    """Return generated judgment fields, excluding internal writer instructions."""

    return {
        "bottom_line": interface.get("bottom_line"),
        "answer_frame": interface.get("answer_frame"),
        "support_that_drives_answer": _claim_surface(interface.get("support_that_drives_answer")),
        "counterweights_and_disposition": [
            {
                "claim": row.get("claim"),
                "disposition": row.get("disposition"),
                "disposition_rationale": row.get("disposition_rationale"),
            }
            for row in _list(interface.get("counterweights_and_disposition"))
            if isinstance(row, dict)
        ],
        "scope_boundaries": _claim_surface(interface.get("scope_boundaries")),
        "decision_cruxes": _claim_surface(interface.get("decision_cruxes")),
        "practical_implications": interface.get("practical_implications"),
        "practical_implication_cards": [
            {
                "implication_type": row.get("implication_type"),
                "statement": row.get("statement"),
            }
            for row in _list(interface.get("practical_implication_cards"))
            if isinstance(row, dict)
        ],
        "critique_writer_guidance": interface.get("critique_writer_guidance"),
    }


def _claim_surface(rows: Any) -> list[dict[str, Any]]:
    return [
        {
            "claim": row.get("claim"),
            "why_it_matters": row.get("why_it_matters"),
            "answer_relation": row.get("answer_relation"),
        }
        for row in _list(rows)
        if isinstance(row, dict)
    ]


def _informative_source_appraisal(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    if str(row.get("decision_directness") or "").strip() not in {"", "unknown"}:
        return True
    return bool(
        _list(row.get("evidence_proximity"))
        or _list(row.get("recommended_uses"))
        or _list(row.get("source_use_warnings"))
        or _list(row.get("interpretation_caveats"))
        or _dict(row.get("allowed_wording"))
    )


def _first_claim(visible_items: list[dict[str, Any]], roles: set[str]) -> str:
    for item in visible_items:
        if isinstance(item, dict) and str(item.get("role") or "") in roles:
            claim = str(item.get("reader_claim") or "").strip()
            if claim:
                return claim
    return ""


def _first_item(items: list[dict[str, Any]]) -> dict[str, Any]:
    return items[0] if items else {}


def _clean_answer_text(value: Any) -> str:
    text = _short_text(str(value or ""), 700)
    text = re.sub(r"^The evidence supports a bounded answer to ['\"][^'\"]+['\"]:\s*", "", text)
    text = re.sub(r"^The evidence supports a bounded answer to [^:]{1,240}:\s*", "", text)
    text = re.sub(r"^The evidence supports a bounded answer:\s*", "", text)
    text = re.sub(
        r"\b(main|primary|central) limiting consideration is ([A-Z])",
        lambda match: f"{match.group(1)} limiting consideration is that {match.group(2).lower()}",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _strip_terminal_punctuation(text: str) -> str:
    return re.sub(r"[.。؛;:\s]+$", "", str(text or "").strip())


def _content_terms(text: str) -> set[str]:
    stop = {
        "about",
        "after",
        "against",
        "also",
        "and",
        "are",
        "answer",
        "associated",
        "between",
        "claim",
        "decision",
        "does",
        "evidence",
        "for",
        "from",
        "into",
        "not",
        "other",
        "provides",
        "significant",
        "source",
        "sources",
        "that",
        "the",
        "their",
        "this",
        "using",
        "with",
        "without",
    }
    return {
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", str(text).lower())
        if token not in stop
    }


def _source_labels(item: dict[str, Any]) -> list[str]:
    return _dedupe([*_string_list(item.get("source_labels")), str(item.get("source_label") or "").strip()])


def _quantity_values(value: Any) -> list[dict[str, str]]:
    rows = []
    for row in _list(value):
        if isinstance(row, dict):
            quantity = str(row.get("value") or "").strip()
            interpretation = str(row.get("interpretation") or "").strip()
        else:
            quantity = str(row or "").strip()
            interpretation = ""
        if quantity:
            rows.append({"value": quantity, "interpretation": interpretation})
    return rows
