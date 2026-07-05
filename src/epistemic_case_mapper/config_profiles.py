from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.prompt_templates import examples_block, json_schema_block, render_prompt, xml_block
from epistemic_case_mapper.config_profile_vocabularies import (
    _biomedical_nutrition_vocabulary,
    _empirical_policy_vocabulary,
    _merged_profile_vocabulary,
    _string_list,
    _technical_safety_vocabulary,
)


DEFAULT_PROFILE_ID = "general_decision_support"


class ClaimRoleConfig(BaseModel):
    role_id: str
    description: str
    use_when: str


class RelationTypeConfig(BaseModel):
    relation_type: str
    description: str
    use_when: str
    sharpness_markers: list[str] = Field(default_factory=list)


class EvidenceSectionConfig(BaseModel):
    section_id: str
    title: str
    description: str
    claim_roles: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)


class SourceRoleConfig(BaseModel):
    role_id: str
    description: str
    keyword_markers: list[str] = Field(default_factory=list)
    provenance_level: str = "unspecified"
    limitations: list[str] = Field(default_factory=list)


class EpistemicConfigProfile(BaseModel):
    profile_id: str
    label: str
    description: str
    best_for: list[str] = Field(default_factory=list)
    claim_roles: list[ClaimRoleConfig]
    relation_types: list[RelationTypeConfig]
    evidence_sections: list[EvidenceSectionConfig]
    source_roles: list[SourceRoleConfig] = Field(default_factory=list)
    relation_prompt_rules: list[str] = Field(default_factory=list)
    vocabulary: dict[str, Any] = Field(default_factory=dict)

    def claim_role_ids(self) -> list[str]:
        return [role.role_id for role in self.claim_roles]

    def relation_type_ids(self) -> list[str]:
        return [relation.relation_type for relation in self.relation_types]


class ConfigRecommendation(BaseModel):
    schema_id: str = "epistemic_config_recommendation/v1"
    profile_id: str
    confidence: str = "low"
    reasons: list[str] = Field(default_factory=list)
    suggested_overrides: dict[str, Any] = Field(default_factory=dict)
    fallback_reason: str | None = None
    backend: str = "prompt"
    prompt_only: bool = False
    raw_profile_id: str | None = None


@dataclass(frozen=True)
class ConfigRecommendationRun:
    recommendation: ConfigRecommendation
    prompt: str
    raw_output: str


def builtin_profiles() -> dict[str, EpistemicConfigProfile]:
    profiles = [
        _general_decision_support(),
        _empirical_policy_decision(),
        _technical_safety_case(),
        _biomedical_nutrition_case(),
        _legal_regulatory_case(),
    ]
    return {profile.profile_id: profile for profile in profiles}


def default_profile() -> EpistemicConfigProfile:
    return builtin_profiles()[DEFAULT_PROFILE_ID]


def profile_for_id(profile_id: str | None) -> EpistemicConfigProfile:
    profiles = builtin_profiles()
    return profiles.get(str(profile_id or "").strip(), profiles[DEFAULT_PROFILE_ID])


def profile_vocabulary(profile_id: str | None) -> dict[str, Any]:
    profile = profile_for_id(profile_id)
    return _merged_profile_vocabulary(profile.vocabulary)


def infer_profile_id_from_text(text: str, *, fallback_profile_id: str | None = None) -> str:
    normalized = str(text or "").lower()
    fallback = str(fallback_profile_id or DEFAULT_PROFILE_ID)
    best_profile = fallback if fallback in builtin_profiles() else DEFAULT_PROFILE_ID
    best_score = 0
    for profile_id, profile in builtin_profiles().items():
        markers = _string_list(profile.vocabulary.get("profile_detection_markers"))
        if not markers:
            continue
        score = sum(1 for marker in markers if marker.lower() in normalized)
        threshold = int(profile.vocabulary.get("profile_detection_threshold", 2))
        if score >= threshold and score > best_score:
            best_profile = profile_id
            best_score = score
    return best_profile








def config_profile_from_manifest_payload(payload: dict[str, Any] | None) -> EpistemicConfigProfile:
    if not isinstance(payload, dict):
        return default_profile()
    return profile_for_id(str(payload.get("profile_id", "")))


def profile_manifest_payload(
    profile: EpistemicConfigProfile,
    recommendation: ConfigRecommendation | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "profile_id": profile.profile_id,
        "label": profile.label,
        "description": profile.description,
        "claim_roles": profile.claim_role_ids(),
        "relation_types": profile.relation_type_ids(),
        "source": "builtin_profile",
    }
    if recommendation is not None:
        payload["source"] = "model_recommendation"
        payload["confidence"] = recommendation.confidence
        payload["reasons"] = recommendation.reasons
        if recommendation.suggested_overrides:
            payload["suggested_overrides"] = recommendation.suggested_overrides
        if recommendation.fallback_reason:
            payload["fallback_reason"] = recommendation.fallback_reason
    return payload


def source_summaries_from_docs(doc_paths: list[Path], max_chars: int = 1600) -> list[dict[str, str]]:
    summaries: list[dict[str, str]] = []
    for doc_path in doc_paths:
        path = doc_path.expanduser().resolve()
        text = path.read_text(encoding="utf-8", errors="replace")
        excerpt = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        summaries.append(
            {
                "path": path.as_posix(),
                "title": path.stem.replace("_", " ").replace("-", " ").strip() or path.name,
                "excerpt": excerpt[:max_chars],
            }
        )
    return summaries


def build_config_recommendation_prompt(
    *,
    question: str,
    source_summaries: list[dict[str, str]],
    profiles: dict[str, EpistemicConfigProfile] | None = None,
) -> str:
    profile_payloads = [
        {
            "profile_id": profile.profile_id,
            "label": profile.label,
            "description": profile.description,
            "best_for": profile.best_for,
            "claim_roles": [
                {"role_id": role.role_id, "description": role.description, "use_when": role.use_when}
                for role in profile.claim_roles
            ],
            "relation_types": [
                {
                    "relation_type": relation.relation_type,
                    "description": relation.description,
                    "use_when": relation.use_when,
                }
                for relation in profile.relation_types
            ],
        }
        for profile in (profiles or builtin_profiles()).values()
    ]
    return render_prompt(
        ("Task", "You are selecting an epistemic mapping configuration for a new document packet."),
        (
            "Rules",
            [
                "- Choose the built-in profile that best fits the decision question and source mix.",
                "- Prefer the most general adequate profile over a narrow one.",
                "- profile_id must be one of the available profile IDs.",
                "- Do not invent a new full schema; put lightweight additions under suggested_overrides.",
                "- Name uncertainties when the source packet is too thin to justify a specialized profile.",
            ],
        ),
        ("Output Schema", json_schema_block(_config_recommendation_schema())),
        ("Examples", examples_block(_config_recommendation_examples())),
        (
            "Context",
            "\n\n".join(
                (
                    f"Decision question:\n{question}",
                    xml_block("document_packet_summaries", json.dumps(source_summaries, indent=2)),
                    xml_block("available_profiles", json.dumps(profile_payloads, indent=2)),
                )
            ),
        ),
    )


def recommend_config_profile(
    *,
    question: str,
    doc_paths: list[Path],
    backend: str,
    timeout_seconds: int | None = 60,
    max_retries: int = 0,
) -> ConfigRecommendationRun:
    source_summaries = source_summaries_from_docs(doc_paths)
    prompt = build_config_recommendation_prompt(question=question, source_summaries=source_summaries)
    result = run_model_backend(
        prompt,
        backend,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        response_schema=_config_recommendation_json_schema(),
    )
    raw_output = result.text
    recommendation = _parse_recommendation(raw_output, backend=result.backend, prompt_only=result.prompt_only)
    return ConfigRecommendationRun(recommendation=recommendation, prompt=prompt, raw_output=raw_output)


def render_config_recommendation_markdown(
    recommendation: ConfigRecommendation,
    profile: EpistemicConfigProfile | None = None,
) -> str:
    selected = profile or profile_for_id(recommendation.profile_id)
    reasons = recommendation.reasons or ["No model reason supplied."]
    lines = [
        "# Config Recommendation",
        "",
        f"Selected profile: `{selected.profile_id}` ({selected.label})",
        f"Confidence: `{recommendation.confidence}`",
    ]
    if recommendation.fallback_reason:
        lines.append(f"Fallback: `{recommendation.fallback_reason}`")
    lines.extend(["", "## Why", ""])
    lines.extend(f"- {reason}" for reason in reasons)
    lines.extend(["", "## Claim Roles", ""])
    lines.extend(f"- `{role.role_id}`: {role.description}" for role in selected.claim_roles)
    lines.extend(["", "## Relation Types", ""])
    lines.extend(f"- `{relation.relation_type}`: {relation.description}" for relation in selected.relation_types)
    if recommendation.suggested_overrides:
        lines.extend(["", "## Suggested Overrides", "", "```json", json.dumps(recommendation.suggested_overrides, indent=2), "```"])
    lines.append("")
    return "\n".join(lines)


def _parse_recommendation(raw_output: str, backend: str, prompt_only: bool) -> ConfigRecommendation:
    profiles = builtin_profiles()
    payload: dict[str, Any] = {}
    fallback_reason: str | None = None
    if prompt_only:
        fallback_reason = "prompt_backend_did_not_select_profile"
    else:
        try:
            parsed = json.loads(canonical_json_output(raw_output))
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            payload = parsed
        else:
            fallback_reason = "invalid_recommendation_json"
    raw_profile_id = str(payload.get("profile_id", "")).strip() if payload else None
    profile_id = raw_profile_id or DEFAULT_PROFILE_ID
    if profile_id not in profiles:
        fallback_reason = f"unknown_profile_id:{profile_id}"
        profile_id = DEFAULT_PROFILE_ID
    confidence = str(payload.get("confidence", "low")).strip().lower() if payload else "low"
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"
    reasons = payload.get("reasons", []) if payload else []
    if isinstance(reasons, str):
        reasons = [reasons]
    if not isinstance(reasons, list):
        reasons = []
    overrides = payload.get("suggested_overrides", {}) if payload else {}
    if not isinstance(overrides, dict):
        overrides = {}
    return ConfigRecommendation(
        profile_id=profile_id,
        confidence=confidence,
        reasons=[str(reason).strip() for reason in reasons if str(reason).strip()],
        suggested_overrides=overrides,
        fallback_reason=fallback_reason,
        backend=backend,
        prompt_only=prompt_only,
        raw_profile_id=raw_profile_id,
    )


def _config_recommendation_schema() -> dict[str, Any]:
    return {
        "profile_id": DEFAULT_PROFILE_ID,
        "confidence": "low|medium|high",
        "reasons": ["why this profile fits the question and documents"],
        "suggested_overrides": {
            "claim_roles": ["optional additional or renamed roles"],
            "relation_types": ["optional additional relation types"],
            "evidence_sections": ["optional briefing/map sections"],
            "source_roles": ["optional source-role hints"],
        },
    }


def _config_recommendation_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "profile_id": {"type": "string"},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "reasons": {"type": "array", "items": {"type": "string"}},
            "suggested_overrides": {"type": "object"},
        },
        "required": ["profile_id", "confidence", "reasons"],
    }


def _config_recommendation_examples() -> list[dict[str, Any]]:
    return [
        {
            "input_hint": "Generic decision question with mixed source summaries.",
            "output": {
                "profile_id": "general_decision_support",
                "confidence": "medium",
                "reasons": ["The packet mixes decision-relevant claims without a specialized domain signal."],
                "suggested_overrides": {},
            },
        },
        {
            "input_hint": "Documents emphasize hazards, mitigations, failure modes, and residual risk.",
            "output": {
                "profile_id": "technical_safety_case",
                "confidence": "high",
                "reasons": ["The source mix is organized around failure modes and mitigations."],
                "suggested_overrides": {"claim_roles": ["monitoring_gap"]},
            },
        },
    ]


def _base_relations() -> list[RelationTypeConfig]:
    return [
        RelationTypeConfig(
            relation_type="supports",
            description="One claim increases support for another without being the decisive dependency.",
            use_when="Use for direct evidence or argument support.",
            sharpness_markers=["supports", "consistent with", "evidence for"],
        ),
        RelationTypeConfig(
            relation_type="challenges",
            description="One claim undercuts or contradicts another.",
            use_when="Use for contrary evidence, validity objections, or failed assumptions.",
            sharpness_markers=["contradicts", "undercuts", "casts doubt"],
        ),
        RelationTypeConfig(
            relation_type="refines",
            description="One claim narrows the population, endpoint, mechanism, condition, or interpretation of another.",
            use_when="Use when the boundary being refined is explicit.",
            sharpness_markers=["only for", "specifically", "boundary", "population", "endpoint"],
        ),
        RelationTypeConfig(
            relation_type="similar_to",
            description="Claims are close enough that a reviewer may consider merging them.",
            use_when="Use only for near-duplicate or strongly overlapping claims.",
            sharpness_markers=["same as", "duplicates", "substantially overlaps"],
        ),
        RelationTypeConfig(
            relation_type="depends_on",
            description="The force of one claim depends on a condition, implementation detail, or prerequisite.",
            use_when="Use for conditional recommendations, feasibility dependencies, and assumptions.",
            sharpness_markers=["depends", "requires", "only if", "unless", "condition"],
        ),
        RelationTypeConfig(
            relation_type="crux_for",
            description="One claim is a decision crux for another or for the question.",
            use_when="Use when changing belief in one claim would materially change the decision read.",
            sharpness_markers=["crux", "decisive", "would change", "key uncertainty"],
        ),
        RelationTypeConfig(
            relation_type="in_tension_with",
            description="Claims can both be partly true but pull the decision in different directions.",
            use_when="Use for tradeoffs, external-validity limits, and evidence-vs-implementation tensions.",
            sharpness_markers=["however", "tradeoff", "tension", "limited", "unclear"],
        ),
    ]


def _general_roles() -> list[ClaimRoleConfig]:
    return [
        ClaimRoleConfig(role_id="conclusion_support", description="Evidence or reasoning that supports a candidate answer.", use_when="A claim bears directly on the likely answer."),
        ClaimRoleConfig(role_id="crux", description="A claim whose truth would materially change the answer.", use_when="The decision turns on this uncertainty."),
        ClaimRoleConfig(role_id="scope_limit", description="A boundary on where a claim applies.", use_when="Population, context, timing, or evidence limits matter."),
        ClaimRoleConfig(role_id="implementation_constraint", description="A practical condition for applying a recommendation.", use_when="Feasibility, compliance, cost, operations, or rollout matters."),
        ClaimRoleConfig(role_id="background", description="Context needed to interpret the evidence.", use_when="Useful context that is not itself load-bearing."),
        ClaimRoleConfig(role_id="other", description="A useful claim that does not fit the other roles.", use_when="Use sparingly when no sharper role fits."),
    ]


def _general_decision_support() -> EpistemicConfigProfile:
    return EpistemicConfigProfile(
        profile_id=DEFAULT_PROFILE_ID,
        label="General Decision Support",
        description="A broad profile for mixed evidence packets and decision-relevant synthesis.",
        best_for=["mixed document packets", "contested but non-specialized decisions", "early exploration"],
        claim_roles=_general_roles(),
        relation_types=_base_relations(),
        evidence_sections=[
            EvidenceSectionConfig(section_id="answer_drivers", title="Answer Drivers", description="Load-bearing evidence and cruxes.", claim_roles=["conclusion_support", "crux"], relation_types=["supports", "crux_for"]),
            EvidenceSectionConfig(section_id="bounds_and_tensions", title="Bounds and Tensions", description="Limits, disagreements, and dependencies.", claim_roles=["scope_limit", "implementation_constraint"], relation_types=["depends_on", "in_tension_with", "challenges"]),
        ],
        source_roles=[
            SourceRoleConfig(role_id="source_document", description="Provided source whose role is not yet known.", keyword_markers=[], limitations=["Source role may need review."]),
        ],
        relation_prompt_rules=[
            "Prefer crux_for, depends_on, in_tension_with, or challenges when those sharper relations fit.",
            "Use similar_to only when the claims are redundant enough to merge.",
        ],
    )


def _empirical_policy_decision() -> EpistemicConfigProfile:
    roles = _general_roles() + [
        ClaimRoleConfig(role_id="measurement_validity", description="A claim about whether measured outcomes represent the construct of interest.", use_when="Outcome choice, proxy quality, or measurement error matters."),
        ClaimRoleConfig(role_id="external_validity", description="A claim about whether evidence transfers across populations, settings, or time.", use_when="Generalizing from studies or pilots is uncertain."),
        ClaimRoleConfig(role_id="cost_feasibility", description="A claim about resource needs, cost, or operational feasibility.", use_when="Adoption depends on budget or implementation capacity."),
    ]
    return EpistemicConfigProfile(
        profile_id="empirical_policy_decision",
        label="Empirical Policy Decision",
        description="For policy questions grounded in studies, guidelines, evaluations, and implementation evidence.",
        best_for=["RCTs and observational studies", "guidelines", "public policy", "program evaluation"],
        claim_roles=roles,
        relation_types=_base_relations(),
        evidence_sections=[
            EvidenceSectionConfig(section_id="effect_evidence", title="Effect Evidence", description="Evidence about effect size and direction.", claim_roles=["conclusion_support", "measurement_validity"], relation_types=["supports", "challenges"]),
            EvidenceSectionConfig(section_id="transfer_limits", title="Transfer Limits", description="External-validity and implementation limits.", claim_roles=["external_validity", "implementation_constraint", "cost_feasibility"], relation_types=["refines", "depends_on", "in_tension_with"]),
        ],
        source_roles=[
            SourceRoleConfig(role_id="empirical_study", description="Study or trial evidence.", keyword_markers=["trial", "study", "cohort", "rct"], provenance_level="peer_reviewed", limitations=["Check design, population, endpoint, and confounding."]),
            SourceRoleConfig(role_id="policy_guidance", description="Official recommendation or guidance.", keyword_markers=["guideline", "recommendation", "advisory"], provenance_level="official_guidance", limitations=["May combine evidence with policy judgment."]),
        ],
        relation_prompt_rules=[
            "Look for measurement-validity and external-validity claims before treating effect evidence as decisive.",
            "Represent implementation and cost conditions as depends_on or in_tension_with edges.",
        ],
        vocabulary=_empirical_policy_vocabulary(),
    )




def _technical_safety_case() -> EpistemicConfigProfile:
    roles = _general_roles() + [
        ClaimRoleConfig(role_id="failure_mode", description="A claim about how a system can fail.", use_when="The document names hazards, incidents, attack paths, or reliability failures."),
        ClaimRoleConfig(role_id="mitigation", description="A claim about a control that reduces risk.", use_when="A proposed design, policy, or process reduces a failure mode."),
        ClaimRoleConfig(role_id="residual_risk", description="A claim about risk remaining after controls.", use_when="A mitigation is incomplete or uncertain."),
        ClaimRoleConfig(role_id="operational_constraint", description="A claim about operating conditions or monitoring needs.", use_when="Safety depends on procedures, staffing, observability, or maintenance."),
    ]
    return EpistemicConfigProfile(
        profile_id="technical_safety_case",
        label="Technical Safety Case",
        description="For engineering, security, AI safety, infrastructure, and reliability decisions.",
        best_for=["safety cases", "engineering systems", "risk controls", "failure analysis"],
        claim_roles=roles,
        relation_types=_base_relations(),
        evidence_sections=[
            EvidenceSectionConfig(section_id="hazards", title="Hazards", description="Failure modes and consequences.", claim_roles=["failure_mode", "residual_risk"], relation_types=["challenges", "in_tension_with"]),
            EvidenceSectionConfig(section_id="controls", title="Controls", description="Mitigations, dependencies, and monitoring conditions.", claim_roles=["mitigation", "operational_constraint"], relation_types=["supports", "depends_on", "refines"]),
        ],
        source_roles=[
            SourceRoleConfig(role_id="incident_report", description="Report about a failure or near miss.", keyword_markers=["incident", "postmortem", "failure"], limitations=["May be incomplete or organization-specific."]),
            SourceRoleConfig(role_id="technical_specification", description="Specification, design doc, or standard.", keyword_markers=["specification", "standard", "architecture"], limitations=["Specs may be out of date relative to operations."]),
        ],
        relation_prompt_rules=[
            "Map mitigations to the failure modes they address and residual risks they leave.",
            "Use depends_on for controls that only work under operational assumptions.",
        ],
        vocabulary=_technical_safety_vocabulary(),
    )




def _biomedical_nutrition_case() -> EpistemicConfigProfile:
    roles = _general_roles() + [
        ClaimRoleConfig(role_id="population_or_subgroup", description="A claim about who the evidence applies to.", use_when="Baseline health, subgroup risk, or generalizability matters."),
        ClaimRoleConfig(role_id="dose_or_exposure", description="A claim about intake, exposure level, or threshold.", use_when="The recommendation changes by dose or intensity."),
        ClaimRoleConfig(role_id="endpoint_or_biomarker", description="A claim about direct outcomes, biomarkers, or mechanisms.", use_when="Outcome type controls evidential weight."),
        ClaimRoleConfig(role_id="substitution_context", description="A claim about replacement foods, comparators, or dietary pattern context.", use_when="The practical advice changes with the comparator."),
    ]
    return EpistemicConfigProfile(
        profile_id="biomedical_nutrition_case",
        label="Biomedical or Nutrition Evidence Case",
        description="For health and nutrition questions where population, dose, endpoint type, biomarkers, substitution, and guideline context matter.",
        best_for=["nutrition evidence", "biomedical guideline questions", "dietary exposure decisions"],
        claim_roles=roles,
        relation_types=_base_relations(),
        evidence_sections=[
            EvidenceSectionConfig(section_id="outcomes", title="Outcomes and Endpoints", description="Direct outcomes, surrogate endpoints, and endpoint boundaries.", claim_roles=["conclusion_support", "endpoint_or_biomarker"], relation_types=["supports", "challenges", "refines"]),
            EvidenceSectionConfig(section_id="scope_and_context", title="Scope and Context", description="Population, dose, subgroup, substitution, and guideline context.", claim_roles=["population_or_subgroup", "dose_or_exposure", "substitution_context", "scope_limit"], relation_types=["depends_on", "refines", "in_tension_with"]),
        ],
        source_roles=[
            SourceRoleConfig(role_id="cohort_or_observational_study", description="Observational health-outcome evidence.", keyword_markers=["cohort", "prospective", "observational"], limitations=["Check confounding, population, dose, and endpoint definitions."]),
            SourceRoleConfig(role_id="intervention_or_marker_trial", description="Trial or intervention evidence, often with biomarkers or surrogate endpoints.", keyword_markers=["trial", "randomized", "rct", "biomarker"], limitations=["Check whether markers answer the decision endpoint."]),
            SourceRoleConfig(role_id="guideline_or_review", description="Guideline, advisory, or evidence review.", keyword_markers=["guideline", "recommendation", "review"], limitations=["Guidance may mix evidence with policy judgment."]),
        ],
        relation_prompt_rules=[
            "Do not collapse direct health outcomes, biomarkers, mechanisms, and guideline advice into one evidence type.",
            "Represent dose, population, and substitution context as explicit scope or depends_on relations.",
        ],
        vocabulary=_biomedical_nutrition_vocabulary(),
    )






def _legal_regulatory_case() -> EpistemicConfigProfile:
    roles = _general_roles() + [
        ClaimRoleConfig(role_id="jurisdictional_constraint", description="A claim about where a rule or precedent applies.", use_when="Jurisdiction, authority, or scope determines relevance."),
        ClaimRoleConfig(role_id="statutory_authority", description="A claim grounded in statute, regulation, or formal rule.", use_when="Legal authority is load-bearing."),
        ClaimRoleConfig(role_id="precedent", description="A claim about prior cases, enforcement, or interpretive history.", use_when="Past decisions shape the current answer."),
        ClaimRoleConfig(role_id="compliance_burden", description="A claim about cost, operational burden, or enforcement practicality.", use_when="Decision quality depends on compliance impact."),
    ]
    return EpistemicConfigProfile(
        profile_id="legal_regulatory_case",
        label="Legal or Regulatory Case",
        description="For questions dominated by statutes, rules, authority, compliance, and jurisdiction.",
        best_for=["regulatory compliance", "legal analysis", "agency guidance", "jurisdiction-specific questions"],
        claim_roles=roles,
        relation_types=_base_relations(),
        evidence_sections=[
            EvidenceSectionConfig(section_id="authority", title="Authority", description="Statutes, rules, precedents, and official interpretations.", claim_roles=["statutory_authority", "precedent", "jurisdictional_constraint"], relation_types=["supports", "refines", "challenges"]),
            EvidenceSectionConfig(section_id="application", title="Application", description="Practical compliance consequences and uncertainties.", claim_roles=["compliance_burden", "implementation_constraint"], relation_types=["depends_on", "in_tension_with"]),
        ],
        source_roles=[
            SourceRoleConfig(role_id="formal_rule", description="Statute, regulation, or official rule text.", keyword_markers=["statute", "regulation", "rule", "code"], provenance_level="official_guidance", limitations=["Rule text may require jurisdiction-specific interpretation."]),
            SourceRoleConfig(role_id="guidance_or_commentary", description="Agency guidance or legal commentary.", keyword_markers=["guidance", "commentary", "analysis"], limitations=["May not be binding authority."]),
        ],
        relation_prompt_rules=[
            "Do not treat commentary as equivalent to statutory authority.",
            "Use refines for jurisdictional or scope boundaries and depends_on for compliance conditions.",
        ],
    )
