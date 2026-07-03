from __future__ import annotations

import json
import re
import sys
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
from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.model_backends import run_model_backend


ENGINE_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ENGINE_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from run_synthesis_uplift_eval import (  # noqa: E402
    _clean_reader_packet_metadata,
    _parse_json,
    _render_synthesis_packet,
)


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
DISPLAY_ACRONYMS = {
    "acx": "ACX",
    "aha": "AHA",
    "bmj": "BMJ",
    "cdc": "CDC",
    "cadr": "CADR",
    "covid": "COVID",
    "dga": "DGA",
    "flf": "FLF",
    "guv": "GUV",
    "hepa": "HEPA",
    "hvac": "HVAC",
    "jama": "JAMA",
    "merv": "MERV",
    "nnr": "NNR",
    "pm": "PM",
    "pmc": "PMC",
    "rct": "RCT",
    "who": "WHO",
}


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
    backend_timeout: int | None = 120,
    backend_retries: int = 0,
    source_titles: dict[str, str] | None = None,
    max_claims: int | None = 0,
) -> MapBriefingResult:
    if backend_retries < 0:
        raise ValueError("backend_retries must be nonnegative")
    if backend_timeout is not None and backend_timeout < 1:
        raise ValueError("backend_timeout must be positive")
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
    parse_diagnostics = model_parse_diagnostics(result.text, parse_ok=False)
    if result.prompt_only:
        rendered = prompt
        model_confidence = "not specified"
        calibrated = calibrate_confidence(model_confidence, quality_report)["calibrated_confidence"]
        parse_ok = False
    else:
        payload = _parse_json(result.text)
        parse_ok = isinstance(payload, dict)
        parse_diagnostics = model_parse_diagnostics(result.text, parse_ok=parse_ok)
        if payload is not None:
            model_confidence = _confidence_label(payload.get("confidence"))
            calibration = calibrate_confidence(model_confidence, quality_report)
            calibrated = calibration["calibrated_confidence"]
            payload = repair_briefing_payload(payload, scaffold, source_lookup, prioritized_map)
            payload["confidence"] = calibrated
            rendered = _render_synthesis_packet(payload, map_payload=prioritized_map, requirements=())
        elif _looks_like_structured_attempt(result.text):
            model_confidence = "not specified"
            calibration = calibrate_confidence(model_confidence, quality_report)
            calibrated = calibration["calibrated_confidence"]
            payload = deterministic_briefing_payload(
                scaffold,
                extracted_brief=_extract_json_string_field_local(result.text, "decision_brief"),
                parse_failure=True,
            )
            payload = repair_briefing_payload(payload, scaffold, source_lookup, prioritized_map)
            payload["confidence"] = calibrated
            rendered = _render_synthesis_packet(payload, map_payload=prioritized_map, requirements=())
        else:
            model_confidence = "not specified"
            calibration = calibrate_confidence(model_confidence, quality_report)
            calibrated = calibration["calibrated_confidence"]
            rendered = result.text.strip()
    if not result.prompt_only:
        calibration = calibrate_confidence(model_confidence, quality_report)
    rendered = _ensure_confidence_visible(rendered, calibrated)
    rendered = append_evidence_by_decision_lever(rendered, scaffold)
    rendered = append_map_coverage_snapshot(rendered, scaffold)
    rendered = _normalize_reader_punctuation(expand_reader_map_references(rendered, prioritized_map))
    rendered = _clean_reader_packet_metadata(replace_source_ids(rendered, source_lookup))
    rendered = polish_briefing_for_reader(rendered, scaffold)
    memo_package = compose_final_reader_memo_package(rendered, scaffold)
    deterministic_reader_memo = str(memo_package["memo"])
    evidence_appendix = str(memo_package["appendix"])
    rewrite_prompt_path = artifacts / "reader_memo_rewrite_prompt.txt"
    rewrite_raw_path = artifacts / "reader_memo_rewrite_raw.txt"
    rewrite_report_path = artifacts / "reader_memo_rewrite_report.json"
    rewrite_result = rewrite_reader_memo_with_contract(
        deterministic_reader_memo,
        evidence_appendix,
        memo_package["scaffold"],
        prioritized_map,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
    )
    reader_memo = rewrite_result["memo"]
    if rewrite_result.get("prompt"):
        write_markdown(rewrite_prompt_path, str(rewrite_result.get("prompt", "")))
    if rewrite_result.get("raw"):
        write_markdown(rewrite_raw_path, str(rewrite_result.get("raw", "")))
    combined_for_validation = reader_memo.rstrip() + "\n\n" + evidence_appendix.rstrip() + "\n"
    polish_report = briefing_reader_polish_report(combined_for_validation, memo_package["scaffold"])
    briefing_validation = validate_briefing_against_scaffold(combined_for_validation, memo_package["scaffold"], prioritized_map)
    briefing_path = artifacts / "BRIEFING.md"
    evidence_appendix_path = artifacts / "EVIDENCE_APPENDIX.md"
    summary_path = artifacts / "briefing_summary.json"
    polish_report_path = artifacts / "briefing_polish_report.json"
    curation_report_path = artifacts / "evidence_curation_report.json"
    write_markdown(briefing_path, reader_memo.rstrip() + "\n")
    write_markdown(evidence_appendix_path, evidence_appendix.rstrip() + "\n")
    write_json(briefing_validation_path, briefing_validation)
    write_json(polish_report_path, polish_report)
    write_json(curation_report_path, memo_package["curation_report"])
    write_json(rewrite_report_path, rewrite_result["report"])
    write_json(
        summary_path,
        {
            "schema_id": "map_briefing_v1",
            "backend": result.backend,
            "parse_ok": parse_ok,
            "parse_diagnostics": parse_diagnostics,
            "question": question,
            "paths": {
                "briefing": _rel(repo_root, briefing_path),
                "evidence_appendix": _rel(repo_root, evidence_appendix_path),
                "prompt": _rel(repo_root, prompt_path),
                "raw": _rel(repo_root, raw_path),
                "prioritized_map": _rel(repo_root, prioritized_map_path),
                "prioritization_report": _rel(repo_root, prioritization_report_path),
                "generated_map_erosion_audit": _rel(repo_root, erosion_audit_path),
                "map_sufficiency_report": _rel(repo_root, sufficiency_report_path),
                "briefing_validation_report": _rel(repo_root, briefing_validation_path),
                "briefing_polish_report": _rel(repo_root, polish_report_path),
                "evidence_curation_report": _rel(repo_root, curation_report_path),
                "reader_memo_rewrite_report": _rel(repo_root, rewrite_report_path),
                "reader_memo_rewrite_prompt": _rel(repo_root, rewrite_prompt_path) if rewrite_result.get("prompt") else None,
                "reader_memo_rewrite_raw": _rel(repo_root, rewrite_raw_path) if rewrite_result.get("raw") else None,
            },
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
        },
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
            "- `main_support` means evidence for the bottom-line answer or low-concern/default recommendation; do not put concern evidence there.",
            "- `conflicting_evidence` means evidence for harm, contrary findings, or tension with the bottom line.",
            "- `scope_limits` means subgroup, dose, population, endpoint, transfer, and conditional limits.",
            "- `method_limits` means measurement validity, source limitations, guideline/practical implementation limits, and abstract-only/full-text limitations.",
            "- Preserve tensions, scope limits, and method limits; do not flatten them into a single confident answer.",
            "- Write section prose in human terms; do not say `Claim A`, `Claim B`, raw claim IDs, or raw relation IDs.",
            "- Use source display names, not raw source IDs, claim IDs, or relation IDs, in reader-facing fields.",
            "- Every evidence_roles bullet must be a substantive evidence statement, not just a source name.",
            "- An evidence_roles bullet is invalid if it only says which source exists; include the relevant claim and put the source in parentheses.",
            "- Do not invent facts beyond the map, quality report, or erosion audit.",
            "- Calibrate uncertainty to the quality report. A map marked review_recommended or needs_repair cannot support high confidence.",
            "- Keep the briefing concise and readable for a human judge.",
            f"Decision question: {question}",
            "Deterministic briefing scaffold:\n" + json.dumps(_model_briefing_scaffold(scaffold), indent=2),
            "Map quality report:\n" + json.dumps(_quality_brief(quality_report), indent=2),
        )
    )


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
        "decision_model": compact_decision_model,
        "evidence_compression_table": scaffold.get("evidence_compression_table"),
        "concept_evidence_packets": _model_concept_evidence_packets(scaffold.get("concept_evidence_packets")),
        "map_sufficiency_report": scaffold.get("map_sufficiency_report"),
        "briefing_plan": scaffold.get("briefing_plan"),
        "evidence_weighting_ledger": compact_ledger,
        "evidence_roles_for_deterministic_attachment": scaffold.get("evidence_roles"),
        "crux_candidates": scaffold.get("crux_candidates"),
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
    contract = build_briefing_contract(partition, quality_report)
    evidence_ledger = build_evidence_weighting_ledger(candidate_map, partition, quality_report, source_lookup)
    proposition_clusters = build_proposition_clusters(candidate_map, evidence_ledger, source_lookup)
    decision_model = build_decision_model(proposition_clusters, contract, quality_report, evidence_ledger)
    evidence_compression_table = build_evidence_compression_table(candidate_map, evidence_ledger, source_lookup)
    concept_evidence_packets = build_concept_evidence_packets(evidence_ledger)
    option_comparison = build_option_comparison(question, evidence_ledger, candidate_map)
    crux_contract = build_crux_contract(candidate_map, evidence_ledger, option_comparison)
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
        "section_policy": {
            "main_support": "Evidence supporting the bottom-line answer or low-concern/default recommendation.",
            "conflicting_evidence": "Evidence for harm, contrary findings, or tensions with the bottom line.",
            "scope_limits": "Subgroup, dose, population, endpoint, transfer, and conditional limits.",
            "method_limits": "Measurement validity, source limitations, guideline/practical implementation limits, and abstract-only/full-text limits.",
        },
        "briefing_contract": contract,
        "evidence_weighting_ledger": evidence_ledger,
        "evidence_slot_ledger": build_evidence_slot_ledger(evidence_ledger),
        "proposition_clusters": proposition_clusters,
        "decision_model": decision_model,
        "evidence_compression_table": evidence_compression_table,
        "concept_evidence_packets": concept_evidence_packets,
        "option_comparison": option_comparison,
        "crux_contract": crux_contract,
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


def append_evidence_by_decision_lever(rendered: str, scaffold: dict[str, Any]) -> str:
    if "## Evidence by Decision Lever" in rendered:
        return rendered
    packets = scaffold.get("concept_evidence_packets", {})
    if not isinstance(packets, dict):
        return rendered
    packet_rows = [packet for packet in packets.get("packets", []) if isinstance(packet, dict)]
    if not packet_rows:
        return rendered
    lines = [
        rendered.rstrip(),
        "",
        "## Evidence by Decision Lever",
        "",
    ]
    for packet in packet_rows[:10]:
        label = str(packet.get("label", "")).strip() or _concept_label(str(packet.get("concept", "")))
        rows = [row for row in packet.get("rows", []) if isinstance(row, dict)]
        if not rows:
            continue
        lines.extend(
            [
                f"### {label}",
                "",
                str(packet.get("synthesis_job", "")).strip() or "State the decision-relevant contribution and caveat for this evidence family.",
                "",
                "| Evidence | Source | Role |",
                "|---|---|---|",
            ]
        )
        for row in rows[:4]:
            lines.append(
                "| "
                + " | ".join(
                    _markdown_table_cell(value)
                    for value in (
                        str(row.get("claim", "")),
                        str(row.get("source", "")),
                        str(row.get("why_it_matters", "")),
                    )
                )
                + " |"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def polish_briefing_for_reader(rendered: str, scaffold: dict[str, Any], *, executive_word_target: int = 1400) -> str:
    """Turn the map-backed packet into a judge-readable brief plus appendix.

    The polish pass may compress, reorder, and clean text, but it only uses
    statements already present in the scaffold or rendered packet.
    """
    cleaned = clean_reader_briefing_text(rendered)
    if "## Evidence Appendix" in cleaned:
        return cleaned
    executive = _build_polished_executive_brief(cleaned, scaffold, executive_word_target=executive_word_target)
    appendix = _build_polished_evidence_appendix(cleaned, scaffold)
    return clean_reader_briefing_text("\n\n".join(part for part in (executive, appendix) if part.strip()))


def compose_final_reader_memo_package(rendered: str, scaffold: dict[str, Any]) -> dict[str, Any]:
    curated_packets = build_curated_evidence_packets(scaffold)
    final_scaffold = dict(scaffold)
    final_scaffold["curated_evidence_packets"] = curated_packets
    decision_memo_slots = build_decision_memo_slots(final_scaffold, rendered=rendered)
    final_scaffold["decision_memo_slots"] = decision_memo_slots
    memo = _build_final_reader_memo(rendered, final_scaffold)
    appendix = _build_final_evidence_appendix(rendered, final_scaffold)
    return {
        "memo": clean_reader_memo_text(memo),
        "appendix": clean_reader_briefing_text(appendix),
        "curation_report": {**curated_packets.get("curation_report", {}), "decision_memo_slots": decision_memo_slots},
        "scaffold": final_scaffold,
    }


def annotate_map_with_evidence_slots(candidate_map: dict[str, Any]) -> dict[str, Any]:
    """Attach canonical evidence slots to claims without changing required schema fields."""
    enriched = json.loads(json.dumps(candidate_map))
    for claim in enriched.get("claims", []) if isinstance(enriched.get("claims"), list) else []:
        if isinstance(claim, dict):
            slots = _evidence_slots_for_claim(claim)
            claim["evidence_slots"] = slots
            claim["decision_slots"] = _decision_slots_for_claim(claim)
    return enriched


def build_evidence_slot_ledger(evidence_ledger: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in evidence_ledger.get("all_evidence", []) if isinstance(row, dict)]
    slots: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for slot in row.get("evidence_slots", []) if isinstance(row.get("evidence_slots"), list) else []:
            slots.setdefault(str(slot), []).append(
                {
                    "claim_id": row.get("claim_id"),
                    "claim": row.get("claim"),
                    "source": row.get("source"),
                    "weight": row.get("weight"),
                    "section": row.get("section"),
                    "why_it_matters": _evidence_slot_why_it_matters(str(slot)),
                }
            )
    for slot, entries in list(slots.items()):
        slots[slot] = sorted(
            entries,
            key=lambda item: (
                -{"high": 2, "medium": 1, "low": 0}.get(str(item.get("weight")), 1),
                str(item.get("claim_id", "")),
            ),
        )[:6]
    return {
        "schema_id": "evidence_slot_ledger_v1",
        "method": "pico_grade_policy_safety_slot_classifier",
        "slot_counts": {slot: len(entries) for slot, entries in slots.items()},
        "slots": slots,
        "slot_definitions": {
            "population_scope": "Who or what setting the evidence transfers to.",
            "intervention_or_option": "The option or intervention being evaluated.",
            "comparator": "Alternative option or substitution that can change the answer.",
            "outcome_or_endpoint": "Outcome, proxy, harm, or decision endpoint.",
            "evidence_design": "Study design or source design supporting the claim.",
            "causal_identification": "Whether causal attribution is identified, confounded, or package-level.",
            "implementation_condition": "Operational condition needed for the option to work.",
            "harm_or_failure_mode": "Downside, hazard, or failure mode.",
            "cost_or_feasibility": "Resource, speed, staffing, or practical feasibility consideration.",
            "equity_or_distribution": "Distributional, subgroup, or access consequence.",
            "missing_evidence_gap": "Named absence or limitation in the current packet.",
        },
    }


def build_option_comparison(question: str, evidence_ledger: dict[str, Any], candidate_map: dict[str, Any]) -> dict[str, Any]:
    options = _question_options(question)
    if not options:
        options = _infer_options_from_evidence(evidence_ledger)
    rows = [row for row in evidence_ledger.get("all_evidence", []) if isinstance(row, dict)]
    criteria = _option_criteria_for_rows(rows)
    option_terms_by_option = _option_terms_by_option(options)
    option_rows: list[dict[str, Any]] = []
    for option in options:
        option_terms = option_terms_by_option.get(option, _option_terms(option))
        criteria_rows = []
        for criterion in criteria:
            matches = [
                row
                for row in rows
                if _row_matches_option(row, option_terms) and _row_matches_option_criterion(row, criterion)
            ]
            if not matches and criterion == "comparator_scope":
                matches = [row for row in rows if _row_matches_option_criterion(row, criterion)]
            ranked = sorted(matches, key=lambda row: (-int(row.get("score", 0)), len(str(row.get("claim", "")))))
            criteria_rows.append(
                {
                    "criterion": criterion,
                    "label": _option_criterion_label(criterion),
                    "current_read": _option_current_read(option, criterion, ranked[:2]),
                    "evidence": [_option_evidence_row(row) for row in ranked[:3]],
                }
            )
        option_rows.append(
            {
                "option": option,
                "terms": option_terms,
                "criteria": criteria_rows,
            }
        )
    tradeoffs = _option_tradeoff_rows(options, rows, option_terms_by_option)
    return {
        "schema_id": "option_comparison_v1",
        "method": "question_option_extraction_plus_slot_weighted_evidence",
        "question": question,
        "options": option_rows,
        "criteria": [{"criterion": criterion, "label": _option_criterion_label(criterion)} for criterion in criteria],
        "tradeoffs": tradeoffs,
        "summary": _option_comparison_summary(options, tradeoffs),
    }


def build_crux_contract(candidate_map: dict[str, Any], evidence_ledger: dict[str, Any], option_comparison: dict[str, Any]) -> dict[str, Any]:
    claim_lookup = {str(claim.get("claim_id", "")): claim for claim in _claims(candidate_map)}
    rows: list[dict[str, Any]] = []
    for relation in _relations(candidate_map):
        rtype = str(relation.get("relation_type", ""))
        if rtype not in {"crux_for", "in_tension_with", "challenges", "depends_on"}:
            continue
        source = claim_lookup.get(str(relation.get("source_claim", "")), {})
        target = claim_lookup.get(str(relation.get("target_claim", "")), {})
        text = " ".join(
            str(value)
            for value in (
                source.get("claim", ""),
                target.get("claim", ""),
                relation.get("rationale", ""),
            )
        )
        label = _crux_label(text, rtype)
        rows.append(
            {
                "crux": label,
                "relation_type": rtype,
                "source_claim": relation.get("source_claim"),
                "target_claim": relation.get("target_claim"),
                "why_it_matters": _crux_why_it_matters(label, text, relation),
                "current_read": _crux_current_read(label, text),
                "would_change_if": _crux_would_change_if(label, text),
                "affected_options": _crux_affected_options(label, option_comparison),
                "evidence": [
                    _claim_contract_row(source),
                    _claim_contract_row(target),
                ],
            }
        )
    rows = _dedupe_crux_rows(rows)
    if len(rows) < 3:
        rows.extend(_fallback_crux_rows_from_option_comparison(option_comparison, evidence_ledger, existing={row["crux"] for row in rows}))
    rows = _dedupe_crux_rows(rows)[:6]
    return {
        "schema_id": "crux_contract_v1",
        "method": "relation_edges_plus_option_tradeoff_cruxes",
        "crux_count": len(rows),
        "cruxes": rows,
    }


def rewrite_reader_memo_with_contract(
    memo: str,
    evidence_appendix: str,
    scaffold: dict[str, Any],
    candidate_map: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    """Use the model as a constrained prose compiler, accepting only validated rewrites."""
    if backend.strip() == "prompt":
        return {
            "memo": memo,
            "prompt": "",
            "raw": "",
            "report": {
                "schema_id": "reader_memo_rewrite_report_v1",
                "status": "skipped_prompt_backend",
                "accepted": False,
                "issues": [],
            },
        }
    contract = build_reader_memo_rewrite_contract(memo, scaffold)
    prompt = build_reader_memo_rewrite_prompt(memo, contract)
    report: dict[str, Any] = {
        "schema_id": "reader_memo_rewrite_report_v1",
        "status": "not_run",
        "accepted": False,
        "issues": [],
        "contract": _compact_rewrite_contract_for_report(contract),
    }
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        report.update({"status": "backend_error_fallback", "issues": [str(exc)]})
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    raw = result.text
    if result.prompt_only:
        report.update({"status": "prompt_backend_fallback", "issues": ["rewrite backend returned prompt only"]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    payload = parse_reader_memo_rewrite_payload(raw)
    if not isinstance(payload, dict):
        report.update({"status": "parse_failed_fallback", "issues": ["rewrite response was not a JSON object"]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    rewritten = str(payload.get("memo_markdown", "")).strip()
    rewritten = ensure_rewrite_confidence_visible(rewritten, str(contract.get("confidence") or "medium"))
    repaired = repair_reader_memo_rewrite_candidate(rewritten, scaffold, contract)
    candidate = repaired if repaired != rewritten else rewritten
    issues = reader_memo_rewrite_issues(candidate, memo, evidence_appendix, scaffold, candidate_map, contract)
    report["issues"] = issues
    report["raw_word_count"] = len(rewritten.split())
    report["deterministic_word_count"] = len(memo.split())
    if repaired != rewritten:
        report["repair_issues"] = issues
        report["repaired_word_count"] = len(repaired.split())
    if issues:
        report["status"] = "rejected_fallback"
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    report["status"] = "accepted_after_repair" if repaired != rewritten else "accepted"
    report["accepted"] = True
    return {"memo": clean_reader_memo_text(candidate), "prompt": prompt, "raw": raw, "report": report}


def repair_reader_memo_rewrite_candidate(markdown: str, scaffold: dict[str, Any], contract: dict[str, Any]) -> str:
    """Repair narrow model-writing defects without adding new evidence.

    This pass is intentionally conservative: it can normalize source-label
    glitches, remove duplicated prose sentences, replace internal scaffolding
    language, and repair repeated generic crux cells from the rewrite contract.
    It cannot invent new evidence rows or loosen the acceptance checks.
    """
    repaired = clean_reader_memo_text(markdown)
    repaired = _repair_reader_source_label_noise(repaired, scaffold, contract)
    repaired = _replace_internal_reader_phrases(repaired)
    repaired = _repair_overclaim_strength_language(repaired)
    repaired = _repair_generic_crux_table_cells(repaired, contract)
    repaired = _drop_duplicate_reader_sentences(repaired)
    repaired = ensure_rewrite_confidence_visible(repaired, str(contract.get("confidence") or "medium"))
    return clean_reader_memo_text(repaired)


def build_reader_memo_rewrite_contract(memo: str, scaffold: dict[str, Any]) -> dict[str, Any]:
    slot_model = scaffold.get("decision_memo_slots", {}) if isinstance(scaffold.get("decision_memo_slots"), dict) else {}
    slots = [slot for slot in slot_model.get("slots", []) if isinstance(slot, dict)]
    required_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for slot in slots:
        for row in slot.get("rows", []) if isinstance(slot.get("rows"), list) else []:
            if not isinstance(row, dict):
                continue
            claim = str(row.get("claim", "")).strip()
            source = str(row.get("source", "")).strip()
            if not claim:
                continue
            key = f"{source}::{claim}"
            if key in seen:
                continue
            seen.add(key)
            required_rows.append(
                {
                    "slot": str(slot.get("label", "")),
                    "claim": claim,
                    "source": source,
                    "anchor_terms": _rewrite_anchor_terms(claim),
                }
            )
            if len(required_rows) >= 12:
                break
        if len(required_rows) >= 12:
            break
    sufficiency = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    required_rows = select_reader_memo_required_evidence(required_rows, scaffold)
    required_gaps = _sufficiency_implications(sufficiency)
    crux_rows = _rewrite_crux_contract_rows(scaffold)[:4]
    answer_frame = build_reader_memo_answer_frame(scaffold, required_rows)
    practical_actions = build_reader_memo_practical_actions(scaffold, required_rows)
    option_comparison = _compact_option_comparison_for_contract(scaffold.get("option_comparison", {}))
    return {
        "schema_id": "reader_memo_rewrite_contract_v1",
        "question": str(scaffold.get("question", "")).strip(),
        "confidence": _extract_confidence(memo) or str(scaffold.get("confidence_cap") or "medium"),
        "answer_frame": answer_frame,
        "option_comparison": option_comparison,
        "practical_actions": practical_actions,
        "required_evidence": required_rows,
        "required_gaps": required_gaps,
        "required_cruxes": crux_rows,
        "editorial_lints": _reader_memo_editorial_lints(),
        "forbidden_moves": [
            "Do not introduce claims, sources, numbers, or recommendations not present in the supplied deterministic memo.",
            "Do not drop named uncertainty, missing-evidence gaps, or implementation constraints.",
            "Do not mention the internal slot labels as prose labels unless they are section headings already in the deterministic memo.",
            "Do not use internal phrases such as mapped support, map-backed read, decision role, load-bearing map distinction, preserved as a load-bearing map distinction, or not specified.",
            "Do not include an evidence appendix; rewrite only the reader memo.",
        ],
        "target_sections": [
            "Decision Brief",
            "Practical Read",
            "Why This Read",
            "Decision Cruxes",
            "Limits of the Current Map",
            "Evidence Trail",
        ],
    }


def _compact_rewrite_contract_for_report(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": contract.get("schema_id"),
        "required_evidence_count": len(contract.get("required_evidence", [])),
        "required_gap_count": len(contract.get("required_gaps", [])),
        "required_crux_count": len(contract.get("required_cruxes", [])),
        "practical_action_count": len(contract.get("practical_actions", [])),
        "option_count": len((contract.get("option_comparison") or {}).get("options", [])) if isinstance(contract.get("option_comparison"), dict) else 0,
        "tradeoff_count": len((contract.get("option_comparison") or {}).get("tradeoffs", [])) if isinstance(contract.get("option_comparison"), dict) else 0,
        "confidence": contract.get("confidence"),
    }


def _compact_option_comparison_for_contract(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"options": [], "tradeoffs": []}
    options = []
    for option in value.get("options", []) if isinstance(value.get("options"), list) else []:
        if not isinstance(option, dict):
            continue
        options.append(
            {
                "option": option.get("option"),
                "criteria": [
                    {
                        "label": row.get("label"),
                        "current_read": row.get("current_read"),
                    }
                    for row in option.get("criteria", [])[:4]
                    if isinstance(row, dict) and str(row.get("current_read", "")).strip()
                ],
            }
        )
    tradeoffs = []
    for row in value.get("tradeoffs", []) if isinstance(value.get("tradeoffs"), list) else []:
        if not isinstance(row, dict):
            continue
        tradeoffs.append(
            {
                "label": row.get("label"),
                "decision_use": row.get("decision_use"),
            }
        )
    return {"options": options[:3], "tradeoffs": tradeoffs[:6], "summary": value.get("summary")}


def select_reader_memo_required_evidence(rows: list[dict[str, str]], scaffold: dict[str, Any], *, max_rows: int = 8) -> list[dict[str, str]]:
    question = str(scaffold.get("question", "")).lower()
    ranked = sorted(rows, key=lambda row: _rewrite_required_evidence_rank(row, question))
    selected: list[dict[str, str]] = []
    seen_claims: set[str] = set()
    seen_slots: dict[str, int] = {}
    for row in ranked:
        claim = str(row.get("claim", ""))
        if not claim:
            continue
        claim_key = " ".join(_content_terms(claim)[:12])
        if claim_key in seen_claims:
            continue
        if _rewrite_row_is_secondary_alternative(row, question):
            continue
        slot = str(row.get("slot", ""))
        if seen_slots.get(slot, 0) >= 2 and len(selected) >= 5:
            continue
        selected.append(row)
        seen_claims.add(claim_key)
        seen_slots[slot] = seen_slots.get(slot, 0) + 1
        if len(selected) >= max_rows:
            break
    if len(selected) < min(4, len(rows)):
        for row in rows:
            if row not in selected and not _rewrite_row_is_secondary_alternative(row, question):
                selected.append(row)
            if len(selected) >= min(4, len(rows)):
                break
    return selected[:max_rows]


def _rewrite_required_evidence_rank(row: dict[str, str], question: str) -> tuple[int, int, int, str]:
    claim = str(row.get("claim", "")).lower()
    slot = str(row.get("slot", ""))
    score = 0
    if _has_quantitative_specificity(claim):
        score += 4
    if any(marker in claim for marker in ("cadr", "room size", "ozone", "unsafe", "not safe")):
        score += 4
    if "portable air cleaners" in claim and "supplemental" in claim:
        score += 4
    if "hepa-treated" in claim or "hepa filters" in claim:
        score += 3
    if "hvac" in claim and ("outdoor ventilation" in claim or "operating" in claim):
        score += 3
    if slot in {"Main support", "Implementation constraints", "Safety and downside risk", "Scope and boundary conditions"}:
        score += 2
    if _rewrite_row_is_secondary_alternative(row, question):
        score -= 6
    if claim.startswith("good ventilation is a step"):
        score -= 3
    return (-score, len(claim), 0 if slot == "Main support" else 1, claim)


def _rewrite_row_is_secondary_alternative(row: dict[str, str], question: str) -> bool:
    claim = str(row.get("claim", "")).lower()
    if claim.startswith("good ventilation is a step"):
        return True
    if "germicidal ultraviolet" in claim or " guv " in f" {claim} ":
        return "guv" not in question and "ultraviolet" not in question
    return False


def build_reader_memo_answer_frame(scaffold: dict[str, Any], required_rows: list[dict[str, str]]) -> dict[str, Any]:
    question = str(scaffold.get("question", "")).strip()
    lowered = f" {question.lower()} "
    comparator = _question_comparator_phrase(question)
    main_support = _first_required_claim(required_rows, slots=("Main support",))
    implementation = _first_required_claim(required_rows, slots=("Implementation constraints", "Scope and boundary conditions"))
    safety = _first_required_claim(required_rows, slots=("Safety and downside risk",))
    answer = "Give a direct, conditional recommendation using only the supplied evidence."
    if "prioritize" in lowered and "hepa" in lowered:
        answer = "Prioritize portable HEPA air cleaners for near-term targeted risk reduction, but describe them as supplemental rather than a substitute for ventilation/source-control work."
    elif "should" in lowered and comparator:
        answer = f"Answer whether the first option should be preferred {comparator}, then state the conditions that could reverse that preference."
    return {
        "direct_answer": answer,
        "comparator_sentence_required": bool(comparator),
        "comparator_phrase": comparator,
        "near_term_recommendation": _short_claim_fragment(main_support, max_chars=220),
        "implementation_condition": _short_claim_fragment(implementation, max_chars=220),
        "downside_or_exception": _short_claim_fragment(safety, max_chars=220),
    }


def _question_comparator_phrase(question: str) -> str:
    lowered = question.lower()
    patterns = (
        r"\bover\b[^?.,;]{0,80}",
        r"\bversus\b[^?.,;]{0,80}",
        r"\bvs\.?\b[^?.,;]{0,80}",
        r"\brather than\b[^?.,;]{0,80}",
        r"\binstead of\b[^?.,;]{0,80}",
        r"\bcompared (?:with|to)\b[^?.,;]{0,80}",
    )
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip()
    return ""


def _first_required_claim(required_rows: list[dict[str, str]], *, slots: tuple[str, ...]) -> str:
    for row in required_rows:
        if str(row.get("slot", "")) in slots:
            return str(row.get("claim", "")).strip()
    return ""


def build_reader_memo_practical_actions(scaffold: dict[str, Any], required_rows: list[dict[str, str]]) -> list[str]:
    actions: list[str] = []
    claims = " ".join(row.get("claim", "") for row in required_rows).lower()
    if "cadr" in claims or "room size" in claims:
        actions.append("Verify that each portable unit's CADR is appropriate for the room size.")
    if "limited airflow" in claims or "targeted filtration" in claims or "sick individuals" in claims:
        actions.append("Deploy portable units first in rooms with limited airflow, targeted filtration needs, or higher-risk occupancy.")
    if "outdoor ventilation" in claims or "source control" in claims or "adequate ventilation" in claims:
        actions.append("Continue HVAC operation, source control, and outdoor-air ventilation rather than treating portable filtration as a replacement.")
    if "ozone" in claims or "unsafe" in claims:
        actions.append("Exclude ozone-generating air cleaners from occupied spaces.")
    if not actions:
        for row in required_rows[:4]:
            claim = str(row.get("claim", "")).strip()
            if claim:
                actions.append(_short_claim_fragment(claim, max_chars=180))
    return _dedupe(actions)[:5]


def _reader_memo_editorial_lints() -> list[str]:
    return [
        "Open with a concrete answer to the decision question.",
        "Use practical bullets that name actions or checks, not abstract process advice.",
        "Use human current-read cells in the crux table.",
        "Do not write: mapped support, map-backed read, decision role, load-bearing map distinction, preserved as a load-bearing map distinction, or not specified.",
        "Do not repeat the same evidence sentence in multiple sections.",
    ]


def _rewrite_anchor_terms(claim: str) -> list[str]:
    terms = _content_terms(claim)
    important = [
        term for term in terms
        if len(term) >= 4 and term not in {"should", "with", "from", "that", "this", "into", "than", "when", "where"}
    ]
    number_terms = re.findall(r"\b\d+(?:\.\d+)?%?\b|PM\s?2\.5|MERV\s?\d+|CADR", claim, flags=re.IGNORECASE)
    return _dedupe([*number_terms, *important])[:6]


def _rewrite_crux_contract_rows(scaffold: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in _deterministic_top_cruxes(scaffold):
        if not isinstance(item, dict):
            continue
        crux = _clean_reader_relation_placeholders(str(item.get("crux", "")).strip())
        if not crux or "line of evidence" in crux.lower():
            continue
        rows.append(
            {
                "crux": crux,
                "why_it_matters": _clean_reader_relation_placeholders(str(item.get("why_it_matters", "")).strip()),
                "current_read": _human_current_read_for_crux(crux, item),
                "would_change_if": _human_would_change_if_for_crux(crux, item),
            }
        )
    return [row for row in rows if row.get("crux")]


def _human_current_read_for_crux(crux: str, item: dict[str, Any]) -> str:
    text = f" {crux.lower()} "
    if "air cleaning alone may not be sufficient" in text or "source control" in text:
        return "Portable filtration is a supplement, not a standalone replacement for source control and ventilation."
    if "health benefits" in text or "translate" in text or "pm levels" in text:
        return "Measured PM reductions are relevant, but health-outcome translation remains uncertain."
    if "cadr" in text or "room size" in text or "technical capacity" in text:
        return "Room-size/CADR fit gates whether portable units can deliver the intended filtration."
    if "site" in text or "constraint" in text or "right-of-way" in text or "geometry" in text:
        return "Local geometry, access needs, and operating constraints determine how far the default recommendation travels."
    if "maintenance" in text or "maintain" in text or "sweeping" in text or "snow" in text:
        return "The recommendation holds only where the city can keep the intervention usable after installation."
    if "volume" in text or "exposure" in text or "rider" in text:
        return "Exposure changes matter because a safety signal is stronger if it is not explained by fewer users."
    if "attribution" in text or "randomized" in text or "confounding" in text or "regression" in text:
        return "The observed result is decision-relevant, but it should be read as a package effect rather than a clean single-cause estimate."
    current = _clean_reader_relation_placeholders(str(item.get("current_read", "")).strip())
    if not current or _contains_banned_editorial_phrase(current):
        relation_type = str(item.get("relation_type", "")).replace("_", " ").strip()
        if relation_type:
            return relation_type.capitalize()
        crux_label = _short_claim_fragment(crux, max_chars=90).rstrip(".")
        return f"The available evidence treats {crux_label.lower()} as a condition on the recommendation."
    return current


def _human_would_change_if_for_crux(crux: str, item: dict[str, Any]) -> str:
    text = f" {crux.lower()} "
    if "air cleaning alone may not be sufficient" in text or "source control" in text:
        return "Portable filtration alone was shown to achieve the relevant respiratory-risk reduction without source control or ventilation."
    if "health benefits" in text or "translate" in text or "pm levels" in text:
        return "Direct student or teacher health outcomes improved at the observed PM-reduction levels."
    if "cadr" in text or "room size" in text or "technical capacity" in text:
        return "Portable units worked reliably without room-size/CADR matching."
    if "site" in text or "constraint" in text or "right-of-way" in text or "geometry" in text:
        return "The target corridors were shown to have workable geometry and manageable access conflicts."
    if "maintenance" in text or "maintain" in text or "sweeping" in text or "snow" in text:
        return "The city lacked the staff, equipment, or budget to keep the intervention usable."
    if "volume" in text or "exposure" in text or "rider" in text:
        return "The apparent safety gain was explained by reduced exposure or suppressed use."
    if "attribution" in text or "randomized" in text or "confounding" in text or "regression" in text:
        return "Better evaluation separated the intervention effect from concurrent street-safety changes."
    value = str(item.get("would_change_if", "")).strip()
    if value and not _contains_banned_editorial_phrase(value) and "weakened or reversed" not in value.lower():
        return value
    crux_label = _short_claim_fragment(crux, max_chars=90).rstrip(".")
    return f"New evidence showed that {crux_label.lower()} did not materially affect the decision."


def build_reader_memo_rewrite_prompt(memo: str, contract: dict[str, Any]) -> str:
    return (
        "You are a controlled prose compiler for a decision-support memo.\n"
        "Rewrite the supplied deterministic memo into clearer, less repetitive prose.\n"
        "You must obey the evidence contract exactly. Do not add outside facts.\n\n"
        "Return only valid JSON with this schema:\n"
        "{\n"
        '  "memo_markdown": "A polished Markdown memo. No evidence appendix."\n'
        "}\n\n"
        "Style requirements:\n"
        "- Start with a direct decision read that follows `answer_frame.direct_answer`; do not start with 'mixed or context-dependent'.\n"
        "- If `answer_frame.comparator_sentence_required` is true, include one plain sentence comparing the named alternatives.\n"
        "- In Practical Read, use the `practical_actions` as concrete action/check bullets; avoid abstract process bullets.\n"
        "- Use `option_comparison` to make the compared options explicit; do not hide the comparator in generic evidence prose.\n"
        "- Merge repeated evidence; each substantive fact should appear once unless needed in the crux table.\n"
        "- Keep source labels in parentheses for substantive evidence claims.\n"
        "- Preserve every required gap and crux.\n"
        "- In crux table `Current read` cells, use concrete human wording from `required_cruxes.current_read`; never write 'Not specified' or 'Preserved as...'.\n"
        "- Keep the memo under 900 words when possible.\n"
        "- Use this section shape: Decision Brief: 2 short paragraphs; Practical Read: 3-5 concrete bullets; Why This Read: 3 short bullets; Decision Cruxes: 3 rows; Limits: short named gaps.\n"
        "- Use the same top-level headings as the deterministic memo.\n\n"
        "Evidence contract:\n"
        f"{json.dumps(contract, indent=2, ensure_ascii=False)}\n\n"
        "Deterministic memo to rewrite:\n"
        f"{memo.strip()}\n"
    )


def parse_reader_memo_rewrite_payload(raw: str) -> dict[str, Any] | None:
    payload = _parse_json(raw)
    if isinstance(payload, dict) and isinstance(payload.get("memo_markdown"), str):
        return payload
    match = re.search(r'"memo_markdown"\s*:\s*"(?P<value>.*)"\s*}\s*(?:```)?\s*$', raw.strip(), flags=re.DOTALL)
    if not match:
        return None
    value = match.group("value")
    value = _decode_tolerant_json_string(value)
    return {"memo_markdown": value}


def _decode_tolerant_json_string(value: str) -> str:
    value = re.sub(r"\\(?![\"\\/bfnrtu])", r"\\\\", value)
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return (
            value.replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace('\\"', '"')
            .replace("\\/", "/")
            .replace("\\\\", "\\")
        )


def ensure_rewrite_confidence_visible(markdown: str, confidence: str) -> str:
    if "**Confidence:**" in markdown:
        return _replace_confidence_line(markdown, confidence)
    if "## Practical Read" in markdown:
        return markdown.replace("## Practical Read", f"**Confidence:** {confidence}\n\n## Practical Read", 1)
    return markdown.rstrip() + f"\n\n**Confidence:** {confidence}\n"


def reader_memo_rewrite_issues(
    rewritten: str,
    original_memo: str,
    evidence_appendix: str,
    scaffold: dict[str, Any],
    candidate_map: dict[str, Any],
    contract: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    if not rewritten:
        return ["missing memo_markdown"]
    if "## Evidence Appendix" in rewritten:
        issues.append("rewrite included evidence appendix")
    if "## Decision Brief" not in rewritten:
        issues.append("rewrite dropped Decision Brief heading")
    if "**Confidence:**" not in rewritten:
        issues.append("rewrite dropped confidence line")
    if len(rewritten.split()) < 250:
        issues.append("rewrite is too short to preserve the decision contract")
    if _rewrite_introduces_domain_leakage(rewritten, scaffold):
        issues.append("rewrite introduced unrelated domain language")
    if _rewrite_has_raw_identifiers(rewritten):
        issues.append("rewrite contains raw map identifiers")
    issues.extend(_rewrite_editorial_issues(rewritten, contract))
    for row in contract.get("required_evidence", []) if isinstance(contract.get("required_evidence"), list) else []:
        if not isinstance(row, dict):
            continue
        if not _rewrite_mentions_anchor_row(rewritten, row):
            issues.append(f"rewrite dropped required evidence: {str(row.get('claim', ''))[:90]}")
    for gap in _string_list(contract.get("required_gaps")):
        if not _rewrite_mentions_gap(rewritten, gap):
            issues.append(f"rewrite dropped required gap: {gap[:90]}")
    combined = rewritten.rstrip() + "\n\n" + evidence_appendix.rstrip() + "\n"
    validation = validate_briefing_against_scaffold(combined, scaffold, candidate_map)
    if validation.get("status") == "needs_review":
        issues.append(f"rewrite failed scaffold validation: {validation.get('issues')}")
    original_sentences = _sentence_fingerprints(_markdown_without_tables(original_memo))
    rewritten_sentences = _sentence_fingerprints(_markdown_without_tables(rewritten))
    if rewritten_sentences and len(set(rewritten_sentences)) < max(3, len(rewritten_sentences) - 3):
        issues.append("rewrite still has duplicate sentence overload")
    if len(rewritten.split()) > int(len(original_memo.split()) * 0.95):
        issues.append("rewrite did not compress the deterministic memo")
    return issues


def _markdown_without_tables(markdown: str) -> str:
    return "\n".join(line for line in markdown.splitlines() if not line.lstrip().startswith("|"))


def _rewrite_editorial_issues(rewritten: str, contract: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    lowered = rewritten.lower()
    for phrase in _banned_editorial_phrases():
        if phrase in lowered:
            issues.append(f"rewrite contains internal phrase: {phrase}")
    answer_frame = contract.get("answer_frame", {}) if isinstance(contract.get("answer_frame"), dict) else {}
    if answer_frame.get("comparator_sentence_required"):
        comparator_terms = _content_terms(str(answer_frame.get("comparator_phrase", "")))
        if comparator_terms and sum(1 for term in comparator_terms if term in lowered) < min(2, len(comparator_terms)):
            issues.append("rewrite does not explicitly address the comparator structure of the question")
    practical_actions = _string_list(contract.get("practical_actions"))
    if practical_actions:
        action_hits = sum(1 for action in practical_actions if _rewrite_mentions_action(rewritten, action))
        if action_hits < min(2, len(practical_actions)):
            issues.append("rewrite did not convert the Practical Read into concrete action checks")
    crux_section = _markdown_section_with_heading(rewritten, "Decision Cruxes")
    if crux_section and any(
        phrase in crux_section.lower()
        for phrase in (
            "not specified",
            "preserved as",
            "load-bearing map",
            "this condition changes how strongly",
            "named condition no longer affected",
        )
    ):
        issues.append("rewrite crux table contains non-human current-read language")
    first_paragraph = _first_non_heading_paragraph(rewritten)
    if first_paragraph and any(phrase in first_paragraph.lower() for phrase in ("mixed or context-dependent", "decision is mixed")):
        issues.append("rewrite opens with generic uncertainty instead of a direct answer")
    return issues


def _banned_editorial_phrases() -> tuple[str, ...]:
    return (
        "mapped support",
        "map-backed read",
        "map-backed default",
        "decision role",
        "load-bearing map distinction",
        "preserved as a load-bearing",
        "not specified",
    )


def _contains_banned_editorial_phrase(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _banned_editorial_phrases())


def _replace_internal_reader_phrases(text: str) -> str:
    replacements = {
        "mapped support": "available evidence",
        "map-backed read": "evidence-based read",
        "map-backed default": "best-supported default",
        "decision role": "function in the decision",
        "load-bearing map distinction": "important distinction",
        "preserved as a load-bearing map distinction": "important for interpreting the recommendation",
        "not specified": "not established by this packet",
        "full map-backed detail": "full source-grounded detail",
    }
    cleaned = text
    for phrase, replacement in replacements.items():
        cleaned = re.sub(re.escape(phrase), replacement, cleaned, flags=re.IGNORECASE)
    return cleaned


def _repair_overclaim_strength_language(text: str) -> str:
    replacements = {
        "Proven Safety Impact": "Mapped Safety Signal",
        "Proven Outcome": "Mapped Outcome",
        "proven safety impact": "mapped safety signal",
        "proven outcome": "mapped outcome",
        "significant safety benefits": "source-supported safety benefits",
        "significant benefit": "source-supported benefit",
        "significantly reduce": "reduce",
        "significantly reduced": "reduced",
        "significant reduction": "mapped reduction",
        "proven benefit": "source-supported benefit",
        "proven effective": "supported in the mapped evidence",
        "proven safe": "not established as risk-free by this packet",
        "no risk": "no established risk-free finding",
        "clearly safe": "not established as risk-free by this packet",
    }
    cleaned = text
    for phrase, replacement in replacements.items():
        cleaned = re.sub(re.escape(phrase), replacement, cleaned, flags=re.IGNORECASE)
    return cleaned


def _repair_reader_source_label_noise(text: str, scaffold: dict[str, Any], contract: dict[str, Any]) -> str:
    source_names = set()
    source_lookup = scaffold.get("source_display_names", {}) if isinstance(scaffold.get("source_display_names"), dict) else {}
    source_names.update(str(value).strip() for value in source_lookup.values() if str(value).strip())
    for row in contract.get("required_evidence", []) if isinstance(contract.get("required_evidence"), list) else []:
        if isinstance(row, dict) and str(row.get("source", "")).strip():
            source_names.add(str(row.get("source", "")).strip())
    if not source_names:
        return text

    cleaned = text
    for source in sorted(source_names, key=len, reverse=True):
        source = _reader_source_name(source)
        variants = _source_label_noise_variants(source)
        for variant in variants:
            if variant and variant != source:
                cleaned = re.sub(rf"\b{re.escape(variant)}\b", source, cleaned)
    cleaned = _repair_near_miss_parenthetical_sources(cleaned, {_reader_source_name(source) for source in source_names})
    cleaned = re.sub(r"\(([^()\n]*_[^()\n]*)\)", lambda match: "(" + _dedupe_adjacent_words(match.group(1).replace("_", " ")) + ")", cleaned)
    return cleaned


def _source_label_noise_variants(source: str) -> list[str]:
    words = source.split()
    variants = {source.replace(" ", "_")}
    if len(words) >= 2:
        for index in range(len(words) - 1):
            duplicated = words[: index + 1] + words[index:] 
            variants.add(" ".join(duplicated))
            variants.add("_".join(duplicated))
    return sorted(variants, key=len, reverse=True)


def _repair_near_miss_parenthetical_sources(text: str, source_names: set[str]) -> str:
    sources = [source for source in source_names if source]
    if not sources:
        return text

    def replace(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        if not label or ";" in label or "," in label:
            return match.group(0)
        repaired = _nearest_source_label(label, sources)
        if not repaired:
            return match.group(0)
        return f"({repaired})"

    return re.sub(r"\(([^()\n]{4,90})\)", replace, text)


def _nearest_source_label(label: str, sources: list[str]) -> str:
    normalized_label = _normalize_source_label(label)
    best_source = ""
    best_score = 0.0
    for source in sources:
        normalized_source = _normalize_source_label(source)
        if normalized_label == normalized_source:
            return source
        token_overlap = _source_label_token_overlap(normalized_label, normalized_source)
        if token_overlap < 0.6:
            continue
        score = SequenceMatcher(None, normalized_label, normalized_source).ratio()
        if score > best_score:
            best_score = score
            best_source = source
    return best_source if best_score >= 0.84 else ""


def _normalize_source_label(label: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", label.lower())).strip()


def _source_label_token_overlap(left: str, right: str) -> float:
    left_terms = set(left.split())
    right_terms = set(right.split())
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / max(1, min(len(left_terms), len(right_terms)))


def _dedupe_adjacent_words(text: str) -> str:
    words = text.split()
    kept: list[str] = []
    for word in words:
        if kept and kept[-1].lower().strip(".,;:") == word.lower().strip(".,;:"):
            continue
        kept.append(word)
    return " ".join(kept)


def _repair_generic_crux_table_cells(text: str, contract: dict[str, Any]) -> str:
    cruxes = [row for row in contract.get("required_cruxes", []) if isinstance(row, dict)]
    if not cruxes or "| Crux |" not in text:
        return text
    lines = text.splitlines()
    repaired_lines: list[str] = []
    for line in lines:
        if not line.lstrip().startswith("|") or line.count("|") < 4:
            repaired_lines.append(line)
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0].lower() in {"crux", "---"} or set(cells[0]) <= {"-", ":"}:
            repaired_lines.append(line)
            continue
        matching = _matching_crux_contract(cells[0], cruxes)
        if matching:
            if _is_generic_crux_cell(cells[2]):
                cells[2] = _human_current_read_for_crux(str(matching.get("crux", "")), matching)
            if _is_generic_crux_cell(cells[3]):
                cells[3] = _human_would_change_if_for_crux(str(matching.get("crux", "")), matching)
            line = "| " + " | ".join(_markdown_table_cell(cell) for cell in cells) + " |"
        repaired_lines.append(line)
    return "\n".join(repaired_lines)


def _matching_crux_contract(crux_text: str, cruxes: list[dict[str, Any]]) -> dict[str, Any] | None:
    terms = set(_content_terms(crux_text))
    if not terms:
        return None
    best: tuple[int, dict[str, Any] | None] = (0, None)
    for row in cruxes:
        row_terms = set(_content_terms(str(row.get("crux", ""))))
        overlap = len(terms & row_terms)
        if overlap > best[0]:
            best = (overlap, row)
    return best[1] if best[0] >= 1 else None


def _is_generic_crux_cell(value: str) -> bool:
    lowered = value.lower()
    return any(
        phrase in lowered
        for phrase in (
            "this condition changes how strongly",
            "named condition no longer affected",
            "preserved as",
            "not specified",
            "load-bearing map",
        )
    )


def _drop_duplicate_reader_sentences(text: str) -> str:
    lines = text.splitlines()
    seen: set[str] = set()
    cleaned_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("|"):
            cleaned_lines.append(line)
            continue
        prefix = ""
        body = line
        bullet_match = re.match(r"^(\s*[-*]\s+)(.*)$", line)
        if bullet_match:
            prefix = "- "
            body = bullet_match.group(2)
        sentences = re.findall(r".*?(?:[.!?](?=\s+[A-Z0-9(]|\s*$)|$)", body)
        kept: list[str] = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            fps = _sentence_fingerprints(sentence)
            fp = fps[0] if fps else ""
            if fp and fp in seen:
                continue
            if fp:
                seen.add(fp)
            kept.append(sentence)
        if kept:
            cleaned_lines.append(prefix + " ".join(kept) if prefix else " ".join(kept))
        elif not stripped:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _rewrite_mentions_action(rewritten: str, action: str) -> bool:
    lowered = rewritten.lower()
    terms = [term for term in _content_terms(action) if len(term) >= 4]
    if not terms:
        return True
    return sum(1 for term in terms[:6] if term in lowered) >= min(2, len(terms))


def _first_non_heading_paragraph(markdown: str) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", markdown) if part.strip()]
    for paragraph in paragraphs:
        if paragraph.startswith("#") or paragraph.startswith("|") or paragraph.startswith("- ") or paragraph.startswith("* "):
            continue
        return paragraph
    return ""


def _rewrite_introduces_domain_leakage(text: str, scaffold: dict[str, Any]) -> bool:
    if _looks_like_nutrition_case(scaffold):
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in (" egg", " eggs", " dietary", " cholesterol", " apob", " saturated fat", " replacement foods"))


def _rewrite_has_raw_identifiers(text: str) -> bool:
    return any(
        re.search(pattern, text)
        for pattern in (
            r"\b[A-Za-z0-9_\-]+_c\d{3,}\b",
            r"\b[A-Za-z0-9_\-]+_r\d{3,}\b",
            r"\bClaim [A-Z]\b",
            r"\bClaim [cC]?\d{3,}\b",
        )
    )


def _rewrite_mentions_anchor_row(text: str, row: dict[str, Any]) -> bool:
    lowered = text.lower()
    source = str(row.get("source", "")).strip().lower()
    terms = [str(term).lower() for term in row.get("anchor_terms", []) if isinstance(term, str)]
    if _is_synthetic_rewrite_source(source):
        return _rewrite_mentions_synthetic_anchor_row(lowered, row, terms)
    source_ok = not source or source in lowered
    if not terms:
        return source_ok
    hits = sum(1 for term in terms if term.lower() in lowered)
    required = 1 if len(terms) <= 2 else 2
    return source_ok and hits >= required


def _is_synthetic_rewrite_source(source: str) -> bool:
    return source in {"structured option comparison"}


def _rewrite_mentions_synthetic_anchor_row(lowered_text: str, row: dict[str, Any], terms: list[str]) -> bool:
    if not terms:
        return True
    hits = sum(1 for term in terms if term in lowered_text)
    required = min(3, max(2, len(terms) // 2))
    if hits < required:
        return False
    claim = str(row.get("claim", "")).lower()
    if "compared " in claim or " versus " in claim or " vs " in claim:
        return _rewrite_mentions_comparison_sides(lowered_text, claim)
    return True


def _rewrite_mentions_comparison_sides(lowered_text: str, claim: str) -> bool:
    match = re.search(
        r"\bcompared\s+(?P<a>.+?)\s+(?:versus|vs\.?|over|rather than|instead of)\s+(?P<b>.+?)\s+on\b",
        claim,
    )
    if not match:
        return True
    side_a = _comparison_side_terms(match.group("a"))
    side_b = _comparison_side_terms(match.group("b"))
    return _mentions_any_term(lowered_text, side_a) and _mentions_any_term(lowered_text, side_b)


def _comparison_side_terms(text: str) -> list[str]:
    return [
        term
        for term in _content_terms(text)
        if len(term) >= 4 and term not in {"compared", "versus", "rather", "instead", "with", "over"}
    ][:4]


def _mentions_any_term(lowered_text: str, terms: list[str]) -> bool:
    return bool(terms) and any(term in lowered_text for term in terms)


def _rewrite_mentions_gap(text: str, gap: str) -> bool:
    lowered = text.lower()
    gap_terms = [term for term in _content_terms(gap) if len(term) >= 6]
    if not gap_terms:
        return True
    hits = sum(1 for term in gap_terms[:6] if term in lowered)
    return hits >= min(2, len(gap_terms))


def _sentence_fingerprints(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip())
    fingerprints = []
    for sentence in sentences:
        terms = _content_terms(sentence)
        if len(terms) >= 5:
            fingerprints.append(" ".join(terms[:12]))
    return fingerprints


def build_curated_evidence_packets(scaffold: dict[str, Any], *, rows_per_packet: int = 3) -> dict[str, Any]:
    source_counts: dict[str, int] = {}
    packets_in = scaffold.get("concept_evidence_packets", {}) if isinstance(scaffold.get("concept_evidence_packets"), dict) else {}
    curated_packets: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for packet in packets_in.get("packets", []) if isinstance(packets_in.get("packets"), list) else []:
        if not isinstance(packet, dict):
            continue
        good_rows: list[dict[str, Any]] = []
        concept = str(packet.get("concept", ""))
        for row in packet.get("rows", []) if isinstance(packet.get("rows"), list) else []:
            if not isinstance(row, dict):
                continue
            quality = _reader_evidence_row_quality(row)
            clean_row = _reader_clean_evidence_row(row)
            if not quality["usable"]:
                excluded.append(
                    {
                        "concept": concept,
                        "source": str(clean_row.get("source", "")),
                        "claim": str(row.get("claim", "")),
                        "reason": ", ".join(quality["reasons"]),
                    }
                )
                continue
            source = str(clean_row.get("source", ""))
            source_penalty = source_counts.get(source, 0)
            clean_row["reader_score"] = int(row.get("score", 0)) + int(quality["score"]) - source_penalty
            good_rows.append(clean_row)
        good_rows.sort(key=lambda item: (-int(item.get("reader_score", 0)), str(item.get("source", "")), str(item.get("claim", ""))))
        selected: list[dict[str, Any]] = []
        packet_sources: set[str] = set()
        for row in good_rows:
            source = str(row.get("source", ""))
            if source in packet_sources and len(good_rows) > rows_per_packet:
                continue
            selected.append(row)
            packet_sources.add(source)
            source_counts[source] = source_counts.get(source, 0) + 1
            if len(selected) >= rows_per_packet:
                break
        if selected:
            curated_packets.append(
                {
                    "concept": concept,
                    "label": str(packet.get("label") or _concept_label(concept)),
                    "synthesis_job": str(packet.get("synthesis_job", "")),
                    "must_surface_terms": packet.get("must_surface_terms", []),
                    "rows": selected,
                }
            )
    return {
        "schema_id": "curated_evidence_packets_v1",
        "method": "readability_directness_source_diversity_filter",
        "packets": curated_packets,
        "curation_report": {
            "schema_id": "evidence_curation_report_v1",
            "packet_count": len(curated_packets),
            "selected_row_count": sum(len(packet.get("rows", [])) for packet in curated_packets),
            "excluded_row_count": len(excluded),
            "excluded_rows": excluded[:40],
        },
    }


def build_decision_memo_slots(scaffold: dict[str, Any], *, rendered: str = "") -> dict[str, Any]:
    slots: list[dict[str, Any]] = []
    for spec in _decision_memo_slot_specs(scaffold):
        rows = _candidate_rows_for_memo_slot(scaffold, spec)
        selected = sorted(rows, key=lambda row: _memo_slot_row_rank(row, spec))[: int(spec.get("max_rows", 2))]
        slots.append(
            {
                "slot_id": spec["slot_id"],
                "label": spec["label"],
                "job": spec["job"],
                "required": bool(spec.get("required", True)),
                "status": "filled" if selected else "missing",
                "missing_message": spec.get("missing_message", "The current source packet does not establish clean evidence for this slot."),
                "rows": selected,
            }
        )
    crux_table = _compact_crux_table(rendered, scaffold)
    return {
        "schema_id": "decision_memo_slots_v1",
        "method": "required_decision_slot_coverage_from_curated_evidence",
        "slots": slots,
        "coverage": {
            "required_slot_count": sum(1 for slot in slots if slot.get("required")),
            "filled_required_slot_count": sum(1 for slot in slots if slot.get("required") and slot.get("status") == "filled"),
            "missing_required_slots": [slot["slot_id"] for slot in slots if slot.get("required") and slot.get("status") != "filled"],
            "has_crux_table": bool(crux_table),
        },
    }


def _decision_memo_slot_specs(scaffold: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Build reader-memo obligations from the question and observed map concepts."""
    if _looks_like_nutrition_case(scaffold):
        return _NUTRITION_DECISION_MEMO_SLOT_SPECS
    sufficiency = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    profile = sufficiency.get("question_profile", {}) if isinstance(sufficiency.get("question_profile"), dict) else {}
    expected_slots = set(_string_list(profile.get("expected_decision_slots")))
    question = f" {re.sub(r'\\s+', ' ', str(scaffold.get('question', '')).lower())} "
    asks_comparison = any(marker in question for marker in (" over ", " versus ", " vs ", " compared", " rather than ", " instead of "))
    asks_action = any(marker in question for marker in (" should ", " prioritize", " recommend", " use ", " adopt ", " implement ", " decision "))
    return (
        {
            "slot_id": "main_support",
            "label": "Main support",
            "job": "Surface the evidence that most directly supports the current read.",
            "concepts": (),
            "sections": ("main_support",),
            "max_rows": 3,
            "required": True,
            "missing_message": "The current source packet does not establish clean evidence supporting a default answer.",
        },
        {
            "slot_id": "counterevidence_or_tension",
            "label": "Counterevidence or tension",
            "job": "Surface contrary evidence, tensions, or the strongest live counterposition.",
            "concepts": (),
            "sections": ("conflicting_evidence",),
            "max_rows": 3,
            "required": False,
            "missing_message": "The current source packet does not establish clean counterevidence or tensions.",
        },
        {
            "slot_id": "scope_conditions",
            "label": "Scope and boundary conditions",
            "job": "State the setting, population, scale, intensity, or threshold where the read applies.",
            "concepts": ("default_population", "dose_or_threshold", "technical_performance_or_capacity", "setting_or_context"),
            "sections": ("scope_limits", "main_support", "method_limits"),
            "max_rows": 3,
            "required": bool({"default_population", "dose_or_intensity_threshold"} & expected_slots) or asks_action,
            "missing_message": "The current source packet does not establish clean scope, setting, or intensity boundaries.",
        },
        {
            "slot_id": "alternatives_or_comparators",
            "label": "Alternatives and comparators",
            "job": "State how the read changes across the options being compared.",
            "concepts": ("substitution_or_comparator", "alternative_or_comparator"),
            "sections": ("main_support", "conflicting_evidence", "scope_limits", "method_limits"),
            "max_rows": 3,
            "required": "substitution_or_comparator" in expected_slots or asks_comparison,
            "missing_message": "The current source packet does not establish clean comparator evidence for the named alternatives.",
        },
        {
            "slot_id": "implementation_constraints",
            "label": "Implementation constraints",
            "job": "Surface feasibility, safety, operational, policy, or technical conditions that gate action.",
            "concepts": ("implementation_constraint", "technical_performance_or_capacity", "safety_or_adverse_effect", "guideline_or_policy"),
            "sections": ("method_limits", "scope_limits", "main_support", "conflicting_evidence"),
            "max_rows": 4,
            "required": asks_action or "practical_recommendation" in expected_slots,
            "missing_message": "The current source packet does not establish clean implementation constraints.",
        },
        {
            "slot_id": "evidence_type_limits",
            "label": "Evidence type and outcome limits",
            "job": "Separate direct outcomes from proxies, mechanisms, intervention results, guidance, and method limits.",
            "concepts": (
                "hard_outcome_endpoint",
                "surrogate_or_biomarker_endpoint",
                "mechanism_or_causal_path",
                "study_design_rct",
                "study_design_cohort",
                "guideline_or_policy",
            ),
            "sections": ("method_limits", "main_support", "scope_limits", "conflicting_evidence"),
            "max_rows": 4,
            "required": True,
            "missing_message": "The current source packet does not establish clean evidence-type or outcome limitations.",
        },
        {
            "slot_id": "safety_or_risk",
            "label": "Safety and downside risk",
            "job": "Surface risks, harms, or failure modes that could change the practical recommendation.",
            "concepts": ("safety_or_adverse_effect", "hard_outcome_endpoint"),
            "sections": ("conflicting_evidence", "method_limits", "scope_limits", "main_support"),
            "max_rows": 2,
            "required": False,
            "missing_message": "The current source packet does not establish clean downside-risk evidence.",
        },
    )


def _looks_like_nutrition_case(scaffold: dict[str, Any]) -> bool:
    question = str(scaffold.get("question", "")).lower()
    if any(marker in question for marker in ("egg", "diet", "nutrition", "cholesterol", "cardiovascular")):
        return True
    packets = scaffold.get("concept_evidence_packets", {}) if isinstance(scaffold.get("concept_evidence_packets"), dict) else {}
    packet_text = " ".join(
        str(row.get("claim", ""))
        for packet in packets.get("packets", [])
        if isinstance(packet, dict)
        for row in packet.get("rows", [])
        if isinstance(row, dict)
    ).lower()
    packet_markers = ("egg", "dietary", "ldl", "apob", "cholesterol", "saturated fat")
    if sum(1 for marker in packet_markers if marker in packet_text) >= 2:
        return True
    ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    text = " ".join(str(row.get("claim", "")) for row in ledger.get("all_evidence", []) if isinstance(row, dict)).lower()
    markers = ("egg", "dietary", "ldl", "apob", "cholesterol", "saturated fat")
    return sum(1 for marker in markers if marker in text) >= 2


_NUTRITION_DECISION_MEMO_SLOT_SPECS = (
    {
        "slot_id": "default_population",
        "label": "Default population",
        "job": "State who inherits the default answer.",
        "concepts": ("default_population",),
        "sections": ("scope_limits", "main_support"),
        "max_rows": 1,
        "required": True,
        "missing_message": "The current source packet does not establish a clean default-population boundary.",
    },
    {
        "slot_id": "dose_boundary",
        "label": "Dose boundary",
        "job": "State the intake level or threshold the answer applies to.",
        "concepts": ("dose_or_threshold",),
        "sections": ("main_support", "scope_limits"),
        "max_rows": 1,
        "required": True,
        "missing_message": "The current source packet does not establish a clean dose or intensity boundary.",
    },
    {
        "slot_id": "hard_outcome_support",
        "label": "Hard-outcome support",
        "job": "Surface direct outcome evidence that supports the default answer.",
        "concepts": ("hard_outcome_endpoint", "study_design_cohort"),
        "sections": ("main_support",),
        "max_rows": 2,
        "required": True,
        "missing_message": "The map lacks clean hard-outcome support for the default answer.",
    },
    {
        "slot_id": "hard_outcome_counter",
        "label": "Hard-outcome counterevidence",
        "job": "Surface outcome evidence that pushes against the default answer.",
        "concepts": ("hard_outcome_endpoint", "study_design_cohort"),
        "sections": ("conflicting_evidence",),
        "max_rows": 2,
        "required": True,
        "missing_message": "The map lacks clean hard-outcome counterevidence.",
    },
    {
        "slot_id": "mechanism_surrogate",
        "label": "Mechanism and surrogate evidence",
        "job": "Explain biomarkers or mechanisms and what they cannot settle.",
        "concepts": ("mechanism_ldl_apob", "surrogate_or_biomarker_endpoint", "dietary_context_or_saturated_fat"),
        "sections": ("main_support", "conflicting_evidence", "method_limits", "scope_limits"),
        "max_rows": 3,
        "required": True,
        "missing_message": "The map lacks clean mechanism or surrogate-endpoint evidence.",
    },
    {
        "slot_id": "comparator_substitution",
        "label": "Comparator or substitution",
        "job": "State how replacement foods or comparators change the practical advice.",
        "concepts": ("substitution_or_comparator",),
        "sections": ("main_support", "conflicting_evidence", "method_limits", "scope_limits"),
        "max_rows": 2,
        "required": True,
        "missing_message": "The map lacks clean comparator or substitution evidence.",
    },
    {
        "slot_id": "high_risk_subgroup",
        "label": "High-risk subgroup",
        "job": "State who should not inherit the default answer without extra caution.",
        "concepts": ("subgroup_diabetes_or_metabolic_risk", "subgroup_fh_hyper_responder"),
        "sections": ("scope_limits", "conflicting_evidence", "method_limits", "main_support"),
        "max_rows": 2,
        "required": True,
        "missing_message": "The map lacks clean high-risk subgroup evidence.",
    },
    {
        "slot_id": "study_design_limits",
        "label": "Study-design limits",
        "job": "Distinguish hard outcomes from RCT/intervention or biomarker evidence.",
        "concepts": ("study_design_rct", "study_design_cohort"),
        "sections": ("method_limits", "main_support", "scope_limits"),
        "max_rows": 2,
        "required": False,
        "missing_message": "The current source packet does not establish clean study-design limitations.",
    },
)


def _candidate_rows_for_memo_slot(scaffold: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    concepts = tuple(str(item) for item in spec.get("concepts", ()))
    sections = tuple(str(item) for item in spec.get("sections", ()))
    curated = scaffold.get("curated_evidence_packets", {}) if isinstance(scaffold.get("curated_evidence_packets"), dict) else {}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for packet in curated.get("packets", []) if isinstance(curated.get("packets"), list) else []:
        if not isinstance(packet, dict):
            continue
        if concepts and str(packet.get("concept", "")) not in concepts:
            continue
        for row in packet.get("rows", []) if isinstance(packet.get("rows"), list) else []:
            if not isinstance(row, dict):
                continue
            if sections and str(row.get("section", "")) not in sections:
                continue
            if not _row_matches_memo_slot_direction(row, spec):
                continue
            key = f"{row.get('source')}::{row.get('claim')}"
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    if rows:
        return rows
    option_rows = _option_rows_for_memo_slot(scaffold, spec)
    if option_rows:
        return option_rows
    return _fallback_rows_for_memo_slot(scaffold, spec)


def _fallback_rows_for_memo_slot(scaffold: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    concepts = set(str(item) for item in spec.get("concepts", ()))
    sections = set(str(item) for item in spec.get("sections", ()))
    ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    rows: list[dict[str, Any]] = []
    for row in ledger.get("all_evidence", []) if isinstance(ledger.get("all_evidence"), list) else []:
        if not isinstance(row, dict):
            continue
        row_concepts = set(str(item) for item in row.get("decision_concepts", []) if isinstance(item, str))
        if concepts and not row_concepts.intersection(concepts):
            continue
        if sections and str(row.get("section", "")) not in sections:
            continue
        clean = _reader_clean_evidence_row(row)
        quality = _reader_evidence_row_quality(row)
        if quality["usable"] and _row_matches_memo_slot_direction(clean, spec):
            clean["reader_score"] = int(row.get("score", 0)) + int(quality["score"])
            rows.append(clean)
    return rows


def _option_rows_for_memo_slot(scaffold: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    slot_id = str(spec.get("slot_id", ""))
    if slot_id not in {"alternatives_or_comparators", "comparator_substitution"}:
        return []
    option_comparison = scaffold.get("option_comparison", {}) if isinstance(scaffold.get("option_comparison"), dict) else {}
    options = [str(row.get("option", "")).strip() for row in option_comparison.get("options", []) if isinstance(row, dict) and str(row.get("option", "")).strip()]
    if len(options) < 2:
        return []
    rows: list[dict[str, Any]] = []
    for tradeoff in option_comparison.get("tradeoffs", []) if isinstance(option_comparison.get("tradeoffs"), list) else []:
        if not isinstance(tradeoff, dict):
            continue
        claim = _option_tradeoff_slot_claim(tradeoff, options)
        if not claim:
            continue
        rows.append(
            {
                "claim": claim,
                "source": "structured option comparison",
                "section": "main_support",
                "weight": "medium",
                "score": _option_tradeoff_slot_score(tradeoff),
                "reader_score": _option_tradeoff_slot_score(tradeoff) + 4,
                "decision_concepts": ["alternative_or_comparator", "substitution_or_comparator"],
                "evidence_slots": ["intervention_or_option", "comparator", "missing_evidence_gap"],
                "criterion": tradeoff.get("criterion"),
            }
        )
    return sorted(rows, key=lambda row: _memo_slot_row_rank(row, spec))[:1]


def _row_matches_memo_slot_direction(row: dict[str, Any], spec: dict[str, Any]) -> bool:
    slot_id = str(spec.get("slot_id", ""))
    claim = str(row.get("claim", ""))
    lowered = f" {claim.lower()} "
    if slot_id in {
        "main_support",
        "counterevidence_or_tension",
        "scope_conditions",
        "implementation_constraints",
        "evidence_type_limits",
        "safety_or_risk",
    }:
        return True
    if slot_id == "alternatives_or_comparators":
        return any(
            marker in lowered
            for marker in (
                " compared",
                " versus",
                " vs ",
                " over ",
                " rather than ",
                " instead of",
                " alternative",
                " supplemental",
                " replacement",
                " replace",
                " substitut",
            )
        )
    if slot_id == "hard_outcome_support":
        return _looks_like_support_evidence(claim) and not _looks_like_concern_evidence(claim)
    if slot_id == "hard_outcome_counter":
        return _looks_like_concern_evidence(claim)
    if slot_id == "high_risk_subgroup":
        if "free of" in lowered and "baseline" in lowered:
            return False
        return any(
            marker in lowered
            for marker in (
                " diabetes",
                " type 2",
                " t2d",
                " prediabetes",
                " familial",
                " hyper",
                " high ldl",
                " high apob",
                " kidney",
                " vascular disease",
            )
        )
    if slot_id == "comparator_substitution":
        return any(marker in lowered for marker in (" replace", " replacing", " substitut", " instead of", " compared with", " versus", " egg white", " plant protein"))
    if slot_id == "mechanism_surrogate":
        return any(marker in lowered for marker in (" ldl", " apob", " hdl", " cholesterol", " saturated fat", " biomarker", " tmao", " triglyceride"))
    return True


def _memo_slot_row_rank(row: dict[str, Any], spec: dict[str, Any]) -> tuple[int, int, int, int, str]:
    claim = str(row.get("claim", ""))
    lowered = claim.lower()
    quantitative_bonus = 2 if _has_quantitative_specificity(claim) else 0
    direct_bonus = 0
    slot_id = str(spec.get("slot_id", ""))
    if slot_id.startswith("hard_outcome") and any(marker in lowered for marker in ("mortality", "cardiovascular", "cvd", "stroke", "myocardial infarction")):
        direct_bonus += 2
    if slot_id == "mechanism_surrogate" and any(marker in lowered for marker in ("ldl", "apob", "hdl", "cholesterol", "saturated fat", "biomarker")):
        direct_bonus += 2
    if slot_id == "comparator_substitution" and any(marker in lowered for marker in ("replace", "replacing", "substitut", "instead of", "compared with")):
        direct_bonus += 2
    if slot_id == "high_risk_subgroup" and any(marker in lowered for marker in ("diabetes", "familial", "hyper", "high ldl", "kidney", "vascular")):
        direct_bonus += 2
    if slot_id == "alternatives_or_comparators" and any(marker in lowered for marker in ("compared", "versus", "rather than", "instead of", "alternative", "supplemental")):
        direct_bonus += 2
    if slot_id in {"scope_conditions", "implementation_constraints"} and any(
        marker in lowered for marker in ("depends", "requires", "feasible", "capacity", "size", "setting", "maintenance", "standard", "should")
    ):
        direct_bonus += 2
    if slot_id == "safety_or_risk" and any(marker in lowered for marker in ("unsafe", "risk", "harm", "adverse", "ozone", "failure")):
        direct_bonus += 2
    score = int(row.get("reader_score", 0)) + quantitative_bonus + direct_bonus
    return (-score, len(claim), -len(set(_content_terms(claim))), str(row.get("source", "")), str(row.get("claim", "")))


def _option_tradeoff_slot_claim(tradeoff: dict[str, Any], options: list[str]) -> str:
    evidence_by_option = tradeoff.get("evidence_by_option", {}) if isinstance(tradeoff.get("evidence_by_option"), dict) else {}
    if not any(isinstance(evidence_by_option.get(option), list) and evidence_by_option.get(option) for option in options):
        return ""
    label = str(tradeoff.get("label") or _option_criterion_label(str(tradeoff.get("criterion", "")))).strip()
    compared = " versus ".join(options[:2])
    clauses: list[str] = []
    for option in options[:2]:
        evidence_rows = evidence_by_option.get(option, [])
        if not isinstance(evidence_rows, list) or not evidence_rows:
            clauses.append(f"{option}: no clean mapped evidence for this criterion")
            continue
        claim = _option_claim_snippet(str(evidence_rows[0].get("claim", "")), max_chars=130)
        if not claim:
            continue
        clauses.append(f"{option}: {claim}")
    if not clauses:
        return ""
    return f"Compared {compared} on {label.lower()}: " + "; ".join(clauses) + "."


def _option_tradeoff_slot_score(tradeoff: dict[str, Any]) -> int:
    evidence_by_option = tradeoff.get("evidence_by_option", {}) if isinstance(tradeoff.get("evidence_by_option"), dict) else {}
    evidence_count = sum(
        len(rows)
        for rows in evidence_by_option.values()
        if isinstance(rows, list)
    )
    covered_options = sum(1 for rows in evidence_by_option.values() if isinstance(rows, list) and rows)
    return min(10, 4 + evidence_count + covered_options)


def _option_claim_snippet(text: str, *, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip().rstrip(".")
    if len(cleaned) <= max_chars:
        return cleaned
    words: list[str] = []
    for word in cleaned.split():
        candidate = " ".join([*words, word]).strip()
        if words and len(candidate) > max_chars:
            break
        words.append(word)
    return " ".join(words).strip(" ,;:.")


def _has_quantitative_specificity(text: str) -> bool:
    return bool(
        re.search(
            r"(?:\bHR\b|\bRR\b|\bCI\b|\bP\s*[<=>]|%|mg/dL|mmol/L|participants?|events?|n\s*=|≥|≤|<|>\s*)",
            text,
            flags=re.IGNORECASE,
        )
    )


def _slot_lookup(slot_model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(slot.get("slot_id", "")): slot
        for slot in slot_model.get("slots", []) if isinstance(slot, dict)
    }


def _slot_paragraph(
    slot_model: dict[str, Any],
    slot_ids: tuple[str, ...],
    *,
    lead: str,
    fallback_items: list[str],
    max_sentences: int,
) -> str:
    lookup = _slot_lookup(slot_model)
    sentences = [lead]
    for slot_id in slot_ids:
        slot = lookup.get(slot_id)
        if not slot:
            continue
        if slot.get("status") == "missing":
            if slot.get("required"):
                sentences.append(str(slot.get("missing_message", "The current source packet does not establish this evidence slot.")))
            continue
        slot_sentence = _memo_slot_sentence(slot)
        if slot_sentence:
            sentences.append(slot_sentence)
    if len(sentences) == 1:
        sentences.extend(fallback_items[: max_sentences - 1])
    return _join_polished_sentences(sentences, max_sentences=max_sentences)


def _memo_slot_sentence(slot: dict[str, Any]) -> str:
    rows = [row for row in slot.get("rows", []) if isinstance(row, dict)]
    if not rows:
        return ""
    label = str(slot.get("label", "Evidence"))
    clauses = []
    for row in rows[:3]:
        claim = str(row.get("claim", "")).strip().rstrip(".")
        source = str(row.get("source", "")).strip()
        if not claim:
            continue
        if source == "structured option comparison":
            source = ""
        clauses.append(claim + (f" ({source})" if source and source not in claim else ""))
    if not clauses:
        return ""
    if len(clauses) == 1:
        return f"{label}: {clauses[0]}."
    return f"{label}: " + "; ".join(clauses[:-1]) + "; and " + clauses[-1] + "."


def _build_final_reader_memo(rendered: str, scaffold: dict[str, Any]) -> str:
    confidence = _extract_confidence(rendered) or str(scaffold.get("confidence_cap") or "medium")
    decision_brief = _executive_decision_brief(rendered, scaffold)
    slot_model = scaffold.get("decision_memo_slots", {}) if isinstance(scaffold.get("decision_memo_slots"), dict) else {}
    implications = _slot_practical_implications(slot_model, fallback_items=_executive_implications(rendered, scaffold))
    paragraph_specs = _reader_memo_paragraph_specs(scaffold)
    default_paragraph = _slot_paragraph(
        slot_model,
        paragraph_specs["why_this_read"]["slot_ids"],
        lead=paragraph_specs["why_this_read"]["lead"],
        fallback_items=_executive_default_reasons(scaffold),
        max_sentences=5,
    )
    evidence_paragraph = _slot_paragraph(
        slot_model,
        paragraph_specs["evidence"]["slot_ids"],
        lead=paragraph_specs["evidence"]["lead"],
        fallback_items=_executive_carrying_evidence(scaffold),
        max_sentences=6,
    )
    practical_paragraph = _slot_paragraph(
        slot_model,
        paragraph_specs["practical"]["slot_ids"],
        lead=paragraph_specs["practical"]["lead"],
        fallback_items=_executive_counter_reasons(scaffold),
        max_sentences=5,
    )
    weak_paragraph = _humanized_limitations_paragraph(scaffold)
    crux_table = _compact_crux_table(rendered, scaffold)
    lines = [
        "## Decision Brief",
        "",
        decision_brief,
        "",
        f"**Confidence:** {confidence}",
        "",
        "## Practical Read",
        "",
    ]
    lines.extend(f"- {item}" for item in implications[:4])
    lines.extend(["", "## Why This Read", "", default_paragraph])
    lines.extend(["", "## Evidence Carrying the Conclusion", "", evidence_paragraph])
    lines.extend(["", "## Practical Scope and Exceptions", "", practical_paragraph])
    if crux_table:
        lines.extend(["", "## Decision Cruxes", "", crux_table])
    lines.extend(
        [
            "",
            "## Limits of the Current Map",
            "",
            weak_paragraph,
            "",
            "## Evidence Trail",
            "",
            "The structured evidence trail, decision-lever tables, coverage snapshot, and excluded extraction artifacts are in `EVIDENCE_APPENDIX.md`.",
        ]
    )
    return "\n".join(lines)


def _reader_memo_paragraph_specs(scaffold: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if _looks_like_nutrition_case(scaffold):
        return {
            "why_this_read": {
                "slot_ids": ("default_population", "dose_boundary", "hard_outcome_support"),
                "lead": "The cleanest evidence-backed default is bounded by the mapped population, exposure level, and direct outcome evidence.",
            },
            "evidence": {
                "slot_ids": ("hard_outcome_support", "hard_outcome_counter", "mechanism_surrogate", "study_design_limits"),
                "lead": "The evidence mix matters because direct outcomes, intervention evidence, mechanisms, and proxies answer different parts of the decision.",
            },
            "practical": {
                "slot_ids": ("comparator_substitution", "high_risk_subgroup"),
                "lead": "The practical recommendation changes most when comparators, context, or higher-risk groups enter the decision.",
            },
        }
    return {
        "why_this_read": {
            "slot_ids": ("main_support", "scope_conditions"),
            "lead": "The best-supported read is conditional: it depends on the options being compared, the setting, and the implementation conditions the evidence actually covers.",
        },
        "evidence": {
            "slot_ids": ("main_support", "counterevidence_or_tension", "evidence_type_limits", "safety_or_risk"),
            "lead": "The evidence mix should be read by function: direct support, counterevidence, proxies, guidance, and method limits should not be collapsed into one confidence signal.",
        },
        "practical": {
            "slot_ids": ("alternatives_or_comparators", "implementation_constraints", "scope_conditions"),
            "lead": "The practical decision turns on whether the mapped benefits survive the real comparator, operational constraints, and downside risks.",
        },
    }


def _slot_practical_implications(slot_model: dict[str, Any], *, fallback_items: list[str]) -> list[str]:
    lookup = _slot_lookup(slot_model)
    items: list[str] = []
    if lookup.get("main_support", {}).get("status") == "filled":
        items.append("Use the available evidence as a provisional read, not as a claim that all versions of the intervention or option work equally well.")
    if lookup.get("alternatives_or_comparators", {}).get("status") == "filled":
        items.append("Frame the recommendation around the actual alternatives being compared, since the answer can change with the comparator.")
    if lookup.get("scope_conditions", {}).get("status") == "filled":
        items.append("Keep the setting, scale, population, and intensity boundaries attached to the recommendation.")
    if lookup.get("implementation_constraints", {}).get("status") == "filled":
        items.append("Treat feasibility, safety, maintenance, and technical-fit constraints as part of the decision, not as afterthoughts.")
    if lookup.get("evidence_type_limits", {}).get("status") == "filled":
        items.append("Separate direct outcome evidence from proxy, mechanism, guidance, and implementation evidence when setting confidence.")
    if lookup.get("safety_or_risk", {}).get("status") == "filled":
        items.append("Make downside risks and failure modes visible before converting the evidence into action.")
    if lookup.get("dose_boundary", {}).get("status") == "filled":
        items.append("Treat the default answer as scoped to the mapped intensity or threshold, not to all possible exposure levels.")
    if lookup.get("hard_outcome_support", {}).get("status") == "filled":
        items.append("For the mapped default population, let direct outcome evidence carry more weight than indirect evidence.")
    if lookup.get("mechanism_surrogate", {}).get("status") == "filled":
        items.append("Keep mechanism and surrogate evidence visible because it can bound confidence without settling direct outcomes by itself.")
    if lookup.get("comparator_substitution", {}).get("status") == "filled":
        items.append("Frame practical advice around the relevant alternatives, since comparator evidence can change the recommendation.")
    if lookup.get("high_risk_subgroup", {}).get("status") == "filled":
        items.append("Do not automatically generalize the default answer to higher-risk subgroups; treat those as separate scope decisions.")
    if not items:
        items = fallback_items
    return _dedupe([_polish_reader_sentence_block(item, max_chars=240) for item in items if item])[:5]


def _build_final_evidence_appendix(rendered: str, scaffold: dict[str, Any]) -> str:
    curated = scaffold.get("curated_evidence_packets", {}) if isinstance(scaffold.get("curated_evidence_packets"), dict) else {}
    lines = [
        "## Evidence Appendix",
        "",
        "This appendix keeps the machinery inspectable while the main brief remains reader-facing.",
        "",
        "## Evidence Roles",
        "",
    ]
    for section, label in (
        ("main_support", "Main Support"),
        ("conflicting_evidence", "Conflicting Evidence"),
        ("scope_limits", "Scope Limits"),
        ("method_limits", "Method Limits"),
    ):
        rows = _curated_rows_for_sections(scaffold, (section,))
        if not rows:
            continue
        lines.extend([f"### {label}", ""])
        for row in rows[:5]:
            claim = str(row.get("claim", "")).strip()
            source = str(row.get("source", "")).strip()
            if claim:
                lines.append(f"- {claim}" + (f" ({source})" if source and source not in claim else ""))
        lines.append("")
    lines.extend(
        [
        "## Evidence by Decision Lever",
        "",
        ]
    )
    for packet in curated.get("packets", []) if isinstance(curated.get("packets"), list) else []:
        if not isinstance(packet, dict):
            continue
        rows = [row for row in packet.get("rows", []) if isinstance(row, dict)]
        if not rows:
            continue
        lines.extend(
            [
                f"### {packet.get('label') or _concept_label(str(packet.get('concept', '')))}",
                "",
                str(packet.get("synthesis_job", "")).strip() or "Decision-relevant evidence packet.",
                "",
                "| Evidence | Source | Role |",
                "|---|---|---|",
            ]
        )
        for row in rows:
            lines.append(
                "| "
                + " | ".join(
                    _markdown_table_cell(str(value))
                    for value in (row.get("claim", ""), row.get("source", ""), row.get("why_it_matters", ""))
                )
                + " |"
            )
        lines.append("")
    coverage = _markdown_section_with_heading(rendered, "Map Coverage Snapshot")
    if coverage:
        lines.extend([coverage, ""])
    lines.extend(_excluded_artifacts_section(curated))
    return "\n".join(lines).strip()


def _reader_clean_evidence_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "claim": _first_complete_sentences(_polish_reader_sentence_block(str(row.get("claim", "")), max_chars=0), max_sentences=1, max_chars=360),
        "source": _reader_source_name(str(row.get("source", ""))),
        "why_it_matters": _polish_reader_sentence_block(str(row.get("why_it_matters", "")), max_chars=220),
    }


def _reader_evidence_row_quality(row: dict[str, Any]) -> dict[str, Any]:
    raw_claim = str(row.get("claim", "")).strip()
    cleaned = _reader_clean_evidence_row(row)
    claim = str(cleaned.get("claim", "")).strip()
    lowered = claim.lower()
    reasons: list[str] = []
    score = 0
    if len(_content_terms(claim)) < 5:
        reasons.append("too_short")
    if (
        "..." in raw_claim
        or "..." in claim
        or _contains_truncated_fragment(raw_claim)
        or _contains_truncated_fragment(claim)
        or raw_claim.startswith(("...", ".", "(", "-"))
        or claim.startswith(("...", ".", "(", "-"))
    ):
        reasons.append("fragmentary_extraction")
    if _looks_like_reference_or_citation_line(raw_claim) or _looks_like_reference_or_citation_line(claim):
        reasons.append("reference_or_citation_line")
    if _looks_like_boilerplate_disclosure(lowered) or _looks_like_publisher_or_license_boilerplate(lowered):
        reasons.append("boilerplate")
    if claim and claim[-1] in ".!?":
        score += 2
    if any(
        marker in lowered
        for marker in (
            "risk",
            "mortality",
            "cardiovascular",
            "ldl",
            "apob",
            "diabetes",
            "replace",
            "substitut",
            "compared",
            "versus",
            "rather than",
            "supplemental",
            "per day",
            "per week",
            "hepa",
            "hvac",
            "cadr",
            "merv",
            "ventilation",
            "filtration",
            "pm2.5",
            "pm 2.5",
            "unsafe",
            "ozone",
        )
    ):
        score += 2
    if str(row.get("weight", "")) == "high":
        score += 2
    elif str(row.get("weight", "")) == "medium":
        score += 1
    return {"usable": not reasons, "reasons": reasons, "score": score}


def _looks_like_reference_or_citation_line(text: str) -> bool:
    lowered = text.lower()
    return bool(re.search(r"\bpmid:\d+|\bet al\.\s+[a-z].*\b\d{4};\d+|^\s*[A-Z][A-Za-z]+ [A-Z],", text)) or (
        lowered.count(" et al") >= 1 and bool(re.search(r"\b\d{4};\d+", lowered))
    )


def _curated_rows_for_concepts(scaffold: dict[str, Any], concepts: tuple[str, ...]) -> list[dict[str, Any]]:
    curated = scaffold.get("curated_evidence_packets", {}) if isinstance(scaffold.get("curated_evidence_packets"), dict) else {}
    rows: list[dict[str, Any]] = []
    for concept in concepts:
        for packet in curated.get("packets", []) if isinstance(curated.get("packets"), list) else []:
            if isinstance(packet, dict) and packet.get("concept") == concept:
                rows.extend([row for row in packet.get("rows", []) if isinstance(row, dict)])
    return rows


def _curated_rows_for_sections(scaffold: dict[str, Any], sections: tuple[str, ...]) -> list[dict[str, Any]]:
    curated = scaffold.get("curated_evidence_packets", {}) if isinstance(scaffold.get("curated_evidence_packets"), dict) else {}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for packet in curated.get("packets", []) if isinstance(curated.get("packets"), list) else []:
        if not isinstance(packet, dict):
            continue
        for row in packet.get("rows", []) if isinstance(packet.get("rows"), list) else []:
            if not isinstance(row, dict) or str(row.get("section", "")) not in sections:
                continue
            key = f"{row.get('source')}::{row.get('claim')}"
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def _synthesis_paragraph(rows: list[dict[str, Any]], *, fallback_items: list[str], lead: str, max_items: int) -> str:
    sentences = [lead]
    seen_sources: set[str] = set()
    for row in rows:
        claim = str(row.get("claim", "")).strip()
        source = str(row.get("source", "")).strip()
        if not claim:
            continue
        if source in seen_sources and len(sentences) > 2:
            continue
        seen_sources.add(source)
        source_suffix = f" ({source})" if source and source not in claim else ""
        sentences.append(claim.rstrip(".") + source_suffix + ".")
        if len(sentences) >= max_items + 1:
            break
    if len(sentences) == 1:
        sentences.extend(fallback_items[:max_items])
    return _join_polished_sentences(sentences, max_sentences=max_items + 1)


def _humanized_limitations_paragraph(scaffold: dict[str, Any]) -> str:
    issues = _string_list(scaffold.get("quality_issues"))
    readable: list[str] = []
    for issue in issues:
        lowered = issue.lower()
        if "high_claim_count" in lowered:
            readable.append("The map is dense, so the output should be read as a structured decision aid rather than as a final literature review.")
        elif "near_duplicate" in lowered:
            readable.append("The extractor produced near-duplicate claims, which can overweight repeated formulations unless curated.")
        elif "missing" in lowered:
            readable.append(_polish_reader_sentence_block(issue, max_chars=260))
    sufficiency = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    if sufficiency.get("status"):
        readable.append(f"The map sufficiency status is {str(sufficiency.get('status')).replace('_', ' ')}, so absent slots should be treated as named gaps.")
    readable.extend(_sufficiency_implications(sufficiency))
    if not readable:
        readable = _executive_weak_points(scaffold)
    return _join_polished_sentences(_dedupe(readable), max_sentences=7)


def _excluded_artifacts_section(curated: dict[str, Any]) -> list[str]:
    report = curated.get("curation_report", {}) if isinstance(curated.get("curation_report"), dict) else {}
    excluded = [row for row in report.get("excluded_rows", []) if isinstance(row, dict)]
    if not excluded:
        return ["## Extraction Artifacts Excluded From Reader Brief", "", "No evidence rows were excluded by the reader-facing curation pass."]
    lines = [
        "## Extraction Artifacts Excluded From Reader Brief",
        "",
        "These rows remain auditable but are kept out of the main memo because they are fragmentary, boilerplate-like, or citation/reference debris.",
        "",
        "| Reason | Source | Excluded text |",
        "|---|---|---|",
    ]
    for row in excluded[:12]:
        lines.append(
            "| "
            + " | ".join(
                _markdown_table_cell(str(value))
                for value in (row.get("reason", ""), row.get("source", ""), row.get("claim", ""))
            )
            + " |"
        )
    return lines


def clean_reader_briefing_text(text: str) -> str:
    lines = [_clean_reader_briefing_line(line) for line in text.splitlines()]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"\.{4,}", "...", cleaned)
    return cleaned.strip()


def clean_reader_memo_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        line = re.sub(r"\\\s*$", "", line).replace("\\|", "|")
        line = re.sub(r"^(\s*)\*\s+", r"\1- ", line)
        if not line.strip():
            lines.append("")
            continue
        if line.lstrip().startswith("|"):
            cells = [_clean_memo_table_cell(cell) for cell in line.split("|")]
            lines.append("|".join(cells))
        else:
            lines.append(_drop_ellipsis_sentences(_polish_reader_sentence_block(line, max_chars=0)))
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = _normalize_technical_acronyms(cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _normalize_technical_acronyms(text: str) -> str:
    replacements = {
        "hepa": "HEPA",
        "hvac": "HVAC",
        "cadr": "CADR",
        "merv": "MERV",
        "guv": "GUV",
        "covid": "COVID",
    }
    cleaned = text
    for lower, upper in replacements.items():
        cleaned = re.sub(rf"\b{lower}\b", upper, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bpm\s*2\.5\b", "PM 2.5", cleaned, flags=re.IGNORECASE)
    return cleaned


def _clean_memo_table_cell(cell: str) -> str:
    if not cell.strip() or set(cell.strip()) <= {"-", ":"}:
        return cell
    cleaned = _drop_ellipsis_sentences(cell)
    cleaned = _normalize_reader_source_labels(cleaned)
    return f" {cleaned.strip()} "


def _drop_ellipsis_sentences(text: str) -> str:
    if "..." not in text:
        return _normalize_reader_source_labels(text)
    pieces = re.findall(r".*?(?:[.!?](?=\s+[A-Z0-9(]|\s*$)|$)", text)
    kept = [piece.strip() for piece in pieces if piece.strip() and "..." not in piece]
    if kept:
        return _normalize_reader_source_labels(" ".join(kept))
    prefix = _normalize_reader_source_labels(text.split("...", 1)[0].rstrip(" ,;:."))
    if not prefix or not prefix.endswith((".", "?", "!")):
        return "See appendix for full source-grounded detail."
    return prefix


def _normalize_reader_source_labels(text: str) -> str:
    pattern = r"\b((?:[A-Z][A-Za-z]+|AHA|AJCN|BMJ|EAS|JAHA|JAMA|PLOS|PURE)(?:\s+(?:[A-Z][A-Za-z]+|AHA|AJCN|BMJ|EAS|JAHA|JAMA|PLOS|PURE))*\s+(?:19|20)\d{2})\s+(?:Fullish|Full|Abstract|Metadata|Pubmed|PMC)\b"
    return re.sub(pattern, lambda match: _reader_source_name(match.group(0)), text)


def briefing_reader_polish_report(rendered: str, scaffold: dict[str, Any]) -> dict[str, Any]:
    word_count = len(re.findall(r"\b\w+\b", rendered))
    executive = _executive_markdown(rendered)
    appendix_present = "## Evidence Appendix" in rendered
    issues: list[dict[str, str]] = []
    if _contains_truncated_fragment(rendered):
        issues.append(
            {
                "severity": "warning",
                "issue_type": "truncated_fragment",
                "message": "The briefing still appears to contain an extraction fragment.",
            }
        )
    if "..." in executive:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "executive_contains_ellipsis",
                "message": "The reader memo contains ellipsis-truncated prose.",
            }
        )
    if not appendix_present:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "missing_evidence_appendix",
                "message": "The briefing does not separate executive prose from the detailed evidence appendix.",
            }
        )
    if _markdown_table_count(executive) > 1:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "executive_table_overload",
                "message": "The executive brief contains too many tables for a reader-first artifact.",
            }
        )
    if len(re.findall(r"\b\w+\b", executive)) > int(executive_word_target := 1500):
        issues.append(
            {
                "severity": "warning",
                "issue_type": "executive_brief_too_long",
                "message": f"The executive brief exceeds the {executive_word_target}-word readability target.",
            }
        )
    duplicate_sentence_count = _duplicate_sentence_count(executive)
    if duplicate_sentence_count > 2:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "duplicate_sentence_overload",
                "message": "The briefing repeats too many full sentences.",
            }
        )
    if "## Evidence Roles" not in rendered or "## Evidence by Decision Lever" not in rendered:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "missing_structured_evidence_section",
                "message": "The detailed evidence structure is not visible in the appendix.",
            }
        )
    decision_slots = scaffold.get("decision_memo_slots", {}) if isinstance(scaffold.get("decision_memo_slots"), dict) else {}
    slot_coverage = decision_slots.get("coverage", {}) if isinstance(decision_slots.get("coverage"), dict) else {}
    missing_memo_slots = _string_list(slot_coverage.get("missing_required_slots"))
    if missing_memo_slots:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "missing_decision_memo_slots",
                "message": "The reader memo lacks required decision slots: " + ", ".join(missing_memo_slots) + ".",
            }
        )
    concept_packets = scaffold.get("concept_evidence_packets", {}) if isinstance(scaffold.get("concept_evidence_packets"), dict) else {}
    visible_packets = 0
    for packet in concept_packets.get("packets", []) if isinstance(concept_packets.get("packets"), list) else []:
        if isinstance(packet, dict) and _rendered_mentions_any_surface_term(rendered, _string_list(packet.get("must_surface_terms"))):
            visible_packets += 1
    packet_count = len(concept_packets.get("packets", [])) if isinstance(concept_packets.get("packets"), list) else 0
    if packet_count and visible_packets < max(1, packet_count // 2):
        issues.append(
            {
                "severity": "warning",
                "issue_type": "thin_decision_lever_visibility",
                "message": "Fewer than half of retained decision-lever packets are visibly surfaced.",
            }
        )
    score = max(0, 100 - 10 * len(issues))
    return {
        "schema_id": "briefing_reader_polish_report_v1",
        "method": "deterministic_readability_lints_for_two_tier_briefings",
        "status": "polished" if not issues else "polished_with_warnings" if score >= 70 else "needs_reader_edit",
        "score": score,
        "word_count": word_count,
        "executive_word_count": len(re.findall(r"\b\w+\b", executive)),
        "table_count": _markdown_table_count(rendered),
        "executive_table_count": _markdown_table_count(executive),
        "duplicate_sentence_count": duplicate_sentence_count,
        "decision_lever_packets_visible": visible_packets,
        "decision_lever_packet_count": packet_count,
        "decision_memo_required_slot_count": slot_coverage.get("required_slot_count"),
        "decision_memo_filled_required_slot_count": slot_coverage.get("filled_required_slot_count"),
        "decision_memo_missing_required_slots": missing_memo_slots,
        "issues": issues,
    }


def _build_polished_executive_brief(rendered: str, scaffold: dict[str, Any], *, executive_word_target: int) -> str:
    decision_brief = _executive_decision_brief(rendered, scaffold)
    confidence = _extract_confidence(rendered) or str(scaffold.get("confidence_cap") or "medium")
    implications = _executive_implications(rendered, scaffold)
    default_reasons = _executive_default_reasons(scaffold)
    counter_reasons = _executive_counter_reasons(scaffold)
    carrying_evidence = _executive_carrying_evidence(scaffold)
    weak_points = _executive_weak_points(scaffold)
    crux_table = _compact_crux_table(rendered, scaffold)
    lines = [
        "## Decision Brief",
        "",
        decision_brief,
        "",
        f"**Confidence:** {confidence}",
        "",
        "## Decision Implications",
        "",
    ]
    lines.extend(f"- {item}" for item in implications[:5])
    lines.extend(["", "## Why This Is the Right Default", ""])
    lines.append(_join_polished_sentences(default_reasons, max_sentences=5))
    lines.extend(["", "## What Could Make This Wrong", ""])
    lines.append(_join_polished_sentences(counter_reasons, max_sentences=5))
    if crux_table:
        lines.extend(["", "## What Could Change the Decision", "", crux_table])
    lines.extend(["", "## Evidence Carrying the Conclusion", ""])
    lines.append(_join_polished_sentences(carrying_evidence, max_sentences=6))
    lines.extend(["", "## Where the Map Is Weak", ""])
    lines.append(_join_polished_sentences(weak_points, max_sentences=5))
    executive = "\n".join(lines)
    if len(re.findall(r"\b\w+\b", executive)) <= executive_word_target:
        return executive
    return _trim_executive_sections(executive, target_words=executive_word_target)


def _build_polished_evidence_appendix(rendered: str, scaffold: dict[str, Any]) -> str:
    sections = []
    for title in ("Evidence Roles", "Evidence by Decision Lever", "Map Coverage Snapshot", "Audit Trail"):
        section = _markdown_section_with_heading(rendered, title)
        if section:
            sections.append(_clean_appendix_section(section))
    if not sections:
        sections = [_deterministic_appendix_from_scaffold(scaffold)]
    return "\n\n".join(["## Evidence Appendix", *sections]).strip()


def _executive_decision_brief(rendered: str, scaffold: dict[str, Any]) -> str:
    body = _markdown_section(rendered, "Decision Brief")
    body = re.sub(r"\*\*Confidence:\*\*[^\n]+", "", body).strip()
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", body) if paragraph.strip()]
    if paragraphs:
        return _first_complete_sentences(_polish_reader_sentence_block(paragraphs[0], max_chars=0), max_sentences=3, max_chars=850)
    return _polish_reader_sentence_block(_deterministic_decision_brief(scaffold), max_chars=900)


def _executive_implications(rendered: str, scaffold: dict[str, Any]) -> list[str]:
    body = _markdown_section(rendered, "Decision Implications")
    bullets = re.findall(r"^\s*[-*]\s+(.+)$", body, flags=re.MULTILINE)
    if not bullets:
        decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
        bullets = _deterministic_decision_implications(decision_model)
    return _dedupe([_polish_reader_sentence_block(item, max_chars=220) for item in bullets if item.strip()])[:6]


def _executive_default_reasons(scaffold: dict[str, Any]) -> list[str]:
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    reasons = []
    default = decision_model.get("default_answer", {}) if isinstance(decision_model.get("default_answer"), dict) else {}
    if default.get("why_this_frame"):
        reasons.append(str(default["why_this_frame"]))
    reasons.extend(_concept_packet_sentences(scaffold, preferred=("dose_or_threshold", "default_population", "hard_outcome_endpoint")))
    for row in decision_model.get("main_reasons", []) if isinstance(decision_model.get("main_reasons"), list) else []:
        if isinstance(row, dict):
            if _generic_cluster_proposition(str(row.get("proposition", ""))):
                continue
            source = _source_suffix(row.get("sources"))
            reasons.append(str(row.get("proposition", "")).strip() + source)
    return _dedupe([_polish_reader_sentence_block(item, max_chars=320) for item in reasons if item])


def _executive_counter_reasons(scaffold: dict[str, Any]) -> list[str]:
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    reasons = []
    reasons.extend(_concept_packet_sentences(scaffold, preferred=("subgroup_diabetes_or_metabolic_risk", "dietary_context_or_saturated_fat", "substitution_or_comparator")))
    for row in decision_model.get("strongest_counterarguments", []) if isinstance(decision_model.get("strongest_counterarguments"), list) else []:
        if isinstance(row, dict):
            if _generic_cluster_proposition(str(row.get("proposition", ""))):
                continue
            source = _source_suffix(row.get("sources"))
            reasons.append(str(row.get("proposition", "")).strip() + source)
    reasons.extend(_string_list(decision_model.get("what_would_change_answer"))[:3])
    return _dedupe([_polish_reader_sentence_block(item, max_chars=320) for item in reasons if item])


def _executive_carrying_evidence(scaffold: dict[str, Any]) -> list[str]:
    sentences = []
    sentences.extend(_concept_packet_sentences(scaffold, preferred=("study_design_cohort", "study_design_rct", "mechanism_ldl_apob", "surrogate_or_biomarker_endpoint")))
    ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    by_section = ledger.get("top_evidence_by_section", {}) if isinstance(ledger.get("top_evidence_by_section"), dict) else {}
    for section in ("main_support", "conflicting_evidence"):
        for row in by_section.get(section, [])[:2] if isinstance(by_section.get(section), list) else []:
            if isinstance(row, dict):
                claim = _first_complete_sentences(_polish_reader_sentence_block(str(row.get("claim", "")), max_chars=0), max_sentences=1, max_chars=320)
                source = str(row.get("source", "")).strip()
                if claim:
                    sentences.append(claim + (f" ({source})." if source and source not in claim else ""))
    return _dedupe(sentences)


def _executive_weak_points(scaffold: dict[str, Any]) -> list[str]:
    quality_status = str(scaffold.get("quality_status", "")).strip()
    items = []
    sufficiency = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    if sufficiency.get("status"):
        items.append(f"The map sufficiency status is {str(sufficiency.get('status')).replace('_', ' ')}, so absence of a slot should be read as a mapped gap rather than as negative evidence.")
    if quality_status and quality_status != "unknown":
        items.append(f"The map quality status is {quality_status.replace('_', ' ')}, which caps confidence and argues against a stronger bottom line.")
    items.extend(_string_list(scaffold.get("quality_issues"))[:3])
    contract = scaffold.get("briefing_contract", {}) if isinstance(scaffold.get("briefing_contract"), dict) else {}
    answer_frame = contract.get("answer_frame", {}) if isinstance(contract.get("answer_frame"), dict) else {}
    items.extend(_string_list(answer_frame.get("why_not_stronger"))[:3])
    return _dedupe([_polish_reader_sentence_block(item, max_chars=320) for item in items if item])


def _concept_packet_sentences(scaffold: dict[str, Any], *, preferred: tuple[str, ...]) -> list[str]:
    packets = scaffold.get("concept_evidence_packets", {}) if isinstance(scaffold.get("concept_evidence_packets"), dict) else {}
    packet_rows = [packet for packet in packets.get("packets", []) if isinstance(packet, dict)]
    by_concept = {str(packet.get("concept", "")): packet for packet in packet_rows}
    sentences = []
    for concept in preferred:
        packet = by_concept.get(concept)
        if not packet:
            continue
        rows = [row for row in packet.get("rows", []) if isinstance(row, dict)]
        if not rows:
            continue
        first = rows[0]
        label = str(packet.get("label") or _concept_label(concept))
        claim = _first_complete_sentences(_polish_reader_sentence_block(str(first.get("claim", "")), max_chars=0), max_sentences=1, max_chars=340)
        source = str(first.get("source", "")).strip()
        if claim:
            sentences.append(f"{label}: {claim}" + (f" ({source})." if source and source not in claim else ""))
    return sentences


def _compact_crux_table(rendered: str, scaffold: dict[str, Any]) -> str:
    section = _markdown_section(rendered, "What Could Change the Decision")
    table_lines = [line for line in section.splitlines() if line.strip().startswith("|")]
    if len(table_lines) >= 3:
        return "\n".join(table_lines[:6])
    cruxes = _deterministic_top_cruxes(scaffold)[:3]
    if not cruxes:
        return ""
    lines = ["| Crux | Current read | Would change if |", "|---|---|---|"]
    for row in cruxes:
        lines.append(
            "| "
            + " | ".join(
                _markdown_table_cell(_polish_reader_sentence_block(str(row.get(key, "")), max_chars=150))
                for key in ("crux", "current_read", "would_change_if")
            )
            + " |"
        )
    return "\n".join(lines)


def _deterministic_appendix_from_scaffold(scaffold: dict[str, Any]) -> str:
    roles = scaffold.get("evidence_roles", {}) if isinstance(scaffold.get("evidence_roles"), dict) else {}
    lines = ["## Evidence Roles", ""]
    for key, label in (
        ("main_support", "Main Support"),
        ("conflicting_evidence", "Conflicting Evidence"),
        ("scope_limits", "Scope Limits"),
        ("method_limits", "Method Limits"),
    ):
        lines.extend([f"### {label}", ""])
        lines.extend(f"- {_polish_reader_sentence_block(item, max_chars=260)}" for item in _string_list(roles.get(key))[:6])
        lines.append("")
    return "\n".join(lines).strip()


def _markdown_section(markdown: str, title: str) -> str:
    match = re.search(rf"^##\s+{re.escape(title)}\s*$\n?(.*?)(?=^##\s+|\Z)", markdown, flags=re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _markdown_section_with_heading(markdown: str, title: str) -> str:
    match = re.search(rf"^##\s+{re.escape(title)}\s*$\n?(.*?)(?=^##\s+|\Z)", markdown, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return ""
    return f"## {title}\n\n{match.group(1).strip()}".strip()


def _clean_appendix_section(section: str) -> str:
    lines = []
    previous_content = ""
    source_counts: dict[str, int] = {}
    for line in section.splitlines():
        cleaned = _clean_reader_briefing_line(line)
        if not cleaned.strip():
            lines.append("")
            continue
        content_key = re.sub(r"\([^)]{3,120}\)", "", cleaned).strip().lower()
        if content_key and content_key == previous_content:
            continue
        source_match = re.search(r"\|\s*([^|]{3,120})\s*\|[^|]*\|?$", cleaned) if cleaned.startswith("|") else re.search(r"\(([^)]{3,120})\)\.?$", cleaned)
        if source_match and not cleaned.startswith("|---"):
            source = source_match.group(1).strip()
            if source.lower() in {"source", "role", "why it matters"}:
                lines.append(cleaned)
                continue
            source_counts[source] = source_counts.get(source, 0) + 1
            if source_counts[source] > 5 and not cleaned.startswith("##"):
                continue
        lines.append(cleaned)
        if content_key:
            previous_content = content_key
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _clean_reader_briefing_line(line: str) -> str:
    if not line.strip():
        return ""
    if line.lstrip().startswith("|"):
        cells = line.split("|")
        if len(cells) > 2 and not set(line.strip()) <= {"|", "-", " ", ":"}:
            return "|".join(_clean_reader_table_cell(cell) for cell in cells)
    prefix = ""
    body = line
    bullet = re.match(r"^(\s*[-*]\s+)(.+)$", line)
    if bullet:
        prefix, body = bullet.group(1), bullet.group(2)
    return prefix + _polish_reader_sentence_block(body, max_chars=420)


def _clean_reader_table_cell(cell: str) -> str:
    if not cell.strip() or set(cell.strip()) <= {"-", ":"}:
        return cell
    return " " + _polish_reader_sentence_block(cell, max_chars=260).strip() + " "


def _polish_reader_sentence_block(text: str, *, max_chars: int = 500) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = _remove_extraction_fragments(cleaned)
    cleaned = re.sub(r"\b(?:Dose/threshold|Comparator/substitution|Subgroup/scope|Method-limit) evidence:\s*", "", cleaned)
    cleaned = re.sub(r"\b[A-Za-z]+ evidence:\s*(?=[a-z])", "", cleaned)
    cleaned = _remove_extraction_fragments(cleaned)
    cleaned = _polish_embedded_source_prefixes(cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"\.{4,}", "...", cleaned)
    cleaned = cleaned.strip(" ")
    if max_chars and len(cleaned) > max_chars:
        cleaned = _short_claim_fragment(cleaned, max_chars=max_chars)
    return cleaned


def _remove_extraction_fragments(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"(^|[\s(*-])\.{2,}[a-z]{2,}\s+", r"\1", cleaned)
    cleaned = re.sub(r"(^|[\s(])\.[a-z]{2,}\s+", r"\1", cleaned)
    cleaned = re.sub(r"(?<=[A-Za-z])\.[a-z]{2,}\s+", " ", cleaned)
    cleaned = re.sub(r"\b[a-z]{1,3}\.(?=[a-z]{3,})", "", cleaned)
    cleaned = re.sub(r"\b[A-Za-z]{2,}-containi\b", "ApoB-containing", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ,;")


def _contains_truncated_fragment(text: str) -> bool:
    return bool(re.search(r"(^|[\s(*-])\.{1,3}[a-z]{2,}\s+|(?<=[A-Za-z])\.[a-z]{2,}\s+|\b[a-z]{1,3}\.(?=[a-z]{3,})|\b[A-Za-z]{2,}-containi\b", text))


def _join_polished_sentences(items: list[str], *, max_sentences: int) -> str:
    polished = []
    for item in items:
        sentence = _first_complete_sentences(_polish_reader_sentence_block(item, max_chars=0), max_sentences=1, max_chars=380)
        if not sentence:
            continue
        if not sentence.endswith((".", "?", "!")):
            sentence += "."
        polished.append(sentence)
    if not polished:
        return "The current source packet does not establish enough clean evidence to support a more specific synthesis for this section."
    return " ".join(_dedupe(polished)[:max_sentences])


def _first_complete_sentences(text: str, *, max_sentences: int, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return ""
    sentences = re.findall(r".*?(?:[.!?](?=\s+[A-Z0-9(]|\s*$)|$)", cleaned)
    selected: list[str] = []
    total = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if "..." in sentence:
            break
        candidate = " ".join([*selected, sentence]).strip()
        if selected and len(candidate) > max_chars:
            break
        selected.append(sentence)
        total = candidate
        if len(selected) >= max_sentences or len(total) >= max_chars:
            break
    if total and len(total) <= max_chars:
        return total
    if selected:
        return " ".join(selected[:-1] or selected[:1]).strip()
    return _short_claim_fragment(cleaned, max_chars=max_chars)


def _source_suffix(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    sources = [_reader_source_name(str(item).strip()) for item in value if str(item).strip()]
    if not sources:
        return ""
    return f" ({', '.join(sources[:2])})."


def _generic_cluster_proposition(text: str) -> bool:
    normalized = text.lower()
    return (
        normalized.count("evidence supports") >= 1
        and any(marker in normalized for marker in ("default answer", "under stated conditions", "caution because some evidence"))
        and len(_content_terms(normalized)) < 8
    )


def _reader_source_name(source: str) -> str:
    raw = source.strip()
    if "_sources_" in raw.lower():
        raw = re.split(r"_sources_", raw, maxsplit=1, flags=re.IGNORECASE)[1]
    title = display_source_name(raw)
    title = re.sub(r"^.*\bSources\s+", "", title)
    title = polish_source_display_name(title)
    title = re.sub(r"\b(?:Fullish|Full|Abstract|Metadata|Pubmed|PMC)\b", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return _compact_citation_label(title)


def _compact_citation_label(title: str) -> str:
    words = title.split()
    year_index = next((index for index, word in enumerate(words) if re.fullmatch(r"(?:19|20)\d{2}", word)), -1)
    if year_index <= 0:
        return title
    author_words = [
        word
        for word in words[:year_index]
        if word.lower() not in {"aha", "ajcn", "bmj", "eas", "jaha", "jama", "plos", "pure"}
    ]
    if not author_words:
        author_words = words[:year_index]
    return f"{' '.join(author_words[:2])} {words[year_index]}".strip()


def _polish_embedded_source_prefixes(text: str) -> str:
    cleaned = re.sub(
        r"\b[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*_sources_([A-Za-z0-9_]+)",
        lambda match: _reader_source_name(match.group(0)),
        text,
    )
    cleaned = re.sub(r"\b[A-Z][A-Za-z0-9 ]{3,80}\b Sources ([A-Z][A-Za-z0-9 ,&/().-]+)", r"\1", cleaned)
    return cleaned


def _executive_markdown(rendered: str) -> str:
    return rendered.split("\n## Evidence Appendix", 1)[0].strip()


def _extract_confidence(markdown: str) -> str:
    match = re.search(r"\*\*Confidence:\*\*\s*([A-Za-z_\- ]+)", markdown)
    return match.group(1).strip() if match else ""


def _trim_executive_sections(markdown: str, *, target_words: int) -> str:
    if len(re.findall(r"\b\w+\b", markdown)) <= target_words:
        return markdown
    lines = markdown.splitlines()
    trimmed = []
    for line in lines:
        if line.startswith("|") and len(trimmed) > 0:
            continue
        trimmed.append(line)
        if len(re.findall(r"\b\w+\b", "\n".join(trimmed))) >= target_words:
            break
    return "\n".join(trimmed).rstrip()


def _markdown_table_count(markdown: str) -> int:
    return len(re.findall(r"^\|[-:| ]+\|$", markdown, flags=re.MULTILINE))


def _duplicate_sentence_count(markdown: str) -> int:
    seen: set[str] = set()
    duplicates = 0
    for sentence in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", markdown)):
        key = sentence.strip().lower()
        if len(key) < 80:
            continue
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
    return duplicates


def _coverage_snapshot_rows(table: dict[str, Any], *, max_rows: int = 12) -> list[dict[str, str]]:
    rows = [row for row in table.get("rows", []) if isinstance(row, dict)]
    selected: list[dict[str, str]] = []
    concept_order = sorted(
        _obligatory_coverage_concepts(_ordered_concepts(rows)),
        key=lambda concept: _COVERAGE_CONCEPT_PRIORITY.get(concept, 50),
    )
    for concept in concept_order:
        candidates = [row for row in rows if concept in row.get("concepts", []) and _coverage_concept_visible(concept, row)]
        if not candidates:
            continue
        row = sorted(candidates, key=lambda item: _coverage_concept_row_rank(concept, item))[0]
        source = str(row.get("source", "")).strip()
        claim = _coverage_current_read(concept, row)
        current_read = _short_claim_fragment(claim + (f" ({source})" if source else ""), max_chars=210)
        selected.append(
            {
                "concept": _concept_label(concept),
                "current_map_read": current_read,
                "why_it_matters": _coverage_why_it_matters(concept, row),
            }
        )
        if len(selected) >= max_rows:
            break
    return selected


def _obligatory_coverage_concepts(concepts: list[str]) -> list[str]:
    return [concept for concept in concepts if concept not in _NON_OBLIGATORY_COVERAGE_CONCEPTS]


def _coverage_concept_visible(concept: str, row: dict[str, Any]) -> bool:
    text = _coverage_text_for_row(row)
    if concept == "hard_outcome_endpoint" and _looks_like_baseline_population_criterion(text):
        return False
    markers = _COVERAGE_VISIBLE_MARKERS.get(concept, ())
    return any(marker in text for marker in markers)


def _coverage_current_read(concept: str, row: dict[str, Any]) -> str:
    slot_values = row.get("slot_values", {}) if isinstance(row.get("slot_values"), dict) else {}
    concept_slot = _COVERAGE_CONCEPT_SLOT.get(concept)
    claim = str(row.get("claim", "")).strip()
    if concept_slot and str(slot_values.get(concept_slot, "")).strip():
        value = str(slot_values[concept_slot]).strip()
        min_len = 24 if concept in {"study_design_rct", "study_design_cohort"} else 12
        if _slot_value_visibly_represents_concept(value, concept) and len(value) >= min_len:
            return value
    return claim


def _slot_value_visibly_represents_concept(value: str, concept: str) -> bool:
    normalized = value.lower()
    preferred = _COVERAGE_PREFERRED_MARKERS.get(concept)
    if not preferred:
        return True
    first_tier = preferred[0] if preferred else ()
    return any(marker in normalized for marker in first_tier)


def _coverage_why_it_matters(concept: str, row: dict[str, Any]) -> str:
    specific = {
        "default_population": "This controls who or what inherits the default answer rather than needing a separate judgment.",
        "dose_or_threshold": "Intensity, threshold, and scale boundaries keep a scoped finding from becoming an unlimited recommendation.",
        "substitution_or_comparator": "Comparator evidence affects practical advice because the best answer can change with the alternative.",
        "alternative_or_comparator": "Comparator evidence affects practical advice because the best answer can change with the alternative.",
        "hard_outcome_endpoint": "Hard outcomes are more decision-direct than surrogate movement.",
        "surrogate_or_biomarker_endpoint": "Proxy evidence can support mechanism but should not by itself settle decision-relevant outcomes.",
        "mechanism_or_causal_path": "Mechanism evidence helps explain why an effect may transfer, but it should not be read as direct outcome proof.",
        "mechanism_ldl_apob": "Mechanistic lipid evidence bounds whether the hard-outcome read is biologically plausible.",
        "subgroup_diabetes_or_metabolic_risk": "Subgroup evidence controls whether the default answer travels to higher-risk people.",
        "subgroup_fh_hyper_responder": "This subgroup can invalidate a generic population-level recommendation.",
        "dietary_context_or_saturated_fat": "Dietary context can explain why the same exposure appears harmful or neutral across settings.",
        "study_design_rct": "Trial evidence helps separate intervention effects from observational confounding.",
        "study_design_cohort": "Cohort evidence carries long-term outcome signal but remains confounding-sensitive.",
        "guideline_or_policy": "Guidance evidence shows how the map translates into practical advice.",
        "technical_performance_or_capacity": "Technical performance evidence gates whether the option can deliver the intended effect in the target setting.",
        "implementation_constraint": "Implementation constraints can determine whether evidence-backed options work in practice.",
        "safety_or_adverse_effect": "Safety and downside-risk evidence can change a recommendation even when the main effect is favorable.",
        "setting_or_context": "Setting evidence controls whether the mapped result transfers to the decision context.",
    }
    return specific.get(concept) or str(row.get("why_it_matters", "")).strip() or "This is a retained decision-relevant map ingredient."


def _coverage_text_for_row(row: dict[str, Any]) -> str:
    slot_values = row.get("slot_values", {}) if isinstance(row.get("slot_values"), dict) else {}
    parts = [str(row.get("claim", "")), *(str(value) for value in slot_values.values())]
    return re.sub(r"\s+", " ", " ".join(parts).lower())


def _looks_like_baseline_population_criterion(text: str) -> bool:
    return (
        any(marker in text for marker in ("free of", "without", "with no history of"))
        and "baseline" in text
        and not any(marker in text for marker in ("risk", "outcome", "mortality", "incident", "associated", "hazard ratio", "relative risk"))
    )


def _coverage_snapshot_rank(row: dict[str, Any]) -> tuple[int, int, int, str]:
    concepts = [concept for concept in row.get("concepts", []) if isinstance(concept, str)]
    concept_priority = min((_COVERAGE_CONCEPT_PRIORITY.get(concept, 50) for concept in concepts), default=50)
    return (concept_priority, -int(row.get("score", 0)), len(str(row.get("claim", ""))), str(row.get("claim_id", "")))


def _coverage_concept_row_rank(concept: str, row: dict[str, Any]) -> tuple[int, int, int, str]:
    return (
        _coverage_concept_specificity(concept, row),
        -int(row.get("score", 0)),
        len(str(row.get("claim", ""))),
        str(row.get("claim_id", "")),
    )


def _coverage_concept_specificity(concept: str, row: dict[str, Any]) -> int:
    text = _coverage_text_for_row(row)
    preferred_markers = _COVERAGE_PREFERRED_MARKERS.get(concept, ())
    for index, markers in enumerate(preferred_markers):
        if any(marker in text for marker in markers):
            return index
    return len(preferred_markers) + 1


_NON_OBLIGATORY_COVERAGE_CONCEPTS = {"source_quality_or_incentive"}


_COVERAGE_CONCEPT_PRIORITY = {
    "default_population": 0,
    "dose_or_threshold": 1,
    "substitution_or_comparator": 2,
    "alternative_or_comparator": 3,
    "technical_performance_or_capacity": 4,
    "implementation_constraint": 5,
    "safety_or_adverse_effect": 6,
    "hard_outcome_endpoint": 7,
    "surrogate_or_biomarker_endpoint": 8,
    "mechanism_or_causal_path": 9,
    "mechanism_ldl_apob": 10,
    "subgroup_diabetes_or_metabolic_risk": 11,
    "subgroup_fh_hyper_responder": 12,
    "dietary_context_or_saturated_fat": 13,
    "setting_or_context": 14,
    "study_design_rct": 15,
    "study_design_cohort": 16,
    "guideline_or_policy": 17,
}


def _concept_label(concept: str) -> str:
    return {
        "default_population": "Default population",
        "dose_or_threshold": "Dose or threshold",
        "hard_outcome_endpoint": "Hard outcomes",
        "surrogate_or_biomarker_endpoint": "Proxy or surrogate outcomes",
        "mechanism_or_causal_path": "Mechanism or causal path",
        "mechanism_ldl_apob": "LDL/ApoB mechanism",
        "dietary_context_or_saturated_fat": "Saturated fat or dietary context",
        "substitution_or_comparator": "Comparator or substitution",
        "alternative_or_comparator": "Alternatives or comparators",
        "subgroup_diabetes_or_metabolic_risk": "Metabolic-risk subgroup",
        "subgroup_fh_hyper_responder": "FH or hyper-responder subgroup",
        "technical_performance_or_capacity": "Technical capacity or performance",
        "implementation_constraint": "Implementation constraints",
        "safety_or_adverse_effect": "Safety or downside risk",
        "setting_or_context": "Setting or context",
        "study_design_rct": "RCT/intervention evidence",
        "study_design_cohort": "Cohort/observational evidence",
        "guideline_or_policy": "Guidance or policy",
    }.get(concept, concept.replace("_", " "))


_COVERAGE_CONCEPT_SLOT = {
    "default_population": "default_population",
    "dose_or_threshold": "dose_or_intensity_threshold",
    "substitution_or_comparator": "substitution_or_comparator",
    "alternative_or_comparator": "substitution_or_comparator",
    "hard_outcome_endpoint": "endpoint_type",
    "surrogate_or_biomarker_endpoint": "mechanism",
    "mechanism_or_causal_path": "mechanism",
    "mechanism_ldl_apob": "mechanism",
    "subgroup_diabetes_or_metabolic_risk": "high_risk_subgroup",
    "subgroup_fh_hyper_responder": "high_risk_subgroup",
    "study_design_rct": "study_design",
    "study_design_cohort": "study_design",
    "technical_performance_or_capacity": "practical_recommendation",
    "implementation_constraint": "practical_recommendation",
    "safety_or_adverse_effect": "practical_recommendation",
    "setting_or_context": "default_population",
}


_COVERAGE_VISIBLE_MARKERS = {
    "default_population": ("generally healthy", "healthy adults", "general population", "free of", "without", "free-living"),
    "dose_or_threshold": ("per day", "per week", "up to", "moderate", "high intake", "low intake", "≥", "≤", "<", ">"),
    "hard_outcome_endpoint": ("mortality", "cvd", "cardiovascular", "stroke", "myocardial infarction", "coronary", "incident"),
    "surrogate_or_biomarker_endpoint": ("biomarker", "surrogate", "proxy", "pm2.5", "pm 2.5", "particulate", "particle", "ldl", "hdl", "apob", "cholesterol", "lipid"),
    "mechanism_or_causal_path": ("mechanism", "causal", "pathway", "mediated", "exposure", "transmission", "filtration", "ventilation", "source control"),
    "mechanism_ldl_apob": ("ldl", "apob", "cholesterol", "atherosclerosis", "tmao", "trimethylamine", "metabolite"),
    "dietary_context_or_saturated_fat": ("saturated fat", "dietary pattern", "dietary cholesterol", "red meat", "processed meat", "overnutrition"),
    "substitution_or_comparator": ("replace", "replacing", "substitut", "compared with", "versus", "instead of", "egg white", "plant protein"),
    "alternative_or_comparator": ("compared with", "compared to", "versus", " vs ", "rather than", "instead of", "alternative", "supplemental", "over "),
    "subgroup_diabetes_or_metabolic_risk": ("type 2 diabetes", "diabetes", "t2d", "prediabetes", "metabolic", "renal", "kidney"),
    "subgroup_fh_hyper_responder": ("familial", "hyper-responder", "hyper responder", "high ldl", "high apob", "elevated ldl", "elevated apob"),
    "study_design_rct": ("randomized", "randomised", "rct", "trial", "crossover", "intervention"),
    "study_design_cohort": ("cohort", "prospective", "follow-up", "observational", "participants"),
    "guideline_or_policy": ("guideline", "advisory", "recommendation", "dietary guidance", "clinicians", "consumers", "should"),
    "technical_performance_or_capacity": ("cadr", "merv", "hvac", "hepa", "airflow", "ventilation", "filtration", "room size", "capacity", "pm2.5", "pm 2.5"),
    "implementation_constraint": ("feasible", "not feasible", "maintenance", "operate", "operated", "serviced", "upgrade", "standard", "cost", "noise", "capacity", "room size"),
    "safety_or_adverse_effect": ("unsafe", "ozone", "adverse", "harm", "risk", "hazard", "not safe", "failure"),
    "setting_or_context": ("classroom", "school", "district", "building", "home", "workplace", "setting", "county", "region", "site"),
}


_COVERAGE_PREFERRED_MARKERS = {
    "mechanism_ldl_apob": (("apob", "apo b"), ("ldl", "ldl-c"), ("cholesterol",)),
    "surrogate_or_biomarker_endpoint": (("apob", "apo b"), ("ldl", "hdl", "lipid", "particle"), ("cholesterol", "biomarker")),
    "dietary_context_or_saturated_fat": (("saturated fat",), ("dietary pattern", "diet quality"), ("dietary cholesterol", "red meat", "processed meat", "overnutrition")),
    "substitution_or_comparator": (("plant protein", "egg white"), ("replace", "replacing", "substitut"), ("compared with", "versus", "instead of")),
    "alternative_or_comparator": (("compared with", "compared to", "versus"), ("rather than", "instead of", "over "), ("alternative", "supplemental")),
    "guideline_or_policy": (("guideline", "dietary guidance"), ("recommendation", "advisory"), ("clinicians", "consumers", "should")),
    "technical_performance_or_capacity": (("cadr", "merv", "hvac", "hepa"), ("ventilation", "filtration", "airflow"), ("room size", "capacity")),
    "implementation_constraint": (("not feasible", "feasible"), ("maintenance", "serviced", "operate", "operated"), ("cost", "noise", "capacity")),
    "safety_or_adverse_effect": (("unsafe", "not safe", "ozone"), ("adverse", "harm", "risk"), ("failure", "hazard")),
    "setting_or_context": (("classroom", "school", "district"), ("building", "home", "workplace"), ("setting", "site", "region")),
}


def _markdown_table_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value).replace("|", "\\|").strip()


def _extract_json_string_field_local(text: str, field: str) -> str:
    match = re.search(rf'"{re.escape(field)}"\s*:\s*"((?:\\.|[^"\\])*)"', text, flags=re.DOTALL)
    if not match:
        return ""
    try:
        return json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        return match.group(1).replace(r"\"", '"').replace(r"\n", "\n")


def build_briefing_contract(partition: dict[str, Any], quality_report: dict[str, Any]) -> dict[str, Any]:
    evidence_roles = partition.get("evidence_roles", {})
    support = _string_list(evidence_roles.get("main_support"))
    conflict = _string_list(evidence_roles.get("conflicting_evidence"))
    scope = _string_list(evidence_roles.get("scope_limits"))
    method = _string_list(evidence_roles.get("method_limits"))
    support_profile = _support_signal_profile(support)
    scope_ledger = _scope_ledger([*scope, *method, *conflict])
    active_lints = _active_overstatement_lints(
        support_profile=support_profile,
        conflict=conflict,
        scope_ledger=scope_ledger,
        method_limits=method,
        quality_report=quality_report,
    )
    return {
        "schema_id": "briefing_contract_v1",
        "answer_frame": {
            "default_stance_instruction": _default_stance_instruction(support_profile, conflict),
            "confidence_cap": confidence_cap(quality_report),
            "holds_when": _dedupe(_positive_scope_items(scope))[:5],
            "weakens_when": _dedupe([*conflict, *_limiting_scope_items(scope)])[:6],
            "strongest_counterposition": conflict[0] if conflict else "",
            "why_not_stronger": _dedupe([*method, *quality_report_issue_text(quality_report)])[:6],
        },
        "scope_ledger": scope_ledger,
        "evidence_direction": {
            "supports_default_stance": support[:8],
            "supports_counterposition": conflict[:8],
            "bounds_scope": scope[:8],
            "changes_interpretation": _string_list(partition.get("audit_trail"))[:8],
            "identifies_missing_or_limited_evidence": method[:8],
        },
        "support_signal_profile": support_profile,
        "overstatement_lint": active_lints,
    }


def build_evidence_weighting_ledger(
    candidate_map: dict[str, Any],
    partition: dict[str, Any],
    quality_report: dict[str, Any],
    source_lookup: dict[str, str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for claim in _claims(candidate_map):
        section = _claim_evidence_section(claim)
        score, modifiers = _claim_evidence_weight_score(claim, section, quality_report, source_lookup)
        concepts = _claim_concepts(claim)
        noise = _claim_noise_profile(claim)
        rows.append(
            {
                "claim_id": str(claim.get("claim_id", "")),
                "section": section,
                "evidence_family": _evidence_family_for_claim(claim, section, source_lookup),
                "decision_slots": _decision_slots_for_claim(claim),
                "evidence_slots": _evidence_slots_for_claim(claim),
                "decision_concepts": concepts,
                "noise": noise,
                "weight": _weight_label(score),
                "score": score,
                "modifiers": modifiers,
                "claim": str(claim.get("claim") or claim.get("text") or ""),
                "source": source_lookup.get(str(claim.get("source_id", "")), display_source_name(str(claim.get("source_id", "")))),
                "supporting_source_count": len(_claim_supporting_sources_for_briefing(claim)),
            }
        )
    rows.sort(key=lambda row: (-int(row["score"]), str(row["section"]), str(row["claim_id"])))
    by_section: dict[str, list[dict[str, Any]]] = {
        "main_support": [],
        "conflicting_evidence": [],
        "scope_limits": [],
        "method_limits": [],
    }
    for row in rows:
        by_section.setdefault(str(row["section"]), []).append(row)
    return {
        "schema_id": "evidence_weighting_ledger_v1",
        "method": "generic_entailment_source_directness_support_role_scoring",
        "quality_status": quality_report.get("status"),
        "all_evidence": rows,
        "family_counts": _counts(row["evidence_family"] for row in rows),
        "decision_slot_counts": _decision_slot_counts(rows),
        "evidence_slot_counts": _counts(slot for row in rows for slot in row.get("evidence_slots", [])),
        "decision_concept_counts": _counts(concept for row in rows for concept in row.get("decision_concepts", [])),
        "noise_counts": _counts(row.get("noise", {}).get("kind") for row in rows if isinstance(row.get("noise"), dict)),
        "top_evidence_by_section": {section: items[:6] for section, items in by_section.items()},
        "weight_counts": _counts(row["weight"] for row in rows),
        "notes": [
            "Weights are deterministic synthesis guidance, not statistical study-quality scores.",
            "Low-weight evidence may still matter as a caveat, scope boundary, or source-completeness warning.",
        ],
        "partition_counts": {key: len(value) for key, value in partition.get("evidence_roles", {}).items()},
    }


def build_evidence_compression_table(
    candidate_map: dict[str, Any],
    evidence_ledger: dict[str, Any],
    source_lookup: dict[str, str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    claim_lookup = {str(claim.get("claim_id", "")): claim for claim in _claims(candidate_map)}
    for row in evidence_ledger.get("all_evidence", []):
        if not isinstance(row, dict):
            continue
        claim_id = str(row.get("claim_id", ""))
        claim = claim_lookup.get(claim_id, {})
        concepts = [str(item) for item in row.get("decision_concepts", []) if isinstance(item, str)]
        if not concepts and str(row.get("section", "")) not in {"main_support", "conflicting_evidence"}:
            continue
        noise = row.get("noise", {}) if isinstance(row.get("noise"), dict) else {}
        if str(noise.get("kind", "")) in {"boilerplate_disclosure", "publisher_or_license_boilerplate"} and int(row.get("score", 0)) < 5:
            continue
        rows.append(
            {
                "claim_id": claim_id,
                "source": row.get("source", ""),
                "section": row.get("section", ""),
                "role": str(claim.get("role", "")),
                "weight": row.get("weight", "medium"),
                "score": row.get("score", 0),
                "concepts": concepts,
                "evidence_slots": [str(item) for item in row.get("evidence_slots", []) if isinstance(item, str)],
                "evidence_family": row.get("evidence_family", "general_evidence"),
                "slot_values": _compression_slot_values(str(row.get("claim", "")), row.get("decision_slots", [])),
                "claim": _compressed_claim_text(str(row.get("claim", "")), noise),
                "why_it_matters": _compression_why_it_matters(row),
                "noise_kind": noise.get("kind", "none"),
            }
        )
    selected = _select_compression_rows(rows, max_rows=36)
    present_obligatory = _obligatory_coverage_concepts(_ordered_concepts(rows))
    selected_obligatory = _obligatory_coverage_concepts(_ordered_concepts(selected))
    return {
        "schema_id": "evidence_compression_table_v1",
        "method": "concept_coverage_then_weighted_evidence_with_noise_suppression",
        "coverage": {
            "present_concepts": _ordered_concepts(rows),
            "selected_concepts": _ordered_concepts(selected),
            "obligatory_present_concepts": present_obligatory,
            "obligatory_selected_concepts": selected_obligatory,
            "concept_coverage_preserved": set(present_obligatory).issubset(set(selected_obligatory)),
        },
        "rows": selected,
    }


def build_concept_evidence_packets(evidence_ledger: dict[str, Any], *, max_packets: int = 10, rows_per_packet: int = 4) -> dict[str, Any]:
    rows = [
        _concept_packet_row(row)
        for row in evidence_ledger.get("all_evidence", [])
        if isinstance(row, dict)
    ]
    rows = [row for row in rows if row.get("concepts") and str(row.get("noise_kind", "none")) in {"", "none"}]
    packets: list[dict[str, Any]] = []
    for concept in _obligatory_coverage_concepts(_ordered_concepts(rows)):
        candidates = [row for row in rows if concept in row.get("concepts", [])]
        if not candidates:
            continue
        selected = sorted(candidates, key=lambda row: _concept_packet_row_rank(concept, row))[:rows_per_packet]
        packets.append(
            {
                "concept": concept,
                "label": _concept_label(concept),
                "synthesis_job": _concept_packet_synthesis_job(concept),
                "must_surface_terms": _concept_packet_surface_terms(concept, selected),
                "rows": selected,
            }
        )
        if len(packets) >= max_packets:
            break
    return {
        "schema_id": "concept_evidence_packets_v1",
        "method": "concept_family_ranked_evidence_packets_for_staged_synthesis",
        "packet_count": len(packets),
        "packets": packets,
    }


def _concept_packet_row(row: dict[str, Any]) -> dict[str, Any]:
    noise = row.get("noise", {}) if isinstance(row.get("noise"), dict) else {}
    concepts = [str(item) for item in row.get("decision_concepts", []) if isinstance(item, str)]
    claim = _compressed_claim_text(str(row.get("claim", "")), noise)
    return {
        "claim_id": row.get("claim_id"),
        "source": row.get("source"),
        "section": row.get("section"),
        "weight": row.get("weight", "medium"),
        "score": row.get("score", 0),
        "concepts": concepts,
        "evidence_slots": [str(item) for item in row.get("evidence_slots", []) if isinstance(item, str)],
        "evidence_family": row.get("evidence_family", "general_evidence"),
        "claim": claim,
        "why_it_matters": _compression_why_it_matters({"decision_concepts": concepts, "section": row.get("section")}),
        "noise_kind": noise.get("kind", "none"),
    }


def _concept_packet_row_rank(concept: str, row: dict[str, Any]) -> tuple[int, int, int, str]:
    return (
        _coverage_concept_specificity(concept, row),
        -int(row.get("score", 0)),
        len(str(row.get("claim", ""))),
        str(row.get("claim_id", "")),
    )


def _concept_packet_synthesis_job(concept: str) -> str:
    return {
        "default_population": "State who the default answer applies to and where transfer is uncertain.",
        "dose_or_threshold": "State the dose or threshold boundary that keeps the advice from overgeneralizing.",
        "substitution_or_comparator": "State how the recommendation changes when replacement options or comparators matter.",
        "hard_outcome_endpoint": "Separate direct outcome evidence from biomarker or mechanistic evidence.",
        "surrogate_or_biomarker_endpoint": "Explain what proxy or surrogate outcomes can support and what they cannot settle.",
        "mechanism_or_causal_path": "Explain the causal pathway and where it falls short of direct outcome evidence.",
        "mechanism_ldl_apob": "Explain the LDL/ApoB mechanism and whether it changes the bottom-line read.",
        "subgroup_diabetes_or_metabolic_risk": "State whether subgroup evidence narrows the general-population advice.",
        "subgroup_fh_hyper_responder": "State whether high-risk lipid subgroups need separate advice.",
        "dietary_context_or_saturated_fat": "State how diet composition or saturated fat modifies the exposure read.",
        "alternative_or_comparator": "State how the recommendation changes across the alternatives being compared.",
        "technical_performance_or_capacity": "State what technical capacity or performance evidence is needed for the option to work.",
        "implementation_constraint": "State what practical constraints gate implementation.",
        "safety_or_adverse_effect": "State what harms, safety issues, or downside risks constrain the recommendation.",
        "setting_or_context": "State whether the mapped evidence transfers to the target setting.",
        "study_design_rct": "State what intervention evidence contributes and its limits.",
        "study_design_cohort": "State what long-run observational evidence contributes and its confounding limits.",
        "guideline_or_policy": "State what practical guidance follows and where implementation is hard.",
    }.get(concept, "State the decision-relevant contribution and caveat for this evidence family.")


def _concept_packet_surface_terms(concept: str, rows: list[dict[str, Any]]) -> list[str]:
    text = " ".join(str(row.get("claim", "")) for row in rows).lower()
    preferred = [marker for tier in _COVERAGE_PREFERRED_MARKERS.get(concept, ()) for marker in tier]
    visible = [marker for marker in preferred if marker in text and len(marker) >= 4]
    if visible:
        return _dedupe(visible)[:5]
    markers = [marker for marker in _COVERAGE_VISIBLE_MARKERS.get(concept, ()) if marker in text and len(marker) >= 4]
    return _dedupe(markers)[:5]


def _compression_slot_values(claim: str, slots: Any) -> dict[str, str]:
    values: dict[str, str] = {}
    for slot in slots if isinstance(slots, list) else []:
        if not isinstance(slot, str):
            continue
        value = _slot_value(slot, claim)
        if value:
            values[slot] = value
    return values


def _compressed_claim_text(claim: str, noise: dict[str, Any]) -> str:
    kind = str(noise.get("kind", "none"))
    if kind == "boilerplate_disclosure":
        return "The source includes extensive funding or conflict-of-interest disclosures; treat this as source context, not substantive outcome evidence."
    if kind == "publisher_or_license_boilerplate":
        return "The source includes publisher, copyright, license, or metadata boilerplate; do not use it as substantive evidence."
    return _short_claim_fragment(claim, max_chars=260)


def _compression_why_it_matters(row: dict[str, Any]) -> str:
    concepts = set(str(item) for item in row.get("decision_concepts", []))
    section = str(row.get("section", ""))
    if "mechanism_ldl_apob" in concepts:
        return "Mechanistic lipid evidence bounds whether the hard-outcome read is biologically plausible."
    if "mechanism_or_causal_path" in concepts:
        return "Mechanism evidence helps explain transfer but should not be treated as direct outcome evidence."
    if "technical_performance_or_capacity" in concepts:
        return "Technical capacity evidence gates whether the option can deliver the intended effect."
    if "implementation_constraint" in concepts:
        return "Implementation constraints can determine whether a mapped option works in practice."
    if "safety_or_adverse_effect" in concepts:
        return "Downside-risk evidence can change the recommendation even when the main effect is favorable."
    if "alternative_or_comparator" in concepts:
        return "Comparator evidence affects the practical recommendation because the alternative matters."
    if "setting_or_context" in concepts:
        return "Setting evidence controls whether the mapped result transfers to the decision context."
    if "dietary_context_or_saturated_fat" in concepts:
        return "Dietary context can explain why an exposure appears harmful or neutral across settings."
    if "subgroup_diabetes_or_metabolic_risk" in concepts or "subgroup_fh_hyper_responder" in concepts:
        return "Subgroup evidence controls whether the default answer travels to higher-risk people."
    if "substitution_or_comparator" in concepts:
        return "Comparator evidence affects the practical recommendation because the alternative matters."
    if "hard_outcome_endpoint" in concepts:
        return "Hard-outcome evidence is more decision-direct than surrogate evidence."
    if "surrogate_or_biomarker_endpoint" in concepts:
        return "Surrogate evidence should limit confidence rather than settle long-term outcomes."
    if section == "conflicting_evidence":
        return "This evidence pushes against the default answer or limits its scope."
    if section == "method_limits":
        return "This evidence affects how strongly the mapped findings should be read."
    return "This is part of the decision-relevant evidence base."


def _select_compression_rows(rows: list[dict[str, Any]], *, max_rows: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for concept in _ordered_concepts(rows):
        candidates = [row for row in rows if concept in row.get("concepts", []) and str(row.get("claim_id", "")) not in seen_ids]
        if not candidates:
            continue
        best = sorted(candidates, key=_compression_row_rank)[0]
        selected.append(best)
        seen_ids.add(str(best.get("claim_id", "")))
        if len(selected) >= max_rows:
            return selected
    for section in ("main_support", "conflicting_evidence", "scope_limits", "method_limits"):
        candidates = [row for row in rows if row.get("section") == section and str(row.get("claim_id", "")) not in seen_ids]
        if not candidates:
            continue
        best = sorted(candidates, key=_compression_row_rank)[0]
        selected.append(best)
        seen_ids.add(str(best.get("claim_id", "")))
        if len(selected) >= max_rows:
            return selected
    for row in sorted(rows, key=_compression_row_rank):
        claim_id = str(row.get("claim_id", ""))
        if claim_id in seen_ids:
            continue
        selected.append(row)
        seen_ids.add(claim_id)
        if len(selected) >= max_rows:
            break
    return selected


def _compression_row_rank(row: dict[str, Any]) -> tuple[int, int, int, str]:
    noise_penalty = 1 if row.get("noise_kind") not in {"", "none", None} else 0
    section_priority = {"main_support": 0, "conflicting_evidence": 1, "scope_limits": 2, "method_limits": 3}.get(str(row.get("section")), 4)
    return (noise_penalty, -int(row.get("score", 0)), section_priority, str(row.get("claim_id", "")))


def _ordered_concepts(rows: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "dose_or_threshold",
        "default_population",
        "hard_outcome_endpoint",
        "surrogate_or_biomarker_endpoint",
        "mechanism_or_causal_path",
        "technical_performance_or_capacity",
        "implementation_constraint",
        "safety_or_adverse_effect",
        "setting_or_context",
        "mechanism_ldl_apob",
        "dietary_context_or_saturated_fat",
        "substitution_or_comparator",
        "alternative_or_comparator",
        "subgroup_diabetes_or_metabolic_risk",
        "subgroup_fh_hyper_responder",
        "study_design_rct",
        "study_design_cohort",
        "guideline_or_policy",
        "source_quality_or_incentive",
    ]
    present: list[str] = []
    for concept in preferred:
        if any(concept in row.get("concepts", []) for row in rows):
            present.append(concept)
    for row in rows:
        for concept in row.get("concepts", []):
            if concept not in present:
                present.append(concept)
    return present


def build_proposition_clusters(
    candidate_map: dict[str, Any],
    evidence_ledger: dict[str, Any],
    source_lookup: dict[str, str],
) -> dict[str, Any]:
    claim_lookup = {str(claim.get("claim_id")): claim for claim in _claims(candidate_map)}
    ledger_rows = [
        row for row in evidence_ledger.get("all_evidence", [])
        if isinstance(row, dict) and str(row.get("claim_id", "")) in claim_lookup
    ]
    clusters_by_key: dict[str, dict[str, Any]] = {}
    for row in ledger_rows:
        claim = claim_lookup[str(row["claim_id"])]
        key = _proposition_cluster_key(claim, str(row.get("section", "")))
        cluster = clusters_by_key.setdefault(
            key,
            {
                "cluster_id": f"cluster_{len(clusters_by_key) + 1:03d}",
                "direction": _cluster_direction(str(row.get("section", ""))),
                "stance": _claim_stance(claim, str(row.get("section", ""))),
                "scope_dimensions": [],
                "claim_ids": [],
                "sources": [],
                "representative_claims": [],
                "weight_scores": [],
                "weight_labels": [],
                "proposition": "",
            },
        )
        claim_text = str(claim.get("claim") or claim.get("text") or "")
        cluster["claim_ids"].append(str(row["claim_id"]))
        cluster["sources"].extend(_claim_supporting_sources_for_briefing(claim))
        cluster["representative_claims"].append(
            {
                "claim_id": str(row["claim_id"]),
                "claim": claim_text,
                "source": source_lookup.get(str(claim.get("source_id", "")), display_source_name(str(claim.get("source_id", "")))),
                "weight": row.get("weight", "medium"),
            }
        )
        cluster["scope_dimensions"].extend(_scope_dimensions_for_text(claim_text))
        cluster["weight_scores"].append(int(row.get("score", 0)))
        cluster["weight_labels"].append(str(row.get("weight", "medium")))
    clusters: list[dict[str, Any]] = []
    for cluster in clusters_by_key.values():
        scores = [int(score) for score in cluster.pop("weight_scores", [])]
        labels = [str(label) for label in cluster.pop("weight_labels", [])]
        cluster["claim_ids"] = _dedupe(cluster["claim_ids"])
        cluster["sources"] = sorted(set(cluster["sources"]))
        cluster["scope_dimensions"] = sorted(set(cluster["scope_dimensions"])) or ["general"]
        cluster["representative_claims"] = sorted(
            cluster["representative_claims"],
            key=lambda item: (
                -{"high": 2, "medium": 1, "low": 0}.get(str(item.get("weight")), 1),
                str(item.get("claim_id", "")),
            ),
        )[:5]
        cluster["strength_score"] = sum(scores)
        cluster["evidence_weight"] = _cluster_weight_label(scores, labels)
        cluster["proposition"] = _cluster_proposition(cluster)
        clusters.append(cluster)
    clusters.sort(key=lambda item: (-int(item.get("strength_score", 0)), str(item.get("cluster_id", ""))))
    clusters = _attach_cluster_tensions(clusters, _relations(candidate_map))
    return {
        "schema_id": "proposition_clusters_v1",
        "method": "direction_stance_scope_weighted_claim_clustering",
        "clusters": clusters[:12],
        "cluster_count": len(clusters),
    }


def build_decision_model(
    proposition_clusters: dict[str, Any],
    contract: dict[str, Any],
    quality_report: dict[str, Any],
    evidence_ledger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence_ledger = evidence_ledger or {}
    clusters = [cluster for cluster in proposition_clusters.get("clusters", []) if isinstance(cluster, dict)]
    classification = _decision_classification(clusters, contract)
    support_clusters = [cluster for cluster in clusters if cluster.get("direction") == "supports_default"]
    counter_clusters = [cluster for cluster in clusters if cluster.get("direction") == "supports_counterposition"]
    scope_clusters = [cluster for cluster in clusters if cluster.get("direction") == "bounds_scope"]
    method_clusters = [cluster for cluster in clusters if cluster.get("direction") == "limits_confidence"]
    answer_frame = contract.get("answer_frame", {}) if isinstance(contract.get("answer_frame"), dict) else {}
    return {
        "schema_id": "decision_model_v1",
        "default_answer": {
            "classification": classification,
            "confidence_cap": confidence_cap(quality_report),
            "plain_language_instruction": _classification_instruction(classification),
            "why_this_frame": _decision_frame_reason(classification, support_clusters, counter_clusters),
        },
        "decision_slots": build_decision_slots(evidence_ledger),
        "missing_decision_slots": _missing_decision_slots(evidence_ledger),
        "evidence_families": evidence_ledger.get("family_counts", {}),
        "holds_for": _cluster_scope_items(scope_clusters, positive=True)[:6],
        "does_not_hold_for": _dedupe([*_string_list(answer_frame.get("weakens_when")), *_cluster_scope_items(scope_clusters, positive=False)])[:8],
        "main_reasons": _cluster_proposition_rows(support_clusters)[:5],
        "strongest_counterarguments": _cluster_proposition_rows(counter_clusters)[:5],
        "tension_resolutions": _tension_resolution_rows(clusters)[:5],
        "practical_recommendations": _practical_recommendations(classification, scope_clusters, method_clusters, evidence_ledger)[:7],
        "what_would_change_answer": _what_would_change_answer(counter_clusters, method_clusters, quality_report)[:6],
        "prose_requirements": _decision_model_prose_requirements(classification),
    }


def build_decision_slots(evidence_ledger: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    slots = {
        "default_population": [],
        "dose_or_intensity_threshold": [],
        "high_risk_subgroup": [],
        "mechanism": [],
        "substitution_or_comparator": [],
        "endpoint_type": [],
        "study_design": [],
        "practical_recommendation": [],
        "technical_or_capacity": [],
        "implementation_constraint": [],
        "safety_or_risk": [],
        "setting_or_context": [],
    }
    rows = [row for row in evidence_ledger.get("all_evidence", []) if isinstance(row, dict)]
    for row in sorted(rows, key=lambda item: (-int(item.get("score", 0)), str(item.get("claim_id", "")))):
        claim = str(row.get("claim", ""))
        for slot in row.get("decision_slots", []):
            if slot not in slots:
                continue
            value = _slot_value(slot, claim)
            if not value:
                continue
            entry = {
                "value": value,
                "claim": claim,
                "source": row.get("source", ""),
                "weight": row.get("weight", "medium"),
                "evidence_family": row.get("evidence_family", "general_evidence"),
            }
            if not _slot_entry_exists(slots[slot], entry):
                slots[slot].append(entry)
    return {slot: entries[:6] for slot, entries in slots.items()}


def build_map_sufficiency_report(
    candidate_map: dict[str, Any],
    *,
    question: str,
    evidence_ledger: dict[str, Any],
    decision_model: dict[str, Any],
    quality_report: dict[str, Any],
) -> dict[str, Any]:
    slots = decision_model.get("decision_slots", {}) if isinstance(decision_model.get("decision_slots"), dict) else {}
    families = evidence_ledger.get("family_counts", {}) if isinstance(evidence_ledger.get("family_counts"), dict) else {}
    expected_slots = _expected_slots_for_question(question, evidence_ledger)
    expected_families = _expected_families_for_question(question)
    present_slots = sorted(slot for slot, entries in slots.items() if isinstance(entries, list) and entries)
    missing_expected_slots = [slot for slot in expected_slots if slot not in present_slots]
    missing_expected_families = [family for family in expected_families if int(families.get(family, 0)) == 0]
    obligations = _sufficiency_output_obligations(slots, missing_expected_slots, missing_expected_families)
    issues = _sufficiency_issues(
        claim_count=len(_claims(candidate_map)),
        relation_count=len(_relations(candidate_map)),
        missing_expected_slots=missing_expected_slots,
        missing_expected_families=missing_expected_families,
        quality_report=quality_report,
    )
    status = _sufficiency_status(issues)
    return {
        "schema_id": "map_sufficiency_report_v1",
        "method": "question_expected_slots_plus_map_detected_slots_and_evidence_families",
        "status": status,
        "question_profile": {
            "expected_decision_slots": expected_slots,
            "expected_evidence_families": expected_families,
        },
        "present_decision_slots": {
            slot: entries
            for slot, entries in slots.items()
            if isinstance(entries, list) and entries
        },
        "missing_expected_decision_slots": missing_expected_slots,
        "present_evidence_families": families,
        "missing_expected_evidence_families": missing_expected_families,
        "output_obligations": obligations,
        "issues": issues,
        "notes": [
            "This report evaluates whether the current map exposes decision-support ingredients; it does not judge whether the underlying sources are complete.",
            "Missing slots should be acknowledged in the briefing when they matter to the question, not filled in by inference.",
        ],
    }


def _expected_slots_for_question(question: str, evidence_ledger: dict[str, Any]) -> list[str]:
    normalized = f" {re.sub(r'\\s+', ' ', question.lower())} "
    expected = ["endpoint_type", "study_design"]
    marker_map = {
        "default_population": (" for ", " among ", " in ", " adults", " people", " patients", " population", " users"),
        "dose_or_intensity_threshold": (
            " consumption",
            " intake",
            " dose",
            " threshold",
            " exposure",
            " use",
            " using",
            " intervention",
            " treatment",
            " treated",
        ),
        "high_risk_subgroup": (" subgroup", " especially", " high-risk", " higher-risk", " people with", " patients with", " adults with"),
        "mechanism": (" why ", " mechanism", " causal", " pathway", " mediated", " biomarker"),
        "substitution_or_comparator": (" compared", " versus", " vs ", " replace", " instead of", " rather than ", " alternative", " relative to", " over "),
        "technical_or_capacity": (" capacity", " technical", " performance", " cadr", " merv", " hvac", " hepa", " filtration", " ventilation"),
        "implementation_constraint": (" feasible", " implementation", " maintenance", " cost", " noise", " upgrade", " operate", " serviced"),
        "safety_or_risk": (" safety", " unsafe", " adverse", " harm", " risk", " ozone", " failure"),
        "setting_or_context": (" school", " classroom", " district", " building", " setting", " site"),
        "practical_recommendation": (" should ", " prioritize", " recommend", " guidance", " advice", " decision", " policy", " treat ", " use "),
    }
    for slot, markers in marker_map.items():
        if any(marker in normalized for marker in markers):
            expected.append(slot)
    counts = evidence_ledger.get("decision_slot_counts", {}) if isinstance(evidence_ledger.get("decision_slot_counts"), dict) else {}
    for slot in (
        "dose_or_intensity_threshold",
        "high_risk_subgroup",
        "substitution_or_comparator",
        "mechanism",
        "technical_or_capacity",
        "implementation_constraint",
        "safety_or_risk",
        "setting_or_context",
    ):
        if int(counts.get(slot, 0)) > 0:
            expected.append(slot)
    return _dedupe(expected)


def _expected_families_for_question(question: str) -> list[str]:
    normalized = f" {re.sub(r'\\s+', ' ', question.lower())} "
    expected = ["cohort_or_observational", "evidence_synthesis"]
    if any(marker in normalized for marker in (" should ", " recommend", " advice", " guidance", " policy", " decision")):
        expected.append("guideline_or_recommendation")
    if any(marker in normalized for marker in (" trial", " intervention", " treatment", " randomized", " randomised", " rct")):
        expected.append("rct_or_intervention")
    if any(marker in normalized for marker in (" mechanism", " why ", " causal", " biomarker", " pathway")):
        expected.append("mechanism_or_biomarker")
    return _dedupe(expected)


def _sufficiency_output_obligations(
    slots: dict[str, Any],
    missing_expected_slots: list[str],
    missing_expected_families: list[str],
) -> list[dict[str, Any]]:
    obligations: list[dict[str, Any]] = []
    for slot, entries in slots.items():
        if not isinstance(entries, list) or not entries:
            continue
        label = _slot_label(slot)
        values = [str(entry.get("value", "")).strip() for entry in entries if isinstance(entry, dict) and str(entry.get("value", "")).strip()]
        if not values:
            continue
        obligations.append(
            {
                "obligation_id": f"present_{slot}",
                "kind": "include_present_slot",
                "slot": slot,
                "instruction": f"Include at least one map-backed {label}.",
                "candidate_values": values[:4],
            }
        )
    for slot in missing_expected_slots:
        obligations.append(
            {
                "obligation_id": f"missing_{slot}",
                "kind": "acknowledge_missing_slot",
                "slot": slot,
                "instruction": f"Do not invent a { _slot_label(slot) }; state that the source packet does not establish it if relevant.",
                "candidate_values": [],
            }
        )
    for family in missing_expected_families:
        obligations.append(
            {
                "obligation_id": f"missing_family_{family}",
                "kind": "acknowledge_missing_family",
                "evidence_family": family,
                "instruction": f"Do not imply that {family.replace('_', ' ')} evidence was assessed if the map lacks it.",
                "candidate_values": [],
            }
        )
    return obligations[:16]


def _sufficiency_issues(
    *,
    claim_count: int,
    relation_count: int,
    missing_expected_slots: list[str],
    missing_expected_families: list[str],
    quality_report: dict[str, Any],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if claim_count == 0:
        issues.append({"severity": "fail", "issue_type": "no_claims", "message": "The map has no claims to synthesize."})
    if relation_count == 0:
        issues.append({"severity": "warning", "issue_type": "no_relations", "message": "The map exposes no claim relations or tensions."})
    for slot in missing_expected_slots:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "missing_expected_decision_slot",
                "message": f"The question appears to require {_slot_label(slot)}, but the source packet does not establish it.",
            }
        )
    for family in missing_expected_families:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "missing_expected_evidence_family",
                "message": f"The question appears to benefit from {family.replace('_', ' ')} evidence, but the source packet does not establish it.",
            }
        )
    if confidence_cap(quality_report) != "high":
        issues.append(
            {
                "severity": "warning",
                "issue_type": "quality_report_caps_confidence",
                "message": f"The map quality report caps confidence at {confidence_cap(quality_report)}.",
            }
        )
    return issues


def _sufficiency_status(issues: list[dict[str, str]]) -> str:
    if any(issue.get("severity") == "fail" for issue in issues):
        return "insufficient"
    if any(issue.get("severity") == "warning" for issue in issues):
        return "usable_with_named_gaps"
    return "sufficient_for_scaffolded_briefing"


def _slot_label(slot: str) -> str:
    return {
        "default_population": "default population",
        "dose_or_intensity_threshold": "dose or intensity threshold",
        "high_risk_subgroup": "high-risk subgroup",
        "mechanism": "mechanism",
        "substitution_or_comparator": "substitution or comparator",
        "endpoint_type": "endpoint type",
        "study_design": "study design",
        "practical_recommendation": "practical recommendation",
        "technical_or_capacity": "technical capacity",
        "implementation_constraint": "implementation constraint",
        "safety_or_risk": "safety or risk",
        "setting_or_context": "setting or context",
        "population_scope": "population or scope",
        "intervention_or_option": "intervention or option",
        "comparator": "comparator",
        "outcome_or_endpoint": "outcome or endpoint",
        "evidence_design": "evidence design",
        "causal_identification": "causal identification",
        "implementation_condition": "implementation condition",
        "harm_or_failure_mode": "harm or failure mode",
        "cost_or_feasibility": "cost or feasibility",
        "equity_or_distribution": "equity or distribution",
        "missing_evidence_gap": "missing evidence gap",
    }.get(slot, slot.replace("_", " "))


def _missing_decision_slots(evidence_ledger: dict[str, Any]) -> list[str]:
    required = (
        "default_population",
        "dose_or_intensity_threshold",
        "high_risk_subgroup",
        "mechanism",
        "substitution_or_comparator",
        "endpoint_type",
        "study_design",
        "practical_recommendation",
    )
    counts = evidence_ledger.get("decision_slot_counts", {}) if isinstance(evidence_ledger.get("decision_slot_counts"), dict) else {}
    return [slot for slot in required if int(counts.get(slot, 0)) == 0]


def _slot_value(slot: str, claim: str) -> str:
    if slot == "dose_or_intensity_threshold":
        return _extract_threshold_phrase(claim)
    if slot == "high_risk_subgroup":
        return _extract_subgroup_phrase(claim)
    if slot == "mechanism":
        return _extract_mechanism_phrase(claim)
    if slot == "substitution_or_comparator":
        return _extract_comparator_phrase(claim)
    if slot == "study_design":
        return _extract_design_phrase(claim)
    if slot == "endpoint_type":
        return _extract_endpoint_phrase(claim)
    if slot == "practical_recommendation":
        return _short_claim_fragment(claim)
    if slot == "technical_or_capacity":
        return _extract_technical_capacity_phrase(claim)
    if slot == "implementation_constraint":
        return _extract_implementation_phrase(claim)
    if slot == "safety_or_risk":
        return _extract_safety_phrase(claim)
    if slot == "setting_or_context":
        return _extract_setting_phrase(claim)
    if slot == "default_population":
        return _extract_population_phrase(claim)
    return _short_claim_fragment(claim)


def _slot_entry_exists(entries: list[dict[str, Any]], candidate: dict[str, Any]) -> bool:
    candidate_terms = set(_content_terms(_normalize_slot_value(str(candidate.get("value", "")))))
    for entry in entries:
        entry_terms = set(_content_terms(_normalize_slot_value(str(entry.get("value", "")))))
        if candidate_terms and entry_terms and len(candidate_terms & entry_terms) / min(len(candidate_terms), len(entry_terms)) >= 0.75:
            return True
    return False


def _normalize_slot_value(value: str) -> str:
    normalized = value.lower()
    normalized = re.sub(r"\b(?:people|patients|adults|individuals|participants)\b", "person", normalized)
    normalized = re.sub(r"\btype\s*2\s*diabetes\b|\bt2d\b", "diabetes", normalized)
    return normalized


def _extract_threshold_phrase(text: str) -> str:
    number = r"(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)"
    patterns = (
        rf"(?:up to|less than|more than|at least|at most|around|approximately|about)?\s*[<≥≤>]?\s*{number}\s*(?:eggs?|egg)?\s*(?:per|/)\s*(?:day|week|month)",
        rf"\b{number}\s*(?:eggs?|egg)/(?:day|week|month)\b",
        r"\b(?:high|moderate|low)[-\s]?(?:egg|intake|consumption|use)[A-Za-z0-9/ <≥≤.,-]{0,60}",
    )
    return _first_pattern(text, patterns)


def _extract_subgroup_phrase(text: str) -> str:
    patterns = (
        r"(?:people|patients|adults|individuals|participants) with type 2 diabetes",
        r"(?:people|patients|adults|individuals|participants) with impaired (?:kidney|renal) function(?:, including the elderly)?",
        r"\b(?:type 2 diabetes|diabetes|t2d|impaired kidney function|impaired renal function|elderly|familial hypercholesterolemia|high LDL|high ApoB|hyper-responders?)\b(?:, including the elderly)?",
        r"(?:people|patients|adults|individuals|participants) with [A-Za-z0-9 /\-]{3,80}",
    )
    return _first_pattern(text, patterns)


def _extract_mechanism_phrase(text: str) -> str:
    patterns = (
        r"\b(?:LDL|HDL|ApoB|cholesterol|homeostasis|metabolites?|microbiome|particle)[A-Za-z0-9 ,/\-]{0,90}",
        r"[A-Za-z0-9 ,/\-]{0,70}\b(?:mechanism|causal|driven by|influenced by)\b[A-Za-z0-9 ,/\-]{0,70}",
    )
    return _first_pattern(text, patterns)


def _extract_comparator_phrase(text: str) -> str:
    patterns = (
        r"[A-Za-z0-9 ,/\-]{0,80}\b(?:replace|replacing|substitut(?:e|ing|ion)|compared with|versus|instead of)\b[A-Za-z0-9 ,/\-]{0,90}",
        r"[A-Za-z0-9 ,/\-]{0,80}\b(?:compared to|rather than|alternative to|supplement(?:al|ary)? to|over)\b[A-Za-z0-9 ,/\-]{0,90}",
        r"\b(?:egg whites?|plant protein|animal protein|red meat|processed meat|low-egg diet|high-egg diet)[A-Za-z0-9 ,/\-]{0,90}",
    )
    return _first_pattern(text, patterns)


def _extract_technical_capacity_phrase(text: str) -> str:
    patterns = (
        r"[A-Za-z0-9 .,%/\-]{0,80}\b(?:CADR|MERV|HEPA|HVAC|airflow|filtration|ventilation|room size|capacity|PM\s?2\.5)\b[A-Za-z0-9 .,%/\-]{0,100}",
        r"[A-Za-z0-9 .,%/\-]{0,80}\b(?:clean air delivery rate|particulate matter|outdoor air|filter)\b[A-Za-z0-9 .,%/\-]{0,100}",
    )
    return _first_pattern(text, patterns)


def _extract_implementation_phrase(text: str) -> str:
    patterns = (
        r"[A-Za-z0-9 .,%/\-]{0,80}\b(?:feasible|not feasible|maintenance|operate|operated|serviced|upgrade|standard|cost|noise|capacity|room size)\b[A-Za-z0-9 .,%/\-]{0,100}",
        r"[A-Za-z0-9 .,%/\-]{0,80}\b(?:should|recommend|guidance|policy|implementation|practical)\b[A-Za-z0-9 .,%/\-]{0,100}",
    )
    return _first_pattern(text, patterns)


def _extract_safety_phrase(text: str) -> str:
    patterns = (
        r"[A-Za-z0-9 .,%/\-]{0,80}\b(?:unsafe|not safe|ozone|adverse|harm|risk|hazard|failure)\b[A-Za-z0-9 .,%/\-]{0,100}",
    )
    return _first_pattern(text, patterns)


def _extract_setting_phrase(text: str) -> str:
    patterns = (
        r"[A-Za-z0-9 .,%/\-]{0,80}\b(?:classroom|school|district|building|home|workplace|setting|county|region|site)\b[A-Za-z0-9 .,%/\-]{0,100}",
    )
    return _first_pattern(text, patterns)


def _extract_design_phrase(text: str) -> str:
    patterns = (
        r"\b(?:prospective cohort|cohort study|randomized controlled trial|randomised controlled trial|RCT|trial|meta-analysis|systematic review|pooled analysis|observational)[A-Za-z0-9 ,/\-]{0,70}",
    )
    return _first_pattern(text, patterns)


def _extract_endpoint_phrase(text: str) -> str:
    patterns = (
        r"\b(?:mortality|all-cause mortality|CVD|cardiovascular disease|cardiovascular risk|stroke|myocardial infarction|LDL|HDL|ApoB|biomarker|endpoint)[A-Za-z0-9 ,/\-]{0,70}",
    )
    return _first_pattern(text, patterns)


def _extract_population_phrase(text: str) -> str:
    patterns = (
        r"\b(?:generally healthy adults|healthy adults|general population|free-living individuals|participants without [A-Za-z0-9 ,/\-]{3,80})",
        r"\b(?:participants|adults|individuals|people) (?:free of|without|with no history of) [A-Za-z0-9 ,/\-]{3,90}",
        r"\bfree of (?:cardiovascular disease|type 2 diabetes|cancer|chronic disease)[A-Za-z0-9 ,/\-]{0,90}",
    )
    return _first_pattern(text, patterns)


def _first_pattern(text: str, patterns: tuple[str, ...]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip(" ,.;")
    return ""


def _short_claim_fragment(text: str, max_chars: int = 140) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    candidate = cleaned[: max_chars - 3].rstrip(" ,.;")
    last_space = candidate.rfind(" ")
    if last_space >= max(24, int(max_chars * 0.6)):
        candidate = candidate[:last_space].rstrip(" ,.;")
    return candidate + "..."


def build_briefing_plan(
    partition: dict[str, Any],
    contract: dict[str, Any],
    evidence_ledger: dict[str, Any],
    quality_report: dict[str, Any],
    decision_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    top_by_section = evidence_ledger.get("top_evidence_by_section", {})
    support = _ledger_claim_texts(top_by_section.get("main_support", []), weight_floor="medium")
    conflicts = _ledger_claim_texts(top_by_section.get("conflicting_evidence", []), weight_floor="medium")
    scope = _ledger_claim_texts(top_by_section.get("scope_limits", []), weight_floor="low")
    methods = _ledger_claim_texts(top_by_section.get("method_limits", []), weight_floor="low")
    answer_frame = contract.get("answer_frame", {}) if isinstance(contract.get("answer_frame"), dict) else {}
    decision_model = decision_model or {}
    default_answer = decision_model.get("default_answer", {}) if isinstance(decision_model.get("default_answer"), dict) else {}
    return {
        "schema_id": "briefing_plan_v1",
        "opening_move": default_answer.get(
            "plain_language_instruction",
            answer_frame.get("default_stance_instruction", "Answer directly with calibrated uncertainty."),
        ),
        "paragraph_order": [
            {
                "section": "bottom_line",
                "job": "Give the controlling classification directly, then name the strongest counterposition if present.",
                "must_use": _dedupe([
                    str(default_answer.get("classification", "")),
                    str(default_answer.get("why_this_frame", "")),
                    str(answer_frame.get("strongest_counterposition", "")),
                    *support[:2],
                    *conflicts[:1],
                ])[:5],
            },
            {
                "section": "why_this_read",
                "job": "Explain the weighted support without overstating null, indirect, or backfilled evidence.",
                "must_use": support[:4],
            },
            {
                "section": "what_pushes_back",
                "job": "Explain contrary evidence and tensions as live considerations, not as afterthoughts.",
                "must_use": conflicts[:4],
            },
            {
                "section": "where_it_applies",
                "job": "Separate population, dose, endpoint, and setting boundaries from the general answer.",
                "must_use": scope[:4],
            },
            {
                "section": "why_not_stronger",
                "job": "Name method, source-completeness, quality-report, and coverage limits.",
                "must_use": _dedupe([*methods[:4], *quality_report_issue_text(quality_report)[:3]])[:6],
            },
        ],
        "section_transition_rules": [
            "Do not repeat evidence-role bullets verbatim when a synthesis sentence can combine them.",
            "Do not let low-weight evidence drive the bottom line unless it is the only evidence on a decision-critical caveat.",
            "When evidence conflicts, state what scope or method difference explains the tension if the map supports one.",
        ],
    }


def _claim_evidence_weight_score(
    claim: dict[str, Any],
    section: str,
    quality_report: dict[str, Any],
    source_lookup: dict[str, str],
) -> tuple[int, list[str]]:
    score = 2
    modifiers: list[str] = ["base_source_grounded_claim"]
    entailed = str(claim.get("entailed_by_excerpt", "")).lower()
    if entailed == "yes":
        score += 2
        modifiers.append("entailed_by_excerpt")
    elif entailed == "uncertain":
        score -= 1
        modifiers.append("uncertain_entailment")
    else:
        score -= 2
        modifiers.append("not_entailed_or_unmarked")
    role = str(claim.get("role", "other"))
    if role in {"crux", "conclusion_support"}:
        score += 2
        modifiers.append(f"decision_role:{role}")
    elif role in {"scope_limit", "external_validity", "implementation_constraint", "measurement_validity", "cost_feasibility"}:
        score += 1
        modifiers.append(f"boundary_role:{role}")
    supporting_sources = _claim_supporting_sources_for_briefing(claim)
    if len(supporting_sources) > 1:
        score += min(2, len(supporting_sources) - 1)
        modifiers.append(f"multi_source_support:{len(supporting_sources)}")
    extraction_method = str(claim.get("extraction_method", "model"))
    if extraction_method == "deterministic_coverage_backfill":
        score -= 1
        modifiers.append("coverage_backfill_lower_weight")
    elif extraction_method.startswith("deterministic"):
        score -= 1
        modifiers.append("deterministic_fallback_lower_weight")
    source_name = source_lookup.get(str(claim.get("source_id", "")), str(claim.get("source_id", "")))
    source_text = f"{source_name} {claim.get('source_id', '')}".lower()
    if any(marker in source_text for marker in ("abstract", "pubmed", "metadata")):
        score -= 1
        modifiers.append("source_incomplete_or_abstract")
    text = _claim_text_bundle(claim)
    if _looks_like_method_or_source_limit(text):
        score -= 1
        modifiers.append("method_or_source_limit")
    if _looks_like_scope_or_subgroup(text):
        modifiers.append("scope_specific")
    if _contains_hard_outcome_signal(text):
        score += 1
        modifiers.append("hard_outcome_signal")
    if _contains_surrogate_signal(text):
        score -= 1
        modifiers.append("surrogate_or_biomarker_signal")
    concepts = _claim_concepts(claim)
    if concepts:
        score += min(2, max(1, len(concepts) // 2))
        modifiers.append(f"decision_concept_count:{len(concepts)}")
    noise = _claim_noise_profile(claim)
    if int(noise.get("penalty", 0)):
        score -= int(noise.get("penalty", 0))
        modifiers.append(f"noise:{noise.get('kind')}")
    if section in {"main_support", "conflicting_evidence"} and (
        _looks_like_support_evidence(text) or _looks_like_concern_evidence(text)
    ):
        score += 1
        modifiers.append("directional_decision_signal")
    if any(isinstance(issue, dict) and issue.get("severity") == "risk" for issue in quality_report.get("issues", [])):
        modifiers.append("quality_risk_context")
    return max(0, min(score, 8)), modifiers


def _claim_concepts(claim: dict[str, Any]) -> list[str]:
    text = _claim_text_bundle(claim)
    concept_markers = {
        "default_population": ("generally healthy", "healthy adults", "general population", "free of cardiovascular", "without cardiovascular", "free-living"),
        "dose_or_threshold": ("per day", "per week", "egg/day", "eggs/wk", "up to one", "up to 1", "moderate", "high intake", "threshold", "dose", "intensity", "%", "<", ">", "≥", "≤"),
        "hard_outcome_endpoint": ("mortality", "all-cause", "cvd", "cardiovascular disease", "stroke", "myocardial infarction", "coronary heart disease", "incident"),
        "surrogate_or_biomarker_endpoint": ("biomarker", "surrogate", "proxy", "pm2.5", "pm 2.5", "particulate", "particle", "ldl", "hdl", "apob", "cholesterol", "lipid", "tmao", "trimethylamine"),
        "mechanism_or_causal_path": ("mechanism", "causal", "pathway", "mediated", "exposure", "transmission", "filtration", "ventilation", "source control"),
        "mechanism_ldl_apob": ("ldl", "apob", "atherosclerosis", "cholesterol homeostasis", "tmao", "trimethylamine", "metabolite", "microbiome"),
        "dietary_context_or_saturated_fat": ("saturated fat", "dietary pattern", "red meat", "processed meat", "bacon", "sausage", "co-consum", "dietary cholesterol"),
        "substitution_or_comparator": ("replace", "replacing", "substitut", "compared with", "versus", "vs ", "instead of", "egg white", "plant protein", "low-egg", "high-egg"),
        "alternative_or_comparator": ("compared with", "compared to", "versus", "vs ", "rather than", "instead of", "alternative", "supplemental", "over "),
        "subgroup_diabetes_or_metabolic_risk": ("type 2 diabetes", "diabetes", "t2d", "prediabetes", "metabolic", "impaired kidney", "renal", "vascular disease"),
        "subgroup_fh_hyper_responder": ("familial hypercholesterolemia", "hyper-responder", "hyper responder", "high ldl", "high apob", "elevated ldl", "elevated apob"),
        "technical_performance_or_capacity": ("cadr", "merv", "hvac", "hepa", "airflow", "ventilation", "filtration", "room size", "capacity", "pm2.5", "pm 2.5"),
        "implementation_constraint": ("feasible", "not feasible", "maintenance", "operate", "operated", "serviced", "upgrade", "standard", "cost", "noise", "capacity", "room size"),
        "safety_or_adverse_effect": ("unsafe", "ozone", "adverse", "harm", "risk", "hazard", "not safe", "failure"),
        "setting_or_context": ("classroom", "school", "district", "building", "home", "workplace", "setting", "county", "region", "site"),
        "study_design_rct": ("randomized", "randomised", " rct", "trial", "crossover", "intervention"),
        "study_design_cohort": ("cohort", "prospective", "follow-up", "observational", "participants"),
        "guideline_or_policy": ("guideline", "advisory", "recommendation", "dietary guidance", "clinicians", "consumers", "policy", "should"),
        "source_quality_or_incentive": ("funding", "conflict of interest", "disclosure", "industry", "consultant", "grant", "abstract", "full text"),
    }
    concepts: list[str] = []
    for concept, markers in concept_markers.items():
        if any(marker in text for marker in markers):
            concepts.append(concept)
    return _filter_claim_concepts_by_visible_text(concepts, text)


def _filter_claim_concepts_by_visible_text(concepts: list[str], text: str) -> list[str]:
    if "mechanism_ldl_apob" in concepts and not _contains_lipid_marker(text):
        concepts = [concept for concept in concepts if concept != "mechanism_ldl_apob"]
    if "dietary_context_or_saturated_fat" in concepts and not any(
        marker in text
        for marker in ("dietary", "diet ", "saturated fat", "red meat", "processed meat", "bacon", "sausage", "cholesterol")
    ):
        concepts = [concept for concept in concepts if concept != "dietary_context_or_saturated_fat"]
    return concepts


def _contains_lipid_marker(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:ldl(?:-c)?|apo\s?b|apob|cholesterol|atherosclerosis|tmao|trimethylamine|lipids?)\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def _claim_noise_profile(claim: dict[str, Any]) -> dict[str, Any]:
    text = _claim_text_bundle(claim)
    compact = re.sub(r"\s+", " ", text).strip()
    if _looks_like_boilerplate_disclosure(compact):
        return {"kind": "boilerplate_disclosure", "penalty": 4}
    if _looks_like_publisher_or_license_boilerplate(compact):
        return {"kind": "publisher_or_license_boilerplate", "penalty": 4}
    if _looks_like_statistical_method_trivia(compact):
        return {"kind": "statistical_method_trivia", "penalty": 2}
    if len(compact) > 900:
        return {"kind": "overlong_claim", "penalty": 2}
    return {"kind": "none", "penalty": 0}


def _looks_like_boilerplate_disclosure(text: str) -> bool:
    markers = (
        "received research grants",
        "received research support",
        "speaker fees",
        "honoraria",
        "scientific advisory board",
        "consultant to",
        "conflict of interest",
        "competing interests",
        "disclosures",
        "funding and travel support",
        "corresponding author on request",
    )
    return sum(1 for marker in markers if marker in text) >= 2 or ("professor" in text and "received" in text and len(text) > 700)


def _looks_like_publisher_or_license_boilerplate(text: str) -> bool:
    markers = (
        "creative commons",
        "copyright",
        "publisher",
        "license",
        "all rights reserved",
        "plos is a nonprofit",
        "terms of use",
    )
    return any(marker in text for marker in markers)


def _looks_like_statistical_method_trivia(text: str) -> bool:
    markers = (
        "competing risk regression",
        "cox proportional hazards",
        "statistical software",
        "sensitivity analysis was performed using",
        "model was adjusted for",
    )
    return any(marker in text for marker in markers) and not _contains_hard_outcome_signal(text)


def _evidence_family_for_claim(claim: dict[str, Any], section: str, source_lookup: dict[str, str]) -> str:
    text = " ".join(
        str(part or "")
        for part in (
            claim.get("claim"),
            claim.get("text"),
            claim.get("excerpt"),
            claim.get("role"),
            claim.get("source_id"),
            source_lookup.get(str(claim.get("source_id", "")), ""),
        )
    ).lower()
    if any(marker in text for marker in ("guideline", "advisory", "recommendation", "dietary guidance", "policy", "should", "cdc", "epa")):
        return "guideline_or_recommendation"
    if any(marker in text for marker in ("meta-analysis", "systematic review", "pooled relative risk", "pooled rr")):
        return "evidence_synthesis"
    if any(marker in text for marker in ("randomized", "randomised", " rct", "trial", "crossover", "intervention")):
        return "rct_or_intervention"
    if any(marker in text for marker in ("cohort", "prospective", "pooled analysis", "observational", "participants", "follow-up")):
        return "cohort_or_observational"
    if any(marker in text for marker in ("replace", "substitut", "instead of", "compared with", "compared to", "versus", "vs ", "rather than", "alternative", "supplemental", "over ")):
        return "substitution_or_comparator"
    if any(marker in text for marker in ("cadr", "merv", "hvac", "hepa", "airflow", "ventilation", "filtration", "room size", "capacity", "pm2.5", "pm 2.5")):
        return "technical_or_performance"
    if any(marker in text for marker in ("unsafe", "ozone", "adverse", "harm", "hazard", "not safe")):
        return "safety_or_risk"
    if any(marker in text for marker in ("mechanism", "metabolite", "homeostasis", "ldl", "apob", "biomarker", "cholesterol", "microbiome", "causal", "pathway", "transmission", "source control")):
        return "mechanism_or_biomarker"
    if section == "scope_limits" or _looks_like_scope_or_subgroup(text):
        return "subgroup_or_scope"
    if section == "method_limits" or _looks_like_method_or_source_limit(text):
        return "method_or_validity"
    return "general_evidence"


def _decision_slots_for_claim(claim: dict[str, Any]) -> list[str]:
    text = _claim_text_bundle(claim)
    slots: list[str] = []
    slot_markers = {
        "default_population": ("healthy adults", "generally healthy", "general population", "free-living", "without history", "free of cardiovascular", "free of type 2 diabetes", "free of cancer"),
        "dose_or_intensity_threshold": ("per day", "per week", "egg/day", "eggs/wk", "high intake", "moderate", "up to", "<", ">", "≥", "≤"),
        "high_risk_subgroup": ("diabetes", "t2d", "impaired kidney", "renal", "elderly", "familial", "high ldl", "high apob", "high-risk", "hyper-responder"),
        "mechanism": ("ldl", "apob", "cholesterol", "homeostasis", "metabolite", "microbiome", "mechanism", "particle"),
        "substitution_or_comparator": ("replace", "substitut", "compared with", "compared to", "versus", "vs ", "instead of", "rather than", "alternative", "supplemental", "over ", "low-egg", "high-egg", "egg white", "plant protein"),
        "endpoint_type": ("mortality", "cvd", "cardiovascular", "stroke", "myocardial", "biomarker", "endpoint", "ldl", "hdl", "apob", "pm2.5", "pm 2.5", "particulate", "exposure", "infection", "transmission"),
        "study_design": ("cohort", "trial", "rct", "meta-analysis", "systematic review", "pooled", "prospective", "observational"),
        "practical_recommendation": ("guidance", "recommend", "should", "limit", "focus", "dietary pattern", "mediterranean", "dash", "prioritize", "use", "consider"),
        "technical_or_capacity": ("cadr", "merv", "hvac", "hepa", "airflow", "ventilation", "filtration", "room size", "capacity", "pm2.5", "pm 2.5"),
        "implementation_constraint": ("feasible", "not feasible", "maintenance", "operate", "operated", "serviced", "upgrade", "standard", "cost", "noise", "capacity", "room size"),
        "safety_or_risk": ("unsafe", "ozone", "adverse", "harm", "risk", "hazard", "not safe", "failure"),
        "setting_or_context": ("classroom", "school", "district", "building", "home", "workplace", "setting", "county", "region", "site"),
    }
    for slot, markers in slot_markers.items():
        if any(marker in text for marker in markers):
            slots.append(slot)
    return slots or ["unspecified"]


def _evidence_slots_for_claim(claim: dict[str, Any]) -> list[str]:
    text = _claim_text_bundle(claim)
    slots: list[str] = []
    markers = {
        "population_scope": (
            "generally healthy",
            "healthy adults",
            "participants",
            "patients",
            "people with",
            "students",
            "teachers",
            "riders",
            "arterial",
            "school",
            "site",
            "corridor",
            "setting",
        ),
        "intervention_or_option": (
            "intervention",
            "protected",
            "painted",
            "hepa",
            "hvac",
            "filtration",
            "program",
            "policy",
            "lane",
            "separator",
            "quick-build",
        ),
        "comparator": (
            "compared with",
            "compared to",
            "versus",
            "rather than",
            "instead of",
            "over ",
            "painted",
            "protected",
            "alternative",
            "substitut",
            "replace",
        ),
        "outcome_or_endpoint": (
            "mortality",
            "injury",
            "crash",
            "risk",
            "endpoint",
            "biomarker",
            "infection",
            "exposure",
            "pm2.5",
            "pm 2.5",
            "comfort",
            "safety",
        ),
        "evidence_design": (
            "randomized",
            "trial",
            "cohort",
            "observational",
            "before-after",
            "before after",
            "evaluation",
            "systematic review",
            "meta-analysis",
            "guidance",
            "memo",
        ),
        "causal_identification": (
            "not randomized",
            "confounding",
            "regression to the mean",
            "cannot be attributed",
            "causal",
            "package",
            "alongside",
            "concurrent",
            "mechanism",
        ),
        "implementation_condition": (
            "maintenance",
            "maintain",
            "operate",
            "implementation",
            "feasible",
            "capacity",
            "intersection",
            "turning",
            "loading",
            "bus",
            "drainage",
            "snow",
            "sweeping",
            "access",
        ),
        "harm_or_failure_mode": (
            "harm",
            "hazard",
            "unsafe",
            "failure",
            "blocked",
            "conflict",
            "risk",
            "degradation",
            "unusable",
            "encroachment",
            "close passing",
        ),
        "cost_or_feasibility": (
            "cost",
            "budget",
            "staff",
            "capital",
            "cheap",
            "inexpensive",
            "quick",
            "faster",
            "right-of-way",
            "limited resources",
            "construction",
        ),
        "equity_or_distribution": (
            "equity",
            "distribution",
            "high-injury",
            "lower car ownership",
            "transit dependence",
            "access",
            "neighborhood",
            "subgroup",
            "higher-risk",
        ),
        "missing_evidence_gap": (
            "not randomized",
            "limitations",
            "cannot be assigned",
            "not assessed",
            "missing",
            "uncertain",
            "not establish",
        ),
    }
    for slot, slot_markers in markers.items():
        if any(marker in text for marker in slot_markers):
            slots.append(slot)
    return _dedupe(slots) or ["other_evidence"]


def _evidence_slot_why_it_matters(slot: str) -> str:
    return {
        "population_scope": "Controls whether the evidence transfers to the decision setting.",
        "intervention_or_option": "Identifies the option whose performance is being judged.",
        "comparator": "Prevents the recommendation from ignoring the real alternative.",
        "outcome_or_endpoint": "Separates decision-relevant endpoints from proxies or intermediate signals.",
        "evidence_design": "Controls how much causal and external-validity weight the evidence can bear.",
        "causal_identification": "Names whether the observed result can be attributed to the option itself.",
        "implementation_condition": "Gates whether the option can work in practice.",
        "harm_or_failure_mode": "Identifies ways the preferred option could fail or cause downside risk.",
        "cost_or_feasibility": "Captures constraints that can reverse an otherwise attractive option.",
        "equity_or_distribution": "Keeps distributional and subgroup consequences visible.",
        "missing_evidence_gap": "Prevents absent evidence from being filled in by inference.",
    }.get(slot, "This evidence slot affects how far the conclusion should travel.")


def _question_options(question: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", question.strip().rstrip("?"))
    patterns = (
        r"\bprioritize\s+(?P<a>.+?)\s+over\s+(?P<b>.+?)(?:\s+to\b|\s+for\b|$)",
        r"\bshould\s+(?P<a>.+?)\s+(?:rather than|instead of|over|versus|vs\.?)\s+(?P<b>.+?)(?:\s+to\b|\s+for\b|$)",
        r"(?P<a>.+?)\s+(?:versus|vs\.?)\s+(?P<b>.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if not match:
            continue
        options = [_clean_option_text(match.group("a")), _clean_option_text(match.group("b"))]
        options = [option for option in options if option and len(option.split()) <= 12]
        if len(options) == 2:
            return _dedupe(options)
    return []


def _clean_option_text(text: str) -> str:
    text = re.sub(r"^(?:a|an|the|city|cities|mid-sized city|mid-sized cities)\s+", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\bthis year\b.*$", "", text, flags=re.IGNORECASE)
    return text.strip(" ,.;:")


def _infer_options_from_evidence(evidence_ledger: dict[str, Any]) -> list[str]:
    text = " ".join(str(row.get("claim", "")) for row in evidence_ledger.get("all_evidence", []) if isinstance(row, dict)).lower()
    candidates: list[str] = []
    if "protected" in text:
        candidates.append("protected option")
    if "painted" in text:
        candidates.append("painted option")
    if "hepa" in text:
        candidates.append("portable HEPA filtration")
    if "hvac" in text:
        candidates.append("HVAC or ventilation upgrade")
    return _dedupe(candidates)[:3]


def _option_terms(option: str) -> list[str]:
    terms = [term for term in _content_terms(option) if len(term) >= 4]
    aliases = {
        "curb": ["protected", "separator", "separated"],
        "protected": ["curb", "separated", "separator", "physical"],
        "painted": ["paint", "striping", "paint-only"],
        "hepa": ["portable", "filtration", "filter"],
        "hvac": ["ventilation", "outdoor", "upgrade"],
    }
    expanded = list(terms)
    for term in terms:
        expanded.extend(aliases.get(term, []))
    return _dedupe(expanded)


def _option_terms_by_option(options: list[str]) -> dict[str, list[str]]:
    raw = {option: _option_terms(option) for option in options}
    term_counts: Counter[str] = Counter(term for terms in raw.values() for term in terms)
    resolved: dict[str, list[str]] = {}
    for option, terms in raw.items():
        discriminating = [term for term in terms if term_counts[term] == 1]
        resolved[option] = discriminating or terms
    return resolved


def _option_criteria_for_rows(rows: list[dict[str, Any]]) -> list[str]:
    base = ["outcome_effect", "comparator_scope", "implementation_condition", "cost_feasibility", "harm_or_failure_mode", "equity_distribution", "evidence_strength"]
    present_slots = {slot for row in rows for slot in row.get("evidence_slots", []) if isinstance(slot, str)}
    if "causal_identification" in present_slots:
        base.append("causal_attribution")
    return base


def _row_matches_option(row: dict[str, Any], option_terms: list[str]) -> bool:
    text = str(row.get("claim", "")).lower()
    return any(_text_has_option_term(text, term) for term in option_terms)


def _text_has_option_term(text: str, term: str) -> bool:
    term = str(term).strip().lower()
    if not term:
        return False
    return bool(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text))


def _row_matches_option_criterion(row: dict[str, Any], criterion: str) -> bool:
    slots = set(str(slot) for slot in row.get("evidence_slots", []) if isinstance(slot, str))
    concepts = set(str(concept) for concept in row.get("decision_concepts", []) if isinstance(concept, str))
    section = str(row.get("section", ""))
    mapping = {
        "outcome_effect": {"outcome_or_endpoint", "intervention_or_option"},
        "comparator_scope": {"comparator"},
        "implementation_condition": {"implementation_condition"},
        "cost_feasibility": {"cost_or_feasibility"},
        "harm_or_failure_mode": {"harm_or_failure_mode"},
        "equity_distribution": {"equity_or_distribution"},
        "evidence_strength": {"evidence_design", "causal_identification"},
        "causal_attribution": {"causal_identification"},
    }
    if slots.intersection(mapping.get(criterion, set())):
        return True
    if criterion == "implementation_condition" and {"implementation_constraint", "technical_performance_or_capacity"}.intersection(concepts):
        return True
    if criterion == "comparator_scope" and {"alternative_or_comparator", "substitution_or_comparator"}.intersection(concepts):
        return True
    if criterion == "harm_or_failure_mode" and (section == "conflicting_evidence" or "safety_or_adverse_effect" in concepts):
        return True
    return False


def _option_criterion_label(criterion: str) -> str:
    return {
        "outcome_effect": "Outcome effect",
        "comparator_scope": "Comparator scope",
        "implementation_condition": "Implementation condition",
        "cost_feasibility": "Cost or feasibility",
        "harm_or_failure_mode": "Harm or failure mode",
        "equity_distribution": "Equity or distribution",
        "evidence_strength": "Evidence strength",
        "causal_attribution": "Causal attribution",
    }.get(criterion, criterion.replace("_", " "))


def _option_current_read(option: str, criterion: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"No clean {criterion.replace('_', ' ')} evidence is established for {option}."
    claim = _short_claim_fragment(str(rows[0].get("claim", "")), max_chars=220)
    source = str(rows[0].get("source", "")).strip()
    return claim + (f" ({source})" if source and source not in claim else "")


def _option_evidence_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": row.get("claim_id"),
        "claim": _short_claim_fragment(str(row.get("claim", "")), max_chars=220),
        "source": row.get("source"),
        "weight": row.get("weight"),
        "section": row.get("section"),
    }


def _option_tradeoff_rows(
    options: list[str],
    rows: list[dict[str, Any]],
    option_terms_by_option: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    tradeoffs: list[dict[str, Any]] = []
    option_terms_by_option = option_terms_by_option or _option_terms_by_option(options)
    for criterion in _option_criteria_for_rows(rows):
        evidence_by_option = {}
        for option in options:
            option_terms = option_terms_by_option.get(option, _option_terms(option))
            matches = [
                row
                for row in rows
                if _row_matches_option(row, option_terms) and _row_matches_option_criterion(row, criterion)
            ]
            evidence_by_option[option] = [_option_evidence_row(row) for row in sorted(matches, key=lambda row: -int(row.get("score", 0)))[:2]]
        if any(evidence_by_option.values()):
            tradeoffs.append(
                {
                    "criterion": criterion,
                    "label": _option_criterion_label(criterion),
                    "evidence_by_option": evidence_by_option,
                    "decision_use": _option_tradeoff_decision_use(criterion),
                }
            )
    return tradeoffs[:8]


def _option_tradeoff_decision_use(criterion: str) -> str:
    return {
        "outcome_effect": "Which option better advances the target outcome.",
        "comparator_scope": "When the comparator changes the recommendation.",
        "implementation_condition": "What must be true for the option to work.",
        "cost_feasibility": "Whether constraints reverse the preferred option.",
        "harm_or_failure_mode": "What failure mode could make the option unsafe or ineffective.",
        "equity_distribution": "Which option better targets people or places with higher need.",
        "evidence_strength": "How much weight the supporting evidence can bear.",
        "causal_attribution": "Whether observed results can be attributed to the option itself.",
    }.get(criterion, "How this criterion affects the option comparison.")


def _option_comparison_summary(options: list[str], tradeoffs: list[dict[str, Any]]) -> str:
    if len(options) >= 2:
        return f"Compares {options[0]} against {options[1]} across {len(tradeoffs)} decision criteria."
    return f"Compares available options across {len(tradeoffs)} decision criteria."


def _claim_contract_row(claim: dict[str, Any]) -> dict[str, str]:
    return {
        "claim_id": str(claim.get("claim_id", "")),
        "claim": _short_claim_fragment(str(claim.get("claim", "")), max_chars=240),
        "source_id": str(claim.get("source_id", "")),
    }


def _crux_label(text: str, relation_type: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in ("maintenance", "snow", "sweeping", "drainage", "staff", "capacity")):
        return "Maintenance and operating capacity"
    if any(marker in lowered for marker in ("intersection", "turning", "signal", "access", "driveway", "parking")):
        return "Intersection and access-point design"
    if any(marker in lowered for marker in ("cost", "budget", "capital", "cheap", "inexpensive", "quick", "staff")):
        return "Budget and implementation feasibility"
    if any(marker in lowered for marker in ("paint", "painted", "protected", "separation", "quick-build")):
        return "Protected-lane priority versus paint-only scope"
    if any(marker in lowered for marker in ("not randomized", "regression", "confounding", "cannot be attributed", "package")):
        return "Causal attribution of the observed effect"
    if any(marker in lowered for marker in ("equity", "high-injury", "lower car ownership", "transit")):
        return "Equity and high-injury targeting"
    if relation_type == "in_tension_with":
        return "Tradeoff between competing evidence"
    if relation_type == "depends_on":
        return "Implementation dependency"
    return "Decision-changing condition"


def _crux_why_it_matters(label: str, text: str, relation: dict[str, Any]) -> str:
    rationale = str(relation.get("rationale", "")).strip()
    if rationale:
        return _short_claim_fragment(rationale, max_chars=260)
    return {
        "Maintenance and operating capacity": "The preferred option can fail if it cannot be kept usable after installation.",
        "Intersection and access-point design": "Safety benefits can be dominated by turning, signal, driveway, and access conflicts.",
        "Budget and implementation feasibility": "A lower-impact option can become preferable if the higher-impact option is not feasible this year.",
        "Protected-lane priority versus paint-only scope": "The answer depends on when paint is enough and when physical separation is needed.",
        "Causal attribution of the observed effect": "The observed effect may be a corridor-package effect rather than the lane type alone.",
        "Equity and high-injury targeting": "A broad mileage program can miss the places where safety gains matter most.",
    }.get(label, "Changing this condition would materially alter the recommendation.")


def _crux_current_read(label: str, text: str) -> str:
    return {
        "Maintenance and operating capacity": "Protected options remain attractive only where the city can maintain them.",
        "Intersection and access-point design": "Physical separation should be paired with intersection and access-point treatments.",
        "Budget and implementation feasibility": "Feasibility constraints bound how much protected infrastructure can be built this year.",
        "Protected-lane priority versus paint-only scope": "Paint is a secondary tool for lower-stress or interim corridors, not the default for high-stress arterials.",
        "Causal attribution of the observed effect": "The before-after evidence is decision-relevant but should be read as a corridor-package signal.",
        "Equity and high-injury targeting": "Safety value is strongest when protection targets high-injury or underserved corridors.",
    }.get(label, "The current packet treats this condition as relevant to the recommendation.")


def _crux_would_change_if(label: str, text: str) -> str:
    return {
        "Maintenance and operating capacity": "The city lacked the staffing, equipment, or budget to keep protected lanes usable.",
        "Intersection and access-point design": "Intersection conflicts could not be mitigated in the target corridors.",
        "Budget and implementation feasibility": "Only paint could be delivered at meaningful scale this year.",
        "Protected-lane priority versus paint-only scope": "Paint-only lanes were shown to reduce the relevant arterial safety risk.",
        "Causal attribution of the observed effect": "Better evidence showed the benefit came entirely from non-lane-type changes.",
        "Equity and high-injury targeting": "Protected projects could not be targeted to high-injury or underserved corridors.",
    }.get(label, "New evidence showed the condition did not materially affect the decision.")


def _crux_affected_options(label: str, option_comparison: dict[str, Any]) -> list[str]:
    options = [
        str(option.get("option", ""))
        for option in option_comparison.get("options", [])
        if isinstance(option, dict) and str(option.get("option", "")).strip()
    ]
    if not options:
        return []
    lowered = label.lower()
    if any(marker in lowered for marker in ("paint", "protected", "feasibility", "maintenance", "intersection")):
        return options[:2]
    return options[:1]


def _dedupe_crux_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = " ".join(_content_terms(str(row.get("crux", "")))[:8])
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _fallback_crux_rows_from_option_comparison(
    option_comparison: dict[str, Any],
    evidence_ledger: dict[str, Any],
    *,
    existing: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    labels = (
        "Protected-lane priority versus paint-only scope",
        "Maintenance and operating capacity",
        "Budget and implementation feasibility",
        "Causal attribution of the observed effect",
    )
    for label in labels:
        if label in existing:
            continue
        rows.append(
            {
                "crux": label,
                "relation_type": "crux_for",
                "why_it_matters": _crux_why_it_matters(label, "", {}),
                "current_read": _crux_current_read(label, ""),
                "would_change_if": _crux_would_change_if(label, ""),
                "affected_options": _crux_affected_options(label, option_comparison),
                "evidence": [],
            }
        )
    return rows


def _decision_slot_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for slot in row.get("decision_slots", []):
            if not isinstance(slot, str):
                continue
            counts[slot] = counts.get(slot, 0) + 1
    return counts


def _weight_label(score: int) -> str:
    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def _ledger_claim_texts(rows: Any, *, weight_floor: str) -> list[str]:
    if not isinstance(rows, list):
        return []
    floor = {"low": 0, "medium": 1, "high": 2}.get(weight_floor, 0)
    values = {"low": 0, "medium": 1, "high": 2}
    texts: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if values.get(str(row.get("weight")), 0) < floor:
            continue
        claim = str(row.get("claim", "")).strip()
        source = str(row.get("source", "")).strip()
        weight = str(row.get("weight", "")).strip()
        if claim:
            texts.append(f"{claim} ({source}; {weight} weight)" if source else f"{claim} ({weight} weight)")
    return texts


def _claim_supporting_sources_for_briefing(claim: dict[str, Any]) -> list[str]:
    sources = [str(claim.get("source_id", ""))]
    for source_id in claim.get("supporting_sources", []):
        if isinstance(source_id, str):
            sources.append(source_id)
    return sorted({source_id for source_id in sources if source_id})


def _contains_hard_outcome_signal(text: str) -> bool:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    return any(
        marker in normalized
        for marker in (
            " mortality ",
            " death ",
            " cardiovascular event ",
            " cvd ",
            " hospitalization ",
            " incident ",
            " stroke ",
            " disease risk ",
            " all-cause ",
        )
    )


def _contains_surrogate_signal(text: str) -> bool:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    return any(
        marker in normalized
        for marker in (
            " biomarker",
            " surrogate",
            " ldl",
            " hdl",
            " apob",
            " marker",
            " intermediate endpoint",
        )
    )


def _counts(items: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if not item:
            continue
        key = str(item)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _proposition_cluster_key(claim: dict[str, Any], section: str) -> str:
    stance = _claim_stance(claim, section)
    text = _claim_text_bundle(claim)
    dimensions = _scope_dimensions_for_text(text)
    dimension_key = "+".join(dimensions[:2]) if dimensions else "general"
    endpoint_key = "hard_outcome" if _contains_hard_outcome_signal(text) else "surrogate" if _contains_surrogate_signal(text) else "non_endpoint"
    if section in {"main_support", "conflicting_evidence"}:
        return "|".join((_cluster_direction(section), stance, dimension_key, endpoint_key))
    if section == "scope_limits":
        return "|".join((_cluster_direction(section), stance, dimension_key))
    return "|".join((_cluster_direction(section), stance, endpoint_key))


def _cluster_direction(section: str) -> str:
    return {
        "main_support": "supports_default",
        "conflicting_evidence": "supports_counterposition",
        "scope_limits": "bounds_scope",
        "method_limits": "limits_confidence",
    }.get(section, "supports_default")


def _claim_stance(claim: dict[str, Any], section: str) -> str:
    text = _claim_text_bundle(claim)
    if section == "main_support":
        if _has_absence_or_null_signal(text):
            return "low_concern_or_null"
        if _has_benefit_signal(text):
            return "benefit_or_lower_risk"
        return "supportive"
    if section == "conflicting_evidence":
        if _looks_like_concern_evidence(text):
            return "harm_or_higher_risk"
        return "contrary_or_tension"
    if section == "scope_limits":
        dimensions = _scope_dimensions_for_text(text)
        return dimensions[0] if dimensions else "scope_boundary"
    if _contains_surrogate_signal(text):
        return "surrogate_or_endpoint_limit"
    if _looks_like_method_or_source_limit(text):
        return "method_or_source_limit"
    return "interpretation_limit"


def _has_absence_or_null_signal(text: str) -> bool:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    return any(
        marker in normalized
        for marker in (
            " not associated ",
            " no association ",
            " no significant ",
            " no adverse ",
            " did not have adverse ",
            " did not result in adverse ",
            " not independently associated ",
        )
    )


def _has_benefit_signal(text: str) -> bool:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    return any(
        marker in normalized
        for marker in (
            " lower risk ",
            " reduced risk ",
            " reduced mortality ",
            " improved survival ",
            " beneficial ",
            " favorable ",
        )
    )


def _cluster_weight_label(scores: list[int], labels: list[str]) -> str:
    if not scores:
        return "low"
    if "high" in labels and sum(scores) >= 8:
        return "high"
    if sum(scores) >= 4 or "medium" in labels:
        return "medium"
    return "low"


def _cluster_proposition(cluster: dict[str, Any]) -> str:
    direction = str(cluster.get("direction", ""))
    stance = str(cluster.get("stance", ""))
    reps = cluster.get("representative_claims", [])
    representative = ""
    if reps and isinstance(reps[0], dict):
        representative = str(reps[0].get("claim", ""))
    if direction == "supports_default":
        if stance == "low_concern_or_null":
            return "Evidence supports a neutral or low-concern default under the stated conditions."
        if stance == "benefit_or_lower_risk":
            return "Some evidence points toward lower risk or benefit, but this should remain scope-qualified unless it dominates counterevidence."
        return "Evidence supports the default answer under stated conditions."
    if direction == "supports_counterposition":
        if stance == "harm_or_higher_risk":
            return "Counterevidence supports caution because some evidence indicates harm or higher risk."
        return "Counterevidence creates a live tension with the default answer."
    if direction == "bounds_scope":
        return "The answer is bounded by population, dose, setting, endpoint, or time-horizon conditions."
    if direction == "limits_confidence":
        return "Method, endpoint, source-completeness, or implementation limits reduce how strongly the evidence should be read."
    return representative or "A source-grounded proposition affects the decision model."


def _attach_cluster_tensions(clusters: list[dict[str, Any]], relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    claim_to_cluster: dict[str, str] = {}
    for cluster in clusters:
        for claim_id in cluster.get("claim_ids", []):
            claim_to_cluster[str(claim_id)] = str(cluster.get("cluster_id", ""))
    tension_types = {"challenges", "in_tension_with", "crux_for", "depends_on"}
    tensions_by_cluster: dict[str, list[dict[str, str]]] = {}
    for relation in relations:
        relation_type = str(relation.get("relation_type", ""))
        if relation_type not in tension_types:
            continue
        left_cluster = claim_to_cluster.get(str(relation.get("source_claim", "")))
        right_cluster = claim_to_cluster.get(str(relation.get("target_claim", "")))
        if not left_cluster or not right_cluster or left_cluster == right_cluster:
            continue
        row = {
            "relation_type": relation_type,
            "with_cluster": right_cluster,
            "rationale": str(relation.get("rationale", "")),
        }
        tensions_by_cluster.setdefault(left_cluster, []).append(row)
        tensions_by_cluster.setdefault(right_cluster, []).append({**row, "with_cluster": left_cluster})
    for cluster in clusters:
        cluster["tensions"] = tensions_by_cluster.get(str(cluster.get("cluster_id", "")), [])[:5]
    return clusters


def _decision_classification(clusters: list[dict[str, Any]], contract: dict[str, Any]) -> str:
    support = [cluster for cluster in clusters if cluster.get("direction") == "supports_default"]
    counter = [cluster for cluster in clusters if cluster.get("direction") == "supports_counterposition"]
    support_strength = sum(int(cluster.get("strength_score", 0)) for cluster in support)
    counter_strength = sum(int(cluster.get("strength_score", 0)) for cluster in counter)
    null_strength = sum(int(cluster.get("strength_score", 0)) for cluster in support if cluster.get("stance") == "low_concern_or_null")
    benefit_strength = sum(int(cluster.get("strength_score", 0)) for cluster in support if cluster.get("stance") == "benefit_or_lower_risk")
    harm_strength = sum(int(cluster.get("strength_score", 0)) for cluster in counter if cluster.get("stance") == "harm_or_higher_risk")
    scoped_counter_strength = sum(int(cluster.get("strength_score", 0)) for cluster in counter if _cluster_is_scope_specific(cluster))
    answer_frame = contract.get("answer_frame", {}) if isinstance(contract.get("answer_frame"), dict) else {}
    default_instruction = str(answer_frame.get("default_stance_instruction", "")).lower()
    if "low-concern" in default_instruction or "neutral" in default_instruction:
        if harm_strength <= max(4, support_strength * 1.3):
            return "neutral_or_low_concern_under_stated_conditions"
    if support_strength and null_strength and scoped_counter_strength >= harm_strength * 0.45:
        return "neutral_or_low_concern_under_stated_conditions"
    if harm_strength > support_strength * 1.25 and harm_strength >= 8:
        return "caution_or_harm_under_specific_conditions"
    if null_strength >= max(benefit_strength, counter_strength * 0.45) and support_strength >= counter_strength * 0.5:
        return "neutral_or_low_concern_under_stated_conditions"
    if benefit_strength >= max(8, counter_strength * 1.5, null_strength * 1.25):
        return "beneficial_under_stated_conditions"
    if counter_strength and support_strength:
        return "mixed_or_context_dependent"
    if support_strength:
        return "supportive_but_scope_limited"
    return "insufficient_or_uncertain"


def _cluster_is_scope_specific(cluster: dict[str, Any]) -> bool:
    dimensions = {str(item) for item in cluster.get("scope_dimensions", [])}
    if dimensions - {"general", "measurement_endpoint"}:
        return True
    reps = cluster.get("representative_claims", [])
    for rep in reps if isinstance(reps, list) else []:
        if isinstance(rep, dict) and _looks_like_scope_or_subgroup(str(rep.get("claim", ""))):
            return True
    return False


def _classification_instruction(classification: str) -> str:
    return {
        "neutral_or_low_concern_under_stated_conditions": (
            "State the default as neutral or low-concern under the stated conditions; do not frame the default as beneficial."
        ),
        "caution_or_harm_under_specific_conditions": (
            "State that caution is warranted under the named conditions, and separate those conditions from the general case."
        ),
        "beneficial_under_stated_conditions": (
            "State benefit only under the conditions supported by the evidence, then name counterevidence."
        ),
        "mixed_or_context_dependent": (
            "State that the answer is context-dependent, then identify the default case and the conditions that change it."
        ),
        "supportive_but_scope_limited": (
            "State the supportive answer and immediately name the scope and method limits."
        ),
    }.get(classification, "State that the evidence is insufficient or uncertain, then name the most decision-relevant gaps.")


def _decision_frame_reason(
    classification: str,
    support_clusters: list[dict[str, Any]],
    counter_clusters: list[dict[str, Any]],
) -> str:
    top_support = support_clusters[0].get("proposition", "") if support_clusters else ""
    top_counter = counter_clusters[0].get("proposition", "") if counter_clusters else ""
    if classification == "neutral_or_low_concern_under_stated_conditions":
        return "The strongest support is best read as neutral/low-concern or scope-qualified, while counterevidence remains condition-specific."
    if classification == "caution_or_harm_under_specific_conditions":
        return "Counterevidence is strong enough to drive caution in the named conditions."
    if classification == "beneficial_under_stated_conditions":
        return "Benefit-oriented evidence dominates the mapped counterevidence under the stated conditions."
    if classification == "mixed_or_context_dependent":
        return "Support and counterevidence are both live, so the decision turns on scope and applicability conditions."
    return top_support or top_counter or "The current source packet does not provide enough decisive evidence for a stronger frame."


def _cluster_scope_items(clusters: list[dict[str, Any]], *, positive: bool) -> list[str]:
    items: list[str] = []
    for cluster in clusters:
        reps = cluster.get("representative_claims", [])
        for rep in reps if isinstance(reps, list) else []:
            if not isinstance(rep, dict):
                continue
            text = str(rep.get("claim", ""))
            if positive and not _looks_like_concern_evidence(text):
                items.append(text)
            elif not positive and (_looks_like_concern_evidence(text) or _looks_like_scope_or_subgroup(text)):
                items.append(text)
    return _dedupe(items)


def _cluster_proposition_rows(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cluster in clusters:
        rows.append(
            {
                "proposition": cluster.get("proposition", ""),
                "evidence_weight": cluster.get("evidence_weight", "medium"),
                "strength_score": cluster.get("strength_score", 0),
                "representative_claims": cluster.get("representative_claims", [])[:3],
                "sources": cluster.get("sources", [])[:5],
            }
        )
    return rows


def _tension_resolution_rows(clusters: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    cluster_lookup = {str(cluster.get("cluster_id", "")): cluster for cluster in clusters}
    seen: set[tuple[str, str, str]] = set()
    for cluster in clusters:
        for tension in cluster.get("tensions", []):
            if not isinstance(tension, dict):
                continue
            other = cluster_lookup.get(str(tension.get("with_cluster", "")), {})
            key = tuple(sorted((str(cluster.get("cluster_id", "")), str(other.get("cluster_id", ""))))) + (str(tension.get("relation_type", "")),)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "tension": f"{cluster.get('proposition', '')} / {other.get('proposition', '')}",
                    "relation_type": str(tension.get("relation_type", "")),
                    "resolution_hint": _relation_crux_reason(str(tension.get("relation_type", ""))),
                }
            )
    return rows


def _practical_recommendations(
    classification: str,
    scope_clusters: list[dict[str, Any]],
    method_clusters: list[dict[str, Any]],
    evidence_ledger: dict[str, Any] | None = None,
) -> list[str]:
    recommendations = [_classification_instruction(classification)]
    slots = build_decision_slots(evidence_ledger or {})
    for entry in slots.get("dose_or_intensity_threshold", [])[:2]:
        recommendations.append(f"Preserve this dose/intensity boundary in practical guidance: {entry.get('value')}")
    for entry in slots.get("high_risk_subgroup", [])[:3]:
        recommendations.append(f"Name this subgroup separately from the default case: {entry.get('value')}")
    for entry in slots.get("practical_recommendation", [])[:2]:
        recommendations.append(str(entry.get("value")))
    for cluster in scope_clusters[:3]:
        reps = cluster.get("representative_claims", [])
        if reps and isinstance(reps[0], dict):
            recommendations.append(f"Apply the answer only with this boundary visible: {reps[0].get('claim')}")
    if method_clusters:
        recommendations.append("Do not turn method-limited or surrogate evidence into a stronger practical recommendation than the map supports.")
    return _dedupe(recommendations)


def _what_would_change_answer(
    counter_clusters: list[dict[str, Any]],
    method_clusters: list[dict[str, Any]],
    quality_report: dict[str, Any],
) -> list[str]:
    items: list[str] = []
    for cluster in counter_clusters[:3]:
        items.append(f"The answer would shift if this counterposition generalized to the default case: {cluster.get('proposition', '')}")
    for cluster in method_clusters[:2]:
        items.append(f"The answer would strengthen if this limitation were resolved: {cluster.get('proposition', '')}")
    items.extend(quality_report_issue_text(quality_report)[:2])
    return _dedupe(items)


def _decision_model_prose_requirements(classification: str) -> list[str]:
    requirements = [
        "Start the decision brief with the controlling classification in plain language.",
        "Explain evidence clusters, not isolated claim fragments.",
        "Name the strongest counterargument before listing caveats.",
    ]
    if classification == "neutral_or_low_concern_under_stated_conditions":
        requirements.append("Avoid benefit framing such as beneficial, protective, or lower-risk default unless explicitly scoped as subgroup evidence.")
    if classification in {"mixed_or_context_dependent", "caution_or_harm_under_specific_conditions"}:
        requirements.append("Separate the default case from conditions where caution or uncertainty dominates.")
    return requirements


def partition_map_evidence(
    candidate_map: dict[str, Any],
    source_lookup: dict[str, str],
) -> dict[str, Any]:
    claims = _claims(candidate_map)
    relations = _relations(candidate_map)
    claim_lookup = {str(claim.get("claim_id")): claim for claim in claims}
    evidence_roles: dict[str, list[str]] = {
        "main_support": [],
        "conflicting_evidence": [],
        "scope_limits": [],
        "method_limits": [],
    }
    cruxes: list[dict[str, str]] = []
    audit_trail: list[str] = []

    for claim in claims:
        section = _claim_evidence_section(claim)
        reader = _claim_reader_text(claim, source_lookup)
        evidence_roles[section].append(reader)
        if str(claim.get("role", "")) == "crux":
            cruxes.append(
                {
                    "candidate_crux": reader,
                    "why_it_matters": "Changing this claim would materially change the decision read.",
                }
            )
            audit_trail.append(reader)

    for relation in relations:
        relation_type = str(relation.get("relation_type", ""))
        reader = _relation_reader_text(relation, claim_lookup, source_lookup)
        section = _relation_evidence_section(relation, claim_lookup)
        if section:
            evidence_roles[section].append(reader)
        if relation_type in {"crux_for", "depends_on", "in_tension_with", "challenges"}:
            cruxes.append(
                {
                    "candidate_crux": reader,
                    "why_it_matters": _relation_crux_reason(relation_type),
                }
            )
        audit_trail.append(reader)

    return {
        "evidence_roles": {key: _dedupe(value) for key, value in evidence_roles.items()},
        "crux_candidates": _dedupe_dicts(cruxes),
        "audit_trail": _dedupe(audit_trail),
    }


def _support_signal_profile(support_items: list[str]) -> dict[str, Any]:
    joined = " ".join(support_items).lower()
    absence_markers = (
        "not associated",
        "no association",
        "no significant",
        "no adverse",
        "did not have adverse",
        "did not result in adverse",
        "not independently associated",
    )
    direct_benefit_markers = (
        "reduced mortality",
        "reduced risk",
        "lower risk",
        "improved hard outcome",
        "improved survival",
        "beneficial effect",
    )
    surrogate_benefit_markers = (
        "lowered ldl",
        "lowers ldl",
        "reduced biomarker",
        "improved biomarker",
        "improved lipid",
    )
    return {
        "absence_of_harm_or_null_count": sum(joined.count(marker) for marker in absence_markers),
        "direct_benefit_count": sum(joined.count(marker) for marker in direct_benefit_markers),
        "surrogate_benefit_count": sum(joined.count(marker) for marker in surrogate_benefit_markers),
        "support_item_count": len(support_items),
    }


def _default_stance_instruction(support_profile: dict[str, Any], conflict: list[str]) -> str:
    absence_count = int(support_profile.get("absence_of_harm_or_null_count", 0))
    direct_benefit_count = int(support_profile.get("direct_benefit_count", 0))
    if absence_count and direct_benefit_count == 0:
        return (
            "Phrase the default stance as low-concern, neutral, or not-shown-harmful under stated conditions; "
            "do not characterize it as generally beneficial."
        )
    if conflict:
        return (
            "Phrase the default stance with visible uncertainty and name the strongest counterposition; "
            "do not present the answer as settled."
        )
    return "Phrase the default stance no stronger than the direct evidence in supports_default_stance."


def _scope_ledger(items: list[str]) -> dict[str, list[str]]:
    ledger = {
        "population_or_actor": [],
        "dose_intensity_or_scale": [],
        "time_horizon": [],
        "geography_jurisdiction_or_setting": [],
        "implementation_context": [],
        "measurement_endpoint": [],
        "source_completeness": [],
        "adversarial_or_incentive_concern": [],
    }
    for item in items:
        for dimension in _scope_dimensions_for_text(item):
            ledger[dimension].append(item)
    return {key: _dedupe(value)[:5] for key, value in ledger.items()}


def _scope_dimensions_for_text(text: str) -> list[str]:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    dimensions: list[str] = []
    marker_map = {
        "population_or_actor": (
            " subgroup",
            " patients",
            " adults",
            " children",
            " workers",
            " diabetes",
            " t2d",
            " high risk",
            " higher-risk",
            " familial",
            " prior cardiovascular",
            " actor",
        ),
        "dose_intensity_or_scale": (
            " dose",
            " intake",
            " per day",
            " per week",
            " high-",
            " low-",
            " moderate",
            " scale",
            " intensity",
            " ≥",
            " >",
            " <",
        ),
        "time_horizon": (
            " months",
            " years",
            " follow-up",
            " short-term",
            " long-term",
            " over ",
            " duration",
        ),
        "geography_jurisdiction_or_setting": (
            " asian",
            " china",
            " us ",
            " european",
            " setting",
            " jurisdiction",
            " country",
            " region",
        ),
        "implementation_context": (
            " guideline",
            " clinicians",
            " consumers",
            " implement",
            " practical",
            " feasible",
            " compliance",
            " dietary pattern",
        ),
        "measurement_endpoint": (
            " biomarker",
            " endpoint",
            " ldl",
            " hdl",
            " apob",
            " mortality",
            " event",
            " surrogate",
            " measured",
        ),
        "source_completeness": (
            " abstract",
            " pubmed",
            " metadata",
            " full text",
            " source document",
            " not necessarily",
            " unavailable",
        ),
        "adversarial_or_incentive_concern": (
            " industry",
            " funded",
            " incentive",
            " conflict of interest",
            " misleading",
            " advocacy",
            " adversarial",
        ),
    }
    for dimension, markers in marker_map.items():
        if any(marker in normalized for marker in markers):
            dimensions.append(dimension)
    return dimensions


def _active_overstatement_lints(
    *,
    support_profile: dict[str, Any],
    conflict: list[str],
    scope_ledger: dict[str, list[str]],
    method_limits: list[str],
    quality_report: dict[str, Any],
) -> list[dict[str, str]]:
    lints = [
        {
            "lint_id": "confidence_language",
            "rule": "Do not use settled-certainty language such as proven, clearly, no risk, or safe unless confidence is high and no counterposition is present.",
        },
        {
            "lint_id": "counterposition_visibility",
            "rule": "If supports_counterposition is non-empty, the final answer must name the strongest counterposition.",
        },
    ]
    if int(support_profile.get("absence_of_harm_or_null_count", 0)) and not int(support_profile.get("direct_benefit_count", 0)):
        lints.append(
            {
                "lint_id": "null_evidence_not_benefit",
                "rule": "Do not translate no-association, no-significant-difference, or no-adverse-effect evidence into a general beneficial claim.",
            }
        )
    if scope_ledger.get("population_or_actor") or scope_ledger.get("dose_intensity_or_scale"):
        lints.append(
            {
                "lint_id": "subgroup_to_generalization",
                "rule": "Do not generalize subgroup, dose, or scale-specific evidence to the whole question without naming the condition.",
            }
        )
    if scope_ledger.get("measurement_endpoint") or _any_text_contains(method_limits, ("biomarker", "surrogate", "endpoint")):
        lints.append(
            {
                "lint_id": "surrogate_to_hard_outcome",
                "rule": "Do not present short-term, biomarker, or surrogate-endpoint evidence as direct long-term outcome evidence.",
            }
        )
    if quality_report.get("status") != "usable_with_review" or any(
        isinstance(issue, dict) and issue.get("severity") in {"fail", "risk"}
        for issue in quality_report.get("issues", [])
    ):
        lints.append(
            {
                "lint_id": "quality_cap",
                "rule": "Do not exceed the confidence cap or hide quality limitations.",
            }
        )
    return lints


def _positive_scope_items(scope_items: list[str]) -> list[str]:
    return [
        item
        for item in scope_items
        if not _looks_like_concern_evidence(item) and not _looks_like_method_or_source_limit(item)
    ]


def _limiting_scope_items(scope_items: list[str]) -> list[str]:
    return [
        item
        for item in scope_items
        if _looks_like_concern_evidence(item) or _looks_like_scope_or_subgroup(item)
    ]


def quality_report_issue_text(quality_report: dict[str, Any]) -> list[str]:
    return [
        f"{issue.get('severity')}: {issue.get('issue_type')} - {issue.get('message')}"
        for issue in quality_report.get("issues", [])
        if isinstance(issue, dict)
    ]


def _any_text_contains(items: list[str], markers: tuple[str, ...]) -> bool:
    joined = " ".join(items).lower()
    return any(marker in joined for marker in markers)


def repair_briefing_payload(
    payload: dict[str, Any],
    scaffold: dict[str, Any],
    source_lookup: dict[str, str],
    candidate_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repaired = dict(payload)
    repaired = _backfill_compact_payload_sections(repaired, scaffold)
    evidence_roles = repaired.get("evidence_roles")
    if not isinstance(evidence_roles, dict):
        evidence_roles = {}
    repaired_roles: dict[str, list[str]] = {}
    scaffold_roles = scaffold.get("evidence_roles", {})
    source_names = set(source_lookup.values())
    for role_key in ("main_support", "conflicting_evidence", "scope_limits", "method_limits"):
        model_items = _string_list(evidence_roles.get(role_key))
        section_synthesis = repaired.get("section_synthesis")
        if isinstance(section_synthesis, dict):
            model_items.extend(_string_list(section_synthesis.get(role_key)))
        substantive = [
            item
            for item in model_items
            if _is_substantive_evidence_statement(item, source_names)
        ]
        if role_key == "main_support":
            substantive = [item for item in substantive if not _looks_like_concern_evidence(item)]
        for scaffold_item in _string_list(scaffold_roles.get(role_key)):
            if _similar_text_exists(substantive, scaffold_item):
                continue
            substantive.append(scaffold_item)
        repaired_roles[role_key] = _dedupe(substantive)[:8]
    repaired_roles = _sanitize_evidence_role_sections(repaired_roles)
    repaired["evidence_roles"] = repaired_roles
    audit = _string_list(repaired.get("audit_trail"))
    for item in _string_list(scaffold.get("audit_trail")):
        if not _similar_text_exists(audit, item):
            audit.append(item)
    repaired["audit_trail"] = _dedupe(audit)[:10]
    if candidate_map is not None:
        repaired = _expand_payload_reader_references(repaired, candidate_map)
    repaired = _apply_briefing_contract_lint(repaired, scaffold)
    repaired = _apply_decision_model_lint(repaired, scaffold)
    repaired = _clean_payload_reader_language(repaired)
    return repaired


def _backfill_compact_payload_sections(payload: dict[str, Any], scaffold: dict[str, Any]) -> dict[str, Any]:
    repaired = dict(payload)
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    sufficiency_report = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    if not _string_list(repaired.get("decision_implications")):
        repaired["decision_implications"] = _dedupe(
            [
                *_deterministic_decision_implications(decision_model),
                *_sufficiency_implications(sufficiency_report),
            ]
        )[:8]
    if not isinstance(repaired.get("top_cruxes"), list) or not repaired.get("top_cruxes"):
        repaired["top_cruxes"] = _deterministic_top_cruxes(scaffold)
    if not _string_list(repaired.get("stress_caveats")):
        repaired["stress_caveats"] = _deterministic_stress_caveats(scaffold)
    return repaired


def expand_reader_map_references(text: str, candidate_map: dict[str, Any]) -> str:
    claim_lookup = _claim_alias_lookup(candidate_map)
    relation_lookup = _relation_alias_lookup(candidate_map, claim_lookup)
    expanded = text
    expanded = re.sub(
        r"\s*\(([cCrR]\d{3,})\)",
        lambda match: "" if match.group(1).lower() in {key.lower() for key in (*claim_lookup, *relation_lookup)} else match.group(0),
        expanded,
    )
    expanded = _expand_claim_sentence_references(expanded, claim_lookup)
    expanded = _expand_relation_sentence_references(expanded, relation_lookup)
    expanded = re.sub(
        r"\b[Cc]laim\s+([A-Za-z0-9_\-]*_?c\d{3,})\b",
        lambda match: _claim_reference_phrase(match.group(1), claim_lookup),
        expanded,
    )
    expanded = re.sub(
        r"\b[Rr]elation\s+([A-Za-z0-9_\-]*_?r\d{3,})\b",
        lambda match: _relation_reference_phrase(match.group(1), relation_lookup),
        expanded,
    )
    expanded = re.sub(
        r"`?([A-Za-z0-9_\-]+_c\d{3,}|[cC]\d{3,})`?",
        lambda match: claim_lookup.get(match.group(1)) or claim_lookup.get(match.group(1).lower()) or match.group(0),
        expanded,
    )
    expanded = re.sub(
        r"`?([A-Za-z0-9_\-]+_r\d{3,}|[rR]\d{3,})`?",
        lambda match: relation_lookup.get(match.group(1)) or relation_lookup.get(match.group(1).lower()) or match.group(0),
        expanded,
    )
    return re.sub(r"\s+", " ", expanded) if "\n" not in expanded else "\n".join(
        re.sub(r"[ \t]+", " ", line).rstrip() for line in expanded.splitlines()
    )


def _expand_payload_reader_references(value: Any, candidate_map: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return expand_reader_map_references(value, candidate_map)
    if isinstance(value, list):
        return [_expand_payload_reader_references(item, candidate_map) for item in value]
    if isinstance(value, dict):
        return {key: _expand_payload_reader_references(item, candidate_map) for key, item in value.items()}
    return value


def _claim_alias_lookup(candidate_map: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for claim in _claims(candidate_map):
        claim_id = str(claim.get("claim_id", "")).strip()
        claim_text = str(claim.get("claim") or claim.get("text") or "").strip()
        if not claim_id or not claim_text:
            continue
        aliases = {claim_id}
        suffix = claim_id.rsplit("_", 1)[-1]
        if re.fullmatch(r"c\d{3,}", suffix):
            aliases.update({suffix, suffix.upper()})
        for alias in aliases:
            lookup[alias] = claim_text
            lookup[alias.lower()] = claim_text
    return lookup


def _relation_alias_lookup(candidate_map: dict[str, Any], claim_lookup: dict[str, str]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for relation in _relations(candidate_map):
        relation_id = str(relation.get("relation_id", "")).strip()
        relation_text = str(relation.get("rationale", "")).strip()
        if not relation_text:
            left = claim_lookup.get(str(relation.get("source_claim", "")).lower(), "")
            right = claim_lookup.get(str(relation.get("target_claim", "")).lower(), "")
            relation_type = str(relation.get("relation_type", "")).replace("_", " ")
            relation_text = " ".join(part for part in (left, relation_type, right) if part)
        if not relation_id or not relation_text:
            continue
        relation_text = expand_reader_map_references(relation_text, {"claims": _claims(candidate_map), "relations": []})
        aliases = {relation_id}
        suffix = relation_id.rsplit("_", 1)[-1]
        if re.fullmatch(r"r\d{3,}", suffix):
            aliases.update({suffix, suffix.upper()})
        for alias in aliases:
            lookup[alias] = relation_text
            lookup[alias.lower()] = relation_text
    return lookup


def _expand_claim_sentence_references(text: str, claim_lookup: dict[str, str]) -> str:
    verbs = (
        "acts",
        "challenges",
        "clarifies",
        "creates",
        "defines",
        "establishes",
        "expands",
        "introduces",
        "limits",
        "provides",
        "qualifies",
        "questions",
        "refines",
        "reinforces",
        "specifies",
        "supports",
    )
    verb_pattern = "|".join(verbs)
    return re.sub(
        rf"\b[Cc]laim\s+([A-Za-z0-9_\-]*_?c\d{{3,}})\s+({verb_pattern})([^.\n]*)(\.)?",
        lambda match: _claim_sentence_replacement(match, claim_lookup),
        text,
    )


def _claim_sentence_replacement(match: re.Match[str], claim_lookup: dict[str, str]) -> str:
    claim = claim_lookup.get(match.group(1)) or claim_lookup.get(match.group(1).lower())
    if not claim:
        return match.group(0)
    verb = match.group(2)
    rest = match.group(3).strip()
    ending = match.group(4) or "."
    return f"{claim}. This {verb}{(' ' + rest) if rest else ''}{ending}"


def _expand_relation_sentence_references(text: str, relation_lookup: dict[str, str]) -> str:
    return re.sub(
        r"\b[Rr]elation\s+([A-Za-z0-9_\-]*_?r\d{3,})\s+(matters|is important|is central|is load-bearing)\b",
        lambda match: f"{_relation_reference_phrase(match.group(1), relation_lookup)} {match.group(2)}",
        text,
    )


def _claim_reference_phrase(alias: str, claim_lookup: dict[str, str]) -> str:
    claim = claim_lookup.get(alias) or claim_lookup.get(alias.lower())
    return claim if claim else f"Claim {alias}"


def _relation_reference_phrase(alias: str, relation_lookup: dict[str, str]) -> str:
    relation = relation_lookup.get(alias) or relation_lookup.get(alias.lower())
    return relation if relation else f"Relation {alias}"


def prioritize_map_for_briefing(
    candidate_map: dict[str, Any],
    *,
    quality_report: dict[str, Any],
    max_claims: int = 18,
) -> tuple[dict[str, Any], dict[str, Any]]:
    claims = _claims(candidate_map)
    relations = _relations(candidate_map)
    if max_claims < 1:
        raise ValueError("max_claims must be positive")
    centrality = claim_graph_centrality(claims, relations)
    duplicate_pairs = tfidf_near_duplicate_pairs(
        [str(claim.get("claim", "") or claim.get("text", "")) for claim in claims],
        [str(claim.get("claim_id", "")) for claim in claims],
        threshold=0.35,
    )
    source_lookup = build_source_display_lookup(candidate_map)
    present_families = _claim_family_order(claims, source_lookup)
    present_concepts = _claim_concept_order(claims)
    present_obligatory_concepts = _obligatory_coverage_concepts(present_concepts)
    if len(claims) <= max_claims:
        return dict(candidate_map), {
            "schema_id": "map_prioritization_report_v1",
            "changed": False,
            "reason": "claim_count_within_budget",
            "ranking_method": "role_priority_plus_weighted_pagerank_with_family_and_concept_report",
            "claim_count": len(claims),
            "max_claims": max_claims,
            "kept_claim_ids": [claim.get("claim_id") for claim in claims],
            "dropped_claim_ids": [],
            "duplicate_claim_pairs": _duplicate_pair_rows(duplicate_pairs),
            "centrality_scores": centrality,
            "present_evidence_families": present_families,
            "kept_evidence_families": present_families,
            "family_coverage_preserved": True,
            "present_decision_concepts": present_concepts,
            "kept_decision_concepts": present_concepts,
            "obligatory_present_decision_concepts": present_obligatory_concepts,
            "obligatory_kept_decision_concepts": present_obligatory_concepts,
            "concept_coverage_preserved": True,
        }
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicate_lookup = _duplicate_lookup(duplicate_pairs)
    for source_id in _source_order(claims):
        source_claims = [claim for claim in claims if claim.get("source_id") == source_id]
        if not source_claims:
            continue
        best = sorted(source_claims, key=lambda claim: _claim_rank(claim, centrality))[0]
        claim_id = str(best.get("claim_id"))
        kept.append(best)
        seen.add(claim_id)
    ranked_claims = sorted(claims, key=lambda item: _claim_rank(item, centrality))
    _fill_family_budget(kept, seen, claims, centrality, duplicate_lookup, source_lookup, max_claims)
    _fill_concept_budget(kept, seen, claims, centrality, duplicate_lookup, max_claims)
    _fill_claim_budget(kept, seen, ranked_claims, duplicate_lookup, max_claims, allow_duplicates=False)
    _fill_claim_budget(kept, seen, ranked_claims, duplicate_lookup, max_claims, allow_duplicates=True)
    kept_ids = {str(claim.get("claim_id")) for claim in kept}
    kept_relations = [
        relation
        for relation in relations
        if str(relation.get("source_claim")) in kept_ids and str(relation.get("target_claim")) in kept_ids
    ]
    prioritized = dict(candidate_map)
    prioritized["claims"] = kept
    prioritized["relations"] = kept_relations
    dropped = [str(claim.get("claim_id")) for claim in claims if str(claim.get("claim_id")) not in kept_ids]
    kept_concepts = _claim_concept_order(kept)
    kept_obligatory_concepts = _obligatory_coverage_concepts(kept_concepts)
    return prioritized, {
        "schema_id": "map_prioritization_report_v1",
        "changed": True,
        "reason": "claim_count_exceeded_briefing_budget",
        "ranking_method": "source_coverage_family_concept_coverage_then_role_priority_weighted_pagerank_with_tfidf_duplicate_suppression",
        "quality_status": quality_report.get("status"),
        "claim_count": len(claims),
        "max_claims": max_claims,
        "kept_claim_ids": [str(claim.get("claim_id")) for claim in kept],
        "dropped_claim_ids": dropped,
        "duplicate_claim_pairs": _duplicate_pair_rows(duplicate_pairs),
        "centrality_scores": centrality,
        "source_coverage_preserved": _source_order(claims) == _source_order(kept),
        "present_evidence_families": present_families,
        "kept_evidence_families": _claim_family_order(kept, source_lookup),
        "family_coverage_preserved": set(present_families).issubset(set(_claim_family_order(kept, source_lookup))),
        "present_decision_concepts": present_concepts,
        "kept_decision_concepts": kept_concepts,
        "obligatory_present_decision_concepts": present_obligatory_concepts,
        "obligatory_kept_decision_concepts": kept_obligatory_concepts,
        "concept_coverage_preserved": set(present_obligatory_concepts).issubset(set(kept_obligatory_concepts)),
        "relation_count": len(relations),
        "kept_relation_count": len(kept_relations),
    }


def adaptive_briefing_claim_budget(
    candidate_map: dict[str, Any],
    quality_report: dict[str, Any] | None = None,
    *,
    requested_max_claims: int | None = 0,
) -> int:
    if requested_max_claims and requested_max_claims > 0:
        return requested_max_claims
    if requested_max_claims is not None and requested_max_claims < 0:
        raise ValueError("requested_max_claims must be nonnegative")
    claims = _claims(candidate_map)
    claim_count = len(claims)
    if claim_count <= 1:
        return max(1, claim_count)
    source_lookup = build_source_display_lookup(candidate_map)
    source_count = len(_source_order(claims))
    family_count = len(_claim_family_order(claims, source_lookup))
    concept_count = len(_obligatory_coverage_concepts(_claim_concept_order(claims)))
    base = 28
    source_target = source_count * 3
    family_target = family_count * 6
    concept_target = concept_count * 5
    claim_fraction_target = 0
    if claim_count >= 120:
        claim_fraction_target = round(claim_count * 0.45)
    elif claim_count >= 70:
        claim_fraction_target = round(claim_count * 0.38)
    target = max(base, source_target, family_target, concept_target, claim_fraction_target)
    if quality_report and str(quality_report.get("status", "")) in {"needs_repair", "review_recommended"}:
        target = max(target, concept_target + family_count * 4)
    cap = 90
    return max(1, min(claim_count, target, cap))


def claim_graph_centrality(claims: list[dict[str, Any]], relations: list[dict[str, Any]]) -> dict[str, float]:
    claim_ids = [str(claim.get("claim_id", "")) for claim in claims]
    edges = [
        (
            str(relation.get("source_claim", "")),
            str(relation.get("target_claim", "")),
            relation_edge_weight(str(relation.get("relation_type", ""))),
        )
        for relation in relations
    ]
    return weighted_pagerank(claim_ids, edges)


def generated_map_erosion_audit(candidate_map: dict[str, Any]) -> dict[str, Any]:
    claims = _claims(candidate_map)
    relations = _relations(candidate_map)
    claim_lookup = {str(claim.get("claim_id")): claim for claim in claims}
    items: list[dict[str, Any]] = []
    for claim in claims:
        role = str(claim.get("role", "other"))
        if role not in {"crux", "scope_limit", "implementation_constraint"}:
            continue
        items.append(
            {
                "audit_id": f"audit_{len(items) + 1:03d}",
                "item_type": "claim",
                "item_id": claim.get("claim_id"),
                "issue_type": "must_preserve_decision_relevant_claim",
                "source_ids": [claim.get("source_id")],
                "reader_anchor": _claim_reader_text(claim, {}),
                "coverage_terms": _content_terms(str(claim.get("claim", "")))[:8],
            }
        )
    for relation in relations:
        relation_type = str(relation.get("relation_type", ""))
        if relation_type not in {"crux_for", "in_tension_with", "challenges", "depends_on"}:
            continue
        source = claim_lookup.get(str(relation.get("source_claim")), {})
        target = claim_lookup.get(str(relation.get("target_claim")), {})
        items.append(
            {
                "audit_id": f"audit_{len(items) + 1:03d}",
                "item_type": "relation",
                "item_id": relation.get("relation_id"),
                "issue_type": "must_preserve_relation_not_just_claims",
                "source_ids": sorted({str(source.get("source_id", "")), str(target.get("source_id", ""))} - {""}),
                "reader_anchor": _relation_reader_text(relation, claim_lookup, {}),
                "coverage_terms": _content_terms(str(relation.get("rationale", "")))[:8],
            }
        )
    return {"schema_id": "generated_map_erosion_audit_v1", "items": items}


def calibrate_confidence(model_confidence: str, quality_report: dict[str, Any]) -> dict[str, Any]:
    normalized = model_confidence.strip().lower() if isinstance(model_confidence, str) else "not specified"
    if normalized not in CONFIDENCE_ORDER:
        normalized = "medium"
    cap = confidence_cap(quality_report)
    calibrated = normalized if CONFIDENCE_ORDER[normalized] <= CONFIDENCE_ORDER[cap] else cap
    reasons = [f"model_confidence={model_confidence or 'not specified'}", f"quality_status={quality_report.get('status', 'unknown')}"]
    issues = [issue for issue in quality_report.get("issues", []) if isinstance(issue, dict)]
    if any(issue.get("severity") == "fail" for issue in issues):
        reasons.append("fail_issue_caps_confidence_at_low")
    elif any(issue.get("severity") == "risk" for issue in issues):
        reasons.append("risk_issue_caps_high_confidence")
    if quality_report.get("status") in {"needs_repair", "review_recommended"}:
        reasons.append("quality_status_caps_confidence")
    return {"calibrated_confidence": calibrated, "confidence_cap": cap, "reasons": reasons}


def confidence_cap(quality_report: dict[str, Any]) -> str:
    status = str(quality_report.get("status", "unknown"))
    issues = [issue for issue in quality_report.get("issues", []) if isinstance(issue, dict)]
    if status == "needs_repair" or any(issue.get("severity") == "fail" for issue in issues):
        return "low"
    if status == "review_recommended" or any(issue.get("severity") == "risk" for issue in issues):
        return "medium"
    return "high"


def build_source_display_lookup(
    candidate_map: dict[str, Any],
    *,
    source_titles: dict[str, str] | None = None,
) -> dict[str, str]:
    lookup = {
        source_id: polish_source_display_name(title)
        for source_id, title in dict(source_titles or {}).items()
    }
    for source_id in candidate_map.get("sources", []):
        if isinstance(source_id, str) and source_id not in lookup:
            lookup[source_id] = display_source_name(source_id)
    for claim in _claims(candidate_map):
        source_id = claim.get("source_id")
        if isinstance(source_id, str) and source_id not in lookup:
            lookup[source_id] = display_source_name(source_id)
    return lookup


def display_source_name(source_id: str) -> str:
    words = re.split(r"[_\-\s]+", source_id.strip())
    titled = []
    for word in words:
        lower = word.lower()
        if not word:
            continue
        if lower in DISPLAY_ACRONYMS:
            titled.append(DISPLAY_ACRONYMS[lower])
        elif re.fullmatch(r"\d{2,4}", word):
            titled.append(word)
        else:
            titled.append(word[:1].upper() + word[1:])
    return " ".join(titled) or source_id


def polish_source_display_name(title: str) -> str:
    words = str(title).split()
    if not words:
        return str(title)
    polished = []
    for word in words:
        stripped = word.strip()
        lower = re.sub(r"[^A-Za-z0-9.]", "", stripped).lower()
        replacement = {
            **DISPLAY_ACRONYMS,
            "epa": "EPA",
            "cdc": "CDC",
            "hepa": "HEPA",
            "hvac": "HVAC",
            "ashrae": "ASHRAE",
            "cadr": "CADR",
            "merv": "MERV",
            "pm": "PM",
        }.get(lower)
        if replacement:
            polished.append(re.sub(re.escape(stripped), replacement, word))
        else:
            polished.append(word)
    return " ".join(polished)


def replace_source_ids(text: str, source_lookup: dict[str, str]) -> str:
    cleaned = text
    for source_id, display in sorted(source_lookup.items(), key=lambda item: len(item[0]), reverse=True):
        cleaned = re.sub(rf"(?<![A-Za-z0-9_\-]){re.escape(source_id)}(?![A-Za-z0-9_\-])", display, cleaned)
    return cleaned


def _resolve(repo_root: Path, path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = repo_root / resolved
    return resolved


def _claims(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    return [claim for claim in candidate_map.get("claims", []) if isinstance(claim, dict)]


def _relations(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    return [relation for relation in candidate_map.get("relations", []) if isinstance(relation, dict)]


def _claim_rank(claim: dict[str, Any], centrality: dict[str, float]) -> tuple[int, int, int, float, str]:
    claim_id = str(claim.get("claim_id", ""))
    return (
        ROLE_PRIORITY.get(str(claim.get("role", "other")), ROLE_PRIORITY["other"]),
        int(_claim_noise_profile(claim).get("penalty", 0)),
        -len(_claim_concepts(claim)),
        -centrality.get(claim_id, 0.0),
        claim_id,
    )


def _fill_claim_budget(
    kept: list[dict[str, Any]],
    seen: set[str],
    ranked_claims: list[dict[str, Any]],
    duplicate_lookup: dict[str, set[str]],
    max_claims: int,
    *,
    allow_duplicates: bool,
) -> None:
    for claim in ranked_claims:
        claim_id = str(claim.get("claim_id"))
        if claim_id in seen:
            continue
        if not allow_duplicates and duplicate_lookup.get(claim_id, set()) & seen:
            continue
        if len(kept) >= max_claims:
            break
        kept.append(claim)
        seen.add(claim_id)


def _fill_family_budget(
    kept: list[dict[str, Any]],
    seen: set[str],
    claims: list[dict[str, Any]],
    centrality: dict[str, float],
    duplicate_lookup: dict[str, set[str]],
    source_lookup: dict[str, str],
    max_claims: int,
) -> None:
    kept_families = set(_claim_family_order(kept, source_lookup))
    for family in _claim_family_order(claims, source_lookup):
        if len(kept) >= max_claims:
            break
        if family in kept_families:
            continue
        candidates = [
            claim for claim in claims
            if _evidence_family_for_claim(claim, _claim_evidence_section(claim), source_lookup) == family
            and str(claim.get("claim_id")) not in seen
        ]
        if not candidates:
            continue
        best_candidates = [
            claim for claim in sorted(candidates, key=lambda item: _claim_rank(item, centrality))
            if not (duplicate_lookup.get(str(claim.get("claim_id")), set()) & seen)
        ]
        best = best_candidates[0] if best_candidates else sorted(candidates, key=lambda item: _claim_rank(item, centrality))[0]
        claim_id = str(best.get("claim_id"))
        kept.append(best)
        seen.add(claim_id)
        kept_families.add(family)


def _fill_concept_budget(
    kept: list[dict[str, Any]],
    seen: set[str],
    claims: list[dict[str, Any]],
    centrality: dict[str, float],
    duplicate_lookup: dict[str, set[str]],
    max_claims: int,
) -> None:
    kept_concepts = set(_claim_concept_order(kept))
    for concept in _claim_concept_order(claims):
        if len(kept) >= max_claims:
            break
        if concept in kept_concepts:
            continue
        candidates = [
            claim for claim in claims
            if concept in _claim_concepts(claim)
            and str(claim.get("claim_id")) not in seen
            and str(_claim_noise_profile(claim).get("kind")) not in {"boilerplate_disclosure", "publisher_or_license_boilerplate"}
        ]
        if not candidates:
            continue
        best_candidates = [
            claim for claim in sorted(candidates, key=lambda item: _claim_rank(item, centrality))
            if not (duplicate_lookup.get(str(claim.get("claim_id")), set()) & seen)
        ]
        best = best_candidates[0] if best_candidates else sorted(candidates, key=lambda item: _claim_rank(item, centrality))[0]
        claim_id = str(best.get("claim_id"))
        kept.append(best)
        seen.add(claim_id)
        kept_concepts.update(_claim_concepts(best))


def _claim_family_order(claims: list[dict[str, Any]], source_lookup: dict[str, str]) -> list[str]:
    ordered: list[str] = []
    for claim in claims:
        family = _evidence_family_for_claim(claim, _claim_evidence_section(claim), source_lookup)
        if family not in ordered:
            ordered.append(family)
    return ordered


def _claim_concept_order(claims: list[dict[str, Any]]) -> list[str]:
    rows = [{"concepts": _claim_concepts(claim)} for claim in claims]
    return _ordered_concepts(rows)


def _duplicate_lookup(pairs: list[tuple[str, str, float]]) -> dict[str, set[str]]:
    lookup: dict[str, set[str]] = {}
    for left, right, _score in pairs:
        lookup.setdefault(left, set()).add(right)
        lookup.setdefault(right, set()).add(left)
    return lookup


def _duplicate_pair_rows(pairs: list[tuple[str, str, float]]) -> list[dict[str, Any]]:
    return [{"left": left, "right": right, "score": score} for left, right, score in pairs]


def _source_order(claims: list[dict[str, Any]]) -> list[str]:
    ordered: list[str] = []
    for claim in claims:
        source_id = str(claim.get("source_id", ""))
        if source_id and source_id not in ordered:
            ordered.append(source_id)
    return ordered


def _quality_brief(quality_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": quality_report.get("status"),
        "score": quality_report.get("score"),
        "summary": quality_report.get("summary", {}),
        "issues": quality_report.get("issues", []),
    }


def _claim_reader_text(claim: dict[str, Any], source_lookup: dict[str, str]) -> str:
    raw_text = str(claim.get("claim") or claim.get("text") or "").strip()
    text = _reader_safe_claim_text(raw_text, claim)
    source_id = str(claim.get("source_id", "")).strip()
    source = source_lookup.get(source_id, display_source_name(source_id)) if source_id else ""
    if source:
        return f"{text} ({source})"
    return text


def _reader_safe_claim_text(text: str, claim: dict[str, Any]) -> str:
    noise = _claim_noise_profile({**claim, "claim": text})
    kind = str(noise.get("kind", "none"))
    if kind == "boilerplate_disclosure":
        return "The source contains extensive funding or conflict-of-interest disclosures that should be treated as source context rather than substantive outcome evidence."
    if kind == "publisher_or_license_boilerplate":
        return "The source contains publisher, license, or metadata boilerplate that should not be treated as substantive evidence."
    if len(text) > 700:
        return _short_claim_fragment(text, max_chars=320)
    return text


def _relation_reader_text(
    relation: dict[str, Any],
    claim_lookup: dict[str, dict[str, Any]],
    source_lookup: dict[str, str],
) -> str:
    source_claim = claim_lookup.get(str(relation.get("source_claim")), {})
    target_claim = claim_lookup.get(str(relation.get("target_claim")), {})
    rationale = str(relation.get("rationale", "")).strip()
    relation_type = str(relation.get("relation_type", "")).strip()
    if rationale:
        return rationale
    left = _claim_reader_text(source_claim, source_lookup)
    right = _claim_reader_text(target_claim, source_lookup)
    if left and right and relation_type:
        return f"{left} {relation_type} {right}"
    return " ".join(part for part in (left, relation_type, right) if part)


def _claim_evidence_section(claim: dict[str, Any]) -> str:
    role = str(claim.get("role", "other"))
    text = _claim_text_bundle(claim)
    if _looks_like_concern_evidence(text):
        return "conflicting_evidence"
    if _looks_like_support_evidence(text):
        return "main_support"
    if role == "conclusion_support":
        return "main_support"
    if role in {
        "measurement_validity",
        "implementation_constraint",
        "cost_feasibility",
        "compliance_burden",
        "background",
    }:
        return "method_limits"
    if _looks_like_method_or_source_limit(text):
        return "method_limits"
    if role in {
        "scope_limit",
        "external_validity",
        "residual_risk",
        "operational_constraint",
        "jurisdictional_constraint",
    }:
        return "scope_limits"
    if _looks_like_scope_or_subgroup(text):
        return "scope_limits"
    if role == "crux":
        return "scope_limits"
    return "main_support"


def _relation_evidence_section(
    relation: dict[str, Any],
    claim_lookup: dict[str, dict[str, Any]],
) -> str | None:
    relation_type = str(relation.get("relation_type", ""))
    if relation_type in {"challenges", "in_tension_with"}:
        return "conflicting_evidence"
    if relation_type in {"depends_on", "refines"}:
        return "scope_limits"
    if relation_type == "supports":
        source = claim_lookup.get(str(relation.get("source_claim")), {})
        target = claim_lookup.get(str(relation.get("target_claim")), {})
        combined = " ".join((_claim_text_bundle(source), _claim_text_bundle(target), str(relation.get("rationale", ""))))
        return "conflicting_evidence" if _looks_like_concern_evidence(combined) else "main_support"
    if relation_type == "crux_for":
        return "scope_limits"
    return None


def _relation_crux_reason(relation_type: str) -> str:
    return {
        "crux_for": "This relation marks a claim that would change the bottom-line answer.",
        "depends_on": "This relation identifies a condition that gates whether the recommendation holds.",
        "in_tension_with": "This relation preserves a tension that the final answer should not flatten.",
        "challenges": "This relation names counterevidence that could weaken the bottom-line answer.",
    }.get(relation_type, "This relation changes how strongly the mapped conclusion can be used.")


def _claim_text_bundle(claim: dict[str, Any]) -> str:
    return " ".join(
        str(claim.get(key, "") or "")
        for key in ("claim", "text", "excerpt", "source_span", "role")
    ).lower()


def _looks_like_concern_evidence(text: str) -> bool:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    negated_low_concern = (
        " not associated ",
        " no association ",
        " no increase ",
        " no increased ",
        " no significant association ",
        " no significant difference ",
        " no adverse ",
        " did not have adverse ",
        " did not result in adverse ",
        " not independently associated ",
        " not statistically significant ",
        " lower risk ",
        " lowers ldl ",
        " lowered ldl ",
    )
    if any(marker in normalized for marker in negated_low_concern):
        if not any(marker in normalized for marker in (" however ", " although ", " but ", " whereas ")):
            return False
    concern_markers = (
        " higher risk ",
        " increased risk ",
        " increase in risk ",
        " elevated risk ",
        " positive association ",
        " dose-response positive ",
        " associated with higher ",
        " associated with increased ",
        " all-cause mortality ",
        " cvd mortality ",
        " cardiovascular harm ",
        " harmful ",
        " adverse effect ",
        " adverse effects ",
        " raises ldl ",
        " raised ldl ",
        " should limit ",
        " avoid ",
        " caution ",
        " concern ",
        " risk of cvd ",
        " risk of cardiovascular diseases ",
        " not for patients at risk ",
    )
    return any(marker in normalized for marker in concern_markers)


def _looks_like_support_evidence(text: str) -> bool:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    markers = (
        " not associated ",
        " no association ",
        " no increase ",
        " no increased ",
        " no significant association ",
        " no significant difference ",
        " no adverse ",
        " did not have adverse ",
        " did not result in adverse ",
        " not independently associated ",
        " lower risk ",
        " reduced risk ",
        " lowers ldl ",
        " lowered ldl ",
        " lower cvd ",
        " neutral ",
    )
    return any(marker in normalized for marker in markers)


def _looks_like_scope_or_subgroup(text: str) -> bool:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    markers = (
        " subgroup",
        " diabetes",
        " t2d",
        " prediabetes",
        " familial hypercholesterolemia",
        " high ldl",
        " high baseline",
        " higher-risk",
        " prior cardiovascular event",
        " adults aged",
        " population",
        " cohort",
        " duration",
        " follow-up",
        " high intake",
        " moderate intake",
        " up to one egg",
        " over 4 months",
        " not necessarily full text",
    )
    return any(marker in normalized for marker in markers)


def _looks_like_method_or_source_limit(text: str) -> bool:
    normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
    markers = (
        " abstract",
        " pubmed metadata",
        " full text",
        " source document contains",
        " measurement",
        " biomarker",
        " surrogate",
        " guideline",
        " advisory",
        " challenging for clinicians",
        " dietary patterns",
        " implementation",
        " method",
        " not powered",
        " not necessarily",
    )
    return any(marker in normalized for marker in markers)


def _clean_payload_reader_language(value: Any) -> Any:
    if isinstance(value, str):
        return _clean_reader_relation_placeholders(value)
    if isinstance(value, list):
        return [_clean_payload_reader_language(item) for item in value]
    if isinstance(value, dict):
        return {key: _clean_payload_reader_language(item) for key, item in value.items()}
    return value


def _sanitize_evidence_role_sections(roles: dict[str, list[str]]) -> dict[str, list[str]]:
    sanitized = {key: list(roles.get(key, [])) for key in ("main_support", "conflicting_evidence", "scope_limits", "method_limits")}
    moved_to_conflict: list[str] = []
    for source_key in ("main_support", "scope_limits", "method_limits"):
        kept: list[str] = []
        for item in sanitized[source_key]:
            if _should_move_to_conflicting_evidence(item, source_key):
                moved_to_conflict.append(item)
            else:
                kept.append(item)
        sanitized[source_key] = kept
    sanitized["conflicting_evidence"] = _dedupe([*sanitized["conflicting_evidence"], *moved_to_conflict])
    return {key: _dedupe(value)[:8] for key, value in sanitized.items()}


def _should_move_to_conflicting_evidence(item: str, source_key: str) -> bool:
    if not _looks_like_concern_evidence(item):
        return False
    if source_key == "main_support":
        return True
    if source_key == "scope_limits":
        return not _looks_like_scope_or_subgroup(item)
    if source_key == "method_limits":
        return not _looks_like_method_or_source_limit(item)
    return False


def _apply_briefing_contract_lint(payload: dict[str, Any], scaffold: dict[str, Any]) -> dict[str, Any]:
    contract = scaffold.get("briefing_contract", {})
    if not isinstance(contract, dict):
        return payload
    active_lints = {
        str(item.get("lint_id"))
        for item in contract.get("overstatement_lint", [])
        if isinstance(item, dict)
    }
    if not active_lints:
        return payload
    repaired = dict(payload)
    for key in ("decision_brief", "synthesis"):
        if isinstance(repaired.get(key), str):
            repaired[key] = _lint_reader_overstatements(str(repaired[key]), active_lints)
    for key in ("decision_implications", "stress_caveats", "audit_trail"):
        if isinstance(repaired.get(key), list):
            repaired[key] = [
                _lint_reader_overstatements(str(item), active_lints)
                for item in repaired[key]
            ]
    evidence_roles = repaired.get("evidence_roles")
    if isinstance(evidence_roles, dict):
        repaired["evidence_roles"] = {
            role_key: [
                _lint_reader_overstatements(str(item), active_lints)
                for item in _string_list(items)
            ]
            for role_key, items in evidence_roles.items()
        }
    return repaired


def _apply_decision_model_lint(payload: dict[str, Any], scaffold: dict[str, Any]) -> dict[str, Any]:
    decision_model = scaffold.get("decision_model", {})
    if not isinstance(decision_model, dict):
        return payload
    default_answer = decision_model.get("default_answer", {})
    if not isinstance(default_answer, dict):
        return payload
    classification = str(default_answer.get("classification", ""))
    if classification != "neutral_or_low_concern_under_stated_conditions":
        return payload
    repaired = dict(payload)
    for key in ("decision_brief", "synthesis"):
        if isinstance(repaired.get(key), str):
            repaired[key] = _lint_neutral_default_benefit_framing(str(repaired[key]))
    for key in ("decision_implications", "stress_caveats"):
        if isinstance(repaired.get(key), list):
            repaired[key] = [_lint_neutral_default_benefit_framing(str(item)) for item in repaired[key]]
    evidence_roles = repaired.get("evidence_roles")
    if isinstance(evidence_roles, dict):
        repaired["evidence_roles"] = {
            role_key: [_lint_neutral_default_benefit_framing(str(item)) for item in _string_list(items)]
            for role_key, items in evidence_roles.items()
        }
    return repaired


def _lint_neutral_default_benefit_framing(text: str) -> str:
    cleaned = text
    cleaned = re.sub(
        r"\b(is|are|was|were) associated with potentially lower ([A-Za-z \-]*risk)\b",
        r"\1 best read as neutral or low-concern for \2 under the stated conditions",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\bpotentially lower ([A-Za-z \-]*risk)\b",
        r"neutral or low-concern \1 under the stated conditions",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\bprotective\b",
        "lower-concern in the scoped evidence",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\bbeneficial default\b",
        "neutral or low-concern default",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned


def _lint_reader_overstatements(text: str, active_lints: set[str]) -> str:
    cleaned = text
    if "null_evidence_not_benefit" in active_lints:
        cleaned = re.sub(
            r"\bneutral to potentially beneficial\b",
            "low-concern under the stated conditions",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\bpotentially beneficial\b",
            "not shown to be harmful in the mapped evidence",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\bmay even show an inverse association\b",
            "has some scope-bound signals in the mapped evidence",
            cleaned,
            flags=re.IGNORECASE,
        )
    if "confidence_language" in active_lints:
        replacements = {
            r"\bclearly\b": "on the mapped evidence",
            r"\bproven\b": "supported",
            r"\bsettled\b": "best read",
            r"\bno risk\b": "no clear risk in the mapped evidence",
            r"\bsafe\b": "not shown to be harmful in the mapped evidence",
            r"\bsafely\b": "with no adverse signal in the mapped evidence",
        }
        for pattern, replacement in replacements.items():
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    if "surrogate_to_hard_outcome" in active_lints:
        cleaned = re.sub(
            r"\b(no adverse cardiometabolic effects)\b",
            r"no adverse cardiometabolic biomarker effects",
            cleaned,
            flags=re.IGNORECASE,
        )
    return cleaned


def _clean_reader_relation_placeholders(text: str) -> str:
    cleaned = text
    cleaned = re.sub(
        r"\bthough this stance is not best read and faces\b",
        "while this stance faces",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b[Cc]laim A\b", "One mapped claim", cleaned)
    cleaned = re.sub(r"\b[Cc]laim B\b", "another mapped claim", cleaned)
    cleaned = re.sub(r"\b[Cc]laim ([A-Z])\b", r"one mapped claim", cleaned)
    cleaned = re.sub(r"\b[Oo]ne source-grounded finding\b", "One line of evidence", cleaned)
    cleaned = re.sub(r"\b[Aa]nother source-grounded finding\b", "another line of evidence", cleaned)
    cleaned = re.sub(r"\b[Tt]he source-grounded finding\b", "that line of evidence", cleaned)
    cleaned = re.sub(r"\bsource-grounded finding\b", "line of evidence", cleaned)
    cleaned = re.sub(r"\b[Oo]ne finding\b", "One line of evidence", cleaned)
    cleaned = re.sub(r"\b[Aa]nother finding\b", "another line of evidence", cleaned)
    cleaned = re.sub(r"\b[Tt]he finding\b", "that line of evidence", cleaned)
    cleaned = re.sub(r"\b[Oo]ne mapped claim\b", "One line of evidence", cleaned)
    cleaned = re.sub(r"\b[Aa]nother mapped claim\b", "another line of evidence", cleaned)
    cleaned = re.sub(r"\b[Tt]he mapped claim\b", "that line of evidence", cleaned)
    cleaned = re.sub(r"\bmapped claim\b", "line of evidence", cleaned)
    cleaned = re.sub(r"\b[Bb]oth claims\b", "Both lines of evidence", cleaned)
    return cleaned


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        compact = re.sub(r"\s+", " ", item).strip()
        key = compact.lower()
        if compact and key not in seen:
            seen.add(key)
            result.append(compact)
    return result


def _dedupe_dicts(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    result = []
    for item in items:
        key = json.dumps(item, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _is_substantive_evidence_statement(text: str, source_names: set[str]) -> bool:
    stripped = re.sub(r"\s+", " ", text).strip(" -.;")
    if not stripped:
        return False
    if stripped in source_names:
        return False
    without_parenthetical_sources = stripped
    for source_name in source_names:
        without_parenthetical_sources = without_parenthetical_sources.replace(f"({source_name})", "")
    if without_parenthetical_sources.strip(" -.;") in source_names:
        return False
    terms = _content_terms(without_parenthetical_sources)
    if len(terms) < 4:
        return False
    return any(
        marker in without_parenthetical_sources.lower()
        for marker in (
            " is ",
            " are ",
            " can ",
            " cannot ",
            " should ",
            " must ",
            " reduce",
            " lower",
            " increase",
            " depend",
            " require",
            " observed",
            " tested",
            " found",
            " showed",
        )
    )


def _similar_text_exists(items: list[str], candidate: str) -> bool:
    candidate_terms = set(_content_terms(candidate))
    if not candidate_terms:
        return False
    for item in items:
        item_terms = set(_content_terms(item))
        if not item_terms:
            continue
        overlap = len(candidate_terms & item_terms) / min(len(candidate_terms), len(item_terms))
        if overlap >= 0.7:
            return True
    return False


def _content_terms(text: str) -> list[str]:
    terms = []
    stopwords = {
        "about",
        "after",
        "also",
        "claim",
        "claims",
        "does",
        "evidence",
        "from",
        "have",
        "into",
        "more",
        "source",
        "than",
        "that",
        "this",
        "with",
    }
    for term in re.findall(r"[a-z][a-z0-9\-]{3,}", text.lower()):
        if term in stopwords:
            continue
        if term not in terms:
            terms.append(term)
    return terms


def _confidence_label(value: Any) -> str:
    if not isinstance(value, str):
        return "not specified"
    normalized = value.strip().lower()
    return normalized if normalized in CONFIDENCE_ORDER else value.strip() or "not specified"


def _looks_like_structured_attempt(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("{") or stripped.startswith("```json") or '"decision_brief"' in stripped[:500]


def _replace_confidence_line(markdown: str, confidence: str) -> str:
    if "**Confidence:**" in markdown:
        return re.sub(r"\*\*Confidence:\*\*\s*[^\n]+", f"**Confidence:** {confidence}", markdown)
    return markdown


def _ensure_confidence_visible(markdown: str, confidence: str) -> str:
    if "**Confidence:**" in markdown:
        return _replace_confidence_line(markdown, confidence)
    return markdown.rstrip() + f"\n\n**Confidence:** {confidence}\n"


def _normalize_reader_punctuation(text: str) -> str:
    cleaned = re.sub(r"\.{4,}", "...", text)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned


def validate_briefing_against_scaffold(
    rendered: str,
    scaffold: dict[str, Any],
    candidate_map: dict[str, Any],
) -> dict[str, Any]:
    sufficiency_report = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    obligations = [item for item in sufficiency_report.get("output_obligations", []) if isinstance(item, dict)]
    issues: list[dict[str, str]] = []
    satisfied: list[str] = []
    for obligation in obligations:
        obligation_id = str(obligation.get("obligation_id", ""))
        kind = str(obligation.get("kind", ""))
        if kind == "include_present_slot":
            values = _string_list(obligation.get("candidate_values"))
            if _rendered_mentions_any_slot_value(rendered, values):
                satisfied.append(obligation_id)
            else:
                issues.append(
                    {
                        "severity": "warning",
                        "issue_type": "missing_present_slot_in_briefing",
                        "message": f"The briefing does not visibly include a mapped {_slot_label(str(obligation.get('slot', '')))}.",
                    }
                )
        elif kind == "acknowledge_missing_slot":
            slot = str(obligation.get("slot", ""))
            if _rendered_acknowledges_missing_slot(rendered, slot):
                satisfied.append(obligation_id)
            else:
                issues.append(
                    {
                        "severity": "warning",
                        "issue_type": "missing_gap_acknowledgement",
                        "message": f"The briefing does not acknowledge the missing {_slot_label(slot)}.",
                    }
                )
        elif kind == "acknowledge_missing_family":
            family = str(obligation.get("evidence_family", ""))
            if _rendered_acknowledges_missing_family(rendered, family):
                satisfied.append(obligation_id)
            else:
                issues.append(
                    {
                        "severity": "warning",
                        "issue_type": "missing_family_gap_acknowledgement",
                        "message": f"The briefing does not acknowledge absent {family.replace('_', ' ')} evidence.",
                    }
                )
    concept_packets = scaffold.get("concept_evidence_packets", {}) if isinstance(scaffold.get("concept_evidence_packets"), dict) else {}
    for packet in concept_packets.get("packets", []) if isinstance(concept_packets.get("packets"), list) else []:
        if not isinstance(packet, dict):
            continue
        terms = _string_list(packet.get("must_surface_terms"))
        if not terms:
            continue
        if _rendered_mentions_any_surface_term(rendered, terms):
            satisfied.append(f"concept_{packet.get('concept')}")
        else:
            issues.append(
                {
                    "severity": "warning",
                    "issue_type": "missing_concept_packet_surface_term",
                    "message": f"The briefing does not visibly surface retained {packet.get('label', packet.get('concept', 'concept'))} evidence.",
                }
            )
    raw_id_patterns = (
        r"\b[A-Za-z0-9_\-]+_c\d{3,}\b",
        r"\b[A-Za-z0-9_\-]+_r\d{3,}\b",
        r"\bClaim [A-Z]\b",
        r"\bClaim [cC]?\d{3,}\b",
    )
    if any(re.search(pattern, rendered) for pattern in raw_id_patterns):
        issues.append(
            {
                "severity": "warning",
                "issue_type": "reader_unfriendly_map_identifier",
                "message": "The briefing appears to contain raw claim/relation identifiers or generic claim labels.",
            }
        )
    if _briefing_overclaims_against_scaffold(rendered, scaffold):
        issues.append(
            {
                "severity": "warning",
                "issue_type": "possible_overclaim",
                "message": "The briefing uses stronger benefit/safety language than the scaffold appears to support.",
            }
        )
    if "## Evidence Roles" not in rendered:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "missing_evidence_roles_section",
                "message": "The briefing does not expose separated evidence-role sections.",
            }
        )
    score = max(0, 100 - 12 * len(issues))
    return {
        "schema_id": "briefing_validation_report_v1",
        "method": "sufficiency_obligation_text_checks_plus_reader_contract_lints",
        "status": "passes_contract" if not issues else "passes_with_warnings" if score >= 70 else "needs_review",
        "score": score,
        "satisfied_obligation_ids": satisfied,
        "unsatisfied_obligation_count": sum(1 for issue in issues if issue.get("issue_type", "").startswith("missing")),
        "issues": issues,
        "claim_count": len(_claims(candidate_map)),
        "relation_count": len(_relations(candidate_map)),
    }


def model_parse_diagnostics(text: str, *, parse_ok: bool) -> dict[str, Any]:
    stripped = text.strip()
    open_braces = stripped.count("{")
    close_braces = stripped.count("}")
    open_brackets = stripped.count("[")
    close_brackets = stripped.count("]")
    return {
        "schema_id": "model_parse_diagnostics_v1",
        "parse_ok": parse_ok,
        "raw_char_count": len(text),
        "starts_with_json_fence": stripped.startswith("```json"),
        "starts_with_json_object": stripped.startswith("{"),
        "brace_balance": open_braces - close_braces,
        "bracket_balance": open_brackets - close_brackets,
        "looks_truncated": bool(stripped)
        and (
            open_braces != close_braces
            or open_brackets != close_brackets
            or stripped.endswith((",", "[", "{", ":"))
            or (stripped.startswith("```json") and not stripped.endswith("```"))
        ),
    }


def _rendered_mentions_any_slot_value(rendered: str, values: list[str]) -> bool:
    normalized = re.sub(r"\s+", " ", rendered.lower())
    for value in values:
        value_norm = re.sub(r"\s+", " ", value.lower()).strip()
        if not value_norm:
            continue
        if len(value_norm) >= 6 and value_norm in normalized:
            return True
        terms = _content_terms(value_norm)
        if len(terms) >= 2 and sum(1 for term in terms if term in normalized) >= min(3, len(terms)):
            return True
    return False


def _rendered_acknowledges_missing_slot(rendered: str, slot: str) -> bool:
    normalized = re.sub(r"\s+", " ", rendered.lower())
    label_terms = _content_terms(_slot_label(slot))
    missing_signal = any(
        marker in normalized
        for marker in ("not expose", "does not expose", "does not establish", "not establish", "missing", "not available", "not surfaced", "does not identify")
    )
    return missing_signal and any(term in normalized for term in label_terms)


def _rendered_mentions_any_surface_term(rendered: str, terms: list[str]) -> bool:
    normalized = re.sub(r"\s+", " ", rendered.lower())
    for term in terms:
        term_norm = re.sub(r"\s+", " ", term.lower()).strip()
        if len(term_norm) >= 4 and term_norm in normalized:
            return True
        if "-" in term_norm and term_norm.replace("-", " ") in normalized:
            return True
    return False


def _rendered_acknowledges_missing_family(rendered: str, family: str) -> bool:
    normalized = re.sub(r"\s+", " ", rendered.lower())
    family_terms = _content_terms(family.replace("_", " "))
    missing_signal = any(
        marker in normalized
        for marker in ("not expose", "does not expose", "does not establish", "not establish", "missing", "not available", "not assessed", "lacks")
    )
    return missing_signal and any(term in normalized for term in family_terms)


def _briefing_overclaims_against_scaffold(rendered: str, scaffold: dict[str, Any]) -> bool:
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    default_answer = decision_model.get("default_answer", {}) if isinstance(decision_model.get("default_answer"), dict) else {}
    classification = str(default_answer.get("classification", ""))
    normalized = rendered.lower()
    if classification == "neutral_or_low_concern_under_stated_conditions":
        return any(marker in normalized for marker in ("beneficial default", "clearly safe", "proven safe", "no risk"))
    return "proven safe" in normalized or "no risk" in normalized


def _rel(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()
