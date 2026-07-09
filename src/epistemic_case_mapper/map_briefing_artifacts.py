from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.decision_argument_artifacts import (
    render_argument_case_graph_markdown,
    render_competing_reads_markdown,
    render_decision_traceability_matrix_markdown,
    render_evidence_to_decision_matrix_markdown,
    render_summary_of_findings_markdown,
)
from epistemic_case_mapper.map_briefing_telemetry import write_gap_telemetry
from epistemic_case_mapper.map_briefing_spine_audit import (
    render_before_after_briefing_comparison,
    render_spine_completion_audit,
)
from epistemic_case_mapper.map_briefing_memo_ready_packet import build_memo_ready_packet_synthesis_prompt
from epistemic_case_mapper.map_briefing_simplification_comparison import build_pipeline_simplification_comparison


@dataclass(frozen=True)
class ArtifactContext:
    prompt: str
    prioritized_map: dict[str, Any]
    prioritization_report: dict[str, Any]
    erosion_audit: dict[str, Any]
    scaffold: dict[str, Any]


@dataclass(frozen=True)
class ArtifactSpec:
    key: str
    filename: str
    kind: str
    value: Callable[[ArtifactContext], Any]
    summary_key: str | None = None
    review_label: str | None = None


def _scaffold_artifact_specs() -> tuple[ArtifactSpec, ...]:
    return (
        ArtifactSpec("prompt", "map_briefing_prompt.txt", "markdown", lambda ctx: ctx.prompt),
        ArtifactSpec("prioritized_map", "prioritized_map.json", "json", lambda ctx: ctx.prioritized_map, review_label="Prioritized map"),
        ArtifactSpec("prioritization_report", "map_prioritization_report.json", "json", lambda ctx: ctx.prioritization_report, review_label="Prioritization report"),
        ArtifactSpec("erosion_audit", "generated_map_erosion_audit.json", "json", lambda ctx: ctx.erosion_audit, summary_key="generated_map_erosion_audit"),
        ArtifactSpec("sufficiency_report", "map_sufficiency_report.json", "json", _scaffold_value("map_sufficiency_report"), summary_key="map_sufficiency_report"),
        ArtifactSpec("decision_synthesis_model", "decision_synthesis_model.json", "json", _scaffold_value("decision_synthesis_model"), review_label="Decision synthesis model"),
        ArtifactSpec("argument_model", "argument_model.json", "json", _scaffold_value("argument_model"), review_label="Argument model"),
        ArtifactSpec("graph_synthesis_packet", "graph_synthesis_packet.json", "json", _scaffold_value("graph_synthesis_packet"), review_label="Graph synthesis packet"),
        ArtifactSpec("source_evidence_cards", "source_evidence_cards.json", "json", _scaffold_value("source_evidence_cards"), review_label="Source evidence cards"),
        ArtifactSpec("source_bottom_line_cards", "source_bottom_line_cards.json", "json", _scaffold_value("source_bottom_line_cards"), review_label="Source bottom-line cards"),
        ArtifactSpec("source_sufficiency_report", "source_sufficiency_report.json", "json", _scaffold_value("source_sufficiency_report"), review_label="Source sufficiency report"),
        ArtifactSpec("evidence_quality_report", "evidence_quality_report.json", "json", _scaffold_value("evidence_quality_report"), review_label="Evidence quality report"),
        ArtifactSpec("candidate_evidence_cards", "candidate_evidence_cards.json", "json", _scaffold_value("candidate_evidence_cards"), review_label="Candidate evidence cards"),
        ArtifactSpec("source_map_reconciliation", "source_map_reconciliation.json", "json", _scaffold_value("source_map_reconciliation"), review_label="Source-map reconciliation"),
        ArtifactSpec("source_coverage_report", "source_coverage_report.json", "json", _scaffold_value("source_coverage_report"), review_label="Source coverage report"),
        ArtifactSpec("classical_evidence_selection_report", "classical_evidence_selection_report.json", "json", _scaffold_value("classical_evidence_selection_report"), review_label="Classical evidence selection"),
        ArtifactSpec("claim_cluster_report", "claim_cluster_report.json", "json", _scaffold_value("claim_cluster_report")),
        ArtifactSpec("evidence_centrality_report", "evidence_centrality_report.json", "json", _scaffold_value("evidence_centrality_report")),
        ArtifactSpec("coverage_balance_report", "coverage_balance_report.json", "json", _scaffold_value("coverage_balance_report")),
        ArtifactSpec("quantity_outlier_report", "quantity_outlier_report.json", "json", _scaffold_value("quantity_outlier_report")),
        ArtifactSpec("relation_value_report", "relation_value_report.json", "json", _scaffold_value("relation_value_report"), review_label="Relation value report"),
        ArtifactSpec("slot_eligibility_audit", "slot_eligibility_audit.json", "json", _scaffold_value("slot_eligibility_audit"), review_label="Slot eligibility audit"),
        ArtifactSpec("canonical_decision_spine", "canonical_decision_spine.json", "json", _scaffold_value("canonical_decision_spine"), review_label="Canonical decision spine"),
        ArtifactSpec("canonical_decision_spine_validation", "canonical_decision_spine_validation.json", "json", _scaffold_value("canonical_decision_spine_validation")),
        ArtifactSpec("canonical_decision_spine_model_arbitration_report", "canonical_decision_spine_model_arbitration_report.json", "json", _scaffold_value("canonical_decision_spine_model_arbitration_report"), review_label="Canonical spine model arbitration"),
        ArtifactSpec("canonical_decision_spine_model_prompt", "canonical_decision_spine_model_prompt.txt", "markdown", _scaffold_text("canonical_decision_spine_model_prompt")),
        ArtifactSpec("canonical_decision_spine_model_raw", "canonical_decision_spine_model_raw.txt", "markdown", _scaffold_text("canonical_decision_spine_model_raw")),
        ArtifactSpec("decision_spine_consistency_report", "decision_spine_consistency_report.json", "json", _scaffold_value("decision_spine_consistency_report"), review_label="Decision spine consistency"),
        ArtifactSpec("slot_reconciliation_report", "slot_reconciliation_report.json", "json", _scaffold_value("slot_reconciliation_report"), review_label="Slot reconciliation report"),
        ArtifactSpec("section_projection_packets", "section_projection_packets.json", "json", _scaffold_value("section_projection_packets"), review_label="Section projection packets"),
        ArtifactSpec("section_context_decision_packets", "section_context_decision_packets.json", "json", _scaffold_value("section_context_decision_packets"), review_label="Section context decision packets"),
        ArtifactSpec("evidence_role_matrix", "evidence_role_matrix.json", "json", _scaffold_value("evidence_role_matrix"), review_label="Evidence role matrix"),
        ArtifactSpec("section_evidence_working_sets", "section_evidence_working_sets.json", "json", _scaffold_value("section_evidence_working_sets"), review_label="Section evidence working sets"),
        ArtifactSpec("evidence_role_coverage_report", "evidence_role_coverage_report.json", "json", _scaffold_value("evidence_role_coverage_report"), review_label="Evidence role coverage report"),
        ArtifactSpec("section_context_quality_report", "section_context_quality_report.json", "json", _scaffold_value("section_context_quality_report"), review_label="Section context quality report"),
        ArtifactSpec("section_projection_readiness_report", "section_projection_readiness_report.json", "json", _scaffold_value("section_projection_readiness_report"), review_label="Section projection readiness"),
        ArtifactSpec("spine_quality_report", "spine_quality_report.json", "json", _scaffold_value("spine_quality_report"), review_label="Spine quality report"),
        ArtifactSpec("answer_frame_normalization_report", "answer_frame_normalization_report.json", "json", _scaffold_value("answer_frame_normalization_report"), review_label="Answer frame normalization"),
        ArtifactSpec("decision_briefing_packet", "decision_briefing_packet.json", "json", _scaffold_value("decision_briefing_packet"), review_label="Decision briefing packet"),
        ArtifactSpec("decision_briefing_packet_report", "decision_briefing_packet_report.json", "json", _scaffold_value("decision_briefing_packet_report"), review_label="Decision briefing packet report"),
        ArtifactSpec("packet_sufficiency_report_pre_refinement", "packet_sufficiency_report_pre_refinement.json", "json", _scaffold_value("packet_sufficiency_report_pre_refinement"), review_label="Packet sufficiency before refinement"),
        ArtifactSpec("packet_sufficiency_report", "packet_sufficiency_report.json", "json", _scaffold_value("packet_sufficiency_report"), review_label="Packet sufficiency report"),
        ArtifactSpec("packet_quality_gate_report", "packet_quality_gate_report.json", "json", _scaffold_value("packet_quality_gate_report"), review_label="Packet quality gate"),
        ArtifactSpec("packet_critique_prompt", "packet_critique_prompt.txt", "markdown", _scaffold_text("packet_critique_prompt")),
        ArtifactSpec("packet_critique_raw", "packet_critique_raw.txt", "markdown", _scaffold_text("packet_critique_raw")),
        ArtifactSpec("packet_critique_report", "packet_critique_report.json", "json", _scaffold_value("packet_critique_report"), review_label="Packet critique report"),
        ArtifactSpec("packet_critique_adjudication_report", "packet_critique_adjudication_report.json", "json", _scaffold_value("packet_critique_adjudication_report"), review_label="Packet critique adjudication"),
        ArtifactSpec("decision_briefing_packet_refinement_prompt", "decision_briefing_packet_refinement_prompt.txt", "markdown", _scaffold_text("decision_briefing_packet_refinement_prompt")),
        ArtifactSpec("decision_briefing_packet_refinement_raw", "decision_briefing_packet_refinement_raw.txt", "markdown", _scaffold_text("decision_briefing_packet_refinement_raw")),
        ArtifactSpec("decision_briefing_packet_refinement_report", "decision_briefing_packet_refinement_report.json", "json", _scaffold_value("decision_briefing_packet_refinement_report"), review_label="Decision briefing packet refinement"),
        ArtifactSpec("packet_role_adjudication_report", "packet_role_adjudication_report.json", "json", _scaffold_value("packet_role_adjudication_report"), review_label="Packet role adjudication"),
        ArtifactSpec("role_conflict_candidates", "role_conflict_candidates.json", "json", _scaffold_value("role_conflict_candidates"), review_label="Role conflict candidates"),
        ArtifactSpec("packet_assembly_clusters", "packet_assembly_clusters.json", "json", _scaffold_value("packet_assembly_clusters"), review_label="Packet assembly clusters"),
        ArtifactSpec("packet_role_assignment_report", "packet_role_assignment_report.json", "json", _scaffold_value("packet_role_assignment_report"), review_label="Packet role assignment"),
        ArtifactSpec("diagnosticity_matrix", "diagnosticity_matrix.json", "json", _scaffold_value("diagnosticity_matrix"), review_label="Diagnosticity matrix"),
        ArtifactSpec("quantity_binding_report", "quantity_binding_report.json", "json", _scaffold_value("quantity_binding_report"), review_label="Quantity binding report"),
        ArtifactSpec("evidence_profile_report", "evidence_profile_report.json", "json", _scaffold_value("evidence_profile_report"), review_label="Evidence profile report"),
        ArtifactSpec("packet_assembly_audit", "packet_assembly_audit.json", "json", _scaffold_value("packet_assembly_audit"), review_label="Packet assembly audit"),
        ArtifactSpec("packet_qa_report", "packet_qa_report.json", "json", _scaffold_value("packet_qa_report"), review_label="Packet QA report"),
        ArtifactSpec("memo_ready_packet", "memo_ready_packet.json", "json", _scaffold_value("memo_ready_packet"), review_label="Memo-ready packet"),
        ArtifactSpec("memo_ready_selection_report", "memo_ready_selection_report.json", "json", _scaffold_value("memo_ready_selection_report"), review_label="Memo-ready selection"),
        ArtifactSpec("decision_crux_reconstruction_report", "decision_crux_reconstruction_report.json", "json", _scaffold_value("decision_crux_reconstruction_report"), review_label="Decision crux reconstruction"),
        ArtifactSpec("quantity_slot_report", "quantity_slot_report.json", "json", _scaffold_value("quantity_slot_report"), review_label="Quantity slot report"),
        ArtifactSpec("memo_ready_packet_quality_report", "memo_ready_packet_quality_report.json", "json", _scaffold_value("memo_ready_packet_quality_report"), review_label="Memo-ready packet quality"),
        ArtifactSpec("memo_ready_packet_synthesis_prompt", "memo_ready_packet_synthesis_prompt.txt", "markdown", lambda ctx: build_memo_ready_packet_synthesis_prompt(_scaffold_dict(ctx.scaffold, "memo_ready_packet"))),
        ArtifactSpec("before_after_briefing_comparison", "before_after_briefing_comparison.md", "markdown", lambda ctx: render_before_after_briefing_comparison(ctx.scaffold), review_label="Before/after briefing comparison"),
        ArtifactSpec("spine_completion_audit", "spine_completion_audit.md", "markdown", lambda ctx: render_spine_completion_audit(ctx.scaffold), review_label="Spine completion audit"),
        ArtifactSpec("atomic_evidence_cards", "atomic_evidence_cards.json", "json", _scaffold_value("atomic_evidence_cards")),
        ArtifactSpec("quantity_ledger", "quantity_ledger.json", "json", _scaffold_value("quantity_ledger"), review_label="Quantity ledger"),
        ArtifactSpec("evidence_to_decision_matrix", "evidence_to_decision_matrix.json", "json", _argument_artifact_value("evidence_to_decision_matrix"), review_label="Evidence-to-decision matrix"),
        ArtifactSpec("summary_of_findings", "summary_of_findings.json", "json", _argument_artifact_value("summary_of_findings"), review_label="Summary of findings"),
        ArtifactSpec("competing_reads", "competing_reads.json", "json", _argument_artifact_value("competing_reads"), review_label="Competing reads"),
        ArtifactSpec("argument_case_graph", "argument_case_graph.json", "json", _argument_artifact_value("argument_case_graph"), review_label="Argument case graph"),
        ArtifactSpec("decision_traceability_matrix", "decision_traceability_matrix.json", "json", _argument_artifact_value("decision_traceability_matrix"), review_label="Decision traceability matrix"),
        ArtifactSpec("evidence_to_decision_matrix_markdown", "EVIDENCE_TO_DECISION_MATRIX.md", "markdown", lambda ctx: render_evidence_to_decision_matrix_markdown(_argument_artifacts(ctx.scaffold).get("evidence_to_decision_matrix", {}))),
        ArtifactSpec("summary_of_findings_markdown", "SUMMARY_OF_FINDINGS.md", "markdown", lambda ctx: render_summary_of_findings_markdown(_argument_artifacts(ctx.scaffold).get("summary_of_findings", {}))),
        ArtifactSpec("competing_reads_markdown", "COMPETING_READS.md", "markdown", lambda ctx: render_competing_reads_markdown(_argument_artifacts(ctx.scaffold).get("competing_reads", {}))),
        ArtifactSpec("argument_case_graph_markdown", "ARGUMENT_CASE_GRAPH.md", "markdown", lambda ctx: render_argument_case_graph_markdown(_argument_artifacts(ctx.scaffold).get("argument_case_graph", {}))),
        ArtifactSpec("decision_traceability_matrix_markdown", "DECISION_TRACEABILITY_MATRIX.md", "markdown", lambda ctx: render_decision_traceability_matrix_markdown(_argument_artifacts(ctx.scaffold).get("decision_traceability_matrix", {}))),
    )


def _scaffold_value(key: str) -> Callable[[ArtifactContext], Any]:
    return lambda ctx: ctx.scaffold.get(key, {})


def _scaffold_text(key: str) -> Callable[[ArtifactContext], str]:
    return lambda ctx: str(ctx.scaffold.get(key, ""))


def _argument_artifacts(scaffold: dict[str, Any]) -> dict[str, Any]:
    value = scaffold.get("decision_argument_artifacts", {})
    return value if isinstance(value, dict) else {}


def _argument_artifact_value(key: str) -> Callable[[ArtifactContext], Any]:
    return lambda ctx: _argument_artifacts(ctx.scaffold).get(key, {})


def _scaffold_artifact_paths(artifacts: Path) -> dict[str, Path]:
    return {spec.key: artifacts / spec.filename for spec in _scaffold_artifact_specs()}


def _write_artifact(path: Path, kind: str, value: Any) -> None:
    if kind == "markdown":
        write_markdown(path, str(value))
    else:
        write_json(path, value if isinstance(value, dict) else {})


def _scaffold_summary_paths(scaffold_paths: dict[str, Path], *, final_review_packet_path: Path) -> dict[str, Path]:
    hidden = {
        "atomic_evidence_cards",
        "evidence_to_decision_matrix_markdown",
        "summary_of_findings_markdown",
        "competing_reads_markdown",
        "argument_case_graph_markdown",
        "decision_traceability_matrix_markdown",
    }
    paths = {
        spec.summary_key or spec.key: scaffold_paths[spec.key]
        for spec in _scaffold_artifact_specs()
        if spec.key in scaffold_paths
        and spec.key not in hidden
    }
    paths["final_review_packet"] = final_review_packet_path
    return paths


def _review_artifact_lines(repo_root: Path, scaffold_paths: dict[str, Path]) -> list[str]:
    return [
        f"- {spec.review_label}: `{_rel(repo_root, scaffold_paths.get(spec.key))}`"
        for spec in _scaffold_artifact_specs()
        if spec.review_label
    ]


def write_scaffold_artifacts(
    *,
    artifacts: Path,
    prompt: str,
    prioritized_map: dict[str, Any],
    prioritization_report: dict[str, Any],
    erosion_audit: dict[str, Any],
    scaffold: dict[str, Any],
) -> dict[str, Path]:
    ctx = ArtifactContext(
        prompt=prompt,
        prioritized_map=prioritized_map,
        prioritization_report=prioritization_report,
        erosion_audit=erosion_audit,
        scaffold=scaffold,
    )
    paths = _scaffold_artifact_paths(artifacts)
    for spec in _scaffold_artifact_specs():
        _write_artifact(paths[spec.key], spec.kind, spec.value(ctx))
    return paths


def write_map_briefing_summary(
    summary_path: Path,
    *,
    repo_root: Path,
    result_backend: str,
    parse_ok: bool,
    parse_diagnostics: dict[str, Any],
    question: str,
    paths: dict[str, Path | None],
    source_lookup: dict[str, str],
    quality_report: dict[str, Any],
    model_confidence: str,
    calibrated: str,
    calibration: dict[str, Any],
    candidate_map: dict[str, Any],
    prioritized_map: dict[str, Any],
    max_claims: int | None,
    effective_max_claims: int,
    erosion_audit: dict[str, Any],
    scaffold: dict[str, Any],
    briefing_validation: dict[str, Any],
    polish_report: dict[str, Any],
    rewrite_result: dict[str, Any],
) -> None:
    write_json(
        summary_path,
        map_briefing_summary_payload(
            repo_root=repo_root,
            result_backend=result_backend,
            parse_ok=parse_ok,
            parse_diagnostics=parse_diagnostics,
            question=question,
            paths=paths,
            source_lookup=source_lookup,
            quality_report=quality_report,
            model_confidence=model_confidence,
            calibrated=calibrated,
            calibration=calibration,
            candidate_map=candidate_map,
            prioritized_map=prioritized_map,
            max_claims=max_claims,
            effective_max_claims=effective_max_claims,
            erosion_audit=erosion_audit,
            scaffold=scaffold,
            briefing_validation=briefing_validation,
            polish_report=polish_report,
            rewrite_result=rewrite_result,
            decision_synthesis_model=scaffold.get("decision_synthesis_model", {}),
        ),
    )


def write_run_summary(
    *,
    artifacts: Path,
    repo_root: Path,
    backend: str,
    parse_ok: bool,
    parse_diagnostics: dict[str, Any],
    question: str,
    briefing_path: Path,
    evidence_appendix_path: Path,
    raw_path: Path,
    scaffold_paths: dict[str, Path],
    telemetry_paths: dict[str, Path],
    final_outputs: dict[str, Any],
    source_lookup: dict[str, str],
    quality_report: dict[str, Any],
    model_confidence: str,
    calibrated: str,
    calibration: dict[str, Any],
    candidate_map: dict[str, Any],
    prioritized_map: dict[str, Any],
    max_claims: int | None,
    effective_max_claims: int,
    erosion_audit: dict[str, Any],
    scaffold: dict[str, Any],
) -> Path:
    summary_path = artifacts / "briefing_summary.json"
    final_review_packet_path = artifacts / "FINAL_REVIEW_PACKET.md"
    comparison_path = artifacts / "pipeline_simplification_comparison.json"
    write_json(
        comparison_path,
        build_pipeline_simplification_comparison(
            scaffold=scaffold,
            final_outputs=final_outputs,
            briefing_path=str(briefing_path),
            evidence_appendix_path=str(evidence_appendix_path),
        ),
    )
    final_outputs.setdefault("summary_paths", {})["pipeline_simplification_comparison"] = comparison_path
    write_map_briefing_summary(
        summary_path,
        repo_root=repo_root,
        result_backend=backend,
        parse_ok=parse_ok,
        parse_diagnostics=parse_diagnostics,
        question=question,
        paths={
            "briefing": briefing_path,
            "evidence_appendix": evidence_appendix_path,
            "raw": raw_path,
            **_scaffold_summary_paths(scaffold_paths, final_review_packet_path=final_review_packet_path),
            **telemetry_paths,
            **final_outputs["summary_paths"],
        },
        source_lookup=source_lookup,
        quality_report=quality_report,
        model_confidence=model_confidence,
        calibrated=calibrated,
        calibration=calibration,
        candidate_map=candidate_map,
        prioritized_map=prioritized_map,
        max_claims=max_claims,
        effective_max_claims=effective_max_claims,
        erosion_audit=erosion_audit,
        scaffold=scaffold,
        briefing_validation=final_outputs["briefing_validation"],
        polish_report=final_outputs["polish_report"],
        rewrite_result=final_outputs["rewrite_result"],
    )
    write_final_review_packet(
        final_review_packet_path,
        repo_root=repo_root,
        question=question,
        backend=backend,
        summary_path=summary_path,
        briefing_path=briefing_path,
        evidence_appendix_path=evidence_appendix_path,
        scaffold_paths=scaffold_paths,
        telemetry_paths=telemetry_paths,
        final_outputs=final_outputs,
        quality_report=quality_report,
        candidate_map=candidate_map,
        prioritized_map=prioritized_map,
        scaffold=scaffold,
    )
    return summary_path


def write_final_review_packet(
    packet_path: Path,
    *,
    repo_root: Path,
    question: str,
    backend: str,
    summary_path: Path,
    briefing_path: Path,
    evidence_appendix_path: Path,
    scaffold_paths: dict[str, Path],
    telemetry_paths: dict[str, Path],
    final_outputs: dict[str, Any],
    quality_report: dict[str, Any],
    candidate_map: dict[str, Any],
    prioritized_map: dict[str, Any],
    scaffold: dict[str, Any],
) -> None:
    argument_model = scaffold.get("argument_model", {}) if isinstance(scaffold.get("argument_model"), dict) else {}
    validation = final_outputs["briefing_validation"]
    polish_report = final_outputs["polish_report"]
    rewrite_report = final_outputs["rewrite_result"]["report"]
    lines = [
        "# Final Review Packet",
        "",
        f"Question: {question or 'not specified'}",
        f"Backend: `{backend}`",
        "",
        "## Reader Artifacts",
        "",
        f"- Briefing: `{_rel(repo_root, briefing_path)}`",
        f"- Evidence appendix: `{_rel(repo_root, evidence_appendix_path)}`",
        f"- Summary JSON: `{_rel(repo_root, summary_path)}`",
        "",
        "## Structured Artifacts",
        "",
        *_review_artifact_lines(repo_root, scaffold_paths),
        f"- Final traceability check: `{_rel(repo_root, final_outputs['summary_paths'].get('decision_traceability_matrix_final'))}`",
        f"- Section packets: `{_rel(repo_root, final_outputs['summary_paths'].get('section_synthesis_packets'))}`",
        f"- Section context acceptance: `{_rel(repo_root, final_outputs['summary_paths'].get('section_context_acceptance_report'))}`",
        f"- Memo coherence report: `{_rel(repo_root, final_outputs['summary_paths'].get('memo_coherence_report'))}`",
        f"- Section role quality report: `{_rel(repo_root, final_outputs['summary_paths'].get('section_role_quality_report'))}`",
        f"- Final memo diagnosis: `{_rel(repo_root, final_outputs['summary_paths'].get('memo_final_diagnosis'))}`",
        f"- Memo protected spans: `{_rel(repo_root, final_outputs['summary_paths'].get('memo_protected_spans'))}`",
        f"- Coherence edit report: `{_rel(repo_root, final_outputs['summary_paths'].get('memo_coherence_edits'))}`",
        f"- Prose edit report: `{_rel(repo_root, final_outputs['summary_paths'].get('memo_prose_edits'))}`",
        f"- Pipeline migration ledger: `{_rel(repo_root, final_outputs['summary_paths'].get('pipeline_migration_ledger'))}`",
        f"- Runtime budget report: `{_rel(repo_root, final_outputs['summary_paths'].get('runtime_budget_report'))}`",
        f"- Pipeline simplification comparison: `{_rel(repo_root, final_outputs['summary_paths'].get('pipeline_simplification_comparison'))}`",
        f"- Final brief evaluation: `{_rel(repo_root, final_outputs['summary_paths'].get('final_brief_evaluation'))}`",
        f"- Model context audit: `{_rel(repo_root, final_outputs['summary_paths'].get('model_context_audit'))}`",
        f"- Gap diagnosis: `{_rel(repo_root, telemetry_paths.get('gap_diagnosis'))}`",
        f"- Main memo obligation ledger: `{_rel(repo_root, telemetry_paths.get('main_memo_obligation_ledger'))}`",
        f"- Unified requirement ledger: `{_rel(repo_root, telemetry_paths.get('unified_requirement_ledger'))}`",
        "",
        "## Quality Snapshot",
        "",
        f"- Map quality: `{quality_report.get('status', 'unknown')}` score `{quality_report.get('score', 'unknown')}`",
        f"- Claims: `{len(_claims(candidate_map))}` raw, `{len(_claims(prioritized_map))}` prioritized",
        f"- Relations: `{len(_relations(candidate_map))}` raw, `{len(_relations(prioritized_map))}` prioritized",
        f"- Briefing validation: `{validation.get('status', 'unknown')}` score `{validation.get('score', 'unknown')}`",
        f"- Reader polish: `{polish_report.get('status', 'unknown')}` score `{polish_report.get('score', 'unknown')}`",
        f"- Rewrite status: `{rewrite_report.get('status', 'unknown')}`",
        "",
        "## Argument Model Coverage",
        "",
        f"- Support items: `{_list_count(argument_model, 'strongest_support')}`",
        f"- Counterarguments: `{_list_count(argument_model, 'strongest_counterarguments')}`",
        f"- Quantitative anchors: `{_list_count(argument_model, 'quantitative_anchors')}`",
        f"- Scope boundaries: `{_list_count(argument_model, 'scope_boundaries')}`",
        f"- Cruxes: `{_list_count(argument_model, 'cruxes')}`",
        f"- Known failure modes: `{_list_count(argument_model, 'known_failure_modes')}`",
        "",
        "## Completion Notes",
        "",
        "- This packet is generated from the run artifacts; it is not a separate quality judgment.",
        "- Remaining weaknesses should be read from the gap diagnosis, validation report, rewrite report, and any baseline comparison artifacts.",
    ]
    write_markdown(packet_path, "\n".join(lines).rstrip() + "\n")


def write_gap_telemetry_outputs(
    *,
    artifacts: Path,
    repo_root: Path,
    question: str,
    candidate_map: dict[str, Any],
    prioritized_map: dict[str, Any],
    quality_report: dict[str, Any],
    prioritization_report: dict[str, Any],
    scaffold: dict[str, Any],
    briefing_path: Path,
    final_outputs: dict[str, Any],
    baseline_path: str | Path | None,
) -> dict[str, Path]:
    return write_gap_telemetry(
        artifacts=artifacts,
        repo_root=repo_root,
        question=question,
        candidate_map=candidate_map,
        prioritized_map=prioritized_map,
        quality_report=quality_report,
        prioritization_report=prioritization_report,
        scaffold=scaffold,
        briefing_text=briefing_path.read_text(encoding="utf-8"),
        validation=final_outputs["briefing_validation"],
        polish_report=final_outputs["polish_report"],
        rewrite_report=final_outputs["rewrite_result"]["report"],
        baseline_path=baseline_path,
    )


def map_briefing_summary_payload(
    *,
    repo_root: Path,
    result_backend: str,
    parse_ok: bool,
    parse_diagnostics: dict[str, Any],
    question: str,
    paths: dict[str, Path | None],
    source_lookup: dict[str, str],
    quality_report: dict[str, Any],
    model_confidence: str,
    calibrated: str,
    calibration: dict[str, Any],
    candidate_map: dict[str, Any],
    prioritized_map: dict[str, Any],
    max_claims: int | None,
    effective_max_claims: int,
    erosion_audit: dict[str, Any],
    scaffold: dict[str, Any],
    briefing_validation: dict[str, Any],
    polish_report: dict[str, Any],
    rewrite_result: dict[str, Any],
    decision_synthesis_model: dict[str, Any],
) -> dict[str, Any]:
    graph_packet = scaffold.get("graph_synthesis_packet", {}) if isinstance(scaffold.get("graph_synthesis_packet"), dict) else {}
    graph_summary = graph_packet.get("graph_summary", {}) if isinstance(graph_packet.get("graph_summary"), dict) else {}
    canonicalization = scaffold.get("claim_canonicalization_report", {}) if isinstance(scaffold.get("claim_canonicalization_report"), dict) else {}
    atomic_cards = scaffold.get("atomic_evidence_cards", {}) if isinstance(scaffold.get("atomic_evidence_cards"), dict) else {}
    argument_model = scaffold.get("argument_model", {}) if isinstance(scaffold.get("argument_model"), dict) else {}
    argument_artifacts = scaffold.get("decision_argument_artifacts", {}) if isinstance(scaffold.get("decision_argument_artifacts"), dict) else {}
    source_cards = scaffold.get("source_evidence_cards", {}) if isinstance(scaffold.get("source_evidence_cards"), dict) else {}
    source_sufficiency = scaffold.get("source_sufficiency_report", {}) if isinstance(scaffold.get("source_sufficiency_report"), dict) else {}
    evidence_quality = scaffold.get("evidence_quality_report", {}) if isinstance(scaffold.get("evidence_quality_report"), dict) else {}
    candidate_cards = scaffold.get("candidate_evidence_cards", {}) if isinstance(scaffold.get("candidate_evidence_cards"), dict) else {}
    reconciliation = scaffold.get("source_map_reconciliation", {}) if isinstance(scaffold.get("source_map_reconciliation"), dict) else {}
    source_coverage = scaffold.get("source_coverage_report", {}) if isinstance(scaffold.get("source_coverage_report"), dict) else {}
    slot_audit = _scaffold_dict(scaffold, "slot_eligibility_audit")
    canonical_spine = _scaffold_dict(scaffold, "canonical_decision_spine")
    spine_validation = _scaffold_dict(scaffold, "canonical_decision_spine_validation")
    spine_arbitration = _scaffold_dict(scaffold, "canonical_decision_spine_model_arbitration_report")
    spine_readiness = _scaffold_dict(scaffold, "section_projection_readiness_report")
    spine_quality = _scaffold_dict(scaffold, "spine_quality_report")
    section_acceptance_status = rewrite_result["report"].get("section_context_acceptance_status")
    traceability = argument_artifacts.get("decision_traceability_matrix", {}) if isinstance(argument_artifacts.get("decision_traceability_matrix"), dict) else {}
    return {
        "schema_id": "map_briefing_v1",
        "backend": result_backend,
        "parse_ok": parse_ok,
        "parse_diagnostics": parse_diagnostics,
        "question": question,
        "paths": {key: _rel(repo_root, value) if value else None for key, value in paths.items()},
        "source_display_names": source_lookup,
        "source_urls": scaffold.get("source_urls", {}) if isinstance(scaffold.get("source_urls"), dict) else {},
        "source_citation_labels": scaffold.get("source_citation_labels", {}) if isinstance(scaffold.get("source_citation_labels"), dict) else {},
        "map_quality_status": str(quality_report.get("status", "unknown")),
        "map_quality_score": quality_report.get("score"),
        "model_confidence": model_confidence,
        "calibrated_confidence": calibrated,
        "confidence_reasons": calibration["reasons"],
        "claim_count": len(_claims(candidate_map)),
        "prioritized_claim_count": len(_claims(prioritized_map)),
        "canonicalization_changed": canonicalization.get("changed", False),
        "canonical_original_claim_count": canonicalization.get("original_claim_count"),
        "canonical_claim_count": canonicalization.get("canonical_claim_count"),
        "canonical_duplicate_group_count": len(canonicalization.get("merged_duplicate_groups", [])) if isinstance(canonicalization.get("merged_duplicate_groups"), list) else 0,
        "canonical_fragment_drop_count": len(canonicalization.get("dropped_fragment_claim_ids", [])) if isinstance(canonicalization.get("dropped_fragment_claim_ids"), list) else 0,
        "atomic_evidence_card_count": atomic_cards.get("card_count"),
        "atomic_evidence_appendix_only_count": atomic_cards.get("appendix_only_count"),
        "atomic_evidence_noise_counts": atomic_cards.get("noise_counts", {}),
        "source_evidence_card_count": source_cards.get("source_card_count"),
        "source_evidence_anchored_card_count": source_cards.get("anchored_card_count"),
        "source_sufficiency_status": source_sufficiency.get("status"),
        "source_sufficiency_bounded_answer_required": source_sufficiency.get("bounded_answer_required"),
        "source_sufficiency_missing_categories": source_sufficiency.get("missing_source_categories", []),
        "evidence_quality_weak_or_indirect_count": evidence_quality.get("weak_or_indirect_count"),
        "evidence_quality_unknown_count": evidence_quality.get("unknown_quality_count"),
        "candidate_evidence_card_count": candidate_cards.get("card_count"),
        "candidate_evidence_main_text_count": candidate_cards.get("main_text_count"),
        "source_map_reconciliation_unbacked_count": reconciliation.get("unbacked_count"),
        "source_coverage_omitted_high_relevance_count": _list_count(source_coverage, "omitted_high_relevance_card_ids"),
        "slot_eligibility_status": slot_audit.get("status"),
        "canonical_decision_spine_status": canonical_spine.get("status"),
        "canonical_decision_spine_validation_status": spine_validation.get("status"),
        "canonical_decision_spine_model_arbitration_status": spine_arbitration.get("status"),
        "section_projection_readiness_status": spine_readiness.get("status"),
        "spine_quality_status": spine_quality.get("status"),
        "canonical_spine_missing_slot_count": _list_count(canonical_spine, "missing_decision_slots"),
        "requested_max_claims": max_claims,
        "effective_max_claims": effective_max_claims,
        "relation_count": len(_relations(candidate_map)),
        "prioritized_relation_count": len(_relations(prioritized_map)),
        "audit_item_count": len(erosion_audit.get("items", [])),
        "map_sufficiency_status": scaffold.get("map_sufficiency_report", {}).get("status"),
        "briefing_validation_status": briefing_validation.get("status"),
        "briefing_validation_score": briefing_validation.get("score"),
        "briefing_polish_status": polish_report.get("status"),
        "briefing_polish_score": polish_report.get("score"),
        "reader_memo_rewrite_status": rewrite_result["report"].get("status"),
        "section_context_acceptance_status": section_acceptance_status,
        "memo_coherence_report_path": _rel(repo_root, paths.get("memo_coherence_report")),
        "section_role_quality_report_path": _rel(repo_root, paths.get("section_role_quality_report")),
        "pipeline_migration_ledger_path": _rel(repo_root, paths.get("pipeline_migration_ledger")),
        "runtime_budget_report_path": _rel(repo_root, paths.get("runtime_budget_report")),
        "final_brief_evaluation_path": _rel(repo_root, paths.get("final_brief_evaluation")),
        "decision_synthesis_evidence_line_count": len(decision_synthesis_model.get("evidence_lines", [])),
        "decision_synthesis_tension_count": len(decision_synthesis_model.get("central_tensions", [])),
        "decision_synthesis_recommendation_count": len(decision_synthesis_model.get("recommendations", [])),
        "argument_support_count": _list_count(argument_model, "strongest_support"),
        "argument_counterargument_count": _list_count(argument_model, "strongest_counterarguments"),
        "argument_quantitative_anchor_count": _list_count(argument_model, "quantitative_anchors"),
        "argument_scope_boundary_count": _list_count(argument_model, "scope_boundaries"),
        "argument_crux_count": _list_count(argument_model, "cruxes"),
        "graph_issue_cluster_count": graph_summary.get("issue_cluster_count"),
        "graph_tension_edge_count": graph_summary.get("tension_edge_count"),
        "graph_load_bearing_claim_count": len(graph_packet.get("load_bearing_claims", [])),
        "graph_bridge_claim_count": len(graph_packet.get("bridge_claims", [])),
        "quantity_count": scaffold.get("quantity_ledger", {}).get("quantity_count"),
        "quantitative_card_count": scaffold.get("quantity_ledger", {}).get("quantitative_card_count"),
        "quantitative_anchor_count": len(scaffold.get("quantitative_anchors", [])) if isinstance(scaffold.get("quantitative_anchors"), list) else 0,
        "evidence_to_decision_row_count": argument_artifacts.get("evidence_to_decision_matrix", {}).get("row_count") if isinstance(argument_artifacts.get("evidence_to_decision_matrix"), dict) else 0,
        "summary_of_findings_count": argument_artifacts.get("summary_of_findings", {}).get("finding_count") if isinstance(argument_artifacts.get("summary_of_findings"), dict) else 0,
        "competing_read_count": len(argument_artifacts.get("competing_reads", {}).get("reads", [])) if isinstance(argument_artifacts.get("competing_reads"), dict) and isinstance(argument_artifacts.get("competing_reads", {}).get("reads"), list) else 0,
        "argument_case_node_count": argument_artifacts.get("argument_case_graph", {}).get("node_count") if isinstance(argument_artifacts.get("argument_case_graph"), dict) else 0,
        "traceability_row_count": traceability.get("row_count"),
    }


def _claims(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    claims = candidate_map.get("claims", [])
    return [claim for claim in claims if isinstance(claim, dict)] if isinstance(claims, list) else []


def _relations(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    relations = candidate_map.get("relations", [])
    return [relation for relation in relations if isinstance(relation, dict)] if isinstance(relations, list) else []


def _list_count(value: dict[str, Any], key: str) -> int:
    items = value.get(key, [])
    return len(items) if isinstance(items, list) else 0


def _scaffold_dict(scaffold: dict[str, Any], key: str) -> dict[str, Any]:
    value = scaffold.get(key, {})
    return value if isinstance(value, dict) else {}


def _rel(repo_root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)
