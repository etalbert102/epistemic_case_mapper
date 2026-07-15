from __future__ import annotations

import json
from typing import Any

from epistemic_case_mapper.map_briefing_decision_usefulness import compact_decision_usefulness_for_prompt
from epistemic_case_mapper.map_briefing_lightweight_guidance import compact_lightweight_guidance_for_prompt
from epistemic_case_mapper.map_briefing_canonical_decision_writer_packet import build_canonical_decision_writer_packet
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import dedupe as _dedupe
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import string_list as _string_list


def build_memo_ready_packet_synthesis_prompt(memo_ready_packet: dict[str, Any]) -> str:
    if isinstance(memo_ready_packet, dict) and memo_ready_packet.get("evidence_items"):
        canonical = _dict(memo_ready_packet.get("canonical_decision_writer_packet")) or build_canonical_decision_writer_packet(memo_ready_packet)
        canonical = _with_top_level_guidance(canonical, memo_ready_packet)
        return build_canonical_decision_writer_packet_synthesis_prompt(canonical)
    return (
        "Memo-ready packet synthesis prompt unavailable.\n"
        "Active memo synthesis requires memo_ready_packet.evidence_items so a canonical decision writer packet can be compiled without raw packet or audit-only fields.\n"
    )


def build_memo_ready_section_synthesis_plan(memo_ready_packet: dict[str, Any]) -> dict[str, Any]:
    """Build section-local synthesis prompts from the canonical writer handoff."""

    if not isinstance(memo_ready_packet, dict) or not memo_ready_packet.get("evidence_items"):
        return {
            "schema_id": "memo_ready_section_synthesis_plan_v1",
            "status": "unavailable",
            "sections": [],
            "issues": ["memo_ready_packet.evidence_items unavailable"],
        }
    canonical = _dict(memo_ready_packet.get("canonical_decision_writer_packet")) or build_canonical_decision_writer_packet(memo_ready_packet)
    canonical = _with_top_level_guidance(canonical, memo_ready_packet)
    reader_packet = _reader_synthesis_packet(canonical)
    section_packets = _section_synthesis_packets(reader_packet)
    known_source_ids = _known_source_ids(memo_ready_packet, canonical, reader_packet)
    return {
        "schema_id": "memo_ready_section_synthesis_plan_v1",
        "status": "ready" if section_packets else "unavailable",
        "reader_packet_schema_id": reader_packet.get("schema_id"),
        "decision_question": reader_packet.get("decision_question"),
        "title": _short_decision_title(reader_packet.get("decision_question")),
        "bottom_line": _bottom_line_from_reader_packet(reader_packet),
        "known_source_ids": known_source_ids,
        "sections": [
            {
                "section_id": packet["section_id"],
                "heading": packet["heading"],
                "prompt": build_memo_ready_section_synthesis_prompt(packet, known_source_ids=known_source_ids),
                "packet": packet,
            }
            for packet in section_packets
        ],
        "issues": [] if section_packets else ["canonical writer packet has no section writing packets"],
    }


def build_memo_ready_section_synthesis_prompt(
    section_packet: dict[str, Any],
    *,
    known_source_ids: list[str],
) -> str:
    heading = str(section_packet.get("heading") or "").strip()
    return (
        "You are writing one section of a source-grounded decision memo from a section-local packet.\n"
        "Use the packet as the sole semantic handoff for this section.\n\n"
        "Section role discipline:\n"
        "- Follow section_role_contract as the controlling job for this section.\n"
        "- If evidence appears in another section, mention it only to perform this section's distinct job.\n"
        "- Do not re-prove the bottom line unless this section's contract asks for the proof.\n\n"
        "Output rules:\n"
        f"- Return Markdown for this section only, starting with exactly: ## {heading}\n"
        "- Use bracketed citations only for source_id values listed in known_source_ids.\n"
        "- Never cite analyst_item IDs, claim IDs, evidence item IDs, source labels, article titles, or author-year names inside brackets.\n"
        "- Every bracketed citation must be one or more known source_ids separated by comma-space.\n"
        "- Keep packet IDs, validation machinery, and audit language out of the prose.\n"
        "- Write natural expert analyst prose, not a checklist, unless bullets are the clearest form for concrete boundaries.\n"
        "- Make each paragraph do a distinct reasoning job and avoid repeating earlier-section sentences.\n\n"
        "Writing priorities:\n"
        "- Use bluf_contract for the opening bottom line and as a local reference for answer-first wording when this section restates the read.\n"
        "- Treat balanced_answer_frame as the controlling top-level read: reconcile support, counterweight, scope, and underused balance evidence instead of letting one evidence lane dominate.\n"
        "- Use must_not_overstate to calibrate causal and confidence language.\n"
        "- Use evidence_language_contracts to keep source-specific verbs and confidence no stronger than the source design permits.\n"
        "- Lead with the distinction or tradeoff that resolves this section when the packet supplies one.\n"
        "- Explain which evidence carries the answer, which evidence bounds it, and which evidence mainly contextualizes application.\n"
        "- Preserve required quantities near the claims they support and explain what they mean for the decision.\n"
        "- Section role discipline never overrides retention: include every protected quantity and source_id listed in section_retention_requirements.\n"
        "- If one claim has several protected quantities, keep the full set together rather than sampling representative values.\n"
        "- Translate source weighting into prose instead of generic labels.\n"
        "- For practical sections, state the concrete implication for the decision-maker within the packet's scope.\n\n"
        f"known_source_ids:\n{json.dumps(known_source_ids, indent=2, ensure_ascii=False)}\n\n"
        f"section_packet:\n{json.dumps(section_packet, indent=2, ensure_ascii=False)}\n"
    )


def build_writer_packet_synthesis_prompt(
    writer_packet: dict[str, Any],
    *,
    memo_ready_packet: dict[str, Any] | None = None,
) -> str:
    if isinstance(memo_ready_packet, dict) and memo_ready_packet.get("evidence_items"):
        canonical = _dict(memo_ready_packet.get("canonical_decision_writer_packet")) or build_canonical_decision_writer_packet(memo_ready_packet)
        canonical = _with_top_level_guidance(canonical, memo_ready_packet)
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
        "- Use lightweight_writer_guidance to avoid misleading wording, generic source-quality labels, quantity endpoint mixups, and overstatement.\n"
        "- Use decision_usefulness to make the answer's options, criteria, tradeoffs, crux thresholds, and update triggers explicit when available.\n"
        "- If decision_usefulness says the answer shape is a single stance, threshold, or classification, explain the relevant choice without inventing fake alternatives.\n"
        "- Use decision_usefulness tradeoffs and cruxes as prose scaffolding; do not dump the option-criteria matrix unless the decision question genuinely needs a matrix.\n"
        "- Lead with the key distinction that resolves the decision when the packet supplies one; make it feel like analyst judgment, not a list of findings.\n"
        "- Use bluf_contract for the opening bottom line: answer first, then scope, confidence, and the main exception or boundary.\n"
        "- Treat balanced_answer_frame as the controlling answer frame. The bottom line and every section should preserve its best_current_read, main_support, main_counterweight, scope, practical_read, must_not_overstate, and underused_balance_evidence.\n"
        "- Use balanced_answer_frame.must_not_overstate to calibrate causal language and confidence. Do not turn observational or guidance evidence into stronger proof than the packet supports.\n"
        "- Use evidence_language_contracts to choose verbs: observational evidence should stay associational, guidance should stay contextual, and indirect endpoints should stay tied to the measured endpoint.\n"
        "- Explain the evidence hierarchy in prose: which evidence carries the answer, which evidence mainly bounds it, and which evidence contextualizes practical advice.\n"
        "- Convert tradeoff labels into natural prose about what a decision-maker is choosing to privilege.\n"
        "- Make Practical Implication concrete: state what the reader should do, not just what the evidence says.\n"
        "- State what would change the answer when update triggers or crux thresholds are available.\n"
        "- Use source_weighting to explain why sources drive, calibrate, bound, or contextualize the answer.\n"
        "- Use argument_spine as the primary writing plan; follow its section_plan and primary_section fields to decide where each evidence step belongs.\n"
        "- Treat section_writing_packets as the primary section-local context. Each section packet contains the argument steps, evidence rows, source roles, and retention requirements for that section.\n"
        "- Write each section around its owned spine steps. If a later section needs evidence already used earlier, make a short cross-reference and add the new decision function instead of repeating the earlier sentence.\n"
        "- Use section_retention_requirements as exact section-level obligations; preserve their source_ids and protected quantities near the claims they support.\n"
        "- Use section_role_contract to keep sections distinct: answer-evidence explains why the read is best; counterweight sections bound or update it; practical sections translate it into action.\n"
        "- Use answer_frame to state the bottom-line answer, scope, confidence, and unsupported options.\n"
        "- Use supplemental_evidence only when it adds practical framing, comparators, scope, or interpretive context missing from the argument spine.\n"
        "- Interpret important quantities in decision terms.\n"
        "- If lightweight_writer_guidance says a quantity could be confused with another endpoint, keep those endpoints in separate clauses.\n"
        "- Surface evidence-quality caveats specifically; do not use generic labels such as quality limit as a substitute for explanation.\n"
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
        "balanced_answer_frame": packet.get("balanced_answer_frame"),
        "bluf_contract": packet.get("bluf_contract"),
        "evidence_language_contracts": _compact_language_contracts(_list(packet.get("evidence_language_contracts"))),
        "source_weighting": [_compact_source_judgment(row) for row in _list(packet.get("source_weight_judgments")) if isinstance(row, dict)],
        "lightweight_writer_guidance": compact_lightweight_guidance_for_prompt(_dict(packet.get("lightweight_writer_guidance"))),
        "decision_usefulness": compact_decision_usefulness_for_prompt(_dict(packet.get("decision_usefulness_packet"))),
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


def _section_synthesis_packets(reader_packet: dict[str, Any]) -> list[dict[str, Any]]:
    top_context = _drop_empty(
        {
            "decision_question": reader_packet.get("decision_question"),
            "answer_frame": reader_packet.get("answer_frame"),
            "balanced_answer_frame": reader_packet.get("balanced_answer_frame"),
            "bluf_contract": reader_packet.get("bluf_contract"),
            "evidence_language_contracts": reader_packet.get("evidence_language_contracts"),
            "decision_usefulness": reader_packet.get("decision_usefulness"),
            "lightweight_writer_guidance": reader_packet.get("lightweight_writer_guidance"),
            "citation_registry": reader_packet.get("citation_registry"),
        }
    )
    packets = []
    for raw in _list(reader_packet.get("section_writing_packets")):
        if not isinstance(raw, dict):
            continue
        source_section = str(raw.get("section") or "").strip()
        section_id = _section_id_from_heading(source_section)
        heading = _canonical_section_heading(source_section)
        if section_id == "bottom_line" or not heading:
            continue
        packets.append(
            _drop_empty(
                {
                    "schema_id": "memo_ready_section_writer_packet_v1",
                    "section_id": section_id,
                    "heading": heading,
                    "source_section": source_section,
                    "section_job": raw.get("writing_job"),
                    "section_role_contract": _section_role_contract(heading),
                    "top_context": top_context,
                    "section_argument_steps": raw.get("argument_steps"),
                    "required_points": raw.get("required_points"),
                    "section_retention_requirements": raw.get("retention_requirements"),
                    "evidence_context": raw.get("evidence_context"),
                    "source_weighting": raw.get("source_weighting"),
                }
            )
        )
    return packets


def _canonical_section_heading(heading: str) -> str:
    section_id = _section_id_from_heading(heading)
    return {
        "answer_evidence": "Why This Is the Best Current Read",
        "counterweights": "What Could Change or Bound the Answer",
        "source_weighting": "How to Weight the Evidence",
        "practical_implication": "Practical Implication",
    }.get(section_id, "")


def _section_role_contract(heading: str) -> dict[str, Any]:
    section_id = _section_id_from_heading(heading)
    contracts = {
        "answer_evidence": {
            "role": "explain_why_this_read_is_best",
            "do": [
                "integrate the strongest supporting evidence into the reason for the current answer",
                "interpret key quantities only where they carry the main read",
                "name the main uncertainty only as it affects confidence in this read",
            ],
            "avoid": [
                "turning into a source inventory",
                "listing every scope boundary or practical action",
                "repeating the bottom line without adding evidential reasoning",
            ],
        },
        "counterweights": {
            "role": "bound_or_change_the_answer",
            "do": [
                "explain what could weaken, reverse, or narrow the answer",
                "separate causal limits, subgroup limits, endpoint limits, and update triggers",
                "say whether each limit overturns the answer or only narrows confidence/scope",
            ],
            "avoid": [
                "repeating the full affirmative case",
                "presenting caveats as generic uncertainty",
                "turning every limitation into an equal-weight objection",
            ],
        },
        "source_weighting": {
            "role": "explain_how_to_read_the_sources",
            "do": [
                "state which sources carry the answer and which mainly calibrate, bound, or contextualize it",
                "explain source caveats compactly without restating the evidence argument",
            ],
            "avoid": [
                "using schema labels as prose",
                "repeating the same support and counterweight paragraphs from other sections",
            ],
        },
        "practical_implication": {
            "role": "translate_the_read_into_action",
            "do": [
                "state what the reader should do with the answer inside the stated scope",
                "turn the main boundary into a practical condition or monitoring point",
                "keep the implication proportional to the evidence strength",
            ],
            "avoid": [
                "reopening the whole evidence argument",
                "adding new evidence not needed for action",
                "restating the bottom line without a practical consequence",
            ],
        },
    }
    return contracts.get(section_id, contracts["answer_evidence"])


def _section_id_from_heading(heading: str) -> str:
    text = str(heading or "").strip().lower()
    if not text:
        return ""
    if "bottom" in text or text in {"decision brief", "current read"}:
        return "bottom_line"
    if "practical" in text or "use this read" in text:
        return "practical_implication"
    if "weight" in text and "evidence" in text:
        return "source_weighting"
    if any(token in text for token in ("change", "bound", "limit", "counter", "crux")):
        return "counterweights"
    if "evidence carrying" in text or "best current" in text or "why this" in text:
        return "answer_evidence"
    return "answer_evidence"


def _known_source_ids(
    memo_ready_packet: dict[str, Any],
    canonical_packet: dict[str, Any],
    reader_packet: dict[str, Any],
) -> list[str]:
    ids = []
    for source in _list(memo_ready_packet.get("source_trail")):
        if isinstance(source, dict):
            ids.append(str(source.get("source_id") or "").strip())
    registry = _dict(reader_packet.get("citation_registry")) or _dict(canonical_packet.get("citation_registry"))
    for value in registry.values():
        if isinstance(value, dict):
            ids.append(str(value.get("source_id") or value.get("id") or "").strip())
        else:
            ids.append(str(value or "").strip())
    return _dedupe([source_id for source_id in ids if source_id])


def _bottom_line_from_reader_packet(reader_packet: dict[str, Any]) -> str:
    balanced = _dict(reader_packet.get("balanced_answer_frame"))
    answer_frame = _dict(reader_packet.get("answer_frame"))
    skeleton = _dict(answer_frame.get("skeleton"))
    classification = _dict(answer_frame.get("classification"))
    for value in (
        _dict(reader_packet.get("bluf_contract")).get("one_sentence_version"),
        _dict(reader_packet.get("bluf_contract")).get("recommended_read"),
        balanced.get("best_current_read"),
        skeleton.get("direct_answer"),
        skeleton.get("bottom_line"),
        classification.get("current_answer_state"),
        classification.get("recommended_stance"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _short_decision_title(question: Any) -> str:
    text = str(question or "").strip().rstrip("?")
    if not text:
        return "Decision Memo"
    text = " ".join(text.split())
    if len(text) <= 72:
        return text
    return text[:69].rstrip(" ,;:") + "..."


def _with_top_level_guidance(canonical: dict[str, Any], memo_ready_packet: dict[str, Any]) -> dict[str, Any]:
    guidance = _dict(canonical.get("lightweight_writer_guidance")) or _dict(memo_ready_packet.get("lightweight_writer_guidance"))
    usefulness = _dict(canonical.get("decision_usefulness_packet")) or _dict(memo_ready_packet.get("decision_usefulness_packet"))
    quality = _dict(canonical.get("decision_usefulness_quality_report")) or _dict(memo_ready_packet.get("decision_usefulness_quality_report"))
    additions = _drop_empty(
        {
            "lightweight_writer_guidance": guidance,
            "decision_usefulness_packet": usefulness,
            "decision_usefulness_quality_report": quality,
        }
    )
    if not additions:
        return canonical
    return {**canonical, **additions}


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


def _compact_language_contracts(rows: list[Any]) -> list[dict[str, Any]]:
    return [
        _drop_empty(
            {
                "contract_id": row.get("contract_id"),
                "item_id": row.get("item_id"),
                "source_ids": row.get("source_ids"),
                "evidence_design": row.get("evidence_design"),
                "allowed_language": row.get("allowed_language"),
                "avoid_language": row.get("avoid_language"),
                "must_qualify_with": row.get("must_qualify_with"),
                "wording_rule": row.get("wording_rule"),
            }
        )
        for row in rows
        if isinstance(row, dict)
    ][:24]


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
