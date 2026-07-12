from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_obligations import required_memo_obligations
from epistemic_case_mapper.map_briefing_writer_decision_interface import (
    build_writer_decision_interface,
    build_writer_model_context,
)


def build_memo_ready_packet_synthesis_prompt(memo_ready_packet: dict[str, Any]) -> str:
    writer_packet = memo_ready_packet.get("writer_packet") if isinstance(memo_ready_packet, dict) else None
    if isinstance(memo_ready_packet, dict) and memo_ready_packet.get("evidence_items"):
        return build_writer_packet_synthesis_prompt(_dict(writer_packet), memo_ready_packet=memo_ready_packet)
    return (
        "Memo-ready packet synthesis prompt unavailable.\n"
        "Active memo synthesis requires memo_ready_packet.evidence_items so the writer model context can be compiled without raw packet or audit-only fields.\n"
    )


def build_writer_packet_synthesis_prompt(
    writer_packet: dict[str, Any],
    *,
    memo_ready_packet: dict[str, Any] | None = None,
) -> str:
    if not (isinstance(memo_ready_packet, dict) and memo_ready_packet.get("evidence_items")):
        return (
            "Decision-writer packet synthesis prompt unavailable.\n"
            "Active memo synthesis requires a memo-ready packet with evidence_items so the writer model context can be compiled without audit-only fields.\n"
        )
    writing_interface = build_writer_decision_interface(memo_ready_packet)
    narrative_blueprint = build_memo_narrative_blueprint(memo_ready_packet or {}, writing_interface=writing_interface)
    model_context = build_writer_model_context(writing_interface)
    blueprint_context: dict[str, Any] = narrative_blueprint
    if _list(_dict(model_context.get("reasoning_hierarchy")).get("reasoning_moves")):
        blueprint_context = {
            "schema_id": "memo_narrative_blueprint_reference_v1",
            "status": "superseded_by_reasoning_hierarchy",
            "decision_question": narrative_blueprint.get("decision_question"),
            "note": "Use writer_model_context.reasoning_hierarchy as the organizing spine; this placeholder preserves the prompt section without duplicating evidence.",
        }
    return (
        "You are a senior decision analyst. Write a coherent decision memo from the writer model context.\n"
        "The writer model context is the complete model-visible evidence and judgment record. It already reflects upstream evidence selection, quantity binding, and analyst planning.\n"
        "Write for a human decision-maker; do not expose packet structure.\n"
        "Use decision_evidence_table as the primary evidence surface, adaptive_memo_outline as the section plan, reasoning_hierarchy as the organizing spine, and decision_boundary_source_contract as the guide for boundaries, source roles, source-specific cautions, and quantity priorities. Use the narrative blueprint as secondary orientation. The adaptive outline's must-write cards are the retention contract for synthesis: satisfy each card in natural prose when it affects the decision read. Merge related cards into the same paragraph when that reads better.\n\n"
        "Rules:\n"
        "- Start the first paragraph with a direct bottom-line answer to the decision question, using answer_frame.direct_answer from the writer model context when present.\n"
        "- Scope the opening answer using answer_frame.scope_note and answer_frame.main_uncertainty when they are present.\n"
        "- State the confidence level and main reason for uncertainty using answer_frame.confidence_basis when the writer model context supplies it.\n"
        "- Use adaptive_memo_outline.sections as the memo's visible section sequence and section-title source when it is present.\n"
        "- Use decision_boundary_source_contract.boundary_obligations to make the answer's population, dose, endpoint, setting, counterweight, crux, or missing-evidence boundaries visible when the contract supplies them.\n"
        "- Use decision_boundary_source_contract.source_use_cards to cite sources for their specific memo job rather than citing every source generically.\n"
        "- Use decision_boundary_source_contract.quantity_priority_cards to decide which retained quantities deserve main-prose interpretation first.\n"
        "- Follow decision_boundary_source_contract.language_discipline when it gives source-appraisal cautions about association, causality, quality, or interpretation.\n"
        "- Satisfy every adaptive_memo_outline.must_write_cards entry in natural prose; use the cards to preserve required evidence, not to create checklist rhythm.\n"
        "- When a must-write card has multiple quantities_to_keep_together, write those quantities in the same sentence or adjacent clause so the model does not split paired estimates from their interval, denominator, or interpretation.\n"
        "- Use only facts, quantities, and source labels present in the writer model context.\n"
        "- Use only quantities listed inside adaptive_memo_outline.must_write_cards, quantity_anchors, decision_evidence_table.quantities, or practical_implication_cards.\n"
        "- When a quantity value is ambiguous by itself, use its interpretation wording from quantity_anchors or decision_evidence_table.quantities.\n"
        "- Cite the source label attached to the evidence unit or quantity that supports the sentence.\n"
        "- Use source_appraisal_summary and source_appraisal_note to calibrate wording, confidence, and source weight.\n"
        "- Explain what the most important quantities mean for the decision; omit lower-value numbers when prose would become cluttered.\n"
        "- Use a longer memo when the packet has many load-bearing units; do not compress away decision-relevant quantities, caveats, source-appraisal constraints, or counterweights just to stay brief.\n"
        "- Weigh support against counterweights and scope boundaries instead of listing evidence mechanically.\n"
        "- Use the hierarchy's counterweight, scope, and crux moves to explain whether counterevidence overturns, weakens, bounds, or contextualizes the answer.\n"
        "- Use critique_writer_guidance to avoid answer-frame mistakes, source-quality omissions, and synthesis traps identified during packet critique.\n"
        "- Use practical_implication_cards to make the final section specific about default application, exceptions, scope, and cruxes.\n"
        "- Treat cruxes and subgroup signals as calibration unless the packet says they change the default answer.\n"
        "- Follow do_not_overstate constraints; use calibrated language for causal, safety, and confidence claims.\n"
        "- Include a concise practical implication.\n"
        "- Let reasoning_hierarchy determine the sequence of reasoning moves; it is a compact projection of existing packet judgments, not a separate evidence source.\n"
        "- Use source_weighting sections from adaptive_memo_outline to explain source quality, directness, or measurement limits when those limits affect confidence.\n"
        "- Write from the blueprint's reasoning moves rather than from the ledger's order.\n"
        "- Avoid checklist rhythm: do not make source labels or obligation statements the repeated grammatical subject.\n"
        "- Turn bare statistics into decision interpretation before moving to the next point.\n"
        "- Use natural Markdown; do not use To/From/Subject memo headers.\n\n"
        "Narrative blueprint:\n"
        f"{json.dumps(blueprint_context, indent=2, ensure_ascii=False)}\n\n"
        "Writer model context:\n"
        f"{json.dumps(model_context, indent=2, ensure_ascii=False)}\n"
    )


def build_memo_narrative_blueprint(
    memo_ready_packet: dict[str, Any],
    *,
    writing_interface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(writing_interface, dict) and writing_interface.get("schema_id") == "writer_decision_interface_v1":
        return _writer_interface_narrative_blueprint(writing_interface)
    interface = (
        writing_interface
        if isinstance(writing_interface, dict)
        else (_dict(memo_ready_packet.get("writer_packet")) or memo_ready_packet)
    )
    obligations = required_memo_obligations(memo_ready_packet)
    spine = _dict(interface.get("answer_spine") or memo_ready_packet.get("answer_spine"))
    logic = _dict(interface.get("decision_logic") or memo_ready_packet.get("analyst_decision_logic"))
    argument_plan = _list(interface.get("analyst_argument_plan") or interface.get("argument_plan"))
    grouped = _group_obligations(obligations)
    moves = [
        _blueprint_move(
            "bottom_line",
            "Open with the answer, confidence, and the main reason the answer is bounded.",
            [
                _clean_answer_text(spine.get("default_read") or spine.get("bounded_answer") or logic.get("bounded_bottom_line")),
                _clean_answer_text(spine.get("why_this_read") or logic.get("support_summary")),
            ],
            source_types=("must_weigh_support", "must_interpret_quantity"),
            grouped=grouped,
            limit=3,
        ),
        _blueprint_move(
            "main_support",
            "Explain the strongest support and interpret the load-bearing quantities.",
            [],
            source_types=("must_weigh_support", "must_interpret_quantity"),
            grouped=grouped,
            limit=6,
        ),
        _blueprint_move(
            "counterweights",
            "Give the strongest counterweights their force, then explain whether they change the answer.",
            [_clean_answer_text(logic.get("counterweight_weighting"))],
            source_types=("must_weigh_counterweight", "must_weigh_omitted_evidence"),
            grouped=grouped,
            limit=5,
        ),
        _blueprint_move(
            "scope_and_cruxes",
            "State the boundaries, cruxes, or assumptions that would change the answer.",
            _string_list(logic.get("scope_boundaries")) + _string_list(logic.get("reconciled_cruxes")),
            source_types=("must_bound_scope", "must_address_crux"),
            grouped=grouped,
            limit=6,
        ),
        _blueprint_move(
            "practical_implication",
            "Translate the evidence into the next decision action or monitoring implication.",
            _string_list(logic.get("practical_implications")),
            source_types=(),
            grouped=grouped,
            limit=0,
        ),
    ]
    return {
        "schema_id": "memo_narrative_blueprint_v1",
        "decision_question": memo_ready_packet.get("decision_question") or interface.get("decision_question"),
        "opening_answer": _clean_answer_text(
            spine.get("default_read") or spine.get("bounded_answer") or logic.get("bounded_bottom_line")
        ),
        "confidence": spine.get("confidence") or logic.get("confidence"),
        "moves": [move for move in moves if move.get("guidance") or move.get("required_points")],
        "argument_plan_hints": _compact_argument_plan(argument_plan),
        "prose_discipline": [
            "Use the moves as a reasoning sequence, not as visible labels unless the headings fit naturally.",
            "Connect support, counterweight, and scope in sentences that explain why they matter for the decision.",
            "Use adaptive must-write cards only to check retention after drafting.",
        ],
    }


def _writer_interface_narrative_blueprint(writer_interface: dict[str, Any]) -> dict[str, Any]:
    support = _list(writer_interface.get("support_that_drives_answer"))
    counterweights = _list(writer_interface.get("counterweights_and_disposition"))
    scope = _list(writer_interface.get("scope_boundaries"))
    cruxes = _list(writer_interface.get("decision_cruxes"))
    implications = _string_list(writer_interface.get("practical_implications"))
    return {
        "schema_id": "memo_narrative_blueprint_v1",
        "decision_question": writer_interface.get("decision_question"),
        "opening_answer": _clean_answer_text(writer_interface.get("bottom_line")),
        "confidence": writer_interface.get("confidence"),
        "moves": [
            {
                "move": "bottom_line",
                "writing_goal": "Open with the answer, confidence, and the main reason the answer is bounded.",
                "guidance": [_clean_answer_text(writer_interface.get("bottom_line"))],
                "required_points": _blueprint_points(support[:3]),
            },
            {
                "move": "main_support",
                "writing_goal": "Explain the strongest support and interpret the load-bearing quantities.",
                "guidance": [],
                "required_points": _blueprint_points(support),
            },
            {
                "move": "counterweights",
                "writing_goal": "Give the strongest counterweights their force, then explain whether they change the answer.",
                "guidance": [],
                "required_points": _blueprint_points(counterweights),
            },
            {
                "move": "scope_and_cruxes",
                "writing_goal": "State the boundaries, cruxes, or assumptions that would change the answer.",
                "guidance": [],
                "required_points": _blueprint_points([*scope, *cruxes]),
            },
            {
                "move": "practical_implication",
                "writing_goal": "Translate the evidence into the next decision action or monitoring implication.",
                "guidance": implications,
                "required_points": [],
            },
        ],
        "argument_plan_hints": [],
        "prose_discipline": [
            "Use the moves as a reasoning sequence, not as visible labels unless the headings fit naturally.",
            "Connect support, counterweight, and scope in sentences that explain why they matter for the decision.",
            "Use adaptive must-write cards only to check retention after drafting.",
        ],
    }


def _blueprint_points(items: list[Any]) -> list[dict[str, Any]]:
    points = []
    for item in items:
        if not isinstance(item, dict):
            continue
        points.append(
            {
                "item_id": item.get("item_id"),
                "point": _short_text(item.get("claim")),
                "source_labels": _string_list(item.get("source_labels")),
                "quantities": _quantity_values(item.get("quantities")),
                "disposition": item.get("disposition"),
            }
        )
    return points


def _obligation_ledger(obligations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "obligation_id": obligation.get("obligation_id"),
            "obligation_type": obligation.get("obligation_type"),
            "role": obligation.get("role"),
            "statement": obligation.get("statement"),
            "prose_instruction": obligation.get("prose_instruction"),
            "source_labels": obligation.get("source_labels", []),
            "quantities": obligation.get("quantities", []),
        }
        for obligation in obligations
    ]


def _blueprint_move(
    move: str,
    writing_goal: str,
    guidance: list[str],
    *,
    source_types: tuple[str, ...],
    grouped: dict[str, list[dict[str, Any]]],
    limit: int,
) -> dict[str, Any]:
    rows = [row for obligation_type in source_types for row in grouped.get(obligation_type, [])][:limit]
    return {
        "move": move,
        "writing_goal": writing_goal,
        "guidance": [_short_text(row) for row in guidance if _short_text(row)],
        "required_points": [_obligation_point(row) for row in rows],
    }


def _obligation_point(obligation: dict[str, Any]) -> dict[str, Any]:
    return {
        "obligation_id": obligation.get("obligation_id"),
        "point": _short_text(obligation.get("statement") or obligation.get("audit_claim")),
        "source_labels": _string_list(obligation.get("source_labels")),
        "quantities": _quantity_values(obligation.get("quantities")),
        "prose_instruction": _short_text(obligation.get("prose_instruction")),
    }


def _group_obligations(obligations: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for obligation in obligations:
        obligation_type = str(obligation.get("obligation_type") or "optional_context")
        grouped.setdefault(obligation_type, []).append(obligation)
    return grouped


def _compact_argument_plan(argument_plan: list[Any]) -> list[dict[str, Any]]:
    rows = []
    for row in argument_plan[:6]:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "step_id": row.get("step_id"),
                "section": row.get("section"),
                "writing_goal": _short_text(row.get("writing_goal")),
                "transition_from_previous": _short_text(row.get("transition_from_previous")),
                "source_labels": _string_list(row.get("source_labels")),
            }
        )
    return rows


def _clean_answer_text(value: Any) -> str:
    text = _short_text(value, limit=500)
    if not text:
        return ""
    text = re.sub(r"^The evidence supports a bounded answer to ['\"][^'\"]+['\"]:\s*", "", text)
    text = re.sub(r"^The evidence supports a bounded answer:\s*", "", text)
    text = text.replace("...", ".")
    return re.sub(r"\s+", " ", text).strip()


def _short_text(value: Any, *, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "."


def _quantity_values(value: Any) -> list[str]:
    rows = []
    for row in _list(value):
        if isinstance(row, dict):
            quantity = str(row.get("value") or "").strip()
        else:
            quantity = str(row or "").strip()
        if quantity and quantity not in rows:
            rows.append(quantity)
    return rows


def _string_list(value: Any) -> list[str]:
    rows = []
    for row in _list(value):
        text = str(row or "").strip()
        if text and text not in rows:
            rows.append(text)
    return rows


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
