from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.map_briefing_analytical_balance_contract import build_analytical_balance_contract
from epistemic_case_mapper.map_briefing_decision_interpretation_plan import build_decision_interpretation_plan
from epistemic_case_mapper.map_briefing_memo_obligations import required_memo_obligations
from epistemic_case_mapper.map_briefing_reader_brief_plan import build_reader_brief_plan
from epistemic_case_mapper.map_briefing_reader_language import project_reader_language_for_model
from epistemic_case_mapper.map_briefing_source_identity import project_sources_to_ids_for_model
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
    source_identity_trail = _list(writing_interface.get("_source_identity_trail")) or _list(writing_interface.get("source_trail"))
    model_context["analytical_balance_contract"] = project_sources_to_ids_for_model(
        build_analytical_balance_contract(memo_ready_packet),
        source_identity_trail,
    )
    model_context["mandatory_evidence_ledger"] = project_sources_to_ids_for_model(
        _mandatory_evidence_ledger(memo_ready_packet),
        source_identity_trail,
    )
    model_context["required_memo_obligations"] = project_sources_to_ids_for_model(
        _required_memo_obligation_context(memo_ready_packet),
        source_identity_trail,
    )
    model_context = _strict_ledger_writer_context(model_context)
    blueprint_context: dict[str, Any] = project_sources_to_ids_for_model(
        narrative_blueprint,
        source_identity_trail,
    )
    if _list(_dict(model_context.get("reasoning_hierarchy")).get("reasoning_moves")):
        blueprint_context = {
            "schema_id": "memo_narrative_blueprint_reference_v1",
            "status": "superseded_by_reasoning_hierarchy",
            "decision_question": narrative_blueprint.get("decision_question"),
            "note": "Use writer_model_context.reasoning_hierarchy as the organizing spine; this placeholder preserves the prompt section without duplicating evidence.",
        }
    model_context["decision_interpretation_plan"] = build_decision_interpretation_plan(model_context)
    model_context["reader_brief_plan"] = build_reader_brief_plan(model_context)
    model_context = project_reader_language_for_model(model_context)
    blueprint_context = project_reader_language_for_model(blueprint_context)
    return (
        "You are a senior decision analyst. Write a coherent decision memo from the writer model context.\n"
        "The writer model context is the complete model-visible evidence and judgment record. It already reflects upstream evidence selection, quantity binding, and analyst planning.\n"
        "Write for a human decision-maker; do not expose packet structure.\n"
        "Use reader_brief_plan as the writing plan. Use decision_evidence_table, reasoning_hierarchy, analytical_balance_contract, and decision_boundary_source_contract to support that plan. Use mandatory_evidence_ledger as the non-negotiable retention check after drafting, not as the memo outline. Merge related ledger rows into the same paragraph when that reads better.\n\n"
        "Required visible structure:\n"
        "# Decision Memo: <short title>\n"
        "**Decision Question:** <question>\n"
        "**Bottom Line:** <direct answer>\n"
        "## Why This Is the Best Current Read\n"
        "## What Could Change or Bound the Answer\n"
        "## Practical Implication\n\n"
        "Non-negotiable retention rule:\n"
        "- Every row in mandatory_evidence_ledger must be represented in the memo.\n"
        "- Use at least one source_id from each ledger row in brackets in the sentence or paragraph representing it; presentation code will replace source IDs with reader-facing source names.\n"
        "- Preserve every value in quantities_to_preserve unless it is a pure duplicate of another value in the same row.\n"
        "- If several quantities belong together, keep them in the same sentence or adjacent clause.\n"
        "- Do not hide required quantities in a sources section; write them where they support the reasoning.\n\n"
        "Analyst writing rules:\n"
        "- Start the bottom line with a direct answer to the decision question, using answer_frame.direct_answer from the writer model context when present.\n"
        "- Scope the opening answer using answer_frame.scope_note and answer_frame.main_uncertainty when they are present.\n"
        "- State the confidence level and main reason for uncertainty using answer_frame.confidence_basis when the writer model context supplies it.\n"
        "- Use calibrated confidence language: prefer bounded, low-concern, compatible with, not associated with, or does not clearly show over absolute safety, safe limit, proven harmless, or high-confidence unless the context explicitly warrants that wording.\n"
        "- Use decision_boundary_source_contract.boundary_obligations to make the answer's population, dose, endpoint, setting, counterweight, crux, or missing-evidence boundaries visible when the contract supplies them.\n"
        "- Use decision_boundary_source_contract.source_use_cards to cite sources for their specific memo job rather than citing every source generically.\n"
        "- Use decision_boundary_source_contract.quantity_priority_cards to decide which retained quantities deserve main-prose interpretation first.\n"
        "- Follow decision_boundary_source_contract.language_discipline when it gives source-appraisal cautions about association, causality, quality, or interpretation.\n"
        "- Use analytical_balance_contract.required_balance_cards to ensure high-priority support, counterweight, scope, or crux evidence is visibly weighed even when it was not mandatory in the original packet.\n"
        "- Use analytical_balance_contract.answer_classification to answer the exact decision frame; when the question offers named options, state which option the evidence supports and which options it does not support at the stated scope.\n"
        "- Use analytical_balance_contract.scope_dose_guardrails to distinguish broad decision-scope quantities from study-, source-, subgroup-, or setting-specific quantities.\n"
        "- Use analytical_balance_contract.targeted_quantity_requirements to include the support, counterweight, boundary, or uncertainty quantities that are load-bearing for the decision read.\n"
        "- Use analytical_balance_contract.causal_language_discipline to keep causal wording calibrated to the source appraisal and evidence type.\n"
        "- Use analytical_balance_contract.subgroup_boundary_cards to state subgroup, population, setting, or applicability boundaries when they affect how the answer should be used.\n"
        "- For every required counterweight in analytical_balance_contract, explain whether it overturns, weakens, bounds, or contextualizes the answer.\n"
        "- Use analytical_balance_contract.evidence_type_contrasts to separate evidence types when they answer different subquestions.\n"
        "- Satisfy adaptive_memo_outline.must_write_cards in natural prose when they add useful routing detail; mandatory_evidence_ledger is the primary retention contract.\n"
        "- Satisfy required_memo_obligations when they add source warnings or critique-derived guidance not already represented in mandatory_evidence_ledger.\n"
        "- When a must-write card has multiple quantities_to_keep_together, write those quantities in the same sentence or adjacent clause so the model does not split paired estimates from their interval, denominator, or interpretation.\n"
        "- Use only facts, quantities, and source IDs present in the writer model context.\n"
        "- Use only quantities listed inside adaptive_memo_outline.must_write_cards, quantity_anchors, decision_evidence_table.quantities, or practical_implication_cards.\n"
        "- When a quantity value is ambiguous by itself, use its interpretation wording from quantity_anchors or decision_evidence_table.quantities.\n"
        "- Cite the source_id attached to the evidence unit or quantity that supports the sentence; presentation code will replace source IDs with reader-facing source names.\n"
        "- Use source_appraisal_summary and source_appraisal_note to calibrate wording, confidence, and source weight.\n"
        "- Explain what the required quantities mean for the decision; optional lower-value numbers may be omitted when prose would become cluttered.\n"
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
        "- Use natural Markdown; do not use To/From/Subject memo headers.\n"
        "- Do not include a sources section; the final source list is added deterministically.\n\n"
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


def _strict_ledger_writer_context(model_context: dict[str, Any]) -> dict[str, Any]:
    outline = _dict(model_context.get("adaptive_memo_outline"))
    return {
        "schema_id": "writer_model_context_v1",
        "source_schema_id": model_context.get("source_schema_id"),
        "decision_question": model_context.get("decision_question"),
        "bottom_line": model_context.get("bottom_line"),
        "confidence": model_context.get("confidence"),
        "answer_frame": _dict(model_context.get("answer_frame")),
        "reasoning_hierarchy": _dict(model_context.get("reasoning_hierarchy")),
        "adaptive_memo_outline": {
            "schema_id": outline.get("schema_id"),
            "sections": _list(outline.get("sections")),
        },
        "decision_evidence_table": _list(model_context.get("decision_evidence_table"))[:8],
        "source_appraisal_summary": _list(model_context.get("source_appraisal_summary")),
        "decision_boundary_source_contract": _dict(model_context.get("decision_boundary_source_contract")),
        "analytical_balance_contract": _dict(model_context.get("analytical_balance_contract")),
        "quantity_anchors": _list(model_context.get("quantity_anchors")),
        "mandatory_evidence_ledger": _list(model_context.get("mandatory_evidence_ledger")),
        "required_memo_obligations": _list(model_context.get("required_memo_obligations")),
        "critique_writer_guidance": _dict(model_context.get("critique_writer_guidance")),
        "source_registry": _list(model_context.get("source_registry")),
    }


def _mandatory_evidence_ledger(memo_ready_packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in _list(memo_ready_packet.get("evidence_items")):
        if not isinstance(item, dict) or not item.get("must_use"):
            continue
        rows.append(
            {
                "item_id": item.get("item_id"),
                "role": item.get("role"),
                "claim": _short_text(item.get("reader_claim") or item.get("claim"), limit=640),
                "decision_relevance": _short_text(item.get("decision_relevance"), limit=360),
                "source_label": item.get("source_label"),
                "source_labels": _string_list(item.get("source_labels")),
                "quantities_to_preserve": _ledger_quantities(item),
            }
        )
    return rows


def _ledger_quantities(item: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for quantity in _list(item.get("quantities")):
        if not isinstance(quantity, dict):
            continue
        value = str(quantity.get("value") or "").strip()
        if not value:
            continue
        rows.append(
            {
                "value": value,
                "retention_phrase": str(quantity.get("retention_phrase") or "").strip(),
                "interpretation": _short_text(quantity.get("interpretation"), limit=240),
            }
        )
    return rows


def _required_memo_obligation_context(memo_ready_packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for obligation in required_memo_obligations(memo_ready_packet):
        if not isinstance(obligation, dict):
            continue
        rows.append(
            {
                "obligation_id": obligation.get("obligation_id"),
                "role": obligation.get("role"),
                "obligation_type": obligation.get("obligation_type"),
                "statement": _short_text(obligation.get("statement"), limit=520),
                "prose_instruction": _short_text(obligation.get("prose_instruction"), limit=280),
                "source_label": obligation.get("source_label"),
                "source_labels": _string_list(obligation.get("source_labels")),
                "quantities": _quantity_values(obligation.get("quantities")),
                "validation_terms": _string_list(obligation.get("validation_terms"))[:8],
            }
        )
    return rows


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
