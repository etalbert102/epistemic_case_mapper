from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, Field

from epistemic_case_mapper.map_briefing_decision_packet import packet_summary_for_model
from epistemic_case_mapper.map_briefing_packet_sufficiency import build_packet_sufficiency_report
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.model_schemas import parse_model_output_report


PacketJudgment = Literal["ready", "needs_repair", "not_sufficient"]
PacketEditType = Literal["promote", "demote", "split", "merge", "relabel", "add_warning"]


class PacketFrameRisk(BaseModel):
    risk: str = ""
    affected_bundle_ids: list[str] = Field(default_factory=list, max_length=12)
    why_it_matters: str = ""
    recommended_action: str = ""


class MissingDecisionFunction(BaseModel):
    decision_function: str = ""
    evidence_ids_that_suggest_gap: list[str] = Field(default_factory=list, max_length=12)
    recommended_action: str = ""


class MisassignedRole(BaseModel):
    bundle_id: str = ""
    current_role: str = ""
    recommended_role: str = ""
    rationale: str = ""


class RecommendedPacketEdit(BaseModel):
    edit_type: PacketEditType
    target_ids: list[str] = Field(default_factory=list, max_length=12)
    rationale: str = ""
    recommended_role: str = ""
    recommended_weight: str = ""
    warning: str = ""


class PacketCritiqueOutput(BaseModel):
    schema_id: Literal["packet_critique_v1"] = "packet_critique_v1"
    packet_sufficiency_judgment: PacketJudgment = "ready"
    bad_answer_frame_risks: list[PacketFrameRisk] = Field(default_factory=list, max_length=8)
    missing_decision_functions: list[MissingDecisionFunction] = Field(default_factory=list, max_length=8)
    misassigned_roles: list[MisassignedRole] = Field(default_factory=list, max_length=12)
    overweighted_bundles: list[str] = Field(default_factory=list, max_length=12)
    underweighted_bundles: list[str] = Field(default_factory=list, max_length=12)
    missing_or_weak_cruxes: list[str] = Field(default_factory=list, max_length=8)
    section_plan_risks: list[str] = Field(default_factory=list, max_length=8)
    recommended_packet_edits: list[RecommendedPacketEdit] = Field(default_factory=list, max_length=16)


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
) -> dict[str, Any]:
    pre_sufficiency = deepcopy(sufficiency_report)
    critique = run_packet_critique(
        packet,
        pre_sufficiency,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
    )
    refined = run_packet_refinement(
        packet,
        pre_sufficiency,
        critique["adjudication_report"],
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
    )
    candidate_pool = _candidate_pool_from_packet(packet)
    post_sufficiency = build_packet_sufficiency_report(refined["packet"], candidate_pool=candidate_pool)
    return {
        "decision_briefing_packet": refined["packet"],
        "packet_sufficiency_report_pre_refinement": pre_sufficiency,
        "packet_sufficiency_report": post_sufficiency,
        "packet_critique_prompt": critique["prompt"],
        "packet_critique_raw": critique["raw"],
        "packet_critique_report": critique["report"],
        "packet_critique_adjudication_report": critique["adjudication_report"],
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
) -> dict[str, Any]:
    prompt = build_packet_critique_prompt(packet, sufficiency_report)
    if backend.strip() == "prompt":
        report = _skipped_report("packet_critique_report_v1", "prompt_backend")
        adjudication = _adjudication_report({}, packet, skipped=True)
        return {"prompt": prompt, "raw": "", "report": report, "adjudication_report": adjudication}
    raw = run_model_backend(
        prompt,
        backend,
        timeout_seconds=backend_timeout,
        max_retries=backend_retries,
        response_schema=PacketCritiqueOutput.model_json_schema(),
    ).text
    parse_report = parse_model_output_report(raw, PacketCritiqueOutput)
    critique = parse_report.get("data") if parse_report.get("ok") else {}
    adjudication = _adjudication_report(critique if isinstance(critique, dict) else {}, packet)
    report = {
        "schema_id": "packet_critique_report_v1",
        "status": "parsed" if parse_report.get("ok") else "parse_failed",
        "parse_report": parse_report,
        "judgment": (critique or {}).get("packet_sufficiency_judgment") if isinstance(critique, dict) else "unknown",
    }
    return {"prompt": prompt, "raw": canonical_json_output(raw), "report": report, "adjudication_report": adjudication}


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
    raw = run_model_backend(
        prompt,
        backend,
        timeout_seconds=backend_timeout,
        max_retries=backend_retries,
        response_schema=PacketRefinementOutput.model_json_schema(),
    ).text
    parse_report = parse_model_output_report(raw, PacketRefinementOutput)
    if not parse_report.get("ok"):
        return {
            "packet": packet,
            "prompt": prompt,
            "raw": canonical_json_output(raw),
            "report": {
                "schema_id": "decision_briefing_packet_refinement_report_v1",
                "status": "parse_failed",
                "parse_report": parse_report,
                "applied_update_count": 0,
                "rejected_update_count": 0,
            },
        }
    refined, applied, rejected = apply_packet_refinement(packet, parse_report["data"])
    return {
        "packet": refined,
        "prompt": prompt,
        "raw": canonical_json_output(raw),
        "report": {
            "schema_id": "decision_briefing_packet_refinement_report_v1",
            "status": "applied",
            "parse_report": parse_report,
            "packet_ready_for_synthesis": parse_report["data"].get("packet_ready_for_synthesis"),
            "applied_update_count": len(applied),
            "rejected_update_count": len(rejected),
            "applied_updates": applied[:30],
            "rejected_updates": rejected[:30],
            "warnings": parse_report["data"].get("warnings", []),
        },
    }


def build_packet_critique_prompt(packet: dict[str, Any], sufficiency_report: dict[str, Any]) -> str:
    view = packet_summary_for_model(packet, max_bundles=24)
    return (
        "You are an adversarial analyst reviewing a source-grounded decision briefing packet before prose synthesis.\n"
        "Do not write the memo. Identify whether the packet is decision-adequate and where it may mislead synthesis.\n"
        "You may challenge the answer frame, role assignments, weights, cruxes, and section plan.\n"
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
    for edit in critique.get("recommended_packet_edits", []) if isinstance(critique.get("recommended_packet_edits"), list) else []:
        target_ids = [str(item) for item in edit.get("target_ids", []) if str(item).strip()]
        if target_ids and all(target_id in ids for target_id in target_ids):
            accepted.append(edit)
        elif target_ids:
            rejected.append({**edit, "reason": "unknown_target_id"})
        else:
            warning_only.append({**edit, "reason": "no_target_ids"})
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
        "bad_answer_frame_risks": critique.get("bad_answer_frame_risks", []),
        "missing_decision_functions": critique.get("missing_decision_functions", []),
        "misassigned_roles": critique.get("misassigned_roles", []),
        "section_plan_risks": critique.get("section_plan_risks", []),
    }


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
