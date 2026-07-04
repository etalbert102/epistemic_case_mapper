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
        "argument_model": artifacts / "argument_model.json",
        "graph_synthesis_packet": artifacts / "graph_synthesis_packet.json",
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
    write_json(paths["argument_model"], scaffold.get("argument_model", {}))
    write_json(paths["graph_synthesis_packet"], scaffold.get("graph_synthesis_packet", {}))
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
            "argument_model": scaffold_paths["argument_model"],
            "graph_synthesis_packet": scaffold_paths["graph_synthesis_packet"],
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
        f"- Graph synthesis packet: `{_rel(repo_root, scaffold_paths.get('graph_synthesis_packet'))}`",
        f"- Quantity ledger: `{_rel(repo_root, scaffold_paths.get('quantity_ledger'))}`",
        f"- Evidence-to-decision matrix: `{_rel(repo_root, scaffold_paths.get('evidence_to_decision_matrix'))}`",
        f"- Summary of findings: `{_rel(repo_root, scaffold_paths.get('summary_of_findings'))}`",
        f"- Competing reads: `{_rel(repo_root, scaffold_paths.get('competing_reads'))}`",
        f"- Argument case graph: `{_rel(repo_root, scaffold_paths.get('argument_case_graph'))}`",
        f"- Decision traceability matrix: `{_rel(repo_root, scaffold_paths.get('decision_traceability_matrix'))}`",
        f"- Final traceability check: `{_rel(repo_root, final_outputs['summary_paths'].get('decision_traceability_matrix_final'))}`",
        f"- Section packets: `{_rel(repo_root, final_outputs['summary_paths'].get('section_synthesis_packets'))}`",
        f"- Gap diagnosis: `{_rel(repo_root, telemetry_paths.get('gap_diagnosis'))}`",
        f"- Main memo obligation ledger: `{_rel(repo_root, telemetry_paths.get('main_memo_obligation_ledger'))}`",
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
    argument_model = scaffold.get("argument_model", {}) if isinstance(scaffold.get("argument_model"), dict) else {}
    argument_artifacts = scaffold.get("decision_argument_artifacts", {}) if isinstance(scaffold.get("decision_argument_artifacts"), dict) else {}
    traceability = argument_artifacts.get("decision_traceability_matrix", {}) if isinstance(argument_artifacts.get("decision_traceability_matrix"), dict) else {}
    return {
        "schema_id": "map_briefing_v1",
        "backend": result_backend,
        "parse_ok": parse_ok,
        "parse_diagnostics": parse_diagnostics,
        "question": question,
        "paths": {key: _rel(repo_root, value) if value else None for key, value in paths.items()},
        "source_display_names": source_lookup,
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
        "decision_synthesis_evidence_line_count": len(decision_synthesis_model.get("evidence_lines", [])),
        "decision_synthesis_tension_count": len(decision_synthesis_model.get("central_tensions", [])),
        "decision_synthesis_recommendation_count": len(decision_synthesis_model.get("recommendations", [])),
        "argument_support_count": len(argument_model.get("strongest_support", [])) if isinstance(argument_model.get("strongest_support"), list) else 0,
        "argument_counterargument_count": len(argument_model.get("strongest_counterarguments", [])) if isinstance(argument_model.get("strongest_counterarguments"), list) else 0,
        "argument_quantitative_anchor_count": len(argument_model.get("quantitative_anchors", [])) if isinstance(argument_model.get("quantitative_anchors"), list) else 0,
        "argument_scope_boundary_count": len(argument_model.get("scope_boundaries", [])) if isinstance(argument_model.get("scope_boundaries"), list) else 0,
        "argument_crux_count": len(argument_model.get("cruxes", [])) if isinstance(argument_model.get("cruxes"), list) else 0,
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


def _rel(repo_root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)
