from __future__ import annotations

import json
from typing import Any

from epistemic_case_mapper.map_briefing_canonical_decision_writer_packet import build_canonical_decision_writer_packet
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import dedupe as _dedupe
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import string_list as _string_list


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
    packet = _reader_synthesis_packet(canonical_packet)
    return (
        "You are a senior decision analyst. Write a decision-ready memo from the reader synthesis packet.\n"
        "The packet is a compact writing view derived from the canonical decision writer packet; use it as the sole semantic handoff for the memo.\n"
        "Write for a human decision-maker. Make the answer crisp before explaining the evidence, and make each paragraph do one distinct reasoning job.\n\n"
        "Required visible structure:\n"
        "# Decision Memo: <short title>\n"
        "**Decision Question:** <question>\n"
        "**Bottom Line:** <direct answer with scope and confidence>\n"
        "## Why This Is the Best Current Read\n"
        "## What Could Change or Bound the Answer\n"
        "## Practical Implication\n\n"
        "Writing rules:\n"
        "- Use source_weighting to explain why sources drive, calibrate, bound, or contextualize the answer.\n"
        "- Use argument_spine as the primary writing plan; follow its section_plan and primary_section fields to decide where each evidence step belongs.\n"
        "- Treat section_writing_packets as the primary section-local context. Each section packet contains the argument steps, evidence rows, source roles, and retention requirements for that section.\n"
        "- Write each section around its owned spine steps. If a later section needs evidence already used earlier, make a short cross-reference and add the new decision function instead of repeating the earlier sentence.\n"
        "- Use section_retention_requirements as exact section-level obligations; preserve their source_ids and protected quantities near the claims they support.\n"
        "- Use answer_frame to state the bottom-line answer, scope, confidence, and unsupported options.\n"
        "- Use supplemental_evidence only when it adds practical framing, comparators, scope, or interpretive context missing from the argument spine.\n"
        "- Interpret important quantities in decision terms.\n"
        "- Use limiting_evidence to say whether each major limiting point overturns, weakens, bounds, explains, or creates a crux for the answer. Preserve uncertainty when the packet says a point may only bound the answer.\n"
        "- Preserve each section_plan must_include_point in natural prose within that section.\n"
        "- Include every required visible structure heading exactly once, including Practical Implication.\n"
        "- Cite source_ids in brackets near the claims they support; presentation code will replace them with reader-facing source names.\n"
        "- Keep source IDs and quantities attached to their claims.\n"
        "- Write naturally; do not expose packet keys, IDs other than source_ids, validation machinery, or audit language.\n"
        "- Do not include a sources section; the final source list is added deterministically.\n\n"
        "Reader synthesis packet:\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n"
    )


def _reader_synthesis_packet(canonical_packet: dict[str, Any]) -> dict[str, Any]:
    packet = canonical_packet if isinstance(canonical_packet, dict) else {}
    spine = _dict(packet.get("evidence_weighted_argument_spine"))
    return {
        "schema_id": "reader_synthesis_packet_v1",
        "canonical_schema_id": packet.get("schema_id"),
        "decision_question": packet.get("decision_question"),
        "answer_frame": _drop_empty(
            {
                "skeleton": packet.get("decision_brief_skeleton"),
                "classification": packet.get("decision_answer_classification"),
            }
        ),
        "source_weighting": [_compact_source_judgment(row) for row in _list(packet.get("source_weight_judgments")) if isinstance(row, dict)],
        "argument_spine": _drop_empty(
            {
                "section_plan": spine.get("section_plan"),
                "steps": [_compact_spine_step(row) for row in _list(spine.get("steps")) if isinstance(row, dict)],
            }
        ),
        "section_writing_packets": _section_writing_packets(packet),
        "section_retention_requirements": _section_retention_requirements(packet),
        "limiting_evidence": [_compact_row(row) for row in _list(packet.get("counterweight_dispositions")) if isinstance(row, dict)],
        "supplemental_evidence": {
            "priority_evidence": [_compact_row(row) for row in _list(packet.get("priority_evidence")) if isinstance(row, dict)],
            "inventory": _compact_inventory(_dict(packet.get("organized_evidence_inventory"))),
        },
        "citation_registry": packet.get("citation_registry"),
    }


def _compact_source_judgment(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "source_ids": row.get("source_ids"),
            "main_use": row.get("main_use"),
            "weight_summary": row.get("why_weight_this_way"),
            "limits": row.get("what_not_to_use_it_for"),
            "evidence_item_ids": row.get("evidence_item_ids"),
            "omission_reason": row.get("omission_reason"),
        }
    )


def _compact_spine_step(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "step_id": row.get("step_id"),
            "primary_section": row.get("primary_section"),
            "memo_job": row.get("memo_job"),
            "point": row.get("point"),
            "source_ids": row.get("source_ids"),
            "evidence_item_ids": row.get("evidence_item_ids"),
            "quantities": row.get("quantities"),
            "disposition": row.get("disposition"),
            "disposition_rationale": row.get("disposition_rationale"),
            "confidence": row.get("confidence"),
            "scope": row.get("scope"),
        }
    )


def _compact_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    lanes = _dict(inventory.get("lanes"))
    compact_lanes = {}
    for lane, rows in lanes.items():
        compact_rows = [_compact_row(row) for row in _list(rows) if isinstance(row, dict)]
        if compact_rows:
            compact_lanes[str(lane)] = compact_rows[:8]
    return _drop_empty({"item_count": inventory.get("item_count"), "lanes": compact_lanes})


def _section_writing_packets(packet: dict[str, Any]) -> list[dict[str, Any]]:
    spine = _dict(packet.get("evidence_weighted_argument_spine"))
    steps = [_compact_spine_step(row) for row in _list(spine.get("steps")) if isinstance(row, dict)]
    steps_by_id = {str(row.get("step_id") or ""): row for row in steps if row.get("step_id")}
    evidence_by_id = _evidence_by_id(packet)
    requirements = _section_retention_requirements(packet)
    source_judgments = [_compact_source_judgment(row) for row in _list(packet.get("source_weight_judgments")) if isinstance(row, dict)]
    packets = []
    for section in _list(spine.get("section_plan")):
        if not isinstance(section, dict):
            continue
        section_name = str(section.get("section") or "").strip()
        owned_steps = [steps_by_id[step_id] for step_id in _string_list(section.get("owned_step_ids")) if step_id in steps_by_id]
        section_requirements = [row for row in requirements if row.get("primary_section") == section_name]
        evidence_ids = _dedupe(
            [
                *_string_list(section.get("owned_evidence_item_ids")),
                *[
                    evidence_id
                    for step in owned_steps
                    for evidence_id in _string_list(step.get("evidence_item_ids"))
                ],
                *[
                    evidence_id
                    for requirement in section_requirements
                    for evidence_id in _string_list(requirement.get("evidence_item_ids"))
                ],
            ]
        )
        evidence_rows = [evidence_by_id[evidence_id] for evidence_id in evidence_ids if evidence_id in evidence_by_id]
        source_ids = _dedupe(
            [
                *[source_id for step in owned_steps for source_id in _string_list(step.get("source_ids"))],
                *[source_id for row in evidence_rows for source_id in _string_list(row.get("source_ids"))],
                *[source_id for row in section_requirements for source_id in _string_list(row.get("source_ids"))],
            ]
        )
        packets.append(
            _drop_empty(
                {
                    "section": section_name,
                    "writing_job": section.get("writing_job"),
                    "argument_steps": owned_steps,
                    "required_points": section.get("must_include_points"),
                    "retention_requirements": section_requirements,
                    "evidence_context": evidence_rows,
                    "source_weighting": [
                        row
                        for row in source_judgments
                        if any(source_id in _string_list(row.get("source_ids")) for source_id in source_ids)
                    ],
                }
            )
        )
    return packets


def _evidence_by_id(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = []
    rows.extend(_compact_row(row) for row in _list(packet.get("priority_evidence")) if isinstance(row, dict))
    rows.extend(_compact_row(row) for row in _list(packet.get("counterweight_dispositions")) if isinstance(row, dict))
    rows.extend(_compact_row(row) for row in _list(packet.get("scope_boundaries")) if isinstance(row, dict))
    rows.extend(_compact_row(row) for row in _list(packet.get("decision_cruxes")) if isinstance(row, dict))
    inventory = _dict(packet.get("organized_evidence_inventory"))
    for lane_rows in _dict(inventory.get("lanes")).values():
        rows.extend(_compact_row(row) for row in _list(lane_rows) if isinstance(row, dict))
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        item_id = str(row.get("item_id") or "").strip()
        if item_id and item_id not in by_id:
            by_id[item_id] = row
    return by_id


def _section_retention_requirements(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in _list(packet.get("mandatory_retention_checklist")):
        if not isinstance(row, dict):
            continue
        rows.append(_compact_retention_requirement(row))
    return rows


def _compact_retention_requirement(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "requirement_id": row.get("obligation_id") or row.get("item_id"),
            "primary_section": _retention_requirement_section(row),
            "role": row.get("role") or row.get("obligation_type"),
            "statement": row.get("statement") or row.get("claim"),
            "source_ids": row.get("source_ids") or ([row.get("source_id")] if row.get("source_id") else None),
            "quantities": row.get("quantities"),
            "evidence_item_ids": row.get("evidence_item_ids"),
            "prose_instruction": row.get("prose_instruction"),
        }
    )


def _retention_requirement_section(row: dict[str, Any]) -> str:
    role = str(row.get("role") or row.get("obligation_type") or "").lower()
    text = str(row.get("statement") or row.get("claim") or row.get("prose_instruction") or "").lower()
    if any(token in role for token in ("counter", "boundary", "scope", "crux", "limit", "risk")):
        return "What Could Change or Bound the Answer"
    if any(token in text for token in ("subgroup", "scope", "bound", "risk factor", "exception", "threshold", "high-risk")):
        return "What Could Change or Bound the Answer"
    if any(token in role for token in ("practical", "application", "implementation")):
        return "Practical Implication"
    if any(token in text for token in ("practical", "application", "implementation", "advice", "recommend", "replacement", "action", "translate")):
        return "Practical Implication"
    if "bottom" in role or "answer" in role:
        return "Bottom Line"
    return "Why This Is the Best Current Read"


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "item_id": row.get("item_id"),
            "role": row.get("role"),
            "answer_relation": row.get("answer_relation"),
            "memo_function": row.get("memo_function"),
            "claim": row.get("claim") or row.get("statement"),
            "source_ids": row.get("source_ids") or ([row.get("source_id")] if row.get("source_id") else None),
            "quantities": row.get("quantities"),
            "decision_relevance": row.get("decision_relevance"),
            "caveat": row.get("caveat"),
            "importance_rank": row.get("importance_rank"),
        }
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}
