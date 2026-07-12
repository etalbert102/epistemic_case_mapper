from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from epistemic_case_mapper.map_briefing_decision_packet import packet_summary_for_model
from epistemic_case_mapper.map_briefing_decision_packet_progress import critique_progress_details, packet_counts, packet_progress, refinement_progress_details
from epistemic_case_mapper.map_briefing_packet_critique_issues import dedupe_issue_rows, normalized_critique_issues
from epistemic_case_mapper.map_briefing_packet_parallel_critique import run_parallel_packet_critique, should_use_parallel_packet_critique
from epistemic_case_mapper.map_briefing_omission_priority import preserve_omissions_with_recomputed_quantities
from epistemic_case_mapper.map_briefing_packet_quality_repair import repair_packet_for_synthesis
from epistemic_case_mapper.map_briefing_packet_sufficiency import build_packet_sufficiency_report
from epistemic_case_mapper.map_briefing_packet_targeted_refinement import run_targeted_packet_refinement
from epistemic_case_mapper.map_briefing_writer_guidance import attach_writer_guidance, build_writer_guidance_packet
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.model_schemas import parse_model_output_report


PacketJudgment = Literal["ready", "needs_repair", "not_sufficient"]
PacketEditType = Literal["promote", "demote", "split", "merge", "relabel", "add_warning", "insufficiency_warning"]


def _blank_if_none(value: Any) -> Any:
    return "" if value is None else value


def _note_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("description", "risk", "issue", "critique", "comment", "warning", "recommended_action"):
            text = str(value.get(key, "")).strip()
            if text:
                return text
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value).strip()


class _FlexibleCritiqueModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class PacketFrameRisk(_FlexibleCritiqueModel):
    risk: str = ""
    affected_bundle_ids: list[str] = Field(default_factory=list, max_length=12)
    why_it_matters: str = ""
    recommended_action: str = ""


class MissingDecisionFunction(_FlexibleCritiqueModel):
    decision_function: str = ""
    evidence_ids_that_suggest_gap: list[str] = Field(default_factory=list, max_length=12)
    recommended_action: str = ""


class MisassignedRole(_FlexibleCritiqueModel):
    bundle_id: str = ""
    current_role: str = ""
    recommended_role: str = ""
    rationale: str = ""

    @field_validator("bundle_id", "current_role", "recommended_role", "rationale", mode="before")
    @classmethod
    def coerce_nullable_text(cls, value: Any) -> Any:
        return _blank_if_none(value)


class RecommendedPacketEdit(_FlexibleCritiqueModel):
    edit_type: PacketEditType
    target_ids: list[str] = Field(default_factory=list, max_length=12)
    target_id: str = ""
    bundle_id: str = ""
    source_id: str = ""
    rationale: str = ""
    description: str = ""
    reason: str = ""
    recommended_role: str = ""
    recommended_weight: str = ""
    warning: str = ""

    @field_validator("target_id", "bundle_id", "source_id", "rationale", "description", "reason", "recommended_role", "recommended_weight", "warning", mode="before")
    @classmethod
    def coerce_nullable_text(cls, value: Any) -> Any:
        return _blank_if_none(value)


class BundleRoleCheck(_FlexibleCritiqueModel):
    bundle_id: str = ""
    current_role: str = ""
    directionality: str = ""
    role_matches_claim_and_direction: bool = True
    recommended_role: str = ""
    rationale: str = ""
    problem: str = ""

    @field_validator("bundle_id", "current_role", "directionality", "recommended_role", "rationale", "problem", mode="before")
    @classmethod
    def coerce_nullable_text(cls, value: Any) -> Any:
        return _blank_if_none(value)


class SynthesisRisk(_FlexibleCritiqueModel):
    type: str = ""
    risk_type: str = ""
    risk: str = ""
    description: str = ""
    impact_level: str = ""
    affected_bundle_ids: list[str] = Field(default_factory=list, max_length=12)
    affected_sections: list[str] = Field(default_factory=list, max_length=8)
    why_it_matters: str = ""
    recommended_action: str = ""

    @field_validator("type", "risk_type", "risk", "description", "impact_level", "why_it_matters", "recommended_action", mode="before")
    @classmethod
    def coerce_nullable_text(cls, value: Any) -> Any:
        return _blank_if_none(value)

    @model_validator(mode="after")
    def normalize_synonyms(self) -> "SynthesisRisk":
        if not self.type and self.risk_type:
            self.type = self.risk_type
        if not self.risk and self.description:
            self.risk = self.description
        return self


class PacketInsufficiencyWarning(_FlexibleCritiqueModel):
    type: str = ""
    bundle_id: str = ""
    source_id: str = ""
    reason: str = ""
    description: str = ""
    warning: str = ""
    recommended_action: str = ""

    @field_validator("type", "bundle_id", "source_id", "reason", "description", "warning", "recommended_action", mode="before")
    @classmethod
    def coerce_nullable_text(cls, value: Any) -> Any:
        return _blank_if_none(value)

    @model_validator(mode="after")
    def normalize_description(self) -> "PacketInsufficiencyWarning":
        if not self.reason and self.description:
            self.reason = self.description
        if not self.warning and self.description:
            self.warning = self.description
        return self


class ClaimQualityIssue(_FlexibleCritiqueModel):
    bundle_id: str = ""
    claim: str = ""
    issue: str = ""
    description: str = ""
    why_it_matters: str = ""
    recommended_action: str = ""

    @field_validator("bundle_id", "claim", "issue", "description", "why_it_matters", "recommended_action", mode="before")
    @classmethod
    def coerce_nullable_text(cls, value: Any) -> Any:
        return _blank_if_none(value)

    @model_validator(mode="after")
    def normalize_description(self) -> "ClaimQualityIssue":
        if not self.issue and self.description:
            self.issue = self.description
        return self


class SectionRoutingIssue(_FlexibleCritiqueModel):
    bundle_id: str = ""
    section: str = ""
    current_bucket: str = ""
    issue: str = ""
    description: str = ""
    recommended_action: str = ""

    @field_validator("bundle_id", "section", "current_bucket", "issue", "description", "recommended_action", mode="before")
    @classmethod
    def coerce_nullable_text(cls, value: Any) -> Any:
        return _blank_if_none(value)

    @model_validator(mode="after")
    def normalize_description(self) -> "SectionRoutingIssue":
        if not self.issue and self.description:
            self.issue = self.description
        return self


class AnswerFrameIssue(_FlexibleCritiqueModel):
    component: str = ""
    critique: str = ""
    risk: str = ""
    why_it_matters: str = ""
    recommended_action: str = ""

    @field_validator("component", "critique", "risk", "why_it_matters", "recommended_action", mode="before")
    @classmethod
    def coerce_nullable_text(cls, value: Any) -> Any:
        return _blank_if_none(value)


class PacketCritiqueOutput(_FlexibleCritiqueModel):
    schema_id: Literal["packet_critique_v1"] = "packet_critique_v1"
    decision_adequate: bool | None = None
    packet_sufficiency_judgment: PacketJudgment = "ready"
    bundle_role_checks: list[BundleRoleCheck] = Field(default_factory=list, max_length=24)
    bad_answer_frame_risks: list[PacketFrameRisk] = Field(default_factory=list, max_length=8)
    answer_frame_issues: list[AnswerFrameIssue] = Field(default_factory=list, max_length=8)
    answer_frame_challenges: list[AnswerFrameIssue] = Field(default_factory=list, max_length=8)
    misleading_synthesis_risks: list[SynthesisRisk | str] = Field(default_factory=list, max_length=12)
    misleading_risks: list[SynthesisRisk | str] = Field(default_factory=list, max_length=12)
    insufficiency_warnings: list[PacketInsufficiencyWarning] = Field(default_factory=list, max_length=12)
    claim_quality_issues: list[ClaimQualityIssue] = Field(default_factory=list, max_length=12)
    section_routing_issues: list[SectionRoutingIssue] = Field(default_factory=list, max_length=12)
    challenges: dict[str, Any] = Field(default_factory=dict)
    missing_decision_functions: list[MissingDecisionFunction] = Field(default_factory=list, max_length=8)
    misassigned_roles: list[MisassignedRole] = Field(default_factory=list, max_length=12)
    overweighted_bundles: list[str] = Field(default_factory=list, max_length=12)
    underweighted_bundles: list[str] = Field(default_factory=list, max_length=12)
    missing_or_weak_cruxes: list[str] = Field(default_factory=list, max_length=8)
    section_plan_risks: list[str] = Field(default_factory=list, max_length=8)
    recommended_packet_edits: list[RecommendedPacketEdit] = Field(default_factory=list, max_length=16)

    @field_validator(
        "bundle_role_checks",
        "bad_answer_frame_risks",
        "answer_frame_issues",
        "answer_frame_challenges",
        "misleading_synthesis_risks",
        "misleading_risks",
        "insufficiency_warnings",
        "claim_quality_issues",
        "section_routing_issues",
        "misassigned_roles",
        "overweighted_bundles",
        "underweighted_bundles",
        "recommended_packet_edits",
        mode="before",
    )
    @classmethod
    def coerce_optional_list_fields(cls, value: Any) -> Any:
        return _coerce_list_field(value)

    @field_validator("missing_decision_functions", mode="before")
    @classmethod
    def coerce_missing_decision_functions(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, list):
            rows: list[Any] = []
            for item in value:
                if isinstance(item, dict):
                    rows.append(item)
                    continue
                text = _note_to_text(item)
                if text:
                    rows.append({"decision_function": text})
            return rows
        text = _note_to_text(value)
        return [{"decision_function": text}] if text else []

    @field_validator("missing_or_weak_cruxes", "section_plan_risks", mode="before")
    @classmethod
    def coerce_note_rows(cls, value: Any) -> Any:
        return [text for item in _coerce_list_field(value) if (text := _note_to_text(item))]


def _coerce_list_field(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    text = _note_to_text(value)
    return [text] if text else []


class BundleRefinement(BaseModel):
    bundle_id: str
    decision_role: str = ""
    weight: str = ""
    why_it_matters: str = ""
    limits: list[str] = Field(default_factory=list, max_length=6)
    section_use: str = ""
    section_targets: list[str] = Field(default_factory=list, max_length=6)
    rationale: str = ""


class RetainItemRefinement(BaseModel):
    item_id: str
    importance: str = ""
    omission_policy: str = ""
    required_terms: list[str] = Field(default_factory=list, max_length=12)
    rationale: str = ""


class PacketRefinementOutput(BaseModel):
    schema_id: Literal["decision_briefing_packet_refinement_v1"] = "decision_briefing_packet_refinement_v1"
    packet_ready_for_synthesis: bool = True
    bundle_updates: list[BundleRefinement] = Field(default_factory=list, max_length=24)
    retain_item_updates: list[RetainItemRefinement] = Field(default_factory=list, max_length=24)
    warnings: list[str] = Field(default_factory=list, max_length=12)
    rationale: str = ""


def run_packet_critique_and_refinement(
    packet: dict[str, Any],
    sufficiency_report: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    progress: Callable[[str, str, dict[str, Any] | None], None] | None = None,
) -> dict[str, Any]:
    pre_sufficiency = deepcopy(sufficiency_report)
    packet_progress(progress, "packet_critique", "started", packet_counts(packet))
    critique = run_packet_critique(
        packet,
        pre_sufficiency,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        progress=progress,
    )
    packet_progress(progress, "packet_critique", "completed", critique_progress_details(critique))
    packet_progress(
        progress,
        "packet_refinement",
        "started",
        {
            "accepted_count": critique["adjudication_report"].get("accepted_count", 0),
            "warning_only_count": critique["adjudication_report"].get("warning_only_count", 0),
        },
    )
    refined = run_packet_refinement(
        packet,
        pre_sufficiency,
        critique["adjudication_report"],
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
    )
    packet_progress(progress, "packet_refinement", "completed", refinement_progress_details(refined))
    packet_progress(progress, "packet_sufficiency_recompute", "started")
    candidate_pool = _post_refinement_candidate_pool(packet, pre_sufficiency)
    if _refinement_left_packet_semantics_unchanged(refined["report"]):
        recomputed = build_packet_sufficiency_report(refined["packet"], candidate_pool=candidate_pool)
        post_sufficiency = preserve_omissions_with_recomputed_quantities(pre_sufficiency, recomputed)
    else:
        post_sufficiency = build_packet_sufficiency_report(refined["packet"], candidate_pool=candidate_pool)
    _sync_packet_coverage_with_sufficiency(refined["packet"], post_sufficiency)
    writer_guidance = build_writer_guidance_packet(critique_adjudication=critique["adjudication_report"], sufficiency_report=post_sufficiency)
    attach_writer_guidance(refined["packet"], writer_guidance)
    packet_progress(progress, "packet_sufficiency_recompute", "completed", {"status": post_sufficiency.get("status", "unknown")})
    return {
        "decision_briefing_packet": refined["packet"],
        "packet_sufficiency_report_pre_refinement": pre_sufficiency,
        "packet_sufficiency_report": post_sufficiency,
        "packet_critique_prompt": critique["prompt"],
        "packet_critique_raw": critique["raw"],
        "packet_critique_report": critique["report"],
        "packet_critique_adjudication_report": critique["adjudication_report"],
        "writer_guidance_packet": writer_guidance,
        "decision_briefing_packet_refinement_prompt": refined["prompt"],
        "decision_briefing_packet_refinement_raw": refined["raw"],
        "decision_briefing_packet_refinement_report": refined["report"],
    }


def run_packet_critique(
    packet: dict[str, Any],
    sufficiency_report: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    progress: Callable[[str, str, dict[str, Any] | None], None] | None = None,
) -> dict[str, Any]:
    prompt = build_packet_critique_prompt(packet, sufficiency_report)
    if backend.strip() == "prompt":
        report = _skipped_report("packet_critique_report_v1", "prompt_backend")
        adjudication = _adjudication_report({}, packet, skipped=True)
        return {"prompt": prompt, "raw": "", "report": report, "adjudication_report": adjudication}
    if should_use_parallel_packet_critique(packet, threshold=_packet_critique_parallel_threshold()):
        return run_parallel_packet_critique(
            packet,
            sufficiency_report,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            run_backend=run_model_backend,
            critique_schema=PacketCritiqueOutput,
            adjudicate=_adjudication_report,
            progress=progress,
        )
    packet_progress(progress, "packet_critique_single_model_call", "started", {"prompt_chars": len(prompt)})
    raw = run_model_backend(
        prompt,
        backend,
        timeout_seconds=backend_timeout,
        max_retries=backend_retries,
        response_schema=PacketCritiqueOutput.model_json_schema(),
    ).text
    packet_progress(progress, "packet_critique_single_model_call", "completed", {"raw_chars": len(raw)})
    parse_report = parse_model_output_report(raw, PacketCritiqueOutput)
    critique = parse_report.get("data") if parse_report.get("ok") else {}
    adjudication = _adjudication_report(critique if isinstance(critique, dict) else {}, packet)
    report = {
        "schema_id": "packet_critique_report_v1",
        "status": "parsed" if parse_report.get("ok") else "parse_failed",
        "method": "single_packet_critique",
        "parse_report": parse_report,
        "judgment": (critique or {}).get("packet_sufficiency_judgment") if isinstance(critique, dict) else "unknown",
    }
    return {"prompt": prompt, "raw": canonical_json_output(raw), "report": report, "adjudication_report": adjudication}


def _packet_critique_parallel_threshold() -> int:
    try:
        return max(1, int(os.environ.get("ECM_PACKET_CRITIQUE_PARALLEL_THRESHOLD", "8")))
    except ValueError:
        return 8


def run_packet_refinement(
    packet: dict[str, Any],
    sufficiency_report: dict[str, Any],
    critique_adjudication: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    prompt = build_packet_refinement_prompt(packet, sufficiency_report, critique_adjudication)
    if backend.strip() == "prompt":
        return {
            "packet": packet,
            "prompt": prompt,
            "raw": "",
            "report": _skipped_report("decision_briefing_packet_refinement_report_v1", "prompt_backend"),
        }
    return run_targeted_packet_refinement(
        packet=packet,
        sufficiency_report=sufficiency_report,
        critique_adjudication=critique_adjudication,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        run_backend=run_model_backend,
        refinement_schema=PacketRefinementOutput,
        apply_refinement=apply_packet_refinement,
        apply_cleanup=apply_adjudicated_relabel_cleanup,
        repair_packet=repair_packet_for_synthesis,
    )
def build_packet_critique_prompt(packet: dict[str, Any], sufficiency_report: dict[str, Any]) -> str:
    view = packet_summary_for_model(packet, max_bundles=24)
    return (
        "You are an adversarial analyst reviewing a source-grounded decision briefing packet before prose synthesis.\n"
        "Do not write the memo. Identify whether the packet is decision-adequate and where it may mislead synthesis.\n"
        "You must check every evidence_bundles row in the packet summary for role/direction consistency.\n"
        "For each bundle, decide whether `decision_role` matches the claim text, source role, directionality, and section_use.\n"
        "Use these role meanings: strongest_support = evidence supporting the main/default answer; counterweight = evidence that challenges, weakens, or cautions against the answer; scope_boundary = evidence limiting where the answer applies; quantitative_anchor = a load-bearing numeric estimate; decision_crux = a fact or uncertainty that could change the answer; mechanism/context = explanatory or background evidence.\n"
        "If a bundle has directionality like challenges/in_tension/bounds but current_role is strongest_support, treat that as suspicious unless the claim clearly supports the answer despite the direction label.\n"
        "Return one `bundle_role_checks` item for every bundle in the packet summary. If role_matches_claim_and_direction is false, set recommended_role and add the same problem to `misassigned_roles` and `recommended_packet_edits` with edit_type `relabel`.\n"
        "When adding recommended_packet_edits, use target_ids for bundle IDs; if you include a source-only insufficiency warning, use edit_type `add_warning`.\n"
        "Also check for packet problems that would mislead synthesis even when role labels are valid: malformed or non-claim claim text, off-question evidence, low-quality evidence treated as load-bearing, answer-frame problems, section-routing mistakes, missing decision functions, overcompressed scope/crux evidence, and quantity interpretation risks.\n"
        "Record these in the structured fields: misleading_synthesis_risks, insufficiency_warnings, claim_quality_issues, section_routing_issues, answer_frame_issues, missing_decision_functions, missing_or_weak_cruxes, and section_plan_risks.\n"
        "You may not invent new sources, quantities, or claims. Recommendations must reference existing IDs, or be recorded as insufficiency warnings.\n"
        "Return only JSON matching the requested schema.\n\n"
        "Packet summary:\n"
        f"{json.dumps(view, indent=2, ensure_ascii=False)}\n\n"
        "Packet sufficiency report:\n"
        f"{json.dumps(sufficiency_report, indent=2, ensure_ascii=False)}\n"
    )


def build_packet_refinement_prompt(
    packet: dict[str, Any],
    sufficiency_report: dict[str, Any],
    critique_adjudication: dict[str, Any],
) -> str:
    view = packet_summary_for_model(packet, max_bundles=24)
    return (
        "You are improving a structured decision briefing packet, not writing prose.\n"
        "Use the accepted critique recommendations and sufficiency report to improve roles, weights, salience, crux clarity, and bundle rationales.\n"
        "For accepted recommendations with edit_type `relabel`, return a bundle_update for each target bundle with the recommended decision_role and rewrite all role-dependent fields you touch, especially section_use and why_it_matters, so they no longer describe the old role.\n"
        "Role-dependent language must be internally consistent: strongest_support should explain how the item supports the current answer; counterweight should explain how it challenges, limits, or cautions against the current answer; scope_boundary should explain where the answer applies; quantitative_anchor should explain the numeric estimate carried by the item.\n"
        "Do not add new sources, quantities, claims, or IDs. Preserve every critical/high must-retain item unless you explicitly demote it with an anchored rationale.\n"
        "Return only JSON matching the requested schema.\n\n"
        "Packet summary:\n"
        f"{json.dumps(view, indent=2, ensure_ascii=False)}\n\n"
        "Packet sufficiency report:\n"
        f"{json.dumps(sufficiency_report, indent=2, ensure_ascii=False)}\n\n"
        "Accepted critique/adjudication:\n"
        f"{json.dumps(critique_adjudication, indent=2, ensure_ascii=False)}\n"
    )


def apply_packet_refinement(packet: dict[str, Any], payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    refined = deepcopy(packet)
    bundle_lookup = {
        str(bundle.get("bundle_id")): bundle
        for bundle in refined.get("evidence_bundles", [])
        if isinstance(bundle, dict)
    }
    retain_lookup = {
        str(item.get("item_id")): item
        for item in refined.get("must_retain_ledger", [])
        if isinstance(item, dict)
    }
    applied: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for update in payload.get("bundle_updates", []) if isinstance(payload.get("bundle_updates"), list) else []:
        bundle_id = str(update.get("bundle_id", ""))
        target = bundle_lookup.get(bundle_id)
        if not target:
            rejected.append({"target_id": bundle_id, "reason": "unknown_bundle_id"})
            continue
        changed = _apply_bundle_update(target, update)
        if changed:
            applied.append({"target_id": bundle_id, "fields": changed, "rationale": update.get("rationale", "")})
    for update in payload.get("retain_item_updates", []) if isinstance(payload.get("retain_item_updates"), list) else []:
        item_id = str(update.get("item_id", ""))
        target = retain_lookup.get(item_id)
        if not target:
            rejected.append({"target_id": item_id, "reason": "unknown_retain_item_id"})
            continue
        changed = _apply_retain_update(target, update)
        if changed:
            applied.append({"target_id": item_id, "fields": changed, "rationale": update.get("rationale", "")})
    refined["coverage_report"] = {
        **(refined.get("coverage_report", {}) if isinstance(refined.get("coverage_report"), dict) else {}),
        "model_refinement_applied_update_count": len(applied),
        "model_refinement_warning_count": len(payload.get("warnings", []) if isinstance(payload.get("warnings"), list) else []),
    }
    return refined, applied, rejected


def apply_adjudicated_relabel_cleanup(packet: dict[str, Any], critique_adjudication: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bundle_lookup = {
        str(bundle.get("bundle_id")): bundle
        for bundle in packet.get("evidence_bundles", [])
        if isinstance(bundle, dict)
    }
    applied: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for recommendation in critique_adjudication.get("accepted_recommendations", []) if isinstance(critique_adjudication.get("accepted_recommendations"), list) else []:
        if not isinstance(recommendation, dict) or recommendation.get("edit_type") != "relabel":
            continue
        role = str(recommendation.get("recommended_role", "")).strip()
        if not role:
            continue
        for target_id in _string_list(recommendation.get("target_ids")):
            bundle = bundle_lookup.get(target_id)
            if not bundle:
                rejected.append({"target_id": target_id, "reason": "unknown_bundle_id_for_adjudicated_relabel"})
                continue
            changed = _apply_role_consistency_cleanup(bundle, role)
            if changed:
                applied.append(
                    {
                        "target_id": target_id,
                        "fields": changed,
                        "rationale": recommendation.get("rationale", ""),
                        "source": "accepted_critique_relabel_cleanup",
                    }
                )
    return applied, rejected


def _apply_role_consistency_cleanup(bundle: dict[str, Any], role: str) -> list[str]:
    changed = []
    if str(bundle.get("decision_role", "")).strip() != role:
        bundle["decision_role"] = role
        changed.append("decision_role")
    section_use = str(bundle.get("section_use", "")).strip()
    if not section_use or _section_use_conflicts_with_role(section_use, role):
        bundle["section_use"] = _default_section_use_for_role(role)
        changed.append("section_use")
    return changed


def _section_use_conflicts_with_role(section_use: str, role: str) -> bool:
    text = section_use.lower()
    support_terms = ("primary support", "strongest support", "load-bearing support", "supports the current answer")
    caution_terms = ("contrary evidence", "counterweight", "challenges", "cautions against", "limits the current answer")
    if role == "counterweight":
        return any(term in text for term in support_terms)
    if role == "strongest_support":
        return any(term in text for term in caution_terms)
    return False


def _default_section_use_for_role(role: str) -> str:
    uses = {
        "strongest_support": "Use as evidence supporting the current answer.",
        "counterweight": "Use as contrary or cautionary evidence that tests the current answer.",
        "scope_boundary": "Use to define where the current answer does and does not apply.",
        "quantitative_anchor": "Use as a load-bearing quantitative estimate for the decision.",
        "decision_crux": "Use as a crux that could change the recommended answer.",
        "mechanism/context": "Use as mechanism or context for interpreting the decision evidence.",
    }
    return uses.get(role, "Use according to the accepted evidence role for this decision.")


def _adjudication_report(critique: dict[str, Any], packet: dict[str, Any], *, skipped: bool = False) -> dict[str, Any]:
    ids = _known_packet_ids(packet)
    if skipped:
        return {
            "schema_id": "packet_critique_adjudication_report_v1",
            "status": "skipped_prompt_backend",
            "accepted_recommendations": [],
            "rejected_recommendations": [],
            "warning_only_recommendations": [],
        }
    accepted = []
    rejected = []
    warning_only = []
    role_check_edits = _recommended_edits_from_role_checks(critique)
    explicit_edits = critique.get("recommended_packet_edits", []) if isinstance(critique.get("recommended_packet_edits"), list) else []
    for edit in [*role_check_edits, *explicit_edits]:
        edit = _normalize_recommended_edit(edit)
        target_ids = [str(item) for item in edit.get("target_ids", []) if str(item).strip()]
        if edit.get("edit_type") in {"add_warning", "insufficiency_warning"} and not target_ids:
            warning_only.append({**edit, "reason": "source_or_packet_level_warning"})
        elif edit.get("edit_type") == "relabel" and not str(edit.get("recommended_role", "")).strip():
            warning_only.append({**edit, "reason": "relabel_without_recommended_role"})
        elif target_ids and all(target_id in ids for target_id in target_ids):
            accepted.append(edit)
        elif target_ids:
            rejected.append({**edit, "reason": "unknown_target_id"})
        else:
            warning_only.append({**edit, "reason": "no_target_ids"})
    accepted = dedupe_issue_rows(accepted, key_fields=("edit_type", "target_ids", "recommended_role", "recommended_weight"))
    rejected = dedupe_issue_rows(rejected, key_fields=("edit_type", "target_ids", "recommended_role", "reason"))
    warning_only = dedupe_issue_rows(warning_only, key_fields=("edit_type", "target_ids", "bundle_id", "source_id", "warning", "reason"))
    normalized_issues = normalized_critique_issues(critique, packet)
    return {
        "schema_id": "packet_critique_adjudication_report_v1",
        "status": "accepted_with_warnings" if rejected or warning_only else "accepted",
        "judgment": critique.get("packet_sufficiency_judgment", "unknown"),
        "accepted_recommendations": accepted[:24],
        "rejected_recommendations": rejected[:24],
        "warning_only_recommendations": warning_only[:24],
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "warning_only_count": len(warning_only),
        "bundle_role_checks": critique.get("bundle_role_checks", []),
        "bad_answer_frame_risks": critique.get("bad_answer_frame_risks", []),
        "answer_frame_issues": normalized_issues["answer_frame_issues"],
        "misleading_synthesis_risks": normalized_issues["misleading_synthesis_risks"],
        "insufficiency_warnings": normalized_issues["insufficiency_warnings"],
        "claim_quality_issues": normalized_issues["claim_quality_issues"],
        "section_routing_issues": normalized_issues["section_routing_issues"],
        "missing_decision_functions": critique.get("missing_decision_functions", []),
        "misassigned_roles": critique.get("misassigned_roles", []),
        "section_plan_risks": critique.get("section_plan_risks", []),
    }


def _recommended_edits_from_role_checks(critique: dict[str, Any]) -> list[dict[str, Any]]:
    edits = []
    for check in critique.get("bundle_role_checks", []) if isinstance(critique.get("bundle_role_checks"), list) else []:
        if not isinstance(check, dict) or check.get("role_matches_claim_and_direction") is not False:
            continue
        bundle_id = str(check.get("bundle_id", "")).strip()
        recommended_role = str(check.get("recommended_role", "")).strip()
        if not bundle_id or not recommended_role:
            continue
        edits.append(
            {
                "edit_type": "relabel",
                "target_ids": [bundle_id],
                "recommended_role": recommended_role,
                "rationale": str(check.get("rationale") or check.get("problem") or "").strip(),
                "source": "bundle_role_check",
            }
        )
    return edits


def _normalize_recommended_edit(edit: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(edit)
    target_ids = _string_list(normalized.get("target_ids"))
    if not target_ids and str(normalized.get("target_id", "")).strip():
        target_ids = [str(normalized.get("target_id", "")).strip()]
    if not target_ids and str(normalized.get("bundle_id", "")).strip():
        target_ids = [str(normalized.get("bundle_id", "")).strip()]
    if target_ids:
        normalized["target_ids"] = target_ids
    if not normalized.get("rationale") and normalized.get("description"):
        normalized["rationale"] = normalized.get("description")
    if normalized.get("edit_type") == "insufficiency_warning":
        normalized["edit_type"] = "add_warning"
        if normalized.get("description") and not normalized.get("warning"):
            normalized["warning"] = normalized.get("description")
    if normalized.get("edit_type") == "relabel" and not str(normalized.get("recommended_role", "")).strip():
        inferred = _infer_recommended_role_from_text(
            " ".join(
                item
                for item in (
                    str(normalized.get("rationale", "")),
                    str(normalized.get("description", "")),
                    str(normalized.get("warning", "")),
                )
                if item.strip()
            )
        )
        if inferred:
            normalized["recommended_role"] = inferred
    return normalized


def _infer_recommended_role_from_text(text: str) -> str:
    lowered = text.lower()
    roles = (
        "strongest_support",
        "counterweight",
        "scope_boundary",
        "quantitative_anchor",
        "decision_crux",
        "mechanism/context",
        "mechanism",
        "context",
    )
    phrase_map = {
        "strongest support": "strongest_support",
        "primary support": "strongest_support",
        "scope boundary": "scope_boundary",
        "quantitative anchor": "quantitative_anchor",
        "decision crux": "decision_crux",
    }
    for role in roles:
        if re.search(rf"\bto\s+{re.escape(role)}\b", lowered):
            return role
    for phrase, role in phrase_map.items():
        if re.search(rf"\bto\s+{re.escape(phrase)}\b", lowered):
            return role
    for role in roles:
        if role in lowered:
            return role
    for phrase, role in phrase_map.items():
        if phrase in lowered:
            return role
    return ""


def _apply_bundle_update(target: dict[str, Any], update: dict[str, Any]) -> list[str]:
    changed = []
    for field in ("decision_role", "weight", "why_it_matters", "section_use"):
        value = str(update.get(field, "")).strip()
        if value:
            target[field] = value
            changed.append(field)
    for field in ("limits", "section_targets"):
        values = _string_list(update.get(field))
        if values:
            target[field] = values[:8]
            changed.append(field)
    return changed


def _apply_retain_update(target: dict[str, Any], update: dict[str, Any]) -> list[str]:
    changed = []
    for field in ("importance", "omission_policy"):
        value = str(update.get(field, "")).strip()
        if value:
            target[field] = value
            changed.append(field)
    terms = _string_list(update.get("required_terms"))
    if terms:
        target["required_terms"] = _dedupe([*_string_list(target.get("required_terms")), *terms])[:12]
        changed.append("required_terms")
    return changed


def _post_refinement_candidate_pool(packet: dict[str, Any], pre_sufficiency: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _candidate_pool_from_packet(packet)
    rows.extend(_quantity_obligation_candidates(pre_sufficiency))
    return rows


def _refinement_left_packet_semantics_unchanged(report: dict[str, Any]) -> bool:
    status = str(report.get("status") or "")
    if status == "skipped":
        return True
    try:
        applied = int(report.get("applied_update_count", 0) or 0)
    except (TypeError, ValueError):
        applied = 0
    return status == "applied" and applied == 0


def _quantity_obligation_candidates(pre_sufficiency: dict[str, Any]) -> list[dict[str, Any]]:
    ledger = pre_sufficiency.get("quantity_obligation_ledger")
    obligations = ledger.get("obligations", []) if isinstance(ledger, dict) else []
    rows: list[dict[str, Any]] = []
    for index, obligation in enumerate(obligations if isinstance(obligations, list) else []):
        if not isinstance(obligation, dict):
            continue
        quantity = str(obligation.get("quantity", "")).strip()
        if not quantity:
            continue
        fallback_id = f"prior_quantity_obligation_{index:03d}"
        rows.append(
            {
                "pool_id": obligation.get("pool_id") or fallback_id,
                "candidate_card_id": obligation.get("candidate_card_id") or fallback_id,
                "decision_role": "quantitative_anchor",
                "decision_relevance_score": 10,
                "source_ids": _string_list(obligation.get("source_ids")),
                "source_labels": _string_list(obligation.get("source_labels")),
                "quantity_values": [quantity],
                "claim_ids": _string_list(obligation.get("claim_ids")),
                "source_grounded": True,
                "claim": obligation.get("claim"),
            }
        )
    return rows


def _sync_packet_coverage_with_sufficiency(packet: dict[str, Any], sufficiency: dict[str, Any]) -> None:
    ledger = sufficiency.get("quantity_obligation_ledger")
    if not isinstance(ledger, dict):
        return
    coverage = packet.get("coverage_report", {}) if isinstance(packet.get("coverage_report"), dict) else {}
    packet["coverage_report"] = {
        **coverage,
        "quantity_missing_count": int(ledger.get("missing_count", 0) or 0),
        "quantity_obligation_count": int(ledger.get("obligation_count", 0) or 0),
    }


def _candidate_pool_from_packet(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for bundle in packet.get("evidence_bundles", []) if isinstance(packet.get("evidence_bundles"), list) else []:
        if not isinstance(bundle, dict):
            continue
        rows.append(
            {
                "pool_id": bundle.get("pretrim_pool_id") or bundle.get("bundle_id"),
                "candidate_card_id": (_string_list(bundle.get("candidate_card_ids")) or [""])[0],
                "decision_role": bundle.get("decision_role"),
                "decision_relevance_score": 9 if bundle.get("weight") == "high" else 7,
                "source_ids": _string_list(bundle.get("source_ids")),
                "quantity_values": _string_list(bundle.get("quantity_values")),
                "source_grounded": bundle.get("source_grounded", True),
                "claim": bundle.get("claim"),
            }
        )
    return rows


def _known_packet_ids(packet: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for bundle in packet.get("evidence_bundles", []) if isinstance(packet.get("evidence_bundles"), list) else []:
        if not isinstance(bundle, dict):
            continue
        for key in ("bundle_id", "candidate_card_ids", "source_card_ids", "claim_ids", "relation_ids", "quantity_ids"):
            ids.update(_string_list(bundle.get(key)))
    for item in packet.get("must_retain_ledger", []) if isinstance(packet.get("must_retain_ledger"), list) else []:
        if isinstance(item, dict):
            ids.update(_string_list(item.get("item_id")))
    return {item for item in ids if item}


def _skipped_report(schema_id: str, reason: str) -> dict[str, Any]:
    return {"schema_id": schema_id, "status": "skipped", "reason": reason}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
