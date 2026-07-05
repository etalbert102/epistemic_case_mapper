from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epistemic_case_mapper.classical_ml import diverse_ranked_edges, tfidf_near_duplicate_pairs, tfidf_pair_similarities
from epistemic_case_mapper.config_profiles import (
    EpistemicConfigProfile,
    config_profile_from_manifest_payload,
    profile_vocabulary,
)
from epistemic_case_mapper.io import read_yaml, write_json, write_markdown
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.prompt_templates import examples_block, json_schema_block, render_prompt, xml_block
from epistemic_case_mapper.schema import CaseManifest, Source
from epistemic_case_mapper.semantic_pipeline import MAP_PROMPT_VERSION, VALID_ENTAILMENT, validate_map_candidate
from epistemic_case_mapper.staged_semantic_prompt_schemas import (
    relation_batch_prompt_schema,
    relation_examples,
    relation_prompt_schema,
)
from epistemic_case_mapper.submission_manifest import SubmissionManifest, WorkedRegion, load_submission_manifest

def _relation_pair_prompt(
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    packet: dict[str, Any],
) -> str:
    left = packet["left"]
    right = packet["right"]
    relation_types = ", ".join(sorted(manifest.relation_ontology.permitted_types()))
    scaffold = json.dumps(_map_quality_scaffold(manifest, region, case_manifest), indent=2)
    profile_rules = _profile_relation_rule_text(case_manifest)
    return render_prompt(
        ("Task", "You are classifying one possible relation between two already-validated claim cards."),
        ("Metadata", f"Prompt version: {RELATION_PROMPT_VERSION}\nRegion ID: {region.region_id}\nPair ID: {packet['pair_id']}\nCase question: {case_manifest.question}\nAllowed relation types:\n{relation_types}"),
        ("Rules", _relation_rules(profile_rules)),
        ("Output Schema", json_schema_block(relation_prompt_schema(packet["pair_id"], relation_types))),
        ("Examples", examples_block(relation_examples())),
        (
            "Context",
            "\n\n".join(
                (
                    f"Claim A:\n{_relation_claim_card(left, 'A')}",
                    f"Claim B:\n{_relation_claim_card(right, 'B')}",
                    xml_block("deterministic_map_quality_scaffold", f"Deterministic map-quality scaffold:\n{scaffold}"),
                )
            ),
        ),
    )

def _relation_batch_prompt(
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    packets: list[dict[str, Any]],
    batch_id: str,
) -> str:
    relation_types = ", ".join(sorted(manifest.relation_ontology.permitted_types()))
    pair_blocks = "\n\n".join(_relation_pair_block(packet) for packet in packets)
    pair_ids = ", ".join(packet["pair_id"] for packet in packets)
    scaffold = json.dumps(_map_quality_scaffold(manifest, region, case_manifest), indent=2)
    profile_rules = _profile_relation_rule_text(case_manifest)
    return render_prompt(
        ("Task", "You are classifying possible relations between already-validated claim cards."),
        ("Metadata", f"Prompt version: {RELATION_BATCH_PROMPT_VERSION}\nRegion ID: {region.region_id}\nBatch ID: {batch_id}\nCase question: {case_manifest.question}\nAllowed relation types:\n{relation_types}"),
        ("Rules", ["- Return exactly one object for each pair ID in this batch.", *_relation_rules(profile_rules)]),
        ("Output Schema", json_schema_block(relation_batch_prompt_schema(pair_ids, relation_types))),
        ("Examples", examples_block(relation_examples())),
        (
            "Context",
            "\n\n".join(
                (
                    f"Pairs to classify:\n{pair_blocks}",
                    xml_block("deterministic_map_quality_scaffold", f"Deterministic map-quality scaffold:\n{scaffold}"),
                )
            ),
        ),
    )

def _relation_rules(profile_rules: str) -> list[str]:
    rules = [
        "- Do not include relation_id. Deterministic code assigns IDs later.",
        "- Use only the claim IDs shown in the pair.",
        '- Use only allowed relation types, or use relation_type "none".',
        "- Use the map-quality scaffold to preserve cruxes, tensions, source limits, and scope boundaries.",
        "- Prefer decision-relevant relations over generic links.",
        "- Use crux_for when one claim would change the decision read of the other.",
        "- Use depends_on when a recommendation or conclusion only works under a condition.",
        "- Use in_tension_with or challenges when a scope limit or contrary finding weakens another claim.",
        "- Fill the relation evidence contract for every non-none relation.",
        "- Ground anchors in visible excerpt phrases rather than introducing new facts.",
    ]
    if profile_rules.strip():
        rules.append(profile_rules.strip())
    rules.extend(
        [
            "- Use similar_to only when the claims are redundant enough that a reviewer could merge them.",
            "- Use refines only when the rationale names the boundary, population, endpoint, mechanism, or condition being refined.",
            '- If no defensible relation exists, set source_claim and target_claim to null and relation_type "none".',
        ]
    )
    return rules

def _relation_pair_block(packet: dict[str, Any]) -> str:
    left = packet["left"]
    right = packet["right"]
    return f"""Pair ID: {packet['pair_id']}
Claim A:
{_relation_claim_card(left, "A")}

Claim B:
{_relation_claim_card(right, "B")}

Candidate-pair reason: {packet.get('candidate_reason', 'not recorded')}
Candidate-pair score: {packet.get('candidate_score', 'not recorded')}"""

def _relation_claim_card(claim: dict[str, Any], label: str) -> str:
    return "\n".join(
        [
            f"- claim_id: {claim.get('claim_id')}",
            f"- claim: {_compact_relation_text(str(claim.get('claim', '')), max_chars=300)}",
            f"- source_id: {claim.get('source_id')}",
            f"- role: {claim.get('role')}",
            f"- excerpt_{label}: {_compact_relation_text(str(claim.get('excerpt', '')), max_chars=360)}",
        ]
    )

def _compact_relation_text(text: str, *, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    kept: list[str] = []
    for sentence in sentences:
        candidate = " ".join([*kept, sentence]).strip()
        if len(candidate) > max_chars:
            break
        kept.append(sentence)
        if len(kept) >= 3:
            break
    return " ".join(kept) if kept else cleaned[: max_chars - 1].rstrip(" ,.;") + "..."

def _normalize_claim_proposal(
    proposal: Any,
    span_lookup: dict[str, SourceSpan],
    valid_roles: set[str] | None = None,
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(proposal, dict):
        return None, "claim_not_object"
    span_id = str(proposal.get("span_id", proposal.get("spanId", ""))).strip()
    if span_id not in span_lookup:
        return None, "unknown_span_id"
    span = span_lookup[span_id]
    claim_text = str(proposal.get("claim", "")).strip()
    if not claim_text:
        return None, "missing_claim"
    entailed = str(proposal.get("entailed_by_excerpt", "uncertain")).strip().lower()
    if entailed not in VALID_ENTAILMENT:
        entailed = "uncertain"
    role = str(proposal.get("role", "other")).strip()
    allowed_roles = valid_roles or VALID_CLAIM_ROLES
    if role not in allowed_roles:
        role = "other"
    if role not in allowed_roles:
        role = sorted(allowed_roles)[0] if allowed_roles else "other"
    return (
        {
            "claim_id": "",
            "claim": claim_text,
            "source_id": span.source_id,
            "source_span": span.source_span,
            "excerpt": span.text,
            "entailed_by_excerpt": entailed,
            "role": role,
        },
        "",
    )

def _fallback_claim_for_chunk(chunk: SourceChunk) -> dict[str, Any] | None:
    span = _best_fallback_span(chunk)
    if span is None:
        return None
    return {
        "claim_id": "",
        "claim": span.text,
        "source_id": span.source_id,
        "source_span": span.source_span,
        "excerpt": span.text,
        "entailed_by_excerpt": "yes",
        "role": _fallback_role(span.text),
        "span_id": span.span_id,
        "extraction_method": "deterministic_fallback_span",
    }

def _best_fallback_span(chunk: SourceChunk) -> SourceSpan | None:
    candidates = [span for span in chunk.spans if _span_signal_score(span.text) > 0]
    if not candidates:
        return None
    return max(candidates, key=lambda span: (_span_signal_score(span.text), len(span.text)))

def _span_signal_score(text: str) -> int:
    stripped = text.strip()
    lowered = stripped.lower()
    if not stripped or stripped.startswith("#"):
        return 0
    if lowered.startswith(("source:", "author:", "date:", "retrieved:", "use in worked region:")):
        return 0
    score = 1
    for marker in (
        "%",
        "odds",
        "bayes",
        "favor",
        "likely",
        "disagreement",
        "challenge",
        "critique",
        "not measure",
        "limitation",
        "failed",
        "won",
        "risk",
        "could",
    ):
        if marker in lowered:
            score += 2
    return score

def _fallback_role(text: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in ("not measure", "not peer reviewed", "limitation", "failed", "risk")):
        return "scope_limit"
    if any(marker in lowered for marker in ("disagreement", "critique", "challenge")):
        return "crux"
    if any(marker in lowered for marker in ("favor", "likely", "%", "odds")):
        return "conclusion_support"
    return "background"

def _normalize_relation_proposal(
    proposal: Any,
    claim_ids: set[str],
    permitted_types: set[str],
    packet: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(proposal, dict):
        return None, "relation_not_object"
    if str(proposal.get("pair_id", packet["pair_id"])).strip() != packet["pair_id"]:
        return None, "wrong_pair_id"
    source_claim = str(proposal.get("source_claim", "")).strip()
    target_claim = str(proposal.get("target_claim", "")).strip()
    relation_type = str(proposal.get("relation_type", "")).strip()
    rationale = str(proposal.get("rationale", "")).strip()
    if relation_type == "none":
        return None, "no_relation"
    if source_claim not in claim_ids or target_claim not in claim_ids:
        return None, "unknown_endpoint"
    packet_ids = {packet["left"]["claim_id"], packet["right"]["claim_id"]}
    if source_claim not in packet_ids or target_claim not in packet_ids:
        return None, "endpoint_not_in_pair"
    if source_claim == target_claim:
        return None, "self_relation"
    if relation_type not in permitted_types:
        return None, "unknown_relation_type"
    if not rationale:
        return None, "missing_rationale"
    contract = _relation_contract(proposal, packet, rationale)
    confidence = _relation_confidence(proposal, contract)
    return (
        {
            "relation_id": "",
            "source_claim": source_claim,
            "target_claim": target_claim,
            "relation_type": relation_type,
            "rationale": rationale,
            "relation_confidence": confidence,
            "relation_provenance": "model_classified",
            "requires_review": confidence == "low",
            "relation_contract": contract,
            "candidate_pair": _candidate_pair_metadata(packet),
        },
        "",
    )

def _candidate_relation_pairs(claims: list[dict[str, Any]], max_pairs: int) -> list[dict[str, Any]]:
    usable_claims = [claim for claim in claims if _usable_relation_claim(claim)]
    if len(usable_claims) < 2:
        usable_claims = claims
    claim_lookup = {str(claim.get("claim_id", "")): claim for claim in usable_claims if claim.get("claim_id")}
    claim_order = {str(claim.get("claim_id", "")): index for index, claim in enumerate(claims)}
    tfidf_scores = _claim_tfidf_scores(usable_claims)
    scored: list[tuple[str, str, float, str]] = []
    for left_index, left in enumerate(usable_claims):
        for right_index, right in enumerate(usable_claims):
            if left_index >= right_index:
                continue
            score, reason = _pair_score(left, right, tfidf_scores)
            if score <= 0:
                continue
            scored.append((left["claim_id"], right["claim_id"], score, reason))
    selected = diverse_ranked_edges(
        [claim_id for claim_id in claim_order if claim_id],
        scored,
        limit=max_pairs,
    )
    packets = []
    ordered = sorted(selected, key=lambda item: (claim_order.get(item[0], 9999), claim_order.get(item[1], 9999)))
    for index, (left_id, right_id, score, reason) in enumerate(ordered, start=1):
        packets.append(
            {
                "pair_id": f"pair_{index:03d}",
                "left": claim_lookup[left_id],
                "right": claim_lookup[right_id],
                "candidate_score": score,
                "candidate_reason": reason,
            }
        )
    return packets

def _usable_relation_claim(claim: dict[str, Any]) -> bool:
    text = re.sub(r"\s+", " ", str(claim.get("claim", "") or claim.get("excerpt", ""))).strip()
    lowered = text.lower()
    role = str(claim.get("role", ""))
    if len(text) < 18 and role not in {"crux", "conclusion_support", "scope_limit", "implementation_constraint"}:
        return False
    if _looks_like_relation_reference_or_boilerplate(text):
        return False
    if any(marker in lowered for marker in ("[google scholar]", "privacy policy", "nutrition policy", "no. (%)", "pmcid:", "copyright")):
        return False
    if re.fullmatch(r"[\w\s,./()%+-]+", text) and len(_content_terms(text)) <= 3:
        return False
    if re.fullmatch(r"(?:pooled\s+)?(?:relative\s+)?risk\s*\(?95%?\s*ci\)?", lowered):
        return False
    return True

def _looks_like_relation_reference_or_boilerplate(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"\bdoi\b|\bpmid\b|\bgoogle scholar\b|\bcrossref\b", lowered):
        return True
    if lowered.count("received ") >= 2 and len(lowered) > 400:
        return True
    return False

def _fallback_relation(pair_packets: list[dict[str, Any]], permitted_types: set[str]) -> dict[str, Any] | None:
    if not pair_packets:
        return None
    packet = pair_packets[0]
    left = packet["left"]
    right = packet["right"]
    relation_type = _fallback_relation_type(left, right, permitted_types)
    if relation_type is None:
        return None
    return {
        "relation_id": "",
        "source_claim": left["claim_id"],
        "target_claim": right["claim_id"],
        "relation_type": relation_type,
        "rationale": (
            "Deterministic fallback edge: these high-priority cross-source claims were selected as a likely "
            "reasoning dependency after model relation classification produced no accepted edge. Human review "
            "should confirm the exact relation type before treating it as substantive."
        ),
        "relation_confidence": "low",
        "relation_provenance": "deterministic_fallback",
        "requires_review": True,
        "relation_contract": _fallback_relation_contract(left, right),
        "candidate_pair": _candidate_pair_metadata(packet),
        "extraction_method": "deterministic_fallback_pair",
    }

def _fallback_relation_type(left: dict[str, Any], right: dict[str, Any], permitted_types: set[str]) -> str | None:
    left_text = _normalize_text(f"{left.get('claim', '')} {left.get('excerpt', '')}")
    right_text = _normalize_text(f"{right.get('claim', '')} {right.get('excerpt', '')}")
    combined = f"{left_text} {right_text}"
    if "in_tension_with" in permitted_types and _looks_like_tension(left_text, right_text):
        return "in_tension_with"
    if "challenges" in permitted_types and any(
        marker in combined
        for marker in (
            "flawed",
            "no evidence",
            "not require",
            "without requiring",
            "critique",
            "reject",
            "failed",
        )
    ):
        return "challenges"
    if "crux_for" in permitted_types and {left.get("role"), right.get("role")} & {"crux"}:
        return "crux_for"
    if "refines" in permitted_types:
        return "refines"
    return next(iter(sorted(permitted_types)), None)

def _looks_like_tension(left_text: str, right_text: str) -> bool:
    return (
        _has_support_signal(left_text) and _has_limit_or_challenge_signal(right_text)
    ) or (
        _has_support_signal(right_text) and _has_limit_or_challenge_signal(left_text)
    )

def _claim_tfidf_scores(claims: list[dict[str, Any]]) -> dict[tuple[str, str], float]:
    ids = [str(claim.get("claim_id", "")) for claim in claims]
    texts = [_claim_pair_text(claim) for claim in claims]
    return tfidf_pair_similarities(texts, ids)

def _claim_pair_text(claim: dict[str, Any]) -> str:
    return " ".join(
        str(claim.get(key, ""))
        for key in ("claim", "excerpt", "role", "source_id")
    )

def _pair_score(
    left: dict[str, Any],
    right: dict[str, Any],
    tfidf_scores: dict[tuple[str, str], float] | None = None,
) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []
    if left.get("source_id") != right.get("source_id"):
        score += 3
        reasons.append("cross_source")
    left_role = str(left.get("role", ""))
    right_role = str(right.get("role", ""))
    role_reason, role_score = _role_pair_priority(left_role, right_role)
    if role_score:
        score += role_score
        reasons.append(role_reason)
    if "crux" in {left_role, right_role}:
        score += 4
        reasons.append("crux_pair")
    if {left_role, right_role} & {"scope_limit", "implementation_constraint"}:
        score += 3
        reasons.append("scope_or_implementation_pair")
    if {left_role, right_role} & {"conclusion_support"}:
        score += 2
        reasons.append("support_pair")
    left_text = _normalize_text(f"{left.get('claim', '')} {left.get('excerpt', '')}")
    right_text = _normalize_text(f"{right.get('claim', '')} {right.get('excerpt', '')}")
    if _looks_like_tension(left_text, right_text):
        score += 6
        reasons.append("support_limit_tension")
    semantic_score = _semantic_pair_score(left, right, tfidf_scores or {})
    if semantic_score > 0:
        score += min(4.0, semantic_score * 5.0)
        reasons.append("tfidf_semantic_similarity")
    shared_terms = _content_terms(str(left.get("claim", ""))) & _content_terms(str(right.get("claim", "")))
    if shared_terms:
        score += min(3, len(shared_terms))
        reasons.append("shared_terms")
    return score, "+".join(reasons) or "low_signal"

def _semantic_pair_score(
    left: dict[str, Any],
    right: dict[str, Any],
    tfidf_scores: dict[tuple[str, str], float],
) -> float:
    left_id, right_id = sorted((str(left.get("claim_id", "")), str(right.get("claim_id", ""))))
    return float(tfidf_scores.get((left_id, right_id), 0.0))

def _role_pair_priority(left_role: str, right_role: str) -> tuple[str, int]:
    roles = {left_role, right_role}
    if "scope_limit" in roles and roles & {"conclusion_support", "crux"}:
        return "scope_limit_bounds_decision_claim", 8
    if "implementation_constraint" in roles and roles & {"conclusion_support", "crux"}:
        return "implementation_constraint_conditions_decision_claim", 8
    if "measurement_validity" in roles and roles & {"conclusion_support", "crux"}:
        return "measurement_limit_bears_on_decision_claim", 7
    if "external_validity" in roles and roles & {"conclusion_support", "crux"}:
        return "external_validity_bounds_decision_claim", 7
    if "crux" in roles and roles - {"background", "other"}:
        return "crux_connected_to_substantive_claim", 7
    return "", 0

def _relation_contract(proposal: dict[str, Any], packet: dict[str, Any], rationale: str) -> dict[str, str]:
    left = packet["left"]
    right = packet["right"]
    return {
        "edge_basis": _contract_text(proposal.get("edge_basis"), default="source_inferred"),
        "source_anchor_a": _contract_text(proposal.get("source_anchor_a"), default=_short_anchor(left)),
        "source_anchor_b": _contract_text(proposal.get("source_anchor_b"), default=_short_anchor(right)),
        "why_decision_relevant": _contract_text(proposal.get("why_decision_relevant"), default=rationale),
        "failure_condition": _contract_text(
            proposal.get("failure_condition"),
            default="The edge weakens if the two claims address different decisions, populations, mechanisms, or evidence standards.",
        ),
    }

def _fallback_relation_contract(left: dict[str, Any], right: dict[str, Any]) -> dict[str, str]:
    return {
        "edge_basis": "role_template",
        "source_anchor_a": _short_anchor(left),
        "source_anchor_b": _short_anchor(right),
        "why_decision_relevant": "The paired claim roles indicate a possible decision-relevant dependency that needs review.",
        "failure_condition": "A reviewer should reject the edge if the excerpts do not bear on the same decision-relevant proposition.",
    }

def _relation_confidence(proposal: dict[str, Any], contract: dict[str, str]) -> str:
    value = str(proposal.get("relation_confidence", "")).strip().lower()
    if value in {"low", "medium", "high"}:
        return value
    if contract["edge_basis"] == "source_explicit":
        return "high"
    if contract["source_anchor_a"] and contract["source_anchor_b"]:
        return "medium"
    return "low"

def _candidate_pair_metadata(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "pair_id": str(packet.get("pair_id", "")),
        "score": packet.get("candidate_score"),
        "reason": str(packet.get("candidate_reason", "")),
    }

def _short_anchor(claim: dict[str, Any]) -> str:
    text = str(claim.get("excerpt") or claim.get("claim") or "").strip()
    return re.sub(r"\s+", " ", text)[:220]

def _contract_text(value: Any, *, default: str) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", " ", text) if text else default

def _has_support_signal(text: str) -> bool:
    return any(marker in text for marker in ("support", "benefit", "improve", "reduce", "favor", "works", "effective", "associated with"))

def _has_limit_or_challenge_signal(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "limit",
            "uncertain",
            "not",
            "cannot",
            "does not",
            "failed",
            "risk",
            "challenge",
            "weaken",
            "scope",
            "only when",
            "depends",
        )
    )

def _content_terms(text: str) -> set[str]:
    stopwords = {
        "about",
        "after",
        "also",
        "and",
        "are",
        "but",
        "for",
        "from",
        "has",
        "have",
        "into",
        "not",
        "that",
        "the",
        "their",
        "this",
        "with",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]{4,}", text.lower())
        if token not in stopwords
    }

def _source_chunks(
    repo_root: Path,
    case_manifest: CaseManifest,
    region: WorkedRegion,
    chunk_lines: int,
    chunk_overlap_lines: int,
) -> list[SourceChunk]:
    chunks: list[SourceChunk] = []
    ordinal = 0
    step = max(1, chunk_lines - chunk_overlap_lines)
    for source in _required_sources(case_manifest, region):
        lines = _source_text(repo_root, source).splitlines()
        if not lines:
            continue
        for start in range(0, len(lines), step):
            selected = lines[start : start + chunk_lines]
            if not selected:
                continue
            start_line = start + 1
            end_line = start + len(selected)
            chunk_id = f"{source.source_id}_lines_{start_line}_{end_line}"
            numbered = "\n".join(f"{line_no}: {line}" for line_no, line in enumerate(selected, start=start_line))
            spans = tuple(
                SourceSpan(
                    span_id=f"{_safe_filename(source.source_id)}_s{line_no:04d}",
                    source_id=source.source_id,
                    source_span=f"lines {line_no}-{line_no}",
                    text=line.strip(),
                )
                for line_no, line in enumerate(selected, start=start_line)
                if line.strip()
            )
            ordinal += 1
            chunks.append(
                SourceChunk(
                    chunk_id=_safe_filename(chunk_id),
                    source_id=source.source_id,
                    title=source.title,
                    start_line=start_line,
                    end_line=end_line,
                    ordinal=ordinal,
                    numbered_text=numbered,
                    plain_text="\n".join(selected),
                    spans=spans,
                )
            )
    return chunks

def _chunk_summary(chunk: SourceChunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "source_id": chunk.source_id,
        "title": chunk.title,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "ordinal": chunk.ordinal,
        "signal_score": _chunk_signal_score(chunk),
        "span_count": len(chunk.spans),
        "spans": [span.__dict__ for span in chunk.spans],
    }

def _budget_chunks(
    chunks: list[SourceChunk],
    max_chunks_per_source: int | None,
    max_total_chunks: int | None,
) -> tuple[list[SourceChunk], list[dict[str, Any]]]:
    selected = list(chunks)
    skipped: list[dict[str, Any]] = []
    if max_chunks_per_source is not None:
        selected_ids: set[str] = set()
        by_source: dict[str, list[SourceChunk]] = {}
        for chunk in selected:
            by_source.setdefault(chunk.source_id, []).append(chunk)
        for source_chunks in by_source.values():
            ranked = sorted(source_chunks, key=_chunk_priority)
            kept = set(ranked[:max_chunks_per_source])
            selected_ids.update(chunk.chunk_id for chunk in kept)
            for chunk in source_chunks:
                if chunk not in kept:
                    skipped.append(_skipped_chunk_summary(chunk, "max_chunks_per_source"))
        selected = [chunk for chunk in selected if chunk.chunk_id in selected_ids]
    if max_total_chunks is not None and len(selected) > max_total_chunks:
        selected_set = _select_total_budget(selected, max_total_chunks)
        for chunk in selected:
            if chunk.chunk_id not in selected_set:
                skipped.append(_skipped_chunk_summary(chunk, "max_total_chunks"))
        selected = [chunk for chunk in selected if chunk.chunk_id in selected_set]
    selected.sort(key=lambda chunk: chunk.ordinal)
    skipped.sort(key=lambda item: int(item["ordinal"]))
    return selected, skipped

def _select_total_budget(chunks: list[SourceChunk], max_total_chunks: int) -> set[str]:
    by_source: dict[str, list[SourceChunk]] = {}
    for chunk in chunks:
        by_source.setdefault(chunk.source_id, []).append(chunk)
    if max_total_chunks < len(by_source):
        return {chunk.chunk_id for chunk in sorted(chunks, key=_chunk_priority)[:max_total_chunks]}
    selected_order: list[str] = []
    selected: set[str] = set()
    for source_chunks in sorted(by_source.values(), key=lambda items: min(chunk.ordinal for chunk in items)):
        if len(selected) >= max_total_chunks:
            break
        chunk_id = min(source_chunks, key=_chunk_priority).chunk_id
        selected.add(chunk_id)
        selected_order.append(chunk_id)
    if len(selected) >= max_total_chunks:
        return set(selected_order[:max_total_chunks])
    for chunk in sorted(chunks, key=_chunk_priority):
        if len(selected) >= max_total_chunks:
            break
        if chunk.chunk_id not in selected:
            selected.add(chunk.chunk_id)
            selected_order.append(chunk.chunk_id)
    return selected

def _skipped_chunk_summary(chunk: SourceChunk, reason: str) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "source_id": chunk.source_id,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "ordinal": chunk.ordinal,
        "signal_score": _chunk_signal_score(chunk),
        "span_count": len(chunk.spans),
        "reason": reason,
    }

def _chunk_priority(chunk: SourceChunk) -> tuple[int, int, int]:
    return (-_chunk_signal_score(chunk), -len(chunk.spans), chunk.ordinal)

def _chunk_signal_score(chunk: SourceChunk) -> int:
    return sum(_span_signal_score(span.text) for span in chunk.spans)

def _parse_model_json(text: str) -> dict[str, Any] | list[Any] | None:
    canonical = canonical_json_output(text)
    try:
        return json.loads(canonical)
    except json.JSONDecodeError:
        return None

def _parse_relation_model_json(text: str) -> dict[str, Any] | None:
    parsed = _parse_model_json(text)
    salvaged = _salvage_relation_array_objects(text)
    if salvaged and (not isinstance(parsed, dict) or "relations" not in parsed):
        return {"relations": salvaged, "parse_recovery": "truncated_relations_array"}
    return parsed if isinstance(parsed, dict) else None

def _salvage_relation_array_objects(text: str) -> list[dict[str, Any]]:
    match = re.search(r'"relations"\s*:\s*\[', text)
    if not match:
        return []
    decoder = json.JSONDecoder()
    objects: list[dict[str, Any]] = []
    index = match.end()
    while index < len(text):
        next_object = text.find("{", index)
        next_array_end = text.find("]", index)
        if next_object < 0 or (0 <= next_array_end < next_object):
            break
        try:
            value, end = decoder.raw_decode(text[next_object:])
        except json.JSONDecodeError:
            break
        if isinstance(value, dict):
            objects.append(value)
        index = next_object + end
    return objects

def _relation_proposals(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if "pair_id" in payload:
        return [payload]
    proposals = payload.get("relations", [])
    if isinstance(proposals, list):
        return [proposal for proposal in proposals if isinstance(proposal, dict)]
    return []

def _batches(items: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    safe_batch_size = min(batch_size, 4)
    return [items[index : index + safe_batch_size] for index in range(0, len(items), safe_batch_size)]

def _relation_batch_count(max_relation_pairs: int, relation_batch_size: int, claims: list[dict[str, Any]]) -> int:
    if len(claims) < 2:
        return 0
    pair_count = len(_candidate_relation_pairs(claims, max_relation_pairs))
    if pair_count == 0:
        return 0
    safe_batch_size = min(relation_batch_size, 4)
    return (pair_count + safe_batch_size - 1) // safe_batch_size

def _line_span_for_excerpt(chunk: SourceChunk, excerpt: str) -> str:
    chunk_lines = chunk.plain_text.splitlines()
    for offset, line in enumerate(chunk_lines):
        if excerpt in line:
            line_no = chunk.start_line + offset
            return f"lines {line_no}-{line_no}"
    return f"lines {chunk.start_line}-{chunk.end_line}"

def _excerpt_from_source_span(chunk: SourceChunk, source_span: str) -> str | None:
    match = re.search(r"lines?\s+(\d+)(?:\s*-\s*(\d+))?", source_span)
    if not match:
        return None
    start_line = int(match.group(1))
    end_line = int(match.group(2) or match.group(1))
    if start_line < chunk.start_line or end_line > chunk.end_line or end_line < start_line:
        return None
    lines = chunk.plain_text.splitlines()
    start_index = start_line - chunk.start_line
    end_index = end_line - chunk.start_line + 1
    excerpt = "\n".join(lines[start_index:end_index]).strip()
    return excerpt or None

def _load_context(repo_root: Path, manifest_path: str, region_id: str) -> tuple[SubmissionManifest, WorkedRegion, CaseManifest]:
    manifest = load_submission_manifest(repo_root, manifest_path)
    region = manifest.region_for_id(region_id)
    case = manifest.case_for_key(region.case_key)
    case_manifest = CaseManifest.model_validate(read_yaml(repo_root / case.case_path))
    return manifest, region, case_manifest

def _required_sources(case_manifest: CaseManifest, region: WorkedRegion) -> list[Source]:
    if not region.required_sources:
        return case_manifest.sources
    lookup = {source.source_id: source for source in case_manifest.sources}
    return [lookup[source_id] for source_id in region.required_sources if source_id in lookup]

def _source_text(repo_root: Path, source: Source) -> str:
    if source.text:
        return source.text
    if source.path:
        path = repo_root / source.path
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return source.excerpt or source.notes or ""

def _artifact_dir(repo_root: Path, region_id: str, artifact_dir: str | Path | None) -> Path:
    path = Path(artifact_dir or f"artifacts/semantic/{region_id}/staged")
    if not path.is_absolute():
        path = repo_root / path
    return path

def _relative(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()

def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")

def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()



# Explicit cross-module dependencies for compatibility facade removal.
from epistemic_case_mapper.staged_semantic_pipeline_runner import (
    RELATION_BATCH_PROMPT_VERSION,
    RELATION_PROMPT_VERSION,
    SourceChunk,
    SourceSpan,
    VALID_CLAIM_ROLES,
)
from epistemic_case_mapper.staged_semantic_quality import _map_quality_scaffold, _profile_relation_rule_text
