from __future__ import annotations

import json
import re
from typing import Any


def normalized_critique_issues(critique: dict[str, Any], packet: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    deterministic = deterministic_packet_quality_issues(packet)
    challenge_issues = _issues_from_challenges(critique)
    return {
        "answer_frame_issues": dedupe_issue_rows(
            [
                *_list_of_dicts(critique.get("answer_frame_issues")),
                *_list_of_dicts(critique.get("answer_frame_challenges")),
                *challenge_issues["answer_frame_issues"],
                *deterministic["answer_frame_issues"],
            ],
            key_fields=("component", "critique", "risk", "issue"),
        )[:16],
        "misleading_synthesis_risks": dedupe_issue_rows(
            [
                *_risk_rows(critique.get("misleading_synthesis_risks")),
                *_risk_rows(critique.get("misleading_risks")),
                *challenge_issues["misleading_synthesis_risks"],
                *deterministic["misleading_synthesis_risks"],
            ],
            key_fields=("type", "risk", "description", "bundle_id"),
        )[:16],
        "insufficiency_warnings": dedupe_issue_rows(
            [
                *_list_of_dicts(critique.get("insufficiency_warnings")),
                *deterministic["insufficiency_warnings"],
            ],
            key_fields=("bundle_id", "source_id", "reason", "warning"),
        )[:16],
        "claim_quality_issues": dedupe_issue_rows(
            [
                *_list_of_dicts(critique.get("claim_quality_issues")),
                *deterministic["claim_quality_issues"],
            ],
            key_fields=("bundle_id", "claim", "issue"),
        )[:16],
        "section_routing_issues": dedupe_issue_rows(
            [
                *_list_of_dicts(critique.get("section_routing_issues")),
                *deterministic["section_routing_issues"],
            ],
            key_fields=("bundle_id", "section", "current_bucket", "issue"),
        )[:16],
    }


def dedupe_issue_rows(rows: list[dict[str, Any]], *, key_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key_values = [str(row.get(field, "")).strip().lower() for field in key_fields if str(row.get(field, "")).strip()]
        key = "|".join(key_values) or json.dumps(row, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def deterministic_packet_quality_issues(packet: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    bundles = [bundle for bundle in packet.get("evidence_bundles", []) if isinstance(bundle, dict)]
    bundle_lookup = {str(bundle.get("bundle_id")): bundle for bundle in bundles if str(bundle.get("bundle_id", "")).strip()}
    claim_quality_issues = _deterministic_claim_quality_issues(bundles)
    section_routing_issues = _deterministic_section_routing_issues(packet, bundle_lookup)
    answer_frame_issues = _deterministic_answer_frame_issues(packet)
    insufficiency_warnings = [
        {
            "bundle_id": issue.get("bundle_id", ""),
            "reason": issue.get("issue", ""),
            "warning": issue.get("why_it_matters", ""),
            "recommended_action": issue.get("recommended_action", ""),
            "source": "deterministic_claim_quality_scan",
        }
        for issue in claim_quality_issues
        if issue.get("severity") == "high"
    ]
    synthesis_risks = [
        {
            "type": "section_routing_issue",
            "description": issue.get("issue", ""),
            "affected_bundle_ids": _string_list(issue.get("bundle_id")),
            "affected_sections": _string_list(issue.get("section")),
            "impact_level": "medium",
            "recommended_action": issue.get("recommended_action", ""),
            "source": "deterministic_section_routing_scan",
        }
        for issue in section_routing_issues
    ]
    synthesis_risks.extend(
        {
            "type": "claim_quality_issue",
            "description": issue.get("issue", ""),
            "affected_bundle_ids": _string_list(issue.get("bundle_id")),
            "impact_level": issue.get("severity", "medium"),
            "recommended_action": issue.get("recommended_action", ""),
            "source": "deterministic_claim_quality_scan",
        }
        for issue in claim_quality_issues
    )
    synthesis_risks.extend(
        {
            "type": "answer_frame_issue",
            "description": issue.get("critique", ""),
            "impact_level": "medium",
            "recommended_action": issue.get("recommended_action", ""),
            "source": "deterministic_answer_frame_scan",
        }
        for issue in answer_frame_issues
    )
    return {
        "answer_frame_issues": answer_frame_issues,
        "misleading_synthesis_risks": synthesis_risks,
        "insufficiency_warnings": insufficiency_warnings,
        "claim_quality_issues": claim_quality_issues,
        "section_routing_issues": section_routing_issues,
    }


def _issues_from_challenges(critique: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    challenges = critique.get("challenges")
    if not isinstance(challenges, dict):
        return {"answer_frame_issues": [], "misleading_synthesis_risks": []}
    answer_frame_issues: list[dict[str, Any]] = []
    synthesis_risks: list[dict[str, Any]] = []
    for component, value in challenges.items():
        if not isinstance(value, dict):
            continue
        status = str(value.get("status", "")).lower()
        comment = str(value.get("comment") or value.get("critique") or value.get("description") or "").strip()
        if not comment or status not in {"challenge", "needs_repair", "warning", "warn"}:
            continue
        if component == "answer_frame":
            answer_frame_issues.append(
                {
                    "component": component,
                    "critique": comment,
                    "recommended_action": str(value.get("recommended_action", "")).strip(),
                    "source": "model_challenges",
                }
            )
        else:
            synthesis_risks.append(
                {
                    "type": component,
                    "description": comment,
                    "impact_level": str(value.get("impact_level") or "medium"),
                    "source": "model_challenges",
                }
            )
    return {"answer_frame_issues": answer_frame_issues, "misleading_synthesis_risks": synthesis_risks}


def _deterministic_claim_quality_issues(bundles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for bundle in bundles:
        bundle_id = str(bundle.get("bundle_id", "")).strip()
        claim = str(bundle.get("claim", "")).strip()
        lowered = claim.lower()
        issue = ""
        severity = "medium"
        if not claim:
            issue = "Empty claim text cannot support synthesis."
            severity = "high"
        elif re.fullmatch(r"[\d\s.,%+\-–—/:()]+", claim) or len(claim) <= 4:
            issue = "Claim text is only a quantity or fragment, not an interpretable evidence claim."
            severity = "high"
        elif "appendix-only extraction" in lowered or "low atomicity" in lowered:
            issue = "Claim text contains an extraction-quality marker rather than a decision-ready evidence statement."
            severity = "high"
        elif "hhs vulnerability disclosure" in lowered:
            issue = "Claim text appears to be page chrome or administrative text rather than evidence."
            severity = "high"
        if issue:
            issues.append(
                {
                    "bundle_id": bundle_id,
                    "claim": claim,
                    "issue": issue,
                    "severity": severity,
                    "why_it_matters": "Synthesis may treat a fragment or extraction artifact as substantive evidence.",
                    "recommended_action": "Replace with an anchored source claim or demote to context/insufficiency warning before synthesis.",
                    "source": "deterministic_claim_quality_scan",
                }
            )
    return issues


def _deterministic_section_routing_issues(packet: dict[str, Any], bundle_lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    bucket_roles = {
        "primary_bundle_ids": {"strongest_support", "quantitative_anchor", "decision_crux", "mechanism", "context"},
        "contrast_bundle_ids": {"counterweight"},
        "boundary_bundle_ids": {"scope_boundary"},
        "context_bundle_ids": {"context", "mechanism"},
    }
    expected_bucket = {
        "counterweight": "contrast_bundle_ids",
        "scope_boundary": "boundary_bundle_ids",
        "context": "context_bundle_ids",
        "mechanism": "context_bundle_ids",
        "strongest_support": "primary_bundle_ids",
        "quantitative_anchor": "primary_bundle_ids",
        "decision_crux": "primary_bundle_ids",
    }
    for section in packet.get("section_views", []) if isinstance(packet.get("section_views"), list) else []:
        if not isinstance(section, dict):
            continue
        section_name = str(section.get("section", "")).strip()
        for bucket, allowed_roles in bucket_roles.items():
            for bundle_id in _string_list(section.get(bucket)):
                bundle = bundle_lookup.get(bundle_id, {})
                role = str(bundle.get("decision_role", "")).strip()
                if role and role not in allowed_roles:
                    issues.append(
                        {
                            "bundle_id": bundle_id,
                            "section": section_name,
                            "current_bucket": bucket,
                            "issue": f"Bundle role `{role}` appears in `{bucket}`; expected `{expected_bucket.get(role, 'role-appropriate bucket')}`.",
                            "recommended_action": "Move the bundle to the role-appropriate section bucket or update the bundle role before synthesis.",
                            "source": "deterministic_section_routing_scan",
                        }
                    )
    return issues


def _deterministic_answer_frame_issues(packet: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    answer_frame = packet.get("answer_frame", {}) if isinstance(packet.get("answer_frame"), dict) else {}
    for component in ("default_answer", "main_uncertainty"):
        value = str(answer_frame.get(component, "")).strip()
        if value and _looks_like_truncated_or_stringified_structure(value):
            issues.append(
                {
                    "component": component,
                    "critique": "Answer-frame field appears to be a truncated or stringified structure rather than clean decision-ready text.",
                    "risk": value[:180],
                    "recommended_action": "Normalize the answer frame into plain text before synthesis.",
                    "source": "deterministic_answer_frame_scan",
                }
            )
    return issues


def _looks_like_truncated_or_stringified_structure(text: str) -> bool:
    stripped = text.strip()
    return (
        stripped.startswith("{")
        or stripped.startswith("[")
        or ("{" in stripped and "}" not in stripped)
        or ("':" in stripped and stripped.endswith("..."))
        or stripped.endswith("...")
    )


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _risk_rows(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in value if isinstance(value, list) else []:
        if isinstance(row, dict):
            rows.append(row)
        elif str(row).strip():
            rows.append({"description": str(row).strip(), "source": "model_string_risk"})
    return rows


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []
