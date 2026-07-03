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

def _option_criterion_label(criterion: str) -> str:
    return {
        "outcome_effect": "Outcome effect",
        "comparator_scope": "Comparator scope",
        "implementation_condition": "Implementation condition",
        "cost_feasibility": "Cost or feasibility",
        "harm_or_failure_mode": "Harm or failure mode",
        "equity_distribution": "Equity or distribution",
        "evidence_strength": "Evidence strength",
        "causal_attribution": "Causal attribution",
    }.get(criterion, criterion.replace("_", " "))

def _option_current_read(option: str, criterion: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"No clean {criterion.replace('_', ' ')} evidence is established for {option}."
    claim = _short_claim_fragment(str(rows[0].get("claim", "")), max_chars=220)
    source = str(rows[0].get("source", "")).strip()
    return claim + (f" ({source})" if source and source not in claim else "")

def _option_evidence_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": row.get("claim_id"),
        "claim": _short_claim_fragment(str(row.get("claim", "")), max_chars=220),
        "source": row.get("source"),
        "weight": row.get("weight"),
        "section": row.get("section"),
    }

def _option_tradeoff_rows(
    options: list[str],
    rows: list[dict[str, Any]],
    option_terms_by_option: dict[str, list[str]] | None = None,
    vocabulary: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    tradeoffs: list[dict[str, Any]] = []
    option_terms_by_option = option_terms_by_option or _option_terms_by_option(options, vocabulary=vocabulary)
    for criterion in _option_criteria_for_rows(rows):
        evidence_by_option = {}
        for option in options:
            option_terms = option_terms_by_option.get(option, _option_terms(option, vocabulary=vocabulary))
            matches = [
                row
                for row in rows
                if _row_matches_option(row, option_terms) and _row_matches_option_criterion(row, criterion)
            ]
            evidence_by_option[option] = [_option_evidence_row(row) for row in sorted(matches, key=lambda row: -int(row.get("score", 0)))[:2]]
        if any(evidence_by_option.values()):
            tradeoffs.append(
                {
                    "criterion": criterion,
                    "label": _option_criterion_label(criterion),
                    "evidence_by_option": evidence_by_option,
                    "decision_use": _option_tradeoff_decision_use(criterion),
                }
            )
    return tradeoffs[:8]

def _option_tradeoff_decision_use(criterion: str) -> str:
    return {
        "outcome_effect": "Which option better advances the target outcome.",
        "comparator_scope": "When the comparator changes the recommendation.",
        "implementation_condition": "What must be true for the option to work.",
        "cost_feasibility": "Whether constraints reverse the preferred option.",
        "harm_or_failure_mode": "What failure mode could make the option unsafe or ineffective.",
        "equity_distribution": "Which option better targets people or places with higher need.",
        "evidence_strength": "How much weight the supporting evidence can bear.",
        "causal_attribution": "Whether observed results can be attributed to the option itself.",
    }.get(criterion, "How this criterion affects the option comparison.")

def _option_comparison_summary(options: list[str], tradeoffs: list[dict[str, Any]]) -> str:
    if len(options) >= 2:
        return f"Compares {options[0]} against {options[1]} across {len(tradeoffs)} decision criteria."
    return f"Compares available options across {len(tradeoffs)} decision criteria."

def _claim_contract_row(claim: dict[str, Any]) -> dict[str, str]:
    return {
        "claim_id": str(claim.get("claim_id", "")),
        "claim": _short_claim_fragment(str(claim.get("claim", "")), max_chars=240),
        "source_id": str(claim.get("source_id", "")),
    }

def _crux_label(text: str, relation_type: str, *, vocabulary: dict[str, Any] | None = None) -> str:
    lowered = text.lower()
    rule = _crux_label_rule(lowered, vocabulary)
    if rule:
        return str(rule.get("label", "")).strip() or "Decision-changing condition"
    if relation_type == "in_tension_with":
        return "Tradeoff between competing evidence"
    if relation_type == "depends_on":
        return "Implementation dependency"
    return "Decision-changing condition"

def _crux_why_it_matters(label: str, text: str, relation: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> str:
    rationale = str(relation.get("rationale", "")).strip()
    if rationale:
        return _short_claim_fragment(rationale, max_chars=260)
    rule = _crux_label_rule_for_label(label, vocabulary)
    return str(rule.get("why_it_matters", "")).strip() or "Changing this condition would materially alter the recommendation."

def _crux_current_read(label: str, text: str, *, vocabulary: dict[str, Any] | None = None) -> str:
    rule = _crux_label_rule_for_label(label, vocabulary)
    return str(rule.get("current_read", "")).strip() or "The current packet treats this condition as relevant to the recommendation."

def _crux_would_change_if(label: str, text: str, *, vocabulary: dict[str, Any] | None = None) -> str:
    rule = _crux_label_rule_for_label(label, vocabulary)
    return str(rule.get("would_change_if", "")).strip() or "New evidence showed the condition did not materially affect the decision."

def _crux_label_rule(text: str, vocabulary: dict[str, Any] | None = None) -> dict[str, Any]:
    for rule in (vocabulary or profile_vocabulary(DEFAULT_PROFILE_ID)).get("crux_label_rules", []):
        if not isinstance(rule, dict):
            continue
        markers = [str(marker).lower() for marker in rule.get("markers", []) if str(marker).strip()]
        if markers and any(marker in text for marker in markers):
            return rule
    return {}

def _crux_label_rule_for_label(label: str, vocabulary: dict[str, Any] | None = None) -> dict[str, Any]:
    for rule in (vocabulary or profile_vocabulary(DEFAULT_PROFILE_ID)).get("crux_label_rules", []):
        if isinstance(rule, dict) and str(rule.get("label", "")).strip() == label:
            return rule
    return {}

def _crux_affected_options(label: str, option_comparison: dict[str, Any], *, vocabulary: dict[str, Any] | None = None) -> list[str]:
    options = [
        str(option.get("option", ""))
        for option in option_comparison.get("options", [])
        if isinstance(option, dict) and str(option.get("option", "")).strip()
    ]
    if not options:
        return []
    lowered = label.lower()
    if any(marker in lowered for marker in _vocabulary_marker_list(vocabulary, "crux_option_scope_markers")):
        return options[:2]
    return options[:1]

def _dedupe_crux_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = " ".join(_content_terms(str(row.get("crux", "")))[:8])
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped

def _fallback_crux_rows_from_option_comparison(
    option_comparison: dict[str, Any],
    evidence_ledger: dict[str, Any],
    *,
    existing: set[str],
    vocabulary: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    labels = _vocabulary_string_list(vocabulary, "fallback_crux_labels")
    for label in labels:
        if label in existing:
            continue
        rows.append(
            {
                "crux": label,
                "relation_type": "crux_for",
                "why_it_matters": _crux_why_it_matters(label, "", {}, vocabulary=vocabulary),
                "current_read": _crux_current_read(label, "", vocabulary=vocabulary),
                "would_change_if": _crux_would_change_if(label, "", vocabulary=vocabulary),
                "affected_options": _crux_affected_options(label, option_comparison, vocabulary=vocabulary),
                "evidence": [],
            }
        )
    return rows

def _decision_slot_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for slot in row.get("decision_slots", []):
            if not isinstance(slot, str):
                continue
            counts[slot] = counts.get(slot, 0) + 1
    return counts

def _weight_label(score: int) -> str:
    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    return "low"

def _ledger_claim_texts(rows: Any, *, weight_floor: str) -> list[str]:
    if not isinstance(rows, list):
        return []
    floor = {"low": 0, "medium": 1, "high": 2}.get(weight_floor, 0)
    values = {"low": 0, "medium": 1, "high": 2}
    texts: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if values.get(str(row.get("weight")), 0) < floor:
            continue
        claim = str(row.get("claim", "")).strip()
        source = str(row.get("source", "")).strip()
        weight = str(row.get("weight", "")).strip()
        if claim:
            texts.append(f"{claim} ({source}; {weight} weight)" if source else f"{claim} ({weight} weight)")
    return texts

def _claim_supporting_sources_for_briefing(claim: dict[str, Any]) -> list[str]:
    sources = [str(claim.get("source_id", ""))]
    for source_id in claim.get("supporting_sources", []):
        if isinstance(source_id, str):
            sources.append(source_id)
    return sorted({source_id for source_id in sources if source_id})

def _contains_hard_outcome_signal(text: str, *, vocabulary: dict[str, Any] | None = None) -> bool:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    return any(marker in normalized for marker in _vocabulary_marker_list(vocabulary, "hard_outcome_signal_markers"))

def _contains_surrogate_signal(text: str, *, vocabulary: dict[str, Any] | None = None) -> bool:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    return any(marker in normalized for marker in _vocabulary_marker_list(vocabulary, "surrogate_signal_markers"))

def _counts(items: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if not item:
            continue
        key = str(item)
        counts[key] = counts.get(key, 0) + 1
    return counts

def _proposition_cluster_key(claim: dict[str, Any], section: str) -> str:
    stance = _claim_stance(claim, section)
    text = _claim_text_bundle(claim)
    dimensions = _scope_dimensions_for_text(text)
    dimension_key = "+".join(dimensions[:2]) if dimensions else "general"
    endpoint_key = "hard_outcome" if _contains_hard_outcome_signal(text) else "surrogate" if _contains_surrogate_signal(text) else "non_endpoint"
    if section in {"main_support", "conflicting_evidence"}:
        return "|".join((_cluster_direction(section), stance, dimension_key, endpoint_key))
    if section == "scope_limits":
        return "|".join((_cluster_direction(section), stance, dimension_key))
    return "|".join((_cluster_direction(section), stance, endpoint_key))

def _cluster_direction(section: str) -> str:
    return {
        "main_support": "supports_default",
        "conflicting_evidence": "supports_counterposition",
        "scope_limits": "bounds_scope",
        "method_limits": "limits_confidence",
    }.get(section, "supports_default")

def _claim_stance(claim: dict[str, Any], section: str) -> str:
    text = _claim_text_bundle(claim)
    if section == "main_support":
        if _has_absence_or_null_signal(text):
            return "low_concern_or_null"
        if _has_benefit_signal(text):
            return "benefit_or_lower_risk"
        return "supportive"
    if section == "conflicting_evidence":
        if _looks_like_concern_evidence(text):
            return "harm_or_higher_risk"
        return "contrary_or_tension"
    if section == "scope_limits":
        dimensions = _scope_dimensions_for_text(text)
        return dimensions[0] if dimensions else "scope_boundary"
    if _contains_surrogate_signal(text):
        return "surrogate_or_endpoint_limit"
    if _looks_like_method_or_source_limit(text):
        return "method_or_source_limit"
    return "interpretation_limit"

def _has_absence_or_null_signal(text: str) -> bool:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    return any(
        marker in normalized
        for marker in (
            " not associated ",
            " no association ",
            " no significant ",
            " no adverse ",
            " did not have adverse ",
            " did not result in adverse ",
            " not independently associated ",
        )
    )

def _has_benefit_signal(text: str) -> bool:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    return any(
        marker in normalized
        for marker in (
            " lower risk ",
            " reduced risk ",
            " reduced mortality ",
            " improved survival ",
            " beneficial ",
            " favorable ",
        )
    )

def _cluster_weight_label(scores: list[int], labels: list[str]) -> str:
    if not scores:
        return "low"
    if "high" in labels and sum(scores) >= 8:
        return "high"
    if sum(scores) >= 4 or "medium" in labels:
        return "medium"
    return "low"

def _cluster_proposition(cluster: dict[str, Any]) -> str:
    direction = str(cluster.get("direction", ""))
    stance = str(cluster.get("stance", ""))
    reps = cluster.get("representative_claims", [])
    representative = ""
    if reps and isinstance(reps[0], dict):
        representative = str(reps[0].get("claim", ""))
    if direction == "supports_default":
        if stance == "low_concern_or_null":
            return "Evidence supports a neutral or low-concern default under the stated conditions."
        if stance == "benefit_or_lower_risk":
            return "Some evidence points toward lower risk or benefit, but this should remain scope-qualified unless it dominates counterevidence."
        return "Evidence supports the default answer under stated conditions."
    if direction == "supports_counterposition":
        if stance == "harm_or_higher_risk":
            return "Counterevidence supports caution because some evidence indicates harm or higher risk."
        return "Counterevidence creates a live tension with the default answer."
    if direction == "bounds_scope":
        return "The answer is bounded by population, dose, setting, endpoint, or time-horizon conditions."
    if direction == "limits_confidence":
        return "Method, endpoint, source-completeness, or implementation limits reduce how strongly the evidence should be read."
    return representative or "A source-grounded proposition affects the decision model."

def _attach_cluster_tensions(clusters: list[dict[str, Any]], relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    claim_to_cluster: dict[str, str] = {}
    for cluster in clusters:
        for claim_id in cluster.get("claim_ids", []):
            claim_to_cluster[str(claim_id)] = str(cluster.get("cluster_id", ""))
    tension_types = {"challenges", "in_tension_with", "crux_for", "depends_on"}
    tensions_by_cluster: dict[str, list[dict[str, str]]] = {}
    for relation in relations:
        relation_type = str(relation.get("relation_type", ""))
        if relation_type not in tension_types:
            continue
        left_cluster = claim_to_cluster.get(str(relation.get("source_claim", "")))
        right_cluster = claim_to_cluster.get(str(relation.get("target_claim", "")))
        if not left_cluster or not right_cluster or left_cluster == right_cluster:
            continue
        row = {
            "relation_type": relation_type,
            "with_cluster": right_cluster,
            "rationale": str(relation.get("rationale", "")),
        }
        tensions_by_cluster.setdefault(left_cluster, []).append(row)
        tensions_by_cluster.setdefault(right_cluster, []).append({**row, "with_cluster": left_cluster})
    for cluster in clusters:
        cluster["tensions"] = tensions_by_cluster.get(str(cluster.get("cluster_id", "")), [])[:5]
    return clusters

def _decision_classification(clusters: list[dict[str, Any]], contract: dict[str, Any]) -> str:
    support = [cluster for cluster in clusters if cluster.get("direction") == "supports_default"]
    counter = [cluster for cluster in clusters if cluster.get("direction") == "supports_counterposition"]
    support_strength = sum(int(cluster.get("strength_score", 0)) for cluster in support)
    counter_strength = sum(int(cluster.get("strength_score", 0)) for cluster in counter)
    null_strength = sum(int(cluster.get("strength_score", 0)) for cluster in support if cluster.get("stance") == "low_concern_or_null")
    benefit_strength = sum(int(cluster.get("strength_score", 0)) for cluster in support if cluster.get("stance") == "benefit_or_lower_risk")
    harm_strength = sum(int(cluster.get("strength_score", 0)) for cluster in counter if cluster.get("stance") == "harm_or_higher_risk")
    scoped_counter_strength = sum(int(cluster.get("strength_score", 0)) for cluster in counter if _cluster_is_scope_specific(cluster))
    answer_frame = contract.get("answer_frame", {}) if isinstance(contract.get("answer_frame"), dict) else {}
    default_instruction = str(answer_frame.get("default_stance_instruction", "")).lower()
    if "low-concern" in default_instruction or "neutral" in default_instruction:
        if harm_strength <= max(4, support_strength * 1.3):
            return "neutral_or_low_concern_under_stated_conditions"
    if support_strength and null_strength and scoped_counter_strength >= harm_strength * 0.45:
        return "neutral_or_low_concern_under_stated_conditions"
    if harm_strength > support_strength * 1.25 and harm_strength >= 8:
        return "caution_or_harm_under_specific_conditions"
    if null_strength >= max(benefit_strength, counter_strength * 0.45) and support_strength >= counter_strength * 0.5:
        return "neutral_or_low_concern_under_stated_conditions"
    if benefit_strength >= max(8, counter_strength * 1.5, null_strength * 1.25):
        return "beneficial_under_stated_conditions"
    if counter_strength and support_strength:
        return "mixed_or_context_dependent"
    if support_strength:
        return "supportive_but_scope_limited"
    return "insufficient_or_uncertain"

def _cluster_is_scope_specific(cluster: dict[str, Any]) -> bool:
    dimensions = {str(item) for item in cluster.get("scope_dimensions", [])}
    if dimensions - {"general", "measurement_endpoint"}:
        return True
    reps = cluster.get("representative_claims", [])
    for rep in reps if isinstance(reps, list) else []:
        if isinstance(rep, dict) and _looks_like_scope_or_subgroup(str(rep.get("claim", ""))):
            return True
    return False

def _classification_instruction(classification: str) -> str:
    return {
        "neutral_or_low_concern_under_stated_conditions": (
            "State the default as neutral or low-concern under the stated conditions; do not frame the default as beneficial."
        ),
        "caution_or_harm_under_specific_conditions": (
            "State that caution is warranted under the named conditions, and separate those conditions from the general case."
        ),
        "beneficial_under_stated_conditions": (
            "State benefit only under the conditions supported by the evidence, then name counterevidence."
        ),
        "mixed_or_context_dependent": (
            "State that the answer is context-dependent, then identify the default case and the conditions that change it."
        ),
        "supportive_but_scope_limited": (
            "State the supportive answer and immediately name the scope and method limits."
        ),
    }.get(classification, "State that the evidence is insufficient or uncertain, then name the most decision-relevant gaps.")

def _decision_frame_reason(
    classification: str,
    support_clusters: list[dict[str, Any]],
    counter_clusters: list[dict[str, Any]],
) -> str:
    top_support = support_clusters[0].get("proposition", "") if support_clusters else ""
    top_counter = counter_clusters[0].get("proposition", "") if counter_clusters else ""
    if classification == "neutral_or_low_concern_under_stated_conditions":
        return "The strongest support is best read as neutral/low-concern or scope-qualified, while counterevidence remains condition-specific."
    if classification == "caution_or_harm_under_specific_conditions":
        return "Counterevidence is strong enough to drive caution in the named conditions."
    if classification == "beneficial_under_stated_conditions":
        return "Benefit-oriented evidence dominates the mapped counterevidence under the stated conditions."
    if classification == "mixed_or_context_dependent":
        return "Support and counterevidence are both live, so the decision turns on scope and applicability conditions."
    return top_support or top_counter or "The current source packet does not provide enough decisive evidence for a stronger frame."

def _cluster_scope_items(clusters: list[dict[str, Any]], *, positive: bool) -> list[str]:
    items: list[str] = []
    for cluster in clusters:
        reps = cluster.get("representative_claims", [])
        for rep in reps if isinstance(reps, list) else []:
            if not isinstance(rep, dict):
                continue
            text = str(rep.get("claim", ""))
            if positive and not _looks_like_concern_evidence(text):
                items.append(text)
            elif not positive and (_looks_like_concern_evidence(text) or _looks_like_scope_or_subgroup(text)):
                items.append(text)
    return _dedupe(items)

def _cluster_proposition_rows(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cluster in clusters:
        rows.append(
            {
                "proposition": cluster.get("proposition", ""),
                "evidence_weight": cluster.get("evidence_weight", "medium"),
                "strength_score": cluster.get("strength_score", 0),
                "representative_claims": cluster.get("representative_claims", [])[:3],
                "sources": cluster.get("sources", [])[:5],
            }
        )
    return rows

def _tension_resolution_rows(clusters: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    cluster_lookup = {str(cluster.get("cluster_id", "")): cluster for cluster in clusters}
    seen: set[tuple[str, str, str]] = set()
    for cluster in clusters:
        for tension in cluster.get("tensions", []):
            if not isinstance(tension, dict):
                continue
            other = cluster_lookup.get(str(tension.get("with_cluster", "")), {})
            key = tuple(sorted((str(cluster.get("cluster_id", "")), str(other.get("cluster_id", ""))))) + (str(tension.get("relation_type", "")),)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "tension": f"{cluster.get('proposition', '')} / {other.get('proposition', '')}",
                    "relation_type": str(tension.get("relation_type", "")),
                    "resolution_hint": _relation_crux_reason(str(tension.get("relation_type", ""))),
                }
            )
    return rows

def _practical_recommendations(
    classification: str,
    scope_clusters: list[dict[str, Any]],
    method_clusters: list[dict[str, Any]],
    evidence_ledger: dict[str, Any] | None = None,
) -> list[str]:
    recommendations = [_classification_instruction(classification)]
    slots = build_decision_slots(evidence_ledger or {})
    for entry in slots.get("dose_or_intensity_threshold", [])[:2]:
        recommendations.append(f"Preserve this dose/intensity boundary in practical guidance: {entry.get('value')}")
    for entry in slots.get("high_risk_subgroup", [])[:3]:
        recommendations.append(f"Name this subgroup separately from the default case: {entry.get('value')}")
    for entry in slots.get("practical_recommendation", [])[:2]:
        recommendations.append(str(entry.get("value")))
    for cluster in scope_clusters[:3]:
        reps = cluster.get("representative_claims", [])
        if reps and isinstance(reps[0], dict):
            recommendations.append(f"Apply the answer only with this boundary visible: {reps[0].get('claim')}")
    if method_clusters:
        recommendations.append("Do not turn method-limited or surrogate evidence into a stronger practical recommendation than the map supports.")
    return _dedupe(recommendations)

def _what_would_change_answer(
    counter_clusters: list[dict[str, Any]],
    method_clusters: list[dict[str, Any]],
    quality_report: dict[str, Any],
) -> list[str]:
    items: list[str] = []
    for cluster in counter_clusters[:3]:
        items.append(f"The answer would shift if this counterposition generalized to the default case: {cluster.get('proposition', '')}")
    for cluster in method_clusters[:2]:
        items.append(f"The answer would strengthen if this limitation were resolved: {cluster.get('proposition', '')}")
    items.extend(quality_report_issue_text(quality_report)[:2])
    return _dedupe(items)

def _decision_model_prose_requirements(classification: str) -> list[str]:
    requirements = [
        "Start the decision brief with the controlling classification in plain language.",
        "Explain evidence clusters, not isolated claim fragments.",
        "Name the strongest counterargument before listing caveats.",
    ]
    if classification == "neutral_or_low_concern_under_stated_conditions":
        requirements.append("Avoid benefit framing such as beneficial, protective, or lower-risk default unless explicitly scoped as subgroup evidence.")
    if classification in {"mixed_or_context_dependent", "caution_or_harm_under_specific_conditions"}:
        requirements.append("Separate the default case from conditions where caution or uncertainty dominates.")
    return requirements

def partition_map_evidence(
    candidate_map: dict[str, Any],
    source_lookup: dict[str, str],
) -> dict[str, Any]:
    claims = _claims(candidate_map)
    relations = _relations(candidate_map)
    claim_lookup = {str(claim.get("claim_id")): claim for claim in claims}
    evidence_roles: dict[str, list[str]] = {
        "main_support": [],
        "conflicting_evidence": [],
        "scope_limits": [],
        "method_limits": [],
    }
    cruxes: list[dict[str, str]] = []
    audit_trail: list[str] = []

    for claim in claims:
        section = _claim_evidence_section(claim)
        reader = _claim_reader_text(claim, source_lookup)
        evidence_roles[section].append(reader)
        if str(claim.get("role", "")) == "crux":
            cruxes.append(
                {
                    "candidate_crux": reader,
                    "why_it_matters": "Changing this claim would materially change the decision read.",
                }
            )
            audit_trail.append(reader)

    for relation in relations:
        relation_type = str(relation.get("relation_type", ""))
        reader = _relation_reader_text(relation, claim_lookup, source_lookup)
        section = _relation_evidence_section(relation, claim_lookup)
        if section:
            evidence_roles[section].append(reader)
        if relation_type in {"crux_for", "depends_on", "in_tension_with", "challenges"}:
            cruxes.append(
                {
                    "candidate_crux": reader,
                    "why_it_matters": _relation_crux_reason(relation_type),
                }
            )
        audit_trail.append(reader)

    return {
        "evidence_roles": {key: _dedupe(value) for key, value in evidence_roles.items()},
        "crux_candidates": _dedupe_dicts(cruxes),
        "audit_trail": _dedupe(audit_trail),
    }

def _support_signal_profile(support_items: list[str], *, vocabulary: dict[str, Any] | None = None) -> dict[str, Any]:
    joined = " ".join(support_items).lower()
    marker_map = _vocabulary_marker_map(vocabulary, "support_signal_profile_markers")
    absence_markers = marker_map.get("absence_of_harm_or_null", [])
    direct_benefit_markers = marker_map.get("direct_benefit", [])
    surrogate_benefit_markers = marker_map.get("surrogate_benefit", [])
    return {
        "absence_of_harm_or_null_count": sum(joined.count(marker) for marker in absence_markers),
        "direct_benefit_count": sum(joined.count(marker) for marker in direct_benefit_markers),
        "surrogate_benefit_count": sum(joined.count(marker) for marker in surrogate_benefit_markers),
        "support_item_count": len(support_items),
    }

def _default_stance_instruction(support_profile: dict[str, Any], conflict: list[str]) -> str:
    absence_count = int(support_profile.get("absence_of_harm_or_null_count", 0))
    direct_benefit_count = int(support_profile.get("direct_benefit_count", 0))
    if absence_count and direct_benefit_count == 0:
        return (
            "Phrase the default stance as low-concern, neutral, or not-shown-harmful under stated conditions; "
            "do not characterize it as generally beneficial."
        )
    if conflict:
        return (
            "Phrase the default stance with visible uncertainty and name the strongest counterposition; "
            "do not present the answer as settled."
        )
    return "Phrase the default stance no stronger than the direct evidence in supports_default_stance."

def _scope_ledger(items: list[str], *, vocabulary: dict[str, Any] | None = None) -> dict[str, list[str]]:
    ledger = {
        "population_or_actor": [],
        "dose_intensity_or_scale": [],
        "time_horizon": [],
        "geography_jurisdiction_or_setting": [],
        "implementation_context": [],
        "measurement_endpoint": [],
        "source_completeness": [],
        "adversarial_or_incentive_concern": [],
    }
    for item in items:
        for dimension in _scope_dimensions_for_text(item, vocabulary=vocabulary):
            ledger[dimension].append(item)
    return {key: _dedupe(value)[:5] for key, value in ledger.items()}

def _scope_dimensions_for_text(text: str, *, vocabulary: dict[str, Any] | None = None) -> list[str]:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    dimensions: list[str] = []
    marker_map = _vocabulary_marker_map(vocabulary, "scope_dimension_markers")
    for dimension, markers in marker_map.items():
        if any(marker in normalized for marker in markers):
            dimensions.append(dimension)
    return dimensions

def _active_overstatement_lints(
    *,
    support_profile: dict[str, Any],
    conflict: list[str],
    scope_ledger: dict[str, list[str]],
    method_limits: list[str],
    quality_report: dict[str, Any],
) -> list[dict[str, str]]:
    lints = [
        {
            "lint_id": "confidence_language",
            "rule": "Do not use settled-certainty language such as proven, clearly, no risk, or safe unless confidence is high and no counterposition is present.",
        },
        {
            "lint_id": "counterposition_visibility",
            "rule": "If supports_counterposition is non-empty, the final answer must name the strongest counterposition.",
        },
    ]
    if int(support_profile.get("absence_of_harm_or_null_count", 0)) and not int(support_profile.get("direct_benefit_count", 0)):
        lints.append(
            {
                "lint_id": "null_evidence_not_benefit",
                "rule": "Do not translate no-association, no-significant-difference, or no-adverse-effect evidence into a general beneficial claim.",
            }
        )
    if scope_ledger.get("population_or_actor") or scope_ledger.get("dose_intensity_or_scale"):
        lints.append(
            {
                "lint_id": "subgroup_to_generalization",
                "rule": "Do not generalize subgroup, dose, or scale-specific evidence to the whole question without naming the condition.",
            }
        )
    if scope_ledger.get("measurement_endpoint") or _any_text_contains(method_limits, ("biomarker", "surrogate", "endpoint")):
        lints.append(
            {
                "lint_id": "surrogate_to_hard_outcome",
                "rule": "Do not present short-term, biomarker, or surrogate-endpoint evidence as direct long-term outcome evidence.",
            }
        )
    if quality_report.get("status") != "usable_with_review" or any(
        isinstance(issue, dict) and issue.get("severity") in {"fail", "risk"}
        for issue in quality_report.get("issues", [])
    ):
        lints.append(
            {
                "lint_id": "quality_cap",
                "rule": "Do not exceed the confidence cap or hide quality limitations.",
            }
        )
    return lints

def _positive_scope_items(scope_items: list[str]) -> list[str]:
    return [
        item
        for item in scope_items
        if not _looks_like_concern_evidence(item) and not _looks_like_method_or_source_limit(item)
    ]

def _limiting_scope_items(scope_items: list[str]) -> list[str]:
    return [
        item
        for item in scope_items
        if _looks_like_concern_evidence(item) or _looks_like_scope_or_subgroup(item)
    ]

def quality_report_issue_text(quality_report: dict[str, Any]) -> list[str]:
    return [
        f"{issue.get('severity')}: {issue.get('issue_type')} - {issue.get('message')}"
        for issue in quality_report.get("issues", [])
        if isinstance(issue, dict)
    ]

def _any_text_contains(items: list[str], markers: tuple[str, ...]) -> bool:
    joined = " ".join(items).lower()
    return any(marker in joined for marker in markers)

def repair_briefing_payload(
    payload: dict[str, Any],
    scaffold: dict[str, Any],
    source_lookup: dict[str, str],
    candidate_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repaired = dict(payload)
    repaired = _backfill_compact_payload_sections(repaired, scaffold)
    evidence_roles = repaired.get("evidence_roles")
    if not isinstance(evidence_roles, dict):
        evidence_roles = {}
    repaired_roles: dict[str, list[str]] = {}
    scaffold_roles = scaffold.get("evidence_roles", {})
    source_names = set(source_lookup.values())
    for role_key in ("main_support", "conflicting_evidence", "scope_limits", "method_limits"):
        model_items = _string_list(evidence_roles.get(role_key))
        section_synthesis = repaired.get("section_synthesis")
        if isinstance(section_synthesis, dict):
            model_items.extend(_string_list(section_synthesis.get(role_key)))
        substantive = [
            item
            for item in model_items
            if _is_substantive_evidence_statement(item, source_names)
        ]
        if role_key == "main_support":
            substantive = [item for item in substantive if not _looks_like_concern_evidence(item)]
        for scaffold_item in _string_list(scaffold_roles.get(role_key)):
            if _similar_text_exists(substantive, scaffold_item):
                continue
            substantive.append(scaffold_item)
        repaired_roles[role_key] = _dedupe(substantive)[:8]
    repaired_roles = _sanitize_evidence_role_sections(repaired_roles)
    repaired["evidence_roles"] = repaired_roles
    audit = _string_list(repaired.get("audit_trail"))
    for item in _string_list(scaffold.get("audit_trail")):
        if not _similar_text_exists(audit, item):
            audit.append(item)
    repaired["audit_trail"] = _dedupe(audit)[:10]
    if candidate_map is not None:
        repaired = _expand_payload_reader_references(repaired, candidate_map)
    repaired = _apply_briefing_contract_lint(repaired, scaffold)
    repaired = _apply_decision_model_lint(repaired, scaffold)
    repaired = _clean_payload_reader_language(repaired)
    return repaired

def _backfill_compact_payload_sections(payload: dict[str, Any], scaffold: dict[str, Any]) -> dict[str, Any]:
    repaired = dict(payload)
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    sufficiency_report = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    if not _string_list(repaired.get("decision_implications")):
        repaired["decision_implications"] = _dedupe(
            [
                *_deterministic_decision_implications(decision_model),
                *_sufficiency_implications(sufficiency_report),
            ]
        )[:8]
    if not isinstance(repaired.get("top_cruxes"), list) or not repaired.get("top_cruxes"):
        repaired["top_cruxes"] = _deterministic_top_cruxes(scaffold)
    if not _string_list(repaired.get("stress_caveats")):
        repaired["stress_caveats"] = _deterministic_stress_caveats(scaffold)
    return repaired
