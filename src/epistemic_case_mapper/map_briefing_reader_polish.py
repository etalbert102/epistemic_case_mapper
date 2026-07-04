from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from epistemic_case_mapper.map_briefing_reader_graph_seed import reader_graph_seed_decision_brief

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
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.map_briefing_memo_metadata import decision_question_lines, source_list_lines
from epistemic_case_mapper.map_briefing_practical_text import reader_facing_practical_items
from epistemic_case_mapper.map_briefing_section_structure import filter_primary_practical_actions

def _memo_slot_row_rank(row: dict[str, Any], spec: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> tuple[int, int, int, int, str]:
    claim = str(row.get("claim", ""))
    lowered = claim.lower()
    quantitative_bonus = 2 if _has_quantitative_specificity(claim) else 0
    direct_bonus = 0
    slot_id = str(spec.get("slot_id", ""))
    rank_markers = _vocabulary_marker_map(vocabulary, "memo_slot_rank_markers")
    slot_markers = list(rank_markers.get(slot_id, []))
    if slot_id.startswith("hard_outcome"):
        slot_markers.extend(rank_markers.get("hard_outcome", []))
    if any(marker in lowered for marker in slot_markers):
        direct_bonus += 2
    score = int(row.get("reader_score", 0)) + quantitative_bonus + direct_bonus
    return (-score, len(claim), -len(set(_content_terms(claim))), str(row.get("source", "")), str(row.get("claim", "")))

def _option_tradeoff_slot_claim(tradeoff: dict[str, Any], options: list[str]) -> str:
    evidence_by_option = tradeoff.get("evidence_by_option", {}) if isinstance(tradeoff.get("evidence_by_option"), dict) else {}
    if not any(isinstance(evidence_by_option.get(option), list) and evidence_by_option.get(option) for option in options):
        return ""
    label = str(tradeoff.get("label") or _option_criterion_label(str(tradeoff.get("criterion", "")))).strip()
    compared = " versus ".join(options[:2])
    clauses: list[str] = []
    for option in options[:2]:
        evidence_rows = evidence_by_option.get(option, [])
        if not isinstance(evidence_rows, list) or not evidence_rows:
            clauses.append(f"{option}: no clean mapped evidence for this criterion")
            continue
        claim = _option_claim_snippet(str(evidence_rows[0].get("claim", "")), max_chars=130)
        if not claim:
            continue
        clauses.append(f"{option}: {claim}")
    if not clauses:
        return ""
    return f"Compared {compared} on {label.lower()}: " + "; ".join(clauses) + "."

def _option_tradeoff_slot_score(tradeoff: dict[str, Any]) -> int:
    evidence_by_option = tradeoff.get("evidence_by_option", {}) if isinstance(tradeoff.get("evidence_by_option"), dict) else {}
    evidence_count = sum(
        len(rows)
        for rows in evidence_by_option.values()
        if isinstance(rows, list)
    )
    covered_options = sum(1 for rows in evidence_by_option.values() if isinstance(rows, list) and rows)
    return min(10, 4 + evidence_count + covered_options)

def _option_claim_snippet(text: str, *, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip().rstrip(".")
    if len(cleaned) <= max_chars:
        return cleaned
    words: list[str] = []
    for word in cleaned.split():
        candidate = " ".join([*words, word]).strip()
        if words and len(candidate) > max_chars:
            break
        words.append(word)
    return " ".join(words).strip(" ,;:.")

def _has_quantitative_specificity(text: str) -> bool:
    return bool(
        re.search(
            r"(?:\bHR\b|\bRR\b|\bCI\b|\bP\s*[<=>]|%|mg/dL|mmol/L|participants?|events?|n\s*=|≥|≤|<|>\s*)",
            text,
            flags=re.IGNORECASE,
        )
    )

def _slot_lookup(slot_model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(slot.get("slot_id", "")): slot
        for slot in slot_model.get("slots", []) if isinstance(slot, dict)
    }

def _slot_paragraph(
    slot_model: dict[str, Any],
    slot_ids: tuple[str, ...],
    *,
    lead: str,
    fallback_items: list[str],
    max_sentences: int,
) -> str:
    lookup = _slot_lookup(slot_model)
    sentences = [lead]
    for slot_id in slot_ids:
        slot = lookup.get(slot_id)
        if not slot:
            continue
        if slot.get("status") == "missing":
            if slot.get("required"):
                sentences.append(str(slot.get("missing_message", "The current source packet does not establish this evidence slot.")))
            continue
        slot_sentence = _memo_slot_sentence(slot)
        if slot_sentence:
            sentences.append(slot_sentence)
    if len(sentences) == 1:
        sentences.extend(fallback_items[: max_sentences - 1])
    return _join_polished_sentences(sentences, max_sentences=max_sentences)

def _memo_slot_sentence(slot: dict[str, Any]) -> str:
    rows = [row for row in slot.get("rows", []) if isinstance(row, dict)]
    if not rows:
        return ""
    label = str(slot.get("label", "Evidence"))
    clauses = []
    for row in rows[:3]:
        claim = str(row.get("claim", "")).strip().rstrip(".")
        source = str(row.get("source", "")).strip()
        if not claim:
            continue
        if source == "structured option comparison":
            source = ""
        clauses.append(claim + (f" ({source})" if source and source not in claim else ""))
    if not clauses:
        return ""
    if len(clauses) == 1:
        return f"{label}: {clauses[0]}."
    return f"{label}: " + "; ".join(clauses[:-1]) + "; and " + clauses[-1] + "."

def _build_final_reader_memo(rendered: str, scaffold: dict[str, Any]) -> str:
    confidence = _extract_confidence(rendered) or str(scaffold.get("confidence_cap") or "medium")
    decision_brief = _executive_decision_brief(rendered, scaffold)
    slot_model = scaffold.get("decision_memo_slots", {}) if isinstance(scaffold.get("decision_memo_slots"), dict) else {}
    implications = _slot_practical_implications(slot_model, scaffold=scaffold, fallback_items=_executive_implications(rendered, scaffold))
    paragraph_specs = _reader_memo_paragraph_specs(scaffold)
    default_paragraph = _slot_paragraph(
        slot_model,
        paragraph_specs["why_this_read"]["slot_ids"],
        lead=paragraph_specs["why_this_read"]["lead"],
        fallback_items=_executive_default_reasons(scaffold),
        max_sentences=5,
    )
    evidence_paragraph = _slot_paragraph(
        slot_model,
        paragraph_specs["evidence"]["slot_ids"],
        lead=paragraph_specs["evidence"]["lead"],
        fallback_items=_executive_carrying_evidence(scaffold),
        max_sentences=6,
    )
    practical_paragraph = _slot_paragraph(
        slot_model,
        paragraph_specs["practical"]["slot_ids"],
        lead=paragraph_specs["practical"]["lead"],
        fallback_items=_executive_counter_reasons(scaffold),
        max_sentences=5,
    )
    weak_paragraph = _humanized_limitations_paragraph(scaffold)
    crux_table = _compact_crux_table(rendered, scaffold)
    lines = [
        "## Decision Brief",
        "",
        *decision_question_lines(scaffold),
        decision_brief,
        "",
        f"**Confidence:** {confidence}",
        "",
        "## Practical Read",
        "",
    ]
    lines.extend(f"- {item}" for item in implications[:4])
    lines.extend(["", "## Why This Read", "", default_paragraph])
    lines.extend(["", "## Evidence Carrying the Conclusion", "", evidence_paragraph])
    lines.extend(["", "## Practical Scope and Exceptions", "", practical_paragraph])
    if crux_table:
        lines.extend(["", "## Decision Cruxes", "", crux_table])
    lines.extend(
        [
            "",
            "## Limits of the Current Map",
            "",
            weak_paragraph,
            "",
            "## Evidence Trail",
            "",
            "The structured evidence trail, decision-lever tables, coverage snapshot, and excluded extraction artifacts are in `EVIDENCE_APPENDIX.md`.",
            *source_list_lines(scaffold),
        ]
    )
    return "\n".join(lines)

def _reader_memo_paragraph_specs(scaffold: dict[str, Any]) -> dict[str, dict[str, Any]]:
    frame = scaffold.get("decision_frame", {}) if isinstance(scaffold.get("decision_frame"), dict) else {}
    if frame.get("frame_type") == "representation_decision":
        return {
            "why_this_read": {
                "slot_ids": ("main_support", "counterevidence_or_tension", "scope_conditions"),
                "lead": "The representation should preserve the live disagreement, the source roles, and the scope boundaries that make a flat bottom line misleading.",
            },
            "evidence": {
                "slot_ids": ("main_support", "counterevidence_or_tension", "evidence_type_limits"),
                "lead": "The evidence should be read by function: what supports the representation, what creates tension, and what limits the scope of the mapped slice.",
            },
            "practical": {
                "slot_ids": ("alternatives_or_comparators", "implementation_constraints", "scope_conditions"),
                "lead": "The practical use of this map is to show what a reviewer can inspect without treating the slice as a full adjudication.",
            },
        }
    if frame.get("frame_type") == "process_or_method_evaluation":
        return {
            "why_this_read": {
                "slot_ids": ("main_support", "counterevidence_or_tension"),
                "lead": "The read is mainly about process and method quality: which inference practices, debate formats, or evidential shortcuts should be trusted less after seeing this packet.",
            },
            "evidence": {
                "slot_ids": ("main_support", "counterevidence_or_tension", "evidence_type_limits"),
                "lead": "The carrying evidence separates debate-process lessons from evidence about the underlying factual dispute.",
            },
            "practical": {
                "slot_ids": ("alternatives_or_comparators", "implementation_constraints", "scope_conditions"),
                "lead": "The practical scope is bounded by what this packet can diagnose about process, method, and source role.",
            },
        }
    if _uses_nutrition_memo_profile(scaffold):
        return {
            "why_this_read": {
                "slot_ids": ("default_population", "dose_boundary", "hard_outcome_support"),
                "lead": "The cleanest evidence-backed default is bounded by the mapped population, exposure level, and direct outcome evidence.",
            },
            "evidence": {
                "slot_ids": ("hard_outcome_support", "hard_outcome_counter", "mechanism_surrogate", "study_design_limits"),
                "lead": "The evidence mix matters because direct outcomes, intervention evidence, mechanisms, and proxies answer different parts of the decision.",
            },
            "practical": {
                "slot_ids": ("comparator_substitution", "high_risk_subgroup"),
                "lead": "The practical recommendation changes most when comparators, context, or higher-risk groups enter the decision.",
            },
        }
    return {
        "why_this_read": {
            "slot_ids": ("main_support", "scope_conditions"),
            "lead": "The best-supported read is conditional: it depends on the options being compared, the setting, and the implementation conditions the evidence actually covers.",
        },
        "evidence": {
            "slot_ids": ("main_support", "counterevidence_or_tension", "evidence_type_limits", "safety_or_risk"),
            "lead": "The evidence mix should be read by function: direct support, counterevidence, proxies, guidance, and method limits should not be collapsed into one confidence signal.",
        },
        "practical": {
            "slot_ids": ("alternatives_or_comparators", "implementation_constraints", "scope_conditions"),
            "lead": "The practical decision turns on whether the mapped benefits survive the real comparator, operational constraints, and downside risks.",
        },
    }

def _slot_practical_implications(slot_model: dict[str, Any], *, scaffold: dict[str, Any], fallback_items: list[str]) -> list[str]:
    lookup = _slot_lookup(slot_model)
    frame = scaffold.get("decision_frame", {}) if isinstance(scaffold.get("decision_frame"), dict) else {}
    synthesis = _decision_synthesis_model(scaffold)
    items = [str(row.get("recommendation", "")).strip() for row in synthesis.get("recommendations", []) if isinstance(row, dict) and str(row.get("recommendation", "")).strip()]
    items.extend(str(item) for item in frame.get("practical_actions", []) if str(item).strip())
    if lookup.get("main_support", {}).get("status") == "filled":
        object_name = str(frame.get("decision_object", "decision read"))
        items.append(f"Use the available evidence as a provisional {object_name}, not as a claim that the source packet settles the whole case.")
    for slot_id, message in _practical_implication_rules():
        if lookup.get(slot_id, {}).get("status") == "filled":
            items.append(message)
    if not items:
        items = fallback_items
    items = filter_primary_practical_actions(items, scaffold)
    return reader_facing_practical_items(_dedupe([_polish_reader_sentence_block(item, max_chars=240) for item in items if item]))[:5]

def _build_final_evidence_appendix(rendered: str, scaffold: dict[str, Any]) -> str:
    curated = scaffold.get("curated_evidence_packets", {}) if isinstance(scaffold.get("curated_evidence_packets"), dict) else {}
    lines = [
        "## Evidence Appendix",
        "",
        "This appendix keeps the machinery inspectable while the main brief remains reader-facing.",
        "",
        "## Evidence Roles",
        "",
    ]
    for section, label in (
        ("main_support", "Main Support"),
        ("conflicting_evidence", "Conflicting Evidence"),
        ("scope_limits", "Scope Limits"),
        ("method_limits", "Method Limits"),
    ):
        rows = _curated_rows_for_sections(scaffold, (section,))
        if not rows:
            continue
        lines.extend([f"### {label}", ""])
        for row in rows[:5]:
            claim = str(row.get("claim", "")).strip()
            source = str(row.get("source", "")).strip()
            if claim:
                lines.append(f"- {claim}" + (f" ({source})" if source and source not in claim else ""))
        lines.append("")
    lines.extend(
        [
        "## Evidence by Decision Lever",
        "",
        ]
    )
    for packet in curated.get("packets", []) if isinstance(curated.get("packets"), list) else []:
        if not isinstance(packet, dict):
            continue
        rows = [row for row in packet.get("rows", []) if isinstance(row, dict)]
        if not rows:
            continue
        lines.extend(
            [
                f"### {packet.get('label') or _concept_label(str(packet.get('concept', '')))}",
                "",
                str(packet.get("synthesis_job", "")).strip() or "Decision-relevant evidence packet.",
                "",
                "| Evidence | Source | Role |",
                "|---|---|---|",
            ]
        )
        for row in rows:
            lines.append(
                "| "
                + " | ".join(
                    _markdown_table_cell(str(value))
                    for value in (row.get("claim", ""), row.get("source", ""), row.get("why_it_matters", ""))
                )
                + " |"
            )
        lines.append("")
    coverage = _markdown_section_with_heading(rendered, "Map Coverage Snapshot")
    if coverage:
        lines.extend([coverage, ""])
    lines.extend(_excluded_artifacts_section(curated))
    return "\n".join(lines).strip()

def _reader_clean_evidence_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "claim": _first_complete_sentences(_polish_reader_sentence_block(str(row.get("claim", "")), max_chars=0), max_sentences=1, max_chars=360),
        "source": _reader_source_name(str(row.get("source", ""))),
        "why_it_matters": _polish_reader_sentence_block(str(row.get("why_it_matters", "")), max_chars=220),
    }

def _reader_evidence_row_quality(row: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> dict[str, Any]:
    raw_claim = str(row.get("claim", "")).strip()
    cleaned = _reader_clean_evidence_row(row)
    claim = str(cleaned.get("claim", "")).strip()
    lowered = claim.lower()
    reasons: list[str] = []
    score = 0
    if len(_content_terms(claim)) < 5:
        reasons.append("too_short")
    if (
        "..." in raw_claim
        or "..." in claim
        or _contains_truncated_fragment(raw_claim)
        or _contains_truncated_fragment(claim)
        or raw_claim.startswith(("...", ".", "(", "-"))
        or claim.startswith(("...", ".", "(", "-"))
    ):
        reasons.append("fragmentary_extraction")
    if _looks_like_reference_or_citation_line(raw_claim) or _looks_like_reference_or_citation_line(claim):
        reasons.append("reference_or_citation_line")
    if _looks_like_boilerplate_disclosure(lowered) or _looks_like_publisher_or_license_boilerplate(lowered):
        reasons.append("boilerplate")
    if claim and claim[-1] in ".!?":
        score += 2
    if any(marker in lowered for marker in _vocabulary_marker_list(vocabulary, "reader_quality_bonus_markers")):
        score += 2
    if str(row.get("weight", "")) == "high":
        score += 2
    elif str(row.get("weight", "")) == "medium":
        score += 1
    return {"usable": not reasons, "reasons": reasons, "score": score}

def _looks_like_reference_or_citation_line(text: str) -> bool:
    lowered = text.lower()
    return bool(re.search(r"\bpmid:\d+|\bet al\.\s+[a-z].*\b\d{4};\d+|^\s*[A-Z][A-Za-z]+ [A-Z],", text)) or (
        lowered.count(" et al") >= 1 and bool(re.search(r"\b\d{4};\d+", lowered))
    )

def _curated_rows_for_concepts(scaffold: dict[str, Any], concepts: tuple[str, ...]) -> list[dict[str, Any]]:
    curated = scaffold.get("curated_evidence_packets", {}) if isinstance(scaffold.get("curated_evidence_packets"), dict) else {}
    rows: list[dict[str, Any]] = []
    for concept in concepts:
        for packet in curated.get("packets", []) if isinstance(curated.get("packets"), list) else []:
            if isinstance(packet, dict) and packet.get("concept") == concept:
                rows.extend([row for row in packet.get("rows", []) if isinstance(row, dict)])
    return rows

def _curated_rows_for_sections(scaffold: dict[str, Any], sections: tuple[str, ...]) -> list[dict[str, Any]]:
    curated = scaffold.get("curated_evidence_packets", {}) if isinstance(scaffold.get("curated_evidence_packets"), dict) else {}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for packet in curated.get("packets", []) if isinstance(curated.get("packets"), list) else []:
        if not isinstance(packet, dict):
            continue
        for row in packet.get("rows", []) if isinstance(packet.get("rows"), list) else []:
            if not isinstance(row, dict) or str(row.get("section", "")) not in sections:
                continue
            key = f"{row.get('source')}::{row.get('claim')}"
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows

def _synthesis_paragraph(rows: list[dict[str, Any]], *, fallback_items: list[str], lead: str, max_items: int) -> str:
    sentences = [lead]
    seen_sources: set[str] = set()
    for row in rows:
        claim = str(row.get("claim", "")).strip()
        source = str(row.get("source", "")).strip()
        if not claim:
            continue
        if source in seen_sources and len(sentences) > 2:
            continue
        seen_sources.add(source)
        source_suffix = f" ({source})" if source and source not in claim else ""
        sentences.append(claim.rstrip(".") + source_suffix + ".")
        if len(sentences) >= max_items + 1:
            break
    if len(sentences) == 1:
        sentences.extend(fallback_items[:max_items])
    return _join_polished_sentences(sentences, max_sentences=max_items + 1)

def _humanized_limitations_paragraph(scaffold: dict[str, Any]) -> str:
    issues = _string_list(scaffold.get("quality_issues"))
    readable: list[str] = []
    for issue in issues:
        lowered = issue.lower()
        if "high_claim_count" in lowered:
            readable.append("The map is dense, so the output should be read as a structured decision aid rather than as a final literature review.")
        elif "near_duplicate" in lowered:
            readable.append("The extractor produced near-duplicate claims, which can overweight repeated formulations unless curated.")
        elif "missing" in lowered:
            readable.append(_polish_reader_sentence_block(issue, max_chars=260))
    sufficiency = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    if sufficiency.get("status"):
        readable.append(f"The map sufficiency status is {str(sufficiency.get('status')).replace('_', ' ')}, so absent slots should be treated as named gaps.")
    readable.extend(_sufficiency_implications(sufficiency))
    if not readable:
        readable = _executive_weak_points(scaffold)
    return _join_polished_sentences(_dedupe(readable), max_sentences=7)

def _excluded_artifacts_section(curated: dict[str, Any]) -> list[str]:
    report = curated.get("curation_report", {}) if isinstance(curated.get("curation_report"), dict) else {}
    excluded = [row for row in report.get("excluded_rows", []) if isinstance(row, dict)]
    if not excluded:
        return ["## Extraction Artifacts Excluded From Reader Brief", "", "No evidence rows were excluded by the reader-facing curation pass."]
    lines = [
        "## Extraction Artifacts Excluded From Reader Brief",
        "",
        "These rows remain auditable but are kept out of the main memo because they are fragmentary, boilerplate-like, or citation/reference debris.",
        "",
        "| Reason | Source | Excluded text |",
        "|---|---|---|",
    ]
    for row in excluded[:12]:
        lines.append(
            "| "
            + " | ".join(
                _markdown_table_cell(str(value))
                for value in (row.get("reason", ""), row.get("source", ""), row.get("claim", ""))
            )
            + " |"
        )
    return lines

def clean_reader_briefing_text(text: str) -> str:
    lines = [_clean_reader_briefing_line(line) for line in text.splitlines()]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"\.{4,}", "...", cleaned)
    return cleaned.strip()

def clean_reader_memo_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        line = re.sub(r"\\\s*$", "", line).replace("\\|", "|")
        line = re.sub(r"^(\s*)\*\s+", r"\1- ", line)
        if not line.strip():
            lines.append("")
            continue
        if line.lstrip().startswith("|"):
            cells = [_clean_memo_table_cell(cell) for cell in line.split("|")]
            lines.append("|".join(cells))
        else:
            lines.append(_drop_ellipsis_sentences(_polish_reader_sentence_block(line, max_chars=0)))
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = _normalize_technical_acronyms(cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()

def _normalize_technical_acronyms(text: str) -> str:
    vocabulary = profile_vocabulary(infer_profile_id_from_text(text, fallback_profile_id=DEFAULT_PROFILE_ID))
    replacements = _vocabulary_string_dict(vocabulary, "display_acronyms")
    cleaned = text
    for lower, upper in replacements.items():
        cleaned = re.sub(rf"\b{lower}\b", upper, cleaned, flags=re.IGNORECASE)
    for replacement in vocabulary.get("display_regex_replacements", []):
        if not isinstance(replacement, dict):
            continue
        pattern = str(replacement.get("pattern", ""))
        value = str(replacement.get("replacement", ""))
        if pattern and value:
            cleaned = re.sub(pattern, value, cleaned, flags=re.IGNORECASE)
    return cleaned

def _clean_memo_table_cell(cell: str) -> str:
    if not cell.strip() or set(cell.strip()) <= {"-", ":"}:
        return cell
    cleaned = _drop_ellipsis_sentences(cell)
    cleaned = _normalize_reader_source_labels(cleaned)
    return f" {cleaned.strip()} "

def _drop_ellipsis_sentences(text: str) -> str:
    if "..." not in text:
        return _normalize_reader_source_labels(text)
    pieces = re.findall(r".*?(?:[.!?](?=\s+[A-Z0-9(]|\s*$)|$)", text)
    kept = [piece.strip() for piece in pieces if piece.strip() and "..." not in piece]
    if kept:
        return _normalize_reader_source_labels(" ".join(kept))
    prefix = _normalize_reader_source_labels(text.split("...", 1)[0].rstrip(" ,;:."))
    if not prefix or not prefix.endswith((".", "?", "!")):
        return "See appendix for full source-grounded detail."
    return prefix

def _normalize_reader_source_labels(text: str) -> str:
    pattern = r"\b((?:[A-Z][A-Za-z]+|AHA|AJCN|BMJ|EAS|JAHA|JAMA|PLOS|PURE)(?:\s+(?:[A-Z][A-Za-z]+|AHA|AJCN|BMJ|EAS|JAHA|JAMA|PLOS|PURE))*\s+(?:19|20)\d{2})\s+(?:Fullish|Full|Abstract|Metadata|Pubmed|PMC)\b"
    return re.sub(pattern, lambda match: _reader_source_name(match.group(0)), text)

def briefing_reader_polish_report(rendered: str, scaffold: dict[str, Any]) -> dict[str, Any]:
    word_count = len(re.findall(r"\b\w+\b", rendered))
    executive = _executive_markdown(rendered)
    appendix_present = "## Evidence Appendix" in rendered
    issues: list[dict[str, str]] = []
    if _contains_truncated_fragment(rendered):
        issues.append(
            {
                "severity": "warning",
                "issue_type": "truncated_fragment",
                "message": "The briefing still appears to contain an extraction fragment.",
            }
        )
    if "..." in executive:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "executive_contains_ellipsis",
                "message": "The reader memo contains ellipsis-truncated prose.",
            }
        )
    if not appendix_present:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "missing_evidence_appendix",
                "message": "The briefing does not separate executive prose from the detailed evidence appendix.",
            }
        )
    if _markdown_table_count(executive) > 1:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "executive_table_overload",
                "message": "The executive brief contains too many tables for a reader-first artifact.",
            }
        )
    if len(re.findall(r"\b\w+\b", executive)) > int(executive_word_target := 1500):
        issues.append(
            {
                "severity": "warning",
                "issue_type": "executive_brief_too_long",
                "message": f"The executive brief exceeds the {executive_word_target}-word readability target.",
            }
        )
    duplicate_sentence_count = _duplicate_sentence_count(executive)
    if duplicate_sentence_count > 2:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "duplicate_sentence_overload",
                "message": "The briefing repeats too many full sentences.",
            }
        )
    if "## Evidence Roles" not in rendered or "## Evidence by Decision Lever" not in rendered:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "missing_structured_evidence_section",
                "message": "The detailed evidence structure is not visible in the appendix.",
            }
        )
    decision_slots = scaffold.get("decision_memo_slots", {}) if isinstance(scaffold.get("decision_memo_slots"), dict) else {}
    slot_coverage = decision_slots.get("coverage", {}) if isinstance(decision_slots.get("coverage"), dict) else {}
    missing_memo_slots = _string_list(slot_coverage.get("missing_required_slots"))
    if missing_memo_slots:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "missing_decision_memo_slots",
                "message": "The reader memo lacks required decision slots: " + ", ".join(missing_memo_slots) + ".",
            }
        )
    concept_packets = scaffold.get("concept_evidence_packets", {}) if isinstance(scaffold.get("concept_evidence_packets"), dict) else {}
    visible_packets = 0
    for packet in concept_packets.get("packets", []) if isinstance(concept_packets.get("packets"), list) else []:
        if isinstance(packet, dict) and _rendered_mentions_any_surface_term(rendered, _string_list(packet.get("must_surface_terms"))):
            visible_packets += 1
    packet_count = len(concept_packets.get("packets", [])) if isinstance(concept_packets.get("packets"), list) else 0
    if packet_count and visible_packets < max(1, packet_count // 2):
        issues.append(
            {
                "severity": "warning",
                "issue_type": "thin_decision_lever_visibility",
                "message": "Fewer than half of retained decision-lever packets are visibly surfaced.",
            }
        )
    score = max(0, 100 - 10 * len(issues))
    return {
        "schema_id": "briefing_reader_polish_report_v1",
        "method": "deterministic_readability_lints_for_two_tier_briefings",
        "status": "polished" if not issues else "polished_with_warnings" if score >= 70 else "needs_reader_edit",
        "score": score,
        "word_count": word_count,
        "executive_word_count": len(re.findall(r"\b\w+\b", executive)),
        "table_count": _markdown_table_count(rendered),
        "executive_table_count": _markdown_table_count(executive),
        "duplicate_sentence_count": duplicate_sentence_count,
        "decision_lever_packets_visible": visible_packets,
        "decision_lever_packet_count": packet_count,
        "decision_memo_required_slot_count": slot_coverage.get("required_slot_count"),
        "decision_memo_filled_required_slot_count": slot_coverage.get("filled_required_slot_count"),
        "decision_memo_missing_required_slots": missing_memo_slots,
        "issues": issues,
    }

def _build_polished_executive_brief(rendered: str, scaffold: dict[str, Any], *, executive_word_target: int) -> str:
    decision_brief = _executive_decision_brief(rendered, scaffold)
    confidence = _extract_confidence(rendered) or str(scaffold.get("confidence_cap") or "medium")
    implications = _executive_implications(rendered, scaffold)
    default_reasons = _executive_default_reasons(scaffold)
    counter_reasons = _executive_counter_reasons(scaffold)
    carrying_evidence = _executive_carrying_evidence(scaffold)
    weak_points = _executive_weak_points(scaffold)
    crux_table = _compact_crux_table(rendered, scaffold)
    lines = [
        "## Decision Brief",
        "",
        decision_brief,
        "",
        f"**Confidence:** {confidence}",
        "",
        "## Decision Implications",
        "",
    ]
    lines.extend(f"- {item}" for item in implications[:5])
    lines.extend(["", "## Why This Is the Right Default", ""])
    lines.append(_join_polished_sentences(default_reasons, max_sentences=5))
    lines.extend(["", "## What Could Make This Wrong", ""])
    lines.append(_join_polished_sentences(counter_reasons, max_sentences=5))
    if crux_table:
        lines.extend(["", "## What Could Change the Decision", "", crux_table])
    lines.extend(["", "## Evidence Carrying the Conclusion", ""])
    lines.append(_join_polished_sentences(carrying_evidence, max_sentences=6))
    lines.extend(["", "## Where the Map Is Weak", ""])
    lines.append(_join_polished_sentences(weak_points, max_sentences=5))
    executive = "\n".join(lines)
    if len(re.findall(r"\b\w+\b", executive)) <= executive_word_target:
        return executive
    return _trim_executive_sections(executive, target_words=executive_word_target)

def _build_polished_evidence_appendix(rendered: str, scaffold: dict[str, Any]) -> str:
    sections = []
    for title in ("Evidence Roles", "Evidence by Decision Lever", "Map Coverage Snapshot", "Audit Trail"):
        section = _markdown_section_with_heading(rendered, title)
        if section:
            sections.append(_clean_appendix_section(section))
    if not sections:
        sections = [_deterministic_appendix_from_scaffold(scaffold)]
    return "\n\n".join(["## Evidence Appendix", *sections]).strip()

def _executive_decision_brief(rendered: str, scaffold: dict[str, Any]) -> str:
    frame = scaffold.get("decision_frame", {}) if isinstance(scaffold.get("decision_frame"), dict) else {}
    body = _markdown_section(rendered, "Decision Brief")
    body = re.sub(r"\*\*Confidence:\*\*[^\n]+", "", body).strip()
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", body) if paragraph.strip()]
    if paragraphs and _procedural_or_generic_opening(paragraphs[0]):
        graph_seed = reader_graph_seed_decision_brief(scaffold)
        if graph_seed:
            return graph_seed
        deterministic = _deterministic_decision_brief(scaffold)
        if deterministic and not _procedural_or_generic_opening(deterministic):
            return _polish_reader_sentence_block(deterministic, max_chars=900)
        direct = str(frame.get("direct_answer", "")).strip()
        if direct:
            return _polish_reader_sentence_block(direct, max_chars=850)
    if paragraphs:
        return _first_complete_sentences(_polish_reader_sentence_block(paragraphs[0], max_chars=0), max_sentences=3, max_chars=850)
    direct = str(frame.get("direct_answer", "")).strip()
    if direct:
        return _polish_reader_sentence_block(direct, max_chars=850)
    return _polish_reader_sentence_block(_deterministic_decision_brief(scaffold), max_chars=900)

def _procedural_or_generic_opening(text: str) -> bool:
    lowered = text.lower().strip()
    return lowered.startswith(("state ", "use this source packet as")) or "do not frame" in lowered or "evidence supports the default answer under stated conditions" in lowered

def _executive_implications(rendered: str, scaffold: dict[str, Any]) -> list[str]:
    body = _markdown_section(rendered, "Decision Implications")
    bullets = re.findall(r"^\s*[-*]\s+(.+)$", body, flags=re.MULTILINE)
    if not bullets:
        decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
        bullets = _deterministic_decision_implications(decision_model)
    return _dedupe([_polish_reader_sentence_block(item, max_chars=220) for item in bullets if item.strip()])[:6]

def _executive_default_reasons(scaffold: dict[str, Any]) -> list[str]:
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    synthesis = _decision_synthesis_model(scaffold)
    reasons = []
    default = decision_model.get("default_answer", {}) if isinstance(decision_model.get("default_answer"), dict) else {}
    if default.get("why_this_frame"):
        reasons.append(str(default["why_this_frame"]))
    reasons.extend(_synthesis_evidence_sentences(synthesis, roles=("direct_outcome", "guidance_or_practical_advice", "subgroup_or_scope"))[:3])
    reasons.extend(str(item.get("current_resolution", "")) for item in synthesis.get("central_tensions", [])[:1] if isinstance(item, dict))
    reasons.extend(_concept_packet_sentences(scaffold, preferred=("dose_or_threshold", "default_population", "hard_outcome_endpoint")))
    for row in decision_model.get("main_reasons", []) if isinstance(decision_model.get("main_reasons"), list) else []:
        if isinstance(row, dict):
            if _generic_cluster_proposition(str(row.get("proposition", ""))):
                continue
            source = _source_suffix(row.get("sources"))
            reasons.append(str(row.get("proposition", "")).strip() + source)
    return _dedupe([_polish_reader_sentence_block(item, max_chars=320) for item in reasons if item])

def _executive_counter_reasons(scaffold: dict[str, Any]) -> list[str]:
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    synthesis = _decision_synthesis_model(scaffold)
    reasons = []
    reasons.extend(str(row.get("current_read", "")) for row in synthesis.get("exceptions", [])[:3] if isinstance(row, dict) and str(row.get("current_read", "")).strip())
    reasons.extend(str(row.get("why_reasonable_people_disagree", "")) for row in synthesis.get("central_tensions", [])[:2] if isinstance(row, dict) and str(row.get("why_reasonable_people_disagree", "")).strip())
    reasons.extend(_concept_packet_sentences(scaffold, preferred=("subgroup_diabetes_or_metabolic_risk", "dietary_context_or_saturated_fat", "substitution_or_comparator")))
    for row in decision_model.get("strongest_counterarguments", []) if isinstance(decision_model.get("strongest_counterarguments"), list) else []:
        if isinstance(row, dict):
            if _generic_cluster_proposition(str(row.get("proposition", ""))):
                continue
            source = _source_suffix(row.get("sources"))
            reasons.append(str(row.get("proposition", "")).strip() + source)
    reasons.extend(_string_list(decision_model.get("what_would_change_answer"))[:3])
    return _dedupe([_polish_reader_sentence_block(item, max_chars=320) for item in reasons if item])

def _executive_carrying_evidence(scaffold: dict[str, Any]) -> list[str]:
    synthesis = _decision_synthesis_model(scaffold)
    sentences = []
    sentences.extend(_synthesis_evidence_sentences(synthesis, roles=("direct_outcome", "counterevidence_or_risk", "mechanism_or_proxy", "comparator_or_substitution"))[:5])
    sentences.extend(_concept_packet_sentences(scaffold, preferred=("study_design_cohort", "study_design_rct", "mechanism_ldl_apob", "surrogate_or_biomarker_endpoint")))
    ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    by_section = ledger.get("top_evidence_by_section", {}) if isinstance(ledger.get("top_evidence_by_section"), dict) else {}
    for section in ("main_support", "conflicting_evidence"):
        for row in by_section.get(section, [])[:2] if isinstance(by_section.get(section), list) else []:
            if isinstance(row, dict):
                claim = _first_complete_sentences(_polish_reader_sentence_block(str(row.get("claim", "")), max_chars=0), max_sentences=1, max_chars=320)
                source = str(row.get("source", "")).strip()
                if claim:
                    sentences.append(claim + (f" ({source})." if source and source not in claim else ""))
    return _dedupe(sentences)

def _executive_weak_points(scaffold: dict[str, Any]) -> list[str]:
    quality_status = str(scaffold.get("quality_status", "")).strip()
    synthesis = _decision_synthesis_model(scaffold)
    items = []
    items.extend(str(item) for item in synthesis.get("limits", [])[:3] if str(item).strip())
    sufficiency = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    if sufficiency.get("status"):
        items.append(f"The map sufficiency status is {str(sufficiency.get('status')).replace('_', ' ')}, so absence of a slot should be read as a mapped gap rather than as negative evidence.")
    if quality_status and quality_status != "unknown":
        items.append(f"The map quality status is {quality_status.replace('_', ' ')}, which caps confidence and argues against a stronger bottom line.")
    items.extend(_string_list(scaffold.get("quality_issues"))[:3])
    contract = scaffold.get("briefing_contract", {}) if isinstance(scaffold.get("briefing_contract"), dict) else {}
    answer_frame = contract.get("answer_frame", {}) if isinstance(contract.get("answer_frame"), dict) else {}
    items.extend(_string_list(answer_frame.get("why_not_stronger"))[:3])
    return _dedupe([_polish_reader_sentence_block(item, max_chars=320) for item in items if item])

def _concept_packet_sentences(scaffold: dict[str, Any], *, preferred: tuple[str, ...]) -> list[str]:
    packets = scaffold.get("concept_evidence_packets", {}) if isinstance(scaffold.get("concept_evidence_packets"), dict) else {}
    packet_rows = [packet for packet in packets.get("packets", []) if isinstance(packet, dict)]
    by_concept = {str(packet.get("concept", "")): packet for packet in packet_rows}
    sentences = []
    for concept in preferred:
        packet = by_concept.get(concept)
        if not packet:
            continue
        rows = [row for row in packet.get("rows", []) if isinstance(row, dict)]
        if not rows:
            continue
        first = rows[0]
        label = str(packet.get("label") or _concept_label(concept))
        claim = _first_complete_sentences(_polish_reader_sentence_block(str(first.get("claim", "")), max_chars=0), max_sentences=1, max_chars=340)
        source = str(first.get("source", "")).strip()
        if claim:
            sentences.append(f"{label}: {claim}" + (f" ({source})." if source and source not in claim else ""))
    return sentences

def _compact_crux_table(rendered: str, scaffold: dict[str, Any]) -> str:
    section = _markdown_section(rendered, "What Could Change the Decision")
    table_lines = [line for line in section.splitlines() if line.strip().startswith("|")]
    if len(table_lines) >= 3:
        return _clean_crux_table("\n".join(table_lines[:6]))
    synthesis = _decision_synthesis_model(scaffold)
    cruxes = [row for row in synthesis.get("cruxes", []) if isinstance(row, dict)][:3]
    if cruxes:
        return _crux_rows_to_table(cruxes, max_chars=170)
    refined = scaffold.get("refined_cruxes", {}) if isinstance(scaffold.get("refined_cruxes"), dict) else {}
    cruxes = [row for row in refined.get("cruxes", []) if isinstance(row, dict)][:3]
    if not cruxes:
        cruxes = _deterministic_top_cruxes(scaffold)[:3]
    if not cruxes:
        return ""
    return _crux_rows_to_table(cruxes, max_chars=150)

def _practical_implication_rules() -> tuple[tuple[str, str], ...]:
    return (
        ("alternatives_or_comparators", "Frame the recommendation around the actual alternatives being compared, since the answer can change with the comparator."),
        ("scope_conditions", "Keep the setting, scale, population, and intensity boundaries attached to the recommendation."),
        ("implementation_constraints", "Treat feasibility, safety, maintenance, and technical-fit constraints as part of the decision, not as afterthoughts."),
        ("evidence_type_limits", "Separate direct outcome evidence from proxy, mechanism, guidance, and implementation evidence when setting confidence."),
        ("safety_or_risk", "Make downside risks and failure modes visible before converting the evidence into action."),
        ("dose_boundary", "Treat the default answer as scoped to the mapped intensity or threshold, not to all possible exposure levels."),
        ("hard_outcome_support", "For the mapped default population, let direct outcome evidence carry more weight than indirect evidence."),
        ("mechanism_surrogate", "Keep mechanism and surrogate evidence visible because it can bound confidence without settling direct outcomes by itself."),
        ("comparator_substitution", "Frame practical advice around the relevant alternatives, since comparator evidence can change the recommendation."),
        ("high_risk_subgroup", "Do not automatically generalize the default answer to higher-risk subgroups; treat those as separate scope decisions."),
    )

def _crux_rows_to_table(cruxes: list[dict[str, Any]], *, max_chars: int) -> str:
    lines = ["| Crux | Current read | Would change if |", "|---|---|---|"]
    for row in cruxes:
        cells = (_markdown_table_cell(_polish_reader_sentence_block(str(row.get(key, "")), max_chars=max_chars)) for key in ("crux", "current_read", "would_change_if"))
        lines.append("| " + " | ".join(cells) + " |")
    return _clean_crux_table("\n".join(lines))

def _clean_crux_table(table: str) -> str:
    return table.replace("This challenges relation marks a condition that can change the interpretation of the evidence.", "This condition could change how the evidence should be interpreted.").replace("This in tension with relation marks a condition that can change the interpretation of the evidence.", "This tension could change how the evidence should be interpreted.").replace("relation marks", "indicates")

def _decision_synthesis_model(scaffold: dict[str, Any]) -> dict[str, Any]:
    value = scaffold.get("decision_synthesis_model", {})
    return value if isinstance(value, dict) else {}

def _synthesis_evidence_sentences(synthesis: dict[str, Any], *, roles: tuple[str, ...]) -> list[str]:
    lines = [line for line in synthesis.get("evidence_lines", []) if isinstance(line, dict)]
    sentences: list[str] = []
    for role in roles:
        for line in lines:
            if line.get("role") != role:
                continue
            current = str(line.get("current_read", "")).strip()
            if current:
                sentences.append(current)
    return sentences

# Explicit cross-module dependencies for compatibility facade removal.
from epistemic_case_mapper.map_briefing_decision_model import _looks_like_boilerplate_disclosure, _looks_like_publisher_or_license_boilerplate
from epistemic_case_mapper.map_briefing_evidence_partition import _option_criterion_label
from epistemic_case_mapper.map_briefing_evidence_tables import _clean_appendix_section, _clean_reader_briefing_line, _concept_label, _contains_truncated_fragment, _deterministic_appendix_from_scaffold, _duplicate_sentence_count, _executive_markdown, _extract_confidence, _first_complete_sentences, _generic_cluster_proposition, _join_polished_sentences, _markdown_section, _markdown_section_with_heading, _markdown_table_cell, _markdown_table_count, _polish_reader_sentence_block, _reader_source_name, _source_suffix, _trim_executive_sections
from epistemic_case_mapper.map_briefing_memo_slots import _uses_nutrition_memo_profile
from epistemic_case_mapper.map_briefing_pipeline import _deterministic_decision_brief, _deterministic_decision_implications, _deterministic_top_cruxes, _sufficiency_implications
from epistemic_case_mapper.map_briefing_reader_contracts import _vocabulary_marker_list, _vocabulary_marker_map, _vocabulary_string_dict
from epistemic_case_mapper.map_briefing_validation import _content_terms, _dedupe, _rendered_mentions_any_surface_term, _string_list
