from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from epistemic_case_mapper.submission_manifest import WorkedRegion
from epistemic_case_mapper.synthesis_uplift_packet import (
    _as_text,
    _claim_lookup,
    _clean_required_phrase,
    _is_meta_loss_text,
    _normalize_for_coverage,
    _packet_scaffold_prompt_block,
    _reader_claim_statement,
    _rel,
    _relation_lookup,
    _requirement_dict,
    _requirements_prompt_block,
    _run_synthesis_backend,
    _short_text,
    _truncate,
)
from epistemic_case_mapper.synthesis_uplift_types import Loss, RewriteRequirement


def _parse_losses(path: Path) -> list[Loss]:
    text = path.read_text(encoding="utf-8")
    starts = list(re.finditer(r"^loss_id:\s*([A-Za-z0-9_\-]+)\s*$", text, re.MULTILINE))
    losses: list[Loss] = []
    for index, match in enumerate(starts):
        start = match.start()
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        block = text[start:end]
        losses.append(
            Loss(
                loss_id=match.group(1),
                loss_type=_field(block, "loss_type"),
                lost_item=_field(block, "lost_item"),
                flat_baseline_omission=_field(block, "flat_baseline_omission"),
                case_map_preserves=_field(block, "case_map_preserves"),
            )
        )
    return losses


def _field(block: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\s*(.*?)(?=\n[a-z_]+:|\n\n[a-z_]+:|\Z)", block, re.MULTILINE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _synthesis_prompt(
    region: WorkedRegion,
    baseline: str,
    map_text: str,
    losses: list[Loss],
    requirements: tuple[RewriteRequirement, ...],
    stress_report: dict[str, Any] | None,
) -> str:
    loss_brief = "\n".join(
        f"- {loss.loss_id} ({loss.loss_type}): {loss.lost_item} Preserved by: {loss.case_map_preserves}"
        for loss in losses
    )
    stress_brief = "No stress report supplied."
    if stress_report is not None:
        stress_brief = _reference_safe_stress_brief(stress_report)
    requirement_brief = "No compiled rewrite requirements supplied."
    scaffold_brief = "No deterministic packet scaffold supplied."
    if requirements:
        requirement_brief = _requirements_prompt_block(requirements)
        scaffold_brief = _packet_scaffold_prompt_block(requirements)
    return "\n\n".join(
        (
            "You are revising a flat synthesis so it better preserves the decision space.",
            f"Region: {region.region_id}",
            "Write a concise decision-support packet for an informed reader. Return valid JSON only.",
            "Required JSON shape: "
            "{\"decision_brief\": \"readable bottom-line prose\", "
            "\"confidence\": \"low|medium|high\", "
            "\"decision_implications\": [\"action-relevant implication\"], "
            "\"top_cruxes\": [{\"crux\": \"...\", \"why_it_matters\": \"...\", \"current_read\": \"...\", \"would_change_if\": \"...\"}], "
            "\"evidence_roles\": {\"main_support\": [\"...\"], \"conflicting_evidence\": [\"...\"], \"scope_limits\": [\"...\"], \"method_limits\": [\"...\"]}, "
            "\"stress_caveats\": [\"decision-relevant caveat\"], "
            "\"audit_trail\": [\"map-backed distinction or source-role boundary\"]}",
            "Requirements:",
            "- Treat the validated rewrite requirements as the backbone of the synthesis.",
            "- Make the decision picture understandable before exposing the audit machinery.",
            "- Preserve the mapped claim and relation anchors before adding any stress finding.",
            "- Use stress findings only to add pressure, caveats, or uncertainty while preserving map distinctions.",
            "- Preserve cruxes, caveats, source-role boundaries, and load-bearing relations.",
            "- Put readable prose in `decision_brief`; put checklist-like coverage material in `audit_trail`, not in the prose.",
            "- Use `top_cruxes` only for distinctions that could change a decision or confidence level.",
            "- Use `evidence_roles` to separate support, conflict, scope limits, and method limits.",
            "- Write actual distinctions in words in reader-facing fields.",
            "- Keep uncertainty visible and use facts present in the provided artifacts.",
            "- Prefer explicit distinctions over fluent compression when the distinction changes interpretation.",
            "- If a stress finding conflicts with a mapped source-backed distinction, keep the mapped distinction and phrase the stress finding as a question or caveat.",
            "How to use the deterministic scaffold:",
            "- Treat scaffold entries as minimum packet content, not as final prose.",
            "- Every scaffold evidence-role item should appear in the returned `evidence_roles`, unless it is promoted to a crux or decision implication.",
            "- Use scaffold crux candidates as candidates, not mandatory headings; merge overlapping candidates if that makes the packet easier to read.",
            "- Preserve scaffold audit items in `audit_trail` using reader-facing wording.",
            "- Translate internal loss-analysis concepts into reader-facing wording.",
            "Deterministic packet scaffold:\n" + scaffold_brief,
            "Internal erosion-audit losses for diagnostic use only:\n" + loss_brief,
            "Validated rewrite requirements:\n" + requirement_brief,
            "Stress findings:\n" + stress_brief,
            "Flat baseline to revise:\n" + baseline,
            "Structured map artifact:\n" + _truncate(map_text, 14000),
        )
    )


def _reference_safe_stress_brief(stress_report: dict[str, Any]) -> str:
    failed_prompt_ids = {
        issue.get("prompt_id")
        for issue in stress_report.get("reference_issues", [])
        if isinstance(issue, dict) and isinstance(issue.get("prompt_id"), str)
    }
    lines = []
    dropped = sorted(prompt_id for prompt_id in failed_prompt_ids if prompt_id)
    if dropped:
        lines.append(
            "Dropped stress findings from prompts with deterministic reference failures: " + ", ".join(dropped)
        )
    for finding in stress_report.get("findings", []):
        if not isinstance(finding, dict):
            continue
        if finding.get("finding_type") == "reference_validation_issue":
            continue
        if finding.get("prompt_id") in failed_prompt_ids:
            continue
        lines.append(
            f"- {finding.get('severity', 'note')} {finding.get('finding_type', 'finding')}: {finding.get('reason', '')}"
        )
        if len(lines) >= 20:
            break
    return "\n".join(lines) if lines else "No reference-safe stress findings available."


def _compile_rewrite_requirements(
    losses: list[Loss],
    map_payload: dict[str, Any],
    stress_report: dict[str, Any],
) -> tuple[RewriteRequirement, ...]:
    claims = _claim_lookup(map_payload)
    relation_lookup = _relation_lookup(map_payload)
    safe_stress_terms = _safe_stress_terms(stress_report)
    requirements: list[RewriteRequirement] = []
    for index, loss in enumerate(losses, start=1):
        claim_ids, relation_ids = _preserved_ids(loss.case_map_preserves)
        source_refs = []
        claim_anchors = []
        relation_anchors = []
        claim_roles = []
        relation_types = []
        relation_rationales = []
        reader_anchors = []
        fallback_term_source = " ".join((loss.loss_type, loss.lost_item, loss.flat_baseline_omission))
        map_term_parts: list[str] = []
        for claim_id in claim_ids:
            claim = claims.get(claim_id)
            if claim is None:
                continue
            map_term_parts.append(_claim_text(claim))
            claim_anchors.append(f"{claim_id}: {_claim_statement(claim)}")
            claim_role = _as_text(claim.get("role") or claim.get("claim_type"))
            if claim_role:
                claim_roles.append(claim_role)
            reader_claim = _reader_claim_statement(claim)
            if reader_claim:
                reader_anchors.append(reader_claim)
            source_id = _as_text(claim.get("source_id"))
            source_span = _as_text(claim.get("source_span"))
            if source_id:
                source_refs.append(f"{source_id} {source_span}".strip())
        for relation_id in relation_ids:
            relation = relation_lookup.get(relation_id)
            if relation is None:
                continue
            relation_type = _as_text(relation.get("relation_type"))
            rationale = _as_text(relation.get("rationale"))
            map_term_parts.append(relation_type + " " + rationale)
            relation_anchors.append(f"{relation_id}: {_relation_statement(relation)}")
            if relation_type:
                relation_types.append(relation_type)
            if rationale:
                relation_rationales.append(rationale)
            reader_relation = _reader_relation_statement_from_claims(relation, claims)
            if reader_relation:
                reader_anchors.append(reader_relation)
        for stress_terms in safe_stress_terms:
            if _loss_overlap(loss, stress_terms):
                map_term_parts.append(" ".join(stress_terms))
        term_source = " ".join(part for part in map_term_parts if part) or fallback_term_source
        terms = _coverage_terms(term_source)
        phrases = _required_phrases(loss, claim_anchors, relation_anchors)
        requirements.append(
            RewriteRequirement(
                requirement_id=f"req_{index:03d}",
                loss_id=loss.loss_id,
                loss_type=loss.loss_type.strip("`"),
                instruction=_requirement_instruction(loss),
                claim_ids=tuple(claim_id for claim_id in claim_ids if claim_id in claims),
                relation_ids=tuple(relation_id for relation_id in relation_ids if relation_id in relation_lookup),
                source_refs=tuple(dict.fromkeys(source_refs)),
                claim_anchors=tuple(claim_anchors),
                relation_anchors=tuple(relation_anchors),
                required_phrases=tuple(phrases),
                required_terms=tuple(terms),
                claim_roles=tuple(dict.fromkeys(claim_roles)),
                relation_types=tuple(dict.fromkeys(relation_types)),
                relation_rationales=tuple(dict.fromkeys(relation_rationales)),
                reader_anchors=tuple(dict.fromkeys(reader_anchors)),
            )
        )
    return tuple(requirements)


def _requirement_instruction(loss: Loss) -> str:
    omission = loss.flat_baseline_omission or "The flat baseline compresses a loss-critical distinction."
    return (
        f"Preserve the `{loss.loss_type.strip('`')}` distinction from {loss.loss_id}: "
        f"{loss.lost_item} Explicitly avoid this baseline failure: {omission}"
    )


def _preserved_ids(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    claim_ids = tuple(dict.fromkeys(re.findall(r"\b[A-Za-z0-9_\-]+_c\d+\b", text)))
    relation_ids = tuple(dict.fromkeys(re.findall(r"\b[A-Za-z0-9_\-]+_r\d+\b", text)))
    return claim_ids, relation_ids








def _claim_text(claim: dict[str, Any]) -> str:
    return " ".join(
        _as_text(claim.get(key))
        for key in ("claim", "text", "role", "source_id", "source_span", "excerpt")
    )


def _claim_statement(claim: dict[str, Any]) -> str:
    statement = _as_text(claim.get("claim") or claim.get("text"))
    role = _as_text(claim.get("role") or claim.get("claim_type"))
    source_id = _as_text(claim.get("source_id"))
    source_span = _as_text(claim.get("source_span"))
    parts = [statement]
    if role:
        parts.append(f"role={role}")
    if source_id:
        parts.append(f"source={source_id} {source_span}".strip())
    return "; ".join(part for part in parts if part)


def _relation_statement(relation: dict[str, Any]) -> str:
    source_claim = _as_text(relation.get("source_claim") or relation.get("source_claim_id"))
    target_claim = _as_text(relation.get("target_claim") or relation.get("target_claim_id"))
    relation_type = _as_text(relation.get("relation_type"))
    rationale = _as_text(relation.get("rationale"))
    edge = f"{source_claim} -> {target_claim}".strip()
    return "; ".join(part for part in (edge, relation_type, rationale) if part)


def _reader_relation_statement_from_claims(
    relation: dict[str, Any],
    claims: dict[str, dict[str, Any]],
) -> str:
    source_claim = _as_text(relation.get("source_claim") or relation.get("source_claim_id"))
    target_claim = _as_text(relation.get("target_claim") or relation.get("target_claim_id"))
    source_text = _reader_claim_statement(claims.get(source_claim, {}))
    target_text = _reader_claim_statement(claims.get(target_claim, {}))
    relation_type = _as_text(relation.get("relation_type"))
    rationale = _as_text(relation.get("rationale"))
    if rationale:
        return rationale
    if source_text and target_text and relation_type:
        return f"{_short_text(source_text, 120)} {relation_type} {_short_text(target_text, 120)}"
    return _relation_statement(relation)


def _safe_stress_terms(stress_report: dict[str, Any]) -> list[tuple[str, ...]]:
    failed_prompt_ids = {
        issue.get("prompt_id")
        for issue in stress_report.get("reference_issues", [])
        if isinstance(issue, dict) and isinstance(issue.get("prompt_id"), str)
    }
    terms = []
    for finding in stress_report.get("findings", []):
        if not isinstance(finding, dict):
            continue
        if finding.get("finding_type") == "reference_validation_issue":
            continue
        if finding.get("prompt_id") in failed_prompt_ids:
            continue
        reason = _as_text(finding.get("reason"))
        if reason:
            terms.append(tuple(_coverage_terms(reason)))
    return terms


def _loss_overlap(loss: Loss, terms: tuple[str, ...]) -> bool:
    text = _normalize_for_coverage(" ".join((loss.loss_type, loss.lost_item, loss.flat_baseline_omission)))
    return any(term in text for term in terms[:8])


def _coverage_terms(text: str) -> list[str]:
    normalized = _normalize_for_coverage(text)
    candidates = re.findall(r"[a-z][a-z0-9\-]{3,}", normalized)
    stopwords = {
        "about",
        "after",
        "against",
        "also",
        "baseline",
        "because",
        "claim",
        "claims",
        "does",
        "doesn",
        "evidence",
        "explicit",
        "flat",
        "from",
        "into",
        "loss",
        "make",
        "more",
        "preserve",
        "preserves",
        "rather",
        "relation",
        "review",
        "source",
        "than",
        "that",
        "their",
        "this",
        "with",
        "without",
    }
    ordered = []
    for candidate in candidates:
        if candidate in stopwords or candidate.endswith("_id"):
            continue
        if candidate not in ordered:
            ordered.append(candidate)
    return ordered[:14]


def _required_phrases(
    loss: Loss,
    claim_anchors: list[str],
    relation_anchors: list[str],
) -> list[str]:
    anchor_candidates = _phrase_candidates([*claim_anchors, *relation_anchors])
    if anchor_candidates:
        return anchor_candidates[:4]
    return _phrase_candidates([loss.lost_item, loss.flat_baseline_omission])[:4]


def _phrase_candidates(texts: list[str]) -> list[str]:
    candidates: list[str] = []
    for text in texts:
        for sentence in re.split(r"(?<=[.!?])\s+|;\s+", text):
            phrase = _clean_required_phrase(sentence)
            if not phrase:
                continue
            if _is_meta_loss_text(phrase):
                continue
            if _is_directional_or_boundary_phrase(phrase) and phrase not in candidates:
                candidates.append(phrase)
    return candidates




def _is_directional_or_boundary_phrase(text: str) -> bool:
    normalized = _normalize_for_coverage(text)
    markers = (
        " than ",
        " rather than ",
        " versus ",
        " vs ",
        " between ",
        " separate ",
        " distinguish",
        " distinct ",
        " depends on",
        " requires ",
        " may be ",
        " not ",
        " does not ",
        " cannot ",
    )
    return any(marker in f" {normalized} " for marker in markers)
