from __future__ import annotations

from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import dedupe as _dedupe


def declared_document_type(source_type: str) -> str:
    normalized = source_type.lower().replace("-", "_").replace(" ", "_")
    if any(term in normalized for term in ("guideline", "guidance", "advisory")):
        return "guidance_or_advisory"
    if any(term in normalized for term in ("systematic_review", "meta_analysis", "scoping_review", "narrative_review", "evidence_mapping", "overview", "review")):
        return "evidence_synthesis"
    if any(term in normalized for term in ("randomized", "randomised", "trial")):
        return "intervention_study"
    if any(term in normalized for term in ("cohort", "case_control", "cross_sectional", "observational", "empirical")):
        return "observational_study"
    if any(term in normalized for term in ("news", "explanation", "summary", "commentary", "opinion", "editorial")):
        return "contextual_summary"
    if any(term in normalized for term in ("regulatory", "legal")):
        return "legal_or_regulatory"
    if any(term in normalized for term in ("dataset", "record")):
        return "dataset_or_record"
    return "mixed_or_unknown"


def document_type(text: str) -> str:
    if any(term in text for term in ("systematic review", "meta-analysis", "meta analysis", "scoping review", "review")):
        return "evidence_synthesis"
    if any(term in text for term in ("randomized", "randomised", "randomized controlled", "randomised controlled", "trial", " rct ")):
        return "intervention_study"
    if any(term in text for term in ("cohort", "case-control", "case control", "cross-sectional", "observational")):
        return "observational_study"
    if any(term in text for term in ("guideline", "guidance", "recommendation", "advisory")):
        return "guidance_or_advisory"
    if any(term in text for term in ("news", "explainer", "commentary", "opinion", "editorial")):
        return "contextual_summary"
    return "mixed_or_unknown"


def document_flags(document_type_value: str, endpoint_kind_value: str, evidence_text: str) -> list[str]:
    flags = []
    if document_type_value == "observational_study":
        flags.append("association_not_causation")
    if document_type_value == "intervention_study" and endpoint_kind_value in {"surrogate", "proxy"}:
        flags.append("indirect_endpoint")
    if document_type_value == "guidance_or_advisory":
        flags.append("guidance_not_independent_empirical_evidence")
    if document_type_value == "contextual_summary":
        flags.append("context_not_primary_evidence")
    if document_type_value == "evidence_synthesis":
        flags.append("synthesis_depends_on_included_sources")
    if any(term in evidence_text for term in ("subgroup", "population", "applicability", "scope")):
        flags.append("scope_sensitive")
    return flags


def endpoint_kind(endpoint_text: str) -> str:
    if any(term in endpoint_text for term in ("surrogate", "biomarker", "intermediate", "proxy", "marker", "concentration")):
        return "surrogate"
    if any(term in endpoint_text for term in ("process", "implementation", "feasibility")):
        return "proxy"
    if endpoint_text.strip():
        return "direct_or_unspecified"
    return "unknown"


def evidence_proximity(document_type_value: str) -> str:
    return {
        "observational_study": "primary",
        "intervention_study": "primary",
        "evidence_synthesis": "synthesis",
        "guidance_or_advisory": "guidance",
        "contextual_summary": "summary",
    }.get(document_type_value, "unknown")


def recommended_use(flags: set[str], directness: str) -> str:
    if "source_needs_upgrade" in flags or "provenance_not_decision_grade" in flags:
        return "human_review_needed"
    if "context_not_primary_evidence" in flags:
        return "background_or_context"
    if "guidance_not_independent_empirical_evidence" in flags:
        return "decision_context_or_corroboration"
    if "secondary_or_scoping_review" in flags:
        return "corroborate_or_bound"
    if "anchor_limit" in flags or directness == "indirect":
        return "corroborate_or_bound"
    if "association_not_causation" in flags or "indirect_endpoint" in flags or "independence_not_established" in flags:
        return "load_bearing_with_qualification"
    return "load_bearing_ok"


def more_restrictive_use(base: str, model: str) -> str:
    if not model:
        return base
    rank = {
        "load_bearing_ok": 0,
        "load_bearing_with_qualification": 1,
        "corroborate_or_bound": 2,
        "decision_context_or_corroboration": 2,
        "background_or_context": 3,
        "human_review_needed": 4,
    }
    return model if rank.get(model, 4) > rank.get(base, 4) else base


def claim_use_context(recommended_use_value: str) -> str:
    return {
        "load_bearing_ok": "can_support_load_bearing_claims",
        "load_bearing_with_qualification": "can_support_claims_with_explicit_limits",
        "corroborate_or_bound": "use_to_bound_or_corroborate",
        "decision_context_or_corroboration": "use_for_decision_context_or_guidance",
        "background_or_context": "use_for_context_not_primary_support",
    }.get(recommended_use_value, "human_review_if_load_bearing")


def interpretation_caveats(flags: set[str]) -> list[str]:
    caveats = {
        "association_not_causation": "Use association language unless another source supports causal interpretation.",
        "indirect_endpoint": "Treat endpoint evidence as indirect for final decision outcomes.",
        "guidance_not_independent_empirical_evidence": "Use guidance as decision context, not independent empirical confirmation.",
        "context_not_primary_evidence": "Use summary or explainer material for context rather than load-bearing evidence.",
        "synthesis_depends_on_included_sources": "Treat synthesis and included-source evidence as related until an independence check supports independence.",
        "scope_sensitive": "Use this evidence to bound scope or applicability when it concerns narrower populations, settings, or endpoints.",
        "anchor_limit": "Source anchoring is incomplete for at least one card from this source.",
        "explicit_limitations": "Carry explicit source limitations into memo wording when this source is load-bearing.",
        "quality_limit": "Avoid overconfident wording because at least one card has weak, indirect, or unknown quality status.",
        "missing_appraisal": "Source-use appraisal is missing; avoid making the source uniquely load-bearing.",
        "independence_not_established": "Treat this source as correlated with its declared cluster unless an independence check shows otherwise.",
        "provenance_not_decision_grade": "Do not use this source as decision-grade evidence until its provenance is upgraded.",
        "source_needs_upgrade": "The manifest explicitly marks this source as needing upgrade before load-bearing use.",
        "secondary_or_scoping_review": "Use this review to bound or corroborate the evidence rather than as independent primary support.",
    }
    return [caveats[flag] for flag in sorted(flags) if flag in caveats]


def source_use_warnings(flags: set[str], recommended_use_value: str) -> list[str]:
    warnings = sorted(flag for flag in flags if flag in {
        "association_not_causation",
        "indirect_endpoint",
        "guidance_not_independent_empirical_evidence",
        "context_not_primary_evidence",
        "anchor_limit",
        "quality_limit",
        "missing_appraisal",
        "independence_not_established",
        "provenance_not_decision_grade",
        "source_needs_upgrade",
        "secondary_or_scoping_review",
    })
    if recommended_use_value not in {"load_bearing_ok", "load_bearing_with_qualification"}:
        warnings.append(f"recommended_use_{recommended_use_value}")
    return _dedupe(warnings)


def allowed_wording_from_flags(flags: set[str]) -> dict[str, Any]:
    verbs = ["supports", "is consistent with", "suggests"]
    avoid = ["proves", "establishes certainty"]
    qualifiers = []
    if "association_not_causation" in flags:
        verbs = ["is associated with", "is consistent with", "does not clearly show"]
        avoid.extend(["causes", "prevents"])
        qualifiers.append("observational evidence")
    if "indirect_endpoint" in flags:
        verbs = ["indicates", "is consistent with", "raises or lowers concern about"]
        avoid.extend(["shows final-outcome benefit", "shows final-outcome harm"])
        qualifiers.append("indirect endpoint evidence")
    if "guidance_not_independent_empirical_evidence" in flags or "context_not_primary_evidence" in flags:
        verbs = ["frames", "contextualizes", "recommends"]
        avoid.extend(["independently demonstrates", "empirically proves"])
        qualifiers.append("contextual source")
    if "quality_limit" in flags:
        qualifiers.append("source-use limitation")
    if "missing_appraisal" in flags:
        qualifiers.append("source-use appraisal missing")
    if "independence_not_established" in flags:
        avoid.extend(["independently confirms", "adds independent confirmation"])
        qualifiers.append("potentially correlated evidence")
    if "provenance_not_decision_grade" in flags or "source_needs_upgrade" in flags:
        avoid.extend(["decision-grade evidence", "establishes the decision"])
        qualifiers.append("provenance requires review")
    if "secondary_or_scoping_review" in flags:
        avoid.append("independent primary evidence")
        qualifiers.append("secondary synthesis")
    return {
        "preferred_verbs": _dedupe(verbs),
        "avoid_terms": _dedupe(avoid),
        "must_qualify_with": _dedupe(qualifiers),
        "causal_language_allowed": "association_not_causation" not in flags and "indirect_endpoint" not in flags,
    }
