from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.decision_argument_artifacts import evaluate_traceability_against_memo
from epistemic_case_mapper.main_memo_obligations import (
    build_unified_requirement_ledger,
    build_main_memo_obligation_ledger,
    render_main_memo_obligation_ledger_markdown,
    render_unified_requirement_ledger_markdown,
)
from epistemic_case_mapper.map_briefing_crux_telemetry import build_crux_quality_telemetry


def write_gap_telemetry(
    *,
    artifacts: Path,
    repo_root: Path,
    question: str,
    candidate_map: dict[str, Any],
    prioritized_map: dict[str, Any],
    quality_report: dict[str, Any],
    prioritization_report: dict[str, Any],
    scaffold: dict[str, Any],
    briefing_text: str,
    validation: dict[str, Any],
    polish_report: dict[str, Any],
    rewrite_report: dict[str, Any],
    baseline_path: str | Path | None = None,
) -> dict[str, Path]:
    telemetry_dir = artifacts / "telemetry"
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    baseline_text = _read_optional(repo_root, baseline_path)
    diagnosis = build_gap_diagnosis(
        question=question,
        candidate_map=candidate_map,
        prioritized_map=prioritized_map,
        quality_report=quality_report,
        prioritization_report=prioritization_report,
        scaffold=scaffold,
        briefing_text=briefing_text,
        validation=validation,
        polish_report=polish_report,
        rewrite_report=rewrite_report,
        baseline_path=str(baseline_path) if baseline_path else None,
        baseline_text=baseline_text,
    )
    json_path = telemetry_dir / "gap_diagnosis.json"
    md_path = telemetry_dir / "GAP_DIAGNOSIS.md"
    obligation_path = telemetry_dir / "main_memo_obligation_ledger.json"
    obligation_md_path = telemetry_dir / "MAIN_MEMO_OBLIGATION_LEDGER.md"
    unified_path = telemetry_dir / "unified_requirement_ledger.json"
    unified_md_path = telemetry_dir / "UNIFIED_REQUIREMENT_LEDGER.md"
    write_json(json_path, diagnosis)
    write_markdown(md_path, render_gap_diagnosis_markdown(diagnosis))
    obligation_ledger = diagnosis.get("main_memo_obligation_ledger", {})
    unified_ledger = diagnosis.get("unified_requirement_ledger", {})
    write_json(obligation_path, obligation_ledger)
    write_markdown(obligation_md_path, render_main_memo_obligation_ledger_markdown(obligation_ledger))
    write_json(unified_path, unified_ledger)
    write_markdown(unified_md_path, render_unified_requirement_ledger_markdown(unified_ledger))
    return {
        "gap_diagnosis": json_path,
        "gap_diagnosis_markdown": md_path,
        "main_memo_obligation_ledger": obligation_path,
        "main_memo_obligation_ledger_markdown": obligation_md_path,
        "unified_requirement_ledger": unified_path,
        "unified_requirement_ledger_markdown": unified_md_path,
    }


def build_gap_diagnosis(
    *,
    question: str,
    candidate_map: dict[str, Any],
    prioritized_map: dict[str, Any],
    quality_report: dict[str, Any],
    prioritization_report: dict[str, Any],
    scaffold: dict[str, Any],
    briefing_text: str,
    validation: dict[str, Any],
    polish_report: dict[str, Any],
    rewrite_report: dict[str, Any],
    baseline_path: str | None = None,
    baseline_text: str = "",
) -> dict[str, Any]:
    source_coverage = _source_coverage(candidate_map, prioritized_map, scaffold, briefing_text, baseline_text)
    extraction_quality = _extraction_quality(candidate_map, prioritized_map, scaffold, prioritization_report)
    relation_quality = _relation_quality(candidate_map, prioritized_map, quality_report, scaffold, briefing_text)
    synthesis_quality = _decision_synthesis_quality(scaffold, validation, briefing_text)
    reader_quality = _reader_quality(briefing_text, polish_report, rewrite_report)
    baseline_gap = _baseline_gap(question, baseline_path, baseline_text, briefing_text, source_coverage)
    obligation_ledger = build_main_memo_obligation_ledger(
        scaffold=scaffold,
        briefing_text=briefing_text,
        baseline_gap=baseline_gap,
        source_coverage=source_coverage,
    )
    argument_artifacts = scaffold.get("decision_argument_artifacts", {}) if isinstance(scaffold.get("decision_argument_artifacts"), dict) else {}
    traceability = evaluate_traceability_against_memo(
        argument_artifacts.get("decision_traceability_matrix", {}) if isinstance(argument_artifacts, dict) else {},
        briefing_text,
    )
    unified_ledger = build_unified_requirement_ledger(
        main_memo_ledger=obligation_ledger,
        traceability_ledger=traceability,
    )
    drivers = _rank_gap_drivers(
        source_coverage,
        extraction_quality,
        relation_quality,
        synthesis_quality,
        reader_quality,
        baseline_gap,
        obligation_ledger,
    )
    return {
        "schema_id": "map_briefing_gap_telemetry_v1",
        "question": question,
        "baseline_path": baseline_path,
        "source_coverage": source_coverage,
        "extraction_quality": extraction_quality,
        "relation_quality": relation_quality,
        "decision_synthesis_quality": synthesis_quality,
        "reader_prose_quality": reader_quality,
        "baseline_gap_attribution": baseline_gap,
        "main_memo_obligation_summary": _obligation_summary(obligation_ledger),
        "main_memo_obligation_ledger": obligation_ledger,
        "unified_requirement_summary": _unified_requirement_summary(unified_ledger),
        "unified_requirement_ledger": unified_ledger,
        "largest_gap_drivers": drivers,
    }


def render_gap_diagnosis_markdown(diagnosis: dict[str, Any]) -> str:
    lines = ["# Gap Diagnosis", "", f"Question: {diagnosis.get('question', '')}", ""]
    baseline = diagnosis.get("baseline_path")
    if baseline:
        lines.extend([f"Baseline: `{baseline}`", ""])
    lines.extend(["## Largest Gap Drivers", ""])
    for item in diagnosis.get("largest_gap_drivers", []):
        lines.extend(
            [
                f"{item.get('rank')}. **{item.get('gap')}**",
                f"   - Likely stage: `{item.get('likely_stage')}`",
                f"   - Recommended intervention: {item.get('recommended_intervention')}",
            ]
        )
        evidence = item.get("evidence", [])
        if evidence:
            lines.append("   - Evidence: " + "; ".join(str(row) for row in evidence[:4]))
    lines.extend(["", "## Stage Metrics", ""])
    for key in (
        "source_coverage",
        "extraction_quality",
        "relation_quality",
        "decision_synthesis_quality",
        "reader_prose_quality",
        "main_memo_obligation_summary",
        "unified_requirement_summary",
    ):
        section = diagnosis.get(key, {})
        lines.extend([f"### {key.replace('_', ' ').title()}", "", "```json", _compact_json(section), "```", ""])
    return "\n".join(lines).rstrip() + "\n"


def _source_coverage(
    candidate_map: dict[str, Any],
    prioritized_map: dict[str, Any],
    scaffold: dict[str, Any],
    briefing_text: str,
    baseline_text: str,
) -> dict[str, Any]:
    ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    rows = [row for row in ledger.get("all_evidence", []) if isinstance(row, dict)]
    source_counts = Counter(str(row.get("source", "")).strip() for row in rows if str(row.get("source", "")).strip())
    family_counts = Counter(str(row.get("evidence_family", "general_evidence")) for row in rows)
    sufficiency = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    source_names = [*_source_names(candidate_map), *_source_display_names(scaffold)]
    baseline_source_like = _baseline_source_like_terms(baseline_text)
    absent_baseline_sources = [
        term
        for term in baseline_source_like
        if not _source_term_present(term, source_names=source_names, briefing_text=briefing_text)
    ]
    return {
        "candidate_source_count": len(source_names),
        "prioritized_source_count": len(_source_names(prioritized_map)),
        "source_use_counts": dict(source_counts.most_common()),
        "evidence_family_counts": dict(family_counts.most_common()),
        "missing_expected_evidence_families": sufficiency.get("missing_expected_evidence_families", []),
        "missing_expected_decision_slots": sufficiency.get("missing_expected_decision_slots", []),
        "baseline_source_like_terms_absent": absent_baseline_sources[:20],
        "baseline_source_like_absent_count": len(absent_baseline_sources),
    }


def _extraction_quality(
    candidate_map: dict[str, Any],
    prioritized_map: dict[str, Any],
    scaffold: dict[str, Any],
    prioritization_report: dict[str, Any],
) -> dict[str, Any]:
    claims = _claims(candidate_map)
    prioritized_claims = _claims(prioritized_map)
    text = "\n".join(str(claim.get("claim", "")) for claim in claims)
    ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    rows = [row for row in ledger.get("all_evidence", []) if isinstance(row, dict)]
    duplicate_pairs = prioritization_report.get("near_duplicate_claim_pairs") or prioritization_report.get("duplicate_claim_pairs") or []
    canonicalization = prioritization_report.get("claim_canonicalization_report", {})
    if not isinstance(canonicalization, dict):
        canonicalization = {}
    skipped = sum(1 for issue in scaffold.get("quality_issues", []) if "chunk_budget" in str(issue))
    return {
        "candidate_claim_count": len(claims),
        "prioritized_claim_count": len(prioritized_claims),
        "canonical_claim_count": canonicalization.get("canonical_claim_count"),
        "canonicalization_changed": canonicalization.get("changed", False),
        "canonicalized_duplicate_group_count": len(canonicalization.get("merged_duplicate_groups", [])) if isinstance(canonicalization.get("merged_duplicate_groups"), list) else 0,
        "canonicalized_fragment_drop_count": len(canonicalization.get("dropped_fragment_claim_ids", [])) if isinstance(canonicalization.get("dropped_fragment_claim_ids"), list) else 0,
        "claim_retention_ratio": _ratio(len(prioritized_claims), len(claims)),
        "near_duplicate_pair_count": len(duplicate_pairs) if isinstance(duplicate_pairs, list) else 0,
        "fragment_marker_count": _fragment_marker_count(text),
        "quantitative_claim_count": sum(1 for row in rows if _has_number(str(row.get("claim", "")))),
        "quality_issue_count": len(scaffold.get("quality_issues", [])) if isinstance(scaffold.get("quality_issues"), list) else 0,
        "chunk_budget_issue_count": skipped,
    }


def _relation_quality(
    candidate_map: dict[str, Any],
    prioritized_map: dict[str, Any],
    quality_report: dict[str, Any],
    scaffold: dict[str, Any],
    briefing_text: str,
) -> dict[str, Any]:
    relations = _relations(candidate_map)
    kept = _relations(prioritized_map)
    relation_types = Counter(str(row.get("relation_type", "unknown")) for row in relations)
    issues = _quality_issue_texts(quality_report)
    rejected_counts = [int(match.group(1)) for text in issues for match in [re.search(r"Rejected\s+(\d+)\s+relation", text, flags=re.I)] if match]
    return {
        "candidate_relation_count": len(relations),
        "prioritized_relation_count": len(kept),
        "relation_retention_ratio": _ratio(len(kept), len(relations)),
        "relation_type_counts": dict(relation_types.most_common()),
        "relation_type_diversity": len(relation_types),
        "rejected_relation_count_observed": max(rejected_counts) if rejected_counts else None,
        "relation_quality_issues": [text for text in issues if "relation" in text.lower()][:8],
        "crux_quality": build_crux_quality_telemetry(
            scaffold=scaffold,
            candidate_map=candidate_map,
            prioritized_map=prioritized_map,
            briefing_text=briefing_text,
        ),
    }


def _decision_synthesis_quality(scaffold: dict[str, Any], validation: dict[str, Any], briefing_text: str) -> dict[str, Any]:
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    roles = [str(line.get("role", "")) for line in synthesis.get("evidence_lines", []) if isinstance(line, dict)]
    lower = briefing_text.lower()
    return {
        "schema_id": synthesis.get("schema_id"),
        "evidence_line_count": len(roles),
        "evidence_line_roles": roles,
        "central_tension_count": len(synthesis.get("central_tensions", [])) if isinstance(synthesis.get("central_tensions"), list) else 0,
        "crux_count": len(synthesis.get("cruxes", [])) if isinstance(synthesis.get("cruxes"), list) else 0,
        "recommendation_count": len(synthesis.get("recommendations", [])) if isinstance(synthesis.get("recommendations"), list) else 0,
        "answers_question_directly": bool(re.search(r"\b(should|recommend|prefer|acceptable|not acceptable|treat)\b", lower)),
        "decision_question_visible": "**decision question:**" in lower,
        "validation_status": validation.get("status"),
        "validation_score": validation.get("score"),
        "validation_issue_count": len(validation.get("issues", [])) if isinstance(validation.get("issues"), list) else 0,
    }


def _reader_quality(briefing_text: str, polish_report: dict[str, Any], rewrite_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "word_count": len(re.findall(r"\w+", briefing_text)),
        "polish_status": polish_report.get("status"),
        "polish_score": polish_report.get("score"),
        "polish_issues": polish_report.get("issues", []),
        "rewrite_status": rewrite_report.get("status"),
        "awkward_phrase_count": _awkward_phrase_count(briefing_text),
        "malformed_parenthesis_count": max(0, briefing_text.count("(") - briefing_text.count(")")),
        "internal_artifact_phrase_count": sum(briefing_text.lower().count(term) for term in ("relation marks", "claim a", "claim b", "source packet serves")),
        "duplicate_sentence_count": polish_report.get("duplicate_sentence_count"),
    }


def _baseline_gap(
    question: str,
    baseline_path: str | None,
    baseline_text: str,
    briefing_text: str,
    source_coverage: dict[str, Any],
) -> dict[str, Any]:
    if not baseline_text:
        return {"baseline_available": False, "gap_attributions": []}
    baseline_terms = _salient_terms(baseline_text, question)
    briefing_norm = _norm(briefing_text)
    absent_terms = [term for term in baseline_terms if _norm(term) not in briefing_norm]
    attributions = []
    if source_coverage.get("baseline_source_like_absent_count", 0):
        attributions.append(_gap("missing_source", "Baseline names source-like terms absent from the map briefing.", source_coverage["baseline_source_like_terms_absent"][:8]))
    if absent_terms:
        attributions.append(_gap("bad_synthesis", "Baseline salient concepts are not surfaced in the final briefing.", absent_terms[:12]))
    return {
        "baseline_available": True,
        "baseline_word_count": len(re.findall(r"\w+", baseline_text)),
        "baseline_path": baseline_path,
        "salient_baseline_terms_absent": absent_terms[:30],
        "salient_baseline_absent_count": len(absent_terms),
        "gap_attributions": attributions,
    }


def _rank_gap_drivers(*sections: dict[str, Any]) -> list[dict[str, Any]]:
    source, extraction, relation, synthesis, reader, baseline, obligations = sections
    candidates: list[dict[str, Any]] = []
    if baseline.get("baseline_available") and baseline.get("baseline_source_like_absent_count", source.get("baseline_source_like_absent_count", 0)):
        candidates.append(_driver(90, "Baseline uses source/context not present in the briefing packet", "source_coverage", source.get("baseline_source_like_terms_absent", [])[:6], "Either mark source collection out of scope or feed these missing sources into the mapper."))
    if obligations.get("missing_from_memo_count", 0):
        candidates.append(
            _driver(
                86,
                "Main memo drops required decision-support obligations",
                "decision_synthesis",
                [
                    f"missing_from_memo={obligations.get('missing_from_memo_count')}",
                    *[
                        row.get("obligation_id")
                        for row in obligations.get("top_missing_obligations", [])
                        if isinstance(row, dict)
                    ][:5],
                ],
                "Feed the missing obligations into section synthesis as required include/reject/out-of-scope decisions before accepting the memo.",
            )
        )
    if baseline.get("salient_baseline_absent_count", 0) >= 6:
        candidates.append(_driver(78, "Baseline concepts are present as useful context but not synthesized into the memo", "decision_synthesis", baseline.get("salient_baseline_terms_absent", [])[:8], "Add a synthesis coverage check that forces absent high-salience baseline concepts to be accepted, rejected, or marked out of scope."))
    if reader.get("awkward_phrase_count", 0) or reader.get("malformed_parenthesis_count", 0):
        candidates.append(_driver(72, "Final prose still has mechanical or malformed reader-facing passages", "reader_prose", [f"awkward={reader.get('awkward_phrase_count')}", f"paren_delta={reader.get('malformed_parenthesis_count')}"], "Add section-specific prose telemetry and repair for comparator, subgroup, and crux sections."))
    if relation.get("candidate_relation_count", 0) < max(2, extraction.get("prioritized_claim_count", 0) // 8):
        candidates.append(_driver(64, "The map has too few accepted relations for its claim volume", "relation_construction", [f"relations={relation.get('candidate_relation_count')}", f"claims={extraction.get('candidate_claim_count')}"], "Increase relation construction passes for high-weight claims and report orphaned central claims."))
    crux_quality = relation.get("crux_quality", {}) if isinstance(relation.get("crux_quality"), dict) else {}
    if crux_quality.get("status") in {"needs_crux_work", "usable_with_review"}:
        candidates.append(_driver(63, "Relations exist, but cruxes are not yet concrete decision-changing uncertainties", "relation_to_crux_synthesis", [f"crux_score={crux_quality.get('score')}", f"generic={crux_quality.get('generic_crux_count')}", f"anchored={crux_quality.get('anchored_crux_count')}"], crux_quality.get("recommended_intervention", "Regenerate cruxes from graph tensions.")))
    if extraction.get("near_duplicate_pair_count", 0) or extraction.get("fragment_marker_count", 0):
        candidates.append(_driver(58, "Extraction still leaves duplicate or fragment noise that can distort synthesis", "extraction", [f"duplicates={extraction.get('near_duplicate_pair_count')}", f"fragments={extraction.get('fragment_marker_count')}"], "Tighten claim canonicalization before relation building and before final synthesis."))
    elif extraction.get("canonicalization_changed"):
        candidates.append(_driver(44, "Claim canonicalization changed the map before synthesis", "extraction", [f"merged_groups={extraction.get('canonicalized_duplicate_group_count')}", f"fragment_drops={extraction.get('canonicalized_fragment_drop_count')}"], "Inspect canonicalization report to ensure no decision-relevant minority claim was merged away."))
    if synthesis.get("validation_issue_count", 0):
        candidates.append(_driver(52, "The final decision packet fails or strains its briefing contract", "decision_synthesis", [f"validation_status={synthesis.get('validation_status')}", f"issues={synthesis.get('validation_issue_count')}"], "Use validation issues as repair instructions before accepting the memo."))
    if not candidates:
        candidates.append(_driver(20, "No dominant deterministic gap driver detected", "human_or_model_judgment", [], "Use a targeted model-judge or human review to inspect substantive judgment gaps."))
    ranked = sorted(candidates, key=lambda item: -int(item["_score"]))[:6]
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
        item.pop("_score", None)
    return ranked


def _obligation_summary(ledger: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": ledger.get("schema_id"),
        "obligation_count": ledger.get("obligation_count"),
        "satisfied_count": ledger.get("satisfied_count"),
        "missing_from_memo_count": ledger.get("missing_from_memo_count"),
        "source_missing_count": ledger.get("source_missing_count"),
        "status_counts": ledger.get("status_counts", {}),
        "missing_by_stage": ledger.get("missing_by_stage", {}),
        "top_missing_obligation_ids": [
            row.get("obligation_id")
            for row in ledger.get("top_missing_obligations", [])
            if isinstance(row, dict)
        ][:8],
        "recommended_interventions": ledger.get("recommended_interventions", []),
    }


def _unified_requirement_summary(ledger: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in ledger.get("rows", []) if isinstance(row, dict)]
    unresolved = [
        row.get("requirement_id")
        for row in rows
        if row.get("disposition") in {"missing", "source_missing", "needs_review"}
    ]
    return {
        "schema_id": ledger.get("schema_id"),
        "row_count": ledger.get("row_count"),
        "status_counts": ledger.get("status_counts", {}),
        "disposition_counts": ledger.get("disposition_counts", {}),
        "top_unresolved_requirement_ids": unresolved[:10],
    }


def _driver(score: int, gap: str, stage: str, evidence: list[Any], intervention: str) -> dict[str, Any]:
    return {"_score": score, "gap": gap, "likely_stage": stage, "evidence": evidence, "recommended_intervention": intervention}


def _gap(stage: str, explanation: str, evidence: list[str]) -> dict[str, Any]:
    return {"likely_stage": stage, "explanation": explanation, "evidence": evidence}


def _read_optional(repo_root: Path, path: str | Path | None) -> str:
    if not path:
        return ""
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = repo_root / resolved
    return resolved.read_text(encoding="utf-8") if resolved.exists() else ""


def _source_names(candidate_map: dict[str, Any]) -> list[str]:
    raw = candidate_map.get("sources", [])
    names = [str(item) for item in raw if str(item).strip()] if isinstance(raw, list) else []
    for claim in _claims(candidate_map):
        for key in ("source", "source_id"):
            value = str(claim.get(key, "")).strip()
            if value:
                names.append(value)
    return sorted(set(names))


def _source_display_names(scaffold: dict[str, Any]) -> list[str]:
    names = scaffold.get("source_display_names", {})
    if not isinstance(names, dict):
        return []
    return sorted({str(value).strip() for value in names.values() if str(value).strip()})


def _source_term_present(term: str, *, source_names: list[str], briefing_text: str) -> bool:
    normalized_term = _norm(term)
    if not normalized_term:
        return True
    searchable_text = _norm(" ".join([*source_names, briefing_text]))
    if normalized_term in searchable_text:
        return True
    source_token_sets = [set(_tokens(name)) for name in source_names]
    term_tokens = [token for token in _tokens(term) if not token.isdigit()]
    term_years = {token for token in _tokens(term) if re.fullmatch(r"(?:19|20)\d{2}", token)}
    term_acronyms = _term_acronyms(term)
    for name, tokens in zip(source_names, source_token_sets):
        name_text = _norm(name)
        name_years = {token for token in tokens if re.fullmatch(r"(?:19|20)\d{2}", token)}
        if term_years and name_years and not term_years.intersection(name_years):
            continue
        if term_acronyms.intersection(set(_tokens(name_text)) | _term_acronyms(name)):
            return True
        if term_tokens:
            overlap = len(set(term_tokens).intersection(tokens)) / len(set(term_tokens))
            if overlap >= 0.6 and (not term_years or term_years.intersection(name_years)):
                return True
    return False


def _term_acronyms(text: str) -> set[str]:
    tokens = [token for token in _tokens(text) if not token.isdigit()]
    acronyms: set[str] = set()
    for start in range(len(tokens)):
        for end in range(start + 2, min(len(tokens), start + 6) + 1):
            acronym = "".join(token[0] for token in tokens[start:end] if token)
            if 2 <= len(acronym) <= 8:
                acronyms.add(acronym)
    return acronyms


def _baseline_source_like_terms(text: str) -> list[str]:
    terms = set(re.findall(r"\b(?:[A-Z][A-Za-z]+(?:[- ][A-ZA-Za-z0-9]+){0,4}|[A-Z]{2,}(?:[- ][A-Z0-9]+)*)\s+(?:19|20)\d{2}\b", text))
    terms.update(re.findall(r"\b[A-Z][A-Za-z0-9-]{3,}\s+(?:trial|study|cohort|analysis|advisory|consensus)\b", text, flags=re.I))
    return sorted({term.strip(" -*`") for term in terms if len(term.strip()) >= 5})[:40]


def _salient_terms(text: str, question: str) -> list[str]:
    stop = set(_tokens(question)) | {"evidence", "baseline", "research", "decision", "source", "study", "studies"}
    candidates = set(_baseline_source_like_terms(text))
    for phrase in re.findall(r"\b[A-Z][A-Za-z0-9/-]{2,}(?:\s+[A-Z][A-Za-z0-9/-]{2,}){0,3}\b", text):
        if len(phrase) > 4 and _norm(phrase) not in stop:
            candidates.add(phrase)
    return sorted(candidates, key=lambda item: (-len(item.split()), item.lower()))[:50]


def _quality_issue_texts(report: dict[str, Any]) -> list[str]:
    issues = report.get("issues", [])
    if not isinstance(issues, list):
        return []
    return [str(issue.get("message", issue)) if isinstance(issue, dict) else str(issue) for issue in issues]


def _claims(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    value = candidate_map.get("claims", [])
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _relations(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    value = candidate_map.get("relations", [])
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _fragment_marker_count(text: str) -> int:
    return sum(text.lower().count(marker) for marker in ("...", "no. (%)", "pmcid:", "[google scholar]", "respectively. in"))


def _awkward_phrase_count(text: str) -> int:
    patterns = ("no clean mapped evidence", "compared whole-food exposure versus", "relation marks", "this source packet serves")
    return sum(text.lower().count(pattern) for pattern in patterns)


def _has_number(text: str) -> bool:
    return bool(re.search(r"\b\d|%|\bHR\b|\bRR\b|\bCI\b", text, flags=re.I))


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 3) if denominator else None


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _norm(text: str) -> str:
    return " ".join(_tokens(text))


def _compact_json(value: Any) -> str:
    import json

    return json.dumps(value, indent=2, sort_keys=True)
