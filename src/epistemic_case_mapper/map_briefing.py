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
    _render_unparsed_structured_packet,
)


ROLE_PRIORITY = {
    "crux": 0,
    "scope_limit": 1,
    "implementation_constraint": 2,
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
    max_claims: int = 18,
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
    prioritized_map, prioritization_report = prioritize_map_for_briefing(
        candidate_map,
        quality_report=quality_report,
        max_claims=max_claims,
    )
    erosion_audit = generated_map_erosion_audit(prioritized_map)
    scaffold = briefing_scaffold(prioritized_map, quality_report, source_lookup, erosion_audit)
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
    write_markdown(prompt_path, prompt)
    write_json(prioritized_map_path, prioritized_map)
    write_json(prioritization_report_path, prioritization_report)
    write_json(erosion_audit_path, erosion_audit)

    result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    raw_path = artifacts / "map_briefing_raw.txt"
    write_markdown(raw_path, result.text)
    if result.prompt_only:
        rendered = prompt
        model_confidence = "not specified"
        calibrated = calibrate_confidence(model_confidence, quality_report)["calibrated_confidence"]
        parse_ok = False
    else:
        payload = _parse_json(result.text)
        parse_ok = isinstance(payload, dict)
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
            rendered = _render_unparsed_structured_packet(result.text)
            rendered = _replace_confidence_line(rendered, calibrated)
        else:
            model_confidence = "not specified"
            calibration = calibrate_confidence(model_confidence, quality_report)
            calibrated = calibration["calibrated_confidence"]
            rendered = result.text.strip()
    if not result.prompt_only:
        calibration = calibrate_confidence(model_confidence, quality_report)
    rendered = _ensure_confidence_visible(rendered, calibrated)
    rendered = _normalize_reader_punctuation(expand_reader_map_references(rendered, prioritized_map))
    rendered = _clean_reader_packet_metadata(replace_source_ids(rendered, source_lookup))
    briefing_path = artifacts / "BRIEFING.md"
    summary_path = artifacts / "briefing_summary.json"
    write_markdown(briefing_path, rendered.rstrip() + "\n")
    write_json(
        summary_path,
        {
            "schema_id": "map_briefing_v1",
            "backend": result.backend,
            "parse_ok": parse_ok,
            "question": question,
            "paths": {
                "briefing": _rel(repo_root, briefing_path),
                "prompt": _rel(repo_root, prompt_path),
                "raw": _rel(repo_root, raw_path),
                "prioritized_map": _rel(repo_root, prioritized_map_path),
                "prioritization_report": _rel(repo_root, prioritization_report_path),
                "generated_map_erosion_audit": _rel(repo_root, erosion_audit_path),
            },
            "source_display_names": source_lookup,
            "map_quality_status": str(quality_report.get("status", "unknown")),
            "map_quality_score": quality_report.get("score"),
            "model_confidence": model_confidence,
            "calibrated_confidence": calibrated,
            "confidence_reasons": calibration["reasons"],
            "claim_count": len(_claims(candidate_map)),
            "prioritized_claim_count": len(_claims(prioritized_map)),
            "relation_count": len(_relations(candidate_map)),
            "prioritized_relation_count": len(_relations(prioritized_map)),
            "audit_item_count": len(erosion_audit.get("items", [])),
        },
    )
    return MapBriefingResult(
        briefing_path=briefing_path,
        summary_path=summary_path,
        prompt_path=prompt_path,
        prioritized_map_path=prioritized_map_path,
        prioritization_report_path=prioritization_report_path,
        erosion_audit_path=erosion_audit_path,
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
            "Return valid JSON only.",
            "Required JSON shape: "
            "{\"decision_brief\": \"readable bottom-line prose\", "
            "\"confidence\": \"low|medium|high\", "
            "\"decision_implications\": [\"action-relevant implication\"], "
            "\"top_cruxes\": [{\"crux\": \"...\", \"why_it_matters\": \"...\", \"current_read\": \"...\", \"would_change_if\": \"...\"}], "
            "\"evidence_roles\": {\"main_support\": [\"...\"], \"conflicting_evidence\": [\"...\"], \"scope_limits\": [\"...\"], \"method_limits\": [\"...\"]}, "
            "\"stress_caveats\": [\"decision-relevant caveat\"], "
            "\"audit_trail\": [\"map-backed distinction or source-role boundary\"]}",
            "Rules:",
            "- Answer the decision question directly, then explain the map-backed cruxes.",
            "- Use the deterministic scaffold as minimum content, not final wording.",
            "- Preserve tensions, scope limits, and method limits; do not flatten them into a single confident answer.",
            "- Use source display names, not raw source IDs, claim IDs, or relation IDs, in reader-facing fields.",
            "- Every evidence_roles bullet must be a substantive evidence statement, not just a source name.",
            "- An evidence_roles bullet is invalid if it only says which source exists; include the relevant claim and put the source in parentheses.",
            "- Do not invent facts beyond the map, quality report, or erosion audit.",
            "- Calibrate uncertainty to the quality report. A map marked review_recommended or needs_repair cannot support high confidence.",
            "- Keep the briefing concise and readable for a human judge.",
            f"Decision question: {question}",
            "Deterministic briefing scaffold:\n" + json.dumps(scaffold, indent=2),
            "Map quality report:\n" + json.dumps(_quality_brief(quality_report), indent=2),
            "Prioritized map artifact:\n" + json.dumps(candidate_map, indent=2),
        )
    )


def briefing_scaffold(
    candidate_map: dict[str, Any],
    quality_report: dict[str, Any],
    source_lookup: dict[str, str],
    erosion_audit: dict[str, Any],
) -> dict[str, Any]:
    claims = _claims(candidate_map)
    relations = _relations(candidate_map)
    claim_lookup = {str(claim.get("claim_id")): claim for claim in claims}
    evidence_roles = {
        "main_support": [],
        "conflicting_evidence": [],
        "scope_limits": [],
        "method_limits": [],
    }
    for claim in claims:
        text = _claim_reader_text(claim, source_lookup)
        role = str(claim.get("role", "other"))
        if role == "conclusion_support":
            evidence_roles["main_support"].append(text)
        elif role in {"crux", "scope_limit"}:
            evidence_roles["scope_limits"].append(text)
        elif role == "implementation_constraint":
            evidence_roles["method_limits"].append(text)
    cruxes = []
    audit_trail = []
    for relation in relations:
        reader = _relation_reader_text(relation, claim_lookup, source_lookup)
        relation_type = str(relation.get("relation_type", ""))
        if relation_type in {"in_tension_with", "challenges"}:
            evidence_roles["conflicting_evidence"].append(reader)
        elif relation_type in {"depends_on", "crux_for"}:
            cruxes.append(
                {
                    "candidate_crux": reader,
                    "why_it_matters": "This relation changes how strongly the mapped conclusion can be used.",
                }
            )
        audit_trail.append(reader)
    for item in erosion_audit.get("items", []):
        if isinstance(item, dict) and item.get("reader_anchor"):
            audit_trail.append(str(item["reader_anchor"]))
    scaffold = {
        "quality_status": quality_report.get("status"),
        "quality_score": quality_report.get("score"),
        "confidence_cap": confidence_cap(quality_report),
        "evidence_roles": {key: _dedupe(items)[:8] for key, items in evidence_roles.items()},
        "crux_candidates": _dedupe_dicts(cruxes)[:6],
        "audit_trail": _dedupe(audit_trail)[:10],
        "source_display_names": source_lookup,
        "quality_issues": [
            f"{issue.get('severity')}: {issue.get('issue_type')} - {issue.get('message')}"
            for issue in quality_report.get("issues", [])
            if isinstance(issue, dict)
        ][:8],
    }
    return _expand_payload_reader_references(scaffold, candidate_map)


def repair_briefing_payload(
    payload: dict[str, Any],
    scaffold: dict[str, Any],
    source_lookup: dict[str, str],
    candidate_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repaired = dict(payload)
    evidence_roles = repaired.get("evidence_roles")
    if not isinstance(evidence_roles, dict):
        evidence_roles = {}
    repaired_roles: dict[str, list[str]] = {}
    scaffold_roles = scaffold.get("evidence_roles", {})
    source_names = set(source_lookup.values())
    for role_key in ("main_support", "conflicting_evidence", "scope_limits", "method_limits"):
        model_items = _string_list(evidence_roles.get(role_key))
        substantive = [
            item
            for item in model_items
            if _is_substantive_evidence_statement(item, source_names)
        ]
        for scaffold_item in _string_list(scaffold_roles.get(role_key)):
            if _similar_text_exists(substantive, scaffold_item):
                continue
            substantive.append(scaffold_item)
        repaired_roles[role_key] = _dedupe(substantive)[:8]
    repaired["evidence_roles"] = repaired_roles
    audit = _string_list(repaired.get("audit_trail"))
    for item in _string_list(scaffold.get("audit_trail")):
        if not _similar_text_exists(audit, item):
            audit.append(item)
    repaired["audit_trail"] = _dedupe(audit)[:10]
    if candidate_map is not None:
        repaired = _expand_payload_reader_references(repaired, candidate_map)
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
    if len(claims) <= max_claims:
        return dict(candidate_map), {
            "schema_id": "map_prioritization_report_v1",
            "changed": False,
            "reason": "claim_count_within_budget",
            "ranking_method": "role_priority_plus_weighted_pagerank",
            "claim_count": len(claims),
            "max_claims": max_claims,
            "kept_claim_ids": [claim.get("claim_id") for claim in claims],
            "dropped_claim_ids": [],
            "duplicate_claim_pairs": _duplicate_pair_rows(duplicate_pairs),
            "centrality_scores": centrality,
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
    return prioritized, {
        "schema_id": "map_prioritization_report_v1",
        "changed": True,
        "reason": "claim_count_exceeded_briefing_budget",
        "ranking_method": "source_coverage_then_role_priority_weighted_pagerank_with_tfidf_duplicate_suppression",
        "quality_status": quality_report.get("status"),
        "claim_count": len(claims),
        "max_claims": max_claims,
        "kept_claim_ids": [str(claim.get("claim_id")) for claim in kept],
        "dropped_claim_ids": dropped,
        "duplicate_claim_pairs": _duplicate_pair_rows(duplicate_pairs),
        "centrality_scores": centrality,
        "source_coverage_preserved": _source_order(claims) == _source_order(kept),
        "relation_count": len(relations),
        "kept_relation_count": len(kept_relations),
    }


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


def _claim_rank(claim: dict[str, Any], centrality: dict[str, float]) -> tuple[int, float, str]:
    claim_id = str(claim.get("claim_id", ""))
    return (
        ROLE_PRIORITY.get(str(claim.get("role", "other")), ROLE_PRIORITY["other"]),
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
    text = str(claim.get("claim") or claim.get("text") or "").strip()
    source_id = str(claim.get("source_id", "")).strip()
    source = source_lookup.get(source_id, display_source_name(source_id)) if source_id else ""
    if source:
        return f"{text} ({source})"
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


def _rel(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()
