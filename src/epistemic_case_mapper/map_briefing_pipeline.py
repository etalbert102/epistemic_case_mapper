from __future__ import annotations
import json
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from epistemic_case_mapper.classical_ml import (
    relation_edge_weight,
    tfidf_near_duplicate_pairs,
    weighted_pagerank,
)
from epistemic_case_mapper.config_profiles import (
    DEFAULT_PROFILE_ID,
    infer_profile_id_from_text,
    profile_vocabulary,
)
from epistemic_case_mapper.decision_argument_artifacts import (
    build_decision_argument_artifacts,
    evaluate_traceability_against_memo,
    render_decision_traceability_matrix_markdown,
)
from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.synthesis_uplift_packet import (
    _clean_reader_packet_metadata,
    _parse_json,
    _render_synthesis_packet,
)
from epistemic_case_mapper.decision_frame import (
    build_decision_frame,
    memo_quality_report,
    question_quality_report,
    refine_crux_contract,
)
from epistemic_case_mapper.map_briefing_artifacts import write_gap_telemetry_outputs, write_scaffold_artifacts
from epistemic_case_mapper.map_briefing_argument_model import build_argument_model
from epistemic_case_mapper.map_briefing_context_curation import build_decision_ready_context_bundle
from epistemic_case_mapper.map_briefing_context_reports import (
    build_final_brief_evaluation,
    build_memo_coherence_report,
    build_pipeline_migration_ledger,
    build_runtime_budget_report,
)
from epistemic_case_mapper.map_briefing_decision_synthesis import build_decision_synthesis_model
from epistemic_case_mapper.map_briefing_evidence_cards import apply_evidence_cards_to_map
from epistemic_case_mapper.map_briefing_final_editor_artifacts import (
    reader_memo_edit_artifact_paths,
    reader_memo_edit_summary_paths,
    write_reader_memo_edit_artifacts,
)
from epistemic_case_mapper.map_briefing_frame_policy import adapt_decision_model_to_frame, section_policy_for_frame
from epistemic_case_mapper.map_briefing_graph_synthesis import build_graph_synthesis_packet
from epistemic_case_mapper.map_briefing_model_context import write_model_context_audit
from epistemic_case_mapper.map_briefing_prompt_scaffold import model_briefing_scaffold
from epistemic_case_mapper.map_briefing_quantities import build_quantity_ledger, top_quantity_anchors
from epistemic_case_mapper.map_briefing_run_helpers import prepare_map_briefing_inputs, write_map_briefing_run_summary
from epistemic_case_mapper.map_briefing_seed_brief import deterministic_graph_claim_sentences
from epistemic_case_mapper.map_briefing_section_role_quality import section_role_quality_report
from epistemic_case_mapper.map_briefing_spine_bundle import build_decision_spine_bundle
from epistemic_case_mapper.map_briefing_spine_global_plan import attach_global_memo_plan
ROLE_PRIORITY = {
    "crux": 0,
    "scope_limit": 1,
    "external_validity": 1,
    "measurement_validity": 1,
    "implementation_constraint": 2,
    "cost_feasibility": 2,
    "conclusion_support": 3,
    "background": 4,
    "other": 5,
}
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
@dataclass(frozen=True)
class MapBriefingResult:
    briefing_path: Path
    summary_path: Path
    prompt_path: Path
    prioritized_map_path: Path
    prioritization_report_path: Path
    erosion_audit_path: Path
    sufficiency_report_path: Path
    briefing_validation_path: Path
    gap_diagnosis_path: Path
    backend: str
    model_confidence: str
    calibrated_confidence: str
    map_quality_status: str

def run_map_briefing(
    *,
    repo_root: Path,
    map_path: str | Path,
    quality_report_path: str | Path,
    question: str,
    backend: str,
    output_dir: str | Path | None = None,
    backend_timeout: int | None = 120, backend_retries: int = 0,
    source_titles: dict[str, str] | None = None,
    source_urls: dict[str, str] | None = None,
    source_citation_labels: dict[str, str] | None = None,
    max_claims: int | None = 0,
    baseline_path: str | Path | None = None,
    run_reader_memo_rewrite: bool = False,
) -> MapBriefingResult:
    _validate_run_args(question, backend_timeout, backend_retries)
    prep = prepare_map_briefing_inputs(
        repo_root=repo_root,
        map_path=map_path,
        quality_report_path=quality_report_path,
        source_titles=source_titles,
        max_claims=max_claims,
    )
    map_file = prep["map_file"]
    candidate_map = prep["candidate_map"]
    quality_report = prep["quality_report"]
    source_lookup = prep["source_lookup"]
    effective_max_claims = prep["effective_max_claims"]
    prioritized_map = prep["prioritized_map"]
    prioritization_report = prep["prioritization_report"]
    canonicalization_report = prep["canonicalization_report"]
    erosion_audit = prep["erosion_audit"]
    artifacts = _resolve(repo_root, output_dir or Path("artifacts") / "map_briefings" / map_file.stem)
    artifacts.mkdir(parents=True, exist_ok=True)
    scaffold = briefing_scaffold(
        prioritized_map,
        quality_report,
        source_lookup,
        erosion_audit,
        question=question,
        source_urls=source_urls,
        source_citation_labels=source_citation_labels,
    )
    scaffold["claim_canonicalization_report"] = canonicalization_report
    prioritized_map, scaffold = _apply_atomic_cards_to_briefing_map(prioritized_map, scaffold)
    _attach_decision_ready_context_reports(prioritized_map, scaffold, question=question, source_lookup=source_lookup)
    _attach_decision_spine_bundle(prioritized_map, scaffold, question=question, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries)
    attach_global_memo_plan(scaffold, backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries)
    prompt = build_map_briefing_prompt(
        candidate_map=prioritized_map,
        quality_report=quality_report,
        question=question,
        source_lookup=source_lookup,
        erosion_audit=erosion_audit,
        scaffold=scaffold,
    )

    scaffold_paths = write_scaffold_artifacts(
        artifacts=artifacts,
        prompt=prompt,
        prioritized_map=prioritized_map,
        prioritization_report=prioritization_report,
        erosion_audit=erosion_audit,
        scaffold=scaffold,
    )
    briefing_validation_path = artifacts / "briefing_validation_report.json"

    raw_path = artifacts / "map_briefing_raw.txt"
    write_markdown(raw_path, _section_first_generation_note(backend))
    render_state = _section_first_render_state(
        prompt=prompt,
        quality_report=quality_report,
        scaffold=scaffold,
    )
    rendered = _prepare_rendered_reader_packet(
        str(render_state["rendered"]),
        calibrated=str(render_state["calibrated"]),
        scaffold=scaffold,
        prioritized_map=prioritized_map,
        source_lookup=source_lookup,
    )
    final_outputs = _write_final_reader_outputs(
        rendered=rendered,
        scaffold=scaffold,
        prioritized_map=prioritized_map,
        artifacts=artifacts,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        run_reader_memo_rewrite=run_reader_memo_rewrite,
    )
    _attach_model_context_audit(artifacts=artifacts, backend=backend, prompt=prompt, scaffold=scaffold, final_outputs=final_outputs)
    briefing_path = final_outputs["briefing_path"]
    evidence_appendix_path = final_outputs["evidence_appendix_path"]
    telemetry_paths = write_gap_telemetry_outputs(
        artifacts=artifacts,
        repo_root=repo_root,
        question=question,
        candidate_map=candidate_map,
        prioritized_map=prioritized_map,
        quality_report=quality_report,
        prioritization_report=prioritization_report,
        scaffold=scaffold,
        briefing_path=briefing_path,
        final_outputs=final_outputs,
        baseline_path=baseline_path,
    )
    summary_path = write_map_briefing_run_summary(
        artifacts=artifacts,
        repo_root=repo_root,
        backend=backend,
        render_state=render_state,
        question=question,
        briefing_path=briefing_path,
        evidence_appendix_path=evidence_appendix_path,
        raw_path=raw_path,
        scaffold_paths=scaffold_paths,
        telemetry_paths=telemetry_paths,
        final_outputs=final_outputs,
        source_lookup=source_lookup,
        quality_report=quality_report,
        candidate_map=candidate_map,
        prioritized_map=prioritized_map,
        max_claims=max_claims,
        effective_max_claims=effective_max_claims,
        erosion_audit=erosion_audit,
        scaffold=scaffold,
    )
    return _map_briefing_result(
        briefing_path=briefing_path, summary_path=summary_path, scaffold_paths=scaffold_paths,
        briefing_validation_path=briefing_validation_path, telemetry_paths=telemetry_paths,
        backend=backend, render_state=render_state, quality_report=quality_report,
    )
def _map_briefing_result(
    *, briefing_path: Path, summary_path: Path, scaffold_paths: dict[str, Path],
    briefing_validation_path: Path, telemetry_paths: dict[str, Path], backend: str,
    render_state: dict[str, Any], quality_report: dict[str, Any],
) -> MapBriefingResult:
    return MapBriefingResult(
        briefing_path=briefing_path, summary_path=summary_path, prompt_path=scaffold_paths["prompt"],
        prioritized_map_path=scaffold_paths["prioritized_map"], prioritization_report_path=scaffold_paths["prioritization_report"],
        erosion_audit_path=scaffold_paths["erosion_audit"], sufficiency_report_path=scaffold_paths["sufficiency_report"],
        briefing_validation_path=briefing_validation_path, gap_diagnosis_path=telemetry_paths["gap_diagnosis"], backend=backend,
        model_confidence=str(render_state["model_confidence"]),
        calibrated_confidence=str(render_state["calibrated"]),
        map_quality_status=str(quality_report.get("status", "unknown")),
    )
def _attach_decision_ready_context_reports(
    prioritized_map: dict[str, Any],
    scaffold: dict[str, Any],
    *,
    question: str,
    source_lookup: dict[str, str],
) -> None:
    scaffold.update(
        build_decision_ready_context_bundle(
            prioritized_map,
            scaffold=scaffold,
            question=question,
            source_lookup=source_lookup,
        )
    )


def _attach_decision_spine_bundle(
    prioritized_map: dict[str, Any],
    scaffold: dict[str, Any],
    *,
    question: str,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> None:
    scaffold.update(
        build_decision_spine_bundle(
            prioritized_map, scaffold, question=question, backend=backend,
            backend_timeout=backend_timeout, backend_retries=backend_retries,
        )
    )


def _attach_model_context_audit(
    *,
    artifacts: Path,
    backend: str,
    prompt: str,
    scaffold: dict[str, Any],
    final_outputs: dict[str, Any],
) -> None:
    audit_path = write_model_context_audit(
        artifacts / "model_context_audit.json",
        backend=backend,
        legacy_prompt=prompt,
        global_plan_prompt=str(scaffold.get("global_memo_plan_prompt", "")),
        section_packets_path=final_outputs["summary_paths"].get("section_synthesis_packets"),
        reader_rewrite_prompt=str(final_outputs.get("rewrite_result", {}).get("prompt", "")),
    )
    final_outputs["summary_paths"]["model_context_audit"] = audit_path


def _apply_atomic_cards_to_briefing_map(prioritized_map: dict[str, Any], scaffold: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_map = apply_evidence_cards_to_map(prioritized_map, scaffold.get("atomic_evidence_cards", {}))
    updated_scaffold = dict(scaffold)
    updated_scaffold["seed_claims"] = _claims(normalized_map)[:10]
    return normalized_map, _expand_payload_reader_references(updated_scaffold, normalized_map)


def _validate_run_args(question: str, backend_timeout: int | None, backend_retries: int) -> None:
    if backend_retries < 0:
        raise ValueError("backend_retries must be nonnegative")
    if backend_timeout is not None and backend_timeout < 1:
        raise ValueError("backend_timeout must be positive")
    _require_concrete_question(question)


def _prepare_rendered_reader_packet(
    rendered: str,
    *,
    calibrated: str,
    scaffold: dict[str, Any],
    prioritized_map: dict[str, Any],
    source_lookup: dict[str, str],
) -> str:
    rendered = _ensure_confidence_visible(rendered, calibrated)
    rendered = append_evidence_by_decision_lever(rendered, scaffold)
    rendered = append_map_coverage_snapshot(rendered, scaffold)
    rendered = _normalize_reader_punctuation(expand_reader_map_references(rendered, prioritized_map))
    rendered = _clean_reader_packet_metadata(replace_source_ids(rendered, source_lookup))
    return polish_briefing_for_reader(rendered, scaffold)


def _write_final_reader_outputs(
    *,
    rendered: str,
    scaffold: dict[str, Any],
    prioritized_map: dict[str, Any],
    artifacts: Path,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_reader_memo_rewrite: bool = False,
) -> dict[str, Any]:
    from epistemic_case_mapper.map_briefing_section_rewrite import rewrite_reader_memo_by_section

    memo_package = compose_final_reader_memo_package(rendered, scaffold)
    evidence_appendix = str(memo_package["appendix"])
    section_rewrite_report_path = artifacts / "section_rewrite_report.json"
    section_rewrite_result = rewrite_reader_memo_by_section(
        str(memo_package["memo"]),
        evidence_appendix,
        memo_package["scaffold"],
        prioritized_map,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        artifacts=artifacts,
    )
    section_memo = str(section_rewrite_result["memo"])
    rewrite_prompt_path = artifacts / "reader_memo_rewrite_prompt.txt"
    rewrite_raw_path = artifacts / "reader_memo_rewrite_raw.txt"
    rewrite_report_path = artifacts / "reader_memo_rewrite_report.json"
    edit_artifact_paths = reader_memo_edit_artifact_paths(artifacts)
    rewrite_result = (
        rewrite_reader_memo_with_contract(
            section_memo,
            evidence_appendix,
            memo_package["scaffold"],
            prioritized_map,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
        )
        if run_reader_memo_rewrite
        else _skipped_reader_memo_rewrite(section_memo)
    )
    rewrite_result.setdefault("report", {})["section_context_acceptance_status"] = section_rewrite_result.get("report", {}).get(
        "section_context_acceptance_status"
    )
    memo_package["scaffold"]["section_context_acceptance_status"] = rewrite_result["report"]["section_context_acceptance_status"]
    if rewrite_result.get("prompt"):
        write_markdown(rewrite_prompt_path, str(rewrite_result.get("prompt", "")))
    if rewrite_result.get("raw"):
        write_markdown(rewrite_raw_path, str(rewrite_result.get("raw", "")))
    write_reader_memo_edit_artifacts(rewrite_result, edit_artifact_paths)
    reader_memo = ensure_reader_memo_metadata(str(rewrite_result["memo"]), memo_package["scaffold"])
    combined = reader_memo.rstrip() + "\n\n" + evidence_appendix.rstrip() + "\n"
    polish_report = briefing_reader_polish_report(combined, memo_package["scaffold"])
    memo_quality = memo_quality_report(combined, memo_package["scaffold"])
    validation = validate_briefing_against_scaffold(combined, memo_package["scaffold"], prioritized_map)
    briefing_path = artifacts / "BRIEFING.md"
    evidence_appendix_path = artifacts / "EVIDENCE_APPENDIX.md"
    polish_report_path = artifacts / "briefing_polish_report.json"
    memo_quality_path = artifacts / "memo_quality_report.json"
    curation_report_path = artifacts / "evidence_curation_report.json"
    briefing_validation_path = artifacts / "briefing_validation_report.json"
    final_traceability_path = artifacts / "decision_traceability_matrix_final.json"
    final_traceability_md_path = artifacts / "DECISION_TRACEABILITY_MATRIX_FINAL.md"
    memo_coherence_report_path = artifacts / "memo_coherence_report.json"
    section_role_quality_report_path = artifacts / "section_role_quality_report.json"
    pipeline_migration_ledger_path = artifacts / "pipeline_migration_ledger.json"
    runtime_budget_report_path = artifacts / "runtime_budget_report.json"
    final_brief_evaluation_path = artifacts / "final_brief_evaluation.json"
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
    write_markdown(briefing_path, reader_memo.rstrip() + "\n")
    write_markdown(evidence_appendix_path, evidence_appendix.rstrip() + "\n")
    write_json(final_traceability_path, traceability_matrix)
    write_markdown(final_traceability_md_path, render_decision_traceability_matrix_markdown(traceability_matrix))
    write_json(memo_coherence_report_path, memo_coherence)
    write_json(section_role_quality_report_path, role_quality)
    write_json(pipeline_migration_ledger_path, pipeline_migration)
    write_json(runtime_budget_report_path, runtime_budget)
    write_json(final_brief_evaluation_path, final_eval)
    write_json(briefing_validation_path, validation)
    write_json(polish_report_path, polish_report)
    write_json(memo_quality_path, memo_quality)
    write_json(curation_report_path, memo_package["curation_report"])
    write_json(section_rewrite_report_path, section_rewrite_result["report"])
    write_json(rewrite_report_path, rewrite_result["report"])
    return {
        "briefing_path": briefing_path,
        "evidence_appendix_path": evidence_appendix_path,
        "briefing_validation": validation,
        "polish_report": polish_report,
        "rewrite_result": rewrite_result,
        "summary_paths": {
            "briefing_validation_report": briefing_validation_path,
            "briefing_polish_report": polish_report_path,
            "memo_quality_report": memo_quality_path,
            "evidence_curation_report": curation_report_path,
            "section_rewrite_report": section_rewrite_report_path,
            "section_synthesis_packets": section_rewrite_result.get("section_packets_path"),
            "section_context_acceptance_report": section_rewrite_result.get("section_context_acceptance_report_path"),
            "decision_traceability_matrix_final": final_traceability_path,
            "decision_traceability_matrix_final_markdown": final_traceability_md_path,
            "memo_coherence_report": memo_coherence_report_path,
            "section_role_quality_report": section_role_quality_report_path,
            "pipeline_migration_ledger": pipeline_migration_ledger_path,
            "runtime_budget_report": runtime_budget_report_path,
            "final_brief_evaluation": final_brief_evaluation_path,
            "reader_memo_rewrite_report": rewrite_report_path,
            "reader_memo_rewrite_prompt": rewrite_prompt_path if rewrite_result.get("prompt") else None,
            "reader_memo_rewrite_raw": rewrite_raw_path if rewrite_result.get("raw") else None,
            **reader_memo_edit_summary_paths(rewrite_result, edit_artifact_paths),
        },
    }


def _section_first_generation_note(backend: str) -> str:
    return (
        "Whole-memo synthesis skipped.\n\n"
        "The pipeline built a deterministic source-grounded memo scaffold, then used model-backed section synthesis for each eligible section. "
        f"Section synthesis backend: {backend}.\n"
    )


def _skipped_reader_memo_rewrite(memo: str) -> dict[str, Any]:
    return {
        "memo": memo,
        "prompt": "",
        "raw": "",
        "report": {
            "schema_id": "reader_memo_rewrite_report_v1",
            "status": "skipped_after_section_rewrite",
            "accepted": False,
            "issues": [],
        },
    }


def _section_first_render_state(
    *,
    prompt: str,
    quality_report: dict[str, Any],
    scaffold: dict[str, Any],
) -> dict[str, Any]:
    model_confidence = "not specified"
    calibration = calibrate_confidence(model_confidence, quality_report)
    payload = deterministic_briefing_payload(scaffold)
    payload["confidence"] = calibration["calibrated_confidence"]
    rendered = _render_synthesis_packet(payload, map_payload={}, requirements=())
    return {
        "rendered": rendered,
        "model_confidence": model_confidence,
        "calibrated": calibration["calibrated_confidence"],
        "calibration": calibration,
        "parse_ok": False,
        "parse_diagnostics": model_parse_diagnostics(prompt, parse_ok=False),
    }


def build_map_briefing_prompt(
    *,
    candidate_map: dict[str, Any],
    quality_report: dict[str, Any],
    question: str,
    source_lookup: dict[str, str],
    erosion_audit: dict[str, Any],
    scaffold: dict[str, Any] | None = None,
) -> str:
    scaffold = scaffold or briefing_scaffold(candidate_map, quality_report, source_lookup, erosion_audit)
    return "\n\n".join(
        (
            "You are writing a decision-support briefing from a source-grounded epistemic map.",
            "Return valid compact JSON only. Do not wrap it in a markdown code fence.",
            "Required JSON shape: "
            "{\"decision_brief\": \"readable bottom-line prose\", "
            "\"confidence\": \"low|medium|high\", "
            "\"decision_implications\": [\"action-relevant implication\"], "
            "\"top_cruxes\": [{\"crux\": \"...\", \"why_it_matters\": \"...\", \"current_read\": \"...\", \"would_change_if\": \"...\"}], "
            "\"stress_caveats\": [\"decision-relevant caveat\"]}",
            "Rules:",
            "- Keep the JSON compact: decision_brief <= 160 words, decision_implications <= 4 items, top_cruxes <= 3 items, stress_caveats <= 4 items.",
            "- Do not return evidence_roles or audit_trail unless you need to correct the deterministic scaffold; the engine will attach those sections deterministically.",
            "- Answer the decision question directly, then explain the map-backed cruxes.",
            "- Use the deterministic section buckets as hard boundaries: synthesize each evidence_roles section only from that section's bucket.",
            "- Use `briefing_contract.answer_frame` to set the bottom-line strength; do not make a stronger claim than the contract allows.",
            "- Use `briefing_contract.scope_ledger` to keep scope caveats separate from the general/default answer.",
            "- Use `decision_synthesis_model.bottom_line.current_read` and `decision_model.default_answer.plain_language_instruction` as the controlling answer frame. Express it in the decision question's natural vocabulary rather than forcing a generic category label.",
            "- Use `decision_model.decision_slots` to include practical thresholds, high-risk subgroups, mechanisms, comparators, endpoint types, study designs, and recommendations when present.",
            "- If `decision_model.missing_decision_slots` names a slot that matters for the question, say the map did not expose it rather than inventing it.",
            "- Use `decision_model.evidence_families` to avoid dropping whole families such as RCTs, cohorts, guidelines, mechanisms, subgroups, comparators, or method limits.",
            "- Use `graph_synthesis_packet` before raw evidence tables: draft from issue clusters, load-bearing claims, bridge claims, and central tensions.",
            "- Each main section should correspond to a graph issue cluster or a cross-cluster tension; do not merely list isolated claims.",
            "- Use graph orphan claims only as caveats or appendix material unless they are high-weight scope boundaries.",
            "- Use `decision_synthesis_model` as the controlling decision-support structure: preserve its evidence lines, central tensions, scope boundaries, exceptions, recommendations, and cruxes.",
            "- Use `argument_model` to decide which support, counterarguments, scope boundaries, cruxes, quantities, and known failure modes are load-bearing for the memo.",
            "- Use `decision_argument_artifacts`: the matrix, findings, competing reads, argument graph, and traceability rows separate evidence, alternatives, uncertainty, and requirements before prose.",
            "- Treat `map_sufficiency_report.output_obligations` as the prose contract: satisfy present-slot obligations and explicitly acknowledge decision-relevant missing slots.",
            "- If `map_sufficiency_report.status` is limited or thin, make that limitation visible in caveats or audit trail.",
            "- Use `evidence_compression_table` as the main source for compact synthesis; it is already filtered for decision relevance and noise.",
            "- Preserve concept coverage from `evidence_compression_table.coverage`: mechanisms, subgroups, comparators, endpoints, thresholds, and study designs should not silently disappear.",
            "- Use `concept_evidence_packets` to synthesize by decision lever before composing the bottom line; do not collapse RCTs, cohorts, mechanisms, comparators, and subgroups into one generic evidence sentence.",
            "- Use `proposition_clusters` to synthesize claim clusters into propositions; do not narrate isolated claim fragments when a cluster-level proposition exists.",
            "- Use `briefing_plan` as the prose outline: bottom line first, then weighted reasons, then counterposition, then scope/method limits.",
            "- Use `evidence_weighting_ledger`; lead with high/medium weight direct evidence and identify low-weight evidence as limited, indirect, deterministic backfill, or source-incomplete.",
            "- Use `quantitative_evidence_cards` first, then `quantitative_anchors`, for quantitative depth: include only decision-relevant quantities such as effect sizes, intervals, p-values, sample sizes, thresholds, durations, and biomarker changes.",
            "- Do not dump every extracted number into prose; the full `quantity_ledger` is an appendix artifact.",
            "- Apply `briefing_contract.overstatement_lint` before returning: soften any sentence that violates an active lint rule.",
            "- Use `section_policy` for the meanings of main_support, conflicting_evidence, scope_limits, and method_limits.",
            "- Do not put concern, counterposition, or scope-boundary evidence in main_support unless the section_policy explicitly says it supports the requested answer frame.",
            "- Preserve tensions, scope limits, and method limits; do not flatten them into a single confident answer.",
            "- Write section prose in human terms; do not say `Claim A`, `Claim B`, raw claim IDs, or raw relation IDs.",
            "- Use source display names, not raw source IDs, claim IDs, or relation IDs, in reader-facing fields.",
            "- Every evidence_roles bullet must be a substantive evidence statement, not just a source name.",
            "- An evidence_roles bullet is invalid if it only says which source exists; include the relevant claim and put the source in parentheses.",
            "- Do not invent facts beyond the map, quality report, or erosion audit.",
            "- Calibrate uncertainty to the quality report. A map marked review_recommended or needs_repair cannot support high confidence.",
            "- Keep the briefing concise and readable for a human judge.",
            "- Do not replace the decision question with source-use advice. Source-use advice belongs in scope caveats unless the question itself asks how to use sources.",
            f"Decision question: {question}",
            "Deterministic briefing scaffold:\n" + json.dumps(model_briefing_scaffold(scaffold), indent=2),
            "Map quality report:\n" + json.dumps(_quality_brief(quality_report), indent=2),
        )
    )


def _require_concrete_question(question: str) -> None:
    report = question_quality_report(question)
    if report["status"] == "blocked":
        issues = "; ".join(str(issue.get("message", issue.get("issue_type", "question issue"))) for issue in report.get("issues", []))
        raise ValueError(f"run_map_briefing requires a concrete decision question: {issues}")

def briefing_scaffold(
    candidate_map: dict[str, Any],
    quality_report: dict[str, Any],
    source_lookup: dict[str, str],
    erosion_audit: dict[str, Any],
    question: str = "",
    source_urls: dict[str, str] | None = None,
    source_citation_labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    from epistemic_case_mapper.map_briefing_decision_support_model import (
        build_decision_support_model,
        decision_support_scaffold_fields,
    )

    support_model = build_decision_support_model(
        candidate_map=candidate_map,
        quality_report=quality_report,
        source_lookup=source_lookup,
        erosion_audit=erosion_audit,
        question=question,
    )
    briefing_map = support_model.get("briefing_candidate_map") if isinstance(support_model.get("briefing_candidate_map"), dict) else candidate_map
    scaffold = decision_support_scaffold_fields(
        support_model,
        candidate_map=briefing_map,
        quality_report=quality_report,
        source_lookup=source_lookup,
        question=question,
    )
    if source_urls:
        scaffold["source_urls"] = {
            str(source_id): str(url).strip()
            for source_id, url in source_urls.items()
            if str(source_id).strip() and str(url).strip()
        }
    if source_citation_labels:
        scaffold["source_citation_labels"] = {
            str(source_id): str(label).strip()
            for source_id, label in source_citation_labels.items()
            if str(source_id).strip() and str(label).strip()
        }
    return _expand_payload_reader_references(scaffold, briefing_map)
def deterministic_briefing_payload(
    scaffold: dict[str, Any],
    *,
    extracted_brief: str | None = None,
    parse_failure: bool = False,
) -> dict[str, Any]:
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    default_answer = decision_model.get("default_answer", {}) if isinstance(decision_model.get("default_answer"), dict) else {}
    evidence_roles = scaffold.get("evidence_roles", {}) if isinstance(scaffold.get("evidence_roles"), dict) else {}
    sufficiency_report = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    brief = _deterministic_decision_brief(scaffold, extracted_brief=extracted_brief)
    payload = {
        "decision_brief": brief,
        "confidence": str(default_answer.get("confidence_cap") or scaffold.get("confidence_cap") or "medium"),
        "decision_implications": _dedupe(
            [
                *_deterministic_decision_implications(decision_model),
                *_sufficiency_implications(sufficiency_report),
            ]
        )[:8],
        "top_cruxes": _deterministic_top_cruxes(scaffold),
        "evidence_roles": {
            key: _string_list(evidence_roles.get(key))
            for key in ("main_support", "conflicting_evidence", "scope_limits", "method_limits")
        },
        "stress_caveats": _deterministic_stress_caveats(scaffold),
        "audit_trail": _string_list(scaffold.get("audit_trail")),
    }
    if parse_failure:
        payload["audit_trail"] = _dedupe(
            [
                "The model returned a truncated or invalid structured packet; deterministic source-grounded fallback completed the briefing sections.",
                *payload["audit_trail"],
            ]
        )
    return payload
def _sufficiency_implications(sufficiency_report: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for slot in _string_list(sufficiency_report.get("missing_expected_decision_slots")):
        items.append(f"The current source packet does not establish a decision-relevant {_slot_label(slot)}; do not fill that gap by inference.")
    for family in _string_list(sufficiency_report.get("missing_expected_evidence_families")):
        items.append(f"The current source packet does not establish {family.replace('_', ' ')} evidence; do not imply it was assessed.")
    return items

def _deterministic_decision_brief(scaffold: dict[str, Any], *, extracted_brief: str | None = None) -> str:
    if extracted_brief and extracted_brief.strip():
        return extracted_brief.strip()
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    default_answer = decision_model.get("default_answer", {}) if isinstance(decision_model.get("default_answer"), dict) else {}
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    bottom_line = synthesis.get("bottom_line", {}) if isinstance(synthesis.get("bottom_line"), dict) else {}
    classification = str(default_answer.get("classification", "mixed_or_context_dependent")).replace("_", " ")
    instruction = str(default_answer.get("plain_language_instruction", "")).strip()
    current_read = str(bottom_line.get("current_read", "")).strip()
    spine = scaffold.get("canonical_decision_spine", {}) if isinstance(scaffold.get("canonical_decision_spine"), dict) else {}
    canonical = spine.get("default_answer", {}) if isinstance(spine.get("default_answer"), dict) else {}
    if canonical.get("role") != "missing_slot" and str(canonical.get("claim", "")).strip(): current_read = str(canonical["claim"]).strip()
    main_reasons = [row for row in decision_model.get("main_reasons", []) if isinstance(row, dict)]
    counters = [row for row in decision_model.get("strongest_counterarguments", []) if isinstance(row, dict)]
    graph_claims = deterministic_graph_claim_sentences(scaffold)
    if instruction.lower().startswith(("state ", "do not ", "phrase ")):
        instruction = current_read or f"The current map supports a {classification} answer frame."
    parts = [current_read or instruction or f"The map supports a {classification} answer frame."]
    if main_reasons:
        parts.append(f"The main support is: {main_reasons[0].get('proposition', '')}")
    elif graph_claims:
        parts.append(f"The most load-bearing evidence is: {graph_claims[0]}")
    if counters:
        parts.append(f"The strongest counterposition is: {counters[0].get('proposition', '')}")
    elif len(graph_claims) > 1:
        parts.append(f"A second important evidence line is: {graph_claims[1]}")
    return " ".join(part.strip() for part in parts if part and str(part).strip())

def _deterministic_decision_implications(decision_model: dict[str, Any]) -> list[str]:
    items: list[str] = []
    items.extend(_string_list(decision_model.get("practical_recommendations")))
    slots = decision_model.get("decision_slots", {}) if isinstance(decision_model.get("decision_slots"), dict) else {}
    slot_labels = {
        "dose_or_intensity_threshold": "Dose/intensity boundary",
        "high_risk_subgroup": "Separate subgroup",
        "substitution_or_comparator": "Comparator to keep visible",
        "endpoint_type": "Endpoint boundary",
    }
    for slot, label in slot_labels.items():
        for entry in slots.get(slot, [])[:2] if isinstance(slots.get(slot), list) else []:
            if not isinstance(entry, dict):
                continue
            value = str(entry.get("value", "")).strip()
            source = str(entry.get("source", "")).strip()
            if value:
                items.append(f"{label}: {value}" + (f" ({source})" if source else ""))
    missing = _string_list(decision_model.get("missing_decision_slots"))
    if missing:
        items.append("The map did not expose these decision slots: " + ", ".join(missing[:5]) + ".")
    return _dedupe(items)[:8]

def _deterministic_top_cruxes(scaffold: dict[str, Any]) -> list[dict[str, str]]:
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    rows: list[dict[str, str]] = []
    refined = scaffold.get("refined_cruxes", {}) if isinstance(scaffold.get("refined_cruxes"), dict) else {}
    for item in refined.get("cruxes", [])[:5] if isinstance(refined.get("cruxes"), list) else []:
        if not isinstance(item, dict):
            continue
        crux = str(item.get("crux", "")).strip()
        if crux:
            rows.append(
                {
                    "crux": crux,
                    "why_it_matters": str(item.get("why_it_matters", "")).strip(),
                    "current_read": str(item.get("current_read", "")).strip(),
                    "would_change_if": str(item.get("would_change_if", "")).strip(),
                }
            )
    if rows:
        return _dedupe_dicts(rows)[:5]
    crux_contract = scaffold.get("crux_contract", {}) if isinstance(scaffold.get("crux_contract"), dict) else {}
    for item in crux_contract.get("cruxes", [])[:5] if isinstance(crux_contract.get("cruxes"), list) else []:
        if not isinstance(item, dict):
            continue
        crux = str(item.get("crux", "")).strip()
        if not crux:
            continue
        rows.append(
            {
                "crux": crux,
                "why_it_matters": str(item.get("why_it_matters", "")).strip() or "This condition changes the option comparison.",
                "current_read": str(item.get("current_read", "")).strip() or _crux_current_read(crux, ""),
                "would_change_if": str(item.get("would_change_if", "")).strip() or _crux_would_change_if(crux, ""),
            }
        )
    if rows:
        return _dedupe_dicts(rows)[:5]
    for item in scaffold.get("crux_candidates", [])[:5]:
        if not isinstance(item, dict):
            continue
        crux = str(item.get("candidate_crux", "")).strip()
        if not crux:
            continue
        rows.append(
            {
                "crux": crux,
                "why_it_matters": str(item.get("why_it_matters", "")) or "Changing this item would materially alter the decision read.",
                "current_read": "This distinction changes how the evidence should be interpreted.",
                "would_change_if": "New evidence weakened or reversed this distinction.",
            }
        )
    for item in decision_model.get("tension_resolutions", [])[:4]:
        if not isinstance(item, dict):
            continue
        tension = str(item.get("tension", "")).strip()
        if not tension:
            continue
        sides = [side.strip() for side in tension.split(" / ") if side.strip()]
        if len(sides) == 2 and sides[0] == sides[1]:
            continue
        rows.append(
            {
                "crux": tension,
                "why_it_matters": str(item.get("resolution_hint", "")) or "This tension controls how broadly the default answer travels.",
                "current_read": str(item.get("relation_type", "")).replace("_", " ") or "evidence tension",
                "would_change_if": "One side of the tension generalized across the default population, dose, endpoint, and study design.",
            }
        )
    if not rows:
        for item in _string_list(decision_model.get("what_would_change_answer"))[:3]:
            rows.append(
                {
                    "crux": item,
                    "why_it_matters": "This is a stated condition for changing the answer.",
                    "current_read": "Not resolved by the current map.",
                    "would_change_if": "The named limitation were resolved by stronger or more directly applicable evidence.",
                }
            )
    return _dedupe_dicts(rows)[:5]

def _deterministic_stress_caveats(scaffold: dict[str, Any]) -> list[str]:
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    items: list[str] = []
    for key in ("does_not_hold_for", "what_would_change_answer"):
        items.extend(_string_list(decision_model.get(key)))
    contract = scaffold.get("briefing_contract", {}) if isinstance(scaffold.get("briefing_contract"), dict) else {}
    answer_frame = contract.get("answer_frame", {}) if isinstance(contract.get("answer_frame"), dict) else {}
    items.extend(_string_list(answer_frame.get("why_not_stronger")))
    items.extend(_string_list(scaffold.get("quality_issues")))
    return _dedupe(items)[:8]

def append_map_coverage_snapshot(rendered: str, scaffold: dict[str, Any]) -> str:
    """Append compact deterministic coverage rows so retained map concepts remain visible."""
    if "## Map Coverage Snapshot" in rendered:
        return rendered
    table = scaffold.get("evidence_compression_table", {})
    if not isinstance(table, dict):
        return rendered
    rows = _coverage_snapshot_rows(table)
    if not rows:
        return rendered
    lines = [
        rendered.rstrip(),
        "",
        "## Map Coverage Snapshot",
        "",
        "| Concept | Current map read | Why it matters |",
        "|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                _markdown_table_cell(str(row[key]))
                for key in ("concept", "current_map_read", "why_it_matters")
            )
            + " |"
        )
    return "\n".join(lines)



# Explicit cross-module dependencies for compatibility facade removal.
from epistemic_case_mapper.map_briefing_decision_model import (
    _slot_label,
    build_briefing_plan,
    build_decision_model,
    build_map_sufficiency_report,
    build_proposition_clusters,
)
from epistemic_case_mapper.map_briefing_evidence_partition import (
    _crux_current_read,
    _crux_would_change_if,
    partition_map_evidence,
    repair_briefing_payload,
)
from epistemic_case_mapper.map_briefing_evidence_tables import (
    _coverage_snapshot_rows,
    _extract_json_string_field_local,
    _markdown_table_cell,
    build_briefing_contract,
    build_concept_evidence_packets,
    build_evidence_compression_table,
    build_evidence_weighting_ledger,
)
from epistemic_case_mapper.map_briefing_map_utils import (
    _claims,
    _expand_payload_reader_references,
    _quality_brief,
    _relations,
    _resolve,
    adaptive_briefing_claim_budget,
    build_source_display_lookup,
    calibrate_confidence,
    confidence_cap,
    expand_reader_map_references,
    generated_map_erosion_audit,
    prioritize_map_for_briefing,
    replace_source_ids,
)
from epistemic_case_mapper.map_briefing_reader_contracts import (
    _profile_vocabulary_for_map,
    annotate_map_with_evidence_slots,
    append_evidence_by_decision_lever,
    build_crux_contract,
    build_evidence_slot_ledger,
    build_option_comparison,
    compose_final_reader_memo_package,
    polish_briefing_for_reader,
    rewrite_reader_memo_with_contract,
)
from epistemic_case_mapper.map_briefing_reader_polish import briefing_reader_polish_report
from epistemic_case_mapper.map_briefing_memo_metadata import ensure_reader_memo_metadata
from epistemic_case_mapper.map_briefing_validation import (
    _confidence_label,
    _dedupe,
    _dedupe_dicts,
    _ensure_confidence_visible,
    _looks_like_structured_attempt,
    _normalize_reader_punctuation,
    _rel,
    _string_list,
    model_parse_diagnostics,
    validate_briefing_against_scaffold,
)
