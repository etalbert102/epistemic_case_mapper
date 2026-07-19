from __future__ import annotations

import os
from typing import Any, Callable

from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_packet_progress import packet_counts, packet_progress
from epistemic_case_mapper.pipeline.briefing.map_briefing_packet_quality_repair import repair_packet_for_synthesis
from epistemic_case_mapper.pipeline.briefing.map_briefing_packet_sufficiency import build_packet_sufficiency_report
from epistemic_case_mapper.pipeline.briefing.map_briefing_writer_guidance import attach_writer_guidance, build_writer_guidance_packet


def packet_critique_skip_reason(sufficiency_report: dict[str, Any], *, backend: str | None = None) -> str:
    mode = os.environ.get("ECM_PACKET_CRITIQUE_MODE", "auto").strip().lower()
    if mode in {"always", "deep", "full", "on", "true", "1"}:
        return ""
    if mode in {"off", "skip", "false", "0"}:
        return "disabled_by_ecm_packet_critique_mode"
    if mode != "auto" or not _auto_gate_applies_to_backend(backend):
        return ""
    issues = set(_string_list(sufficiency_report.get("issues")))
    status = str(sufficiency_report.get("status") or "").strip()
    if status == "ready" or not issues:
        return "auto_skipped_packet_ready"
    if issues <= {"compression_loss"}:
        return "auto_skipped_compression_loss_only"
    return "auto_skipped_lightweight_guidance_default"


def run_skipped_packet_critique_and_refinement(
    packet: dict[str, Any],
    pre_sufficiency: dict[str, Any],
    *,
    skip_reason: str,
    progress: Callable[[str, str, dict[str, Any] | None], None] | None,
    candidate_pool: Callable[[dict[str, Any], dict[str, Any]], list[dict[str, Any]]],
    sync_coverage: Callable[[dict[str, Any], dict[str, Any]], None],
) -> dict[str, Any]:
    packet_progress(progress, "packet_critique", "skipped", {"reason": skip_reason, **packet_counts(packet)})
    packet_progress(progress, "packet_refinement", "skipped", {"reason": skip_reason})
    packet_progress(progress, "packet_sufficiency_recompute", "started", {"reason": skip_reason})
    adjudication = skipped_packet_critique_adjudication(skip_reason)
    repaired_packet, repair_report = repair_packet_for_synthesis(packet, adjudication)
    post_sufficiency = build_packet_sufficiency_report(repaired_packet, candidate_pool=candidate_pool(repaired_packet, pre_sufficiency))
    sync_coverage(repaired_packet, post_sufficiency)
    writer_guidance = build_writer_guidance_packet(critique_adjudication=adjudication, sufficiency_report=post_sufficiency)
    attach_writer_guidance(repaired_packet, writer_guidance)
    critique_value = _skipped_packet_critique_value_report(
        skip_reason=skip_reason,
        writer_guidance=writer_guidance,
        pre_sufficiency=pre_sufficiency,
        post_sufficiency=post_sufficiency,
    )
    packet_progress(progress, "packet_sufficiency_recompute", "completed", {"status": post_sufficiency.get("status", "unknown"), "reason": skip_reason})
    return {
        "decision_briefing_packet": repaired_packet,
        "packet_sufficiency_report_pre_refinement": pre_sufficiency,
        "packet_sufficiency_report": post_sufficiency,
        "packet_critique_prompt": "",
        "packet_critique_raw": "",
        "packet_critique_report": _skipped_report("packet_critique_report_v1", skip_reason),
        "packet_critique_adjudication_report": adjudication,
        "packet_critique_value_report": critique_value,
        "writer_guidance_packet": writer_guidance,
        "decision_briefing_packet_refinement_prompt": "",
        "decision_briefing_packet_refinement_raw": "",
        "decision_briefing_packet_refinement_report": {
            **_skipped_report("decision_briefing_packet_refinement_report_v1", skip_reason),
            "packet_ready_for_synthesis": post_sufficiency.get("status") != "not_sufficient_for_synthesis",
            "applied_update_count": 0,
            "packet_quality_repair_report": repair_report,
            "warnings": [],
        },
    }


def _skipped_packet_critique_value_report(
    *,
    skip_reason: str,
    writer_guidance: dict[str, Any],
    pre_sufficiency: dict[str, Any],
    post_sufficiency: dict[str, Any],
) -> dict[str, Any]:
    writer_guidance_change_count = _int(writer_guidance.get("warning_or_guidance_count"))
    pre_missing = _int(pre_sufficiency.get("missing_count")) + _int(pre_sufficiency.get("missing_quantity_count"))
    post_missing = _int(post_sufficiency.get("missing_count")) + _int(post_sufficiency.get("missing_quantity_count"))
    return {
        "schema_id": "packet_critique_value_report_v1",
        "status": "skipped_with_guidance" if writer_guidance_change_count else "skipped_no_observed_downstream_effect",
        "critique_status": "skipped",
        "skip_reason": skip_reason,
        "critique_recommendation_count": 0,
        "accepted_recommendation_count": 0,
        "warning_only_recommendation_count": 0,
        "rejected_recommendation_count": 0,
        "packet_field_change_count": 0,
        "writer_guidance_change_count": writer_guidance_change_count,
        "required_writer_obligation_count": _int(writer_guidance.get("required_obligation_count")),
        "final_memo_retention_delta_proxy": pre_missing - post_missing,
        "pre_sufficiency_status": pre_sufficiency.get("status"),
        "post_sufficiency_status": post_sufficiency.get("status"),
    }


def skipped_packet_critique_adjudication(reason: str) -> dict[str, Any]:
    return {
        "schema_id": "packet_critique_adjudication_report_v1",
        "status": "skipped",
        "reason": reason,
        "judgment": "not_run",
        "accepted_recommendations": [],
        "rejected_recommendations": [],
        "warning_only_recommendations": [],
        "accepted_count": 0,
        "rejected_count": 0,
        "warning_only_count": 0,
    }


def _auto_gate_applies_to_backend(backend: str | None) -> bool:
    if backend is None:
        return True
    spec = backend.strip()
    return spec.startswith("ollama:") or spec.startswith("command:")


def _skipped_report(schema_id: str, reason: str) -> dict[str, Any]:
    return {"schema_id": schema_id, "status": "skipped", "reason": reason}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
