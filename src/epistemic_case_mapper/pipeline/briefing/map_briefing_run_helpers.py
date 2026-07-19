from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_artifacts import write_run_summary


def prepare_map_briefing_inputs(
    *,
    repo_root: Path,
    map_path: str | Path,
    quality_report_path: str | Path,
    source_titles: dict[str, str] | None,
    max_claims: int | None,
) -> dict[str, Any]:
    from epistemic_case_mapper.pipeline.briefing.map_briefing_claim_canonicalization import canonicalize_claims_for_briefing
    from epistemic_case_mapper.pipeline.briefing.map_briefing_map_utils import (
        _resolve,
        adaptive_briefing_claim_budget,
        build_source_display_lookup,
        generated_map_erosion_audit,
        prioritize_map_for_briefing,
    )
    from epistemic_case_mapper.pipeline.briefing.map_briefing_reader_contracts import annotate_map_with_evidence_slots

    map_file = _resolve(repo_root, map_path)
    quality_file = _resolve(repo_root, quality_report_path)
    candidate_map = annotate_map_with_evidence_slots(json.loads(map_file.read_text(encoding="utf-8")))
    quality_report = json.loads(quality_file.read_text(encoding="utf-8"))
    candidate_map, canonicalization_report = canonicalize_claims_for_briefing(candidate_map)
    source_lookup = build_source_display_lookup(candidate_map, source_titles=source_titles)
    effective_max_claims = adaptive_briefing_claim_budget(candidate_map, quality_report, requested_max_claims=max_claims)
    prioritized_map, prioritization_report = prioritize_map_for_briefing(
        candidate_map,
        quality_report=quality_report,
        max_claims=effective_max_claims,
    )
    prioritization_report["claim_canonicalization_report"] = canonicalization_report
    prioritization_report["requested_max_claims"] = max_claims
    prioritization_report["effective_max_claims"] = effective_max_claims
    prioritization_report["budget_policy"] = "adaptive" if not max_claims else "fixed"
    return {
        "map_file": map_file,
        "candidate_map": candidate_map,
        "quality_report": quality_report,
        "source_lookup": source_lookup,
        "effective_max_claims": effective_max_claims,
        "prioritized_map": prioritized_map,
        "prioritization_report": prioritization_report,
        "canonicalization_report": canonicalization_report,
        "erosion_audit": generated_map_erosion_audit(prioritized_map),
    }


def write_map_briefing_run_summary(
    *,
    artifacts: Path,
    repo_root: Path,
    backend: str,
    render_state: dict[str, Any],
    question: str,
    briefing_path: Path,
    evidence_appendix_path: Path,
    raw_path: Path,
    scaffold_paths: dict[str, Path],
    telemetry_paths: dict[str, Path],
    final_outputs: dict[str, Any],
    source_lookup: dict[str, str],
    quality_report: dict[str, Any],
    candidate_map: dict[str, Any],
    prioritized_map: dict[str, Any],
    max_claims: int | None,
    effective_max_claims: int,
    erosion_audit: dict[str, Any],
    scaffold: dict[str, Any],
) -> Path:
    return write_run_summary(
        artifacts=artifacts,
        repo_root=repo_root,
        backend=backend,
        parse_ok=bool(render_state["parse_ok"]),
        parse_diagnostics=render_state["parse_diagnostics"],
        question=question,
        briefing_path=briefing_path,
        evidence_appendix_path=evidence_appendix_path,
        raw_path=raw_path,
        scaffold_paths=scaffold_paths,
        telemetry_paths=telemetry_paths,
        final_outputs=final_outputs,
        source_lookup=source_lookup,
        quality_report=quality_report,
        model_confidence=str(render_state["model_confidence"]),
        calibrated=str(render_state["calibrated"]),
        calibration=render_state["calibration"],
        candidate_map=candidate_map,
        prioritized_map=prioritized_map,
        max_claims=max_claims,
        effective_max_claims=effective_max_claims,
        erosion_audit=erosion_audit,
        scaffold=scaffold,
    )
