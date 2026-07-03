from __future__ import annotations

from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown
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
    }
    write_markdown(paths["prompt"], prompt)
    write_json(paths["prioritized_map"], prioritized_map)
    write_json(paths["prioritization_report"], prioritization_report)
    write_json(paths["erosion_audit"], erosion_audit)
    write_json(paths["sufficiency_report"], scaffold.get("map_sufficiency_report", {}))
    write_json(paths["decision_synthesis_model"], scaffold.get("decision_synthesis_model", {}))
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
    return summary_path


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
    }


def _claims(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    claims = candidate_map.get("claims", [])
    return [claim for claim in claims if isinstance(claim, dict)] if isinstance(claims, list) else []


def _relations(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    relations = candidate_map.get("relations", [])
    return [relation for relation in relations if isinstance(relation, dict)] if isinstance(relations, list) else []


def _rel(repo_root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)
