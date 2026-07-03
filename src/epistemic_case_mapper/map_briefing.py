from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
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
    "covid": "COVID",
    "dga": "DGA",
    "flf": "FLF",
    "jama": "JAMA",
    "nnr": "NNR",
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
    briefing_validation = validate_briefing_against_scaffold(rendered, scaffold, prioritized_map)
    briefing_path = artifacts / "BRIEFING.md"
    summary_path = artifacts / "briefing_summary.json"
    write_markdown(briefing_path, rendered.rstrip() + "\n")
    write_json(briefing_validation_path, briefing_validation)
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
                "prompt": _rel(repo_root, prompt_path),
                "raw": _rel(repo_root, raw_path),
                "prioritized_map": _rel(repo_root, prioritized_map_path),
                "prioritization_report": _rel(repo_root, prioritization_report_path),
                "generated_map_erosion_audit": _rel(repo_root, erosion_audit_path),
                "map_sufficiency_report": _rel(repo_root, sufficiency_report_path),
                "briefing_validation_report": _rel(repo_root, briefing_validation_path),
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
        "proposition_clusters": proposition_clusters,
        "decision_model": decision_model,
        "evidence_compression_table": evidence_compression_table,
        "concept_evidence_packets": concept_evidence_packets,
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
                "The model returned a truncated or invalid structured packet; deterministic map-backed fallback completed the briefing sections.",
                *payload["audit_trail"],
            ]
        )
    return payload


def _sufficiency_implications(sufficiency_report: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for slot in _string_list(sufficiency_report.get("missing_expected_decision_slots")):
        items.append(f"The map does not expose a decision-relevant {_slot_label(slot)}; do not fill that gap by inference.")
    for family in _string_list(sufficiency_report.get("missing_expected_evidence_families")):
        items.append(f"The map does not expose {family.replace('_', ' ')} evidence; do not imply it was assessed.")
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
                "current_read": "Preserved as a load-bearing map distinction.",
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
                "current_read": str(item.get("relation_type", "")).replace("_", " ") or "map-backed tension",
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
        "default_population": "This controls whether the default answer applies to generally healthy people or only to a narrower sample.",
        "dose_or_threshold": "Dose boundaries keep a neutral read from turning into an unlimited recommendation.",
        "substitution_or_comparator": "Comparator evidence affects practical advice because replacement foods can change the decision.",
        "hard_outcome_endpoint": "Hard outcomes are more decision-direct than surrogate movement.",
        "surrogate_or_biomarker_endpoint": "Biomarker evidence can support mechanism but should not by itself settle long-term outcomes.",
        "mechanism_ldl_apob": "Mechanistic lipid evidence bounds whether a neutral hard-outcome read is biologically plausible.",
        "subgroup_diabetes_or_metabolic_risk": "Subgroup evidence controls whether the default answer travels to higher-risk people.",
        "subgroup_fh_hyper_responder": "This subgroup can invalidate a generic population-level recommendation.",
        "dietary_context_or_saturated_fat": "Dietary context can explain why the same exposure appears harmful or neutral across settings.",
        "study_design_rct": "Trial evidence helps separate intervention effects from observational confounding.",
        "study_design_cohort": "Cohort evidence carries long-term outcome signal but remains confounding-sensitive.",
        "guideline_or_policy": "Guidance evidence shows how the map translates into practical advice.",
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
    "hard_outcome_endpoint": 3,
    "surrogate_or_biomarker_endpoint": 4,
    "mechanism_ldl_apob": 5,
    "subgroup_diabetes_or_metabolic_risk": 6,
    "subgroup_fh_hyper_responder": 7,
    "dietary_context_or_saturated_fat": 8,
    "study_design_rct": 9,
    "study_design_cohort": 10,
    "guideline_or_policy": 11,
}


def _concept_label(concept: str) -> str:
    return {
        "default_population": "Default population",
        "dose_or_threshold": "Dose or threshold",
        "hard_outcome_endpoint": "Hard outcomes",
        "surrogate_or_biomarker_endpoint": "Biomarkers or surrogates",
        "mechanism_ldl_apob": "LDL/ApoB mechanism",
        "dietary_context_or_saturated_fat": "Saturated fat or dietary context",
        "substitution_or_comparator": "Comparator or substitution",
        "subgroup_diabetes_or_metabolic_risk": "Metabolic-risk subgroup",
        "subgroup_fh_hyper_responder": "FH or hyper-responder subgroup",
        "study_design_rct": "RCT/intervention evidence",
        "study_design_cohort": "Cohort/observational evidence",
        "guideline_or_policy": "Guidance or policy",
    }.get(concept, concept.replace("_", " "))


_COVERAGE_CONCEPT_SLOT = {
    "default_population": "default_population",
    "dose_or_threshold": "dose_or_intensity_threshold",
    "substitution_or_comparator": "substitution_or_comparator",
    "hard_outcome_endpoint": "endpoint_type",
    "surrogate_or_biomarker_endpoint": "mechanism",
    "mechanism_ldl_apob": "mechanism",
    "subgroup_diabetes_or_metabolic_risk": "high_risk_subgroup",
    "subgroup_fh_hyper_responder": "high_risk_subgroup",
    "study_design_rct": "study_design",
    "study_design_cohort": "study_design",
}


_COVERAGE_VISIBLE_MARKERS = {
    "default_population": ("generally healthy", "healthy adults", "general population", "free of", "without", "free-living"),
    "dose_or_threshold": ("per day", "per week", "up to", "moderate", "high intake", "low intake", "≥", "≤", "<", ">"),
    "hard_outcome_endpoint": ("mortality", "cvd", "cardiovascular", "stroke", "myocardial infarction", "coronary", "incident"),
    "surrogate_or_biomarker_endpoint": ("biomarker", "ldl", "hdl", "apob", "cholesterol", "particle", "lipid"),
    "mechanism_ldl_apob": ("ldl", "apob", "cholesterol", "atherosclerosis", "particle", "tmao", "trimethylamine", "metabolite"),
    "dietary_context_or_saturated_fat": ("saturated fat", "dietary pattern", "dietary cholesterol", "red meat", "processed meat", "overnutrition"),
    "substitution_or_comparator": ("replace", "replacing", "substitut", "compared with", "versus", "instead of", "egg white", "plant protein"),
    "subgroup_diabetes_or_metabolic_risk": ("type 2 diabetes", "diabetes", "t2d", "prediabetes", "metabolic", "renal", "kidney"),
    "subgroup_fh_hyper_responder": ("familial", "hyper-responder", "hyper responder", "high ldl", "high apob", "elevated ldl", "elevated apob"),
    "study_design_rct": ("randomized", "randomised", "rct", "trial", "crossover", "intervention"),
    "study_design_cohort": ("cohort", "prospective", "follow-up", "observational", "participants"),
    "guideline_or_policy": ("guideline", "advisory", "recommendation", "dietary guidance", "clinicians", "consumers", "should"),
}


_COVERAGE_PREFERRED_MARKERS = {
    "mechanism_ldl_apob": (("apob", "apo b"), ("ldl", "ldl-c"), ("cholesterol",)),
    "surrogate_or_biomarker_endpoint": (("apob", "apo b"), ("ldl", "hdl", "lipid", "particle"), ("cholesterol", "biomarker")),
    "dietary_context_or_saturated_fat": (("saturated fat",), ("dietary pattern", "diet quality"), ("dietary cholesterol", "red meat", "processed meat", "overnutrition")),
    "substitution_or_comparator": (("plant protein", "egg white"), ("replace", "replacing", "substitut"), ("compared with", "versus", "instead of")),
    "guideline_or_policy": (("guideline", "dietary guidance"), ("recommendation", "advisory"), ("clinicians", "consumers", "should")),
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
        "surrogate_or_biomarker_endpoint": "Explain what biomarkers can support and what they cannot settle.",
        "mechanism_ldl_apob": "Explain the LDL/ApoB mechanism and whether it changes the bottom-line read.",
        "subgroup_diabetes_or_metabolic_risk": "State whether subgroup evidence narrows the general-population advice.",
        "subgroup_fh_hyper_responder": "State whether high-risk lipid subgroups need separate advice.",
        "dietary_context_or_saturated_fat": "State how diet composition or saturated fat modifies the exposure read.",
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
        return "Mechanistic or biomarker evidence bounds whether a neutral hard-outcome read is biologically plausible."
    if "dietary_context_or_saturated_fat" in concepts:
        return "Dietary context can explain why an exposure appears harmful or neutral across settings."
    if "subgroup_diabetes_or_metabolic_risk" in concepts or "subgroup_fh_hyper_responder" in concepts:
        return "Subgroup evidence controls whether the default answer travels to higher-risk people."
    if "substitution_or_comparator" in concepts:
        return "Comparator evidence affects the practical recommendation because replacement food matters."
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
        "mechanism_ldl_apob",
        "dietary_context_or_saturated_fat",
        "substitution_or_comparator",
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
        "substitution_or_comparator": (" compared", " versus", " vs ", " replace", " instead of", " alternative", " relative to"),
        "practical_recommendation": (" should ", " recommend", " guidance", " advice", " decision", " policy", " treat ", " use "),
    }
    for slot, markers in marker_map.items():
        if any(marker in normalized for marker in markers):
            expected.append(slot)
    counts = evidence_ledger.get("decision_slot_counts", {}) if isinstance(evidence_ledger.get("decision_slot_counts"), dict) else {}
    for slot in ("dose_or_intensity_threshold", "high_risk_subgroup", "substitution_or_comparator", "mechanism"):
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
                "instruction": f"Do not invent a { _slot_label(slot) }; state that the map does not expose it if relevant.",
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
                "message": f"The question appears to require {_slot_label(slot)}, but the map does not expose it.",
            }
        )
    for family in missing_expected_families:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "missing_expected_evidence_family",
                "message": f"The question appears to benefit from {family.replace('_', ' ')} evidence, but the map does not expose it.",
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
        r"\b(?:egg whites?|plant protein|animal protein|red meat|processed meat|low-egg diet|high-egg diet)[A-Za-z0-9 ,/\-]{0,90}",
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
    return cleaned[: max_chars - 1].rstrip(" ,.;") + "..."


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
        "dose_or_threshold": ("per day", "per week", "egg/day", "eggs/wk", "up to one", "up to 1", "moderate", "high intake", "<", ">", "≥", "≤"),
        "hard_outcome_endpoint": ("mortality", "all-cause", "cvd", "cardiovascular disease", "stroke", "myocardial infarction", "coronary heart disease", "incident"),
        "surrogate_or_biomarker_endpoint": ("biomarker", "ldl", "hdl", "apob", "cholesterol", "particle", "lipid", "tmao", "trimethylamine"),
        "mechanism_ldl_apob": ("ldl", "apob", "atherosclerosis", "particle", "cholesterol homeostasis", "tmao", "trimethylamine", "metabolite", "microbiome"),
        "dietary_context_or_saturated_fat": ("saturated fat", "dietary pattern", "red meat", "processed meat", "bacon", "sausage", "co-consum", "dietary cholesterol"),
        "substitution_or_comparator": ("replace", "replacing", "substitut", "compared with", "versus", "vs ", "instead of", "egg white", "plant protein", "low-egg", "high-egg"),
        "subgroup_diabetes_or_metabolic_risk": ("type 2 diabetes", "diabetes", "t2d", "prediabetes", "metabolic", "impaired kidney", "renal", "vascular disease"),
        "subgroup_fh_hyper_responder": ("familial hypercholesterolemia", "hyper-responder", "hyper responder", "high ldl", "high apob", "elevated ldl", "elevated apob"),
        "study_design_rct": ("randomized", "randomised", " rct", "trial", "crossover", "intervention"),
        "study_design_cohort": ("cohort", "prospective", "follow-up", "observational", "participants"),
        "guideline_or_policy": ("guideline", "advisory", "recommendation", "dietary guidance", "clinicians", "consumers"),
        "source_quality_or_incentive": ("funding", "conflict of interest", "disclosure", "industry", "consultant", "grant", "abstract", "full text"),
    }
    concepts: list[str] = []
    for concept, markers in concept_markers.items():
        if any(marker in text for marker in markers):
            concepts.append(concept)
    return concepts


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
    if any(marker in text for marker in ("guideline", "advisory", "recommendation", "dietary guidance", "policy")):
        return "guideline_or_recommendation"
    if any(marker in text for marker in ("meta-analysis", "systematic review", "pooled relative risk", "pooled rr")):
        return "evidence_synthesis"
    if any(marker in text for marker in ("randomized", "randomised", " rct", "trial", "crossover", "intervention")):
        return "rct_or_intervention"
    if any(marker in text for marker in ("cohort", "prospective", "pooled analysis", "observational", "participants", "follow-up")):
        return "cohort_or_observational"
    if any(marker in text for marker in ("replace", "substitut", "instead of", "compared with", "versus", "vs ")):
        return "substitution_or_comparator"
    if any(marker in text for marker in ("mechanism", "metabolite", "homeostasis", "ldl", "apob", "biomarker", "cholesterol", "microbiome")):
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
        "substitution_or_comparator": ("replace", "substitut", "compared with", "versus", "vs ", "instead of", "low-egg", "high-egg", "egg white", "plant protein"),
        "endpoint_type": ("mortality", "cvd", "cardiovascular", "stroke", "myocardial", "biomarker", "endpoint", "ldl", "hdl", "apob"),
        "study_design": ("cohort", "trial", "rct", "meta-analysis", "systematic review", "pooled", "prospective", "observational"),
        "practical_recommendation": ("guidance", "recommend", "should", "limit", "focus", "dietary pattern", "mediterranean", "dash"),
    }
    for slot, markers in slot_markers.items():
        if any(marker in text for marker in markers):
            slots.append(slot)
    return slots or ["unspecified"]


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
    return top_support or top_counter or "The map does not provide enough decisive evidence for a stronger frame."


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
    cleaned = re.sub(r"\.{2,}", ".", text)
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
    missing_signal = any(marker in normalized for marker in ("not expose", "does not expose", "missing", "not available", "not surfaced", "does not identify"))
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
    missing_signal = any(marker in normalized for marker in ("not expose", "does not expose", "missing", "not available", "not assessed", "lacks"))
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
