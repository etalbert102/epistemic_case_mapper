from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.semantic_pipeline import validate_map_candidate
from epistemic_case_mapper.staged_semantic_duplicate_quality import near_duplicate_claim_pairs
from epistemic_case_mapper.staged_semantic_prompt_schemas import relation_json_schema
from epistemic_case_mapper.staged_semantic_quality import _map_quality_repair_prompt, _quality_markdown, evaluate_staged_map_quality
from epistemic_case_mapper.staged_semantic_relation_candidates import _candidate_relation_pairs
from epistemic_case_mapper.staged_semantic_relation_quality import relation_pair_intent, relation_semantic_rejection_reason
from epistemic_case_mapper.staged_semantic_sources import (
    _normalize_relation_proposal,
    _parse_model_json,
    _relation_pair_prompt,
    _relative,
)
from epistemic_case_mapper.submission_manifest import SubmissionManifest, WorkedRegion


def run_map_critique_repair_loop(
    *,
    repo_root: Path,
    manifest_path: str,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    all_chunks: list[Any],
    selected_chunks: list[Any],
    skipped_chunks: list[dict[str, Any]],
    candidate_map: dict[str, Any],
    quality_report: dict[str, Any],
    rejected_claims: list[dict[str, Any]],
    rejected_relations: list[dict[str, Any]],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifact_dir: Path,
    decision_question: str | None = None,
) -> dict[str, Any]:
    critique = build_map_critique(candidate_map, quality_report, rejected_claims, rejected_relations)
    write_json(artifact_dir / "map_critique.json", critique)
    repair_plan = build_map_repair_plan(candidate_map, critique)
    write_json(artifact_dir / "map_repair_plan.json", repair_plan)
    info: dict[str, Any] = {
        "ran": True,
        "accepted": False,
        "reason": "",
        "critique_path": artifact_dir / "map_critique.json",
        "repair_plan_path": artifact_dir / "map_repair_plan.json",
        "targeted_relation_repair": {"attempted": 0, "accepted": 0, "rejected": 0},
    }
    candidate, targeted_info = _apply_targeted_repairs(
        manifest=manifest,
        region=region,
        case_manifest=case_manifest,
        candidate_map=candidate_map,
        repair_plan=repair_plan,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        artifact_dir=artifact_dir,
        decision_question=decision_question,
    )
    info["targeted_relation_repair"] = targeted_info
    accepted_info = _accepted_repair_info(
        repo_root=repo_root,
        manifest_path=manifest_path,
        manifest=manifest,
        region=region,
        case_manifest=case_manifest,
        all_chunks=all_chunks,
        selected_chunks=selected_chunks,
        skipped_chunks=skipped_chunks,
        candidate_map=candidate,
        original_quality=quality_report,
        rejected_claims=rejected_claims,
        rejected_relations=rejected_relations + targeted_info.get("rejected_relations", []),
        artifact_dir=artifact_dir,
        decision_question=decision_question,
    )
    if accepted_info.get("accepted"):
        info.update(accepted_info)
        info["reason"] = "accepted_targeted_repair"
        return info
    info.update(_run_whole_map_repair_fallback(
        repo_root=repo_root,
        manifest_path=manifest_path,
        manifest=manifest,
        region=region,
        case_manifest=case_manifest,
        all_chunks=all_chunks,
        selected_chunks=selected_chunks,
        skipped_chunks=skipped_chunks,
        candidate_map=candidate_map,
        quality_report=quality_report,
        rejected_claims=rejected_claims,
        rejected_relations=rejected_relations,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        artifact_dir=artifact_dir,
        decision_question=decision_question,
    ))
    if not info.get("reason"):
        info["reason"] = accepted_info.get("reason", "targeted_repair_not_accepted")
    return info


def build_map_critique(
    candidate_map: dict[str, Any],
    quality_report: dict[str, Any],
    rejected_claims: list[dict[str, Any]],
    rejected_relations: list[dict[str, Any]],
) -> dict[str, Any]:
    claims = [claim for claim in candidate_map.get("claims", []) if isinstance(claim, dict)]
    relations = [relation for relation in candidate_map.get("relations", []) if isinstance(relation, dict)]
    findings: list[dict[str, Any]] = []
    findings.extend(_quality_findings(quality_report))
    findings.extend(_label_audit_findings(claims))
    findings.extend(_duplicate_findings(claims))
    findings.extend(_isolated_core_claim_findings(claims, relations))
    findings.extend(_rejection_findings(rejected_claims, rejected_relations))
    relation_candidates = _missing_relation_candidates(claims, relations)
    for index, packet in enumerate(relation_candidates, start=len(findings) + 1):
        findings.append(
            _finding(
                index,
                severity="risk",
                category="missing_relation",
                target_id=packet["pair_id"],
                issue="A high-priority claim pair has no accepted relation.",
                recommended_fix="Run targeted relation classification for this pair before synthesizing from the map.",
                evidence={"left": packet["left"]["claim_id"], "right": packet["right"]["claim_id"], "reason": packet.get("candidate_reason", "")},
            )
        )
    return {
        "schema_id": "staged_map_critique_v1",
        "status": "review_needed" if findings else "no_findings",
        "summary": {
            "finding_count": len(findings),
            "quality_issue_count": len(quality_report.get("issues", [])),
            "label_audit_warning_count": sum(len(_label_warnings(claim)) for claim in claims),
            "missing_relation_candidate_count": len(relation_candidates),
        },
        "findings": findings,
        "repair_candidates": {"relation_pairs": relation_candidates},
    }


def build_map_repair_plan(candidate_map: dict[str, Any], critique: dict[str, Any]) -> dict[str, Any]:
    relation_pairs = critique.get("repair_candidates", {}).get("relation_pairs", [])
    findings = critique.get("findings", [])
    evidence_rows = [
        ["Map critique", "Needs review", f"{finding['category']}: {finding['issue']}"]
        for finding in findings[:8]
    ]
    crux_notes = [
        f"{pair['left']['claim_id']} and {pair['right']['claim_id']} require relation adjudication."
        for pair in relation_pairs[:5]
    ]
    return {
        "schema_id": "staged_map_repair_plan_v1",
        "actions": [
            {"action": "targeted_relation_classification", "count": len(relation_pairs)},
            {"action": "append_evidence_check_rows", "count": len(evidence_rows)},
            {"action": "append_crux_review_notes", "count": len(crux_notes)},
        ],
        "relation_pairs": relation_pairs[:8],
        "evidence_check_rows": evidence_rows,
        "crux_review_notes": crux_notes,
        "original_counts": {
            "claims": len(candidate_map.get("claims", [])) if isinstance(candidate_map.get("claims"), list) else 0,
            "relations": len(candidate_map.get("relations", [])) if isinstance(candidate_map.get("relations"), list) else 0,
        },
    }


def _apply_targeted_repairs(
    *,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    candidate_map: dict[str, Any],
    repair_plan: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifact_dir: Path,
    decision_question: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    repaired = _copy_map(candidate_map)
    repaired.setdefault("evidence_check", [])
    repaired.setdefault("crux_candidates", [])
    repaired["evidence_check"].extend(repair_plan.get("evidence_check_rows", []))
    repaired["crux_candidates"].extend(repair_plan.get("crux_review_notes", []))
    accepted, rejected = _targeted_relation_repairs(
        manifest=manifest,
        region=region,
        case_manifest=case_manifest,
        candidate_map=repaired,
        relation_pairs=repair_plan.get("relation_pairs", []),
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        artifact_dir=artifact_dir,
        decision_question=decision_question,
    )
    repaired.setdefault("relations", []).extend(accepted)
    return repaired, {
        "attempted": len(repair_plan.get("relation_pairs", [])),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "rejected_relations": rejected,
    }


def _targeted_relation_repairs(
    *,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    candidate_map: dict[str, Any],
    relation_pairs: list[dict[str, Any]],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifact_dir: Path,
    decision_question: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    claim_ids = {str(claim.get("claim_id", "")) for claim in candidate_map.get("claims", []) if isinstance(claim, dict)}
    permitted_types = manifest.relation_ontology.permitted_types()
    seen = {
        (str(relation.get("source_claim", "")), str(relation.get("target_claim", "")), str(relation.get("relation_type", "")))
        for relation in candidate_map.get("relations", [])
        if isinstance(relation, dict)
    }
    relation_index = _next_relation_index(candidate_map.get("relations", []), region.id_prefix)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    repair_dir = artifact_dir / "map_repair_relations"
    for packet in relation_pairs[:8]:
        prompt = _relation_pair_prompt(manifest, region, case_manifest, packet, decision_question=decision_question)
        write_markdown(repair_dir / f"{packet['pair_id']}_prompt.txt", prompt)
        try:
            result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries, response_schema=relation_json_schema(batch=False))
            raw = result.text
        except (RuntimeError, ValueError) as exc:
            rejected.append({"pair_id": packet["pair_id"], "reason": "backend_error", "error": str(exc)})
            continue
        write_markdown(repair_dir / f"{packet['pair_id']}_raw.txt", raw)
        payload = _parse_model_json(raw)
        write_json(repair_dir / f"{packet['pair_id']}_canonical.json", payload or {})
        relation, reason = _normalize_relation_proposal(payload, claim_ids, permitted_types, packet)
        if relation is None:
            rejected.append({"pair_id": packet["pair_id"], "reason": reason, "proposal": payload})
            continue
        semantic_reason = relation_semantic_rejection_reason(relation, packet)
        if semantic_reason:
            rejected.append({"pair_id": packet["pair_id"], "reason": semantic_reason, "proposal": payload})
            continue
        key = (relation["source_claim"], relation["target_claim"], relation["relation_type"])
        if key in seen:
            rejected.append({"pair_id": packet["pair_id"], "reason": "duplicate_relation", "proposal": payload})
            continue
        seen.add(key)
        relation["relation_id"] = f"{region.id_prefix}_r{relation_index:03d}"
        relation["relation_provenance"] = "targeted_map_repair"
        relation_index += 1
        accepted.append(relation)
    return accepted, rejected


def _accepted_repair_info(
    *,
    repo_root: Path,
    manifest_path: str,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    all_chunks: list[Any],
    selected_chunks: list[Any],
    skipped_chunks: list[dict[str, Any]],
    candidate_map: dict[str, Any],
    original_quality: dict[str, Any],
    rejected_claims: list[dict[str, Any]],
    rejected_relations: list[dict[str, Any]],
    artifact_dir: Path,
    decision_question: str | None,
) -> dict[str, Any]:
    canonical_path = artifact_dir / "map_quality_repaired_candidate.json"
    write_json(canonical_path, candidate_map)
    validation_failures = validate_map_candidate(repo_root, manifest_path, region.region_id, canonical_path)
    write_json(artifact_dir / "map_quality_repair_validation.json", {"failures": validation_failures})
    if validation_failures:
        return {"accepted": False, "reason": "validation_failed", "validation_failures": validation_failures, "candidate_path": canonical_path}
    repaired_quality = evaluate_staged_map_quality(
        manifest=manifest,
        region=region,
        case_manifest=case_manifest,
        all_chunks=all_chunks,
        selected_chunks=selected_chunks,
        skipped_chunks=skipped_chunks,
        candidate_map=candidate_map,
        rejected_claims=rejected_claims,
        rejected_relations=rejected_relations,
        decision_question=decision_question,
    )
    write_json(artifact_dir / "map_quality_repaired_report.json", repaired_quality)
    write_markdown(artifact_dir / "MAP_QUALITY_REPAIRED_REPORT.md", _quality_markdown(repaired_quality))
    if not _repair_improves_or_preserves_quality(original_quality, repaired_quality):
        return {"accepted": False, "reason": "quality_not_improved_or_preserved", "quality_report": repaired_quality, "candidate_path": canonical_path}
    return {
        "accepted": True,
        "candidate_map": candidate_map,
        "quality_report": repaired_quality,
        "candidate_path": canonical_path,
        "validation_failures": [],
        "initial_status": original_quality.get("status"),
        "initial_score": original_quality.get("score"),
        "repaired_status": repaired_quality.get("status"),
        "repaired_score": repaired_quality.get("score"),
    }


def _run_whole_map_repair_fallback(
    *,
    repo_root: Path,
    manifest_path: str,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    all_chunks: list[Any],
    selected_chunks: list[Any],
    skipped_chunks: list[dict[str, Any]],
    candidate_map: dict[str, Any],
    quality_report: dict[str, Any],
    rejected_claims: list[dict[str, Any]],
    rejected_relations: list[dict[str, Any]],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifact_dir: Path,
    decision_question: str | None,
) -> dict[str, Any]:
    if quality_report.get("status") == "usable_with_review":
        return {"accepted": False, "reason": "quality_already_usable"}
    prompt = _map_quality_repair_prompt(region, case_manifest, candidate_map, quality_report, decision_question=decision_question)
    prompt_path = artifact_dir / "map_quality_repair_prompt.txt"
    write_markdown(prompt_path, prompt)
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
        raw = result.text
    except (RuntimeError, ValueError) as exc:
        return {"accepted": False, "reason": "backend_error", "error": str(exc), "prompt_path": prompt_path}
    raw_path = artifact_dir / "map_quality_repair_raw.txt"
    write_markdown(raw_path, raw)
    repaired = _parse_model_json(raw)
    if not isinstance(repaired, dict):
        write_json(artifact_dir / "map_quality_repaired_candidate.json", repaired or {})
        return {"accepted": False, "reason": "invalid_json", "prompt_path": prompt_path, "raw_path": raw_path}
    info = _accepted_repair_info(
        repo_root=repo_root,
        manifest_path=manifest_path,
        manifest=manifest,
        region=region,
        case_manifest=case_manifest,
        all_chunks=all_chunks,
        selected_chunks=selected_chunks,
        skipped_chunks=skipped_chunks,
        candidate_map=repaired,
        original_quality=quality_report,
        rejected_claims=rejected_claims,
        rejected_relations=rejected_relations,
        artifact_dir=artifact_dir,
        decision_question=decision_question,
    )
    info["prompt_path"] = prompt_path
    info["raw_path"] = raw_path
    if info.get("accepted"):
        info["reason"] = "accepted"
    return info


def _missing_relation_candidates(claims: list[dict[str, Any]], relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing_pairs = {
        frozenset((str(relation.get("source_claim", "")), str(relation.get("target_claim", ""))))
        for relation in relations
        if isinstance(relation, dict)
    }
    packets = _candidate_relation_pairs(claims, max_pairs=24)
    candidates: list[dict[str, Any]] = []
    for packet in packets:
        pair_key = frozenset((packet["left"]["claim_id"], packet["right"]["claim_id"]))
        if pair_key not in existing_pairs and _repair_pair_priority(packet) >= 2:
            candidates.append(packet)
    if not candidates:
        candidates = _fallback_missing_relation_candidates(claims, existing_pairs)
    return candidates[:8]


def _fallback_missing_relation_candidates(claims: list[dict[str, Any]], existing_pairs: set[frozenset[str]]) -> list[dict[str, Any]]:
    core_claims = [claim for claim in claims if _claim_bucket(claim) == "core" or str(claim.get("role", "")) == "crux"]
    context_claims = [
        claim
        for claim in claims
        if str(claim.get("role", "")) in {"scope_limit", "implementation_constraint", "crux"}
        or _claim_bucket(claim) in {"core", "supporting"}
    ]
    packets: list[dict[str, Any]] = []
    for left in core_claims:
        for right in context_claims:
            if left is right:
                continue
            pair_key = frozenset((str(left.get("claim_id", "")), str(right.get("claim_id", ""))))
            if pair_key in existing_pairs or len(pair_key) < 2:
                continue
            packets.append(
                {
                    "pair_id": f"repair_pair_{len(packets) + 1:03d}",
                    "left": left,
                    "right": right,
                    "candidate_score": 0,
                    "candidate_reason": "critique_isolated_core_claim_fallback",
                    "pair_intent": relation_pair_intent(left, right),
                }
            )
    return packets


def _claim_bucket(claim: dict[str, Any]) -> str:
    audit = claim.get("label_audit") if isinstance(claim.get("label_audit"), dict) else {}
    return str(audit.get("synthesis_bucket", ""))


def _repair_pair_priority(packet: dict[str, Any]) -> int:
    roles = {str(packet[side].get("role", "")) for side in ("left", "right")}
    audit_buckets = {
        str(packet[side].get("label_audit", {}).get("synthesis_bucket", ""))
        for side in ("left", "right")
        if isinstance(packet[side].get("label_audit"), dict)
    }
    score = 0
    if "core" in audit_buckets:
        score += 2
    if roles & {"crux", "scope_limit"} and roles & {"conclusion_support", "crux"}:
        score += 2
    if str(packet.get("pair_intent", {}).get("intent", "")).strip():
        score += 1
    return score


def _quality_findings(quality_report: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    for index, issue in enumerate(quality_report.get("issues", []), start=1):
        findings.append(
            _finding(
                index,
                severity=str(issue.get("severity", "risk")),
                category=f"quality:{issue.get('issue_type', 'unknown')}",
                target_id="map",
                issue=str(issue.get("message", "")),
                recommended_fix="Repair or explicitly mark this issue before accepting the map for synthesis.",
                evidence=issue,
            )
        )
    return findings


def _label_audit_findings(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for claim in claims:
        warnings = _label_warnings(claim)
        if not warnings:
            continue
        findings.append(
            _finding(
                len(findings) + 1,
                severity="risk",
                category="label_audit_warning",
                target_id=str(claim.get("claim_id", "")),
                issue="Audited routing disagrees with or qualifies model-provided labels.",
                recommended_fix="Use audited routing labels for relation selection and synthesis; do not delete the claim.",
                evidence={"warnings": warnings, "label_audit": claim.get("label_audit", {})},
            )
        )
    return findings


def _duplicate_findings(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for pair in near_duplicate_claim_pairs(claims)[:8]:
        left, right = pair[:2]
        score = pair[2] if len(pair) > 2 else None
        findings.append(
            _finding(
                len(findings) + 1,
                severity="risk",
                category="near_duplicate_claim",
                target_id=f"{left}/{right}",
                issue="Near-duplicate claims may dilute relation selection or synthesis.",
                recommended_fix="Treat these as consolidation or distinction candidates before synthesis.",
                evidence={"left": left, "right": right, "score": score},
            )
        )
    return findings


def _isolated_core_claim_findings(claims: list[dict[str, Any]], relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    related_ids = {
        claim_id
        for relation in relations
        for claim_id in (str(relation.get("source_claim", "")), str(relation.get("target_claim", "")))
        if claim_id
    }
    findings = []
    for claim in claims:
        claim_id = str(claim.get("claim_id", ""))
        audit = claim.get("label_audit") if isinstance(claim.get("label_audit"), dict) else {}
        if claim_id in related_ids or audit.get("synthesis_bucket") != "core":
            continue
        findings.append(
            _finding(
                len(findings) + 1,
                severity="risk",
                category="isolated_core_claim",
                target_id=claim_id,
                issue="A core decision claim has no accepted relation edge.",
                recommended_fix="Try targeted relation classification against likely scope, crux, or tension claims.",
                evidence={"claim": claim.get("claim"), "source_id": claim.get("source_id")},
            )
        )
    return findings


def _rejection_findings(rejected_claims: list[dict[str, Any]], rejected_relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if rejected_claims:
        findings.append(_finding(1, severity="note", category="claim_rejections", target_id="claims", issue=f"{len(rejected_claims)} claim proposals were rejected.", recommended_fix="Inspect rejection reasons if source coverage is weak.", evidence={"reason_counts": _reason_counts(rejected_claims)}))
    if rejected_relations:
        findings.append(_finding(2, severity="note", category="relation_rejections", target_id="relations", issue=f"{len(rejected_relations)} relation proposals were rejected.", recommended_fix="Use rejected relation reasons to select targeted repair pairs.", evidence={"reason_counts": _reason_counts(rejected_relations)}))
    return findings


def _finding(index: int, *, severity: str, category: str, target_id: str, issue: str, recommended_fix: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "finding_id": f"map_critique_{index:03d}",
        "severity": severity if severity in {"note", "risk", "fail"} else "risk",
        "category": category,
        "target_id": target_id,
        "issue": issue,
        "recommended_fix": recommended_fix,
        "evidence": evidence,
    }


def _copy_map(candidate_map: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(candidate_map))


def _label_warnings(claim: dict[str, Any]) -> list[str]:
    audit = claim.get("label_audit") if isinstance(claim.get("label_audit"), dict) else {}
    return [str(warning) for warning in audit.get("warnings", [])]


def _reason_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        reason = str(row.get("reason", "unknown"))
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _next_relation_index(relations: Any, id_prefix: str) -> int:
    max_seen = 0
    for relation in relations if isinstance(relations, list) else []:
        relation_id = str(relation.get("relation_id", "")) if isinstance(relation, dict) else ""
        if relation_id.startswith(f"{id_prefix}_r"):
            try:
                max_seen = max(max_seen, int(relation_id.rsplit("_r", 1)[1]))
            except ValueError:
                continue
    return max_seen + 1


def _repair_improves_or_preserves_quality(original: dict[str, Any], repaired: dict[str, Any]) -> bool:
    return _quality_status_rank(str(repaired.get("status", ""))) >= _quality_status_rank(str(original.get("status", ""))) and int(repaired.get("score", 0)) >= int(original.get("score", 0))


def _quality_status_rank(status: str) -> int:
    return {"needs_repair": 0, "review_recommended": 1, "usable_with_review": 2}.get(status, -1)


def summarize_repair_info(repo_root: Path, repair_info: dict[str, Any]) -> dict[str, Any]:
    summary = {key: value for key, value in repair_info.items() if key not in {"candidate_map", "quality_report"}}
    for key, value in list(summary.items()):
        if isinstance(value, Path):
            summary[key] = _relative(repo_root, value)
    return summary
