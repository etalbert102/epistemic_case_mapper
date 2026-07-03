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
from epistemic_case_mapper.map_briefing_frame_policy import adapt_decision_model_to_frame, section_policy_for_frame

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
    source_titles: dict[str, str] | None = None, max_claims: int | None = 0,
) -> MapBriefingResult:
    if backend_retries < 0:
        raise ValueError("backend_retries must be nonnegative")
    if backend_timeout is not None and backend_timeout < 1:
        raise ValueError("backend_timeout must be positive")
    _require_concrete_question(question)
    map_file = _resolve(repo_root, map_path)
    quality_file = _resolve(repo_root, quality_report_path)
    candidate_map = json.loads(map_file.read_text(encoding="utf-8"))
    candidate_map = annotate_map_with_evidence_slots(candidate_map)
    quality_report = json.loads(quality_file.read_text(encoding="utf-8"))
    artifacts = _resolve(repo_root, output_dir or Path("artifacts") / "map_briefings" / map_file.stem)
    artifacts.mkdir(parents=True, exist_ok=True)
    source_lookup = build_source_display_lookup(candidate_map, source_titles=source_titles)
    effective_max_claims = adaptive_briefing_claim_budget(candidate_map, quality_report, requested_max_claims=max_claims)
    prioritized_map, prioritization_report = prioritize_map_for_briefing(
        candidate_map,
        quality_report=quality_report,
        max_claims=effective_max_claims,
    )
    prioritization_report["requested_max_claims"] = max_claims
    prioritization_report["effective_max_claims"] = effective_max_claims
    prioritization_report["budget_policy"] = "adaptive" if not max_claims else "fixed"
    erosion_audit = generated_map_erosion_audit(prioritized_map)
    scaffold = briefing_scaffold(prioritized_map, quality_report, source_lookup, erosion_audit, question=question)
    prompt = build_map_briefing_prompt(
        candidate_map=prioritized_map,
        quality_report=quality_report,
        question=question,
        source_lookup=source_lookup,
        erosion_audit=erosion_audit,
        scaffold=scaffold,
    )

    prompt_path = artifacts / "map_briefing_prompt.txt"
    prioritized_map_path = artifacts / "prioritized_map.json"
    prioritization_report_path = artifacts / "map_prioritization_report.json"
    erosion_audit_path = artifacts / "generated_map_erosion_audit.json"
    sufficiency_report_path = artifacts / "map_sufficiency_report.json"
    briefing_validation_path = artifacts / "briefing_validation_report.json"
    write_markdown(prompt_path, prompt)
    write_json(prioritized_map_path, prioritized_map)
    write_json(prioritization_report_path, prioritization_report)
    write_json(erosion_audit_path, erosion_audit)
    write_json(sufficiency_report_path, scaffold.get("map_sufficiency_report", {}))

    result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    raw_path = artifacts / "map_briefing_raw.txt"
    write_markdown(raw_path, result.text)
    render_state = _render_model_briefing_output(
        result=result,
        prompt=prompt,
        quality_report=quality_report,
        scaffold=scaffold,
        source_lookup=source_lookup,
        prioritized_map=prioritized_map,
    )
    rendered = str(render_state["rendered"])
    model_confidence = str(render_state["model_confidence"])
    calibrated = str(render_state["calibrated"])
    calibration = render_state["calibration"]
    parse_ok = bool(render_state["parse_ok"])
    parse_diagnostics = render_state["parse_diagnostics"]
    rendered = _ensure_confidence_visible(rendered, calibrated)
    rendered = append_evidence_by_decision_lever(rendered, scaffold)
    rendered = append_map_coverage_snapshot(rendered, scaffold)
    rendered = _normalize_reader_punctuation(expand_reader_map_references(rendered, prioritized_map))
    rendered = _clean_reader_packet_metadata(replace_source_ids(rendered, source_lookup))
    rendered = polish_briefing_for_reader(rendered, scaffold)
    final_outputs = _write_final_reader_outputs(
        rendered=rendered,
        scaffold=scaffold,
        prioritized_map=prioritized_map,
        artifacts=artifacts,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
    )
    briefing_path = final_outputs["briefing_path"]
    evidence_appendix_path = final_outputs["evidence_appendix_path"]
    summary_path = artifacts / "briefing_summary.json"
    write_json(
        summary_path,
        _map_briefing_summary_payload(
            repo_root=repo_root,
            result_backend=result.backend,
            parse_ok=parse_ok,
            parse_diagnostics=parse_diagnostics,
            question=question,
            paths={
                "briefing": briefing_path,
                "evidence_appendix": evidence_appendix_path,
                "prompt": prompt_path,
                "raw": raw_path,
                "prioritized_map": prioritized_map_path,
                "prioritization_report": prioritization_report_path,
                "generated_map_erosion_audit": erosion_audit_path,
                "map_sufficiency_report": sufficiency_report_path,
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
        ),
    )
    return MapBriefingResult(
        briefing_path=briefing_path,
        summary_path=summary_path,
        prompt_path=prompt_path,
        prioritized_map_path=prioritized_map_path,
        prioritization_report_path=prioritization_report_path,
        erosion_audit_path=erosion_audit_path,
        sufficiency_report_path=sufficiency_report_path,
        briefing_validation_path=briefing_validation_path,
        backend=result.backend,
        model_confidence=model_confidence,
        calibrated_confidence=calibrated,
        map_quality_status=str(quality_report.get("status", "unknown")),
    )

def _write_final_reader_outputs(
    *,
    rendered: str,
    scaffold: dict[str, Any],
    prioritized_map: dict[str, Any],
    artifacts: Path,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
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
    rewrite_result = rewrite_reader_memo_with_contract(
        section_memo,
        evidence_appendix,
        memo_package["scaffold"],
        prioritized_map,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
    )
    if rewrite_result.get("prompt"):
        write_markdown(rewrite_prompt_path, str(rewrite_result.get("prompt", "")))
    if rewrite_result.get("raw"):
        write_markdown(rewrite_raw_path, str(rewrite_result.get("raw", "")))
    reader_memo = str(rewrite_result["memo"])
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
    write_markdown(briefing_path, reader_memo.rstrip() + "\n")
    write_markdown(evidence_appendix_path, evidence_appendix.rstrip() + "\n")
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
            "reader_memo_rewrite_report": rewrite_report_path,
            "reader_memo_rewrite_prompt": rewrite_prompt_path if rewrite_result.get("prompt") else None,
            "reader_memo_rewrite_raw": rewrite_raw_path if rewrite_result.get("raw") else None,
        },
    }

def _render_model_briefing_output(
    *,
    result: Any,
    prompt: str,
    quality_report: dict[str, Any],
    scaffold: dict[str, Any],
    source_lookup: dict[str, str],
    prioritized_map: dict[str, Any],
) -> dict[str, Any]:
    if result.prompt_only:
        model_confidence = "not specified"
        calibration = calibrate_confidence(model_confidence, quality_report)
        return {
            "rendered": prompt,
            "model_confidence": model_confidence,
            "calibrated": calibration["calibrated_confidence"],
            "calibration": calibration,
            "parse_ok": False,
            "parse_diagnostics": model_parse_diagnostics(result.text, parse_ok=False),
        }
    payload = _parse_json(result.text)
    parse_ok = isinstance(payload, dict)
    parse_diagnostics = model_parse_diagnostics(result.text, parse_ok=parse_ok)
    model_confidence = _confidence_label(payload.get("confidence")) if payload is not None else "not specified"
    calibration = calibrate_confidence(model_confidence, quality_report)
    calibrated = calibration["calibrated_confidence"]
    if payload is None and _looks_like_structured_attempt(result.text):
        payload = deterministic_briefing_payload(
            scaffold,
            extracted_brief=_extract_json_string_field_local(result.text, "decision_brief"),
            parse_failure=True,
        )
    if payload is not None:
        payload = repair_briefing_payload(payload, scaffold, source_lookup, prioritized_map)
        payload["confidence"] = calibrated
        rendered = _render_synthesis_packet(payload, map_payload=prioritized_map, requirements=())
    else:
        rendered = result.text.strip()
    return {
        "rendered": rendered,
        "model_confidence": model_confidence,
        "calibrated": calibrated,
        "calibration": calibration,
        "parse_ok": parse_ok,
        "parse_diagnostics": parse_diagnostics,
    }

def _map_briefing_summary_payload(
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
            "- Use `decision_model.default_answer.classification` as the controlling answer frame. State that frame directly before nuance.",
            "- Use `decision_model.decision_slots` to include practical thresholds, high-risk subgroups, mechanisms, comparators, endpoint types, study designs, and recommendations when present.",
            "- If `decision_model.missing_decision_slots` names a slot that matters for the question, say the map did not expose it rather than inventing it.",
            "- Use `decision_model.evidence_families` to avoid dropping whole families such as RCTs, cohorts, guidelines, mechanisms, subgroups, comparators, or method limits.",
            "- Treat `map_sufficiency_report.output_obligations` as the prose contract: satisfy present-slot obligations and explicitly acknowledge decision-relevant missing slots.",
            "- If `map_sufficiency_report.status` is limited or thin, make that limitation visible in caveats or audit trail.",
            "- Use `evidence_compression_table` as the main source for compact synthesis; it is already filtered for decision relevance and noise.",
            "- Preserve concept coverage from `evidence_compression_table.coverage`: mechanisms, subgroups, comparators, endpoints, thresholds, and study designs should not silently disappear.",
            "- Use `concept_evidence_packets` to synthesize by decision lever before composing the bottom line; do not collapse RCTs, cohorts, mechanisms, comparators, and subgroups into one generic evidence sentence.",
            "- Use `proposition_clusters` to synthesize claim clusters into propositions; do not narrate isolated claim fragments when a cluster-level proposition exists.",
            "- Use `briefing_plan` as the prose outline: bottom line first, then weighted reasons, then counterposition, then scope/method limits.",
            "- Use `evidence_weighting_ledger`; lead with high/medium weight direct evidence and identify low-weight evidence as limited, indirect, deterministic backfill, or source-incomplete.",
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
            "Deterministic briefing scaffold:\n" + json.dumps(_model_briefing_scaffold(scaffold), indent=2),
            "Map quality report:\n" + json.dumps(_quality_brief(quality_report), indent=2),
        )
    )


def _require_concrete_question(question: str) -> None:
    report = question_quality_report(question)
    if report["status"] == "blocked":
        issues = "; ".join(str(issue.get("message", issue.get("issue_type", "question issue"))) for issue in report.get("issues", []))
        raise ValueError(f"run_map_briefing requires a concrete decision question: {issues}")

def _model_briefing_scaffold(scaffold: dict[str, Any]) -> dict[str, Any]:
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    evidence_ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    compact_ledger = {
        "family_counts": evidence_ledger.get("family_counts", {}),
        "decision_concept_counts": evidence_ledger.get("decision_concept_counts", {}),
        "weight_counts": evidence_ledger.get("weight_counts", {}),
        "top_evidence_by_section": _compact_top_evidence_sections(evidence_ledger.get("top_evidence_by_section", {})),
        "notes": evidence_ledger.get("notes", []),
    }
    compact_decision_model = {
        key: decision_model.get(key)
        for key in (
            "default_answer",
            "decision_slots",
            "missing_decision_slots",
            "evidence_families",
            "main_reasons",
            "strongest_counterarguments",
            "tension_resolutions",
            "practical_recommendations",
            "what_would_change_answer",
            "prose_requirements",
        )
    }
    return {
        "quality_status": scaffold.get("quality_status"),
        "quality_score": scaffold.get("quality_score"),
        "confidence_cap": scaffold.get("confidence_cap"),
        "briefing_contract": scaffold.get("briefing_contract"),
        "decision_frame": scaffold.get("decision_frame"),
        "decision_model": compact_decision_model,
        "evidence_compression_table": scaffold.get("evidence_compression_table"),
        "concept_evidence_packets": _model_concept_evidence_packets(scaffold.get("concept_evidence_packets")),
        "map_sufficiency_report": scaffold.get("map_sufficiency_report"),
        "briefing_plan": scaffold.get("briefing_plan"),
        "evidence_weighting_ledger": compact_ledger,
        "evidence_roles_for_deterministic_attachment": scaffold.get("evidence_roles"),
        "crux_candidates": scaffold.get("crux_candidates"),
        "refined_cruxes": scaffold.get("refined_cruxes"),
        "quality_issues": scaffold.get("quality_issues"),
    }

def _compact_top_evidence_sections(value: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, dict):
        return {}
    compact: dict[str, list[dict[str, Any]]] = {}
    for section, rows in value.items():
        compact_rows: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            noise = row.get("noise", {}) if isinstance(row.get("noise"), dict) else {}
            compact_rows.append(
                {
                    "claim_id": row.get("claim_id"),
                    "section": row.get("section"),
                    "weight": row.get("weight"),
                    "score": row.get("score"),
                    "source": row.get("source"),
                    "evidence_family": row.get("evidence_family"),
                    "decision_concepts": row.get("decision_concepts", []),
                    "noise_kind": noise.get("kind", "none"),
                    "claim": _compressed_claim_text(str(row.get("claim", "")), noise),
                }
            )
        compact[str(section)] = compact_rows[:6]
    return compact

def _model_concept_evidence_packets(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    compact_packets: list[dict[str, Any]] = []
    for packet in value.get("packets", []) if isinstance(value.get("packets"), list) else []:
        if not isinstance(packet, dict):
            continue
        compact_packets.append(
            {
                "concept": packet.get("concept"),
                "label": packet.get("label"),
                "synthesis_job": packet.get("synthesis_job"),
                "must_surface_terms": packet.get("must_surface_terms", []),
                "rows": [
                    {
                        "claim_id": row.get("claim_id"),
                        "source": row.get("source"),
                        "weight": row.get("weight"),
                        "claim": row.get("claim"),
                        "why_it_matters": row.get("why_it_matters"),
                    }
                    for row in packet.get("rows", [])[:3]
                    if isinstance(row, dict)
                ],
            }
        )
    return {
        "schema_id": value.get("schema_id"),
        "method": value.get("method"),
        "packets": compact_packets[:8],
    }

def briefing_scaffold(
    candidate_map: dict[str, Any],
    quality_report: dict[str, Any],
    source_lookup: dict[str, str],
    erosion_audit: dict[str, Any],
    question: str = "",
) -> dict[str, Any]:
    partition = partition_map_evidence(candidate_map, source_lookup)
    evidence_roles = partition["evidence_roles"]
    cruxes = partition["crux_candidates"]
    audit_trail = list(partition["audit_trail"])
    vocabulary = _profile_vocabulary_for_map(candidate_map)
    contract = build_briefing_contract(partition, quality_report, vocabulary=vocabulary)
    evidence_ledger = build_evidence_weighting_ledger(candidate_map, partition, quality_report, source_lookup)
    proposition_clusters = build_proposition_clusters(candidate_map, evidence_ledger, source_lookup)
    evidence_compression_table = build_evidence_compression_table(candidate_map, evidence_ledger, source_lookup)
    concept_evidence_packets = build_concept_evidence_packets(evidence_ledger)
    option_comparison = build_option_comparison(question, evidence_ledger, candidate_map)
    crux_contract = build_crux_contract(candidate_map, evidence_ledger, option_comparison)
    refined_cruxes = refine_crux_contract(crux_contract, candidate_map)
    decision_frame = build_decision_frame(candidate_map, evidence_ledger, quality_report, question=question)
    decision_model = build_decision_model(proposition_clusters, contract, quality_report, evidence_ledger)
    decision_model = adapt_decision_model_to_frame(decision_model, decision_frame)
    sufficiency_report = build_map_sufficiency_report(
        candidate_map,
        question=question,
        evidence_ledger=evidence_ledger,
        decision_model=decision_model,
        quality_report=quality_report,
    )
    briefing_plan = build_briefing_plan(partition, contract, evidence_ledger, quality_report, decision_model)
    for item in erosion_audit.get("items", []):
        if isinstance(item, dict) and item.get("reader_anchor"):
            audit_trail.append(str(item["reader_anchor"]))
    scaffold = {
        "question": question,
        "quality_status": quality_report.get("status"),
        "quality_score": quality_report.get("score"),
        "confidence_cap": confidence_cap(quality_report),
        "epistemic_config": candidate_map.get("epistemic_config", {}),
        "section_policy": section_policy_for_frame(decision_frame),
        "briefing_contract": contract,
        "evidence_weighting_ledger": evidence_ledger,
        "evidence_slot_ledger": build_evidence_slot_ledger(evidence_ledger),
        "proposition_clusters": proposition_clusters,
        "decision_model": decision_model,
        "evidence_compression_table": evidence_compression_table,
        "concept_evidence_packets": concept_evidence_packets,
        "option_comparison": option_comparison,
        "crux_contract": crux_contract,
        "refined_cruxes": refined_cruxes,
        "decision_frame": decision_frame,
        "map_sufficiency_report": sufficiency_report,
        "briefing_plan": briefing_plan,
        "evidence_roles": {key: _dedupe(items)[:8] for key, items in evidence_roles.items()},
        "crux_candidates": _dedupe_dicts(cruxes)[:8],
        "audit_trail": _dedupe(audit_trail)[:10],
        "source_display_names": source_lookup,
        "quality_issues": [
            f"{issue.get('severity')}: {issue.get('issue_type')} - {issue.get('message')}"
            for issue in quality_report.get("issues", [])
            if isinstance(issue, dict)
        ][:8],
    }
    return _expand_payload_reader_references(scaffold, candidate_map)

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
    classification = str(default_answer.get("classification", "mixed_or_context_dependent")).replace("_", " ")
    instruction = str(default_answer.get("plain_language_instruction", "")).strip()
    main_reasons = [row for row in decision_model.get("main_reasons", []) if isinstance(row, dict)]
    counters = [row for row in decision_model.get("strongest_counterarguments", []) if isinstance(row, dict)]
    parts = [instruction or f"The map supports a {classification} answer."]
    if main_reasons:
        parts.append(f"The main support is: {main_reasons[0].get('proposition', '')}")
    if counters:
        parts.append(f"The strongest counterposition is: {counters[0].get('proposition', '')}")
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
    _compressed_claim_text,
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
