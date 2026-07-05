from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epistemic_case_mapper.classical_ml import tfidf_near_duplicate_pairs
from epistemic_case_mapper.config_profiles import (
    EpistemicConfigProfile,
    config_profile_from_manifest_payload,
    profile_vocabulary,
)
from epistemic_case_mapper.io import read_yaml, write_json, write_markdown
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.prompt_templates import examples_block, json_schema_block, render_prompt, xml_block
from epistemic_case_mapper.schema import CaseManifest, Source
from epistemic_case_mapper.semantic_pipeline import MAP_PROMPT_VERSION, VALID_ENTAILMENT, validate_map_candidate
from epistemic_case_mapper.staged_semantic_prompt_schemas import relation_json_schema
from epistemic_case_mapper.submission_manifest import SubmissionManifest, WorkedRegion, load_submission_manifest

def _classify_singleton_relations(
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    batch: list[dict[str, Any]],
    claim_ids: set[str],
    permitted_types: set[str],
    seen: set[tuple[str, str, str]],
    relation_index: int,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifact_dir: Path,
    batch_id: str,
    batch_error: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int]:
    accepted: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = [
        {
            "batch_id": batch_id,
            "reason": "batch_failed_used_singleton_fallback",
            "error": batch_error,
            "pair_ids": [packet["pair_id"] for packet in batch],
        }
    ]
    for packet in batch:
        prompt = _relation_pair_prompt(manifest, region, case_manifest, packet)
        write_markdown(artifact_dir / "relation_pairs" / f"{packet['pair_id']}_prompt.txt", prompt)
        try:
            result = run_model_backend(
                prompt,
                backend,
                timeout_seconds=backend_timeout,
                max_retries=backend_retries,
                response_schema=relation_json_schema(batch=False),
            )
            raw = result.text
        except (RuntimeError, ValueError) as exc:
            rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": "backend_error", "error": str(exc)})
            continue
        write_markdown(artifact_dir / "relation_pairs" / f"{packet['pair_id']}_raw.txt", raw)
        payload = _parse_model_json(raw)
        write_json(artifact_dir / "relation_pairs" / f"{packet['pair_id']}_canonical.json", payload or {})
        if not isinstance(payload, dict):
            rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": "invalid_json"})
            continue
        payloads.append(payload)
        proposals = _relation_proposals(payload)
        if not proposals:
            rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": "missing_relation_proposal"})
            continue
        for proposal in proposals:
            relation, reason = _normalize_relation_proposal(proposal, claim_ids, permitted_types, packet)
            if relation is None:
                rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": reason, "proposal": proposal})
                continue
            key = (relation["source_claim"], relation["target_claim"], relation["relation_type"])
            if key in seen:
                rejected.append({"pair_id": packet["pair_id"], "batch_id": batch_id, "reason": "duplicate_relation", "proposal": proposal})
                continue
            seen.add(key)
            relation["relation_id"] = f"{region.id_prefix}_r{relation_index:03d}"
            relation_index += 1
            accepted.append(relation)
            break
    return accepted, payloads, rejected, relation_index

def _sharpen_relations(
    relations: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    permitted_types: set[str],
) -> list[dict[str, Any]]:
    claim_lookup = {str(claim.get("claim_id")): claim for claim in claims}
    sharpened: list[dict[str, Any]] = []
    for relation in relations:
        updated = dict(relation)
        original_type = str(updated.get("relation_type", ""))
        sharper_type = _sharper_relation_type(updated, claim_lookup, permitted_types)
        if sharper_type and sharper_type != original_type:
            updated["relation_type"] = sharper_type
            updated["rationale"] = _append_sharpening_note(
                str(updated.get("rationale", "")),
                original_type,
                sharper_type,
            )
            updated["deterministic_sharpening"] = {
                "from": original_type,
                "to": sharper_type,
                "method": "claim_role_and_rationale_rules_v1",
            }
        sharpened.append(updated)
    return sharpened

def _sharper_relation_type(
    relation: dict[str, Any],
    claim_lookup: dict[str, dict[str, Any]],
    permitted_types: set[str],
) -> str | None:
    current = str(relation.get("relation_type", ""))
    if current not in {"similar_to", "refines", "supports"}:
        return current
    source = claim_lookup.get(str(relation.get("source_claim")), {})
    target = claim_lookup.get(str(relation.get("target_claim")), {})
    source_role = str(source.get("role", ""))
    target_role = str(target.get("role", ""))
    rationale = str(relation.get("rationale", "")).lower()
    claim_text = " ".join((str(source.get("claim", "")), str(target.get("claim", "")))).lower()
    combined = f"{rationale} {claim_text}"
    if "depends_on" in permitted_types and (
        source_role == "implementation_constraint"
        or target_role == "implementation_constraint"
        or any(marker in combined for marker in ("requires", "only when", "if ", "unless", "depends", "must", "condition", "contingent", "when other", "where "))
    ):
        return "depends_on"
    if "in_tension_with" in permitted_types and any(
        marker in combined
        for marker in (
            "however",
            "unclear",
            "unproven",
            "cannot",
            "does not",
            "do not",
            "limitation",
            "small reductions",
            "not a solution",
            "not replace",
            "rather than",
            "scope limit",
            "tension",
        )
    ):
        return "in_tension_with"
    if "crux_for" in permitted_types and (
        source_role == "crux"
        or target_role == "crux"
        or any(marker in combined for marker in ("crux", "determines", "would change", "changes whether", "changes how", "turns on"))
    ):
        return "crux_for"
    if "challenges" in permitted_types and any(marker in combined for marker in ("contradicts", "undercuts", "weakens", "casts doubt")):
        return "challenges"
    return current

def _append_sharpening_note(rationale: str, original_type: str, sharper_type: str) -> str:
    base = rationale.strip()
    if not base:
        return f"Retagged from {original_type} to {sharper_type} because claim roles/rationale make the edge decision-relevant."
    return base

def _relation_sharpening_summary(relations: list[dict[str, Any]]) -> dict[str, Any]:
    changed = [
        {
            "relation_id": relation.get("relation_id"),
            "from": relation.get("deterministic_sharpening", {}).get("from"),
            "to": relation.get("deterministic_sharpening", {}).get("to"),
        }
        for relation in relations
        if isinstance(relation.get("deterministic_sharpening"), dict)
    ]
    return {"changed_count": len(changed), "changed": changed}

def _assemble_map(
    region: WorkedRegion,
    case_manifest: CaseManifest,
    claims: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    relation_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    cruxes = _payload_list_items(relation_payloads, "crux_candidates")
    if not cruxes and relations:
        cruxes = [
            f"{relations[0]['source_claim']} {relations[0]['relation_type']} {relations[0]['target_claim']} is a candidate crux for the question."
        ]
    distinctions = _payload_list_items(relation_payloads, "similar_but_not_identical")
    evidence_rows = [
        [
            f"Does {claim['claim_id']} quote exact source text?",
            "Survives",
            f"{claim['source_id']} {claim['source_span']}: {claim['excerpt']}",
        ]
        for claim in claims[: max(1, region.thresholds.min_evidence_rows)]
    ]
    return {
        "title": f"{case_manifest.title} Staged Map",
        "status": "human-review-needed",
        "prompt_procedure": MAP_PROMPT_VERSION,
        "pipeline": "staged_chunked_mapper_v1",
        "epistemic_config": {
            "profile_id": _case_config_profile(case_manifest).profile_id,
            "source": case_manifest.epistemic_config.get("source", "default_profile")
            if isinstance(case_manifest.epistemic_config, dict)
            else "default_profile",
        },
        "evidence_mode": "source_grounded",
        "sources": [source.source_id for source in _required_sources(case_manifest, region)],
        "claims": claims,
        "relations": relations,
        "crux_candidates": cruxes,
        "similar_but_not_identical": distinctions,
        "evidence_check": evidence_rows,
    }

def evaluate_staged_map_quality(
    *,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    all_chunks: list[SourceChunk],
    selected_chunks: list[SourceChunk],
    skipped_chunks: list[dict[str, Any]],
    candidate_map: dict[str, Any],
    rejected_claims: list[dict[str, Any]],
    rejected_relations: list[dict[str, Any]],
) -> dict[str, Any]:
    claims = [claim for claim in candidate_map.get("claims", []) if isinstance(claim, dict)]
    relations = [relation for relation in candidate_map.get("relations", []) if isinstance(relation, dict)]
    required_sources = [source.source_id for source in _required_sources(case_manifest, region)]
    source_claim_counts = {
        source_id: sum(1 for claim in claims if source_id in _claim_source_coverage_ids(claim))
        for source_id in required_sources
    }
    backfilled_claim_count = sum(
        1
        for claim in claims
        if str(claim.get("extraction_method", "")) == "deterministic_coverage_backfill"
    )
    consolidated_claim_count = sum(1 for claim in claims if claim.get("supporting_claim_ids"))
    role_counts = _counts(str(claim.get("role", "other")) for claim in claims)
    relation_type_counts = _counts(str(relation.get("relation_type", "")) for relation in relations)
    relation_confidence_counts = _counts(str(relation.get("relation_confidence", "unknown")) for relation in relations)
    relation_contract_count = sum(1 for relation in relations if _relation_has_contract(relation))
    fallback_relation_count = sum(1 for relation in relations if relation.get("relation_provenance") == "deterministic_fallback")
    issues = _quality_issues(
        manifest=manifest,
        region=region,
        required_sources=required_sources,
        claims=claims,
        relations=relations,
        source_claim_counts=source_claim_counts,
        role_counts=role_counts,
        relation_type_counts=relation_type_counts,
        relation_confidence_counts=relation_confidence_counts,
        relation_contract_count=relation_contract_count,
        fallback_relation_count=fallback_relation_count,
        rejected_claims=rejected_claims,
        rejected_relations=rejected_relations,
        skipped_chunks=skipped_chunks,
    )
    score = _quality_score(issues)
    status = _quality_status(issues, score)
    return {
        "schema_id": "staged_map_quality_report_v1",
        "status": status,
        "score": score,
        "summary": {
            "claim_count": len(claims),
            "relation_count": len(relations),
            "relation_type_count": len([key for key in relation_type_counts if key]),
            "relation_contract_count": relation_contract_count,
            "fallback_relation_count": fallback_relation_count,
            "required_source_count": len(required_sources),
            "sources_with_claims": sum(1 for count in source_claim_counts.values() if count > 0),
            "all_chunk_count": len(all_chunks),
            "selected_chunk_count": len(selected_chunks),
            "skipped_chunk_count": len(skipped_chunks),
            "coverage_backfilled_claim_count": backfilled_claim_count,
            "consolidated_claim_count": consolidated_claim_count,
            "rejected_claim_count": len(rejected_claims),
            "rejected_relation_count": len(rejected_relations),
        },
        "source_claim_counts": source_claim_counts,
        "claim_role_counts": role_counts,
        "relation_type_counts": relation_type_counts,
        "relation_confidence_counts": relation_confidence_counts,
        "issues": issues,
        "scaffold": _map_quality_scaffold(manifest, region, case_manifest),
    }


def _relation_quality_issues(
    *,
    region: WorkedRegion,
    claim_count: int,
    relations: list[dict[str, Any]],
    relation_type_counts: dict[str, int],
    relation_confidence_counts: dict[str, int],
    relation_contract_count: int,
    fallback_relation_count: int,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if claim_count >= 2 and not relations:
        issues.append(_quality_issue("fail", "missing_relations", "At least two claims exist but no accepted relations were produced."))
    if relations and relation_contract_count < len(relations):
        missing_count = len(relations) - relation_contract_count
        issues.append(
            _quality_issue(
                "risk",
                "missing_relation_contracts",
                f"{missing_count} accepted relation(s) lack source anchors, decision relevance, or failure conditions.",
            )
        )
    if relations and relation_confidence_counts.get("low", 0) / len(relations) > 0.5:
        issues.append(
            _quality_issue(
                "risk",
                "low_confidence_relation_ratio",
                "More than half of accepted relations are low confidence and should be treated as review candidates.",
            )
        )
    if fallback_relation_count:
        issues.append(
            _quality_issue(
                "risk",
                "fallback_relation_needs_review",
                f"{fallback_relation_count} accepted relation(s) came from deterministic fallback rather than model classification.",
            )
        )
    issues.extend(_relation_rationale_and_type_issues(region, relations, relation_type_counts))
    return issues


def _relation_rationale_and_type_issues(
    region: WorkedRegion,
    relations: list[dict[str, Any]],
    relation_type_counts: dict[str, int],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    weak_relation_ids = _weak_relation_rationale_ids(relations)
    if weak_relation_ids:
        issues.append(
            _quality_issue(
                "risk",
                "weak_relation_rationales",
                "Relations with vague or low-information rationales: " + ", ".join(weak_relation_ids[:8]),
            )
        )
    if len(relation_type_counts) < region.thresholds.min_relation_types:
        issues.append(
            _quality_issue(
                "risk",
                "low_relation_type_diversity",
                f"Accepted {len(relation_type_counts)} relation types; region target is at least {region.thresholds.min_relation_types}.",
            )
        )
    relation_types = set(relation_type_counts)
    if relation_types.isdisjoint({"crux_for", "in_tension_with", "challenges"}):
        issues.append(_quality_issue("risk", "missing_crux_or_tension_relation", "No accepted crux/tension/challenge relation."))
    generic_relation_count = sum(relation_type_counts.get(kind, 0) for kind in ("similar_to", "refines", "supports"))
    if relations and len(relations) >= 4 and generic_relation_count / len(relations) > 0.7:
        issues.append(
            _quality_issue(
                "risk",
                "generic_relation_type_overuse",
                "Most accepted relations use generic supports/refines/similar_to types rather than crux, tension, challenge, or dependency edges.",
            )
        )
    return issues

def _quality_issues(
    *,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    required_sources: list[str],
    claims: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    source_claim_counts: dict[str, int],
    role_counts: dict[str, int],
    relation_type_counts: dict[str, int],
    relation_confidence_counts: dict[str, int],
    relation_contract_count: int,
    fallback_relation_count: int,
    rejected_claims: list[dict[str, Any]],
    rejected_relations: list[dict[str, Any]],
    skipped_chunks: list[dict[str, Any]],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not claims:
        issues.append(_quality_issue("fail", "missing_claims", "No accepted claims were produced."))
    if len(claims) < region.thresholds.min_claims:
        issues.append(
            _quality_issue(
                "risk",
                "low_claim_count",
                f"Accepted {len(claims)} claims; region target is at least {region.thresholds.min_claims}.",
            )
        )
    if len(claims) > region.thresholds.max_claims:
        issues.append(
            _quality_issue(
                "risk",
                "high_claim_count",
                f"Accepted {len(claims)} claims; region target is at most {region.thresholds.max_claims}.",
            )
        )
    missing_source_ids = [source_id for source_id, count in source_claim_counts.items() if count == 0]
    for source_id in missing_source_ids:
        issues.append(_quality_issue("fail", "missing_source_claim_coverage", f"No accepted claim from required source {source_id}."))
    uncertain_claims = [
        claim.get("claim_id", "")
        for claim in claims
        if str(claim.get("entailed_by_excerpt", "")) != "yes"
    ]
    if uncertain_claims:
        issues.append(
            _quality_issue(
                "risk",
                "uncertain_claim_entailment",
                "Claims not marked entailed by excerpt: " + ", ".join(str(item) for item in uncertain_claims[:8]),
            )
        )
    for role in ("conclusion_support", "crux", "scope_limit"):
        if role_counts.get(role, 0) == 0:
            issues.append(_quality_issue("risk", "missing_claim_role", f"No accepted claim with role {role}."))
    issues.extend(
        _relation_quality_issues(
            region=region,
            claim_count=len(claims),
            relations=relations,
            relation_type_counts=relation_type_counts,
            relation_confidence_counts=relation_confidence_counts,
            relation_contract_count=relation_contract_count,
            fallback_relation_count=fallback_relation_count,
        )
    )
    duplicate_pairs = _near_duplicate_claim_pairs(claims)
    if duplicate_pairs:
        issues.append(
            _quality_issue(
                "risk",
                "near_duplicate_claims",
                "Near-duplicate claim pairs: " + ", ".join(f"{left}/{right}" for left, right in duplicate_pairs[:6]),
            )
        )
    permitted_types = manifest.relation_ontology.permitted_types()
    unsupported_relation_types = sorted(set(relation_type_counts) - permitted_types)
    for relation_type in unsupported_relation_types:
        issues.append(_quality_issue("fail", "unsupported_relation_type", f"Relation type is not in ontology: {relation_type}."))
    if rejected_claims and len(rejected_claims) > len(claims):
        issues.append(
            _quality_issue(
                "risk",
                "high_rejected_claim_ratio",
                f"Rejected {len(rejected_claims)} claim proposals vs. {len(claims)} accepted claims.",
            )
        )
    if rejected_relations and len(rejected_relations) > max(1, len(relations) * 2):
        issues.append(
            _quality_issue(
                "note",
                "high_rejected_relation_ratio",
                f"Rejected {len(rejected_relations)} relation proposals vs. {len(relations)} accepted relations.",
            )
        )
    if skipped_chunks:
        backfilled_claim_count = sum(
            1
            for claim in claims
            if str(claim.get("extraction_method", "")) == "deterministic_coverage_backfill"
        )
        if backfilled_claim_count:
            issues.append(
                _quality_issue(
                    "note",
                    "chunk_budget_backfilled_content",
                    f"Skipped {len(skipped_chunks)} source chunks due to configured chunk budgets; added {backfilled_claim_count} deterministic coverage claims.",
                )
            )
            return issues
        issues.append(
            _quality_issue(
                "note",
                "chunk_budget_skipped_content",
                f"Skipped {len(skipped_chunks)} source chunks due to configured chunk budgets.",
            )
        )
    return issues

def _quality_issue(severity: str, issue_type: str, message: str) -> dict[str, str]:
    return {"severity": severity, "issue_type": issue_type, "message": message}

def _claim_source_coverage_ids(claim: dict[str, Any]) -> set[str]:
    source_ids = {str(claim.get("source_id", ""))}
    for source_id in claim.get("supporting_sources", []):
        if isinstance(source_id, str):
            source_ids.add(source_id)
    return {source_id for source_id in source_ids if source_id}

def _weak_relation_rationale_ids(relations: list[dict[str, Any]]) -> list[str]:
    weak_ids: list[str] = []
    vague_patterns = (
        "are related",
        "is related",
        "should be read together",
        "provide context",
        "adds context",
        "similar points",
        "same topic",
        "both discuss",
    )
    for relation in relations:
        rationale = str(relation.get("rationale", "")).strip()
        normalized = re.sub(r"\s+", " ", rationale.lower())
        terms = _content_terms(normalized)
        if len(terms) < 4 or any(pattern in normalized for pattern in vague_patterns):
            weak_ids.append(str(relation.get("relation_id", "")) or "<missing_id>")
    return weak_ids

def _relation_has_contract(relation: dict[str, Any]) -> bool:
    contract = relation.get("relation_contract")
    if not isinstance(contract, dict):
        return False
    required = ("edge_basis", "source_anchor_a", "source_anchor_b", "why_decision_relevant", "failure_condition")
    return all(str(contract.get(key, "")).strip() for key in required)

def _quality_score(issues: list[dict[str, str]]) -> int:
    score = 100
    for issue in issues:
        severity = issue.get("severity")
        if severity == "fail":
            score -= 25
        elif severity == "risk":
            score -= 10
        elif severity == "note":
            score -= 2
    return max(0, score)

def _quality_status(issues: list[dict[str, str]], score: int) -> str:
    if any(issue.get("severity") == "fail" for issue in issues):
        return "needs_repair"
    if score < 75:
        return "review_recommended"
    return "usable_with_review"

def _quality_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Staged Map Quality Report",
        "",
        f"Status: `{report['status']}`",
        f"Score: `{report['score']}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Issues", ""])
    issues = report.get("issues", [])
    if issues:
        lines.extend(
            f"- `{issue['severity']}` `{issue['issue_type']}`: {issue['message']}"
            for issue in issues
        )
    else:
        lines.append("- No deterministic map-quality issues detected.")
    lines.extend(["", "## Scaffold", "", "```json", json.dumps(report.get("scaffold", {}), indent=2), "```", ""])
    return "\n".join(lines)

def _map_quality_repair_prompt(
    region: WorkedRegion,
    case_manifest: CaseManifest,
    candidate_map: dict[str, Any],
    quality_report: dict[str, Any],
) -> str:
    return "\n\n".join(
        (
            "You are repairing a source-grounded epistemic case-map candidate.",
            f"Region ID: {region.region_id}",
            f"Case question: {case_manifest.question}",
            "Return only JSON in the same map shape as the candidate.",
            "Repair rules:",
            "- Preserve accepted claims and relations that remain source-grounded.",
            "- Address fail/risk issues in the deterministic quality report before adding polish.",
            "- Add claims only when they are supported by exact excerpts already present in the candidate or staged artifacts.",
            "- Do not invent source IDs, claim IDs, relation IDs, source spans, excerpts, effect sizes, or consensus.",
            "- If a quality issue cannot be fixed from available artifacts, add an evidence_check row naming the missing source or review need.",
            "- Keep relation types within the allowed relation ontology listed in the scaffold.",
            "Deterministic quality report:\n" + json.dumps(quality_report, indent=2),
            "Candidate map:\n" + json.dumps(candidate_map, indent=2),
        )
    )

def _counts(items: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if not item:
            continue
        counts[str(item)] = counts.get(str(item), 0) + 1
    return counts

def _near_duplicate_claim_pairs(claims: list[dict[str, Any]]) -> list[tuple[str, str]]:
    ids = [str(claim.get("claim_id", "")) for claim in claims]
    texts = [str(claim.get("claim", "") or claim.get("text", "")) for claim in claims]
    pair_scores = {
        (left, right): score
        for left, right, score in tfidf_near_duplicate_pairs(texts, ids, threshold=0.35)
        if left and right
    }
    for left_index, left in enumerate(claims):
        for right in claims[left_index + 1 :]:
            pair = (str(left.get("claim_id", "")), str(right.get("claim_id", "")))
            if _text_overlap_ratio(str(left.get("claim", "")), str(right.get("claim", ""))) >= 0.78:
                pair_scores.setdefault(pair, 1.0)
    return list(pair_scores)

def _case_config_profile(case_manifest: CaseManifest) -> EpistemicConfigProfile:
    return config_profile_from_manifest_payload(case_manifest.epistemic_config)

def _configured_claim_roles(case_manifest: CaseManifest) -> list[str]:
    roles = _case_config_profile(case_manifest).claim_role_ids()
    if "other" not in roles:
        roles.append("other")
    return roles

def _profile_relation_rule_text(case_manifest: CaseManifest) -> str:
    rules = _case_config_profile(case_manifest).relation_prompt_rules
    return "\n".join(f"- Profile guidance: {rule}" for rule in rules)

def _text_overlap_ratio(left: str, right: str) -> float:
    left_terms = _content_terms(left)
    right_terms = _content_terms(right)
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / min(len(left_terms), len(right_terms))

def _map_quality_scaffold(
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    chunk: SourceChunk | None = None,
) -> dict[str, Any]:
    required_sources = _required_sources(case_manifest, region)
    profile = _case_config_profile(case_manifest)
    source_roles = {
        source.source_id: _source_role_scaffold(source)
        for source in required_sources
    }
    scaffold: dict[str, Any] = {
        "case_question": case_manifest.question,
        "epistemic_config_profile": {
            "profile_id": profile.profile_id,
            "label": profile.label,
            "description": profile.description,
        },
        "required_sources": [source.source_id for source in required_sources],
        "source_roles": source_roles,
        "source_role_taxonomy": [
            {
                "role_id": role.role_id,
                "description": role.description,
                "keyword_markers": role.keyword_markers,
                "limitations": role.limitations,
            }
            for role in profile.source_roles
        ],
        "target_claim_roles": [
            {"role_id": role.role_id, "description": role.description, "use_when": role.use_when}
            for role in profile.claim_roles
        ],
        "relation_goals": profile.relation_prompt_rules + [
            "connect at least one crux/scope-limit claim to a conclusion-support claim",
            "preserve tensions instead of flattening them",
            "use source limitations to bound claim strength",
            "prefer cross-source relations when they clarify disagreement or scope",
        ],
        "profile_evidence_sections": [
            {
                "section_id": section.section_id,
                "title": section.title,
                "description": section.description,
                "claim_roles": section.claim_roles,
                "relation_types": section.relation_types,
            }
            for section in profile.evidence_sections
        ],
        "profile_relation_types": [
            {
                "relation_type": relation.relation_type,
                "description": relation.description,
                "use_when": relation.use_when,
                "sharpness_markers": relation.sharpness_markers,
            }
            for relation in profile.relation_types
        ],
        "allowed_relation_types": sorted(manifest.relation_ontology.permitted_types()),
        "quality_checks": [
            "every required source should contribute at least one useful claim unless genuinely irrelevant",
            "claims must be entailed by exact excerpts",
            "relations must use only accepted claim IDs and ontology relation types",
            "the final map should expose cruxes, scope limits, and source-role boundaries",
            "near-duplicate claims should be merged or given distinct roles",
        ],
    }
    if chunk is not None:
        scaffold["current_chunk"] = {
            "chunk_id": chunk.chunk_id,
            "source_id": chunk.source_id,
            "line_range": f"{chunk.start_line}-{chunk.end_line}",
            "source_role": source_roles.get(chunk.source_id, {}),
        }
    return scaffold

def _source_role_scaffold(source: Source) -> dict[str, Any]:
    inferred_role, inferred_provenance, inferred_limitations = _infer_source_role(source)
    evidence_role = source.evidence_role if source.evidence_role != "unspecified" else inferred_role
    provenance_level = source.provenance_level if source.provenance_level != "unspecified" else inferred_provenance
    limitations = list(source.limitations)
    for limitation in inferred_limitations:
        if limitation not in limitations:
            limitations.append(limitation)
    return {
        "display_title": source.title,
        "evidence_role": evidence_role,
        "provenance_level": provenance_level,
        "limitations": limitations,
        "needs_upgrade": source.needs_upgrade or source.provenance_level == "unspecified",
        "inferred": source.evidence_role == "unspecified" or source.provenance_level == "unspecified",
    }

def _infer_source_role(source: Source) -> tuple[str, str, list[str]]:
    text = " ".join(
        str(part or "")
        for part in (source.source_id, source.title, source.source_type, source.notes, source.path, source.url)
    ).lower()
    if any(token in text for token in ("randomized", "rct", "trial", "cohort", "case-control", "study")):
        return "empirical study", "peer_reviewed", ["Check population, endpoint, and design limits before treating as direct decision evidence."]
    if any(token in text for token in ("meta-analysis", "systematic review", "scoping review", "review")):
        return "evidence synthesis", "secondary_summary", ["Review conclusions depend on included-study quality and inclusion criteria."]
    if any(token in text for token in ("guideline", "advisory", "recommendation", "official", "cdc", "who")):
        return "policy or guidance", "official_guidance", ["Guidance may combine evidence with policy judgment and may lag new evidence."]
    if any(token in text for token in ("forecast", "prediction", "good judgment")):
        return "forecasting aggregate", "secondary_summary", ["Forecasts summarize expectations, not direct causal evidence."]
    if any(token in text for token in ("brief", "blog", "comment", "acx", "rootclaim", "analysis")):
        return "commentary or case analysis", "secondary_summary", ["Use for framing and argument structure; verify factual claims against primary sources."]
    if any(token in text for token in ("working paper", "preprint", "nber", "ssrn")):
        return "working paper or preprint", "preprint", ["Treat as not fully peer-reviewed unless separately verified."]
    return "source document", "unspecified", ["Source role was inferred from sparse metadata and needs human review."]

def _payload_list_items(payloads: list[dict[str, Any]], key: str) -> list[str]:
    items: list[str] = []
    for payload in payloads:
        direct = payload.get(key, [])
        if isinstance(direct, list):
            items.extend(str(item) for item in direct)
        for proposal in _relation_proposals(payload):
            nested = proposal.get(key, [])
            if isinstance(nested, list):
                items.extend(str(item) for item in nested)
    return items

def _claim_prompt(
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    chunk: SourceChunk,
    max_claims: int,
) -> str:
    span_catalog = "\n".join(
        f"- span_id: {span.span_id}\n  source_span: {span.source_span}\n  text: {span.text}"
        for span in chunk.spans
    )
    scaffold = json.dumps(_map_quality_scaffold(manifest, region, case_manifest, chunk), indent=2)
    role_options = "|".join(_configured_claim_roles(case_manifest))
    return render_prompt(
        ("Task", "You are selecting source-grounded claim candidates from one bounded source-span catalog."),
        (
            "Metadata",
            f"Prompt version: {CLAIM_EXTRACTION_PROMPT_VERSION}\nRegion ID: {region.region_id}\nCase question: {case_manifest.question}\nSource ID: {chunk.source_id}\nSource title: {chunk.title}\nLine range: {chunk.start_line}-{chunk.end_line}",
        ),
        (
            "Rules",
            [
                f"- Return at most {max_claims} claims.",
                "- Do not include claim_id. Deterministic code assigns IDs later.",
                "- Do not include source_id, source_span, or excerpt. Deterministic code derives them from span_id.",
                "- Use only span IDs shown in the catalog.",
                "- Prefer claims that affect the case question, not bibliographic metadata.",
                "- Use the map-quality scaffold to diversify claim roles and preserve source limitations.",
                "- If a source limitation changes the answer, use the sharpest configured role available.",
                '- If the chunk has no useful claim, return {"claims": []}.',
            ],
        ),
        ("Output Schema", json_schema_block(_claim_prompt_schema(role_options))),
        ("Examples", examples_block(_claim_prompt_examples())),
        (
            "Context",
            "\n\n".join(
                (
                    xml_block("source_span_catalog", span_catalog),
                    xml_block("deterministic_map_quality_scaffold", f"Deterministic map-quality scaffold:\n{scaffold}"),
                )
            ),
        ),
    )


def _claim_prompt_schema(role_options: str) -> dict[str, Any]:
    return {
        "claims": [
            {
                "claim": "one concise claim supported by the excerpt",
                "span_id": "one span_id from the catalog",
                "entailed_by_excerpt": "yes|no|uncertain",
                "role": role_options,
            }
        ]
    }


def _claim_prompt_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string"},
                        "span_id": {"type": "string"},
                        "entailed_by_excerpt": {"type": "string", "enum": ["yes", "no", "uncertain"]},
                        "role": {"type": "string"},
                    },
                    "required": ["claim", "span_id", "entailed_by_excerpt", "role"],
                },
            }
        },
        "required": ["claims"],
    }


def _claim_prompt_examples() -> list[dict[str, Any]]:
    return [
        {
            "input_hint": "Span states an outcome relevant to the case question.",
            "output": {"claims": [{"claim": "The program reduced processing time for the target cases.", "span_id": "doc_s0001", "entailed_by_excerpt": "yes", "role": "conclusion_support"}]},
        },
        {
            "input_hint": "Span only gives title, author, or background metadata.",
            "output": {"claims": []},
        },
    ]



# Explicit cross-module dependencies for compatibility facade removal.
from epistemic_case_mapper.staged_semantic_pipeline_runner import CLAIM_EXTRACTION_PROMPT_VERSION, SourceChunk
from epistemic_case_mapper.staged_semantic_sources import (
    _content_terms,
    _normalize_relation_proposal,
    _parse_model_json,
    _relation_pair_prompt,
    _relation_proposals,
    _required_sources,
)
