from __future__ import annotations

import json
from typing import Any

from epistemic_case_mapper.map_briefing_canonical_decision_writer_packet import build_canonical_decision_writer_packet


def build_memo_ready_packet_synthesis_prompt(memo_ready_packet: dict[str, Any]) -> str:
    if isinstance(memo_ready_packet, dict) and memo_ready_packet.get("evidence_items"):
        canonical = _dict(memo_ready_packet.get("canonical_decision_writer_packet")) or build_canonical_decision_writer_packet(memo_ready_packet)
        return build_canonical_decision_writer_packet_synthesis_prompt(canonical)
    return (
        "Memo-ready packet synthesis prompt unavailable.\n"
        "Active memo synthesis requires memo_ready_packet.evidence_items so a canonical decision writer packet can be compiled without raw packet or audit-only fields.\n"
    )


def build_writer_packet_synthesis_prompt(
    writer_packet: dict[str, Any],
    *,
    memo_ready_packet: dict[str, Any] | None = None,
) -> str:
    if isinstance(memo_ready_packet, dict) and memo_ready_packet.get("evidence_items"):
        canonical = _dict(memo_ready_packet.get("canonical_decision_writer_packet")) or build_canonical_decision_writer_packet(memo_ready_packet)
        return build_canonical_decision_writer_packet_synthesis_prompt(canonical)
    return (
        "Decision-writer packet synthesis prompt unavailable.\n"
        "Active synthesis now requires memo_ready_packet.evidence_items so the canonical decision writer packet is the sole semantic handoff.\n"
    )


def build_canonical_decision_writer_packet_synthesis_prompt(canonical_packet: dict[str, Any]) -> str:
    packet = _canonical_packet_for_prompt(canonical_packet)
    return (
        "You are a senior decision analyst. Write a decision-ready memo from the canonical decision writer packet.\n"
        "The packet is the sole semantic handoff from upstream analysis. It now leads with source_weight_judgments and evidence_weighted_argument_spine so the memo can explain why the evidence hierarchy implies the answer.\n"
        "Write for a human decision-maker. Make the answer crisp before explaining the evidence, and make each paragraph do one distinct reasoning job.\n\n"
        "Required visible structure:\n"
        "# Decision Memo: <short title>\n"
        "**Decision Question:** <question>\n"
        "**Bottom Line:** <direct answer with scope and confidence>\n"
        "## Why This Is the Best Current Read\n"
        "## What Could Change or Bound the Answer\n"
        "## Practical Implication\n\n"
        "Writing rules:\n"
        "- Use source_weight_judgments to explain why sources drive, calibrate, bound, or contextualize the answer.\n"
        "- Use evidence_weighted_argument_spine as the primary writing plan; follow its section_plan and primary_section fields to decide where each evidence step belongs.\n"
        "- Write each section around its owned spine steps. If a later section needs evidence already used earlier, make a short cross-reference and add the new decision function instead of repeating the earlier sentence.\n"
        "- Use decision_brief_skeleton and decision_answer_classification to state the bottom-line answer, scope, confidence, and unsupported options.\n"
        "- Use decision_answer_classification in the Bottom Line: state the supported answer shape or option directly, name the scope, and state any named options the evidence does not support at that scope.\n"
        "- Use source_weighted_answer_frame and priority_evidence as supporting detail for the argument spine, not as a second outline.\n"
        "- Use organized_evidence_inventory as the complete memo-facing evidence record; draw from non-priority items only when they add practical framing, comparators, scope, or interpretive context.\n"
        "- Interpret important quantities in decision terms.\n"
        "- Use counterweight_dispositions to say whether each major limiting point overturns, weakens, bounds, explains, or creates a crux for the answer. Preserve uncertainty when the packet says a point may only bound the answer.\n"
        "- Use scope_boundaries and decision_cruxes to state where the answer applies and what would change it.\n"
        "- Use source_weight_notes when source type, directness, or limitations affect confidence.\n"
        "- Preserve each mandatory_retention_checklist item in natural prose.\n"
        "- Cite source_ids in brackets near the claims they support; presentation code will replace them with reader-facing source names.\n"
        "- Keep source IDs and quantities attached to their claims.\n"
        "- Write naturally; do not expose packet keys, IDs other than source_ids, validation machinery, or audit language.\n"
        "- Do not include a sources section; the final source list is added deterministically.\n\n"
        "Canonical decision writer packet:\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n"
    )


def _canonical_packet_for_prompt(canonical_packet: dict[str, Any]) -> dict[str, Any]:
    packet = canonical_packet if isinstance(canonical_packet, dict) else {}
    ordered_keys = [
        "schema_id",
        "decision_question",
        "decision_brief_skeleton",
        "decision_answer_classification",
        "source_weight_judgments",
        "source_weight_judgment_report",
        "evidence_weighted_argument_spine",
        "source_weighted_answer_frame",
        "priority_evidence",
        "organized_evidence_inventory",
        "counterweight_dispositions",
        "scope_boundaries",
        "decision_cruxes",
        "source_weight_notes",
        "analyst_reasoning_frame",
        "mandatory_retention_checklist",
        "citation_registry",
    ]
    return {key: packet[key] for key in ordered_keys if key in packet}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
