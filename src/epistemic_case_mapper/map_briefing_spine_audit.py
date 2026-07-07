from __future__ import annotations

from typing import Any


def build_spine_quality_report(scaffold: dict[str, Any]) -> dict[str, Any]:
    spine = _dict(scaffold.get("canonical_decision_spine"))
    validation = _dict(scaffold.get("canonical_decision_spine_validation"))
    consistency = _dict(scaffold.get("decision_spine_consistency_report"))
    projection = _dict(scaffold.get("section_projection_readiness_report"))
    arbitration = _dict(scaffold.get("canonical_decision_spine_model_arbitration_report"))
    classical = _dict(scaffold.get("classical_evidence_selection_report"))
    slot_audit = _dict(scaffold.get("slot_eligibility_audit"))
    return {
        "schema_id": "spine_quality_report_v1",
        "status": _quality_status(spine, validation, consistency, projection),
        "canonical_spine_status": spine.get("status"),
        "canonical_spine_validation_status": validation.get("status"),
        "decision_spine_consistency_status": consistency.get("status"),
        "model_arbitration_status": arbitration.get("status"),
        "section_projection_readiness_status": projection.get("status"),
        "candidate_card_count": _dict(spine.get("construction_report")).get("candidate_card_count", 0),
        "source_anchor_count": _dict(spine.get("construction_report")).get("source_anchor_count", 0),
        "missing_decision_slot_count": _list_count(spine, "missing_decision_slots"),
        "duplicate_pair_count": _dict(classical.get("claim_cluster_report")).get("duplicate_pair_count", 0),
        "quantity_outlier_count": _dict(classical.get("quantity_outlier_report")).get("outlier_count", 0),
        "slot_audit_status": slot_audit.get("status"),
        "issues": [
            *_string_list(validation.get("issues")),
            *_string_list(consistency.get("issues")),
            *_string_list(projection.get("issues")),
            *([] if arbitration.get("status") in {"accepted", "skipped_prompt_backend", ""} else [str(arbitration.get("message", ""))]),
        ],
    }


def render_before_after_briefing_comparison(scaffold: dict[str, Any]) -> str:
    legacy_spine = _dict(scaffold.get("memo_argument_spine"))
    legacy_sections = _dict(scaffold.get("section_reasoning_cards"))
    canonical = _dict(scaffold.get("canonical_decision_spine"))
    projection = _dict(scaffold.get("section_projection_readiness_report"))
    quality = _dict(scaffold.get("spine_quality_report"))
    lines = [
        "# Before/After Briefing Comparison",
        "",
        "This artifact compares the legacy section-local context path with the canonical decision-spine path for the same run.",
        "",
        "| Dimension | Legacy Context Path | Canonical Spine Path |",
        "|---|---|---|",
        f"| Central answer object | `memo_argument_spine` status `{legacy_spine.get('status', 'unknown')}` | `canonical_decision_spine` status `{canonical.get('status', 'unknown')}` |",
        f"| Section context | `section_reasoning_cards` status `{legacy_sections.get('status', 'unknown')}` | `section_projection_readiness_report` status `{projection.get('status', 'unknown')}` |",
        f"| Source traceability | load-bearing IDs `{len(legacy_spine.get('load_bearing_candidate_card_ids', [])) if isinstance(legacy_spine.get('load_bearing_candidate_card_ids'), list) else 0}` | source anchors `{quality.get('source_anchor_count', 0)}` |",
        f"| Missing slots | legacy issues `{len(legacy_sections.get('issues', [])) if isinstance(legacy_sections.get('issues'), list) else 0}` | canonical missing slots `{quality.get('missing_decision_slot_count', 0)}` |",
        f"| Duplicate control | not canonicalized at section projection | duplicate pairs flagged `{quality.get('duplicate_pair_count', 0)}` |",
        "",
        "## Read",
        "",
        _comparison_read(canonical, projection, quality),
    ]
    return "\n".join(lines).rstrip() + "\n"


def render_spine_completion_audit(scaffold: dict[str, Any]) -> str:
    quality = _dict(scaffold.get("spine_quality_report"))
    canonical = _dict(scaffold.get("canonical_decision_spine"))
    projection = _dict(scaffold.get("section_projection_readiness_report"))
    validation = _dict(scaffold.get("canonical_decision_spine_validation"))
    rows = [
        ("canonical_decision_spine.json", bool(canonical), canonical.get("status", "missing")),
        ("canonical_decision_spine_model_arbitration_report.json", bool(scaffold.get("canonical_decision_spine_model_arbitration_report")), _dict(scaffold.get("canonical_decision_spine_model_arbitration_report")).get("status", "missing")),
        ("canonical_decision_spine_model_prompt.txt", bool(scaffold.get("canonical_decision_spine_model_prompt") is not None), "present" if scaffold.get("canonical_decision_spine_model_prompt") is not None else "missing"),
        ("slot_eligibility_audit.json", bool(scaffold.get("slot_eligibility_audit")), _dict(scaffold.get("slot_eligibility_audit")).get("status", "missing")),
        ("classical_evidence_selection_report.json", bool(scaffold.get("classical_evidence_selection_report")), "present" if scaffold.get("classical_evidence_selection_report") else "missing"),
        ("claim_cluster_report.json", bool(scaffold.get("claim_cluster_report")), "present" if scaffold.get("claim_cluster_report") else "missing"),
        ("coverage_balance_report.json", bool(scaffold.get("coverage_balance_report")), "present" if scaffold.get("coverage_balance_report") else "missing"),
        ("decision_spine_consistency_report.json", bool(scaffold.get("decision_spine_consistency_report")), _dict(scaffold.get("decision_spine_consistency_report")).get("status", "missing")),
        ("section_projection_packets.json", bool(scaffold.get("section_projection_packets")), _dict(scaffold.get("section_projection_packets")).get("status", "missing")),
        ("section_projection_readiness_report.json", bool(projection), projection.get("status", "missing")),
        ("spine_quality_report.json", bool(quality), quality.get("status", "missing")),
    ]
    lines = [
        "# Spine Completion Audit",
        "",
        "| Criterion | Status | Detail |",
        "|---|---:|---|",
    ]
    lines.extend(f"| {name} | {'yes' if present else 'no'} | `{detail}` |" for name, present, detail in rows)
    lines.extend(
        [
            "",
            "## Acceptance Read",
            "",
            f"- Evidence field traceability: `{validation.get('status', 'missing')}`.",
            f"- Projection readiness: `{projection.get('status', 'missing')}`.",
            f"- Canonical spine status: `{canonical.get('status', 'missing')}`.",
            f"- Source-limited or bounded status is treated as acceptable when validation is valid and projection readiness is ready or warning.",
            "",
            "## Deferred Slices",
            "",
            "- Model-assisted spine arbitration remains report-compatible but not enabled by default; deterministic provenance gates are in place first.",
            "- Legacy context artifacts are retained during migration; removal should wait for before/after evidence across more live-backend runs.",
            "- Projection readiness is reported and summary-linked; making it hard-blocking should follow more telemetry on sparse source sets.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _quality_status(
    spine: dict[str, Any],
    validation: dict[str, Any],
    consistency: dict[str, Any],
    projection: dict[str, Any],
) -> str:
    if validation.get("status") == "invalid" or projection.get("status") == "not_synthesis_ready":
        return "fail"
    if spine.get("status") in {"ready", "bounded"} and consistency.get("status") in {"pass", "warning"}:
        return "pass_with_bounds" if spine.get("status") == "bounded" else "pass"
    return "warning"


def _comparison_read(canonical: dict[str, Any], projection: dict[str, Any], quality: dict[str, Any]) -> str:
    if quality.get("status") == "fail":
        return "The canonical path produced artifacts, but readiness or validation failed; use the failure reports before trusting prose."
    if canonical.get("status") == "bounded":
        return "The canonical path improves structure by keeping the answer source-bounded while still projecting traceable evidence into sections."
    if projection.get("status") == "ready":
        return "The canonical path is ready to feed section synthesis from one validated decision spine."
    return "The canonical path produced a reviewable spine and projection reports, but the run still needs reviewer attention."


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_count(value: dict[str, Any], key: str) -> int:
    items = value.get(key, [])
    return len(items) if isinstance(items, list) else 0


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
