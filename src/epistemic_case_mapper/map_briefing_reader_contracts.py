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

# Public facade dependency imports.
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
from epistemic_case_mapper.map_briefing_map_utils import replace_source_ids
from epistemic_case_mapper.map_briefing_memo_slots import (
    _contains_banned_editorial_phrase,
    build_curated_evidence_packets,
    build_decision_memo_slots,
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
