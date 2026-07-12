from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_obligations import required_memo_obligations


def build_memo_ready_packet_synthesis_prompt(memo_ready_packet: dict[str, Any]) -> str:
    writer_packet = memo_ready_packet.get("writer_packet") if isinstance(memo_ready_packet, dict) else None
    if isinstance(writer_packet, dict) and writer_packet.get("evidence_units"):
        return build_writer_packet_synthesis_prompt(writer_packet, memo_ready_packet=memo_ready_packet)
    return (
        "You are a senior decision analyst. Write a coherent decision memo from the memo-ready evidence packet.\n"
        "Use the packet as the complete evidence record, but write for a human decision-maker rather than exposing packet structure.\n"
        "The packet may include memo_obligations, a decision_synthesis_contract, analyst_decision_logic, analyst_argument_plan, and memo_warning_packet. Treat these as guidance for what matters. Exercise analyst judgment about order, emphasis, merging, and compression.\n"
        "Write the best decision-ready answer the evidence supports. It is better to integrate a warning, caveat, or mandatory item by explaining its decision relevance than to restate it mechanically.\n"
        "Use memo_obligations as the writer-facing contract: satisfy required obligations in natural prose; use optional obligations only when they improve the decision read.\n"
        "Produce a decision read: answer, reason, counterweight, scope, uncertainty, and practical implication.\n\n"
        "Rules:\n"
        "- Start the first paragraph with a direct bottom-line answer to the decision question, using the packet's default read or bounded answer.\n"
        "- State the confidence level and main reason for uncertainty in the opening section when the packet supplies them.\n"
        "- Preserve load-bearing quantities, source attributions, strongest support, strongest counterweights, and scope boundaries.\n"
        "- You may merge, reorder, compress, or omit low-value detail when doing so improves the memo while preserving the evidence-backed answer.\n"
        "- Use source labels where they help the reader audit a load-bearing claim.\n"
        "- When quantity_tuples are present, use those tuple labels instead of pairing estimates and intervals yourself.\n"
        "- If a quantity is marked ambiguous or unpaired, describe only the explicit quantity context in the packet.\n"
        "- Explain what the key quantities mean for the decision.\n"
        "- Explain why the strongest support does or does not outweigh the strongest counterweight.\n"
        "- Name the conditions, subgroups, contexts, or assumptions that change the answer.\n"
        "- Include decision cruxes only when they sharpen the decision; translate uncertainty into a practical implication.\n"
        "- Use calibrated causal language, matching the strength of the source-backed claim.\n"
        "- Write reader-facing analysis; keep packet schemas, item IDs, validation, telemetry, obligations, warnings, and internal pipeline machinery out of the prose.\n"
        "- Make each point directly in natural analyst prose.\n"
        "- Use natural Markdown and choose headings that fit the decision question.\n\n"
        "Suggested memo shape when it fits the case:\n"
        "## Decision Brief\n"
        "## Why This Is the Best Current Read\n"
        "## What Could Change the Answer\n"
        "## Decision-Relevant Evidence\n\n"
        "Memo-ready packet:\n"
        f"{json.dumps(memo_ready_packet, indent=2, ensure_ascii=False)}\n"
    )


def build_writer_packet_synthesis_prompt(
    writer_packet: dict[str, Any],
    *,
    memo_ready_packet: dict[str, Any] | None = None,
) -> str:
    obligations = required_memo_obligations(memo_ready_packet or {})
    writing_interface = _writing_interface(writer_packet, memo_ready_packet or {})
    narrative_blueprint = build_memo_narrative_blueprint(memo_ready_packet or {}, writing_interface=writing_interface)
    obligation_ledger = [
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
    return (
        "You are a senior decision analyst. Write a coherent decision memo from the source-bound writer packet writing interface.\n"
        "The writing interface is the complete writing interface and memo-facing evidence record. It already reflects upstream evidence selection, quantity binding, and analyst planning.\n"
        "Write for a human decision-maker; do not expose packet structure.\n"
        "Use the narrative blueprint as the memo's organizing spine. The required obligation ledger below is a retention checklist, not an outline: satisfy each item in natural prose when it affects the decision read. Merge related obligations into the same paragraph when that reads better.\n\n"
        "Rules:\n"
        "- Start the first paragraph with a direct bottom-line answer to the decision question, using the bounded answer/default read from the writing interface.\n"
        "- State the confidence level and main reason for uncertainty in the opening section when the writing interface supplies them.\n"
        "- Use only facts, quantities, and source labels present in the writing interface.\n"
        "- Use only quantities listed inside evidence_items.quantities or the required obligation ledger.\n"
        "- Cite the source_display or source_label attached to the evidence unit or quantity that supports the sentence.\n"
        "- Explain what the most important quantities mean for the decision; omit lower-value numbers when prose would become cluttered.\n"
        "- Use a longer memo when the packet has many load-bearing units; do not compress away decision-relevant quantities, caveats, source-appraisal constraints, or counterweights just to stay brief.\n"
        "- Weigh support against counterweights and scope boundaries instead of listing evidence mechanically.\n"
        "- Use each evidence unit's source_appraisal, allowed_wording, and source_use_warnings to calibrate verbs, causal language, and uncertainty.\n"
        "- Treat cruxes and subgroup signals as calibration unless the packet says they change the default answer.\n"
        "- Follow do_not_overstate constraints; use calibrated language for causal, safety, and confidence claims.\n"
        "- Include a concise practical implication.\n"
        "- Write from the blueprint's reasoning moves rather than from the ledger's order.\n"
        "- Avoid checklist rhythm: do not make source labels or obligation statements the repeated grammatical subject.\n"
        "- Turn bare statistics into decision interpretation before moving to the next point.\n"
        "- Use natural Markdown and choose headings that fit the decision question.\n\n"
        "Narrative blueprint:\n"
        f"{json.dumps(narrative_blueprint, indent=2, ensure_ascii=False)}\n\n"
        "Required obligation ledger:\n"
        f"{json.dumps(obligation_ledger, indent=2, ensure_ascii=False)}\n\n"
        "Suggested memo shape when it fits the case:\n"
        "## Decision Brief\n"
        "## Why This Is the Best Current Read\n"
        "## What Could Change the Answer\n"
        "## Practical Implications\n\n"
        "Source-bound writing interface:\n"
        f"{json.dumps(writing_interface, indent=2, ensure_ascii=False)}\n"
    )


def build_memo_narrative_blueprint(
    memo_ready_packet: dict[str, Any],
    *,
    writing_interface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    interface = writing_interface if isinstance(writing_interface, dict) else _writing_interface(
        _dict(memo_ready_packet.get("writer_packet")), memo_ready_packet
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
            "Use the required obligation ledger only to check retention after drafting.",
        ],
    }


def _writing_interface(writer_packet: dict[str, Any], memo_ready_packet: dict[str, Any]) -> dict[str, Any]:
    if (
        isinstance(memo_ready_packet, dict)
        and memo_ready_packet.get("evidence_items")
        and str(memo_ready_packet.get("method") or "") == "global_decision_writer_packet_adapter"
    ):
        return {
            "schema_id": "source_bound_writing_interface_v1",
            "decision_question": memo_ready_packet.get("decision_question"),
            "answer_spine": memo_ready_packet.get("answer_spine", {}),
            "decision_memo_contract": memo_ready_packet.get("decision_memo_contract", {}),
            "evidence_items": memo_ready_packet.get("evidence_items", []),
            "source_trail": memo_ready_packet.get("source_trail", []),
            "writer_packet_writeability_report": memo_ready_packet.get("writer_packet_writeability_report", {}),
            "decision_logic": memo_ready_packet.get("analyst_decision_logic", {}),
            "analyst_argument_plan": memo_ready_packet.get("analyst_argument_plan", []),
        }
    return writer_packet


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
