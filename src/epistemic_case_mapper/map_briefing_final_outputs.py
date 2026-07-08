from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown


@dataclass(frozen=True)
class ModelBackendConfig:
    backend: str
    timeout: int | None
    retries: int


@dataclass(frozen=True)
class FinalReaderOutputPaths:
    briefing: Path
    evidence_appendix: Path
    polish_report: Path
    memo_quality: Path
    curation_report: Path
    briefing_validation: Path
    final_traceability: Path
    final_traceability_markdown: Path
    memo_coherence: Path
    section_role_quality: Path
    pipeline_migration_ledger: Path
    runtime_budget: Path
    final_brief_evaluation: Path
    section_rewrite_report: Path
    reader_memo_rewrite_prompt: Path
    reader_memo_rewrite_raw: Path
    reader_memo_rewrite_report: Path
    memo_packet_retention: Path
    packet_first_comparison: Path
    packet_repair_prompt: Path
    packet_repair_raw: Path
    packet_repair_report: Path
    reader_packet_repair_prompt: Path
    reader_packet_repair_raw: Path
    reader_packet_repair_report: Path


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
    from epistemic_case_mapper.map_briefing_packet_memo import (
        packet_first_section_rewrite_result,
        write_packet_first_artifacts,
    )
    from epistemic_case_mapper.map_briefing_packet_repair import run_packet_retention_repair
    from epistemic_case_mapper.map_briefing_packet_retention import build_memo_packet_retention_report
    from epistemic_case_mapper.map_briefing_reader_contracts import compose_final_reader_memo_package
    from epistemic_case_mapper.map_briefing_section_rewrite import rewrite_reader_memo_by_section

    memo_package = compose_final_reader_memo_package(rendered, scaffold)
    evidence_appendix = str(memo_package["appendix"])
    packet_first = _should_use_packet_first(memo_package["scaffold"])
    packet_plan_result = None
    if packet_first:
        packet_plan_result = write_packet_first_artifacts(
            artifacts=artifacts,
            packet=memo_package["scaffold"]["decision_briefing_packet"],
        )
        section_rewrite_result = packet_first_section_rewrite_result(packet_plan_result)
    else:
        section_rewrite_result = rewrite_reader_memo_by_section(
            str(memo_package["memo"]),
            evidence_appendix,
            memo_package["scaffold"],
            prioritized_map,
            backend=backend_config.backend,
            backend_timeout=backend_config.timeout,
            backend_retries=backend_config.retries,
            artifacts=artifacts,
        )
    rewrite_result = _run_reader_memo_rewrite(
        section_memo=str(section_rewrite_result["memo"]),
        evidence_appendix=evidence_appendix,
        memo_package=memo_package,
        prioritized_map=prioritized_map,
        backend_config=backend_config,
    )
    _attach_section_context_status(memo_package, rewrite_result, section_rewrite_result)
    packet_repair_result = {"memo": str(rewrite_result["memo"]), "prompt": "", "raw": "", "report": {"status": "not_needed"}}
    packet = memo_package["scaffold"].get("decision_briefing_packet")
    if isinstance(packet, dict) and packet.get("must_retain_ledger"):
        from epistemic_case_mapper.map_briefing_reader_packet_repair import run_reader_packet_retention_repair

        reader_packet_repair_result = run_reader_packet_retention_repair(
            str(rewrite_result["memo"]),
            packet,
            backend=backend_config.backend,
            backend_timeout=backend_config.timeout,
            backend_retries=backend_config.retries,
        )
        rewrite_result["memo"] = reader_packet_repair_result["memo"]
        rewrite_result.setdefault("report", {})["reader_packet_retention_repair_status"] = reader_packet_repair_result.get("report", {}).get("status")
        pre_repair_retention = build_memo_packet_retention_report(str(rewrite_result["memo"]), packet)
        packet_repair_result = run_packet_retention_repair(
            str(rewrite_result["memo"]),
            packet,
            pre_repair_retention,
            backend=backend_config.backend,
            backend_timeout=backend_config.timeout,
            backend_retries=backend_config.retries,
        )
        rewrite_result["memo"] = packet_repair_result["memo"]
        rewrite_result.setdefault("report", {})["packet_retention_repair_status"] = packet_repair_result.get("report", {}).get("status")
    else:
        reader_packet_repair_result = {"memo": str(rewrite_result["memo"]), "prompt": "", "raw": "", "report": {"status": "not_needed"}}
    reader_memo = ensure_reader_memo_metadata(str(rewrite_result["memo"]), memo_package["scaffold"])
    paths = _final_reader_output_paths(artifacts)
    diagnostics = _build_final_reader_diagnostics(
        reader_memo=reader_memo,
        evidence_appendix=evidence_appendix,
        memo_package=memo_package,
        prioritized_map=prioritized_map,
        section_rewrite_result=section_rewrite_result,
        rewrite_result=rewrite_result,
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
        diagnostics=diagnostics,
    )
    return {
        "briefing_path": paths.briefing,
        "evidence_appendix_path": paths.evidence_appendix,
        "briefing_validation": diagnostics["validation"],
        "polish_report": diagnostics["polish_report"],
        "rewrite_result": rewrite_result,
        "summary_paths": _final_reader_summary_paths(
            paths,
            rewrite_result=rewrite_result,
            section_rewrite_result=section_rewrite_result,
            edit_artifact_paths=edit_artifact_paths,
            packet_plan_result=packet_plan_result,
            reader_packet_repair_result=reader_packet_repair_result,
            packet_repair_result=packet_repair_result,
        ),
    }


def _should_use_packet_first(scaffold: dict[str, Any]) -> bool:
    packet = scaffold.get("decision_briefing_packet", {})
    if not isinstance(packet, dict) or not packet.get("evidence_bundles"):
        return False
    return True


def _run_reader_memo_rewrite(
    *,
    section_memo: str,
    evidence_appendix: str,
    memo_package: dict[str, Any],
    prioritized_map: dict[str, Any],
    backend_config: ModelBackendConfig,
) -> dict[str, Any]:
    from epistemic_case_mapper.map_briefing_reader_contracts import rewrite_reader_memo_with_contract

    return rewrite_reader_memo_with_contract(
        section_memo,
        evidence_appendix,
        memo_package["scaffold"],
        prioritized_map,
        backend=backend_config.backend,
        backend_timeout=backend_config.timeout,
        backend_retries=backend_config.retries,
    )


def _attach_section_context_status(
    memo_package: dict[str, Any],
    rewrite_result: dict[str, Any],
    section_rewrite_result: dict[str, Any],
) -> None:
    rewrite_result.setdefault("report", {})["section_context_acceptance_status"] = section_rewrite_result.get("report", {}).get(
        "section_context_acceptance_status"
    )
    memo_package["scaffold"]["section_context_acceptance_status"] = rewrite_result["report"]["section_context_acceptance_status"]


def _final_reader_output_paths(artifacts: Path) -> FinalReaderOutputPaths:
    return FinalReaderOutputPaths(
        briefing=artifacts / "BRIEFING.md",
        evidence_appendix=artifacts / "EVIDENCE_APPENDIX.md",
        polish_report=artifacts / "briefing_polish_report.json",
        memo_quality=artifacts / "memo_quality_report.json",
        curation_report=artifacts / "evidence_curation_report.json",
        briefing_validation=artifacts / "briefing_validation_report.json",
        final_traceability=artifacts / "decision_traceability_matrix_final.json",
        final_traceability_markdown=artifacts / "DECISION_TRACEABILITY_MATRIX_FINAL.md",
        memo_coherence=artifacts / "memo_coherence_report.json",
        section_role_quality=artifacts / "section_role_quality_report.json",
        pipeline_migration_ledger=artifacts / "pipeline_migration_ledger.json",
        runtime_budget=artifacts / "runtime_budget_report.json",
        final_brief_evaluation=artifacts / "final_brief_evaluation.json",
        section_rewrite_report=artifacts / "section_rewrite_report.json",
        reader_memo_rewrite_prompt=artifacts / "reader_memo_rewrite_prompt.txt",
        reader_memo_rewrite_raw=artifacts / "reader_memo_rewrite_raw.txt",
        reader_memo_rewrite_report=artifacts / "reader_memo_rewrite_report.json",
        memo_packet_retention=artifacts / "memo_packet_retention_report.json",
        packet_first_comparison=artifacts / "packet_first_comparison_report.json",
        packet_repair_prompt=artifacts / "packet_repair_prompt.txt",
        packet_repair_raw=artifacts / "packet_repair_raw.md",
        packet_repair_report=artifacts / "packet_repair_report.json",
        reader_packet_repair_prompt=artifacts / "reader_packet_repair_prompt.txt",
        reader_packet_repair_raw=artifacts / "reader_packet_repair_raw.md",
        reader_packet_repair_report=artifacts / "reader_packet_repair_report.json",
    )


def _build_final_reader_diagnostics(
    *,
    reader_memo: str,
    evidence_appendix: str,
    memo_package: dict[str, Any],
    prioritized_map: dict[str, Any],
    section_rewrite_result: dict[str, Any],
    rewrite_result: dict[str, Any],
    briefing_path: Path,
) -> dict[str, Any]:
    from epistemic_case_mapper.decision_argument_artifacts import evaluate_traceability_against_memo
    from epistemic_case_mapper.decision_frame import memo_quality_report
    from epistemic_case_mapper.map_briefing_context_reports import (
        build_final_brief_evaluation,
        build_memo_coherence_report,
        build_pipeline_migration_ledger,
        build_runtime_budget_report,
    )
    from epistemic_case_mapper.map_briefing_packet_comparison import build_packet_first_comparison_report
    from epistemic_case_mapper.map_briefing_packet_retention import build_memo_packet_retention_report
    from epistemic_case_mapper.map_briefing_reader_polish import briefing_reader_polish_report
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
    )
    final_eval = build_final_brief_evaluation(
        memo_markdown=reader_memo,
        memo_path=str(briefing_path),
        decision_question=str(memo_package["scaffold"].get("question", "")),
        coherence_report=memo_coherence,
        scaffold=memo_package["scaffold"],
    )
    packet_retention = build_memo_packet_retention_report(
        reader_memo,
        memo_package["scaffold"].get("decision_briefing_packet"),
    )
    packet_comparison = build_packet_first_comparison_report(
        scaffold=memo_package["scaffold"],
        section_rewrite_report=section_rewrite_result.get("report", {}),
        reader_rewrite_report=rewrite_result.get("report", {}),
        runtime_budget_report=runtime_budget,
        memo_packet_retention_report=packet_retention,
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
        "final_eval": final_eval,
        "packet_retention": packet_retention,
        "packet_comparison": packet_comparison,
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
    diagnostics: dict[str, Any],
) -> None:
    from epistemic_case_mapper.decision_argument_artifacts import render_decision_traceability_matrix_markdown
    from epistemic_case_mapper.map_briefing_final_editor_artifacts import write_reader_memo_edit_artifacts

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
    write_reader_memo_edit_artifacts(rewrite_result, edit_artifact_paths)
    write_markdown(paths.briefing, reader_memo.rstrip() + "\n")
    write_markdown(paths.evidence_appendix, evidence_appendix.rstrip() + "\n")
    write_json(paths.final_traceability, diagnostics["traceability_matrix"])
    write_markdown(paths.final_traceability_markdown, render_decision_traceability_matrix_markdown(diagnostics["traceability_matrix"]))
    write_json(paths.memo_coherence, diagnostics["memo_coherence"])
    write_json(paths.section_role_quality, diagnostics["role_quality"])
    write_json(paths.pipeline_migration_ledger, diagnostics["pipeline_migration"])
    write_json(paths.runtime_budget, diagnostics["runtime_budget"])
    write_json(paths.final_brief_evaluation, diagnostics["final_eval"])
    write_json(paths.memo_packet_retention, diagnostics["packet_retention"])
    write_json(paths.packet_first_comparison, diagnostics["packet_comparison"])
    write_json(paths.reader_packet_repair_report, reader_packet_repair_result.get("report", {}))
    write_json(paths.packet_repair_report, packet_repair_result.get("report", {}))
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
) -> dict[str, Any]:
    from epistemic_case_mapper.map_briefing_final_editor_artifacts import reader_memo_edit_summary_paths

    return {
        "briefing_validation_report": paths.briefing_validation,
        "briefing_polish_report": paths.polish_report,
        "memo_quality_report": paths.memo_quality,
        "evidence_curation_report": paths.curation_report,
        "section_rewrite_report": paths.section_rewrite_report,
        "section_synthesis_packets": section_rewrite_result.get("section_packets_path"),
        "section_context_acceptance_report": section_rewrite_result.get("section_context_acceptance_report_path"),
        "decision_traceability_matrix_final": paths.final_traceability,
        "decision_traceability_matrix_final_markdown": paths.final_traceability_markdown,
        "memo_coherence_report": paths.memo_coherence,
        "section_role_quality_report": paths.section_role_quality,
        "pipeline_migration_ledger": paths.pipeline_migration_ledger,
        "runtime_budget_report": paths.runtime_budget,
        "final_brief_evaluation": paths.final_brief_evaluation,
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
        "reader_memo_rewrite_prompt": paths.reader_memo_rewrite_prompt if rewrite_result.get("prompt") else None,
        "reader_memo_rewrite_raw": paths.reader_memo_rewrite_raw if rewrite_result.get("raw") else None,
        "memo_plan": packet_plan_result.get("memo_plan_path") if packet_plan_result else None,
        "packet_first_draft": packet_plan_result.get("packet_first_draft_path") if packet_plan_result else None,
        **reader_memo_edit_summary_paths(rewrite_result, edit_artifact_paths),
    }
