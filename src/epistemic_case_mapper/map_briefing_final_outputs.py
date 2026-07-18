from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.map_briefing_final_output_paths import (
    FinalReaderOutputPaths,
    final_reader_output_paths,
    final_reader_output_paths as _final_reader_output_paths,
)
from epistemic_case_mapper.map_briefing_memo_progress import (
    ensure_memo_progress,
    memo_progress_path,
    record_memo_progress,
)
from epistemic_case_mapper.map_briefing_source_weighting_contract import build_source_weighting_fidelity_report


@dataclass(frozen=True)
class ModelBackendConfig:
    backend: str
    timeout: int | None
    retries: int


def write_final_reader_outputs(
    *,
    rendered: str,
    scaffold: dict[str, Any],
    prioritized_map: dict[str, Any],
    artifacts: Path,
    backend_config: ModelBackendConfig,
) -> dict[str, Any]:
    from epistemic_case_mapper.map_briefing_final_editor_artifacts import reader_memo_edit_artifact_paths
    from epistemic_case_mapper.map_briefing_memo_metadata import ensure_reader_memo_metadata
    from epistemic_case_mapper.map_briefing_reader_contracts import compose_final_reader_memo_package

    ensure_memo_progress(artifacts)
    record_memo_progress(artifacts, "final_reader_outputs", "started", backend=backend_config.backend)
    memo_package = compose_final_reader_memo_package(rendered, scaffold)
    record_memo_progress(artifacts, "compose_memo_package", "completed", backend=backend_config.backend)
    evidence_appendix = str(memo_package["appendix"])
    if not _should_use_memo_ready_packet(memo_package["scaffold"]):
        record_memo_progress(
            artifacts,
            "memo_output_path",
            "failed_missing_memo_ready_packet",
            backend=backend_config.backend,
        )
        raise ValueError(
            "write_final_reader_outputs requires scaffold.memo_ready_packet.evidence_items; "
            "the final reader output path requires a memo-ready packet"
        )
    record_memo_progress(artifacts, "memo_output_path", "memo_ready", backend=backend_config.backend)
    output_path_result = _run_memo_ready_final_output_path(
        memo_package=memo_package,
        backend_config=backend_config,
        artifacts=artifacts,
    )
    section_rewrite_result = output_path_result["section_rewrite_result"]
    rewrite_result = output_path_result["rewrite_result"]
    packet_plan_result = output_path_result.get("packet_plan_result")
    reader_packet_repair_result = output_path_result["reader_packet_repair_result"]
    packet_repair_result = output_path_result["packet_repair_result"]
    editorial_result = output_path_result["editorial_result"]
    memo_ready_synthesis_result = output_path_result["memo_ready_synthesis_result"]
    memo_ready_repair_result = output_path_result["memo_ready_repair_result"]
    memo_ready_final_polish_result = output_path_result["memo_ready_final_polish_result"]
    reader_memo = ensure_reader_memo_metadata(str(rewrite_result["memo"]), memo_package["scaffold"])
    record_memo_progress(
        artifacts,
        "metadata_and_diagnostics",
        "started",
        backend=backend_config.backend,
        details={"memo_words": len(reader_memo.split())},
    )
    paths = final_reader_output_paths(artifacts)
    diagnostics = _build_final_reader_diagnostics(
        reader_memo=reader_memo,
        evidence_appendix=evidence_appendix,
        memo_package=memo_package,
        prioritized_map=prioritized_map,
        section_rewrite_result=section_rewrite_result,
        rewrite_result=rewrite_result,
        packet_plan_result=packet_plan_result,
        reader_packet_repair_result=reader_packet_repair_result,
        packet_repair_result=packet_repair_result,
        editorial_result=editorial_result,
        memo_ready_synthesis_result=memo_ready_synthesis_result,
        memo_ready_repair_result=memo_ready_repair_result,
        memo_ready_final_polish_result=memo_ready_final_polish_result,
        briefing_path=paths.briefing,
    )
    edit_artifact_paths = reader_memo_edit_artifact_paths(artifacts)
    _write_final_reader_artifacts(
        paths=paths,
        edit_artifact_paths=edit_artifact_paths,
        reader_memo=reader_memo,
        evidence_appendix=evidence_appendix,
        memo_package=memo_package,
        section_rewrite_result=section_rewrite_result,
        rewrite_result=rewrite_result,
        reader_packet_repair_result=reader_packet_repair_result,
        packet_repair_result=packet_repair_result,
        editorial_result=editorial_result,
        memo_ready_synthesis_result=memo_ready_synthesis_result,
        memo_ready_repair_result=memo_ready_repair_result,
        memo_ready_final_polish_result=memo_ready_final_polish_result,
        diagnostics=diagnostics,
    )
    record_memo_progress(artifacts, "final_reader_outputs", "completed", backend=backend_config.backend)
    return {
        "briefing_path": paths.briefing,
        "evidence_appendix_path": paths.evidence_appendix,
        "briefing_validation": diagnostics["validation"],
        "polish_report": diagnostics["polish_report"],
        "rewrite_result": rewrite_result,
        "diagnostics": diagnostics,
        "summary_paths": _final_reader_summary_paths(
            paths,
            rewrite_result=rewrite_result,
            section_rewrite_result=section_rewrite_result,
            edit_artifact_paths=edit_artifact_paths,
            packet_plan_result=packet_plan_result,
            reader_packet_repair_result=reader_packet_repair_result,
            packet_repair_result=packet_repair_result,
            editorial_result=editorial_result,
            memo_ready_synthesis_result=memo_ready_synthesis_result,
            memo_ready_repair_result=memo_ready_repair_result,
            memo_ready_final_polish_result=memo_ready_final_polish_result,
        ),
    }


def _should_use_memo_ready_packet(scaffold: dict[str, Any]) -> bool:
    packet = scaffold.get("memo_ready_packet", {})
    return isinstance(packet, dict) and bool(packet.get("evidence_items"))


def _run_memo_ready_final_output_path(
    *,
    memo_package: dict[str, Any],
    backend_config: ModelBackendConfig,
    artifacts: Path,
) -> dict[str, Any]:
    from epistemic_case_mapper.map_briefing_memo_ready_finalization import (
        build_memo_ready_packet_retention_report,
        run_memo_ready_final_polish,
        run_memo_ready_packet_repair,
        run_memo_ready_presentation_normalization,
        run_memo_ready_packet_synthesis,
    )

    packet = memo_package["scaffold"].get("memo_ready_packet")
    memo_ready_packet = packet if isinstance(packet, dict) else {}
    writer_interface_quality = _attach_writer_interface(memo_package["scaffold"], memo_ready_packet)
    record_memo_progress(
        artifacts,
        "memo_ready_synthesis",
        "started",
        backend=backend_config.backend,
        details={
            "evidence_items": len(memo_ready_packet.get("evidence_items", [])) if isinstance(memo_ready_packet.get("evidence_items"), list) else 0,
            "writer_interface_visible_evidence": writer_interface_quality.get("must_use_evidence_count"),
            "writer_interface_excluded_evidence": writer_interface_quality.get("excluded_evidence_count"),
            "writer_interface_quantity_anchors": writer_interface_quality.get("quantity_anchor_count"),
            "writer_interface_reasoning_moves": writer_interface_quality.get("reasoning_move_count"),
            "writer_interface_rescued_context": writer_interface_quality.get("rescued_context_count"),
            "writer_interface_quality_status": writer_interface_quality.get("status"),
            "writer_interface_quality_warnings": writer_interface_quality.get("warnings", []),
        },
    )
    synthesis = run_memo_ready_packet_synthesis(
        memo_ready_packet,
        backend=backend_config.backend,
        backend_timeout=backend_config.timeout,
        backend_retries=backend_config.retries,
    )
    record_memo_progress(
        artifacts,
        "memo_ready_synthesis",
        "completed",
        backend=backend_config.backend,
        details=_progress_report_details(synthesis),
    )
    if _memo_ready_synthesis_failed(synthesis):
        rewrite_result = _memo_ready_rewrite_result(synthesis)
        failure_result = _memo_ready_failure_result(rewrite_result)
        return {
            "section_rewrite_result": failure_result,
            "rewrite_result": rewrite_result,
            "packet_plan_result": None,
            "reader_packet_repair_result": failure_result,
            "packet_repair_result": failure_result,
            "editorial_result": failure_result,
            "memo_ready_synthesis_result": synthesis,
            "memo_ready_repair_result": failure_result,
            "memo_ready_final_polish_result": failure_result,
        }
    section_rewrite_result = _memo_ready_section_rewrite_result(synthesis, artifacts=artifacts)
    memo_package["scaffold"]["section_context_acceptance_status"] = "ready"
    rewrite_result = _memo_ready_rewrite_result(synthesis)
    record_memo_progress(artifacts, "memo_ready_retention_check", "started", backend=backend_config.backend)
    retention = build_memo_ready_packet_retention_report(str(rewrite_result["memo"]), memo_ready_packet)
    record_memo_progress(
        artifacts,
        "memo_ready_retention_check",
        "completed",
        backend=backend_config.backend,
        details=_progress_report_details({"report": retention}),
    )
    record_memo_progress(artifacts, "memo_ready_repair", "started", backend=backend_config.backend)
    repair = run_memo_ready_packet_repair(
        str(rewrite_result["memo"]),
        memo_ready_packet,
        retention,
        backend=backend_config.backend,
        backend_timeout=backend_config.timeout,
        backend_retries=backend_config.retries,
    )
    record_memo_progress(
        artifacts,
        "memo_ready_repair",
        "completed",
        backend=backend_config.backend,
        details=_progress_report_details(repair),
    )
    rewrite_result["memo"] = repair["memo"]
    rewrite_result.setdefault("report", {})["memo_ready_repair_status"] = repair.get("report", {}).get("status")
    rewrite_result.setdefault("report", {})["active_memo_ready_packet_method"] = str(
        memo_ready_packet.get("method") or ""
    )
    pre_polish_presentation = run_memo_ready_presentation_normalization(str(rewrite_result["memo"]), memo_ready_packet)
    rewrite_result["memo"] = pre_polish_presentation["memo"]
    rewrite_result.setdefault("report", {})["memo_ready_pre_polish_presentation_normalization_status"] = pre_polish_presentation.get("report", {}).get("status")
    rewrite_result.setdefault("report", {})["memo_ready_pre_polish_presentation_normalization_changes"] = pre_polish_presentation.get("report", {}).get("changes", [])
    record_memo_progress(artifacts, "memo_ready_final_polish", "started", backend=backend_config.backend)
    final_polish = run_memo_ready_final_polish(
        str(rewrite_result["memo"]),
        memo_ready_packet,
        backend=backend_config.backend,
        backend_timeout=backend_config.timeout,
        backend_retries=backend_config.retries,
    )
    record_memo_progress(
        artifacts,
        "memo_ready_final_polish",
        "completed",
        backend=backend_config.backend,
        details=_progress_report_details(final_polish),
    )
    rewrite_result["memo"] = final_polish["memo"]
    rewrite_result.setdefault("report", {})["memo_ready_final_polish_status"] = final_polish.get("report", {}).get("status")
    presentation = run_memo_ready_presentation_normalization(str(rewrite_result["memo"]), memo_ready_packet)
    record_memo_progress(
        artifacts,
        "memo_ready_presentation_normalization",
        "completed",
        backend=backend_config.backend,
        details=_progress_report_details(presentation),
    )
    rewrite_result["memo"] = presentation["memo"]
    rewrite_result.setdefault("report", {})["memo_ready_presentation_normalization_status"] = presentation.get("report", {}).get("status")
    rewrite_result.setdefault("report", {})["memo_ready_presentation_normalization_changes"] = presentation.get("report", {}).get("changes", [])
    _attach_final_source_weighting_fidelity(rewrite_result, memo_ready_packet)
    return {
        "section_rewrite_result": section_rewrite_result,
        "rewrite_result": rewrite_result,
        "packet_plan_result": None,
        "reader_packet_repair_result": _not_needed_result(str(rewrite_result["memo"]), "not_needed_memo_ready_path"),
        "packet_repair_result": _not_needed_result(str(rewrite_result["memo"]), "not_needed_memo_ready_path"),
        "editorial_result": {"memo": str(rewrite_result["memo"]), "brief": {}, "prompt": "", "raw": "", "report": {"status": "not_needed_memo_ready_path"}},
        "memo_ready_synthesis_result": synthesis,
        "memo_ready_repair_result": repair,
        "memo_ready_final_polish_result": final_polish,
    }


def _attach_writer_interface(scaffold: dict[str, Any], memo_ready_packet: dict[str, Any]) -> dict[str, Any]:
    from epistemic_case_mapper.map_briefing_writer_decision_interface import (
        build_writer_decision_interface,
        build_writer_decision_interface_quality_report,
    )

    writer_interface = build_writer_decision_interface(memo_ready_packet)
    writer_interface_quality = build_writer_decision_interface_quality_report(writer_interface)
    scaffold["writer_decision_interface"] = writer_interface
    scaffold["writer_decision_interface_quality_report"] = writer_interface_quality
    return writer_interface_quality


def _attach_final_source_weighting_fidelity(rewrite_result: dict[str, Any], memo_ready_packet: dict[str, Any]) -> None:
    rewrite_result.setdefault("report", {})["final_source_weighting_fidelity_report"] = build_source_weighting_fidelity_report(
        str(rewrite_result.get("memo") or ""),
        memo_ready_packet,
    )


def _not_needed_result(memo: str, status: str) -> dict[str, Any]:
    return {"memo": memo, "prompt": "", "raw": "", "report": {"status": status}}


def _memo_ready_section_rewrite_result(synthesis_result: dict[str, Any], *, artifacts: Path) -> dict[str, Any]:
    return {
        "memo": synthesis_result.get("memo", ""),
        "section_context_acceptance_report_path": artifacts / "section_context_acceptance_report.json",
        "report": {
            "schema_id": "section_rewrite_report_v1",
            "status": "skipped_memo_ready_packet_path",
            "accepted_section_count": 0,
            "section_count": 0,
            "sections": [],
            "whole_validation_status": "not_run",
            "packet_first": True,
            "memo_ready_packet": True,
            "section_context_acceptance_status": "ready",
        },
    }


def _memo_ready_rewrite_result(synthesis_result: dict[str, Any]) -> dict[str, Any]:
    report = dict(synthesis_result.get("report", {}))
    status = str(report.get("status") or "unknown")
    report.update(
        {
            "status": f"memo_ready_synthesis_{status}",
            "memo_ready_packet_path": True,
            "pass_count": 1,
            "section_context_acceptance_status": "ready",
            "prompt_artifact_policy": "pass_through_no_separate_reader_rewrite_prompt",
        }
    )
    return {
        "memo": synthesis_result.get("memo", ""),
        "prompt": "",
        "raw": "",
        "report": report,
    }


def _memo_ready_synthesis_failed(synthesis_result: dict[str, Any]) -> bool:
    report = synthesis_result.get("report") if isinstance(synthesis_result, dict) else {}
    if not isinstance(report, dict):
        return True
    if report.get("accepted") is True:
        return False
    status = str(report.get("status") or "")
    return status in {
        "backend_error_live_enrichment_failed",
        "empty_or_unparseable_live_enrichment_failed",
        "section_synthesis_failed",
    }


def _memo_ready_failure_result(rewrite_result: dict[str, Any]) -> dict[str, Any]:
    report = dict(rewrite_result.get("report", {}))
    report.setdefault("status", "memo_ready_synthesis_failed")
    return {
        "memo": "",
        "prompt": "",
        "raw": "",
        "report": {
            **report,
            "accepted": False,
            "memo_ready_packet_path": True,
            "stopped_after_failed_synthesis": True,
        },
    }


def _progress_report_details(result: dict[str, Any]) -> dict[str, Any]:
    report = result.get("report", result) if isinstance(result, dict) else {}
    if not isinstance(report, dict):
        return {}
    keys = ("status", "accepted", "missing_mandatory_count", "unresolved_warning_count", "issue_count")
    details = {key: report[key] for key in keys if key in report}
    issues = report.get("issues")
    if "issue_count" not in details and isinstance(issues, list):
        details["issue_count"] = len(issues)
    return details


def _build_final_reader_diagnostics(
    *,
    reader_memo: str,
    evidence_appendix: str,
    memo_package: dict[str, Any],
    prioritized_map: dict[str, Any],
    section_rewrite_result: dict[str, Any],
    rewrite_result: dict[str, Any],
    packet_plan_result: dict[str, Any] | None,
    reader_packet_repair_result: dict[str, Any],
    packet_repair_result: dict[str, Any],
    editorial_result: dict[str, Any],
    memo_ready_synthesis_result: dict[str, Any],
    memo_ready_repair_result: dict[str, Any],
    memo_ready_final_polish_result: dict[str, Any],
    briefing_path: Path,
) -> dict[str, Any]:
    from epistemic_case_mapper.decision_argument_artifacts import evaluate_traceability_against_memo
    from epistemic_case_mapper.decision_frame import memo_quality_report
    from epistemic_case_mapper.map_briefing_context_reports import (
        build_final_brief_evaluation,
        build_memo_coherence_report,
        build_pipeline_migration_ledger,
    )
    from epistemic_case_mapper.map_briefing_measurement_audit import (
        build_final_source_lineage_report,
        build_pipeline_measurement_audit,
        build_scoped_metric_report,
    )
    from epistemic_case_mapper.map_briefing_packet_comparison import build_packet_first_comparison_report
    from epistemic_case_mapper.map_briefing_packet_retention import build_memo_packet_retention_report
    from epistemic_case_mapper.map_briefing_readiness import build_final_decision_readiness_report, build_memo_semantic_acceptance_report
    from epistemic_case_mapper.map_briefing_reader_polish import briefing_reader_polish_report
    from epistemic_case_mapper.map_briefing_runtime_telemetry import build_runtime_budget_report, build_stage_value_report
    from epistemic_case_mapper.map_briefing_section_role_quality import section_role_quality_report
    from epistemic_case_mapper.map_briefing_validation import validate_briefing_against_scaffold

    combined = reader_memo.rstrip() + "\n\n" + evidence_appendix.rstrip() + "\n"
    polish_report = briefing_reader_polish_report(combined, memo_package["scaffold"])
    memo_quality = memo_quality_report(combined, memo_package["scaffold"])
    validation = validate_briefing_against_scaffold(combined, memo_package["scaffold"], prioritized_map)
    argument_artifacts = memo_package["scaffold"].get("decision_argument_artifacts", {})
    traceability_matrix = evaluate_traceability_against_memo(
        argument_artifacts.get("decision_traceability_matrix", {}) if isinstance(argument_artifacts, dict) else {},
        reader_memo,
    )
    memo_coherence = build_memo_coherence_report(
        memo_markdown=reader_memo,
        decision_question=str(memo_package["scaffold"].get("question", "")),
        scaffold=memo_package["scaffold"],
    )
    role_quality = section_role_quality_report(reader_memo, {"question": str(memo_package["scaffold"].get("question", ""))})
    pipeline_migration = build_pipeline_migration_ledger(
        section_context_acceptance_path=str(section_rewrite_result.get("section_context_acceptance_report_path") or ""),
        scaffold=memo_package["scaffold"],
    )
    runtime_budget = build_runtime_budget_report(
        section_rewrite_report=section_rewrite_result.get("report", {}),
        reader_rewrite_report=rewrite_result.get("report", {}),
        scaffold=memo_package["scaffold"],
        packet_plan_report=packet_plan_result.get("report", {}) if packet_plan_result else {},
        reader_packet_repair_report=reader_packet_repair_result.get("report", {}),
        packet_repair_report=packet_repair_result.get("report", {}),
        editorial_report=editorial_result.get("report", {}),
    )
    final_eval = build_final_brief_evaluation(
        memo_markdown=reader_memo,
        memo_path=str(briefing_path),
        decision_question=str(memo_package["scaffold"].get("question", "")),
        coherence_report=memo_coherence,
        scaffold=memo_package["scaffold"],
    )
    packet_retention = _build_packet_retention_for_final_memo(reader_memo, memo_package["scaffold"])
    stage_value = build_stage_value_report(
        scaffold=memo_package["scaffold"],
        section_rewrite_report=section_rewrite_result.get("report", {}),
        reader_rewrite_report=rewrite_result.get("report", {}),
        packet_retention_report=packet_retention,
        final_evaluation=final_eval,
    )
    final_readiness = build_final_decision_readiness_report(scaffold=memo_package["scaffold"], validation_report=validation, memo_coherence_report=memo_coherence, packet_retention_report=packet_retention, final_evaluation=final_eval)
    semantic_acceptance = build_memo_semantic_acceptance_report(final_readiness_report=final_readiness, memo_quality_report=memo_quality, polish_report=polish_report, validation_report=validation, packet_retention_report=packet_retention, final_evaluation=final_eval)
    packet_comparison = build_packet_first_comparison_report(
        scaffold=memo_package["scaffold"],
        section_rewrite_report=section_rewrite_result.get("report", {}),
        reader_rewrite_report=rewrite_result.get("report", {}),
        runtime_budget_report=runtime_budget,
        memo_packet_retention_report=packet_retention,
    )
    source_lineage = build_final_source_lineage_report(reader_memo, memo_package["scaffold"])
    scoped_metrics = build_scoped_metric_report(
        scaffold=memo_package["scaffold"],
        prioritized_map=prioritized_map,
        runtime_budget_report=runtime_budget,
        packet_retention_report=packet_retention,
    )
    measurement_audit = build_pipeline_measurement_audit(
        scoped_metric_report=scoped_metrics,
        source_lineage_report=source_lineage,
        relation_value_report=memo_package["scaffold"].get("relation_value_report", {}),
        packet_retention_report=packet_retention,
        runtime_budget_report=runtime_budget,
        section_role_quality_report=role_quality,
    )
    return {
        "polish_report": polish_report,
        "memo_quality": memo_quality,
        "validation": validation,
        "traceability_matrix": traceability_matrix,
        "memo_coherence": memo_coherence,
        "role_quality": role_quality,
        "pipeline_migration": pipeline_migration,
        "runtime_budget": runtime_budget,
        "stage_value": stage_value,
        "final_eval": final_eval,
        "final_readiness": final_readiness,
        "semantic_acceptance": semantic_acceptance,
        "packet_retention": packet_retention,
        "packet_comparison": packet_comparison,
        "source_lineage": source_lineage,
        "scoped_metrics": scoped_metrics,
        "measurement_audit": measurement_audit,
    }


def _write_final_reader_artifacts(
    *,
    paths: FinalReaderOutputPaths,
    edit_artifact_paths: dict[str, Path],
    reader_memo: str,
    evidence_appendix: str,
    memo_package: dict[str, Any],
    section_rewrite_result: dict[str, Any],
    rewrite_result: dict[str, Any],
    reader_packet_repair_result: dict[str, Any],
    packet_repair_result: dict[str, Any],
    editorial_result: dict[str, Any],
    memo_ready_synthesis_result: dict[str, Any],
    memo_ready_repair_result: dict[str, Any],
    memo_ready_final_polish_result: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    from epistemic_case_mapper.decision_argument_artifacts import render_decision_traceability_matrix_markdown
    from epistemic_case_mapper.map_briefing_final_editor_artifacts import write_reader_memo_edit_artifacts
    from epistemic_case_mapper.map_briefing_canonical_decision_writer_packet import build_canonical_decision_writer_packet
    from epistemic_case_mapper.map_briefing_citation_trace import build_citation_trace_markdown

    if rewrite_result.get("prompt"):
        write_markdown(paths.reader_memo_rewrite_prompt, str(rewrite_result.get("prompt", "")))
    if rewrite_result.get("raw"):
        write_markdown(paths.reader_memo_rewrite_raw, str(rewrite_result.get("raw", "")))
    if reader_packet_repair_result.get("prompt"):
        write_markdown(paths.reader_packet_repair_prompt, str(reader_packet_repair_result.get("prompt", "")))
    if reader_packet_repair_result.get("raw"):
        write_markdown(paths.reader_packet_repair_raw, str(reader_packet_repair_result.get("raw", "")))
    if packet_repair_result.get("prompt"):
        write_markdown(paths.packet_repair_prompt, str(packet_repair_result.get("prompt", "")))
    if packet_repair_result.get("raw"):
        write_markdown(paths.packet_repair_raw, str(packet_repair_result.get("raw", "")))
    if editorial_result.get("prompt"):
        write_markdown(paths.decision_memo_editorial_prompt, str(editorial_result.get("prompt", "")))
    if editorial_result.get("raw"):
        write_markdown(paths.decision_memo_editorial_raw, str(editorial_result.get("raw", "")))
    if memo_ready_synthesis_result.get("prompt"):
        write_markdown(paths.memo_ready_synthesis_prompt, str(memo_ready_synthesis_result.get("prompt", "")))
    if memo_ready_synthesis_result.get("raw"):
        write_markdown(paths.memo_ready_synthesis_raw, str(memo_ready_synthesis_result.get("raw", "")))
    if memo_ready_synthesis_result.get("evidence_expression_contracts"):
        write_json(paths.evidence_expression_contracts, memo_ready_synthesis_result.get("evidence_expression_contracts", []))
    if memo_ready_synthesis_result.get("evidence_trace"):
        write_json(paths.evidence_trace, memo_ready_synthesis_result.get("evidence_trace", []))
    if memo_ready_synthesis_result.get("evidence_reconciliation_report"):
        write_json(paths.evidence_reconciliation_report, memo_ready_synthesis_result.get("evidence_reconciliation_report", {}))
    if memo_ready_synthesis_result.get("evidence_tag_section_reports"):
        write_json(paths.evidence_tag_section_reports, memo_ready_synthesis_result.get("evidence_tag_section_reports", []))
    if memo_ready_repair_result.get("prompt"):
        write_markdown(paths.memo_ready_repair_prompt, str(memo_ready_repair_result.get("prompt", "")))
    if memo_ready_repair_result.get("raw"):
        write_markdown(paths.memo_ready_repair_raw, str(memo_ready_repair_result.get("raw", "")))
    if memo_ready_final_polish_result.get("prompt"):
        write_markdown(paths.memo_ready_final_polish_prompt, str(memo_ready_final_polish_result.get("prompt", "")))
    if memo_ready_final_polish_result.get("raw"):
        write_markdown(paths.memo_ready_final_polish_raw, str(memo_ready_final_polish_result.get("raw", "")))
    if memo_ready_final_polish_result.get("repair_prompt"):
        write_markdown(
            paths.memo_ready_final_polish_repair_prompt,
            str(memo_ready_final_polish_result.get("repair_prompt", "")),
        )
    if memo_ready_final_polish_result.get("repair_raw"):
        write_markdown(paths.memo_ready_final_polish_repair_raw, str(memo_ready_final_polish_result.get("repair_raw", "")))
    write_reader_memo_edit_artifacts(rewrite_result, edit_artifact_paths)
    write_markdown(paths.briefing, reader_memo.rstrip() + "\n")
    write_markdown(paths.evidence_appendix, evidence_appendix.rstrip() + "\n")
    write_markdown(
        paths.citation_trace,
        build_citation_trace_markdown(reader_memo, memo_package["scaffold"].get("memo_ready_packet", {})),
    )
    memo_ready_packet = memo_package["scaffold"].get("memo_ready_packet", {})
    canonical_packet = memo_ready_packet.get("canonical_decision_writer_packet", {}) if isinstance(memo_ready_packet, dict) else {}
    if not canonical_packet and isinstance(memo_ready_packet, dict) and memo_ready_packet.get("evidence_items"):
        canonical_packet = build_canonical_decision_writer_packet(memo_ready_packet)
    argument_spine = canonical_packet.get("evidence_weighted_argument_spine", {}) if isinstance(canonical_packet, dict) else {}
    write_json(paths.canonical_decision_writer_packet, canonical_packet)
    write_json(paths.canonical_decision_writer_packet_quality, canonical_packet.get("quality_report", {}) if isinstance(canonical_packet, dict) else {})
    write_json(paths.source_weight_judgment_report, canonical_packet.get("source_weight_judgment_report", {}) if isinstance(canonical_packet, dict) else {})
    write_json(paths.argument_spine_quality_report, argument_spine.get("quality_report", {}) if isinstance(argument_spine, dict) else {})
    write_json(paths.canonical_writer_prompt_context_audit, _canonical_writer_prompt_context_audit(memo_ready_synthesis_result))
    write_json(paths.final_traceability, diagnostics["traceability_matrix"])
    write_markdown(paths.final_traceability_markdown, render_decision_traceability_matrix_markdown(diagnostics["traceability_matrix"]))
    write_json(paths.memo_coherence, diagnostics["memo_coherence"])
    write_json(paths.section_role_quality, diagnostics["role_quality"])
    write_json(paths.pipeline_migration_ledger, diagnostics["pipeline_migration"])
    write_json(paths.runtime_budget, diagnostics["runtime_budget"])
    write_json(paths.stage_value, diagnostics["stage_value"])
    write_json(paths.final_brief_evaluation, diagnostics["final_eval"])
    write_json(paths.final_decision_readiness, diagnostics["final_readiness"])
    write_json(paths.memo_semantic_acceptance, diagnostics["semantic_acceptance"])
    write_json(paths.memo_packet_retention, diagnostics["packet_retention"])
    write_json(paths.packet_first_comparison, diagnostics["packet_comparison"])
    write_json(paths.reader_packet_repair_report, reader_packet_repair_result.get("report", {}))
    write_json(paths.packet_repair_report, packet_repair_result.get("report", {}))
    write_json(paths.decision_memo_editorial_brief, editorial_result.get("brief", {}))
    write_json(paths.decision_memo_editorial_report, editorial_result.get("report", {}))
    write_json(paths.memo_ready_synthesis_report, memo_ready_synthesis_result.get("report", {}))
    write_json(paths.memo_ready_repair_report, memo_ready_repair_result.get("report", {}))
    write_json(paths.memo_ready_final_polish_report, memo_ready_final_polish_result.get("report", {}))
    write_json(paths.final_source_lineage, diagnostics["source_lineage"])
    write_json(paths.scoped_metric_report, diagnostics["scoped_metrics"])
    write_json(paths.pipeline_measurement_audit, diagnostics["measurement_audit"])
    write_json(paths.briefing_validation, diagnostics["validation"])
    write_json(paths.polish_report, diagnostics["polish_report"])
    write_json(paths.memo_quality, diagnostics["memo_quality"])
    write_json(paths.curation_report, memo_package["curation_report"])
    write_json(paths.section_rewrite_report, section_rewrite_result["report"])
    write_json(paths.reader_memo_rewrite_report, rewrite_result["report"])


def _final_reader_summary_paths(
    paths: FinalReaderOutputPaths,
    *,
    rewrite_result: dict[str, Any],
    section_rewrite_result: dict[str, Any],
    edit_artifact_paths: dict[str, Path],
    packet_plan_result: dict[str, Any] | None = None,
    reader_packet_repair_result: dict[str, Any] | None = None,
    packet_repair_result: dict[str, Any] | None = None,
    editorial_result: dict[str, Any] | None = None,
    memo_ready_synthesis_result: dict[str, Any] | None = None,
    memo_ready_repair_result: dict[str, Any] | None = None,
    memo_ready_final_polish_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from epistemic_case_mapper.map_briefing_final_editor_artifacts import reader_memo_edit_summary_paths

    return {
        "briefing_validation_report": paths.briefing_validation,
        "briefing_polish_report": paths.polish_report,
        "memo_quality_report": paths.memo_quality,
        "evidence_curation_report": paths.curation_report,
        "citation_trace": paths.citation_trace,
        "canonical_decision_writer_packet": paths.canonical_decision_writer_packet,
        "canonical_decision_writer_packet_quality_report": paths.canonical_decision_writer_packet_quality,
        "source_weight_judgment_report": paths.source_weight_judgment_report,
        "argument_spine_quality_report": paths.argument_spine_quality_report,
        "canonical_writer_prompt_context_audit": paths.canonical_writer_prompt_context_audit,
        "section_rewrite_report": paths.section_rewrite_report,
        "section_synthesis_packets": section_rewrite_result.get("section_packets_path"),
        "section_context_acceptance_report": section_rewrite_result.get("section_context_acceptance_report_path"),
        "decision_traceability_matrix_final": paths.final_traceability,
        "decision_traceability_matrix_final_markdown": paths.final_traceability_markdown,
        "memo_coherence_report": paths.memo_coherence,
        "section_role_quality_report": paths.section_role_quality,
        "pipeline_migration_ledger": paths.pipeline_migration_ledger,
        "runtime_budget_report": paths.runtime_budget,
        "stage_value_report": paths.stage_value,
        "final_brief_evaluation": paths.final_brief_evaluation,
        "final_decision_readiness_report": paths.final_decision_readiness,
        "memo_semantic_acceptance_report": paths.memo_semantic_acceptance,
        "reader_memo_rewrite_report": paths.reader_memo_rewrite_report,
        "memo_packet_retention_report": paths.memo_packet_retention,
        "packet_first_comparison_report": paths.packet_first_comparison,
        "reader_packet_repair_report": paths.reader_packet_repair_report,
        "reader_packet_repair_prompt": paths.reader_packet_repair_prompt
        if reader_packet_repair_result and reader_packet_repair_result.get("prompt")
        else None,
        "reader_packet_repair_raw": paths.reader_packet_repair_raw
        if reader_packet_repair_result and reader_packet_repair_result.get("raw")
        else None,
        "packet_repair_report": paths.packet_repair_report,
        "packet_repair_prompt": paths.packet_repair_prompt if packet_repair_result and packet_repair_result.get("prompt") else None,
        "packet_repair_raw": paths.packet_repair_raw if packet_repair_result and packet_repair_result.get("raw") else None,
        "decision_memo_editorial_brief": paths.decision_memo_editorial_brief,
        "decision_memo_editorial_report": paths.decision_memo_editorial_report,
        "scoped_metric_report": paths.scoped_metric_report,
        "final_source_lineage_report": paths.final_source_lineage,
        "pipeline_measurement_audit": paths.pipeline_measurement_audit,
        "decision_memo_editorial_prompt": paths.decision_memo_editorial_prompt
        if editorial_result and editorial_result.get("prompt")
        else None,
        "decision_memo_editorial_raw": paths.decision_memo_editorial_raw if editorial_result and editorial_result.get("raw") else None,
        "reader_memo_rewrite_prompt": paths.reader_memo_rewrite_prompt if rewrite_result.get("prompt") else None,
        "reader_memo_rewrite_raw": paths.reader_memo_rewrite_raw if rewrite_result.get("raw") else None,
        **_memo_ready_summary_paths(
            paths,
            synthesis_result=memo_ready_synthesis_result,
            repair_result=memo_ready_repair_result,
            final_polish_result=memo_ready_final_polish_result,
        ),
        "memo_plan": packet_plan_result.get("memo_plan_path") if packet_plan_result else None,
        "packet_first_draft": packet_plan_result.get("packet_first_draft_path") if packet_plan_result else None,
        "reader_packet_verbalization_report": packet_plan_result.get("reader_packet_verbalization_report_path") if packet_plan_result else None,
        "reader_packet_verbalization_prompt": packet_plan_result.get("reader_packet_verbalization_prompt_path") if packet_plan_result else None,
        "reader_packet_verbalization_raw": packet_plan_result.get("reader_packet_verbalization_raw_path") if packet_plan_result else None,
        **reader_memo_edit_summary_paths(rewrite_result, edit_artifact_paths),
    }


def _memo_ready_summary_paths(
    paths: FinalReaderOutputPaths,
    *,
    synthesis_result: dict[str, Any] | None,
    repair_result: dict[str, Any] | None,
    final_polish_result: dict[str, Any] | None,
) -> dict[str, Path | None]:
    return {
        "memo_ready_synthesis_report": paths.memo_ready_synthesis_report,
        "memo_ready_synthesis_prompt": paths.memo_ready_synthesis_prompt if synthesis_result and synthesis_result.get("prompt") else None,
        "memo_ready_synthesis_raw": paths.memo_ready_synthesis_raw if synthesis_result and synthesis_result.get("raw") else None,
        "evidence_expression_contracts": paths.evidence_expression_contracts
        if synthesis_result and synthesis_result.get("evidence_expression_contracts")
        else None,
        "evidence_trace": paths.evidence_trace if synthesis_result and synthesis_result.get("evidence_trace") else None,
        "evidence_reconciliation_report": paths.evidence_reconciliation_report
        if synthesis_result and synthesis_result.get("evidence_reconciliation_report")
        else None,
        "evidence_tag_section_reports": paths.evidence_tag_section_reports
        if synthesis_result and synthesis_result.get("evidence_tag_section_reports")
        else None,
        "memo_ready_repair_report": paths.memo_ready_repair_report,
        "memo_ready_repair_prompt": paths.memo_ready_repair_prompt if repair_result and repair_result.get("prompt") else None,
        "memo_ready_repair_raw": paths.memo_ready_repair_raw if repair_result and repair_result.get("raw") else None,
        "memo_ready_final_polish_report": paths.memo_ready_final_polish_report,
        "memo_ready_final_polish_prompt": paths.memo_ready_final_polish_prompt if final_polish_result and final_polish_result.get("prompt") else None,
        "memo_ready_final_polish_raw": paths.memo_ready_final_polish_raw if final_polish_result and final_polish_result.get("raw") else None,
        "memo_ready_final_polish_repair_prompt": paths.memo_ready_final_polish_repair_prompt
        if final_polish_result and final_polish_result.get("repair_prompt")
        else None,
        "memo_ready_final_polish_repair_raw": paths.memo_ready_final_polish_repair_raw
        if final_polish_result and final_polish_result.get("repair_raw")
        else None,
        "memo_creation_progress": memo_progress_path(paths.briefing.parent),
    }


def _canonical_writer_prompt_context_audit(memo_ready_synthesis_result: dict[str, Any]) -> dict[str, Any]:
    prompt = str(memo_ready_synthesis_result.get("prompt") or "")
    retired = [
        "writer_model_context_v1",
        "reader_brief_plan",
        "decision_interpretation_plan",
        "analytical_balance_contract",
        "decision_boundary_source_contract",
        "adaptive_memo_outline",
    ]
    present = [token for token in retired if token in prompt]
    return {
        "schema_id": "canonical_writer_prompt_context_audit_v1",
        "status": "pass" if "canonical_decision_writer_packet_v1" in prompt and not present else "warning",
        "canonical_packet_present": "canonical_decision_writer_packet_v1" in prompt,
        "retired_context_surfaces_present": present,
        "prompt_character_count": len(prompt),
    }


def _build_packet_retention_for_final_memo(reader_memo: str, scaffold: dict[str, Any]) -> dict[str, Any]:
    if _should_use_memo_ready_packet(scaffold):
        from epistemic_case_mapper.map_briefing_memo_ready_finalization import build_memo_ready_packet_retention_report

        packet = scaffold.get("memo_ready_packet")
        return build_memo_ready_packet_retention_report(reader_memo, packet if isinstance(packet, dict) else {})
    from epistemic_case_mapper.map_briefing_packet_retention import build_memo_packet_retention_report

    return build_memo_packet_retention_report(reader_memo, scaffold.get("decision_briefing_packet"))
