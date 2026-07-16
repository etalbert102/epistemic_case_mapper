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
from epistemic_case_mapper.map_briefing_text_cleanup import (
    reader_facing_unresolved_family,
    reader_facing_unresolved_slot,
)
from epistemic_case_mapper.model_backends import run_model_backend

def build_proposition_clusters(
    candidate_map: dict[str, Any],
    evidence_ledger: dict[str, Any],
    source_lookup: dict[str, str],
) -> dict[str, Any]:
    claim_lookup = {str(claim.get("claim_id")): claim for claim in _claims(candidate_map)}
    ledger_rows = [
        row for row in evidence_ledger.get("all_evidence", [])
        if isinstance(row, dict) and str(row.get("claim_id", "")) in claim_lookup
        and not row.get("appendix_only")
    ]
    clusters_by_key: dict[str, dict[str, Any]] = {}
    for row in ledger_rows:
        claim = claim_lookup[str(row["claim_id"])]
        claim_text = str(row.get("claim") or claim.get("claim") or claim.get("text") or "")
        normalized_claim = {**claim, "claim": claim_text}
        key = _proposition_cluster_key(normalized_claim, str(row.get("section", "")))
        cluster = clusters_by_key.setdefault(
            key,
            {
                "cluster_id": f"cluster_{len(clusters_by_key) + 1:03d}",
                "direction": _cluster_direction(str(row.get("section", ""))),
                "stance": _claim_stance(claim, str(row.get("section", ""))),
                "scope_dimensions": [],
                "claim_ids": [],
                "sources": [],
                "representative_claims": [],
                "weight_scores": [],
                "weight_labels": [],
                "proposition": "",
            },
        )
        cluster["claim_ids"].append(str(row["claim_id"]))
        cluster["sources"].extend(_claim_supporting_sources_for_briefing(claim))
        cluster["representative_claims"].append(
            {
                "claim_id": str(row["claim_id"]),
                "claim": claim_text,
                "source": source_lookup.get(str(claim.get("source_id", "")), display_source_name(str(claim.get("source_id", "")))),
                "weight": row.get("weight", "medium"),
            }
        )
        cluster["scope_dimensions"].extend(_scope_dimensions_for_text(claim_text))
        cluster["weight_scores"].append(int(row.get("score", 0)))
        cluster["weight_labels"].append(str(row.get("weight", "medium")))
    clusters: list[dict[str, Any]] = []
    for cluster in clusters_by_key.values():
        scores = [int(score) for score in cluster.pop("weight_scores", [])]
        labels = [str(label) for label in cluster.pop("weight_labels", [])]
        cluster["claim_ids"] = _dedupe(cluster["claim_ids"])
        cluster["sources"] = sorted(set(cluster["sources"]))
        cluster["scope_dimensions"] = sorted(set(cluster["scope_dimensions"])) or ["general"]
        cluster["representative_claims"] = sorted(
            cluster["representative_claims"],
            key=lambda item: (
                -{"high": 2, "medium": 1, "low": 0}.get(str(item.get("weight")), 1),
                str(item.get("claim_id", "")),
            ),
        )[:5]
        cluster["strength_score"] = sum(scores)
        cluster["evidence_weight"] = _cluster_weight_label(scores, labels)
        cluster["proposition"] = _cluster_proposition(cluster)
        clusters.append(cluster)
    clusters.sort(key=lambda item: (-int(item.get("strength_score", 0)), str(item.get("cluster_id", ""))))
    clusters = _attach_cluster_tensions(clusters, _relations(candidate_map))
    return {
        "schema_id": "proposition_clusters_v1",
        "method": "direction_stance_scope_weighted_claim_clustering",
        "clusters": clusters[:12],
        "cluster_count": len(clusters),
    }

def build_decision_model(
    proposition_clusters: dict[str, Any],
    contract: dict[str, Any],
    quality_report: dict[str, Any],
    evidence_ledger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence_ledger = evidence_ledger or {}
    clusters = [cluster for cluster in proposition_clusters.get("clusters", []) if isinstance(cluster, dict)]
    classification = _decision_classification(clusters, contract)
    support_clusters = [cluster for cluster in clusters if cluster.get("direction") == "supports_default"]
    counter_clusters = [cluster for cluster in clusters if cluster.get("direction") == "supports_counterposition"]
    scope_clusters = [cluster for cluster in clusters if cluster.get("direction") == "bounds_scope"]
    method_clusters = [cluster for cluster in clusters if cluster.get("direction") == "limits_confidence"]
    answer_frame = contract.get("answer_frame", {}) if isinstance(contract.get("answer_frame"), dict) else {}
    return {
        "schema_id": "decision_model_v1",
        "default_answer": {
            "classification": classification,
            "confidence_cap": confidence_cap(quality_report),
            "plain_language_instruction": _classification_instruction(classification),
            "why_this_frame": _decision_frame_reason(classification, support_clusters, counter_clusters),
        },
        "decision_slots": build_decision_slots(evidence_ledger),
        "missing_decision_slots": _missing_decision_slots(evidence_ledger),
        "evidence_families": evidence_ledger.get("family_counts", {}),
        "holds_for": _cluster_scope_items(scope_clusters, positive=True)[:6],
        "does_not_hold_for": _dedupe([*_string_list(answer_frame.get("weakens_when")), *_cluster_scope_items(scope_clusters, positive=False)])[:8],
        "main_reasons": _cluster_proposition_rows(support_clusters)[:5],
        "strongest_counterarguments": _cluster_proposition_rows(counter_clusters)[:5],
        "tension_resolutions": _tension_resolution_rows(clusters)[:5],
        "practical_recommendations": _practical_recommendations(classification, scope_clusters, method_clusters, evidence_ledger)[:7],
        "what_would_change_answer": _what_would_change_answer(counter_clusters, method_clusters, quality_report)[:6],
        "prose_requirements": _decision_model_prose_requirements(classification),
    }

def build_decision_slots(evidence_ledger: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    vocabulary = profile_vocabulary(str(evidence_ledger.get("profile_id", DEFAULT_PROFILE_ID)))
    slots = {
        "default_population": [],
        "dose_or_intensity_threshold": [],
        "high_risk_subgroup": [],
        "mechanism": [],
        "substitution_or_comparator": [],
        "endpoint_type": [],
        "study_design": [],
        "practical_recommendation": [],
        "technical_or_capacity": [],
        "implementation_constraint": [],
        "safety_or_risk": [],
        "setting_or_context": [],
    }
    rows = [row for row in evidence_ledger.get("all_evidence", []) if isinstance(row, dict)]
    for row in sorted(rows, key=lambda item: (-int(item.get("score", 0)), str(item.get("claim_id", "")))):
        claim = str(row.get("claim", ""))
        for slot in row.get("decision_slots", []):
            if slot not in slots:
                continue
            if not _row_allowed_for_decision_slot(row, slot):
                continue
            value = _slot_value(slot, claim, vocabulary=vocabulary)
            if not value:
                continue
            if not _slot_value_allowed(slot, value, claim):
                continue
            entry = {
                "value": value,
                "claim": claim,
                "claim_id": row.get("claim_id", ""),
                "source": row.get("source", ""),
                "weight": row.get("weight", "medium"),
                "evidence_family": row.get("evidence_family", "general_evidence"),
            }
            if not _slot_entry_exists(slots[slot], entry):
                slots[slot].append(entry)
    return {slot: entries[:6] for slot, entries in slots.items()}


def _row_allowed_for_decision_slot(row: dict[str, Any], slot: str) -> bool:
    if row.get("appendix_only"):
        return False
    question_fit = row.get("question_fit", {}) if isinstance(row.get("question_fit"), dict) else {}
    status = str(question_fit.get("status", ""))
    if status == "mismatch":
        return False
    if status == "narrower_than_question":
        return slot in {"high_risk_subgroup", "safety_or_risk"}
    if slot in {"default_population", "practical_recommendation", "substitution_or_comparator"}:
        return bool(row.get("top_line_eligible")) or status in {"fits", "uncertain", "not_supplied", ""}
    return True

def build_map_sufficiency_report(
    candidate_map: dict[str, Any],
    *,
    question: str,
    evidence_ledger: dict[str, Any],
    decision_model: dict[str, Any],
    quality_report: dict[str, Any],
) -> dict[str, Any]:
    slots = decision_model.get("decision_slots", {}) if isinstance(decision_model.get("decision_slots"), dict) else {}
    families = evidence_ledger.get("family_counts", {}) if isinstance(evidence_ledger.get("family_counts"), dict) else {}
    expected_slots = _expected_slots_for_question(question, evidence_ledger, vocabulary=_profile_vocabulary_for_map(candidate_map))
    expected_families = _expected_families_for_question(question)
    present_slots = sorted(slot for slot, entries in slots.items() if isinstance(entries, list) and entries)
    missing_expected_slots = [slot for slot in expected_slots if slot not in present_slots]
    missing_expected_families = [family for family in expected_families if int(families.get(family, 0)) == 0]
    obligations = _sufficiency_output_obligations(slots, missing_expected_slots, missing_expected_families)
    issues = _sufficiency_issues(
        claim_count=len(_claims(candidate_map)),
        relation_count=len(_relations(candidate_map)),
        missing_expected_slots=missing_expected_slots,
        missing_expected_families=missing_expected_families,
        quality_report=quality_report,
    )
    status = _sufficiency_status(issues)
    return {
        "schema_id": "map_sufficiency_report_v1",
        "method": "question_expected_slots_plus_map_detected_slots_and_evidence_families",
        "status": status,
        "question_profile": {
            "expected_decision_slots": expected_slots,
            "expected_evidence_families": expected_families,
        },
        "present_decision_slots": {
            slot: entries
            for slot, entries in slots.items()
            if isinstance(entries, list) and entries
        },
        "missing_expected_decision_slots": missing_expected_slots,
        "present_evidence_families": families,
        "missing_expected_evidence_families": missing_expected_families,
        "output_obligations": obligations,
        "issues": issues,
        "notes": [
            "This report evaluates whether the current map exposes decision-support ingredients; it does not judge whether the underlying sources are complete.",
            "Unresolved slots should be acknowledged in the briefing when they matter to the question, not filled in by inference.",
        ],
    }

def _expected_slots_for_question(question: str, evidence_ledger: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> list[str]:
    normalized = f" {re.sub(r'\\s+', ' ', question.lower())} "
    expected = ["endpoint_type", "study_design"]
    marker_map = _vocabulary_marker_map(vocabulary, "expected_slot_question_markers")
    for slot, markers in marker_map.items():
        if any(marker in normalized for marker in markers):
            expected.append(slot)
    counts = evidence_ledger.get("decision_slot_counts", {}) if isinstance(evidence_ledger.get("decision_slot_counts"), dict) else {}
    for slot in (
        "dose_or_intensity_threshold",
        "high_risk_subgroup",
        "substitution_or_comparator",
        "mechanism",
        "technical_or_capacity",
        "implementation_constraint",
        "safety_or_risk",
        "setting_or_context",
    ):
        if int(counts.get(slot, 0)) > 0:
            expected.append(slot)
    return _dedupe(expected)

def _expected_families_for_question(question: str) -> list[str]:
    normalized = f" {re.sub(r'\\s+', ' ', question.lower())} "
    expected = ["cohort_or_observational", "evidence_synthesis"]
    if any(marker in normalized for marker in (" should ", " recommend", " advice", " guidance", " policy", " decision")):
        expected.append("guideline_or_recommendation")
    if any(marker in normalized for marker in (" trial", " intervention", " treatment", " randomized", " randomised", " rct")):
        expected.append("rct_or_intervention")
    if any(marker in normalized for marker in (" mechanism", " why ", " causal", " biomarker", " pathway")):
        expected.append("mechanism_or_biomarker")
    return _dedupe(expected)

def _sufficiency_output_obligations(
    slots: dict[str, Any],
    missing_expected_slots: list[str],
    missing_expected_families: list[str],
) -> list[dict[str, Any]]:
    obligations: list[dict[str, Any]] = []
    for slot, entries in slots.items():
        if not isinstance(entries, list) or not entries:
            continue
        label = _slot_label(slot)
        values = [str(entry.get("value", "")).strip() for entry in entries if isinstance(entry, dict) and str(entry.get("value", "")).strip()]
        if not values:
            continue
        obligations.append(
            {
                "obligation_id": f"present_{slot}",
                "kind": "include_present_slot",
                "slot": slot,
                "instruction": f"Include at least one map-backed {label}.",
                "candidate_values": values[:4],
            }
        )
    for slot in missing_expected_slots:
        obligations.append(
            {
                "obligation_id": f"missing_{slot}",
                "kind": "acknowledge_missing_slot",
                "slot": slot,
                "instruction": f"State that the current map does not cleanly establish a {_slot_label(slot)} if relevant.",
                "candidate_values": [],
            }
        )
    for family in missing_expected_families:
        obligations.append(
            {
                "obligation_id": f"missing_family_{family}",
                "kind": "acknowledge_missing_family",
                "evidence_family": family,
                "instruction": f"State that {family.replace('_', ' ')} evidence is unassessed when the current map does not cleanly establish it.",
                "candidate_values": [],
            }
        )
    return obligations[:16]

def _sufficiency_issues(
    *,
    claim_count: int,
    relation_count: int,
    missing_expected_slots: list[str],
    missing_expected_families: list[str],
    quality_report: dict[str, Any],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if claim_count == 0:
        issues.append({"severity": "fail", "issue_type": "no_claims", "message": "The map has no claims to synthesize."})
    if relation_count == 0:
        issues.append({"severity": "warning", "issue_type": "no_relations", "message": "The map exposes no claim relations or tensions."})
    relation_floor = max(2, claim_count // 20) if claim_count >= 20 else 0
    if relation_floor and relation_count < relation_floor:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "sparse_relation_graph",
                "message": f"The map has {relation_count} relation(s) for {claim_count} claim(s); synthesis may read like ranked snippets instead of an argument graph.",
            }
        )
    for slot in missing_expected_slots:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "missing_expected_decision_slot",
                "message": f"The question appears to require {_slot_label(slot)}, but {_lower_first(reader_facing_unresolved_slot(slot).removesuffix('.'))}.",
            }
        )
    for family in missing_expected_families:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "missing_expected_evidence_family",
                "message": f"The question appears to benefit from {family.replace('_', ' ')} evidence, but {_lower_first(reader_facing_unresolved_family(family).removesuffix('.'))}.",
            }
        )
    if confidence_cap(quality_report) != "high":
        issues.append(
            {
                "severity": "warning",
                "issue_type": "quality_report_caps_confidence",
                "message": f"The map quality report caps confidence at {confidence_cap(quality_report)}.",
            }
        )
    return issues

def _sufficiency_status(issues: list[dict[str, str]]) -> str:
    if any(issue.get("severity") == "fail" for issue in issues):
        return "insufficient"
    if any(issue.get("severity") == "warning" for issue in issues):
        return "usable_with_named_gaps"
    return "sufficient_for_scaffolded_briefing"

def _slot_label(slot: str) -> str:
    return {
        "default_population": "default population",
        "dose_or_intensity_threshold": "dose or intensity threshold",
        "high_risk_subgroup": "high-risk subgroup",
        "mechanism": "mechanism",
        "substitution_or_comparator": "substitution or comparator",
        "endpoint_type": "endpoint type",
        "study_design": "study design",
        "practical_recommendation": "practical recommendation",
        "technical_or_capacity": "technical capacity",
        "implementation_constraint": "implementation constraint",
        "safety_or_risk": "safety or risk",
        "setting_or_context": "setting or context",
        "population_scope": "population or scope",
        "intervention_or_option": "intervention or option",
        "comparator": "comparator",
        "outcome_or_endpoint": "outcome or endpoint",
        "evidence_design": "evidence design",
        "causal_identification": "causal identification",
        "implementation_condition": "implementation condition",
        "harm_or_failure_mode": "harm or failure mode",
        "cost_or_feasibility": "cost or feasibility",
        "equity_or_distribution": "equity or distribution",
        "missing_evidence_gap": "missing evidence gap",
    }.get(slot, slot.replace("_", " "))

def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text

def _missing_decision_slots(evidence_ledger: dict[str, Any]) -> list[str]:
    required = (
        "default_population",
        "dose_or_intensity_threshold",
        "high_risk_subgroup",
        "mechanism",
        "substitution_or_comparator",
        "endpoint_type",
        "study_design",
        "practical_recommendation",
    )
    counts = evidence_ledger.get("decision_slot_counts", {}) if isinstance(evidence_ledger.get("decision_slot_counts"), dict) else {}
    return [slot for slot in required if int(counts.get(slot, 0)) == 0]

def _slot_value(slot: str, claim: str, *, vocabulary: dict[str, Any] | None = None) -> str:
    patterns = _vocabulary_string_map(vocabulary, "slot_value_patterns").get(slot, [])
    if patterns:
        value = _first_pattern(claim, patterns)
        if value:
            return value
    if slot == "practical_recommendation":
        return _short_claim_fragment(claim)
    return _short_claim_fragment(claim)

def _slot_value_allowed(slot: str, value: str, claim: str) -> bool:
    lowered = f" {re.sub(r'\\s+', ' ', value.lower())} "
    claim_lowered = f" {re.sub(r'\\s+', ' ', claim.lower())} "
    if _looks_like_non_substantive_slot_text(value):
        return False
    if slot == "default_population":
        if re.search(r"\b(?:person-years|person years|follow-up|participants?\s+with\s+bmi|sample size|cohort included\s+\d)\b", lowered):
            return False
        return bool(re.search(r"\b(?:adults?|people|patients?|participants?|children|infants?|households|schools|workers|residents|free of|without)\b", lowered))
    if slot == "dose_or_intensity_threshold":
        return bool(re.search(r"\b(?:\d|per\s+day|daily|weekly|dose|threshold|intake|exposure|level|amount)\b", lowered))
    if slot == "endpoint_type":
        if value.strip().lower() == claim.strip().lower() and len(value.split()) <= 8:
            return False
        return bool(re.search(r"\b(?:risk|mortality|events?|outcome|endpoint|hospitalization|stroke|disease|failure|safety|harm|biomarker|marker)\b", lowered))
    if slot == "practical_recommendation":
        return bool(re.search(r"\b(?:recommend|guideline|advice|should|must|offer|provide|use|avoid|prefer|treat)\b", claim_lowered))
    return True

def _looks_like_non_substantive_slot_text(text: str) -> bool:
    lowered = text.lower()
    if "appendix-only extraction" in lowered or "consult the source before using it as evidence" in lowered:
        return True
    if re.search(r"\b(?:privacy|cookie|linking|whistleblower|conflict of interest|editorial guidelines|terms of use)\s+policy\b", lowered):
        return True
    if re.search(r"\b(?:doi|pmid|pmcid|linkout|official website|https:// ensures|google scholar|crossref)\b", lowered):
        return True
    return False

def _slot_entry_exists(entries: list[dict[str, Any]], candidate: dict[str, Any]) -> bool:
    candidate_terms = set(_content_terms(_normalize_slot_value(str(candidate.get("value", "")))))
    for entry in entries:
        entry_terms = set(_content_terms(_normalize_slot_value(str(entry.get("value", "")))))
        if candidate_terms and entry_terms and len(candidate_terms & entry_terms) / min(len(candidate_terms), len(entry_terms)) >= 0.75:
            return True
    return False

def _normalize_slot_value(value: str) -> str:
    normalized = value.lower()
    normalized = re.sub(r"\b(?:people|patients|adults|individuals|participants)\b", "person", normalized)
    normalized = re.sub(r"\btype\s*2\s*diabetes\b|\bt2d\b", "diabetes", normalized)
    return normalized

def _first_pattern(text: str, patterns: list[str] | tuple[str, ...]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip(" ,.;")
    return ""

def _short_claim_fragment(text: str, max_chars: int = 140) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    candidate = cleaned[: max_chars - 3].rstrip(" ,.;")
    last_space = candidate.rfind(" ")
    if last_space >= max(24, int(max_chars * 0.6)):
        candidate = candidate[:last_space].rstrip(" ,.;")
    return candidate + "..."

def build_briefing_plan(
    partition: dict[str, Any],
    contract: dict[str, Any],
    evidence_ledger: dict[str, Any],
    quality_report: dict[str, Any],
    decision_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    top_by_section = evidence_ledger.get("top_evidence_by_section", {})
    support = _ledger_claim_texts(top_by_section.get("main_support", []), weight_floor="medium")
    conflicts = _ledger_claim_texts(top_by_section.get("conflicting_evidence", []), weight_floor="medium")
    scope = _ledger_claim_texts(top_by_section.get("scope_limits", []), weight_floor="low")
    methods = _ledger_claim_texts(top_by_section.get("method_limits", []), weight_floor="low")
    answer_frame = contract.get("answer_frame", {}) if isinstance(contract.get("answer_frame"), dict) else {}
    decision_model = decision_model or {}
    default_answer = decision_model.get("default_answer", {}) if isinstance(decision_model.get("default_answer"), dict) else {}
    return {
        "schema_id": "briefing_plan_v1",
        "opening_move": default_answer.get(
            "plain_language_instruction",
            answer_frame.get("default_stance_instruction", "Answer directly with calibrated uncertainty."),
        ),
        "paragraph_order": [
            {
                "section": "bottom_line",
                "job": "Give the controlling answer frame in the decision question's natural vocabulary, then name the strongest counterposition if present.",
                "must_use": _dedupe([
                    str(default_answer.get("plain_language_instruction", "")),
                    str(default_answer.get("why_this_frame", "")),
                    str(answer_frame.get("strongest_counterposition", "")),
                    *support[:2],
                    *conflicts[:1],
                ])[:5],
            },
            {
                "section": "why_this_read",
                "job": "Explain the weighted support without overstating null, indirect, or backfilled evidence.",
                "must_use": support[:4],
            },
            {
                "section": "what_pushes_back",
                "job": "Explain contrary evidence and tensions as live considerations, not as afterthoughts.",
                "must_use": conflicts[:4],
            },
            {
                "section": "where_it_applies",
                "job": "Separate population, dose, endpoint, and setting boundaries from the general answer.",
                "must_use": scope[:4],
            },
            {
                "section": "why_not_stronger",
                "job": "Name method, source-completeness, quality-report, and coverage limits.",
                "must_use": _dedupe([*methods[:4], *quality_report_issue_text(quality_report)[:3]])[:6],
            },
        ],
        "section_transition_rules": [
            "Combine evidence-role bullets into synthesis sentences when that preserves the meaning.",
            "Let low-weight evidence drive the bottom line only when it is the only evidence on a decision-critical caveat.",
            "When evidence conflicts, state what scope or method difference explains the tension if the map supports one.",
        ],
    }

def _claim_evidence_weight_score(
    claim: dict[str, Any],
    section: str,
    quality_report: dict[str, Any],
    source_lookup: dict[str, str],
    *,
    vocabulary: dict[str, Any] | None = None,
) -> tuple[int, list[str]]:
    score = 2
    modifiers: list[str] = ["base_source_grounded_claim"]
    entailed = str(claim.get("entailed_by_excerpt", "")).lower()
    if entailed == "yes":
        score += 2
        modifiers.append("entailed_by_excerpt")
    elif entailed == "uncertain":
        score -= 1
        modifiers.append("uncertain_entailment")
    else:
        score -= 2
        modifiers.append("not_entailed_or_unmarked")
    role = str(claim.get("role", "other"))
    if role in {"crux", "conclusion_support"}:
        score += 2
        modifiers.append(f"decision_role:{role}")
    elif role in {"scope_limit", "external_validity", "implementation_constraint", "measurement_validity", "cost_feasibility"}:
        score += 1
        modifiers.append(f"boundary_role:{role}")
    supporting_sources = _claim_supporting_sources_for_briefing(claim)
    if len(supporting_sources) > 1:
        score += min(2, len(supporting_sources) - 1)
        modifiers.append(f"multi_source_support:{len(supporting_sources)}")
    extraction_method = str(claim.get("extraction_method", "model"))
    if extraction_method == "deterministic_coverage_backfill":
        score -= 1
        modifiers.append("coverage_backfill_lower_weight")
    elif extraction_method.startswith("deterministic"):
        score -= 1
        modifiers.append("deterministic_fallback_lower_weight")
    source_name = source_lookup.get(str(claim.get("source_id", "")), str(claim.get("source_id", "")))
    source_text = f"{source_name} {claim.get('source_id', '')}".lower()
    if any(marker in source_text for marker in ("abstract", "pubmed", "metadata")):
        score -= 1
        modifiers.append("source_incomplete_or_abstract")
    text = _claim_text_bundle(claim)
    if _looks_like_method_or_source_limit(text):
        score -= 1
        modifiers.append("method_or_source_limit")
    if _looks_like_scope_or_subgroup(text, vocabulary=vocabulary):
        modifiers.append("scope_specific")
    if _contains_hard_outcome_signal(text, vocabulary=vocabulary):
        score += 1
        modifiers.append("hard_outcome_signal")
    if _contains_surrogate_signal(text, vocabulary=vocabulary):
        score -= 1
        modifiers.append("surrogate_or_biomarker_signal")
    concepts = _claim_concepts(claim, vocabulary=vocabulary)
    if concepts:
        score += min(2, max(1, len(concepts) // 2))
        modifiers.append(f"decision_concept_count:{len(concepts)}")
    noise = _claim_noise_profile(claim)
    if int(noise.get("penalty", 0)):
        score -= int(noise.get("penalty", 0))
        modifiers.append(f"noise:{noise.get('kind')}")
    if section in {"main_support", "conflicting_evidence"} and (
        _looks_like_support_evidence(text, vocabulary=vocabulary) or _looks_like_concern_evidence(text, vocabulary=vocabulary)
    ):
        score += 1
        modifiers.append("directional_decision_signal")
    if any(isinstance(issue, dict) and issue.get("severity") == "risk" for issue in quality_report.get("issues", [])):
        modifiers.append("quality_risk_context")
    return max(0, min(score, 8)), modifiers

def _claim_concepts(claim: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> list[str]:
    text = _claim_text_bundle(claim)
    concept_markers = (vocabulary or profile_vocabulary(DEFAULT_PROFILE_ID)).get("claim_concept_markers", {})
    if not isinstance(concept_markers, dict):
        concept_markers = {}
    concepts: list[str] = []
    for concept, markers in concept_markers.items():
        marker_list = [str(marker).lower() for marker in markers] if isinstance(markers, list) else []
        if any(marker in text for marker in marker_list):
            concepts.append(str(concept))
    return _filter_claim_concepts_by_visible_text(concepts, text, vocabulary=vocabulary)

def _filter_claim_concepts_by_visible_text(
    concepts: list[str],
    text: str,
    *,
    vocabulary: dict[str, Any] | None = None,
) -> list[str]:
    required_markers = _vocabulary_nested_marker_map(vocabulary, "concept_visible_required_markers")
    filtered = list(concepts)
    for concept in concepts:
        marker_groups = required_markers.get(concept, [])
        if marker_groups and not any(any(marker in text for marker in group) for group in marker_groups):
            filtered = [item for item in filtered if item != concept]
    return filtered

def _evidence_family_for_claim(
    claim: dict[str, Any],
    section: str,
    source_lookup: dict[str, str],
    *,
    vocabulary: dict[str, Any] | None = None,
) -> str:
    text = " ".join(
        str(part or "")
        for part in (
            claim.get("claim"),
            claim.get("text"),
            claim.get("excerpt"),
            claim.get("role"),
            claim.get("source_id"),
            source_lookup.get(str(claim.get("source_id", "")), ""),
        )
    ).lower()
    for family, markers in _vocabulary_marker_map(vocabulary, "evidence_family_markers").items():
        if any(marker in text for marker in markers):
            return family
    if section == "scope_limits" or _looks_like_scope_or_subgroup(text, vocabulary=vocabulary):
        return "subgroup_or_scope"
    if section == "method_limits" or _looks_like_method_or_source_limit(text):
        return "method_or_validity"
    return "general_evidence"

def _decision_slots_for_claim(claim: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> list[str]:
    text = _claim_text_bundle(claim)
    slots: list[str] = []
    slot_markers = (vocabulary or profile_vocabulary(DEFAULT_PROFILE_ID)).get("decision_slot_markers", {})
    if not isinstance(slot_markers, dict):
        slot_markers = {}
    for slot, markers in slot_markers.items():
        marker_list = [str(marker).lower() for marker in markers] if isinstance(markers, list) else []
        if any(marker in text for marker in marker_list):
            slots.append(str(slot))
    return slots or ["unspecified"]

def _evidence_slots_for_claim(claim: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> list[str]:
    text = _claim_text_bundle(claim)
    slots: list[str] = []
    markers = (vocabulary or profile_vocabulary(DEFAULT_PROFILE_ID)).get("evidence_slot_markers", {})
    if not isinstance(markers, dict):
        markers = {}
    for slot, slot_markers in markers.items():
        marker_list = [str(marker).lower() for marker in slot_markers] if isinstance(slot_markers, list) else []
        if any(marker in text for marker in marker_list):
            slots.append(str(slot))
    return _dedupe(slots) or ["other_evidence"]

def _evidence_slot_why_it_matters(slot: str) -> str:
    return {
        "population_scope": "Controls whether the evidence transfers to the decision setting.",
        "intervention_or_option": "Identifies the option whose performance is being judged.",
        "comparator": "Prevents the recommendation from ignoring the real alternative.",
        "outcome_or_endpoint": "Separates decision-relevant endpoints from proxies or intermediate signals.",
        "evidence_design": "Controls how much causal and external-validity weight the evidence can bear.",
        "causal_identification": "Names whether the observed result can be attributed to the option itself.",
        "implementation_condition": "Gates whether the option can work in practice.",
        "harm_or_failure_mode": "Identifies ways the preferred option could fail or cause downside risk.",
        "cost_or_feasibility": "Captures constraints that can reverse an otherwise attractive option.",
        "equity_or_distribution": "Keeps distributional and subgroup consequences visible.",
        "missing_evidence_gap": "Prevents absent evidence from being filled in by inference.",
    }.get(slot, "This evidence slot affects how far the conclusion should travel.")

def _question_options(question: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", question.strip().rstrip("?"))
    patterns = (
        r"\bprioritize\s+(?P<a>.+?)\s+over\s+(?P<b>.+?)(?:\s+to\b|\s+for\b|$)",
        r"\bshould\s+(?P<a>.+?)\s+(?:rather than|instead of|over|versus|vs\.?)\s+(?P<b>.+?)(?:\s+to\b|\s+for\b|$)",
        r"(?P<a>.+?)\s+(?:versus|vs\.?)\s+(?P<b>.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if not match:
            continue
        options = [_clean_option_text(match.group("a")), _clean_option_text(match.group("b"))]
        options = [option for option in options if option and len(option.split()) <= 12]
        if len(options) == 2:
            return _dedupe(options)
    return []

def _clean_option_text(text: str) -> str:
    text = re.sub(r"^(?:a|an|the|city|cities|mid-sized city|mid-sized cities)\s+", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\bthis year\b.*$", "", text, flags=re.IGNORECASE)
    return text.strip(" ,.;:")

def _infer_options_from_evidence(evidence_ledger: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> list[str]:
    text = " ".join(str(row.get("claim", "")) for row in evidence_ledger.get("all_evidence", []) if isinstance(row, dict)).lower()
    candidates: list[str] = []
    markers_by_option = (vocabulary or {}).get("option_inference_markers", {})
    if isinstance(markers_by_option, dict):
        for option, markers in markers_by_option.items():
            marker_list = [str(marker).lower() for marker in markers] if isinstance(markers, list) else []
            if marker_list and any(marker in text for marker in marker_list):
                candidates.append(str(option))
    return _dedupe(candidates)[:3]

def _option_terms(option: str, *, vocabulary: dict[str, Any] | None = None) -> list[str]:
    terms = [term for term in _content_terms(option) if len(term) >= 4]
    aliases = (vocabulary or {}).get("option_aliases", {})
    if not isinstance(aliases, dict):
        aliases = {}
    expanded = list(terms)
    for term in terms:
        values = aliases.get(term, [])
        if isinstance(values, list):
            expanded.extend(str(value) for value in values)
    return _dedupe(expanded)

def _option_terms_by_option(options: list[str], *, vocabulary: dict[str, Any] | None = None) -> dict[str, list[str]]:
    raw = {option: _option_terms(option, vocabulary=vocabulary) for option in options}
    term_counts: Counter[str] = Counter(term for terms in raw.values() for term in terms)
    resolved: dict[str, list[str]] = {}
    for option, terms in raw.items():
        discriminating = [term for term in terms if term_counts[term] == 1]
        resolved[option] = discriminating or terms
    return resolved

def _option_criteria_for_rows(rows: list[dict[str, Any]]) -> list[str]:
    base = ["outcome_effect", "comparator_scope", "implementation_condition", "cost_feasibility", "harm_or_failure_mode", "equity_distribution", "evidence_strength"]
    present_slots = {slot for row in rows for slot in row.get("evidence_slots", []) if isinstance(slot, str)}
    if "causal_identification" in present_slots:
        base.append("causal_attribution")
    return base

def _row_matches_option(row: dict[str, Any], option_terms: list[str]) -> bool:
    text = str(row.get("claim", "")).lower()
    return any(_text_has_option_term(text, term) for term in option_terms)

def _text_has_option_term(text: str, term: str) -> bool:
    term = str(term).strip().lower()
    if not term:
        return False
    return bool(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text))

def _row_matches_option_criterion(row: dict[str, Any], criterion: str) -> bool:
    slots = set(str(slot) for slot in row.get("evidence_slots", []) if isinstance(slot, str))
    concepts = set(str(concept) for concept in row.get("decision_concepts", []) if isinstance(concept, str))
    section = str(row.get("section", ""))
    mapping = {
        "outcome_effect": {"outcome_or_endpoint", "intervention_or_option"},
        "comparator_scope": {"comparator"},
        "implementation_condition": {"implementation_condition"},
        "cost_feasibility": {"cost_or_feasibility"},
        "harm_or_failure_mode": {"harm_or_failure_mode"},
        "equity_distribution": {"equity_or_distribution"},
        "evidence_strength": {"evidence_design", "causal_identification"},
        "causal_attribution": {"causal_identification"},
    }
    if slots.intersection(mapping.get(criterion, set())):
        return True
    if criterion == "implementation_condition" and {"implementation_constraint", "technical_performance_or_capacity"}.intersection(concepts):
        return True
    if criterion == "comparator_scope" and {"alternative_or_comparator", "substitution_or_comparator"}.intersection(concepts):
        return True
    if criterion == "harm_or_failure_mode" and (section == "conflicting_evidence" or "safety_or_adverse_effect" in concepts):
        return True
    return False



# Public facade dependency imports.
from epistemic_case_mapper.map_briefing_claim_eligibility import (
    claim_eligibility_profile as _claim_eligibility_profile,
    claim_noise_profile as _claim_noise_profile,
)
from epistemic_case_mapper.map_briefing_evidence_partition import (
    _attach_cluster_tensions,
    _claim_stance,
    _claim_supporting_sources_for_briefing,
    _classification_instruction,
    _cluster_direction,
    _cluster_proposition,
    _cluster_proposition_rows,
    _cluster_scope_items,
    _cluster_weight_label,
    _contains_hard_outcome_signal,
    _contains_surrogate_signal,
    _decision_classification,
    _decision_frame_reason,
    _decision_model_prose_requirements,
    _ledger_claim_texts,
    _practical_recommendations,
    _proposition_cluster_key,
    _scope_dimensions_for_text,
    _tension_resolution_rows,
    _what_would_change_answer,
    quality_report_issue_text,
)
from epistemic_case_mapper.map_briefing_map_utils import (
    _claim_text_bundle,
    _claims,
    _looks_like_concern_evidence,
    _looks_like_method_or_source_limit,
    _looks_like_scope_or_subgroup,
    _looks_like_support_evidence,
    _relations,
    confidence_cap,
    display_source_name,
)
from epistemic_case_mapper.map_briefing_reader_contracts import (
    _profile_vocabulary_for_map,
    _vocabulary_marker_map,
    _vocabulary_nested_marker_map,
    _vocabulary_string_map,
)
from epistemic_case_mapper.map_briefing_validation import _content_terms, _dedupe, _string_list
