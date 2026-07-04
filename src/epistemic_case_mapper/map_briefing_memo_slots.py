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
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.map_briefing_text_cleanup import replace_internal_reader_phrases

def reader_memo_rewrite_issues(
    rewritten: str,
    original_memo: str,
    evidence_appendix: str,
    scaffold: dict[str, Any],
    candidate_map: dict[str, Any],
    contract: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    if not rewritten:
        return ["missing memo_markdown"]
    if "## Evidence Appendix" in rewritten:
        issues.append("rewrite included evidence appendix")
    if "## Decision Brief" not in rewritten:
        issues.append("rewrite dropped Decision Brief heading")
    if "**Confidence:**" not in rewritten:
        issues.append("rewrite dropped confidence line")
    if len(rewritten.split()) < 250:
        issues.append("rewrite is too short to preserve the decision contract")
    if _rewrite_introduces_domain_leakage(rewritten, scaffold):
        issues.append("rewrite introduced unrelated domain language")
    if _rewrite_has_raw_identifiers(rewritten):
        issues.append("rewrite contains raw map identifiers")
    issues.extend(_rewrite_editorial_issues(rewritten, contract))
    for row in contract.get("required_evidence", []) if isinstance(contract.get("required_evidence"), list) else []:
        if not isinstance(row, dict):
            continue
        if not _rewrite_mentions_anchor_row(rewritten, row):
            issues.append(f"rewrite dropped required evidence: {str(row.get('claim', ''))[:90]}")
    for gap in _string_list(contract.get("required_gaps")):
        if not _rewrite_mentions_gap(rewritten, gap):
            issues.append(f"rewrite dropped required gap: {gap[:90]}")
    combined = rewritten.rstrip() + "\n\n" + evidence_appendix.rstrip() + "\n"
    validation = validate_briefing_against_scaffold(combined, scaffold, candidate_map)
    if validation.get("status") == "needs_review":
        issues.append(f"rewrite failed scaffold validation: {validation.get('issues')}")
    original_sentences = _sentence_fingerprints(_markdown_without_tables(original_memo))
    rewritten_sentences = _sentence_fingerprints(_markdown_without_tables(rewritten))
    if rewritten_sentences and len(set(rewritten_sentences)) < max(3, len(rewritten_sentences) - 3):
        issues.append("rewrite still has duplicate sentence overload")
    return issues

def _markdown_without_tables(markdown: str) -> str:
    return "\n".join(line for line in markdown.splitlines() if not line.lstrip().startswith("|"))

def _rewrite_editorial_issues(rewritten: str, contract: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    lowered = rewritten.lower()
    for phrase in _banned_editorial_phrases():
        if phrase in lowered:
            issues.append(f"rewrite contains internal phrase: {phrase}")
    answer_frame = contract.get("answer_frame", {}) if isinstance(contract.get("answer_frame"), dict) else {}
    if answer_frame.get("comparator_sentence_required"):
        comparator_terms = _content_terms(str(answer_frame.get("comparator_phrase", "")))
        if comparator_terms and sum(1 for term in comparator_terms if term in lowered) < min(2, len(comparator_terms)):
            issues.append("rewrite does not explicitly address the comparator structure of the question")
    practical_actions = _string_list(contract.get("practical_actions"))
    if practical_actions:
        action_hits = sum(1 for action in practical_actions if _rewrite_mentions_action(rewritten, action))
        if action_hits < min(2, len(practical_actions)):
            issues.append("rewrite did not convert the Practical Read into concrete action checks")
    crux_section = _markdown_section_with_heading(rewritten, "Decision Cruxes")
    if crux_section and any(
        phrase in crux_section.lower()
        for phrase in (
            "not specified",
            "preserved as",
            "load-bearing map",
            "this condition changes how strongly",
            "named condition no longer affected",
            "current packet treats this condition",
            "new evidence showed the condition did not materially affect",
        )
    ):
        issues.append("rewrite crux table contains non-human current-read language")
    first_paragraph = _first_non_heading_paragraph(rewritten)
    if first_paragraph and any(phrase in first_paragraph.lower() for phrase in ("mixed or context-dependent", "decision is mixed")):
        issues.append("rewrite opens with generic uncertainty instead of a direct answer")
    return issues

def _banned_editorial_phrases() -> tuple[str, ...]:
    return (
        "mapped support",
        "map-backed read",
        "map-backed default",
        "decision role",
        "load-bearing map distinction",
        "preserved as a load-bearing",
        "not specified",
    )

def _contains_banned_editorial_phrase(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _banned_editorial_phrases())

def _replace_internal_reader_phrases(text: str) -> str:
    return replace_internal_reader_phrases(text)

def _repair_unbalanced_markdown_strong(text: str) -> str:
    repaired: list[str] = []
    for line in text.splitlines():
        if line.count("**") % 2:
            line = line.replace("**", "")
        repaired.append(line)
    return "\n".join(repaired)

def _repair_overclaim_strength_language(text: str) -> str:
    replacements = {
        "Proven Safety Impact": "Mapped Safety Signal",
        "Proven Outcome": "Mapped Outcome",
        "proven safety impact": "mapped safety signal",
        "proven outcome": "mapped outcome",
        "significant safety benefits": "source-supported safety benefits",
        "significant benefit": "source-supported benefit",
        "significantly reduce": "reduce",
        "significantly reduced": "reduced",
        "significant reduction": "mapped reduction",
        "proven benefit": "source-supported benefit",
        "proven effective": "supported in the mapped evidence",
        "proven safe": "not established as risk-free by this packet",
        "no risk": "no established risk-free finding",
        "clearly safe": "not established as risk-free by this packet",
    }
    cleaned = text
    for phrase, replacement in replacements.items():
        cleaned = re.sub(re.escape(phrase), replacement, cleaned, flags=re.IGNORECASE)
    return cleaned

def _repair_reader_source_label_noise(text: str, scaffold: dict[str, Any], contract: dict[str, Any]) -> str:
    source_names = set()
    source_lookup = scaffold.get("source_display_names", {}) if isinstance(scaffold.get("source_display_names"), dict) else {}
    source_names.update(str(value).strip() for value in source_lookup.values() if str(value).strip())
    for row in contract.get("required_evidence", []) if isinstance(contract.get("required_evidence"), list) else []:
        if isinstance(row, dict) and str(row.get("source", "")).strip():
            source_names.add(str(row.get("source", "")).strip())
    if not source_names:
        return text

    cleaned = text
    for source in sorted(source_names, key=len, reverse=True):
        source = _reader_source_name(source)
        variants = _source_label_noise_variants(source)
        for variant in variants:
            if variant and variant != source:
                cleaned = re.sub(rf"\b{re.escape(variant)}\b", source, cleaned)
    cleaned = _repair_near_miss_parenthetical_sources(cleaned, {_reader_source_name(source) for source in source_names})
    cleaned = re.sub(r"\(([^()\n]*_[^()\n]*)\)", lambda match: "(" + _dedupe_adjacent_words(match.group(1).replace("_", " ")) + ")", cleaned)
    return cleaned

def _source_label_noise_variants(source: str) -> list[str]:
    words = source.split()
    variants = {source.replace(" ", "_")}
    if len(words) >= 2:
        for index in range(len(words) - 1):
            duplicated = words[: index + 1] + words[index:] 
            variants.add(" ".join(duplicated))
            variants.add("_".join(duplicated))
    return sorted(variants, key=len, reverse=True)

def _repair_near_miss_parenthetical_sources(text: str, source_names: set[str]) -> str:
    sources = [source for source in source_names if source]
    if not sources:
        return text

    def replace(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        if not label or ";" in label or "," in label:
            return match.group(0)
        repaired = _nearest_source_label(label, sources)
        if not repaired:
            return match.group(0)
        return f"({repaired})"

    return re.sub(r"\(([^()\n]{4,90})\)", replace, text)

def _nearest_source_label(label: str, sources: list[str]) -> str:
    normalized_label = _normalize_source_label(label)
    best_source = ""
    best_score = 0.0
    for source in sources:
        normalized_source = _normalize_source_label(source)
        if normalized_label == normalized_source:
            return source
        token_overlap = _source_label_token_overlap(normalized_label, normalized_source)
        if token_overlap < 0.6:
            continue
        score = SequenceMatcher(None, normalized_label, normalized_source).ratio()
        if score > best_score:
            best_score = score
            best_source = source
    return best_source if best_score >= 0.84 else ""

def _normalize_source_label(label: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", label.lower())).strip()

def _source_label_token_overlap(left: str, right: str) -> float:
    left_terms = set(left.split())
    right_terms = set(right.split())
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / max(1, min(len(left_terms), len(right_terms)))

def _dedupe_adjacent_words(text: str) -> str:
    words = text.split()
    kept: list[str] = []
    for word in words:
        if kept and kept[-1].lower().strip(".,;:") == word.lower().strip(".,;:"):
            continue
        kept.append(word)
    return " ".join(kept)

def _repair_generic_crux_table_cells(text: str, contract: dict[str, Any]) -> str:
    cruxes = [row for row in contract.get("required_cruxes", []) if isinstance(row, dict)]
    if not cruxes or "| Crux |" not in text:
        return text
    lines = text.splitlines()
    repaired_lines: list[str] = []
    for line in lines:
        if not line.lstrip().startswith("|") or line.count("|") < 4:
            repaired_lines.append(line)
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0].lower() in {"crux", "---"} or set(cells[0]) <= {"-", ":"}:
            repaired_lines.append(line)
            continue
        matching = _matching_crux_contract(cells[0], cruxes)
        if matching:
            if _is_generic_crux_cell(cells[2]):
                cells[2] = _human_current_read_for_crux(str(matching.get("crux", "")), matching)
            if _is_generic_crux_cell(cells[3]):
                cells[3] = _human_would_change_if_for_crux(str(matching.get("crux", "")), matching)
            line = "| " + " | ".join(_markdown_table_cell(cell) for cell in cells) + " |"
        repaired_lines.append(line)
    return "\n".join(repaired_lines)

def _matching_crux_contract(crux_text: str, cruxes: list[dict[str, Any]]) -> dict[str, Any] | None:
    terms = set(_content_terms(crux_text))
    if not terms:
        return None
    best: tuple[int, dict[str, Any] | None] = (0, None)
    for row in cruxes:
        row_terms = set(_content_terms(str(row.get("crux", ""))))
        overlap = len(terms & row_terms)
        if overlap > best[0]:
            best = (overlap, row)
    return best[1] if best[0] >= 1 else None

def _is_generic_crux_cell(value: str) -> bool:
    lowered = value.lower()
    return any(
        phrase in lowered
        for phrase in (
            "this condition changes how strongly",
            "named condition no longer affected",
            "preserved as",
            "not specified",
            "load-bearing map",
        )
    )

def _drop_duplicate_reader_sentences(text: str) -> str:
    lines = text.splitlines()
    seen: set[str] = set()
    cleaned_lines: list[str] = []
    current_heading = ""
    for line in lines:
        stripped = line.strip()
        heading_match = re.match(r"^##\s+(.+?)\s*$", stripped)
        if heading_match:
            current_heading = heading_match.group(1).strip().lower()
        if not stripped or stripped.startswith("#") or stripped.startswith("|"):
            cleaned_lines.append(line)
            continue
        prefix = ""
        body = line
        bullet_match = re.match(r"^(\s*[-*]\s+)(.*)$", line)
        if bullet_match:
            if current_heading == "practical read":
                cleaned_lines.append(line)
                continue
            prefix = "- "
            body = bullet_match.group(2)
        sentences = re.findall(r".*?(?:[.!?](?=\s+[A-Z0-9(]|\s*$)|$)", body)
        kept: list[str] = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            fps = _sentence_fingerprints(sentence)
            fp = fps[0] if fps else ""
            if fp and fp in seen:
                continue
            if fp:
                seen.add(fp)
            kept.append(sentence)
        if kept:
            cleaned_lines.append(prefix + " ".join(kept) if prefix else " ".join(kept))
        elif not stripped:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)

def _rewrite_mentions_action(rewritten: str, action: str) -> bool:
    lowered = rewritten.lower()
    terms = [term for term in _content_terms(action) if len(term) >= 4]
    if not terms:
        return True
    return sum(1 for term in terms[:6] if term in lowered) >= min(2, len(terms))

def _first_non_heading_paragraph(markdown: str) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", markdown) if part.strip()]
    for paragraph in paragraphs:
        if paragraph.startswith("#") or paragraph.startswith("|") or paragraph.startswith("- ") or paragraph.startswith("* "):
            continue
        return paragraph
    return ""

def _rewrite_introduces_domain_leakage(text: str, scaffold: dict[str, Any]) -> bool:
    if _uses_nutrition_memo_profile(scaffold):
        return False
    lowered = text.lower()
    nutrition_terms = profile_vocabulary("biomedical_nutrition_case").get("domain_leakage_terms", [])
    return any(str(marker).lower() in lowered for marker in nutrition_terms if str(marker).strip())

def _rewrite_has_raw_identifiers(text: str) -> bool:
    return any(
        re.search(pattern, text)
        for pattern in (
            r"\b[A-Za-z0-9_\-]+_c\d{3,}\b",
            r"\b[A-Za-z0-9_\-]+_r\d{3,}\b",
            r"\bClaim [A-Z]\b",
            r"\bClaim [cC]?\d{3,}\b",
        )
    )

def _rewrite_mentions_anchor_row(text: str, row: dict[str, Any]) -> bool:
    lowered = text.lower()
    source = str(row.get("source", "")).strip().lower()
    terms = [str(term).lower() for term in row.get("anchor_terms", []) if isinstance(term, str)]
    if _is_synthetic_rewrite_source(source):
        return _rewrite_mentions_synthetic_anchor_row(lowered, row, terms)
    source_ok = not source or source in lowered
    if not terms:
        return source_ok
    hits = sum(1 for term in terms if term.lower() in lowered)
    required = 1 if len(terms) <= 2 else 2
    return source_ok and hits >= required

def _is_synthetic_rewrite_source(source: str) -> bool:
    return source in {"structured option comparison"}

def _rewrite_mentions_synthetic_anchor_row(lowered_text: str, row: dict[str, Any], terms: list[str]) -> bool:
    if not terms:
        return True
    hits = sum(1 for term in terms if term in lowered_text)
    required = min(3, max(2, len(terms) // 2))
    if hits < required:
        return False
    claim = str(row.get("claim", "")).lower()
    if "compared " in claim or " versus " in claim or " vs " in claim:
        return _rewrite_mentions_comparison_sides(lowered_text, claim)
    return True

def _rewrite_mentions_comparison_sides(lowered_text: str, claim: str) -> bool:
    match = re.search(
        r"\bcompared\s+(?P<a>.+?)\s+(?:versus|vs\.?|over|rather than|instead of)\s+(?P<b>.+?)\s+on\b",
        claim,
    )
    if not match:
        return True
    side_a = _comparison_side_terms(match.group("a"))
    side_b = _comparison_side_terms(match.group("b"))
    return _mentions_any_term(lowered_text, side_a) and _mentions_any_term(lowered_text, side_b)

def _comparison_side_terms(text: str) -> list[str]:
    return [
        term
        for term in _content_terms(text)
        if len(term) >= 4 and term not in {"compared", "versus", "rather", "instead", "with", "over"}
    ][:4]

def _mentions_any_term(lowered_text: str, terms: list[str]) -> bool:
    return bool(terms) and any(term in lowered_text for term in terms)

def _rewrite_mentions_gap(text: str, gap: str) -> bool:
    lowered = text.lower()
    gap_terms = [term for term in _content_terms(gap) if len(term) >= 6]
    if not gap_terms:
        return True
    hits = sum(1 for term in gap_terms[:6] if term in lowered)
    return hits >= min(2, len(gap_terms))

def _sentence_fingerprints(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip())
    fingerprints = []
    for sentence in sentences:
        terms = _content_terms(sentence)
        if len(terms) >= 5:
            fingerprints.append(" ".join(terms[:12]))
    return fingerprints

def build_curated_evidence_packets(scaffold: dict[str, Any], *, rows_per_packet: int = 3) -> dict[str, Any]:
    source_counts: dict[str, int] = {}
    vocabulary = _profile_vocabulary_for_scaffold(scaffold)
    packets_in = scaffold.get("concept_evidence_packets", {}) if isinstance(scaffold.get("concept_evidence_packets"), dict) else {}
    curated_packets: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for packet in packets_in.get("packets", []) if isinstance(packets_in.get("packets"), list) else []:
        if not isinstance(packet, dict):
            continue
        good_rows: list[dict[str, Any]] = []
        concept = str(packet.get("concept", ""))
        for row in packet.get("rows", []) if isinstance(packet.get("rows"), list) else []:
            if not isinstance(row, dict):
                continue
            quality = _reader_evidence_row_quality(row, vocabulary=vocabulary)
            clean_row = _reader_clean_evidence_row(row)
            if not quality["usable"]:
                excluded.append(
                    {
                        "concept": concept,
                        "source": str(clean_row.get("source", "")),
                        "claim": str(row.get("claim", "")),
                        "reason": ", ".join(quality["reasons"]),
                    }
                )
                continue
            source = str(clean_row.get("source", ""))
            source_penalty = source_counts.get(source, 0)
            clean_row["reader_score"] = int(row.get("score", 0)) + int(quality["score"]) - source_penalty
            good_rows.append(clean_row)
        good_rows.sort(key=lambda item: (-int(item.get("reader_score", 0)), str(item.get("source", "")), str(item.get("claim", ""))))
        selected: list[dict[str, Any]] = []
        packet_sources: set[str] = set()
        for row in good_rows:
            source = str(row.get("source", ""))
            if source in packet_sources and len(good_rows) > rows_per_packet:
                continue
            selected.append(row)
            packet_sources.add(source)
            source_counts[source] = source_counts.get(source, 0) + 1
            if len(selected) >= rows_per_packet:
                break
        if selected:
            curated_packets.append(
                {
                    "concept": concept,
                    "label": str(packet.get("label") or _concept_label(concept)),
                    "synthesis_job": str(packet.get("synthesis_job", "")),
                    "must_surface_terms": packet.get("must_surface_terms", []),
                    "rows": selected,
                }
            )
    return {
        "schema_id": "curated_evidence_packets_v1",
        "method": "readability_directness_source_diversity_filter",
        "packets": curated_packets,
        "curation_report": {
            "schema_id": "evidence_curation_report_v1",
            "packet_count": len(curated_packets),
            "selected_row_count": sum(len(packet.get("rows", [])) for packet in curated_packets),
            "excluded_row_count": len(excluded),
            "excluded_rows": excluded[:40],
        },
    }

def build_decision_memo_slots(scaffold: dict[str, Any], *, rendered: str = "") -> dict[str, Any]:
    slots: list[dict[str, Any]] = []
    vocabulary = _profile_vocabulary_for_scaffold(scaffold)
    for spec in _decision_memo_slot_specs(scaffold):
        rows = _candidate_rows_for_memo_slot(scaffold, spec, vocabulary=vocabulary)
        selected = sorted(rows, key=lambda row: _memo_slot_row_rank(row, spec, vocabulary=vocabulary))[: int(spec.get("max_rows", 2))]
        slots.append(
            {
                "slot_id": spec["slot_id"],
                "label": spec["label"],
                "job": spec["job"],
                "required": bool(spec.get("required", True)),
                "status": "filled" if selected else "missing",
                "missing_message": spec.get("missing_message", "The current source packet does not establish clean evidence for this slot."),
                "rows": selected,
            }
        )
    crux_table = _compact_crux_table(rendered, scaffold)
    return {
        "schema_id": "decision_memo_slots_v1",
        "method": "required_decision_slot_coverage_from_curated_evidence",
        "slots": slots,
        "coverage": {
            "required_slot_count": sum(1 for slot in slots if slot.get("required")),
            "filled_required_slot_count": sum(1 for slot in slots if slot.get("required") and slot.get("status") == "filled"),
            "missing_required_slots": [slot["slot_id"] for slot in slots if slot.get("required") and slot.get("status") != "filled"],
            "has_crux_table": bool(crux_table),
        },
    }

def _decision_memo_slot_specs(scaffold: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Build reader-memo obligations from the question and observed map concepts."""
    if _uses_nutrition_memo_profile(scaffold):
        return _NUTRITION_DECISION_MEMO_SLOT_SPECS
    sufficiency = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    profile = sufficiency.get("question_profile", {}) if isinstance(sufficiency.get("question_profile"), dict) else {}
    expected_slots = set(_string_list(profile.get("expected_decision_slots")))
    question = f" {re.sub(r'\\s+', ' ', str(scaffold.get('question', '')).lower())} "
    asks_comparison = any(marker in question for marker in (" over ", " versus ", " vs ", " compared", " rather than ", " instead of "))
    asks_action = any(marker in question for marker in (" should ", " prioritize", " recommend", " use ", " adopt ", " implement ", " decision "))
    return (
        {
            "slot_id": "main_support",
            "label": "Main support",
            "job": "Surface the evidence that most directly supports the current read.",
            "concepts": (),
            "sections": ("main_support",),
            "max_rows": 3,
            "required": True,
            "missing_message": "The current source packet does not establish clean evidence supporting a default answer.",
        },
        {
            "slot_id": "counterevidence_or_tension",
            "label": "Counterevidence or tension",
            "job": "Surface contrary evidence, tensions, or the strongest live counterposition.",
            "concepts": (),
            "sections": ("conflicting_evidence",),
            "max_rows": 3,
            "required": False,
            "missing_message": "The current source packet does not establish clean counterevidence or tensions.",
        },
        {
            "slot_id": "scope_conditions",
            "label": "Scope and boundary conditions",
            "job": "State the setting, population, scale, intensity, or threshold where the read applies.",
            "concepts": ("default_population", "dose_or_threshold", "technical_performance_or_capacity", "setting_or_context"),
            "sections": ("scope_limits", "main_support", "method_limits"),
            "max_rows": 3,
            "required": bool({"default_population", "dose_or_intensity_threshold"} & expected_slots) or asks_action,
            "missing_message": "The current source packet does not establish clean scope, setting, or intensity boundaries.",
        },
        {
            "slot_id": "alternatives_or_comparators",
            "label": "Alternatives and comparators",
            "job": "State how the read changes across the options being compared.",
            "concepts": ("substitution_or_comparator", "alternative_or_comparator"),
            "sections": ("main_support", "conflicting_evidence", "scope_limits", "method_limits"),
            "max_rows": 3,
            "required": "substitution_or_comparator" in expected_slots or asks_comparison,
            "missing_message": "The current source packet does not establish clean comparator evidence for the named alternatives.",
        },
        {
            "slot_id": "implementation_constraints",
            "label": "Implementation constraints",
            "job": "Surface feasibility, safety, operational, policy, or technical conditions that gate action.",
            "concepts": ("implementation_constraint", "technical_performance_or_capacity", "safety_or_adverse_effect", "guideline_or_policy"),
            "sections": ("method_limits", "scope_limits", "main_support", "conflicting_evidence"),
            "max_rows": 4,
            "required": asks_action or "practical_recommendation" in expected_slots,
            "missing_message": "The current source packet does not establish clean implementation constraints.",
        },
        {
            "slot_id": "evidence_type_limits",
            "label": "Evidence type and outcome limits",
            "job": "Separate direct outcomes from proxies, mechanisms, intervention results, guidance, and method limits.",
            "concepts": (
                "hard_outcome_endpoint",
                "surrogate_or_biomarker_endpoint",
                "mechanism_or_causal_path",
                "study_design_rct",
                "study_design_cohort",
                "guideline_or_policy",
            ),
            "sections": ("method_limits", "main_support", "scope_limits", "conflicting_evidence"),
            "max_rows": 4,
            "required": True,
            "missing_message": "The current source packet does not establish clean evidence-type or outcome limitations.",
        },
        {
            "slot_id": "safety_or_risk",
            "label": "Safety and downside risk",
            "job": "Surface risks, harms, or failure modes that could change the practical recommendation.",
            "concepts": ("safety_or_adverse_effect", "hard_outcome_endpoint"),
            "sections": ("conflicting_evidence", "method_limits", "scope_limits", "main_support"),
            "max_rows": 2,
            "required": False,
            "missing_message": "The current source packet does not establish clean downside-risk evidence.",
        },
    )

def _uses_nutrition_memo_profile(scaffold: dict[str, Any]) -> bool:
    return _profile_id_for_scaffold(scaffold) == "biomedical_nutrition_case"

_NUTRITION_DECISION_MEMO_SLOT_SPECS = (
    {
        "slot_id": "default_population",
        "label": "Default population",
        "job": "State who inherits the default answer.",
        "concepts": ("default_population",),
        "sections": ("scope_limits", "main_support"),
        "max_rows": 1,
        "required": True,
        "missing_message": "The current source packet does not establish a clean default-population boundary.",
    },
    {
        "slot_id": "dose_boundary",
        "label": "Dose boundary",
        "job": "State the intake level or threshold the answer applies to.",
        "concepts": ("dose_or_threshold",),
        "sections": ("main_support", "scope_limits"),
        "max_rows": 1,
        "required": True,
        "missing_message": "The current source packet does not establish a clean dose or intensity boundary.",
    },
    {
        "slot_id": "hard_outcome_support",
        "label": "Hard-outcome support",
        "job": "Surface direct outcome evidence that supports the default answer.",
        "concepts": ("hard_outcome_endpoint", "study_design_cohort"),
        "sections": ("main_support",),
        "max_rows": 2,
        "required": True,
        "missing_message": "The map lacks clean hard-outcome support for the default answer.",
    },
    {
        "slot_id": "hard_outcome_counter",
        "label": "Hard-outcome counterevidence",
        "job": "Surface outcome evidence that pushes against the default answer.",
        "concepts": ("hard_outcome_endpoint", "study_design_cohort"),
        "sections": ("conflicting_evidence",),
        "max_rows": 2,
        "required": True,
        "missing_message": "The map lacks clean hard-outcome counterevidence.",
    },
    {
        "slot_id": "mechanism_surrogate",
        "label": "Mechanism and surrogate evidence",
        "job": "Explain biomarkers or mechanisms and what they cannot settle.",
        "concepts": ("mechanism_ldl_apob", "surrogate_or_biomarker_endpoint", "dietary_context_or_saturated_fat"),
        "sections": ("main_support", "conflicting_evidence", "method_limits", "scope_limits"),
        "max_rows": 3,
        "required": True,
        "missing_message": "The map lacks clean mechanism or surrogate-endpoint evidence.",
    },
    {
        "slot_id": "comparator_substitution",
        "label": "Comparator or substitution",
        "job": "State how replacement foods or comparators change the practical advice.",
        "concepts": ("substitution_or_comparator",),
        "sections": ("main_support", "conflicting_evidence", "method_limits", "scope_limits"),
        "max_rows": 2,
        "required": True,
        "missing_message": "The map lacks clean comparator or substitution evidence.",
    },
    {
        "slot_id": "high_risk_subgroup",
        "label": "High-risk subgroup",
        "job": "State who should not inherit the default answer without extra caution.",
        "concepts": ("subgroup_diabetes_or_metabolic_risk", "subgroup_fh_hyper_responder"),
        "sections": ("scope_limits", "conflicting_evidence", "method_limits", "main_support"),
        "max_rows": 2,
        "required": True,
        "missing_message": "The map lacks clean high-risk subgroup evidence.",
    },
    {
        "slot_id": "study_design_limits",
        "label": "Study-design limits",
        "job": "Distinguish hard outcomes from RCT/intervention or biomarker evidence.",
        "concepts": ("study_design_rct", "study_design_cohort"),
        "sections": ("method_limits", "main_support", "scope_limits"),
        "max_rows": 2,
        "required": False,
        "missing_message": "The current source packet does not establish clean study-design limitations.",
    },
)

def _candidate_rows_for_memo_slot(scaffold: dict[str, Any], spec: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    concepts = tuple(str(item) for item in spec.get("concepts", ()))
    sections = tuple(str(item) for item in spec.get("sections", ()))
    curated = scaffold.get("curated_evidence_packets", {}) if isinstance(scaffold.get("curated_evidence_packets"), dict) else {}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for packet in curated.get("packets", []) if isinstance(curated.get("packets"), list) else []:
        if not isinstance(packet, dict):
            continue
        if concepts and str(packet.get("concept", "")) not in concepts:
            continue
        for row in packet.get("rows", []) if isinstance(packet.get("rows"), list) else []:
            if not isinstance(row, dict):
                continue
            if sections and str(row.get("section", "")) not in sections:
                continue
            if not _row_matches_memo_slot_direction(row, spec, vocabulary=vocabulary):
                continue
            key = f"{row.get('source')}::{row.get('claim')}"
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    if rows:
        return rows
    option_rows = _option_rows_for_memo_slot(scaffold, spec, vocabulary=vocabulary)
    if option_rows:
        return option_rows
    return _fallback_rows_for_memo_slot(scaffold, spec, vocabulary=vocabulary)

def _fallback_rows_for_memo_slot(scaffold: dict[str, Any], spec: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    concepts = set(str(item) for item in spec.get("concepts", ()))
    sections = set(str(item) for item in spec.get("sections", ()))
    ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    rows: list[dict[str, Any]] = []
    for row in ledger.get("all_evidence", []) if isinstance(ledger.get("all_evidence"), list) else []:
        if not isinstance(row, dict):
            continue
        row_concepts = set(str(item) for item in row.get("decision_concepts", []) if isinstance(item, str))
        if concepts and not row_concepts.intersection(concepts):
            continue
        if sections and str(row.get("section", "")) not in sections:
            continue
        clean = _reader_clean_evidence_row(row)
        quality = _reader_evidence_row_quality(row, vocabulary=vocabulary)
        if quality["usable"] and _row_matches_memo_slot_direction(clean, spec, vocabulary=vocabulary):
            clean["reader_score"] = int(row.get("score", 0)) + int(quality["score"])
            rows.append(clean)
    return rows

def _option_rows_for_memo_slot(scaffold: dict[str, Any], spec: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    slot_id = str(spec.get("slot_id", ""))
    if slot_id not in {"alternatives_or_comparators", "comparator_substitution"}:
        return []
    option_comparison = scaffold.get("option_comparison", {}) if isinstance(scaffold.get("option_comparison"), dict) else {}
    options = [str(row.get("option", "")).strip() for row in option_comparison.get("options", []) if isinstance(row, dict) and str(row.get("option", "")).strip()]
    if len(options) < 2:
        return []
    rows: list[dict[str, Any]] = []
    for tradeoff in option_comparison.get("tradeoffs", []) if isinstance(option_comparison.get("tradeoffs"), list) else []:
        if not isinstance(tradeoff, dict):
            continue
        claim = _option_tradeoff_slot_claim(tradeoff, options)
        if not claim:
            continue
        rows.append(
            {
                "claim": claim,
                "source": "structured option comparison",
                "section": "main_support",
                "weight": "medium",
                "score": _option_tradeoff_slot_score(tradeoff),
                "reader_score": _option_tradeoff_slot_score(tradeoff) + 4,
                "decision_concepts": ["alternative_or_comparator", "substitution_or_comparator"],
                "evidence_slots": ["intervention_or_option", "comparator", "missing_evidence_gap"],
                "criterion": tradeoff.get("criterion"),
            }
        )
    return sorted(rows, key=lambda row: _memo_slot_row_rank(row, spec, vocabulary=vocabulary))[:1]

def _row_matches_memo_slot_direction(row: dict[str, Any], spec: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> bool:
    slot_id = str(spec.get("slot_id", ""))
    claim = str(row.get("claim", ""))
    lowered = f" {claim.lower()} "
    reject_markers = _vocabulary_nested_marker_map(vocabulary, "memo_slot_reject_markers").get(slot_id, [])
    if any(group and all(marker in lowered for marker in group) for group in reject_markers):
        return False
    if slot_id in {
        "main_support",
        "counterevidence_or_tension",
        "scope_conditions",
        "implementation_constraints",
        "evidence_type_limits",
        "safety_or_risk",
    }:
        return True
    marker_map = _vocabulary_marker_map(vocabulary, "memo_slot_direction_markers")
    if slot_id in marker_map:
        return any(marker in lowered for marker in marker_map[slot_id])
    if slot_id == "hard_outcome_support":
        return _looks_like_support_evidence(claim, vocabulary=vocabulary) and not _looks_like_concern_evidence(claim, vocabulary=vocabulary)
    if slot_id == "hard_outcome_counter":
        return _looks_like_concern_evidence(claim, vocabulary=vocabulary)
    return True



# Explicit cross-module dependencies for compatibility facade removal.
from epistemic_case_mapper.map_briefing_evidence_tables import (
    _concept_label,
    _markdown_section_with_heading,
    _markdown_table_cell,
    _reader_source_name,
)
from epistemic_case_mapper.map_briefing_map_utils import _looks_like_concern_evidence, _looks_like_support_evidence
from epistemic_case_mapper.map_briefing_reader_contracts import (
    _human_current_read_for_crux,
    _human_would_change_if_for_crux,
    _profile_id_for_scaffold,
    _profile_vocabulary_for_scaffold,
    _vocabulary_marker_map,
    _vocabulary_nested_marker_map,
)
from epistemic_case_mapper.map_briefing_reader_polish import (
    _compact_crux_table,
    _memo_slot_row_rank,
    _option_tradeoff_slot_claim,
    _option_tradeoff_slot_score,
    _reader_clean_evidence_row,
    _reader_evidence_row_quality,
)
from epistemic_case_mapper.map_briefing_validation import _content_terms, _string_list, validate_briefing_against_scaffold
