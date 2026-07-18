from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.map_briefing_decision_usefulness import compact_decision_usefulness_for_prompt
from epistemic_case_mapper.map_briefing_decision_argument_contract import (
    build_decision_argument_contract,
    compact_decision_argument_contract_for_prompt,
    compact_decision_argument_section_for_prompt,
    decision_argument_section,
)
from epistemic_case_mapper.map_briefing_expert_judgment_compression import (
    compact_expert_judgment_for_prompt,
    expert_judgment_section,
)
from epistemic_case_mapper.map_briefing_lightweight_guidance import compact_lightweight_guidance_for_prompt
from epistemic_case_mapper.map_briefing_canonical_decision_writer_packet import build_canonical_decision_writer_packet
from epistemic_case_mapper.map_briefing_analyst_decision_spine import compact_analyst_decision_spine_for_prompt, section_spine_for_prompt
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import dedupe as _dedupe
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import norm as _norm
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import string_list as _string_list
from epistemic_case_mapper.map_briefing_source_bound_evidence import build_source_bound_evidence_atoms, source_bound_quantity_tuples
from epistemic_case_mapper.map_briefing_memo_ready_guidance_application import build_section_reader_guidance_application
from epistemic_case_mapper.map_briefing_memo_ready_action_contract import build_decision_action_contract
from epistemic_case_mapper.map_briefing_source_identity import source_id_alias_map
from epistemic_case_mapper.map_briefing_memo_ready_section_notes import build_memo_ready_section_markdown_prompt
from epistemic_case_mapper.map_briefing_memo_ready_section_jobs import with_section_specific_jobs
from epistemic_case_mapper.map_briefing_memo_ready_section_packet_context import (
    compact_memo_ready_row as _compact_row,
    section_retention_requirements as _section_retention_requirements,
    section_writing_packets,
)
from epistemic_case_mapper.map_briefing_priority_quantity_contracts import (
    build_priority_quantity_contracts,
    compact_priority_quantity_contracts_for_prompt,
    contracts_for_evidence_ids,
)
from epistemic_case_mapper.map_briefing_reader_judgment_packet import (
    build_reader_judgment_packet,
    compact_reader_judgments_for_section,
)
from epistemic_case_mapper.map_briefing_source_weighting_contract import build_source_weighting_contract, build_source_weighting_flow_audit, build_source_weighting_section_packet


def build_memo_ready_packet_synthesis_prompt(memo_ready_packet: dict[str, Any]) -> str:
    if isinstance(memo_ready_packet, dict) and memo_ready_packet.get("evidence_items"):
        canonical = _dict(memo_ready_packet.get("canonical_decision_writer_packet")) or build_canonical_decision_writer_packet(memo_ready_packet)
        canonical = _with_top_level_guidance(canonical, memo_ready_packet)
        canonical = _with_decision_argument_contract(canonical)
        return build_canonical_decision_writer_packet_synthesis_prompt(canonical)
    return (
        "Memo-ready packet synthesis prompt unavailable.\n"
        "Active memo synthesis requires memo_ready_packet.evidence_items so a canonical decision writer packet can be compiled without raw packet or audit-only fields.\n"
    )


def build_memo_ready_section_synthesis_plan(memo_ready_packet: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(memo_ready_packet, dict) or not memo_ready_packet.get("evidence_items"):
        return {
            "schema_id": "memo_ready_section_synthesis_plan_v1",
            "status": "unavailable",
            "sections": [],
            "issues": ["memo_ready_packet.evidence_items unavailable"],
        }
    canonical = _dict(memo_ready_packet.get("canonical_decision_writer_packet")) or build_canonical_decision_writer_packet(memo_ready_packet)
    canonical = _with_top_level_guidance(canonical, memo_ready_packet)
    canonical = _with_decision_argument_contract(canonical)
    reader_packet = _reader_synthesis_packet(canonical)
    section_packets = _section_synthesis_packets(reader_packet)
    source_weighting_section_packet = next((packet for packet in section_packets if packet.get("section_id") == "source_weighting"), {})
    source_weighting_flow_audit = build_source_weighting_flow_audit(canonical, {**reader_packet, "source_weighting_section_packet": source_weighting_section_packet})
    known_source_ids = _known_source_ids(memo_ready_packet, canonical, reader_packet)
    known_source_aliases = source_id_alias_map(_list(memo_ready_packet.get("source_trail")))
    return {
        "schema_id": "memo_ready_section_synthesis_plan_v1",
        "status": "ready" if section_packets else "unavailable",
        "reader_packet_schema_id": reader_packet.get("schema_id"),
        "decision_question": reader_packet.get("decision_question"),
        "title": _short_decision_title(reader_packet.get("decision_question")),
        "bottom_line": _bottom_line_from_reader_packet(reader_packet),
        "known_source_ids": known_source_ids,
        "known_source_aliases": known_source_aliases,
        "source_weighting_flow_audit": source_weighting_flow_audit,
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


def _with_decision_argument_contract(canonical: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(canonical, dict):
        return {}
    if _dict(canonical.get("decision_argument_contract")).get("schema_id") == "decision_argument_contract_v1":
        return canonical
    enriched = dict(canonical)
    enriched["decision_argument_contract"] = build_decision_argument_contract(enriched)
    enriched["decision_argument_contract_report"] = _dict(enriched["decision_argument_contract"].get("report"))
    return enriched


def build_memo_ready_section_synthesis_prompt(
    section_packet: dict[str, Any],
    *,
    known_source_ids: list[str],
) -> str:
    return build_memo_ready_section_markdown_prompt(section_packet, known_source_ids=known_source_ids)


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
        "- Use lightweight_writer_guidance to choose precise wording, specific source-quality explanations, correct quantity endpoints, and calibrated claims.\n"
        "- Use decision_usefulness to make the answer's options, criteria, tradeoffs, crux thresholds, and update triggers explicit when available.\n"
        "- If decision_usefulness says the answer shape is a single stance, threshold, or classification, explain the relevant choice without inventing fake alternatives.\n"
        "- Use decision_usefulness tradeoffs and cruxes as prose scaffolding; include a matrix only when the decision question genuinely needs one.\n"
        "- Lead with the key distinction that resolves the decision when the packet supplies one; make it feel like analyst judgment, not a list of findings.\n"
        "- Use bluf_contract for the opening bottom line: answer first, then scope, confidence, and the main exception or boundary.\n"
        "- Treat balanced_answer_frame as the controlling answer frame. The bottom line and every section should preserve its best_current_read, main_support, main_counterweight, scope, practical_read, must_not_overstate, and underused_balance_evidence.\n"
        "- Use balanced_answer_frame.must_not_overstate to calibrate causal language and confidence; keep observational and guidance evidence at the strength the packet supports.\n"
        "- Use evidence_language_contracts to choose verbs: observational evidence should stay associational, guidance should stay contextual, and indirect endpoints should stay tied to the measured endpoint.\n"
        "- Explain the evidence hierarchy in prose: which evidence carries the answer, which evidence mainly bounds it, and which evidence contextualizes practical advice.\n"
        "- Convert tradeoff labels into natural prose about what a decision-maker is choosing to privilege.\n"
        "- Make Practical Implication concrete: state the action-relevant implication and the evidence basis.\n"
        "- State what would change the answer when update triggers or crux thresholds are available.\n"
        "- Use source_weighting to explain why sources drive, calibrate, bound, or contextualize the answer.\n"
        "- Use analyst_decision_spine as the controlling reasoning plan: it says the answer, source hierarchy, support, counterweights, quantities, scope, and practical move in the order the memo should express them.\n"
        "- Use argument_spine as the primary writing plan; follow its section_plan and primary_section fields to decide where each evidence step belongs.\n"
        "- Treat section_writing_packets as the primary section-local context. Each section packet contains the argument steps, evidence rows, source roles, and retention requirements for that section.\n"
        "- Write each section around its owned spine steps. If a later section needs evidence already used earlier, make a short cross-reference and add the new decision function instead of repeating the earlier sentence.\n"
        "- Use section_retention_requirements as exact section-level obligations; preserve their source_ids and protected quantities near the claims they support.\n"
        "- Use section_role_contract to keep sections distinct: answer-evidence explains why the read is best; counterweight sections bound or update it; practical sections translate it into action.\n"
        "- Use answer_frame to state the bottom-line answer, scope, confidence, and unsupported options.\n"
        "- Use supplemental_evidence only when it adds practical framing, comparators, scope, or interpretive context missing from the argument spine.\n"
        "- Interpret important quantities in decision terms.\n"
        "- If lightweight_writer_guidance says a quantity could be confused with another endpoint, keep those endpoints in separate clauses.\n"
        "- Surface evidence-quality caveats specifically, replacing generic labels such as quality limit with the concrete limitation.\n"
        "- Use limiting_evidence to say whether each major limiting point overturns, weakens, bounds, explains, or creates a crux for the answer. Preserve uncertainty when the packet says a point may only bound the answer.\n"
        "- Preserve each section_plan must_include_point in natural prose within that section.\n"
        "- Include every required visible structure heading exactly once, including Practical Implication.\n"
        "- Cite source_ids in brackets near the claims they support; presentation code will replace them with reader-facing source names.\n"
        "- Keep source IDs and quantities attached to their claims.\n"
        "- Write naturally with reader-facing language and bracketed source_ids only for citations.\n"
        "- End after Practical Implication; presentation code adds the final source list deterministically.\n\n"
        "Reader synthesis packet:\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n"
    )


def _reader_synthesis_packet(canonical_packet: dict[str, Any]) -> dict[str, Any]:
    packet = canonical_packet if isinstance(canonical_packet, dict) else {}
    spine = _dict(packet.get("evidence_weighted_argument_spine"))
    source_weighting_contract = _dict(packet.get("source_weighting_contract")) or build_source_weighting_contract(packet)
    reader_judgment_packet = _dict(packet.get("reader_judgment_packet")) or build_reader_judgment_packet(packet)
    priority_quantity_contracts = _dict(packet.get("priority_quantity_contracts"))
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
        "analyst_decision_spine": compact_analyst_decision_spine_for_prompt(_dict(packet.get("analyst_decision_spine"))),
        "decision_argument_contract": compact_decision_argument_contract_for_prompt(_dict(packet.get("decision_argument_contract"))),
        "expert_judgment_compression": compact_expert_judgment_for_prompt(_dict(packet.get("expert_judgment_compression"))),
        "evidence_language_contracts": _compact_language_contracts(_list(packet.get("evidence_language_contracts"))),
        "source_weighting": [_compact_source_judgment(row) for row in _list(packet.get("source_weight_judgments")) if isinstance(row, dict)],
        "reader_judgment_packet": reader_judgment_packet,
        "source_weighting_contract": source_weighting_contract,
        "source_weighting_flow_audit": build_source_weighting_flow_audit(packet, {"source_weighting_contract": source_weighting_contract}),
        "lightweight_writer_guidance": compact_lightweight_guidance_for_prompt(_dict(packet.get("lightweight_writer_guidance"))),
        "decision_usefulness": compact_decision_usefulness_for_prompt(_dict(packet.get("decision_usefulness_packet"))),
        "analyst_decision_logic": _compact_analyst_decision_logic(_dict(packet.get("analyst_decision_logic"))),
        "analyst_argument_plan": [
            _compact_analyst_argument_step(row)
            for row in _list(packet.get("analyst_argument_plan"))
            if isinstance(row, dict)
        ][:8],
        "argument_spine": _drop_empty(
            {
                "section_plan": spine.get("section_plan"),
                "steps": [_compact_spine_step(row) for row in _list(spine.get("steps")) if isinstance(row, dict)],
            }
        ),
        "priority_quantity_contracts": priority_quantity_contracts,
        "section_writing_packets": section_writing_packets(
            packet,
            compact_spine_step=_compact_spine_step,
            compact_source_judgment=_compact_source_judgment,
        ),
        "section_retention_requirements": _section_retention_requirements(packet),
        "limiting_evidence": [_compact_row(row) for row in _list(packet.get("counterweight_dispositions")) if isinstance(row, dict)],
        "supplemental_evidence": {
            "priority_evidence": [_compact_row(row) for row in _list(packet.get("priority_evidence")) if isinstance(row, dict)],
            "inventory": _compact_inventory(_dict(packet.get("organized_evidence_inventory"))),
        },
        "citation_registry": packet.get("citation_registry"),
    }
def _section_synthesis_packets(reader_packet: dict[str, Any]) -> list[dict[str, Any]]:
    packets = []
    source_weighting = build_source_weighting_section_packet(reader_packet)
    if source_weighting:
        packets.append(_source_weighting_section_writer_packet(reader_packet, source_weighting))
    for raw in _list(reader_packet.get("section_writing_packets")):
        if not isinstance(raw, dict):
            continue
        source_section = str(raw.get("section") or "").strip()
        section_id = _section_id_from_heading(source_section)
        heading = _canonical_section_heading(source_section)
        if section_id == "bottom_line" or not heading:
            continue
        evidence_ids = _section_evidence_ids(raw)
        analyst_moves = _section_analyst_argument_moves(reader_packet, raw, section_id=section_id)
        usefulness_moves = _section_decision_usefulness_moves(reader_packet, section_id=section_id, evidence_ids=evidence_ids)
        source_bound_atoms = with_section_specific_jobs(
            _model_safe_source_bound_evidence_atoms(_source_bound_atom_rows(raw)),
            section_id=section_id,
        )
        priority_quantity_contracts = _section_priority_quantity_contracts(reader_packet, evidence_ids, section_id)
        packets.append(
            _drop_empty(
                {
                    "schema_id": "memo_ready_section_writer_packet_v1",
                    "section_id": section_id,
                    "heading": heading,
                    "source_section": source_section,
                    "section_job": _section_job(section_id, raw.get("writing_job")),
                    "section_role_contract": _section_role_contract(heading),
                    "section_focus": _section_focus(section_id),
                    "decision_argument_section": compact_decision_argument_section_for_prompt(
                        decision_argument_section(_dict(reader_packet.get("decision_argument_contract")), section_id)
                    ),
                    "expert_judgment_section": expert_judgment_section(
                        _dict(reader_packet.get("expert_judgment_compression")),
                        section_id,
                    ),
                    "analyst_section_spine": section_spine_for_prompt(_dict(reader_packet.get("analyst_decision_spine")), section_id),
                    "top_context": _section_top_context(reader_packet, raw, section_id=section_id),
                    "reader_guidance_application": _guidance_application(reader_packet, raw, section_id),
                    "analyst_argument_moves": analyst_moves,
                    "decision_usefulness_moves": usefulness_moves,
                    "section_argument_steps": raw.get("argument_steps"),
                    "required_points": raw.get("required_points"),
                    "section_retention_requirements": raw.get("retention_requirements"),
                    "priority_quantity_contracts": priority_quantity_contracts,
                    "protected_quantity_sets": _protected_quantity_sets(raw),
                    "source_bound_evidence_atoms": source_bound_atoms,
                    "quantity_collision_warnings": _quantity_collision_warnings(source_bound_atoms),
                    "evidence_context": with_section_specific_jobs(
                        [row for row in _list(raw.get("evidence_context")) if isinstance(row, dict)],
                        section_id=section_id,
                    ),
                    "source_weighting": raw.get("source_weighting"),
                }
            )
        )
    return packets
def _source_weighting_section_writer_packet(reader_packet: dict[str, Any], source_weighting: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "schema_id": "memo_ready_section_writer_packet_v1", "section_id": "source_weighting",
            "heading": "How to Weight the Evidence", "source_section": "How to Weight the Evidence",
            "section_job": _section_job("source_weighting", source_weighting.get("writing_job")),
            "section_role_contract": _section_role_contract("How to Weight the Evidence"),
            "section_focus": _section_focus("source_weighting"),
            "decision_argument_section": compact_decision_argument_section_for_prompt(
                decision_argument_section(_dict(reader_packet.get("decision_argument_contract")), "source_weighting")
            ),
            "expert_judgment_section": expert_judgment_section(
                _dict(reader_packet.get("expert_judgment_compression")),
                "source_weighting",
            ),
            "analyst_section_spine": section_spine_for_prompt(_dict(reader_packet.get("analyst_decision_spine")), "source_weighting"),
            "top_context": _section_top_context(reader_packet, source_weighting, section_id="source_weighting"),
            "reader_guidance_application": _guidance_application(reader_packet, source_weighting, "source_weighting"),
            "analyst_argument_moves": _section_analyst_argument_moves(
                reader_packet,
                source_weighting,
                section_id="source_weighting",
            ),
            "decision_usefulness_moves": _section_decision_usefulness_moves(
                reader_packet,
                section_id="source_weighting",
                evidence_ids=_section_evidence_ids(source_weighting),
            ),
            "required_points": source_weighting.get("required_points"), "source_weighting_contract": reader_packet.get("source_weighting_contract"),
            "source_role_groups": source_weighting.get("source_role_groups"), "lane_cards": source_weighting.get("lane_cards"),
            "validation_contract": source_weighting.get("validation_contract"),
        }
    )
def _guidance_application(reader_packet: dict[str, Any], raw_section: dict[str, Any], section_id: str) -> dict[str, Any]:
    return build_section_reader_guidance_application(reader_packet, raw_section, section_id=section_id, source_ids=_section_source_ids(raw_section))


def _canonical_section_heading(heading: str) -> str:
    raw = str(heading or "").strip()
    section_id = _section_id_from_heading(heading)
    if section_id == "practical_implication" and "use this read" in raw.lower():
        return "How to Use This Read"
    if section_id == "counterweights" and "bound the read" in raw.lower():
        return "What Could Change or Bound the Read"
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
                "show the strongest reason the primary answer follows from the evidence",
                "interpret only quantities that carry the main answer",
                "use one confidence-calibration sentence only if it explains why the answer is neutral rather than stronger",
            ],
            "avoid": [
                "turning into a source inventory",
                "previewing all subgroup boundaries",
                "turning caveats into a full counterweight section",
            ],
        },
        "counterweights": {
            "role": "bound_or_change_the_answer",
            "do": [
                "start with the strongest boundary or dose/subgroup concern",
                "separate scope-narrowing evidence from answer-overturning evidence",
                "state update triggers in decision terms",
            ],
            "avoid": [
                "rebuilding the affirmative case",
                "repeating source hierarchy judgments except where needed to explain a boundary",
                "framing every caveat as equally important",
            ],
        },
        "source_weighting": {
            "role": "explain_how_to_read_the_sources",
            "do": [
                "translate source roles into reader trust judgments",
                "distinguish drivers, calibrators, boundary sources, and context sources",
                "explain what should move the decision and what should only narrow it",
            ],
            "avoid": [
                "restating the BLUF beyond a short reference point",
                "repeating the dose-response or subgroup discussion in full",
                "using source-role labels without explaining decision impact",
            ],
        },
        "practical_implication": {
            "role": "translate_the_read_into_action",
            "do": [
                "state the practical recommendation in ordinary decision language",
                "separate default guidance from exception handling",
                "include only enough evidence basis to make the action defensible",
            ],
            "avoid": [
                "repeating the best-current-read section",
                "listing all study statistics again",
                "opening with abstract decision-maker language",
            ],
        },
    }
    return contracts.get(section_id, contracts["answer_evidence"])
def _section_job(section_id: str, fallback: Any) -> str:
    jobs = {
        "source_weighting": "Explain the source hierarchy and source-use limits only; do not reargue the answer or preview practical advice.",
        "answer_evidence": "Make the positive case for the current read from the driver evidence; leave caveats and action translation to later sections.",
        "counterweights": "Stress-test the current read: identify what narrows it, what would change it, and what merely calibrates confidence.",
        "practical_implication": "Translate the settled answer and its limits into what guidance should say; keep evidence basis short.",
    }
    return jobs.get(section_id, str(fallback or "").strip())
def _section_focus(section_id: str) -> dict[str, Any]:
    focuses = {
        "answer_evidence": {
            "reader_question": "Why should I believe this answer rather than a flatter summary of the sources?",
            "prose_lead": "Open with the strongest evidence pattern or quantity that carries the read.",
            "lead": "Start with the evidence reason this answer is the best current read, not with a restated BLUF.",
            "use_current_read_as": "reference_for_what_the_evidence_must_explain",
            "new_value": "make the positive case for the current read from the driver evidence; leave caveats and action translation to later sections",
            "paragraph_shape": ["driver evidence and key quantity", "how guidance and empirical evidence converge on the primary answer", "brief confidence calibration without rearguing limits"],
            "stock_phrases_to_replace": [
                "The current assessment is driven by",
                "This nuanced view",
                "The evidence suggests",
            ],
        },
        "counterweights": {
            "reader_question": "What could make this answer too strong, too broad, or wrong for some uses?",
            "prose_lead": "Open with the strongest reason the answer may not generalize or may need narrower wording.",
            "lead": "Start with the most important boundary or uncertainty, not with the full bottom line.",
            "use_current_read_as": "the answer being bounded or stress-tested",
            "new_value": "stress-test the current read by identifying what narrows it, what would change it, and what merely calibrates confidence",
            "paragraph_shape": ["highest-value boundary", "subgroup or endpoint limits", "update trigger or crux threshold"],
            "stock_phrases_to_replace": [
                "The primary boundary on this assessment",
                "The current read is further bounded",
                "It is essential to",
            ],
        },
        "source_weighting": {
            "reader_question": "Which sources should carry the answer, and which ones should mostly calibrate or bound it?",
            "prose_lead": "Open with the source hierarchy that matters for trusting the answer.",
            "lead": "Start with how to weight the source base, not with a restatement of the bottom line.",
            "use_current_read_as": "reference_for_source_weighting",
            "new_value": "explain the source hierarchy and source-use limits only; do not reargue the answer or preview practical advice",
            "paragraph_shape": ["one sentence source hierarchy thesis", "why driver sources carry the answer", "why boundary/calibrator/context sources change scope rather than the core answer"],
        },
        "practical_implication": {
            "reader_question": "Given the answer and its limits, what should the decision-maker do next?",
            "prose_lead": "Open with the usable stance inside scope, then name the condition that changes application.",
            "lead": "Start with what the reader should do with the answer inside scope.",
            "use_current_read_as": "background_only",
            "new_value": "translate the settled answer and its limits into what guidance should say; keep evidence basis short",
            "paragraph_shape": ["default advice inside scope", "exceptions and monitoring conditions", "how to phrase advice without overclaiming"],
            "stock_phrases_to_replace": [
                "To avoid over-applying this answer",
                "The decision-maker should",
                "Practical Application",
            ],
        },
    }
    return focuses.get(section_id, focuses["answer_evidence"])
def _section_top_context(reader_packet: dict[str, Any], raw_section: dict[str, Any], *, section_id: str) -> dict[str, Any]:
    balanced = _dict(reader_packet.get("balanced_answer_frame"))
    bluf = _dict(reader_packet.get("bluf_contract"))
    source_ids = _section_source_ids(raw_section)
    base = {
        "decision_question": reader_packet.get("decision_question"),
        "confidence": balanced.get("confidence"),
        "must_not_overstate": balanced.get("must_not_overstate"),
        "evidence_language_contracts": _filter_language_contracts(reader_packet.get("evidence_language_contracts"), source_ids),
        "lightweight_writer_guidance": reader_packet.get("lightweight_writer_guidance"),
        "reader_judgments_to_surface": compact_reader_judgments_for_section(reader_packet.get("reader_judgment_packet"), section_id),
        "analyst_decision_logic": _section_analyst_decision_logic(reader_packet, section_id),
        "citation_registry": reader_packet.get("citation_registry"),
    }
    if section_id == "answer_evidence":
        base.update(
            {
                "current_read_reference": bluf.get("recommended_read") or balanced.get("best_current_read"),
                "main_support": balanced.get("main_support"),
                "answer_frame": reader_packet.get("answer_frame"),
            }
        )
    elif section_id == "counterweights":
        base.update(
            {
                "main_counterweight": balanced.get("main_counterweight"),
                "scope": balanced.get("scope"),
                "decision_usefulness": _counterweight_decision_usefulness(reader_packet.get("decision_usefulness")),
            }
        )
    elif section_id == "source_weighting":
        base.pop("confidence", None)
        base.update(
            {
                "source_hierarchy_thesis": raw_section.get("hierarchy_thesis"),
            }
        )
    elif section_id == "practical_implication":
        base.pop("confidence", None)
        base.update(
            {
                "practical_read": balanced.get("practical_read") or bluf.get("practical_read"),
                "scope": bluf.get("who_it_applies_to") or balanced.get("scope"),
                "main_boundary": bluf.get("main_exception_or_boundary") or balanced.get("main_counterweight"),
                "decision_usefulness": _practical_decision_usefulness(reader_packet.get("decision_usefulness")),
                "decision_action_contract": build_decision_action_contract(reader_packet),
            }
        )
    return _drop_empty(base)


def _section_source_ids(raw_section: dict[str, Any]) -> list[str]:
    return _dedupe(
        [
            *[
                source_id
                for row in _list(raw_section.get("evidence_context"))
                if isinstance(row, dict)
                for source_id in _string_list(row.get("source_ids"))
            ],
            *[
                source_id
                for row in _list(raw_section.get("retention_requirements"))
                if isinstance(row, dict)
                for source_id in _string_list(row.get("source_ids"))
            ],
            *[
                source_id
                for row in _list(raw_section.get("source_weighting"))
                if isinstance(row, dict)
                for source_id in _string_list(row.get("source_ids"))
            ],
        ]
    )


def _section_analyst_argument_moves(reader_packet: dict[str, Any], raw_section: dict[str, Any], *, section_id: str) -> list[dict[str, Any]]:
    evidence_ids = set(_section_evidence_ids(raw_section))
    rows = []
    for row in _list(reader_packet.get("analyst_argument_plan")):
        if not isinstance(row, dict):
            continue
        row_section_id = str(row.get("section_id") or "").strip() or _section_id_from_heading(str(row.get("section") or ""))
        row_evidence_ids = set(_string_list(row.get("evidence_item_ids")))
        if row_section_id == section_id or (evidence_ids and row_evidence_ids.intersection(evidence_ids)):
            rows.append(row)
    return _dedupe_rows(rows, "step_id")[:6]


def _section_decision_usefulness_moves(
    reader_packet: dict[str, Any],
    *,
    section_id: str,
    evidence_ids: list[str],
) -> dict[str, Any]:
    usefulness = _dict(reader_packet.get("decision_usefulness"))
    if not usefulness:
        return {}
    evidence_set = set(evidence_ids)

    def matching_rows(key: str, fallback_limit: int = 4) -> list[dict[str, Any]]:
        rows = [row for row in _list(usefulness.get(key)) if isinstance(row, dict)]
        matched = [
            row
            for row in rows
            if not evidence_set or set(_string_list(row.get("evidence_item_ids"))).intersection(evidence_set)
        ]
        return (matched or rows)[:fallback_limit]

    if section_id == "answer_evidence":
        return _drop_empty(
            {
                "recommended_stance": usefulness.get("recommended_stance"),
                "decision_criteria": matching_rows("decision_criteria", 4),
                "diagnostic_evidence": matching_rows("diagnostic_evidence", 4),
                "tradeoffs": matching_rows("tradeoffs", 2),
            }
        )
    if section_id == "counterweights":
        return _drop_empty(
            {
                "tradeoffs": matching_rows("tradeoffs", 4),
                "cruxes_and_thresholds": matching_rows("cruxes_and_thresholds", 4),
                "premortem": matching_rows("premortem", 4),
                "monitoring_triggers": matching_rows("monitoring_triggers", 4),
                "diagnostic_evidence": matching_rows("diagnostic_evidence", 2),
            }
        )
    if section_id == "practical_implication":
        return _drop_empty(
            {
                "recommended_stance": usefulness.get("recommended_stance"),
                "tradeoffs": matching_rows("tradeoffs", 3),
                "premortem": matching_rows("premortem", 3),
                "monitoring_triggers": matching_rows("monitoring_triggers", 3),
            }
        )
    if section_id == "source_weighting":
        return _drop_empty(
            {
                "answer_shape": usefulness.get("answer_shape"),
                "decision_criteria": matching_rows("decision_criteria", 3),
                "diagnostic_evidence": matching_rows("diagnostic_evidence", 3),
            }
        )
    return {}


def _section_analyst_decision_logic(reader_packet: dict[str, Any], section_id: str) -> dict[str, Any]:
    logic = _dict(reader_packet.get("analyst_decision_logic"))
    if not logic:
        return {}
    shared = {
        "bounded_bottom_line": logic.get("bounded_bottom_line"),
        "do_not_overstate": logic.get("do_not_overstate"),
    }
    section_fields = {
        "source_weighting": ("support_summary", "counterweight_weighting"),
        "answer_evidence": ("support_summary", "reconciled_cruxes"),
        "counterweights": ("strongest_counterweight", "counterweight_weighting", "scope_boundaries", "reconciled_cruxes"),
        "practical_implication": ("practical_implications", "scope_boundaries"),
    }.get(section_id, ())
    return _drop_empty({**shared, **{field: logic.get(field) for field in section_fields}})


def _section_priority_quantity_contracts(reader_packet: dict[str, Any], evidence_ids: list[str], section_id: str) -> list[dict[str, Any]]:
    exact = contracts_for_evidence_ids(reader_packet.get("priority_quantity_contracts"), evidence_ids)
    all_rows = _list(_dict(reader_packet.get("priority_quantity_contracts")).get("rows"))
    section_roles = _priority_quantity_roles_for_section(section_id)
    role_rows = [
        row
        for row in all_rows
        if isinstance(row, dict) and str(row.get("decision_role") or "") in section_roles
    ]
    return compact_priority_quantity_contracts_for_prompt(_dedupe_rows([*exact, *role_rows], "contract_id"), limit=10)


def _priority_quantity_roles_for_section(section_id: str) -> set[str]:
    if section_id == "counterweights":
        return {"scope_or_subgroup_boundary", "comparator_context", "biomarker_calibration"}
    if section_id == "practical_implication":
        return {"dose_boundary", "scope_or_subgroup_boundary", "comparator_context"}
    if section_id == "answer_evidence":
        return {"risk_estimate", "dose_boundary"}
    return set()


def _section_evidence_ids(raw_section: dict[str, Any]) -> list[str]:
    return _dedupe(
        [
            *[
                evidence_id
                for row in _list(raw_section.get("argument_steps"))
                if isinstance(row, dict)
                for evidence_id in _string_list(row.get("evidence_item_ids"))
            ],
            *[
                str(row.get("item_id") or "").strip()
                for row in _list(raw_section.get("evidence_context"))
                if isinstance(row, dict)
            ],
            *[
                evidence_id
                for row in _list(raw_section.get("retention_requirements"))
                if isinstance(row, dict)
                for evidence_id in _string_list(row.get("evidence_item_ids"))
            ],
            *[
                str(row.get("item_id") or row.get("requirement_id") or "").strip()
                for row in _list(raw_section.get("retention_requirements"))
                if isinstance(row, dict)
            ],
        ]
    )


def _protected_quantity_sets(raw_section: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    context_rows = _list(raw_section.get("quantity_binding_context")) or [
        *_list(raw_section.get("evidence_context")),
        *_list(raw_section.get("retention_requirements")),
    ]
    for row in context_rows:
        if not isinstance(row, dict):
            continue
        quantity_atoms = source_bound_quantity_tuples(row)
        if len(quantity_atoms) < 2:
            continue
        rows.append(
            _drop_empty(
                {
                    "item_id": row.get("item_id") or row.get("requirement_id"),
                    "claim": row.get("claim") or row.get("statement"),
                    "source_ids": row.get("source_ids"),
                    "source_bound_quantity_atoms": quantity_atoms,
                }
            )
        )
    return _dedupe_rows(rows, "item_id")[:8]


def _source_bound_atom_rows(raw_section: dict[str, Any]) -> list[dict[str, Any]]:
    binding_rows = [row for row in _list(raw_section.get("quantity_binding_context")) if isinstance(row, dict)]
    evidence_rows = [row for row in _list(raw_section.get("evidence_context")) if isinstance(row, dict)]
    requirement_rows = [row for row in _list(raw_section.get("retention_requirements")) if isinstance(row, dict)]
    if binding_rows:
        return [*binding_rows, *_without_quantities(evidence_rows), *_without_quantities(requirement_rows)]
    return [*evidence_rows, *requirement_rows]


def _model_safe_source_bound_evidence_atoms(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    atoms = []
    for atom in build_source_bound_evidence_atoms(rows, limit=14):
        cleaned = {key: value for key, value in atom.items() if key != "excluded_quantity_tuples"}
        if cleaned.get("claim") or cleaned.get("quantity_tuples"):
            atoms.append(cleaned)
    return atoms


def _quantity_collision_warnings(atoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_surface: dict[str, list[dict[str, Any]]] = {}
    for atom in atoms:
        for quantity in _list(atom.get("quantity_tuples")):
            if not isinstance(quantity, dict):
                continue
            surface = _quantity_surface_key(quantity.get("value"))
            if not surface:
                continue
            by_surface.setdefault(surface, []).append(
                _drop_empty(
                    {
                        "quantity_surface": surface,
                        "claim": atom.get("claim"),
                        "source_ids": quantity.get("source_ids") or atom.get("source_ids"),
                        "applicability_scope": quantity.get("applicability_scope") or atom.get("applicability_scope"),
                        "interpretation": quantity.get("interpretation"),
                    }
                )
            )
    warnings = []
    for surface, rows in by_surface.items():
        scopes = {_norm(str(row.get("applicability_scope") or "")) for row in rows}
        sources = {tuple(_string_list(row.get("source_ids"))) for row in rows}
        interpretations = {_norm(str(row.get("interpretation") or "")) for row in rows}
        if len(rows) > 1 and (len(scopes) > 1 or len(sources) > 1 or len(interpretations) > 1):
            warnings.append(
                {
                    "quantity_surface": surface,
                    "instruction": "Keep these entries separate; keep each quantity with its own population, endpoint, and citation.",
                    "entries": rows[:5],
                }
            )
    return warnings[:8]


def _quantity_surface_key(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"\d+(?:\.\d+)?", text)
    return match.group(0) if match else ""


def _without_quantities(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in row.items() if key != "quantities"} for row in rows]


def _filter_language_contracts(value: Any, source_ids: list[str]) -> list[dict[str, Any]]:
    rows = [row for row in _list(value) if isinstance(row, dict)]
    if not source_ids:
        return rows[:8]
    source_set = set(source_ids)
    return [row for row in rows if source_set.intersection(_string_list(row.get("source_ids")))]


def _counterweight_decision_usefulness(value: Any) -> dict[str, Any]:
    row = _dict(value)
    return _drop_empty(
        {
            "cruxes_and_thresholds": row.get("cruxes_and_thresholds"),
            "monitoring_triggers": row.get("monitoring_triggers"),
        }
    )


def _practical_decision_usefulness(value: Any) -> dict[str, Any]:
    row = _dict(value)
    return _drop_empty(
        {
            "recommended_stance": row.get("recommended_stance"),
            "tradeoffs": row.get("tradeoffs"),
            "monitoring_triggers": row.get("monitoring_triggers"),
        }
    )


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
        _dict(reader_packet.get("bluf_contract")).get("recommended_read"),
        _dict(reader_packet.get("bluf_contract")).get("one_sentence_version"),
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
    quantity_binding = _dict(canonical.get("analyst_quantity_binding_report")) or _dict(memo_ready_packet.get("analyst_quantity_binding_report"))
    priority_quantity_contracts = _dict(canonical.get("priority_quantity_contracts")) or _dict(memo_ready_packet.get("priority_quantity_contracts"))
    if not priority_quantity_contracts:
        priority_quantity_contracts = build_priority_quantity_contracts(memo_ready_packet)
    additions = _drop_empty(
        {
            "lightweight_writer_guidance": guidance,
            "decision_usefulness_packet": usefulness,
            "decision_usefulness_quality_report": quality,
            "analyst_quantity_binding_report": quantity_binding,
            "analyst_decision_logic": _dict(canonical.get("analyst_decision_logic")) or _dict(memo_ready_packet.get("analyst_decision_logic")),
            "analyst_argument_plan": _list(canonical.get("analyst_argument_plan")) or _list(memo_ready_packet.get("analyst_argument_plan")),
            "priority_quantity_contracts": priority_quantity_contracts if priority_quantity_contracts.get("rows") else {},
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
            "reader_facing_limit": row.get("reader_facing_limit"),
            "limits": row.get("what_not_to_use_it_for"),
            "evidence_item_ids": row.get("evidence_item_ids"),
            "omission_reason": row.get("omission_reason"),
        }
    )


def _compact_analyst_decision_logic(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "bounded_bottom_line": row.get("bounded_bottom_line"),
            "support_summary": row.get("support_summary"),
            "strongest_counterweight": row.get("strongest_counterweight"),
            "counterweight_weighting": row.get("counterweight_weighting"),
            "reconciled_cruxes": _string_list(row.get("reconciled_cruxes")),
            "scope_boundaries": _string_list(row.get("scope_boundaries")),
            "practical_implications": _string_list(row.get("practical_implications")),
            "do_not_overstate": _string_list(row.get("do_not_overstate")),
        }
    )


def _compact_analyst_argument_step(row: dict[str, Any]) -> dict[str, Any]:
    section = str(row.get("section") or "").strip()
    return _drop_empty(
        {
            "step_id": row.get("step_id"),
            "section": section,
            "section_id": _section_id_from_heading(section),
            "writing_goal": row.get("writing_goal"),
            "transition_from_previous": row.get("transition_from_previous"),
            "required_points": _string_list(row.get("required_points"))[:8],
            "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:12],
            "source_ids": _string_list(row.get("source_ids"))[:8],
            "source_labels": _string_list(row.get("source_labels"))[:8],
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


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}

def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}


def _dedupe_rows(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        marker = str(row.get(key) or "")
        if not marker or marker in seen:
            continue
        seen.add(marker)
        deduped.append(row)
    return deduped
