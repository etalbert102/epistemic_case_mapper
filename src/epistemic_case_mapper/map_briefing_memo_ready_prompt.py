from __future__ import annotations

import json
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
        "The required obligation ledger below is a writing checklist: satisfy each item in natural prose when it affects the decision read. Merge related obligations into the same paragraph when that reads better.\n\n"
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
        "- Use natural Markdown and choose headings that fit the decision question.\n\n"
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
