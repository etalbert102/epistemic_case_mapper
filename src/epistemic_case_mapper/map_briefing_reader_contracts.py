from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from epistemic_case_mapper.classical_ml import (
    relation_edge_weight,
    tfidf_near_duplicate_pairs,
    weighted_pagerank,
)
from epistemic_case_mapper.config_profiles import (
    DEFAULT_PROFILE_ID,
    infer_profile_id_from_text,
    profile_vocabulary,
)
from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.map_briefing_final_edit_context import model_facing_reader_memo_edit_context
from epistemic_case_mapper.map_briefing_final_memo_editor import run_two_pass_reader_memo_editor
from epistemic_case_mapper.synthesis_uplift_packet import _parse_json
from epistemic_case_mapper.map_briefing_section_structure import (
    filter_primary_practical_actions,
    repair_reader_memo_sections,
)

def append_evidence_by_decision_lever(rendered: str, scaffold: dict[str, Any]) -> str:
    if "## Evidence by Decision Lever" in rendered:
        return rendered
    packets = scaffold.get("concept_evidence_packets", {})
    if not isinstance(packets, dict):
        return rendered
    packet_rows = [packet for packet in packets.get("packets", []) if isinstance(packet, dict)]
    if not packet_rows:
        return rendered
    lines = [
        rendered.rstrip(),
        "",
        "## Evidence by Decision Lever",
        "",
    ]
    for packet in packet_rows[:10]:
        label = str(packet.get("label", "")).strip() or _concept_label(str(packet.get("concept", "")))
        rows = [row for row in packet.get("rows", []) if isinstance(row, dict)]
        if not rows:
            continue
        lines.extend(
            [
                f"### {label}",
                "",
                str(packet.get("synthesis_job", "")).strip() or "State the decision-relevant contribution and caveat for this evidence family.",
                "",
                "| Evidence | Source | Role |",
                "|---|---|---|",
            ]
        )
        for row in rows[:4]:
            lines.append(
                "| "
                + " | ".join(
                    _markdown_table_cell(value)
                    for value in (
                        str(row.get("claim", "")),
                        str(row.get("source", "")),
                        str(row.get("why_it_matters", "")),
                    )
                )
                + " |"
            )
        lines.append("")
    return "\n".join(lines).rstrip()

def polish_briefing_for_reader(rendered: str, scaffold: dict[str, Any], *, executive_word_target: int = 1400) -> str:
    """Turn the map-backed packet into a judge-readable brief plus appendix.

    The polish pass may compress, reorder, and clean text, but it only uses
    statements already present in the scaffold or rendered packet.
    """
    cleaned = clean_reader_briefing_text(rendered)
    if "## Evidence Appendix" in cleaned:
        return cleaned
    executive = _build_polished_executive_brief(cleaned, scaffold, executive_word_target=executive_word_target)
    appendix = _build_polished_evidence_appendix(cleaned, scaffold)
    return clean_reader_briefing_text("\n\n".join(part for part in (executive, appendix) if part.strip()))

def compose_final_reader_memo_package(rendered: str, scaffold: dict[str, Any]) -> dict[str, Any]:
    curated_packets = build_curated_evidence_packets(scaffold)
    final_scaffold = dict(scaffold)
    final_scaffold["curated_evidence_packets"] = curated_packets
    decision_memo_slots = build_decision_memo_slots(final_scaffold, rendered=rendered)
    final_scaffold["decision_memo_slots"] = decision_memo_slots
    memo = _build_final_reader_memo(rendered, final_scaffold)
    appendix = _build_final_evidence_appendix(rendered, final_scaffold)
    return {
        "memo": clean_reader_memo_text(memo),
        "appendix": clean_reader_briefing_text(appendix),
        "curation_report": {**curated_packets.get("curation_report", {}), "decision_memo_slots": decision_memo_slots},
        "scaffold": final_scaffold,
    }

def annotate_map_with_evidence_slots(candidate_map: dict[str, Any]) -> dict[str, Any]:
    """Attach canonical evidence slots to claims without changing required schema fields."""
    enriched = json.loads(json.dumps(candidate_map))
    vocabulary = _profile_vocabulary_for_map(enriched)
    for claim in enriched.get("claims", []) if isinstance(enriched.get("claims"), list) else []:
        if isinstance(claim, dict):
            slots = _evidence_slots_for_claim(claim, vocabulary=vocabulary)
            claim["evidence_slots"] = slots
            claim["decision_slots"] = _decision_slots_for_claim(claim, vocabulary=vocabulary)
    return enriched

def _profile_id_from_payload(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("profile_id", "")).strip()

def _profile_id_for_map(candidate_map: dict[str, Any]) -> str:
    explicit = _profile_id_from_payload(candidate_map.get("epistemic_config"))
    text = _map_profile_detection_text(candidate_map)
    return infer_profile_id_from_text(text, fallback_profile_id=explicit or DEFAULT_PROFILE_ID)

def _profile_id_for_scaffold(scaffold: dict[str, Any]) -> str:
    explicit = _profile_id_from_payload(scaffold.get("epistemic_config"))
    text = _scaffold_profile_detection_text(scaffold)
    return infer_profile_id_from_text(text, fallback_profile_id=explicit or DEFAULT_PROFILE_ID)

def _profile_vocabulary_for_map(candidate_map: dict[str, Any]) -> dict[str, Any]:
    return profile_vocabulary(_profile_id_for_map(candidate_map))

def _profile_vocabulary_for_scaffold(scaffold: dict[str, Any]) -> dict[str, Any]:
    return profile_vocabulary(_profile_id_for_scaffold(scaffold))

def _vocabulary_marker_list(vocabulary: dict[str, Any] | None, key: str) -> list[str]:
    value = (vocabulary or profile_vocabulary(DEFAULT_PROFILE_ID)).get(key, [])
    if not isinstance(value, list):
        return []
    return [str(item).lower() for item in value if str(item).strip()]

def _vocabulary_string_list(vocabulary: dict[str, Any] | None, key: str) -> list[str]:
    value = (vocabulary or profile_vocabulary(DEFAULT_PROFILE_ID)).get(key, [])
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]

def _vocabulary_marker_map(vocabulary: dict[str, Any] | None, key: str) -> dict[str, list[str]]:
    value = (vocabulary or profile_vocabulary(DEFAULT_PROFILE_ID)).get(key, {})
    if not isinstance(value, dict):
        return {}
    marker_map: dict[str, list[str]] = {}
    for name, markers in value.items():
        if isinstance(markers, list):
            marker_map[str(name)] = [str(marker).lower() for marker in markers if str(marker).strip()]
    return marker_map

def _vocabulary_string_map(vocabulary: dict[str, Any] | None, key: str) -> dict[str, list[str]]:
    value = (vocabulary or profile_vocabulary(DEFAULT_PROFILE_ID)).get(key, {})
    if not isinstance(value, dict):
        return {}
    string_map: dict[str, list[str]] = {}
    for name, items in value.items():
        if isinstance(items, list):
            string_map[str(name)] = [str(item) for item in items if str(item).strip()]
    return string_map

def _vocabulary_string_dict(vocabulary: dict[str, Any] | None, key: str) -> dict[str, str]:
    value = (vocabulary or profile_vocabulary(DEFAULT_PROFILE_ID)).get(key, {})
    if not isinstance(value, dict):
        return {}
    return {str(item_key).lower(): str(item_value) for item_key, item_value in value.items() if str(item_key).strip()}

def _vocabulary_nested_marker_map(vocabulary: dict[str, Any] | None, key: str) -> dict[str, list[list[str]]]:
    value = (vocabulary or profile_vocabulary(DEFAULT_PROFILE_ID)).get(key, {})
    if not isinstance(value, dict):
        return {}
    marker_map: dict[str, list[list[str]]] = {}
    for name, groups in value.items():
        if not isinstance(groups, list):
            continue
        normalized_groups: list[list[str]] = []
        for group in groups:
            if isinstance(group, list):
                normalized_groups.append([str(marker).lower() for marker in group if str(marker).strip()])
            elif str(group).strip():
                normalized_groups.append([str(group).lower()])
        marker_map[str(name)] = normalized_groups
    return marker_map

def _map_profile_detection_text(candidate_map: dict[str, Any]) -> str:
    claims = " ".join(str(claim.get("claim", "")) for claim in _claims(candidate_map))
    title = str(candidate_map.get("title", ""))
    sources = " ".join(str(item) for item in candidate_map.get("sources", []) if isinstance(item, str))
    return " ".join([title, claims, sources])

def _scaffold_profile_detection_text(scaffold: dict[str, Any]) -> str:
    ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    claims = " ".join(str(row.get("claim", "")) for row in ledger.get("all_evidence", []) if isinstance(row, dict))
    packets = scaffold.get("concept_evidence_packets", {}) if isinstance(scaffold.get("concept_evidence_packets"), dict) else {}
    packet_text = " ".join(
        str(row.get("claim", ""))
        for packet in packets.get("packets", [])
        if isinstance(packet, dict)
        for row in packet.get("rows", [])
        if isinstance(row, dict)
    )
    crux_text = " ".join(
        " ".join(str(item.get(key, "")) for key in ("crux", "why_it_matters", "current_read", "would_change_if"))
        for item in scaffold.get("crux_candidates", [])
        if isinstance(item, dict)
    )
    return " ".join([str(scaffold.get("question", "")), claims, packet_text, crux_text])

def build_evidence_slot_ledger(evidence_ledger: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in evidence_ledger.get("all_evidence", []) if isinstance(row, dict)]
    slots: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for slot in row.get("evidence_slots", []) if isinstance(row.get("evidence_slots"), list) else []:
            slots.setdefault(str(slot), []).append(
                {
                    "claim_id": row.get("claim_id"),
                    "claim": row.get("claim"),
                    "source": row.get("source"),
                    "weight": row.get("weight"),
                    "section": row.get("section"),
                    "why_it_matters": _evidence_slot_why_it_matters(str(slot)),
                }
            )
    for slot, entries in list(slots.items()):
        slots[slot] = sorted(
            entries,
            key=lambda item: (
                -{"high": 2, "medium": 1, "low": 0}.get(str(item.get("weight")), 1),
                str(item.get("claim_id", "")),
            ),
        )[:6]
    return {
        "schema_id": "evidence_slot_ledger_v1",
        "method": "pico_grade_policy_safety_slot_classifier",
        "slot_counts": {slot: len(entries) for slot, entries in slots.items()},
        "slots": slots,
        "slot_definitions": {
            "population_scope": "Who or what setting the evidence transfers to.",
            "intervention_or_option": "The option or intervention being evaluated.",
            "comparator": "Alternative option or substitution that can change the answer.",
            "outcome_or_endpoint": "Outcome, proxy, harm, or decision endpoint.",
            "evidence_design": "Study design or source design supporting the claim.",
            "causal_identification": "Whether causal attribution is identified, confounded, or package-level.",
            "implementation_condition": "Operational condition needed for the option to work.",
            "harm_or_failure_mode": "Downside, hazard, or failure mode.",
            "cost_or_feasibility": "Resource, speed, staffing, or practical feasibility consideration.",
            "equity_or_distribution": "Distributional, subgroup, or access consequence.",
            "missing_evidence_gap": "Named absence or limitation in the current packet.",
        },
    }

def build_option_comparison(question: str, evidence_ledger: dict[str, Any], candidate_map: dict[str, Any]) -> dict[str, Any]:
    vocabulary = _profile_vocabulary_for_map(candidate_map)
    options = _question_options(question)
    if not options:
        options = _infer_options_from_evidence(evidence_ledger, vocabulary=vocabulary)
    rows = [row for row in evidence_ledger.get("all_evidence", []) if isinstance(row, dict)]
    criteria = _option_criteria_for_rows(rows)
    option_terms_by_option = _option_terms_by_option(options, vocabulary=vocabulary)
    option_rows: list[dict[str, Any]] = []
    for option in options:
        option_terms = option_terms_by_option.get(option, _option_terms(option, vocabulary=vocabulary))
        criteria_rows = []
        for criterion in criteria:
            matches = [
                row
                for row in rows
                if _row_matches_option(row, option_terms) and _row_matches_option_criterion(row, criterion)
            ]
            if not matches and criterion == "comparator_scope":
                matches = [row for row in rows if _row_matches_option_criterion(row, criterion)]
            ranked = sorted(matches, key=lambda row: (-int(row.get("score", 0)), len(str(row.get("claim", "")))))
            criteria_rows.append(
                {
                    "criterion": criterion,
                    "label": _option_criterion_label(criterion),
                    "current_read": _option_current_read(option, criterion, ranked[:2]),
                    "evidence": [_option_evidence_row(row) for row in ranked[:3]],
                }
            )
        option_rows.append(
            {
                "option": option,
                "terms": option_terms,
                "criteria": criteria_rows,
            }
        )
    tradeoffs = _option_tradeoff_rows(options, rows, option_terms_by_option, vocabulary=vocabulary)
    return {
        "schema_id": "option_comparison_v1",
        "method": "question_option_extraction_plus_slot_weighted_evidence",
        "question": question,
        "options": option_rows,
        "criteria": [{"criterion": criterion, "label": _option_criterion_label(criterion)} for criterion in criteria],
        "tradeoffs": tradeoffs,
        "summary": _option_comparison_summary(options, tradeoffs),
    }

def build_crux_contract(candidate_map: dict[str, Any], evidence_ledger: dict[str, Any], option_comparison: dict[str, Any]) -> dict[str, Any]:
    claim_lookup = {str(claim.get("claim_id", "")): claim for claim in _claims(candidate_map)}
    vocabulary = _profile_vocabulary_for_map(candidate_map)
    rows: list[dict[str, Any]] = []
    for relation in _relations(candidate_map):
        rtype = str(relation.get("relation_type", ""))
        if rtype not in {"crux_for", "in_tension_with", "challenges", "depends_on"}:
            continue
        source = claim_lookup.get(str(relation.get("source_claim", "")), {})
        target = claim_lookup.get(str(relation.get("target_claim", "")), {})
        text = " ".join(
            str(value)
            for value in (
                source.get("claim", ""),
                target.get("claim", ""),
                relation.get("rationale", ""),
            )
        )
        label = _crux_label(text, rtype, vocabulary=vocabulary)
        rows.append(
            {
                "crux": label,
                "relation_type": rtype,
                "source_claim": relation.get("source_claim"),
                "target_claim": relation.get("target_claim"),
                "why_it_matters": _crux_why_it_matters(label, text, relation, vocabulary=vocabulary),
                "current_read": _crux_current_read(label, text, vocabulary=vocabulary),
                "would_change_if": _crux_would_change_if(label, text, vocabulary=vocabulary),
                "affected_options": _crux_affected_options(label, option_comparison, vocabulary=vocabulary),
                "evidence": [
                    _claim_contract_row(source),
                    _claim_contract_row(target),
                ],
            }
        )
    rows = _dedupe_crux_rows(rows)
    if len(rows) < 3:
        rows.extend(_fallback_crux_rows_from_option_comparison(option_comparison, evidence_ledger, existing={row["crux"] for row in rows}, vocabulary=vocabulary))
    rows = _dedupe_crux_rows(rows)[:6]
    return {
        "schema_id": "crux_contract_v1",
        "method": "relation_edges_plus_option_tradeoff_cruxes",
        "crux_count": len(rows),
        "cruxes": rows,
    }

def rewrite_reader_memo_with_contract(
    memo: str,
    evidence_appendix: str,
    scaffold: dict[str, Any],
    candidate_map: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    """Use the model as constrained coherence and prose edit suggester."""
    contract = build_reader_memo_rewrite_contract(memo, scaffold)
    return run_two_pass_reader_memo_editor(
        memo,
        evidence_appendix,
        scaffold,
        candidate_map,
        contract,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        repair_candidate=repair_reader_memo_rewrite_candidate,
        validate_candidate=reader_memo_rewrite_issues,
    )

def repair_reader_memo_rewrite_candidate(markdown: str, scaffold: dict[str, Any], contract: dict[str, Any]) -> str:
    """Repair narrow model-writing defects without adding new evidence.

    This pass is intentionally conservative: it can normalize source-label
    glitches, remove duplicated prose sentences, replace internal scaffolding
    language, and repair repeated generic crux cells from the rewrite contract.
    It cannot invent new evidence rows or loosen the acceptance checks.
    """
    repaired = clean_reader_memo_text(markdown)
    repaired = _repair_reader_source_label_noise(repaired, scaffold, contract)
    repaired = _replace_internal_reader_phrases(repaired)
    repaired = _repair_overclaim_strength_language(repaired)
    repaired = _repair_unbalanced_markdown_strong(repaired)
    repaired = _repair_generic_crux_table_cells(repaired, contract)
    repaired = _drop_duplicate_reader_sentences(repaired)
    repaired = repair_reader_memo_sections(repaired, contract, scaffold)
    repaired = ensure_rewrite_confidence_visible(repaired, str(contract.get("confidence") or "medium"))
    return clean_reader_memo_text(repaired)

def build_reader_memo_rewrite_contract(memo: str, scaffold: dict[str, Any]) -> dict[str, Any]:
    slot_model = scaffold.get("decision_memo_slots", {}) if isinstance(scaffold.get("decision_memo_slots"), dict) else {}
    slots = [slot for slot in slot_model.get("slots", []) if isinstance(slot, dict)]
    required_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for slot in slots:
        for row in slot.get("rows", []) if isinstance(slot.get("rows"), list) else []:
            if not isinstance(row, dict):
                continue
            claim = str(row.get("claim", "")).strip()
            source = str(row.get("source", "")).strip()
            if not claim:
                continue
            key = f"{source}::{claim}"
            if key in seen:
                continue
            seen.add(key)
            required_rows.append(
                {
                    "slot": str(slot.get("label", "")),
                    "claim": claim,
                    "source": source,
                    "anchor_terms": _rewrite_anchor_terms(claim),
                }
            )
            if len(required_rows) >= 12:
                break
        if len(required_rows) >= 12:
            break
    sufficiency = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    required_rows = select_reader_memo_required_evidence(required_rows, scaffold)
    required_gaps = _sufficiency_implications(sufficiency)
    crux_rows = _rewrite_crux_contract_rows(scaffold)[:4]
    answer_frame = build_reader_memo_answer_frame(scaffold, required_rows)
    practical_actions = build_reader_memo_practical_actions(scaffold, required_rows)
    option_comparison = _compact_option_comparison_for_contract(scaffold.get("option_comparison", {}))
    decision_frame = scaffold.get("decision_frame", {}) if isinstance(scaffold.get("decision_frame"), dict) else {}
    return {
        "schema_id": "reader_memo_rewrite_contract_v1",
        "question": str(scaffold.get("question", "")).strip(),
        "confidence": _extract_confidence(memo) or str(scaffold.get("confidence_cap") or "medium"),
        "answer_frame": answer_frame,
        "decision_frame": decision_frame,
        "option_comparison": option_comparison,
        "practical_actions": practical_actions,
        "required_evidence": required_rows,
        "required_gaps": required_gaps,
        "required_cruxes": crux_rows,
        "editorial_lints": _reader_memo_editorial_lints(),
        "forbidden_moves": [
            "Do not introduce claims, sources, numbers, or recommendations not present in the supplied deterministic memo.",
            "Do not drop named uncertainty, missing-evidence gaps, or implementation constraints.",
            "Do not mention the internal slot labels as prose labels unless they are section headings already in the deterministic memo.",
            "Do not use internal phrases such as mapped support, map-backed read, decision role, load-bearing map distinction, preserved as a load-bearing map distinction, or not specified.",
            "Do not include an evidence appendix; rewrite only the reader memo.",
        ],
        "target_sections": [
            "Decision Brief",
            "Practical Read",
            "Why This Read",
            "Decision Cruxes",
            "Limits of the Current Map",
            "Evidence Trail",
        ],
    }

def _compact_rewrite_contract_for_report(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": contract.get("schema_id"),
        "required_evidence_count": len(contract.get("required_evidence", [])),
        "required_gap_count": len(contract.get("required_gaps", [])),
        "required_crux_count": len(contract.get("required_cruxes", [])),
        "practical_action_count": len(contract.get("practical_actions", [])),
        "option_count": len((contract.get("option_comparison") or {}).get("options", [])) if isinstance(contract.get("option_comparison"), dict) else 0,
        "tradeoff_count": len((contract.get("option_comparison") or {}).get("tradeoffs", [])) if isinstance(contract.get("option_comparison"), dict) else 0,
        "confidence": contract.get("confidence"),
    }

def _compact_option_comparison_for_contract(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"options": [], "tradeoffs": []}
    options = []
    for option in value.get("options", []) if isinstance(value.get("options"), list) else []:
        if not isinstance(option, dict):
            continue
        options.append(
            {
                "option": option.get("option"),
                "criteria": [
                    {
                        "label": row.get("label"),
                        "current_read": row.get("current_read"),
                    }
                    for row in option.get("criteria", [])[:4]
                    if isinstance(row, dict) and str(row.get("current_read", "")).strip()
                ],
            }
        )
    tradeoffs = []
    for row in value.get("tradeoffs", []) if isinstance(value.get("tradeoffs"), list) else []:
        if not isinstance(row, dict):
            continue
        tradeoffs.append(
            {
                "label": row.get("label"),
                "decision_use": row.get("decision_use"),
            }
        )
    return {"options": options[:3], "tradeoffs": tradeoffs[:6], "summary": value.get("summary")}

def select_reader_memo_required_evidence(rows: list[dict[str, str]], scaffold: dict[str, Any], *, max_rows: int = 8) -> list[dict[str, str]]:
    question = str(scaffold.get("question", "")).lower()
    vocabulary = _profile_vocabulary_for_scaffold(scaffold)
    ranked = sorted(rows, key=lambda row: _rewrite_required_evidence_rank(row, question, vocabulary))
    selected: list[dict[str, str]] = []
    seen_claims: set[str] = set()
    seen_slots: dict[str, int] = {}
    for row in ranked:
        claim = str(row.get("claim", ""))
        if not claim:
            continue
        claim_key = " ".join(_content_terms(claim)[:12])
        if claim_key in seen_claims:
            continue
        if _rewrite_row_is_secondary_alternative(row, question, vocabulary):
            continue
        slot = str(row.get("slot", ""))
        if seen_slots.get(slot, 0) >= 2 and len(selected) >= 5:
            continue
        selected.append(row)
        seen_claims.add(claim_key)
        seen_slots[slot] = seen_slots.get(slot, 0) + 1
        if len(selected) >= max_rows:
            break
    if len(selected) < min(4, len(rows)):
        for row in rows:
            if row not in selected and not _rewrite_row_is_secondary_alternative(row, question, vocabulary):
                selected.append(row)
            if len(selected) >= min(4, len(rows)):
                break
    return selected[:max_rows]

def _rewrite_required_evidence_rank(row: dict[str, str], question: str, vocabulary: dict[str, Any] | None = None) -> tuple[int, int, int, str]:
    claim = str(row.get("claim", "")).lower()
    slot = str(row.get("slot", ""))
    score = 0
    if _has_quantitative_specificity(claim):
        score += 4
    rank_markers = [str(marker).lower() for marker in (vocabulary or {}).get("rewrite_rank_markers", []) if str(marker).strip()]
    if any(marker in claim for marker in rank_markers):
        score += 4
    if slot in {"Main support", "Implementation constraints", "Safety and downside risk", "Scope and boundary conditions"}:
        score += 2
    if _rewrite_row_is_secondary_alternative(row, question, vocabulary):
        score -= 6
    return (-score, len(claim), 0 if slot == "Main support" else 1, claim)

def _rewrite_row_is_secondary_alternative(row: dict[str, str], question: str, vocabulary: dict[str, Any] | None = None) -> bool:
    claim = str(row.get("claim", "")).lower()
    markers = [str(marker).lower() for marker in (vocabulary or {}).get("secondary_alternative_markers", []) if str(marker).strip()]
    if any(marker.strip() in f" {claim} " for marker in markers):
        marker_terms = set(_content_terms(" ".join(markers)))
        question_terms = set(_content_terms(question))
        return not bool(marker_terms & question_terms)
    return False

def build_reader_memo_answer_frame(scaffold: dict[str, Any], required_rows: list[dict[str, str]]) -> dict[str, Any]:
    question = str(scaffold.get("question", "")).strip()
    lowered = f" {question.lower()} "
    vocabulary = _profile_vocabulary_for_scaffold(scaffold)
    decision_frame = scaffold.get("decision_frame", {}) if isinstance(scaffold.get("decision_frame"), dict) else {}
    comparator = _question_comparator_phrase(question)
    main_support = _first_required_claim(required_rows, slots=("Main support",))
    implementation = _first_required_claim(required_rows, slots=("Implementation constraints", "Scope and boundary conditions"))
    safety = _first_required_claim(required_rows, slots=("Safety and downside risk",))
    answer = "Give a direct, conditional recommendation using only the supplied evidence."
    for rule in vocabulary.get("answer_frame_rules", []) if isinstance(vocabulary.get("answer_frame_rules"), list) else []:
        if not isinstance(rule, dict):
            continue
        required_terms = [str(term).lower() for term in rule.get("required_question_terms", []) if str(term).strip()]
        if required_terms and all(term in lowered for term in required_terms):
            answer = str(rule.get("direct_answer", answer)).strip() or answer
            break
    else:
        if "should" in lowered and comparator:
            answer = f"Answer whether the first option should be preferred {comparator}, then state the conditions that could reverse that preference."
    if decision_frame.get("direct_answer"):
        answer = str(decision_frame["direct_answer"])
    return {
        "direct_answer": answer,
        "comparator_sentence_required": bool(comparator),
        "comparator_phrase": comparator,
        "near_term_recommendation": _short_claim_fragment(main_support, max_chars=220),
        "implementation_condition": _short_claim_fragment(implementation, max_chars=220),
        "downside_or_exception": _short_claim_fragment(safety, max_chars=220),
    }

def _question_comparator_phrase(question: str) -> str:
    lowered = question.lower()
    patterns = (
        r"\bover\b[^?.,;]{0,80}",
        r"\bversus\b[^?.,;]{0,80}",
        r"\bvs\.?\b[^?.,;]{0,80}",
        r"\brather than\b[^?.,;]{0,80}",
        r"\binstead of\b[^?.,;]{0,80}",
        r"\bcompared (?:with|to)\b[^?.,;]{0,80}",
    )
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip()
    return ""

def _first_required_claim(required_rows: list[dict[str, str]], *, slots: tuple[str, ...]) -> str:
    for row in required_rows:
        if str(row.get("slot", "")) in slots:
            return str(row.get("claim", "")).strip()
    return ""

def build_reader_memo_practical_actions(scaffold: dict[str, Any], required_rows: list[dict[str, str]]) -> list[str]:
    actions: list[str] = []
    claims = " ".join(row.get("claim", "") for row in required_rows).lower()
    vocabulary = _profile_vocabulary_for_scaffold(scaffold)
    for rule in vocabulary.get("practical_action_rules", []) if isinstance(vocabulary.get("practical_action_rules"), list) else []:
        if not isinstance(rule, dict):
            continue
        markers = [str(marker).lower() for marker in rule.get("markers", []) if str(marker).strip()]
        action = str(rule.get("action", "")).strip()
        if markers and action and any(marker in claims for marker in markers):
            actions.append(action)
    if not actions:
        for row in required_rows[:4]:
            claim = str(row.get("claim", "")).strip()
            if claim:
                actions.append(_short_claim_fragment(claim, max_chars=180))
    return _dedupe(filter_primary_practical_actions(actions, scaffold))[:5]

def _reader_memo_editorial_lints() -> list[str]:
    return [
        "Open with a concrete answer to the decision question.",
        "Use practical bullets that name actions or checks, not abstract process advice.",
        "Use human current-read cells in the crux table.",
        "Do not write: mapped support, map-backed read, decision role, load-bearing map distinction, preserved as a load-bearing map distinction, or not specified.",
        "Do not repeat the same evidence sentence in multiple sections.",
    ]

def _rewrite_anchor_terms(claim: str) -> list[str]:
    terms = _content_terms(claim)
    important = [
        term for term in terms
        if len(term) >= 4 and term not in {"should", "with", "from", "that", "this", "into", "than", "when", "where"}
    ]
    vocabulary = profile_vocabulary(infer_profile_id_from_text(claim, fallback_profile_id=DEFAULT_PROFILE_ID))
    number_terms = [
        match
        for pattern in _vocabulary_string_list(vocabulary, "anchor_term_patterns")
        for match in re.findall(pattern, claim, flags=re.IGNORECASE)
    ]
    return _dedupe([*number_terms, *important])[:6]

def _rewrite_crux_contract_rows(scaffold: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in _deterministic_top_cruxes(scaffold):
        if not isinstance(item, dict):
            continue
        crux = _clean_reader_relation_placeholders(str(item.get("crux", "")).strip())
        if not crux or "line of evidence" in crux.lower():
            continue
        rows.append(
            {
                "crux": crux,
                "why_it_matters": _clean_reader_relation_placeholders(str(item.get("why_it_matters", "")).strip()),
                "current_read": _human_current_read_for_crux(crux, item, scaffold=scaffold),
                "would_change_if": _human_would_change_if_for_crux(crux, item, scaffold=scaffold),
            }
        )
    return [row for row in rows if row.get("crux")]

def _human_current_read_for_crux(crux: str, item: dict[str, Any], scaffold: dict[str, Any] | None = None) -> str:
    text = f" {crux.lower()} "
    matched = _profile_crux_template(text, scaffold)
    if matched and str(matched.get("current_read", "")).strip():
        return str(matched["current_read"]).strip()
    current = _clean_reader_relation_placeholders(str(item.get("current_read", "")).strip())
    if not current or _contains_banned_editorial_phrase(current):
        relation_type = str(item.get("relation_type", "")).replace("_", " ").strip()
        if relation_type:
            return relation_type.capitalize()
        crux_label = _short_claim_fragment(crux, max_chars=90).rstrip(".")
        return f"The available evidence treats {crux_label.lower()} as a condition on the recommendation."
    return current

def _human_would_change_if_for_crux(crux: str, item: dict[str, Any], scaffold: dict[str, Any] | None = None) -> str:
    text = f" {crux.lower()} "
    matched = _profile_crux_template(text, scaffold)
    if matched and str(matched.get("would_change_if", "")).strip():
        return str(matched["would_change_if"]).strip()
    value = str(item.get("would_change_if", "")).strip()
    if value and not _contains_banned_editorial_phrase(value) and "weakened or reversed" not in value.lower():
        return value
    crux_label = _short_claim_fragment(crux, max_chars=90).rstrip(".")
    return f"New evidence showed that {crux_label.lower()} did not materially affect the decision."

def _profile_crux_template(text: str, scaffold: dict[str, Any] | None) -> dict[str, Any]:
    vocabulary = _profile_vocabulary_for_scaffold(scaffold or {})
    for template in vocabulary.get("crux_templates", []) if isinstance(vocabulary.get("crux_templates"), list) else []:
        if not isinstance(template, dict):
            continue
        markers = [str(marker).lower() for marker in template.get("markers", []) if str(marker).strip()]
        if markers and any(marker in text for marker in markers):
            return template
    return {}

def build_reader_memo_rewrite_prompt(memo: str, contract: dict[str, Any]) -> str:
    edit_context = model_facing_reader_memo_edit_context(contract)
    return (
        "You are a controlled prose editor for a decision-support memo.\n"
        "Do not rewrite the memo. Identify only local places where the language is awkward, repetitive, or unclear.\n"
        "Return exact JSON edit suggestions. The deterministic engine will apply only safe exact replacements.\n"
        "You must obey the evidence contract exactly. Do not add outside facts.\n\n"
        "Return only valid JSON with this schema:\n"
        "{\n"
        '  "edits": [\n'
        '    {"target": "exact original text to replace", "replacement": "cleaner replacement text", "reason": "brief reason"}\n'
        "  ]\n"
        "}\n\n"
        "Edit requirements:\n"
        "- Each `target` must be copied exactly from the deterministic memo and appear only once.\n"
        "- Keep edits local: replace one sentence, bullet, table cell, or short paragraph at a time.\n"
        "- Do not edit top-level headings, confidence labels, source labels in parentheses, evidence numbers, crux names, or required gap wording.\n"
        "- Do not remove any required evidence, source label, gap, confidence line, or crux item.\n"
        "- Prefer fewer high-value edits; return at most 8 edits.\n"
        "- If no safe local edit would improve the memo, return {\"edits\": []}.\n\n"
        "Final edit context:\n"
        f"{json.dumps(edit_context, indent=2, ensure_ascii=False)}\n\n"
        "Deterministic memo to inspect:\n"
        f"{memo.strip()}\n"
    )

def parse_reader_memo_rewrite_payload(raw: str) -> dict[str, Any] | None:
    payload = _parse_json(raw)
    if isinstance(payload, dict) and isinstance(payload.get("edits"), list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("memo_markdown"), str):
        return {"edits": [{"target": "", "replacement": "", "reason": "legacy full rewrite payload rejected"}]}
    match = re.search(r'"memo_markdown"\s*:\s*"(?P<value>.*)"\s*}\s*(?:```)?\s*$', raw.strip(), flags=re.DOTALL)
    if not match:
        return None
    return {"edits": [{"target": "", "replacement": "", "reason": "legacy full rewrite payload rejected"}]}

def _decode_tolerant_json_string(value: str) -> str:
    value = re.sub(r"\\(?![\"\\/bfnrtu])", r"\\\\", value)
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return (
            value.replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace('\\"', '"')
            .replace("\\/", "/")
            .replace("\\\\", "\\")
        )

def ensure_rewrite_confidence_visible(markdown: str, confidence: str) -> str:
    if "**Confidence:**" in markdown:
        return _replace_confidence_line(markdown, confidence)
    if "## Practical Read" in markdown:
        return markdown.replace("## Practical Read", f"**Confidence:** {confidence}\n\n## Practical Read", 1)
    return markdown.rstrip() + f"\n\n**Confidence:** {confidence}\n"



# Explicit cross-module dependencies for compatibility facade removal.
from epistemic_case_mapper.map_briefing_decision_model import (
    _decision_slots_for_claim,
    _evidence_slot_why_it_matters,
    _evidence_slots_for_claim,
    _infer_options_from_evidence,
    _option_criteria_for_rows,
    _option_terms,
    _option_terms_by_option,
    _question_options,
    _row_matches_option,
    _row_matches_option_criterion,
    _short_claim_fragment,
)
from epistemic_case_mapper.map_briefing_evidence_partition import (
    _claim_contract_row,
    _crux_affected_options,
    _crux_current_read,
    _crux_label,
    _crux_why_it_matters,
    _crux_would_change_if,
    _dedupe_crux_rows,
    _fallback_crux_rows_from_option_comparison,
    _option_comparison_summary,
    _option_criterion_label,
    _option_current_read,
    _option_evidence_row,
    _option_tradeoff_rows,
)
from epistemic_case_mapper.map_briefing_evidence_tables import _concept_label, _extract_confidence, _markdown_table_cell
from epistemic_case_mapper.map_briefing_map_utils import _claims, _relations
from epistemic_case_mapper.map_briefing_memo_slots import (
    _contains_banned_editorial_phrase,
    _drop_duplicate_reader_sentences,
    _repair_generic_crux_table_cells,
    _repair_overclaim_strength_language,
    _repair_reader_source_label_noise,
    _repair_unbalanced_markdown_strong,
    _replace_internal_reader_phrases,
    build_curated_evidence_packets,
    build_decision_memo_slots,
    reader_memo_rewrite_issues,
)
from epistemic_case_mapper.map_briefing_pipeline import _deterministic_top_cruxes, _sufficiency_implications
from epistemic_case_mapper.map_briefing_reader_polish import (
    _build_final_evidence_appendix,
    _build_final_reader_memo,
    _build_polished_evidence_appendix,
    _build_polished_executive_brief,
    _has_quantitative_specificity,
    clean_reader_briefing_text,
    clean_reader_memo_text,
)
from epistemic_case_mapper.map_briefing_validation import (
    _clean_reader_relation_placeholders,
    _content_terms,
    _dedupe,
    _replace_confidence_line,
)
