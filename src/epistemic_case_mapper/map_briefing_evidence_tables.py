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

def _deterministic_appendix_from_scaffold(scaffold: dict[str, Any]) -> str:
    roles = scaffold.get("evidence_roles", {}) if isinstance(scaffold.get("evidence_roles"), dict) else {}
    lines = ["## Evidence Roles", ""]
    for key, label in (
        ("main_support", "Main Support"),
        ("conflicting_evidence", "Conflicting Evidence"),
        ("scope_limits", "Scope Limits"),
        ("method_limits", "Method Limits"),
    ):
        lines.extend([f"### {label}", ""])
        lines.extend(f"- {_polish_reader_sentence_block(item, max_chars=260)}" for item in _string_list(roles.get(key))[:6])
        lines.append("")
    return "\n".join(lines).strip()

def _markdown_section(markdown: str, title: str) -> str:
    match = re.search(rf"^##\s+{re.escape(title)}\s*$\n?(.*?)(?=^##\s+|\Z)", markdown, flags=re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""

def _markdown_section_with_heading(markdown: str, title: str) -> str:
    match = re.search(rf"^##\s+{re.escape(title)}\s*$\n?(.*?)(?=^##\s+|\Z)", markdown, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return ""
    return f"## {title}\n\n{match.group(1).strip()}".strip()

def _clean_appendix_section(section: str) -> str:
    lines = []
    previous_content = ""
    source_counts: dict[str, int] = {}
    for line in section.splitlines():
        cleaned = _clean_reader_briefing_line(line)
        if not cleaned.strip():
            lines.append("")
            continue
        content_key = re.sub(r"\([^)]{3,120}\)", "", cleaned).strip().lower()
        if content_key and content_key == previous_content:
            continue
        source_match = re.search(r"\|\s*([^|]{3,120})\s*\|[^|]*\|?$", cleaned) if cleaned.startswith("|") else re.search(r"\(([^)]{3,120})\)\.?$", cleaned)
        if source_match and not cleaned.startswith("|---"):
            source = source_match.group(1).strip()
            if source.lower() in {"source", "role", "why it matters"}:
                lines.append(cleaned)
                continue
            source_counts[source] = source_counts.get(source, 0) + 1
            if source_counts[source] > 5 and not cleaned.startswith("##"):
                continue
        lines.append(cleaned)
        if content_key:
            previous_content = content_key
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()

def _clean_reader_briefing_line(line: str) -> str:
    if not line.strip():
        return ""
    if line.lstrip().startswith("|"):
        cells = line.split("|")
        if len(cells) > 2 and not set(line.strip()) <= {"|", "-", " ", ":"}:
            return "|".join(_clean_reader_table_cell(cell) for cell in cells)
    prefix = ""
    body = line
    bullet = re.match(r"^(\s*[-*]\s+)(.+)$", line)
    if bullet:
        prefix, body = bullet.group(1), bullet.group(2)
    return prefix + _polish_reader_sentence_block(body, max_chars=420)

def _clean_reader_table_cell(cell: str) -> str:
    if not cell.strip() or set(cell.strip()) <= {"-", ":"}:
        return cell
    return " " + _polish_reader_sentence_block(cell, max_chars=260).strip() + " "

def _polish_reader_sentence_block(text: str, *, max_chars: int = 500) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = _remove_extraction_fragments(cleaned)
    cleaned = re.sub(r"\b(?:Dose/threshold|Comparator/substitution|Subgroup/scope|Method-limit) evidence:\s*", "", cleaned)
    cleaned = re.sub(r"\b[A-Za-z]+ evidence:\s*(?=[a-z])", "", cleaned)
    cleaned = _remove_extraction_fragments(cleaned)
    cleaned = _polish_embedded_source_prefixes(cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"\.{4,}", "...", cleaned)
    cleaned = cleaned.strip(" ")
    if max_chars and len(cleaned) > max_chars:
        cleaned = _short_claim_fragment(cleaned, max_chars=max_chars)
    return cleaned

def _remove_extraction_fragments(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"(^|[\s(*-])\.{2,}[a-z]{2,}\s+", r"\1", cleaned)
    cleaned = re.sub(r"(^|[\s(])\.[a-z]{2,}\s+", r"\1", cleaned)
    cleaned = re.sub(r"(?<=[A-Za-z])\.[a-z]{2,}\s+", " ", cleaned)
    cleaned = re.sub(r"\b[a-z]{1,3}\.(?=[a-z]{3,})", "", cleaned)
    cleaned = re.sub(r"\b[A-Za-z]{2,}-containi\b", "ApoB-containing", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ,;")

def _contains_truncated_fragment(text: str) -> bool:
    return bool(re.search(r"(^|[\s(*-])\.{1,3}[a-z]{2,}\s+|(?<=[A-Za-z])\.[a-z]{2,}\s+|\b[a-z]{1,3}\.(?=[a-z]{3,})|\b[A-Za-z]{2,}-containi\b", text))

def _join_polished_sentences(items: list[str], *, max_sentences: int) -> str:
    polished = []
    for item in items:
        sentence = _first_complete_sentences(_polish_reader_sentence_block(item, max_chars=0), max_sentences=1, max_chars=380)
        if not sentence:
            continue
        if not sentence.endswith((".", "?", "!")):
            sentence += "."
        polished.append(sentence)
    if not polished:
        return "The current map does not cleanly establish enough evidence to support a more specific synthesis for this section."
    return " ".join(_dedupe(polished)[:max_sentences])

def _first_complete_sentences(text: str, *, max_sentences: int, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return ""
    sentences = re.findall(r".*?(?:[.!?](?=\s+[A-Z0-9(]|\s*$)|$)", cleaned)
    selected: list[str] = []
    total = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if "..." in sentence:
            break
        candidate = " ".join([*selected, sentence]).strip()
        if selected and len(candidate) > max_chars:
            break
        selected.append(sentence)
        total = candidate
        if len(selected) >= max_sentences or len(total) >= max_chars:
            break
    if total and len(total) <= max_chars:
        return total
    if selected:
        return " ".join(selected[:-1] or selected[:1]).strip()
    return _short_claim_fragment(cleaned, max_chars=max_chars)

def _source_suffix(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    sources = [_reader_source_name(str(item).strip()) for item in value if str(item).strip()]
    if not sources:
        return ""
    return f" ({', '.join(sources[:2])})."

def _generic_cluster_proposition(text: str) -> bool:
    normalized = text.lower()
    return (
        normalized.count("evidence supports") >= 1
        and any(marker in normalized for marker in ("default answer", "under stated conditions", "caution because some evidence"))
        and len(_content_terms(normalized)) < 8
    )

def _reader_source_name(source: str) -> str:
    raw = source.strip()
    if "_sources_" in raw.lower():
        raw = re.split(r"_sources_", raw, maxsplit=1, flags=re.IGNORECASE)[1]
    title = display_source_name(raw) if re.fullmatch(r"[A-Za-z0-9_-]+", raw) and ("_" in raw or "-" in raw) else raw
    title = re.sub(r"^.*\bSources\s+", "", title)
    title = polish_source_display_name(title)
    title = re.sub(r"\b(?:Fullish|Full|Abstract|Metadata|Pubmed|PMC)\b", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return _compact_citation_label(title)

def _compact_citation_label(title: str) -> str:
    words = title.split()
    year_index = next((index for index, word in enumerate(words) if re.fullmatch(r"(?:19|20)\d{2}", word)), -1)
    if year_index <= 0:
        return title
    prefix = words[:year_index]
    if len(prefix) > 4 or any(word.lower() in {"and", "or", "of", "for", "with", "risk", "review", "analysis", "recommendations"} for word in prefix):
        return title
    author_words = [word for word in prefix if word.lower() not in {"aha", "ajcn", "bmj", "eas", "jaha", "jama", "plos", "pure"}]
    if not author_words:
        author_words = prefix
    return f"{' '.join(author_words[:2])} {words[year_index]}".strip()

def _polish_embedded_source_prefixes(text: str) -> str:
    cleaned = re.sub(
        r"\b[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*_sources_([A-Za-z0-9_]+)",
        lambda match: _reader_source_name(match.group(0)),
        text,
    )
    cleaned = re.sub(r"\b[A-Z][A-Za-z0-9 ]{3,80}\b Sources ([A-Z][A-Za-z0-9 ,&/().-]+)", r"\1", cleaned)
    return cleaned

def _executive_markdown(rendered: str) -> str:
    return rendered.split("\n## Evidence Appendix", 1)[0].strip()

def _extract_confidence(markdown: str) -> str:
    match = re.search(r"\*\*Confidence:\*\*\s*([A-Za-z_\- ]+)", markdown)
    return match.group(1).strip() if match else ""

def _trim_executive_sections(markdown: str, *, target_words: int) -> str:
    if len(re.findall(r"\b\w+\b", markdown)) <= target_words:
        return markdown
    lines = markdown.splitlines()
    trimmed = []
    for line in lines:
        if line.startswith("|") and len(trimmed) > 0:
            continue
        trimmed.append(line)
        if len(re.findall(r"\b\w+\b", "\n".join(trimmed))) >= target_words:
            break
    return "\n".join(trimmed).rstrip()

def _markdown_table_count(markdown: str) -> int:
    return len(re.findall(r"^\|[-:| ]+\|$", markdown, flags=re.MULTILINE))

def _duplicate_sentence_count(markdown: str) -> int:
    seen: set[str] = set()
    duplicates = 0
    for sentence in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", markdown)):
        key = sentence.strip().lower()
        if len(key) < 80:
            continue
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
    return duplicates

def _coverage_snapshot_rows(table: dict[str, Any], *, max_rows: int = 12) -> list[dict[str, str]]:
    rows = [row for row in table.get("rows", []) if isinstance(row, dict)]
    table_profile_id = str(table.get("profile_id", "")).strip()
    if not table_profile_id:
        table_profile_id = infer_profile_id_from_text(
            " ".join(
                " ".join([str(row.get("claim", "")), " ".join(str(item) for item in row.get("concepts", []) if isinstance(item, str))])
                for row in rows
            ),
            fallback_profile_id=DEFAULT_PROFILE_ID,
        )
    vocabulary = profile_vocabulary(table_profile_id)
    selected: list[dict[str, str]] = []
    concept_order = sorted(
        _obligatory_coverage_concepts(_ordered_concepts(rows)),
        key=lambda concept: _COVERAGE_CONCEPT_PRIORITY.get(concept, 50),
    )
    for concept in concept_order:
        candidates = [row for row in rows if concept in row.get("concepts", []) and _coverage_concept_visible(concept, row, vocabulary=vocabulary)]
        if not candidates:
            continue
        row = sorted(candidates, key=lambda item: _coverage_concept_row_rank(concept, item, vocabulary=vocabulary))[0]
        source = str(row.get("source", "")).strip()
        claim = _coverage_current_read(concept, row, vocabulary=vocabulary)
        current_read = _short_claim_fragment(claim + (f" ({source})" if source else ""), max_chars=210)
        selected.append(
            {
                "concept": _concept_label(concept),
                "current_map_read": current_read,
                "why_it_matters": _coverage_why_it_matters(concept, row),
            }
        )
        if len(selected) >= max_rows:
            break
    return selected

def _obligatory_coverage_concepts(concepts: list[str]) -> list[str]:
    return [concept for concept in concepts if concept not in _NON_OBLIGATORY_COVERAGE_CONCEPTS]

def _coverage_concept_visible(concept: str, row: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> bool:
    text = _coverage_text_for_row(row)
    if concept == "hard_outcome_endpoint" and _looks_like_baseline_population_criterion(text):
        return False
    markers = _vocabulary_marker_map(vocabulary, "coverage_visible_markers").get(concept, [])
    return any(marker in text for marker in markers)

def _coverage_current_read(concept: str, row: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> str:
    slot_values = row.get("slot_values", {}) if isinstance(row.get("slot_values"), dict) else {}
    concept_slot = _COVERAGE_CONCEPT_SLOT.get(concept)
    claim = str(row.get("claim", "")).strip()
    if concept_slot and str(slot_values.get(concept_slot, "")).strip():
        value = str(slot_values[concept_slot]).strip()
        min_len = 24 if concept in {"study_design_rct", "study_design_cohort"} else 12
        if _slot_value_visibly_represents_concept(value, concept, vocabulary=vocabulary) and len(value) >= min_len:
            return value
    return claim

def _slot_value_visibly_represents_concept(value: str, concept: str, *, vocabulary: dict[str, Any] | None = None) -> bool:
    normalized = value.lower()
    preferred = _vocabulary_nested_marker_map(vocabulary, "coverage_preferred_markers").get(concept, [])
    if not preferred:
        return True
    first_tier = preferred[0] if preferred else ()
    return any(marker in normalized for marker in first_tier)

def _coverage_why_it_matters(concept: str, row: dict[str, Any]) -> str:
    specific = {
        "default_population": "This controls who or what inherits the default answer rather than needing a separate judgment.",
        "dose_or_threshold": "Intensity, threshold, and scale boundaries keep a scoped finding from becoming an unlimited recommendation.",
        "substitution_or_comparator": "Comparator evidence affects practical advice because the best answer can change with the alternative.",
        "alternative_or_comparator": "Comparator evidence affects practical advice because the best answer can change with the alternative.",
        "hard_outcome_endpoint": "Hard outcomes are more decision-direct than surrogate movement.",
        "surrogate_or_biomarker_endpoint": "Proxy evidence can support mechanism but should not by itself settle decision-relevant outcomes.",
        "mechanism_or_causal_path": "Mechanism evidence helps explain why an effect may transfer, but it should not be read as direct outcome proof.",
        "mechanism_ldl_apob": "Mechanistic lipid evidence bounds whether the hard-outcome read is biologically plausible.",
        "subgroup_diabetes_or_metabolic_risk": "Subgroup evidence controls whether the default answer travels to higher-risk people.",
        "subgroup_fh_hyper_responder": "This subgroup can invalidate a generic population-level recommendation.",
        "dietary_context_or_saturated_fat": "Dietary context can explain why the same exposure appears harmful or neutral across settings.",
        "study_design_rct": "Trial evidence helps separate intervention effects from observational confounding.",
        "study_design_cohort": "Cohort evidence carries long-term outcome signal but remains confounding-sensitive.",
        "guideline_or_policy": "Guidance evidence shows how the map translates into practical advice.",
        "technical_performance_or_capacity": "Technical performance evidence gates whether the option can deliver the intended effect in the target setting.",
        "implementation_constraint": "Implementation constraints can determine whether evidence-backed options work in practice.",
        "safety_or_adverse_effect": "Safety and downside-risk evidence can change a recommendation even when the main effect is favorable.",
        "setting_or_context": "Setting evidence controls whether the mapped result transfers to the decision context.",
    }
    return specific.get(concept) or str(row.get("why_it_matters", "")).strip() or "This is a retained decision-relevant map ingredient."

def _coverage_text_for_row(row: dict[str, Any]) -> str:
    slot_values = row.get("slot_values", {}) if isinstance(row.get("slot_values"), dict) else {}
    parts = [str(row.get("claim", "")), *(str(value) for value in slot_values.values())]
    return re.sub(r"\s+", " ", " ".join(parts).lower())

def _looks_like_baseline_population_criterion(text: str) -> bool:
    return (
        any(marker in text for marker in ("free of", "without", "with no history of"))
        and "baseline" in text
        and not any(marker in text for marker in ("risk", "outcome", "mortality", "incident", "associated", "hazard ratio", "relative risk"))
    )

def _coverage_snapshot_rank(row: dict[str, Any]) -> tuple[int, int, int, str]:
    concepts = [concept for concept in row.get("concepts", []) if isinstance(concept, str)]
    concept_priority = min((_COVERAGE_CONCEPT_PRIORITY.get(concept, 50) for concept in concepts), default=50)
    return (concept_priority, -int(row.get("score", 0)), len(str(row.get("claim", ""))), str(row.get("claim_id", "")))

def _coverage_concept_row_rank(concept: str, row: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> tuple[int, int, int, str]:
    return (
        _coverage_concept_specificity(concept, row, vocabulary=vocabulary),
        -int(row.get("score", 0)),
        len(str(row.get("claim", ""))),
        str(row.get("claim_id", "")),
    )

def _coverage_concept_specificity(concept: str, row: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> int:
    text = _coverage_text_for_row(row)
    preferred_markers = _vocabulary_nested_marker_map(vocabulary, "coverage_preferred_markers").get(concept, [])
    for index, markers in enumerate(preferred_markers):
        if any(marker in text for marker in markers):
            return index
    return len(preferred_markers) + 1

_NON_OBLIGATORY_COVERAGE_CONCEPTS = {"source_quality_or_incentive"}

_COVERAGE_CONCEPT_PRIORITY = {
    "default_population": 0,
    "dose_or_threshold": 1,
    "substitution_or_comparator": 2,
    "alternative_or_comparator": 3,
    "technical_performance_or_capacity": 4,
    "implementation_constraint": 5,
    "safety_or_adverse_effect": 6,
    "hard_outcome_endpoint": 7,
    "surrogate_or_biomarker_endpoint": 8,
    "mechanism_or_causal_path": 9,
    "mechanism_ldl_apob": 10,
    "subgroup_diabetes_or_metabolic_risk": 11,
    "subgroup_fh_hyper_responder": 12,
    "dietary_context_or_saturated_fat": 13,
    "setting_or_context": 14,
    "study_design_rct": 15,
    "study_design_cohort": 16,
    "guideline_or_policy": 17,
}

def _concept_label(concept: str) -> str:
    return {
        "default_population": "Default population",
        "dose_or_threshold": "Dose or threshold",
        "hard_outcome_endpoint": "Hard outcomes",
        "surrogate_or_biomarker_endpoint": "Proxy or surrogate outcomes",
        "mechanism_or_causal_path": "Mechanism or causal path",
        "mechanism_ldl_apob": "LDL/ApoB mechanism",
        "dietary_context_or_saturated_fat": "Saturated fat or dietary context",
        "substitution_or_comparator": "Comparator or substitution",
        "alternative_or_comparator": "Alternatives or comparators",
        "subgroup_diabetes_or_metabolic_risk": "Metabolic-risk subgroup",
        "subgroup_fh_hyper_responder": "FH or hyper-responder subgroup",
        "technical_performance_or_capacity": "Technical capacity or performance",
        "implementation_constraint": "Implementation constraints",
        "safety_or_adverse_effect": "Safety or downside risk",
        "setting_or_context": "Setting or context",
        "study_design_rct": "RCT/intervention evidence",
        "study_design_cohort": "Cohort/observational evidence",
        "guideline_or_policy": "Guidance or policy",
    }.get(concept, concept.replace("_", " "))

_COVERAGE_CONCEPT_SLOT = {
    "default_population": "default_population",
    "dose_or_threshold": "dose_or_intensity_threshold",
    "substitution_or_comparator": "substitution_or_comparator",
    "alternative_or_comparator": "substitution_or_comparator",
    "hard_outcome_endpoint": "endpoint_type",
    "surrogate_or_biomarker_endpoint": "mechanism",
    "mechanism_or_causal_path": "mechanism",
    "mechanism_ldl_apob": "mechanism",
    "subgroup_diabetes_or_metabolic_risk": "high_risk_subgroup",
    "subgroup_fh_hyper_responder": "high_risk_subgroup",
    "study_design_rct": "study_design",
    "study_design_cohort": "study_design",
    "technical_performance_or_capacity": "practical_recommendation",
    "implementation_constraint": "practical_recommendation",
    "safety_or_adverse_effect": "practical_recommendation",
    "setting_or_context": "default_population",
}

def _markdown_table_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value).replace("|", "\\|").strip()

def _extract_json_string_field_local(text: str, field: str) -> str:
    match = re.search(rf'"{re.escape(field)}"\s*:\s*"((?:\\.|[^"\\])*)"', text, flags=re.DOTALL)
    if not match:
        return ""
    try:
        return json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        return match.group(1).replace(r"\"", '"').replace(r"\n", "\n")

def build_briefing_contract(partition: dict[str, Any], quality_report: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> dict[str, Any]:
    evidence_roles = partition.get("evidence_roles", {})
    support = _string_list(evidence_roles.get("main_support"))
    conflict = _string_list(evidence_roles.get("conflicting_evidence"))
    scope = _string_list(evidence_roles.get("scope_limits"))
    method = _string_list(evidence_roles.get("method_limits"))
    support_profile = _support_signal_profile(support, vocabulary=vocabulary)
    scope_ledger = _scope_ledger([*scope, *method, *conflict], vocabulary=vocabulary)
    active_lints = _active_overstatement_lints(
        support_profile=support_profile,
        conflict=conflict,
        scope_ledger=scope_ledger,
        method_limits=method,
        quality_report=quality_report,
    )
    return {
        "schema_id": "briefing_contract_v1",
        "answer_frame": {
            "default_stance_instruction": _default_stance_instruction(support_profile, conflict),
            "confidence_cap": confidence_cap(quality_report),
            "holds_when": _dedupe(_positive_scope_items(scope))[:5],
            "weakens_when": _dedupe([*conflict, *_limiting_scope_items(scope)])[:6],
            "strongest_counterposition": conflict[0] if conflict else "",
            "why_not_stronger": _dedupe([*method, *quality_report_issue_text(quality_report)])[:6],
        },
        "scope_ledger": scope_ledger,
        "evidence_direction": {
            "supports_default_stance": support[:8],
            "supports_counterposition": conflict[:8],
            "bounds_scope": scope[:8],
            "changes_interpretation": _string_list(partition.get("audit_trail"))[:8],
            "identifies_missing_or_limited_evidence": method[:8],
        },
        "support_signal_profile": support_profile,
        "overstatement_lint": active_lints,
    }

def build_evidence_weighting_ledger(
    candidate_map: dict[str, Any],
    partition: dict[str, Any],
    quality_report: dict[str, Any],
    source_lookup: dict[str, str],
    *,
    question: str = "",
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    profile_id = _profile_id_for_map(candidate_map)
    vocabulary = _profile_vocabulary_for_map(candidate_map)
    for claim in _claims(candidate_map):
        section = _claim_evidence_section(claim)
        score, modifiers = _claim_evidence_weight_score(claim, section, quality_report, source_lookup, vocabulary=vocabulary)
        concepts = _claim_concepts(claim, vocabulary=vocabulary)
        noise = _claim_noise_profile(claim)
        decision_slots = _decision_slots_for_claim(claim, vocabulary=vocabulary)
        evidence_slots = _evidence_slots_for_claim(claim, vocabulary=vocabulary)
        eligibility = _claim_eligibility_profile(
            claim=claim,
            section=section,
            score=score,
            weight=_weight_label(score),
            concepts=concepts,
            decision_slots=decision_slots,
            evidence_slots=evidence_slots,
            noise=noise,
            question=question,
        )
        if eligibility.get("appendix_only"):
            score = min(score, 2)
            modifiers.append("eligibility:appendix_only")
        elif not eligibility.get("top_line_eligible") and section in {"main_support", "conflicting_evidence", "scope_limits"}:
            score = min(score, 5)
            modifiers.append("eligibility:not_top_line")
        rows.append(
            {
                "claim_id": str(claim.get("claim_id", "")),
                "section": section,
                "evidence_family": _evidence_family_for_claim(claim, section, source_lookup, vocabulary=vocabulary),
                "decision_slots": decision_slots,
                "evidence_slots": evidence_slots,
                "decision_concepts": concepts,
                "noise": noise,
                "eligibility": eligibility,
                "decision_relevance_score": eligibility.get("decision_relevance_score", 0),
                "top_line_eligible": bool(eligibility.get("top_line_eligible")),
                "crux_eligible": bool(eligibility.get("crux_eligible")),
                "appendix_only": bool(eligibility.get("appendix_only")),
                "section_eligibility": eligibility.get("section_eligibility", {}),
                "weight": _weight_label(score),
                "score": score,
                "modifiers": modifiers,
                "claim": str(claim.get("claim") or claim.get("text") or ""),
                "source": source_lookup.get(str(claim.get("source_id", "")), display_source_name(str(claim.get("source_id", "")))),
                "supporting_source_count": len(_claim_supporting_sources_for_briefing(claim)),
            }
        )
    rows.sort(key=_evidence_ledger_row_rank)
    by_section: dict[str, list[dict[str, Any]]] = {
        "main_support": [],
        "conflicting_evidence": [],
        "scope_limits": [],
        "method_limits": [],
    }
    for row in rows:
        by_section.setdefault(str(row["section"]), []).append(row)
    return {
        "schema_id": "evidence_weighting_ledger_v1",
        "method": "generic_entailment_source_directness_support_role_scoring",
        "profile_id": profile_id,
        "quality_status": quality_report.get("status"),
        "all_evidence": rows,
        "family_counts": _counts(row["evidence_family"] for row in rows),
        "decision_slot_counts": _decision_slot_counts(rows),
        "evidence_slot_counts": _counts(slot for row in rows for slot in row.get("evidence_slots", [])),
        "decision_concept_counts": _counts(concept for row in rows for concept in row.get("decision_concepts", [])),
        "noise_counts": _counts(row.get("noise", {}).get("kind") for row in rows if isinstance(row.get("noise"), dict)),
        "eligibility_counts": _counts(_eligibility_bucket(row) for row in rows),
        "top_evidence_by_section": {section: items[:6] for section, items in by_section.items()},
        "weight_counts": _counts(row["weight"] for row in rows),
        "notes": [
            "Weights are deterministic synthesis guidance, not statistical study-quality scores.",
            "Low-weight evidence may still matter as a caveat, scope boundary, or source-completeness warning.",
        ],
        "partition_counts": {key: len(value) for key, value in partition.get("evidence_roles", {}).items()},
    }

def _evidence_ledger_row_rank(row: dict[str, Any]) -> tuple[int, int, int, int, str, str]:
    return (
        1 if row.get("appendix_only") else 0,
        0 if row.get("top_line_eligible") else 1,
        -int(row.get("score", 0)),
        -int(row.get("decision_relevance_score", 0)),
        str(row.get("section", "")),
        str(row.get("claim_id", "")),
    )

def _eligibility_bucket(row: dict[str, Any]) -> str:
    if row.get("appendix_only"):
        return "appendix_only"
    if row.get("top_line_eligible"):
        return "top_line_eligible"
    if row.get("crux_eligible"):
        return "crux_eligible"
    return "body_only"

def build_evidence_compression_table(
    candidate_map: dict[str, Any],
    evidence_ledger: dict[str, Any],
    source_lookup: dict[str, str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    vocabulary = _profile_vocabulary_for_map(candidate_map)
    claim_lookup = {str(claim.get("claim_id", "")): claim for claim in _claims(candidate_map)}
    for row in evidence_ledger.get("all_evidence", []):
        if not isinstance(row, dict):
            continue
        claim_id = str(row.get("claim_id", ""))
        claim = claim_lookup.get(claim_id, {})
        concepts = [str(item) for item in row.get("decision_concepts", []) if isinstance(item, str)]
        if not concepts and str(row.get("section", "")) not in {"main_support", "conflicting_evidence"}:
            continue
        if row.get("appendix_only"):
            continue
        noise = row.get("noise", {}) if isinstance(row.get("noise"), dict) else {}
        if str(noise.get("kind", "")) not in {"", "none"} and int(row.get("score", 0)) < 5:
            continue
        rows.append(
            {
                "claim_id": claim_id,
                "source": row.get("source", ""),
                "section": row.get("section", ""),
                "role": str(claim.get("role", "")),
                "weight": row.get("weight", "medium"),
                "score": row.get("score", 0),
                "appendix_only": bool(row.get("appendix_only")),
                "concepts": concepts,
                "evidence_slots": [str(item) for item in row.get("evidence_slots", []) if isinstance(item, str)],
                "evidence_family": row.get("evidence_family", "general_evidence"),
                "slot_values": _compression_slot_values(str(row.get("claim", "")), row.get("decision_slots", []), vocabulary=vocabulary),
                "claim": _compressed_claim_text(str(row.get("claim", "")), noise),
                "why_it_matters": _compression_why_it_matters(row),
                "noise_kind": noise.get("kind", "none"),
            }
        )
    selected = _select_compression_rows(rows, max_rows=36, vocabulary=vocabulary)
    present_obligatory = _obligatory_coverage_concepts(_ordered_concepts(rows))
    selected_obligatory = _obligatory_coverage_concepts(_ordered_concepts(selected))
    return {
        "schema_id": "evidence_compression_table_v1",
        "method": "concept_coverage_then_weighted_evidence_with_noise_suppression",
        "profile_id": _profile_id_for_map(candidate_map),
        "coverage": {
            "present_concepts": _ordered_concepts(rows),
            "selected_concepts": _ordered_concepts(selected),
            "obligatory_present_concepts": present_obligatory,
            "obligatory_selected_concepts": selected_obligatory,
            "concept_coverage_preserved": set(present_obligatory).issubset(set(selected_obligatory)),
        },
        "rows": selected,
    }

def build_concept_evidence_packets(evidence_ledger: dict[str, Any], *, max_packets: int = 10, rows_per_packet: int = 4) -> dict[str, Any]:
    vocabulary = profile_vocabulary(str(evidence_ledger.get("profile_id", DEFAULT_PROFILE_ID)))
    rows = [
        _concept_packet_row(row)
        for row in evidence_ledger.get("all_evidence", [])
        if isinstance(row, dict)
    ]
    rows = [row for row in rows if row.get("concepts") and str(row.get("noise_kind", "none")) in {"", "none"}]
    packets: list[dict[str, Any]] = []
    for concept in _obligatory_coverage_concepts(_ordered_concepts(rows)):
        candidates = [row for row in rows if concept in row.get("concepts", [])]
        if not candidates:
            continue
        selected = sorted(candidates, key=lambda row: _concept_packet_row_rank(concept, row, vocabulary=vocabulary))[:rows_per_packet]
        packets.append(
            {
                "concept": concept,
                "label": _concept_label(concept),
                "synthesis_job": _concept_packet_synthesis_job(concept),
                "must_surface_terms": _concept_packet_surface_terms(concept, selected, vocabulary=vocabulary),
                "rows": selected,
            }
        )
        if len(packets) >= max_packets:
            break
    return {
        "schema_id": "concept_evidence_packets_v1",
        "method": "concept_family_ranked_evidence_packets_for_staged_synthesis",
        "packet_count": len(packets),
        "packets": packets,
    }

def _concept_packet_row(row: dict[str, Any]) -> dict[str, Any]:
    noise = row.get("noise", {}) if isinstance(row.get("noise"), dict) else {}
    concepts = [str(item) for item in row.get("decision_concepts", []) if isinstance(item, str)]
    claim = _compressed_claim_text(str(row.get("claim", "")), noise)
    return {
        "claim_id": row.get("claim_id"),
        "source": row.get("source"),
        "section": row.get("section"),
        "weight": row.get("weight", "medium"),
        "score": row.get("score", 0),
        "concepts": concepts,
        "evidence_slots": [str(item) for item in row.get("evidence_slots", []) if isinstance(item, str)],
        "evidence_family": row.get("evidence_family", "general_evidence"),
        "top_line_eligible": bool(row.get("top_line_eligible")),
        "appendix_only": bool(row.get("appendix_only")),
        "question_fit": row.get("question_fit", {}),
        "eligibility": row.get("eligibility", {}),
        "claim": claim,
        "why_it_matters": _compression_why_it_matters({"decision_concepts": concepts, "section": row.get("section")}),
        "noise_kind": noise.get("kind", "none"),
    }

def _concept_packet_row_rank(concept: str, row: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> tuple[int, int, int, str]:
    return (
        _coverage_concept_specificity(concept, row, vocabulary=vocabulary),
        -int(row.get("score", 0)),
        len(str(row.get("claim", ""))),
        str(row.get("claim_id", "")),
    )

def _concept_packet_synthesis_job(concept: str) -> str:
    return {
        "default_population": "State who the default answer applies to and where transfer is uncertain.",
        "dose_or_threshold": "State the dose or threshold boundary that keeps the advice from overgeneralizing.",
        "substitution_or_comparator": "State how the recommendation changes when replacement options or comparators matter.",
        "hard_outcome_endpoint": "Separate direct outcome evidence from biomarker or mechanistic evidence.",
        "surrogate_or_biomarker_endpoint": "Explain what proxy or surrogate outcomes can support and what they cannot settle.",
        "mechanism_or_causal_path": "Explain the causal pathway and where it falls short of direct outcome evidence.",
        "mechanism_ldl_apob": "Explain the LDL/ApoB mechanism and whether it changes the bottom-line read.",
        "subgroup_diabetes_or_metabolic_risk": "State whether subgroup evidence narrows the general-population advice.",
        "subgroup_fh_hyper_responder": "State whether high-risk lipid subgroups need separate advice.",
        "dietary_context_or_saturated_fat": "State how diet composition or saturated fat modifies the exposure read.",
        "alternative_or_comparator": "State how the recommendation changes across the alternatives being compared.",
        "technical_performance_or_capacity": "State what technical capacity or performance evidence is needed for the option to work.",
        "implementation_constraint": "State what practical constraints gate implementation.",
        "safety_or_adverse_effect": "State what harms, safety issues, or downside risks constrain the recommendation.",
        "setting_or_context": "State whether the mapped evidence transfers to the target setting.",
        "study_design_rct": "State what intervention evidence contributes and its limits.",
        "study_design_cohort": "State what long-run observational evidence contributes and its confounding limits.",
        "guideline_or_policy": "State what practical guidance follows and where implementation is hard.",
    }.get(concept, "State the decision-relevant contribution and caveat for this evidence family.")

def _concept_packet_surface_terms(concept: str, rows: list[dict[str, Any]], *, vocabulary: dict[str, Any] | None = None) -> list[str]:
    text = " ".join(str(row.get("claim", "")) for row in rows).lower()
    preferred = [marker for tier in _vocabulary_nested_marker_map(vocabulary, "coverage_preferred_markers").get(concept, []) for marker in tier]
    visible = [marker for marker in preferred if marker in text and len(marker) >= 4]
    if visible:
        return _dedupe(visible)[:5]
    markers = [
        marker
        for marker in _vocabulary_marker_map(vocabulary, "coverage_visible_markers").get(concept, [])
        if marker in text and len(marker) >= 4
    ]
    return _dedupe(markers)[:5]

def _compression_slot_values(claim: str, slots: Any, *, vocabulary: dict[str, Any] | None = None) -> dict[str, str]:
    values: dict[str, str] = {}
    for slot in slots if isinstance(slots, list) else []:
        if not isinstance(slot, str):
            continue
        value = _slot_value(slot, claim, vocabulary=vocabulary)
        if value:
            values[slot] = value
    return values

def _compressed_claim_text(claim: str, noise: dict[str, Any]) -> str:
    kind = str(noise.get("kind", "none"))
    if kind == "boilerplate_disclosure":
        return "The source includes extensive funding or conflict-of-interest disclosures; treat this as source context, not substantive outcome evidence."
    if kind == "publisher_or_license_boilerplate":
        return "The source includes publisher, copyright, license, or metadata boilerplate; do not use it as substantive evidence."
    return _short_claim_fragment(claim, max_chars=260)

def _compression_why_it_matters(row: dict[str, Any]) -> str:
    concepts = set(str(item) for item in row.get("decision_concepts", []))
    section = str(row.get("section", ""))
    if "mechanism_ldl_apob" in concepts:
        return "Mechanistic lipid evidence bounds whether the hard-outcome read is biologically plausible."
    if "mechanism_or_causal_path" in concepts:
        return "Mechanism evidence helps explain transfer but should not be treated as direct outcome evidence."
    if "technical_performance_or_capacity" in concepts:
        return "Technical capacity evidence gates whether the option can deliver the intended effect."
    if "implementation_constraint" in concepts:
        return "Implementation constraints can determine whether a mapped option works in practice."
    if "safety_or_adverse_effect" in concepts:
        return "Downside-risk evidence can change the recommendation even when the main effect is favorable."
    if "alternative_or_comparator" in concepts:
        return "Comparator evidence affects the practical recommendation because the alternative matters."
    if "setting_or_context" in concepts:
        return "Setting evidence controls whether the mapped result transfers to the decision context."
    if "dietary_context_or_saturated_fat" in concepts:
        return "Dietary context can explain why an exposure appears harmful or neutral across settings."
    if "subgroup_diabetes_or_metabolic_risk" in concepts or "subgroup_fh_hyper_responder" in concepts:
        return "Subgroup evidence controls whether the default answer travels to higher-risk people."
    if "substitution_or_comparator" in concepts:
        return "Comparator evidence affects the practical recommendation because the alternative matters."
    if "hard_outcome_endpoint" in concepts:
        return "Hard-outcome evidence is more decision-direct than surrogate evidence."
    if "surrogate_or_biomarker_endpoint" in concepts:
        return "Surrogate evidence should limit confidence rather than settle long-term outcomes."
    if section == "conflicting_evidence":
        return "This evidence pushes against the default answer or limits its scope."
    if section == "method_limits":
        return "This evidence affects how strongly the mapped findings should be read."
    return "This is part of the decision-relevant evidence base."

def _select_compression_rows(rows: list[dict[str, Any]], *, max_rows: int, vocabulary: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for concept in _ordered_concepts(rows):
        candidates = [row for row in rows if concept in row.get("concepts", []) and str(row.get("claim_id", "")) not in seen_ids]
        if not candidates:
            continue
        best = sorted(candidates, key=_compression_row_rank)[0]
        selected.append(best)
        seen_ids.add(str(best.get("claim_id", "")))
        if len(selected) >= max_rows:
            return selected
    for section in ("main_support", "conflicting_evidence", "scope_limits", "method_limits"):
        candidates = [row for row in rows if row.get("section") == section and str(row.get("claim_id", "")) not in seen_ids]
        if not candidates:
            continue
        best = sorted(candidates, key=_compression_row_rank)[0]
        selected.append(best)
        seen_ids.add(str(best.get("claim_id", "")))
        if len(selected) >= max_rows:
            return selected
    for row in sorted(rows, key=_compression_row_rank):
        claim_id = str(row.get("claim_id", ""))
        if claim_id in seen_ids:
            continue
        selected.append(row)
        seen_ids.add(claim_id)
        if len(selected) >= max_rows:
            break
    return selected

def _compression_row_rank(row: dict[str, Any]) -> tuple[int, int, int, str]:
    noise_penalty = 1 if row.get("noise_kind") not in {"", "none", None} else 0
    section_priority = {"main_support": 0, "conflicting_evidence": 1, "scope_limits": 2, "method_limits": 3}.get(str(row.get("section")), 4)
    return (noise_penalty, -int(row.get("score", 0)), section_priority, str(row.get("claim_id", "")))

def _ordered_concepts(rows: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "dose_or_threshold",
        "default_population",
        "hard_outcome_endpoint",
        "surrogate_or_biomarker_endpoint",
        "mechanism_or_causal_path",
        "technical_performance_or_capacity",
        "implementation_constraint",
        "safety_or_adverse_effect",
        "setting_or_context",
        "mechanism_ldl_apob",
        "dietary_context_or_saturated_fat",
        "substitution_or_comparator",
        "alternative_or_comparator",
        "subgroup_diabetes_or_metabolic_risk",
        "subgroup_fh_hyper_responder",
        "study_design_rct",
        "study_design_cohort",
        "guideline_or_policy",
        "source_quality_or_incentive",
    ]
    present: list[str] = []
    for concept in preferred:
        if any(concept in row.get("concepts", []) for row in rows):
            present.append(concept)
    for row in rows:
        for concept in row.get("concepts", []):
            if concept not in present:
                present.append(concept)
    return present



# Explicit cross-module dependencies for compatibility facade removal.
from epistemic_case_mapper.map_briefing_decision_model import (
    _claim_concepts,
    _claim_evidence_weight_score,
    _claim_eligibility_profile,
    _claim_noise_profile,
    _decision_slots_for_claim,
    _evidence_family_for_claim,
    _evidence_slots_for_claim,
    _short_claim_fragment,
    _slot_value,
)
from epistemic_case_mapper.map_briefing_evidence_partition import (
    _active_overstatement_lints,
    _claim_supporting_sources_for_briefing,
    _counts,
    _decision_slot_counts,
    _default_stance_instruction,
    _limiting_scope_items,
    _positive_scope_items,
    _scope_ledger,
    _support_signal_profile,
    _weight_label,
    quality_report_issue_text,
)
from epistemic_case_mapper.map_briefing_map_utils import (
    _claim_evidence_section,
    _claims,
    confidence_cap,
    display_source_name,
    polish_source_display_name,
)
from epistemic_case_mapper.map_briefing_reader_contracts import (
    _profile_id_for_map,
    _profile_vocabulary_for_map,
    _vocabulary_marker_map,
    _vocabulary_nested_marker_map,
)
from epistemic_case_mapper.map_briefing_validation import _content_terms, _dedupe, _string_list
