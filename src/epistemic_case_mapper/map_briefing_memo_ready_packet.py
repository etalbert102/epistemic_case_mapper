from __future__ import annotations

from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    first as _first,
    list_value as _list,
    norm as _norm,
    quantity_direction as _quantity_direction,
    quantity_type as _quantity_type,
    short_text as _short_text,
    string_list as _string_list,
    topic_key as _topic_key,
)
from epistemic_case_mapper.map_briefing_quantity_binding import build_quantity_binding_report
from epistemic_case_mapper.map_briefing_reader_packet_contract import build_memo_ready_decision_synthesis_contract
from epistemic_case_mapper.map_briefing_packet_qa import build_packet_qa_report
from epistemic_case_mapper.map_briefing_memo_ready_selection import select_memo_ready_items
from epistemic_case_mapper.map_briefing_quantity_slots import build_quantity_slot_report, build_quantity_slots
from epistemic_case_mapper.map_briefing_crux_reconstruction import reconstruct_decision_crux_items
from epistemic_case_mapper.map_briefing_answer_frame import is_weak_answer_frame


MEMO_READY_ROLES = {
    "strongest_support",
    "strongest_counterweight",
    "quantitative_anchor",
    "scope_boundary",
    "mechanism_or_explanation",
    "decision_crux",
    "context_only",
    "uncertain_role",
}

MANDATORY_ROLES = {
    "strongest_support",
    "strongest_counterweight",
    "quantitative_anchor",
    "scope_boundary",
    "decision_crux",
}


def build_quality_synthesis_packet_bundle(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build the minimal viable claim-map-to-packet assembly artifacts.

    The existing decision packet remains the source of truth. This layer turns
    its bundles into a compact model-facing packet with conservative clustering,
    quantity binding, diagnosticity-lite, and packet-quality telemetry.
    """

    packet = packet if isinstance(packet, dict) else {}
    clusters = build_packet_assembly_clusters(packet)
    role_report = build_packet_role_assignment_report(packet, clusters)
    diagnosticity = build_diagnosticity_matrix(packet, clusters)
    quantity_binding = build_quantity_binding_report(packet, clusters)
    evidence_profile = build_evidence_profile_report(packet, clusters, quantity_binding)
    assembly_audit = build_packet_assembly_audit(
        packet,
        clusters=clusters,
        role_report=role_report,
        diagnosticity=diagnosticity,
        quantity_binding=quantity_binding,
        evidence_profile=evidence_profile,
    )
    memo_ready = build_memo_ready_packet(
        packet,
        clusters=clusters,
        diagnosticity=diagnosticity,
        quantity_binding=quantity_binding,
        evidence_profile=evidence_profile,
        assembly_audit=assembly_audit,
    )
    quality = build_memo_ready_packet_quality_report(memo_ready, assembly_audit)
    quantity_slot_report = build_quantity_slot_report(memo_ready)
    packet_qa = build_packet_qa_report(packet, memo_ready_packet=memo_ready)
    return {
        "packet_assembly_clusters": clusters,
        "packet_role_assignment_report": role_report,
        "diagnosticity_matrix": diagnosticity,
        "quantity_binding_report": quantity_binding,
        "evidence_profile_report": evidence_profile,
        "packet_assembly_audit": assembly_audit,
        "memo_ready_packet": memo_ready,
        "memo_ready_selection_report": memo_ready.get("selection_report", {}),
        "decision_crux_reconstruction_report": memo_ready.get("decision_crux_reconstruction_report", {}),
        "quantity_slot_report": quantity_slot_report,
        "memo_ready_packet_quality_report": quality,
        "packet_qa_report": packet_qa,
    }


def build_packet_assembly_clusters(packet: dict[str, Any]) -> dict[str, Any]:
    bundles = _bundles(packet)
    clusters: list[dict[str, Any]] = []
    near_duplicates: list[dict[str, Any]] = []
    bundle_to_cluster: dict[str, str] = {}
    for bundle in bundles:
        if str(bundle.get("synthesis_suppressed") or "").lower() == "true":
            continue
        match = _safe_cluster_match(bundle, clusters)
        if match is None:
            cluster_id = f"cluster_{len(clusters) + 1:03d}"
            cluster = _cluster_from_bundle(cluster_id, bundle)
            clusters.append(cluster)
            bundle_to_cluster[str(bundle.get("bundle_id") or "")] = cluster_id
            continue
        cluster = match["cluster"]
        near_duplicates.append(
            {
                "cluster_id": cluster["cluster_id"],
                "bundle_id": bundle.get("bundle_id"),
                "decision": "merged",
                "reason": match["reason"],
                "similarity": match["similarity"],
            }
        )
        _merge_bundle_into_cluster(cluster, bundle)
        bundle_to_cluster[str(bundle.get("bundle_id") or "")] = str(cluster["cluster_id"])
    kept_separate = _kept_separate_near_duplicates(clusters)
    return {
        "schema_id": "packet_assembly_clusters_v1",
        "method": "conservative_blocking_then_safe_merge",
        "cluster_count": len(clusters),
        "source_bundle_count": len(bundles),
        "bundle_to_cluster": bundle_to_cluster,
        "clusters": clusters,
        "merged_near_duplicates": near_duplicates,
        "kept_separate_near_duplicates": kept_separate,
        "risk_summary": {
            "false_merge_risk": "low" if not near_duplicates else "medium",
            "duplicate_retention_risk": "medium" if kept_separate else "low",
            "policy": "prefer_under_consolidation",
        },
    }


def build_packet_role_assignment_report(packet: dict[str, Any], clusters: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for cluster in _clusters(clusters):
        source_role = str(cluster.get("source_decision_role") or "")
        role = _memo_ready_role(source_role)
        confidence = "high" if role != "uncertain_role" else "low"
        rationale = _role_rationale(role, source_role, cluster)
        rows.append(
            {
                "cluster_id": cluster.get("cluster_id"),
                "source_decision_role": source_role,
                "assigned_role": role,
                "component_type": _component_type_for_role(role),
                "stance": _stance_for_role(role),
                "confidence": confidence,
                "rationale": rationale,
                "needs_adjudication": role == "uncertain_role",
            }
        )
    return {
        "schema_id": "packet_role_assignment_report_v1",
        "method": "deterministic_role_projection_with_uncertain_role_escape_hatch",
        "assignment_count": len(rows),
        "uncertain_role_count": sum(1 for row in rows if row["assigned_role"] == "uncertain_role"),
        "role_counts": dict(Counter(row["assigned_role"] for row in rows)),
        "assignments": rows,
    }


def build_diagnosticity_matrix(packet: dict[str, Any], clusters: dict[str, Any]) -> dict[str, Any]:
    hypotheses = _answer_hypotheses(packet, clusters)
    rows = []
    for cluster in _clusters(clusters):
        role = _memo_ready_role(str(cluster.get("source_decision_role") or ""))
        stance_by_hypothesis = {
            hypothesis["hypothesis_id"]: _diagnostic_stance(role, hypothesis["kind"])
            for hypothesis in hypotheses
        }
        diagnosticity_score = _diagnosticity_score(role, cluster, stance_by_hypothesis)
        rows.append(
            {
                "cluster_id": cluster.get("cluster_id"),
                "role": role,
                "reader_claim": cluster.get("representative_claim"),
                "stance_by_hypothesis": stance_by_hypothesis,
                "diagnosticity_score": diagnosticity_score,
                "high_diagnosticity": diagnosticity_score >= 7,
                "sensitivity_note": _sensitivity_note(role, cluster),
            }
        )
    return {
        "schema_id": "diagnosticity_matrix_v1",
        "method": "role_based_diagnosticity_lite",
        "hypotheses": hypotheses,
        "rows": rows,
        "high_diagnosticity_cluster_ids": [
            str(row["cluster_id"]) for row in rows if row.get("high_diagnosticity")
        ],
    }


def build_evidence_profile_report(
    packet: dict[str, Any],
    clusters: dict[str, Any],
    quantity_binding: dict[str, Any],
) -> dict[str, Any]:
    bound = {str(row.get("cluster_id")) for row in quantity_binding.get("bindings", []) if isinstance(row, dict)}
    rows = []
    for cluster in _clusters(clusters):
        cluster_id = str(cluster.get("cluster_id") or "")
        role = _memo_ready_role(str(cluster.get("source_decision_role") or ""))
        profile = {
            "directness": _directness(cluster),
            "consistency": "not_assessed_in_minimal_slice",
            "precision": "quantified" if cluster_id in bound else "not_quantified_or_unbound",
            "applicability": "scope_named" if role == "scope_boundary" else "not_assessed_in_minimal_slice",
            "quality": str(cluster.get("quality") or "unknown"),
            "primary_caution": _primary_caution(cluster, role),
        }
        rows.append({"cluster_id": cluster_id, "evidence_profile": profile})
    return {
        "schema_id": "evidence_profile_report_v1",
        "method": "lightweight_minimal_slice_profiles",
        "profile_count": len(rows),
        "incomplete_profile_count": sum(
            1
            for row in rows
            if "not_assessed" in " ".join(str(value) for value in row["evidence_profile"].values())
        ),
        "profiles": rows,
    }


def build_packet_assembly_audit(
    packet: dict[str, Any],
    *,
    clusters: dict[str, Any],
    role_report: dict[str, Any],
    diagnosticity: dict[str, Any],
    quantity_binding: dict[str, Any],
    evidence_profile: dict[str, Any],
) -> dict[str, Any]:
    retained_bundle_ids = {
        bundle_id
        for cluster in _clusters(clusters)
        for bundle_id in _string_list(cluster.get("bundle_ids"))
    }
    dropped = [
        {
            "bundle_id": bundle.get("bundle_id"),
            "reason": "suppressed_or_not_selected_for_assembly",
            "decision_role": bundle.get("decision_role"),
        }
        for bundle in _bundles(packet)
        if str(bundle.get("bundle_id") or "") not in retained_bundle_ids
    ]
    warnings = []
    if role_report.get("uncertain_role_count"):
        warnings.append("uncertain_role_assignments_present")
    if quantity_binding.get("unbound_quantity_group_count"):
        warnings.append("unbound_quantities_present")
    if quantity_binding.get("unsafe_quantity_pairing_count"):
        warnings.append("unsafe_quantity_pairings_present")
    if evidence_profile.get("incomplete_profile_count"):
        warnings.append("evidence_profiles_incomplete")
    return {
        "schema_id": "packet_assembly_audit_v1",
        "status": "warning" if warnings else "ready",
        "warnings": warnings,
        "dropped_claims": dropped,
        "merged_claims": clusters.get("merged_near_duplicates", []),
        "kept_separate_near_duplicates": clusters.get("kept_separate_near_duplicates", []),
        "uncertain_role_assignments": [
            row for row in role_report.get("assignments", []) if row.get("assigned_role") == "uncertain_role"
        ],
        "unbound_quantities": quantity_binding.get("unbound_quantities", []),
        "unsafe_quantity_pairings": quantity_binding.get("unsafe_quantity_pairings", []),
        "relation_edges_used_as_signals": _relation_edges_used(clusters),
        "relation_edges_ignored": [],
        "evidence_profile_downgrades": [
            row
            for row in evidence_profile.get("profiles", [])
            if "unknown" in str(row.get("evidence_profile", {})).lower()
            or "not_assessed" in str(row.get("evidence_profile", {})).lower()
        ],
        "high_diagnosticity_promoted_cluster_ids": diagnosticity.get("high_diagnosticity_cluster_ids", []),
        "provenance_warnings": _provenance_warnings(clusters),
    }


def build_memo_ready_packet(
    packet: dict[str, Any],
    *,
    clusters: dict[str, Any],
    diagnosticity: dict[str, Any],
    quantity_binding: dict[str, Any],
    evidence_profile: dict[str, Any],
    assembly_audit: dict[str, Any],
) -> dict[str, Any]:
    quantity_by_cluster = {
        str(row.get("cluster_id")): row
        for row in quantity_binding.get("bindings", [])
        if isinstance(row, dict)
    }
    diagnostic_by_cluster = {
        str(row.get("cluster_id")): row
        for row in diagnosticity.get("rows", [])
        if isinstance(row, dict)
    }
    profile_by_cluster = {
        str(row.get("cluster_id")): row.get("evidence_profile", {})
        for row in evidence_profile.get("profiles", [])
        if isinstance(row, dict)
    }
    items = []
    for cluster in _ranked_clusters(clusters, diagnostic_by_cluster):
        item = _memo_ready_item(
            cluster,
            quantity_binding=quantity_by_cluster.get(str(cluster.get("cluster_id") or "")),
            diagnosticity=diagnostic_by_cluster.get(str(cluster.get("cluster_id") or "")),
            evidence_profile=profile_by_cluster.get(str(cluster.get("cluster_id") or ""), {}),
        )
        if item:
            items.append(item)
    items, crux_report = reconstruct_decision_crux_items(items)
    mandatory = [item for item in items if item.get("must_use")]
    context = [item for item in items if not item.get("must_use")]
    selected, selection_report = select_memo_ready_items(mandatory, context)
    memo_ready_packet = {
        "schema_id": "memo_ready_packet_v1",
        "decision_question": str(packet.get("decision_question") or "").strip(),
        "answer_spine": _answer_spine(packet, diagnosticity, selected),
        "evidence_items": selected,
        "evidence_groups": _evidence_groups(selected),
        "source_trail": _source_trail(packet),
        "selection_report": selection_report,
        "decision_crux_reconstruction_report": crux_report,
        "assembly_summary": {
            "cluster_count": clusters.get("cluster_count", 0),
            "mandatory_item_count": sum(1 for item in selected if item.get("must_use")),
            "context_item_count": sum(1 for item in selected if not item.get("must_use")),
            "assembly_status": assembly_audit.get("status"),
            "assembly_warnings": assembly_audit.get("warnings", []),
        },
    }
    memo_ready_packet["decision_synthesis_contract"] = build_memo_ready_decision_synthesis_contract(memo_ready_packet)
    return memo_ready_packet


def build_memo_ready_packet_quality_report(
    memo_ready_packet: dict[str, Any],
    assembly_audit: dict[str, Any],
) -> dict[str, Any]:
    items = _list(memo_ready_packet.get("evidence_items"))
    mandatory = [item for item in items if isinstance(item, dict) and item.get("must_use")]
    quantitative = [item for item in mandatory if item.get("role") == "quantitative_anchor"]
    issues: list[dict[str, Any]] = []
    if not memo_ready_packet.get("answer_spine"):
        issues.append({"severity": "high", "issue_type": "missing_answer_spine"})
    if not any(item.get("role") == "strongest_support" for item in mandatory):
        issues.append({"severity": "warning", "issue_type": "missing_strongest_support"})
    if not any(item.get("role") == "strongest_counterweight" for item in mandatory):
        issues.append({"severity": "warning", "issue_type": "missing_strongest_counterweight"})
    if not assembly_audit or assembly_audit.get("status") not in {"ready", "warning"}:
        issues.append({"severity": "warning", "issue_type": "missing_or_weak_assembly_audit"})
    for item in mandatory:
        missing = []
        if not item.get("source_label"):
            missing.append("source_label")
        if not item.get("lineage", {}).get("derived_from_claim_ids"):
            missing.append("claim_lineage")
        if not item.get("decision_relevance"):
            missing.append("decision_relevance")
        if not item.get("argument", {}).get("warrant"):
            missing.append("warrant")
        if missing:
            issues.append({"severity": "warning", "issue_type": "mandatory_item_missing_fields", "item_id": item.get("item_id"), "missing": missing})
    for item in quantitative:
        for quantity in _list(item.get("quantities")):
            if not isinstance(quantity, dict):
                continue
            missing = [key for key in ("value", "interpretation") if not quantity.get(key)]
            if missing:
                issues.append({"severity": "warning", "issue_type": "quantity_without_interpretation", "item_id": item.get("item_id"), "missing": missing})
        for warning in _list(item.get("quantity_warnings")):
            issues.append({"severity": "warning", "issue_type": "unsafe_quantity_pairing", "item_id": item.get("item_id"), "warning": warning})
    return {
        "schema_id": "memo_ready_packet_quality_report_v1",
        "status": "ready" if not issues else "warning",
        "mandatory_item_count": len(mandatory),
        "mandatory_with_source_and_lineage_count": sum(
            1
            for item in mandatory
            if item.get("source_label") and item.get("lineage", {}).get("derived_from_claim_ids")
        ),
        "mandatory_quantitative_anchor_count": len(quantitative),
        "bound_quantitative_anchor_count": sum(1 for item in quantitative if item.get("quantities")),
        "issues": issues,
    }


def build_memo_ready_packet_synthesis_prompt(memo_ready_packet: dict[str, Any]) -> str:
    import json

    return (
        "You are a senior decision analyst. Write a coherent decision memo from the memo-ready evidence packet.\n"
        "Use the packet as the complete evidence record for this memo.\n\n"
        "The packet includes a decision_synthesis_contract. Use that contract as the writing plan.\n"
        "Do not merely summarize or list evidence. Produce a decision read: default stance, why it is supported, strongest counterweight, scope/conditions, and practical implication.\n\n"
        "Rules:\n"
        "- Answer the decision question directly in the first paragraph.\n"
        "- Preserve source labels and load-bearing quantities from mandatory evidence items.\n"
        "- When quantity_tuples are present, use those tuple labels instead of pairing estimates and intervals yourself.\n"
        "- If a quantity is marked ambiguous or unpaired, describe it without inventing an estimate/interval pair.\n"
        "- Explain what the key quantities mean for the decision; do not dump bare numbers.\n"
        "- Explain why the strongest support does or does not outweigh the strongest counterweight.\n"
        "- Name the conditions, subgroups, contexts, or assumptions that change the answer.\n"
        "- Include decision cruxes when present and translate uncertainty into a practical implication.\n"
        "- Do not mention packet schemas, item IDs, validation, telemetry, or internal pipeline machinery.\n"
        "- Use natural Markdown and choose headings that fit the decision question.\n\n"
        "Suggested memo shape when it fits the case:\n"
        "## Decision Brief\n"
        "## Why This Is the Best Current Read\n"
        "## What Could Change the Answer\n"
        "## Decision-Relevant Evidence\n"
        "## Sources\n\n"
        "Memo-ready packet:\n"
        f"{json.dumps(memo_ready_packet, indent=2, ensure_ascii=False)}\n"
    )


def _cluster_from_bundle(cluster_id: str, bundle: dict[str, Any]) -> dict[str, Any]:
    source_role = str(bundle.get("decision_role") or "context")
    return {
        "cluster_id": cluster_id,
        "blocking_key": _blocking_key(bundle),
        "source_decision_role": source_role,
        "representative_claim": str(bundle.get("claim") or "").strip(),
        "bundle_ids": _string_list(bundle.get("bundle_id")),
        "claim_ids": _string_list(bundle.get("claim_ids")),
        "relation_ids": _string_list(bundle.get("relation_ids")),
        "source_ids": _string_list(bundle.get("source_ids")),
        "source_labels": _string_list(bundle.get("source_labels")),
        "quantity_ids": _string_list(bundle.get("quantity_ids")),
        "quantity_values": _string_list(bundle.get("quantity_values")),
        "limits": _string_list(bundle.get("limits")),
        "why_it_matters": str(bundle.get("why_it_matters") or "").strip(),
        "quality": bundle.get("quality"),
        "source_excerpt": str(bundle.get("source_excerpt") or "").strip(),
        "directionality": str(bundle.get("directionality") or "").strip(),
        "assembly_confidence": "high" if bundle.get("source_labels") or bundle.get("source_ids") else "medium",
    }


def _safe_cluster_match(bundle: dict[str, Any], clusters: list[dict[str, Any]]) -> dict[str, Any] | None:
    bundle_block = _blocking_key(bundle)
    bundle_claim = str(bundle.get("claim") or "")
    bundle_claim_ids = set(_string_list(bundle.get("claim_ids")))
    for cluster in clusters:
        if cluster.get("blocking_key") != bundle_block:
            continue
        existing_claim_ids = set(_string_list(cluster.get("claim_ids")))
        if bundle_claim_ids and bundle_claim_ids & existing_claim_ids:
            return {"cluster": cluster, "reason": "shared_claim_id_in_same_block", "similarity": 1.0}
        similarity = SequenceMatcher(None, _norm(bundle_claim), _norm(str(cluster.get("representative_claim") or ""))).ratio()
        if similarity >= 0.93:
            return {"cluster": cluster, "reason": "near_identical_claim_in_same_block", "similarity": round(similarity, 3)}
    return None


def _merge_bundle_into_cluster(cluster: dict[str, Any], bundle: dict[str, Any]) -> None:
    for key in ("bundle_ids", "claim_ids", "relation_ids", "source_ids", "source_labels", "quantity_ids", "quantity_values", "limits"):
        cluster[key] = _dedupe([*_string_list(cluster.get(key)), *_string_list(bundle.get(key))])
    if len(str(bundle.get("claim") or "")) > len(str(cluster.get("representative_claim") or "")):
        cluster["representative_claim"] = str(bundle.get("claim") or "").strip()
    if not cluster.get("why_it_matters") and bundle.get("why_it_matters"):
        cluster["why_it_matters"] = str(bundle.get("why_it_matters") or "")


def _kept_separate_near_duplicates(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, left in enumerate(clusters):
        for right in clusters[index + 1 :]:
            similarity = SequenceMatcher(
                None,
                _norm(str(left.get("representative_claim") or "")),
                _norm(str(right.get("representative_claim") or "")),
            ).ratio()
            if similarity < 0.82:
                continue
            if left.get("blocking_key") == right.get("blocking_key"):
                continue
            rows.append(
                {
                    "left_cluster_id": left.get("cluster_id"),
                    "right_cluster_id": right.get("cluster_id"),
                    "similarity": round(similarity, 3),
                    "reason": "kept_separate_due_to_distinct_blocking_key",
                }
            )
    return rows[:20]


def _blocking_key(bundle: dict[str, Any]) -> dict[str, str]:
    return {
        "role": _memo_ready_role(str(bundle.get("decision_role") or "")),
        "source": _first(_string_list(bundle.get("source_ids")) or _string_list(bundle.get("source_labels"))),
        "quantity_type": _quantity_type(_string_list(bundle.get("quantity_values"))),
        "topic": _topic_key(str(bundle.get("claim") or "")),
    }


def _answer_hypotheses(packet: dict[str, Any], clusters: dict[str, Any]) -> list[dict[str, Any]]:
    answer = _dict(packet.get("answer_frame"))
    default = str(answer.get("default_answer") or "the default read is best supported").strip()
    if _answer_frame_needs_rebuild(default):
        default = "The default answer is not settled until the source-backed evidence is weighed."
    hypotheses = [
        {"hypothesis_id": "h_default", "kind": "default", "statement": default},
        {"hypothesis_id": "h_counter", "kind": "counter", "statement": "A major counterweight changes or substantially weakens the default read."},
        {"hypothesis_id": "h_scope_limited", "kind": "scope", "statement": "The answer applies only within a narrower scope boundary."},
        {"hypothesis_id": "h_underdetermined", "kind": "underdetermined", "statement": "The evidence is too uncertain or incomplete for a strong answer."},
    ]
    roles = {str(cluster.get("source_decision_role") or "") for cluster in _clusters(clusters)}
    if not roles & {"counterweight", "scope_boundary", "decision_crux"}:
        hypotheses = hypotheses[:2] + hypotheses[3:]
    return hypotheses[:4]


def _diagnostic_stance(role: str, hypothesis_kind: str) -> str:
    if role == "strongest_support":
        return "supports" if hypothesis_kind == "default" else "weakens"
    if role == "strongest_counterweight":
        return "weakens" if hypothesis_kind == "default" else "supports"
    if role == "scope_boundary":
        return "bounds" if hypothesis_kind in {"default", "scope"} else "supports"
    if role == "decision_crux":
        return "distinguishes"
    if role == "quantitative_anchor":
        return "supports" if hypothesis_kind == "default" else "contextualizes"
    return "contextualizes"


def _diagnosticity_score(role: str, cluster: dict[str, Any], stance_by_hypothesis: dict[str, str]) -> int:
    score = {
        "strongest_counterweight": 8,
        "decision_crux": 8,
        "scope_boundary": 7,
        "quantitative_anchor": 7,
        "strongest_support": 6,
        "mechanism_or_explanation": 4,
        "context_only": 2,
    }.get(role, 3)
    if len(set(stance_by_hypothesis.values())) >= 3:
        score += 1
    if cluster.get("quantity_values"):
        score += 1
    return max(0, min(10, score))


def _memo_ready_item(
    cluster: dict[str, Any],
    *,
    quantity_binding: dict[str, Any] | None,
    diagnosticity: dict[str, Any] | None,
    evidence_profile: dict[str, Any],
) -> dict[str, Any]:
    role = _memo_ready_role(str(cluster.get("source_decision_role") or ""))
    claim = str(cluster.get("representative_claim") or "").strip()
    if not claim:
        return {}
    if role == "strongest_support" and any(term in claim.lower() for term in ("challenge", "challenges", "objection", "objects", "critique", "criticizes", "targets")):
        role = "strongest_counterweight"
    source_label = _first(_string_list(cluster.get("source_labels")))
    diagnosticity = diagnosticity if isinstance(diagnosticity, dict) else {}
    quantities = _list(quantity_binding.get("quantities")) if isinstance(quantity_binding, dict) else []
    quantity_tuples = _list(quantity_binding.get("quantity_tuples")) if isinstance(quantity_binding, dict) else []
    quantity_warnings = [
        str(row.get("warning") or row.get("reason") or row)
        for row in _list(quantity_binding.get("unsafe_quantity_pairings")) if isinstance(row, dict)
    ] if isinstance(quantity_binding, dict) else []
    has_safe_quantity_binding = role != "quantitative_anchor" or bool(quantities)
    has_source = bool(source_label or cluster.get("source_ids"))
    must_use = role in MANDATORY_ROLES and role != "uncertain_role" and has_safe_quantity_binding and has_source
    return {
        "item_id": str(cluster.get("cluster_id") or ""),
        "role": role,
        "reader_claim": claim,
        "source_label": source_label,
        "source_labels": _string_list(cluster.get("source_labels")),
        "quantities": quantities,
        "quantity_slots": build_quantity_slots(quantities),
        "quantity_tuples": quantity_tuples,
        "quantity_warnings": quantity_warnings,
        "decision_relevance": _decision_relevance(role, cluster, diagnosticity),
        "diagnosticity": {
            "score": diagnosticity.get("diagnosticity_score", 0),
            "high_diagnosticity": bool(diagnosticity.get("high_diagnosticity")),
            "sensitivity_note": diagnosticity.get("sensitivity_note", ""),
        },
        "evidence_profile": evidence_profile,
        "argument": {
            "grounds": claim,
            "warrant": _warrant(role, claim),
            "qualifier": _qualifier(cluster, role),
            "backing": _first(_string_list(cluster.get("source_labels"))) or "source-backed claim",
            "rebuttal": _rebuttal(role, cluster),
        },
        "caveat": _primary_caution(cluster, role),
        "lineage": {
            "derived_from_claim_ids": _string_list(cluster.get("claim_ids")),
            "derived_from_relation_ids": _string_list(cluster.get("relation_ids")),
            "derived_from_source_ids": _string_list(cluster.get("source_ids")),
            "assembly_activity": "minimal_packet_assembly",
            "transformations_applied": ["conservative_clustering", "role_projection", "quantity_binding"],
            "assembly_confidence": cluster.get("assembly_confidence", "medium"),
            "lineage_warnings": _lineage_warnings(cluster),
        },
        "must_use": must_use,
    }


def _answer_spine(packet: dict[str, Any], diagnosticity: dict[str, Any], mandatory: list[dict[str, Any]]) -> dict[str, Any]:
    answer = _dict(packet.get("answer_frame"))
    default_read = str(answer.get("default_answer") or "").strip()
    if _answer_frame_needs_rebuild(default_read):
        default_read = _why_this_read(mandatory)
    decisive = [
        item["item_id"]
        for item in mandatory
        if _dict(item.get("diagnosticity")).get("high_diagnosticity")
    ][:8]
    return {
        "default_read": default_read,
        "confidence": str(answer.get("confidence") or "medium").strip(),
        "why_this_read": _why_this_read(mandatory),
        "why_not_stronger": str(answer.get("main_uncertainty") or "").strip() or _why_not_stronger(mandatory),
        "what_would_change_this": _what_would_change_this(mandatory),
        "scope_boundary": str(answer.get("scope") or "").strip(),
        "live_alternatives_considered": diagnosticity.get("hypotheses", []),
        "decisive_evidence": decisive,
        "sensitivity_notes": [
            _dict(item.get("diagnosticity")).get("sensitivity_note")
            for item in mandatory
            if _dict(item.get("diagnosticity")).get("sensitivity_note")
        ][:6],
    }


def _evidence_groups(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {role: [] for role in sorted(MEMO_READY_ROLES)}
    for item in items:
        role = str(item.get("role") or "context_only")
        groups.setdefault(role, []).append(str(item.get("item_id") or ""))
    return {key: value for key, value in groups.items() if value}


def _source_trail(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "source_id": row.get("source_id"),
            "source_label": row.get("source_label") or row.get("citation_label") or row.get("display_label"),
            "source_url": row.get("source_url"),
            "appears_in_packet": row.get("appears_in_packet", True),
        }
        for row in _list(packet.get("source_trail"))
        if isinstance(row, dict) and row.get("appears_in_packet", True)
    ][:24]


def _ranked_clusters(clusters: dict[str, Any], diagnostic_by_cluster: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    def rank(cluster: dict[str, Any]) -> tuple[int, int, str]:
        role = _memo_ready_role(str(cluster.get("source_decision_role") or ""))
        role_rank = {
            "quantitative_anchor": 0,
            "strongest_counterweight": 1,
            "decision_crux": 2,
            "scope_boundary": 3,
            "strongest_support": 4,
            "mechanism_or_explanation": 5,
            "context_only": 6,
        }.get(role, 7)
        diag = int(_dict(diagnostic_by_cluster.get(str(cluster.get("cluster_id") or ""))).get("diagnosticity_score", 0) or 0)
        return (role_rank, -diag, str(cluster.get("cluster_id") or ""))

    return sorted(_clusters(clusters), key=rank)


def _memo_ready_role(role: str) -> str:
    role = str(role or "").strip()
    return {
        "strongest_support": "strongest_support",
        "counterweight": "strongest_counterweight",
        "scope_boundary": "scope_boundary",
        "decision_crux": "decision_crux",
        "quantitative_anchor": "quantitative_anchor",
        "mechanism": "mechanism_or_explanation",
        "context": "context_only",
    }.get(role, "uncertain_role")


def _component_type_for_role(role: str) -> str:
    return {
        "strongest_support": "grounds",
        "strongest_counterweight": "rebuttal",
        "scope_boundary": "qualifier",
        "decision_crux": "crux",
        "quantitative_anchor": "grounds",
        "mechanism_or_explanation": "warrant",
    }.get(role, "context")


def _stance_for_role(role: str) -> str:
    return {
        "strongest_support": "supports_default",
        "strongest_counterweight": "weakens_or_rebuts_default",
        "scope_boundary": "bounds_default",
        "decision_crux": "distinguishes_hypotheses",
        "quantitative_anchor": "quantifies_default_or_tension",
        "mechanism_or_explanation": "explains",
    }.get(role, "contextualizes")


def _role_rationale(role: str, source_role: str, cluster: dict[str, Any]) -> str:
    if role == "uncertain_role":
        return f"Source role {source_role!r} has no safe memo-ready mapping."
    return f"Mapped source role {source_role!r} to {role!r}; claim and source lineage are preserved."


def _decision_relevance(role: str, cluster: dict[str, Any], diagnosticity: dict[str, Any]) -> str:
    claim = str(cluster.get("representative_claim") or "")
    if role == "strongest_support":
        return "Supports the default answer with source-backed evidence."
    if role == "strongest_counterweight":
        return "Identifies evidence that weakens, qualifies, or could change the default answer."
    if role == "scope_boundary":
        return "Bounds where the answer applies or fails to travel."
    if role == "decision_crux":
        return "Names a distinction that could change the decision if resolved differently."
    if role == "quantitative_anchor":
        return "Provides a numerical anchor that should discipline the memo's strength of claim."
    if role == "mechanism_or_explanation":
        return "Explains a possible mechanism or proxy path without making it the whole answer."
    return f"Context for interpreting the decision evidence: {_short_text(claim, 120)}"


def _warrant(role: str, claim: str) -> str:
    if role == "strongest_support":
        return "If this source-backed claim holds, it raises support for the default answer."
    if role == "strongest_counterweight":
        return "If this source-backed claim holds, the default answer needs qualification or lower confidence."
    if role == "scope_boundary":
        return "If this boundary holds, the answer should not be generalized beyond the named scope."
    if role == "decision_crux":
        return "If this distinction is resolved differently, the answer could change."
    if role == "quantitative_anchor":
        return "The quantity constrains how strongly the memo can state the associated claim."
    if role == "mechanism_or_explanation":
        return "The mechanism helps explain why the observed evidence may matter for the decision."
    return "This item provides context but should not carry the decision by itself."


def _qualifier(cluster: dict[str, Any], role: str) -> str:
    limits = _string_list(cluster.get("limits"))
    if limits:
        return "; ".join(limits[:2])
    if role == "scope_boundary":
        return "Applies inside the named boundary."
    return "Apply within the source-backed scope of the claim."


def _rebuttal(role: str, cluster: dict[str, Any]) -> str:
    if role == "strongest_support":
        return "Counterweights and scope boundaries may limit this support."
    if role == "strongest_counterweight":
        return "This counterweight may be less decisive if it applies only to a narrower scope."
    if role == "scope_boundary":
        return "The boundary may not matter if the target case clearly falls inside it."
    return ""


def _directness(cluster: dict[str, Any]) -> str:
    if cluster.get("source_grounded") is False:
        return "weak_or_indirect"
    if cluster.get("source_labels"):
        return "source_grounded"
    return "unknown"


def _primary_caution(cluster: dict[str, Any], role: str) -> str:
    limits = _string_list(cluster.get("limits"))
    if limits:
        return limits[0]
    if role == "scope_boundary":
        return "Scope-sensitive item."
    if role == "mechanism_or_explanation":
        return "Mechanism evidence should not be over-weighted as direct outcome evidence."
    return "Evidence quality not fully assessed in minimal slice."


def _sensitivity_note(role: str, cluster: dict[str, Any]) -> str:
    if role == "strongest_counterweight":
        return "The answer would weaken if this counterweight is more applicable than the support evidence."
    if role == "scope_boundary":
        return "The answer changes if the target case falls outside this boundary."
    if role == "decision_crux":
        return "The answer changes if this crux resolves against the default read."
    if role == "quantitative_anchor":
        return "The answer changes if this quantitative anchor is misbound or materially downgraded."
    return ""


def _why_this_read(mandatory: list[dict[str, Any]]) -> str:
    support = [item for item in mandatory if _item_supports_default(item)]
    quantitative_support = [item for item in mandatory if item.get("role") == "quantitative_anchor" and _item_supports_default(item)]
    counter = [item for item in mandatory if item.get("role") == "strongest_counterweight"]
    support_claim = _short_text(str(support[0].get("reader_claim", "")), 180) if support else ""
    counter_claim = _short_text(str(counter[0].get("reader_claim", "")), 180) if counter else ""
    if support and counter:
        return f"The default read rests on {support_claim}, while {counter_claim} bounds confidence."
    if support:
        return f"The default read rests on {support_claim}."
    if quantitative_support:
        return f"The default read is disciplined by { _short_text(str(quantitative_support[0].get('reader_claim', '')), 180) }."
    if counter:
        return "The default read is weak because counterweights dominate the assembled evidence."
    return "The packet does not identify a strong default read."


def _answer_frame_needs_rebuild(default_read: str) -> bool:
    text = str(default_read or "").strip()
    return is_weak_answer_frame(text) or "State the default" in text


def _item_supports_default(item: dict[str, Any]) -> bool:
    role = str(item.get("role") or "")
    claim = str(item.get("reader_claim") or "").lower()
    if role == "strongest_support":
        return True
    if role != "quantitative_anchor":
        return False
    if any(term in claim for term in ("higher risk", "increased risk", "positive association", "adverse", "mortality", "failed")):
        return False
    return any(term in claim for term in ("not associated", "no association", "reduced", "lower", "neutral", "benefit"))


def _why_not_stronger(mandatory: list[dict[str, Any]]) -> str:
    if any(item.get("role") == "strongest_counterweight" for item in mandatory):
        return "Important counterweights remain in the assembled evidence."
    if any(item.get("role") == "scope_boundary" for item in mandatory):
        return "The answer is scope-sensitive."
    return "Evidence profiles are incomplete in the minimal slice."


def _what_would_change_this(mandatory: list[dict[str, Any]]) -> str:
    cruxes = [item for item in mandatory if item.get("role") == "decision_crux"]
    if cruxes:
        return "Resolving the named decision cruxes differently would change the answer."
    counters = [item for item in mandatory if item.get("role") == "strongest_counterweight"]
    if counters:
        return "Showing the strongest counterweight is inapplicable would strengthen the answer; showing it dominates would weaken it."
    return "Additional direct evidence against the default read would change the answer."


def _relation_edges_used(clusters: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for cluster in _clusters(clusters):
        for relation_id in _string_list(cluster.get("relation_ids")):
            rows.append({"cluster_id": cluster.get("cluster_id"), "relation_id": relation_id, "use": "lineage_signal"})
    return rows


def _provenance_warnings(clusters: dict[str, Any]) -> list[dict[str, Any]]:
    warnings = []
    for cluster in _clusters(clusters):
        if not cluster.get("claim_ids"):
            warnings.append({"cluster_id": cluster.get("cluster_id"), "warning": "missing_claim_lineage"})
        if not cluster.get("source_ids") and not cluster.get("source_labels"):
            warnings.append({"cluster_id": cluster.get("cluster_id"), "warning": "missing_source_lineage"})
    return warnings


def _lineage_warnings(cluster: dict[str, Any]) -> list[str]:
    warnings = []
    if not cluster.get("claim_ids"):
        warnings.append("missing_claim_lineage")
    if not cluster.get("source_ids") and not cluster.get("source_labels"):
        warnings.append("missing_source_lineage")
    return warnings


def _bundles(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _list(packet.get("evidence_bundles")) if isinstance(row, dict)]


def _clusters(clusters: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _list(clusters.get("clusters")) if isinstance(row, dict)]
