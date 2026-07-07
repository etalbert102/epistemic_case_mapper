from __future__ import annotations

from pathlib import Path
from typing import Any

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


def write_scaffold_artifacts(
    *,
    artifacts: Path,
    prompt: str,
    prioritized_map: dict[str, Any],
    prioritization_report: dict[str, Any],
    erosion_audit: dict[str, Any],
    scaffold: dict[str, Any],
) -> dict[str, Path]:
    paths = {
        "prompt": artifacts / "map_briefing_prompt.txt",
        "prioritized_map": artifacts / "prioritized_map.json",
        "prioritization_report": artifacts / "map_prioritization_report.json",
        "erosion_audit": artifacts / "generated_map_erosion_audit.json",
        "sufficiency_report": artifacts / "map_sufficiency_report.json",
        "decision_synthesis_model": artifacts / "decision_synthesis_model.json",
        "global_memo_plan": artifacts / "global_memo_plan.json",
        "global_memo_plan_prompt": artifacts / "global_memo_plan_prompt.txt",
        "global_memo_plan_raw": artifacts / "global_memo_plan_raw.txt",
        "global_memo_plan_validation": artifacts / "global_memo_plan_validation.json",
        "argument_model": artifacts / "argument_model.json",
        "graph_synthesis_packet": artifacts / "graph_synthesis_packet.json",
        "source_evidence_cards": artifacts / "source_evidence_cards.json",
        "source_sufficiency_report": artifacts / "source_sufficiency_report.json",
        "evidence_quality_report": artifacts / "evidence_quality_report.json",
        "candidate_evidence_cards": artifacts / "candidate_evidence_cards.json",
        "source_map_reconciliation": artifacts / "source_map_reconciliation.json",
        "memo_argument_spine": artifacts / "memo_argument_spine.json",
        "section_reasoning_cards": artifacts / "section_reasoning_cards.json",
        "source_coverage_report": artifacts / "source_coverage_report.json",
        "classical_evidence_selection_report": artifacts / "classical_evidence_selection_report.json",
        "claim_cluster_report": artifacts / "claim_cluster_report.json",
        "evidence_centrality_report": artifacts / "evidence_centrality_report.json",
        "coverage_balance_report": artifacts / "coverage_balance_report.json",
        "quantity_outlier_report": artifacts / "quantity_outlier_report.json",
        "slot_eligibility_audit": artifacts / "slot_eligibility_audit.json",
        "canonical_decision_spine": artifacts / "canonical_decision_spine.json",
        "canonical_decision_spine_validation": artifacts / "canonical_decision_spine_validation.json",
        "decision_spine_consistency_report": artifacts / "decision_spine_consistency_report.json",
        "section_projection_packets": artifacts / "section_projection_packets.json",
        "section_projection_readiness_report": artifacts / "section_projection_readiness_report.json",
        "spine_quality_report": artifacts / "spine_quality_report.json",
        "before_after_briefing_comparison": artifacts / "before_after_briefing_comparison.md",
        "spine_completion_audit": artifacts / "spine_completion_audit.md",
        "atomic_evidence_cards": artifacts / "atomic_evidence_cards.json",
        "quantity_ledger": artifacts / "quantity_ledger.json",
        "evidence_to_decision_matrix": artifacts / "evidence_to_decision_matrix.json",
        "summary_of_findings": artifacts / "summary_of_findings.json",
        "competing_reads": artifacts / "competing_reads.json",
        "argument_case_graph": artifacts / "argument_case_graph.json",
        "decision_traceability_matrix": artifacts / "decision_traceability_matrix.json",
        "evidence_to_decision_matrix_markdown": artifacts / "EVIDENCE_TO_DECISION_MATRIX.md",
        "summary_of_findings_markdown": artifacts / "SUMMARY_OF_FINDINGS.md",
        "competing_reads_markdown": artifacts / "COMPETING_READS.md",
        "argument_case_graph_markdown": artifacts / "ARGUMENT_CASE_GRAPH.md",
        "decision_traceability_matrix_markdown": artifacts / "DECISION_TRACEABILITY_MATRIX.md",
    }
    write_markdown(paths["prompt"], prompt)
    write_json(paths["prioritized_map"], prioritized_map)
    write_json(paths["prioritization_report"], prioritization_report)
    write_json(paths["erosion_audit"], erosion_audit)
    write_json(paths["sufficiency_report"], scaffold.get("map_sufficiency_report", {}))
    write_json(paths["decision_synthesis_model"], scaffold.get("decision_synthesis_model", {}))
    write_json(paths["global_memo_plan"], scaffold.get("global_memo_plan", {}))
    write_markdown(paths["global_memo_plan_prompt"], str(scaffold.get("global_memo_plan_prompt", "")))
    write_markdown(paths["global_memo_plan_raw"], str(scaffold.get("global_memo_plan_raw", "")))
    write_json(paths["global_memo_plan_validation"], scaffold.get("global_memo_plan_validation", {}))
    write_json(paths["argument_model"], scaffold.get("argument_model", {}))
    write_json(paths["graph_synthesis_packet"], scaffold.get("graph_synthesis_packet", {}))
    write_json(paths["source_evidence_cards"], scaffold.get("source_evidence_cards", {}))
    write_json(paths["source_sufficiency_report"], scaffold.get("source_sufficiency_report", {}))
    write_json(paths["evidence_quality_report"], scaffold.get("evidence_quality_report", {}))
    write_json(paths["candidate_evidence_cards"], scaffold.get("candidate_evidence_cards", {}))
    write_json(paths["source_map_reconciliation"], scaffold.get("source_map_reconciliation", {}))
    write_json(paths["memo_argument_spine"], scaffold.get("memo_argument_spine", {}))
    write_json(paths["section_reasoning_cards"], scaffold.get("section_reasoning_cards", {}))
    write_json(paths["source_coverage_report"], scaffold.get("source_coverage_report", {}))
    write_json(paths["classical_evidence_selection_report"], scaffold.get("classical_evidence_selection_report", {}))
    write_json(paths["claim_cluster_report"], scaffold.get("claim_cluster_report", {}))
    write_json(paths["evidence_centrality_report"], scaffold.get("evidence_centrality_report", {}))
    write_json(paths["coverage_balance_report"], scaffold.get("coverage_balance_report", {}))
    write_json(paths["quantity_outlier_report"], scaffold.get("quantity_outlier_report", {}))
    write_json(paths["slot_eligibility_audit"], scaffold.get("slot_eligibility_audit", {}))
    write_json(paths["canonical_decision_spine"], scaffold.get("canonical_decision_spine", {}))
    write_json(paths["canonical_decision_spine_validation"], scaffold.get("canonical_decision_spine_validation", {}))
    write_json(paths["decision_spine_consistency_report"], scaffold.get("decision_spine_consistency_report", {}))
    write_json(paths["section_projection_packets"], scaffold.get("section_projection_packets", {}))
    write_json(paths["section_projection_readiness_report"], scaffold.get("section_projection_readiness_report", {}))
    write_json(paths["spine_quality_report"], scaffold.get("spine_quality_report", {}))
    write_markdown(paths["before_after_briefing_comparison"], render_before_after_briefing_comparison(scaffold))
    write_markdown(paths["spine_completion_audit"], render_spine_completion_audit(scaffold))
    write_json(paths["atomic_evidence_cards"], scaffold.get("atomic_evidence_cards", {}))
    write_json(paths["quantity_ledger"], scaffold.get("quantity_ledger", {}))
    argument_artifacts = scaffold.get("decision_argument_artifacts", {}) if isinstance(scaffold.get("decision_argument_artifacts"), dict) else {}
    write_json(paths["evidence_to_decision_matrix"], argument_artifacts.get("evidence_to_decision_matrix", {}))
    write_json(paths["summary_of_findings"], argument_artifacts.get("summary_of_findings", {}))
    write_json(paths["competing_reads"], argument_artifacts.get("competing_reads", {}))
    write_json(paths["argument_case_graph"], argument_artifacts.get("argument_case_graph", {}))
    write_json(paths["decision_traceability_matrix"], argument_artifacts.get("decision_traceability_matrix", {}))
    write_markdown(paths["evidence_to_decision_matrix_markdown"], render_evidence_to_decision_matrix_markdown(argument_artifacts.get("evidence_to_decision_matrix", {})))
    write_markdown(paths["summary_of_findings_markdown"], render_summary_of_findings_markdown(argument_artifacts.get("summary_of_findings", {})))
    write_markdown(paths["competing_reads_markdown"], render_competing_reads_markdown(argument_artifacts.get("competing_reads", {})))
    write_markdown(paths["argument_case_graph_markdown"], render_argument_case_graph_markdown(argument_artifacts.get("argument_case_graph", {})))
    write_markdown(paths["decision_traceability_matrix_markdown"], render_decision_traceability_matrix_markdown(argument_artifacts.get("decision_traceability_matrix", {})))
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
            "prompt": scaffold_paths["prompt"],
            "raw": raw_path,
            "prioritized_map": scaffold_paths["prioritized_map"],
            "prioritization_report": scaffold_paths["prioritization_report"],
            "generated_map_erosion_audit": scaffold_paths["erosion_audit"],
            "map_sufficiency_report": scaffold_paths["sufficiency_report"],
            "decision_synthesis_model": scaffold_paths["decision_synthesis_model"],
            "global_memo_plan": scaffold_paths["global_memo_plan"],
            "global_memo_plan_prompt": scaffold_paths["global_memo_plan_prompt"],
            "global_memo_plan_raw": scaffold_paths["global_memo_plan_raw"],
            "global_memo_plan_validation": scaffold_paths["global_memo_plan_validation"],
            "argument_model": scaffold_paths["argument_model"],
            "graph_synthesis_packet": scaffold_paths["graph_synthesis_packet"],
            "source_evidence_cards": scaffold_paths["source_evidence_cards"],
            "source_sufficiency_report": scaffold_paths["source_sufficiency_report"],
            "evidence_quality_report": scaffold_paths["evidence_quality_report"],
            "candidate_evidence_cards": scaffold_paths["candidate_evidence_cards"],
            "source_map_reconciliation": scaffold_paths["source_map_reconciliation"],
            "memo_argument_spine": scaffold_paths["memo_argument_spine"],
            "section_reasoning_cards": scaffold_paths["section_reasoning_cards"],
            "source_coverage_report": scaffold_paths["source_coverage_report"],
            "classical_evidence_selection_report": scaffold_paths["classical_evidence_selection_report"],
            "claim_cluster_report": scaffold_paths["claim_cluster_report"],
            "evidence_centrality_report": scaffold_paths["evidence_centrality_report"],
            "coverage_balance_report": scaffold_paths["coverage_balance_report"],
            "quantity_outlier_report": scaffold_paths["quantity_outlier_report"],
            "slot_eligibility_audit": scaffold_paths["slot_eligibility_audit"],
            "canonical_decision_spine": scaffold_paths["canonical_decision_spine"],
            "canonical_decision_spine_validation": scaffold_paths["canonical_decision_spine_validation"],
            "decision_spine_consistency_report": scaffold_paths["decision_spine_consistency_report"],
            "section_projection_packets": scaffold_paths["section_projection_packets"],
            "section_projection_readiness_report": scaffold_paths["section_projection_readiness_report"],
            "spine_quality_report": scaffold_paths["spine_quality_report"],
            "before_after_briefing_comparison": scaffold_paths["before_after_briefing_comparison"],
            "spine_completion_audit": scaffold_paths["spine_completion_audit"],
            "quantity_ledger": scaffold_paths["quantity_ledger"],
            "evidence_to_decision_matrix": scaffold_paths["evidence_to_decision_matrix"],
            "summary_of_findings": scaffold_paths["summary_of_findings"],
            "competing_reads": scaffold_paths["competing_reads"],
            "argument_case_graph": scaffold_paths["argument_case_graph"],
            "decision_traceability_matrix": scaffold_paths["decision_traceability_matrix"],
            "final_review_packet": final_review_packet_path,
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
        f"- Prioritized map: `{_rel(repo_root, scaffold_paths.get('prioritized_map'))}`",
        f"- Argument model: `{_rel(repo_root, scaffold_paths.get('argument_model'))}`",
        f"- Decision synthesis model: `{_rel(repo_root, scaffold_paths.get('decision_synthesis_model'))}`",
        f"- Global memo plan: `{_rel(repo_root, scaffold_paths.get('global_memo_plan'))}`",
        f"- Graph synthesis packet: `{_rel(repo_root, scaffold_paths.get('graph_synthesis_packet'))}`",
        f"- Source evidence cards: `{_rel(repo_root, scaffold_paths.get('source_evidence_cards'))}`",
        f"- Source sufficiency report: `{_rel(repo_root, scaffold_paths.get('source_sufficiency_report'))}`",
        f"- Evidence quality report: `{_rel(repo_root, scaffold_paths.get('evidence_quality_report'))}`",
        f"- Candidate evidence cards: `{_rel(repo_root, scaffold_paths.get('candidate_evidence_cards'))}`",
        f"- Source-map reconciliation: `{_rel(repo_root, scaffold_paths.get('source_map_reconciliation'))}`",
        f"- Memo argument spine: `{_rel(repo_root, scaffold_paths.get('memo_argument_spine'))}`",
        f"- Section reasoning cards: `{_rel(repo_root, scaffold_paths.get('section_reasoning_cards'))}`",
        f"- Source coverage report: `{_rel(repo_root, scaffold_paths.get('source_coverage_report'))}`",
        f"- Classical evidence selection: `{_rel(repo_root, scaffold_paths.get('classical_evidence_selection_report'))}`",
        f"- Slot eligibility audit: `{_rel(repo_root, scaffold_paths.get('slot_eligibility_audit'))}`",
        f"- Canonical decision spine: `{_rel(repo_root, scaffold_paths.get('canonical_decision_spine'))}`",
        f"- Decision spine consistency: `{_rel(repo_root, scaffold_paths.get('decision_spine_consistency_report'))}`",
        f"- Section projection packets: `{_rel(repo_root, scaffold_paths.get('section_projection_packets'))}`",
        f"- Section projection readiness: `{_rel(repo_root, scaffold_paths.get('section_projection_readiness_report'))}`",
        f"- Spine quality report: `{_rel(repo_root, scaffold_paths.get('spine_quality_report'))}`",
        f"- Before/after briefing comparison: `{_rel(repo_root, scaffold_paths.get('before_after_briefing_comparison'))}`",
        f"- Spine completion audit: `{_rel(repo_root, scaffold_paths.get('spine_completion_audit'))}`",
        f"- Quantity ledger: `{_rel(repo_root, scaffold_paths.get('quantity_ledger'))}`",
        f"- Evidence-to-decision matrix: `{_rel(repo_root, scaffold_paths.get('evidence_to_decision_matrix'))}`",
        f"- Summary of findings: `{_rel(repo_root, scaffold_paths.get('summary_of_findings'))}`",
        f"- Competing reads: `{_rel(repo_root, scaffold_paths.get('competing_reads'))}`",
        f"- Argument case graph: `{_rel(repo_root, scaffold_paths.get('argument_case_graph'))}`",
        f"- Decision traceability matrix: `{_rel(repo_root, scaffold_paths.get('decision_traceability_matrix'))}`",
        f"- Final traceability check: `{_rel(repo_root, final_outputs['summary_paths'].get('decision_traceability_matrix_final'))}`",
        f"- Section packets: `{_rel(repo_root, final_outputs['summary_paths'].get('section_synthesis_packets'))}`",
        f"- Section context acceptance: `{_rel(repo_root, final_outputs['summary_paths'].get('section_context_acceptance_report'))}`",
        f"- Memo coherence report: `{_rel(repo_root, final_outputs['summary_paths'].get('memo_coherence_report'))}`",
        f"- Final memo diagnosis: `{_rel(repo_root, final_outputs['summary_paths'].get('memo_final_diagnosis'))}`",
        f"- Memo protected spans: `{_rel(repo_root, final_outputs['summary_paths'].get('memo_protected_spans'))}`",
        f"- Coherence edit report: `{_rel(repo_root, final_outputs['summary_paths'].get('memo_coherence_edits'))}`",
        f"- Prose edit report: `{_rel(repo_root, final_outputs['summary_paths'].get('memo_prose_edits'))}`",
        f"- Pipeline migration ledger: `{_rel(repo_root, final_outputs['summary_paths'].get('pipeline_migration_ledger'))}`",
        f"- Runtime budget report: `{_rel(repo_root, final_outputs['summary_paths'].get('runtime_budget_report'))}`",
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
    global_plan = scaffold.get("global_memo_plan", {}) if isinstance(scaffold.get("global_memo_plan"), dict) else {}
    global_plan_validation = scaffold.get("global_memo_plan_validation", {}) if isinstance(scaffold.get("global_memo_plan_validation"), dict) else {}
    source_cards = scaffold.get("source_evidence_cards", {}) if isinstance(scaffold.get("source_evidence_cards"), dict) else {}
    source_sufficiency = scaffold.get("source_sufficiency_report", {}) if isinstance(scaffold.get("source_sufficiency_report"), dict) else {}
    evidence_quality = scaffold.get("evidence_quality_report", {}) if isinstance(scaffold.get("evidence_quality_report"), dict) else {}
    candidate_cards = scaffold.get("candidate_evidence_cards", {}) if isinstance(scaffold.get("candidate_evidence_cards"), dict) else {}
    reconciliation = scaffold.get("source_map_reconciliation", {}) if isinstance(scaffold.get("source_map_reconciliation"), dict) else {}
    argument_spine = scaffold.get("memo_argument_spine", {}) if isinstance(scaffold.get("memo_argument_spine"), dict) else {}
    reasoning_cards = scaffold.get("section_reasoning_cards", {}) if isinstance(scaffold.get("section_reasoning_cards"), dict) else {}
    source_coverage = scaffold.get("source_coverage_report", {}) if isinstance(scaffold.get("source_coverage_report"), dict) else {}
    slot_audit = _scaffold_dict(scaffold, "slot_eligibility_audit")
    canonical_spine = _scaffold_dict(scaffold, "canonical_decision_spine")
    spine_validation = _scaffold_dict(scaffold, "canonical_decision_spine_validation")
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
        "memo_argument_spine_status": argument_spine.get("status"),
        "memo_argument_spine_item_count": _list_count(argument_spine, "items"),
        "section_reasoning_cards_status": reasoning_cards.get("status"),
        "source_coverage_omitted_high_relevance_count": _list_count(source_coverage, "omitted_high_relevance_card_ids"),
        "slot_eligibility_status": slot_audit.get("status"),
        "canonical_decision_spine_status": canonical_spine.get("status"),
        "canonical_decision_spine_validation_status": spine_validation.get("status"),
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
        "pipeline_migration_ledger_path": _rel(repo_root, paths.get("pipeline_migration_ledger")),
        "runtime_budget_report_path": _rel(repo_root, paths.get("runtime_budget_report")),
        "final_brief_evaluation_path": _rel(repo_root, paths.get("final_brief_evaluation")),
        "global_memo_plan_status": global_plan.get("status"),
        "global_memo_plan_method": global_plan.get("method"),
        "global_memo_plan_validation_status": global_plan_validation.get("status"),
        "global_memo_plan_target_word_count": global_plan_validation.get("target_word_count"),
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
