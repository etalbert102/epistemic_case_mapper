from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epistemic_case_mapper.config_profiles import (
    EpistemicConfigProfile,
    config_profile_from_manifest_payload,
    profile_vocabulary,
)
from epistemic_case_mapper.io import read_yaml, write_json, write_markdown
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.prompt_templates import examples_block, json_schema_block, render_prompt
from epistemic_case_mapper.schema import CaseManifest, Source
from epistemic_case_mapper.semantic_pipeline import MAP_PROMPT_VERSION, VALID_ENTAILMENT, validate_map_candidate
from epistemic_case_mapper.staged_semantic_claim_importance import normalized_decision_importance, question_fit_from_relevance
from epistemic_case_mapper.staged_semantic_decision_questions import region_decision_question
from epistemic_case_mapper.staged_semantic_quote_alignment import align_source_quote_to_span, quote_alignment_metadata
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
    decision_question: str | None = None,
) -> str:
    left = packet["left"]
    right = packet["right"]
    relation_types = ", ".join(sorted(manifest.relation_ontology.permitted_types()))
    profile_rules = _profile_relation_rule_text(case_manifest)
    question = region_decision_question(region, case_manifest, decision_question)
    return render_prompt(
        ("Task", "You are classifying one possible relation between two already-validated claim cards."),
        ("Metadata", f"Prompt version: {RELATION_PROMPT_VERSION}\nRegion ID: {region.region_id}\nPair ID: {packet['pair_id']}\nDecision question: {question}\nCase question: {case_manifest.question}\nAllowed relation types:\n{relation_types}"),
        ("Rules", _relation_rules(profile_rules)),
        ("Output Schema", json_schema_block(relation_prompt_schema(packet["pair_id"], relation_types))),
        ("Examples", examples_block(relation_examples())),
        (
            "Context",
            "\n\n".join(
                (
                    f"Claim A:\n{_relation_claim_card(left, 'A')}",
                    f"Claim B:\n{_relation_claim_card(right, 'B')}",
                    _relation_pair_contract(packet),
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
    decision_question: str | None = None,
) -> str:
    relation_types = ", ".join(sorted(manifest.relation_ontology.permitted_types()))
    pair_blocks = "\n\n".join(_relation_pair_block(packet) for packet in packets)
    pair_ids = ", ".join(packet["pair_id"] for packet in packets)
    profile_rules = _profile_relation_rule_text(case_manifest)
    question = region_decision_question(region, case_manifest, decision_question)
    return render_prompt(
        ("Task", "You are classifying possible relations between already-validated claim cards."),
        ("Metadata", f"Prompt version: {RELATION_BATCH_PROMPT_VERSION}\nRegion ID: {region.region_id}\nBatch ID: {batch_id}\nDecision question: {question}\nCase question: {case_manifest.question}\nAllowed relation types:\n{relation_types}"),
        ("Rules", ["- Return exactly one object for each pair ID in this batch.", *_relation_rules(profile_rules)]),
        ("Output Schema", json_schema_block(relation_batch_prompt_schema(pair_ids, relation_types))),
        ("Examples", examples_block(relation_examples())),
        (
            "Context",
            f"Pairs to classify:\n{pair_blocks}",
        ),
    )

def _relation_rules(profile_rules: str) -> list[str]:
    rules = [
        "- Do not include relation_id. Deterministic code assigns IDs later.",
        "- Use only the claim IDs shown in the pair.",
        '- Use only allowed relation types, or use relation_type "none".',
        "- Treat each pair's relation_intent and suggested_relation_types as routing guidance, not a hard limit.",
        "- You may use any allowed relation type when the exact evidence quotes support it; explain the override in the rationale.",
        "- Prefer no relation over a plausible but weak topical association.",
        "- Use only the two claim cards, exact evidence quotes, relation intent, and pair contract shown for each pair.",
        "- Prefer decision-relevant relations over generic links.",
        "- Use crux_for only when the rationale says what answer would change if one claim were false.",
        "- Use depends_on only when the rationale names a condition that must hold.",
        "- Use in_tension_with only when the rationale names what cannot comfortably both be true.",
        "- Use challenges only when the rationale names what proposition is weakened or contradicted.",
        "- Use refines only when the rationale names the exact boundary, population, endpoint, mechanism, or condition being narrowed.",
        "- Use supports only when the rationale names same-proposition support, a mechanism that explains the target claim, or quantitative/statistical evidence that strengthens the target claim.",
        "- Do not use supports merely because both claims lean harmful, neutral, or beneficial.",
        "- Do not use a study-specific population/scope claim to refine findings from a different source.",
        "- Fill the relation evidence contract for every non-none relation.",
        "- Ground anchors in visible evidence-quote phrases rather than introducing new facts.",
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
Candidate-pair score: {packet.get('candidate_score', 'not recorded')}
{_relation_pair_contract(packet)}"""

def _relation_claim_card(claim: dict[str, Any], label: str) -> str:
    return "\n".join(
        [
            f"- claim_id: {claim.get('claim_id')}",
            f"- claim: {_compact_relation_text(str(claim.get('claim', '')), max_chars=300)}",
            f"- source_id: {claim.get('source_id')}",
            f"- role: {claim.get('role')}",
            f"- source_span: {claim.get('source_span', '')}",
            f"- exact_evidence_quote_{label}: {_compact_relation_text(_relation_evidence_quote(claim), max_chars=520)}",
        ]
    )

def _relation_pair_contract(packet: dict[str, Any]) -> str:
    intent = packet.get("pair_intent") if isinstance(packet.get("pair_intent"), dict) else {}
    intent_name = str(intent.get("intent", "generic_decision_relation"))
    suggested = [str(item) for item in intent.get("allowed_relation_types", ["none"])]
    left_id = str(packet.get("left", {}).get("claim_id", "")) if isinstance(packet.get("left"), dict) else ""
    right_id = str(packet.get("right", {}).get("claim_id", "")) if isinstance(packet.get("right"), dict) else ""
    return "\n".join(
        [
            "Pair contract:",
            f"- allowed_claim_ids_for_non_none_relation: {left_id}, {right_id}",
            f"- endpoint_rule: source_claim and target_claim must be these exact claim IDs for a non-none relation; use null/null for relation_type \"none\".",
            f"- relation_intent: {intent_name}",
            f"- suggested_relation_types: {', '.join(suggested)}",
            f"- routing_metadata_only: candidate reason and score explain why this pair was shown; they are not evidence for an edge.",
            f"- decision_rule: {_relation_intent_decision_rule(intent_name)}",
            f"- override_rule: If the exact evidence quotes clearly support a non-suggested allowed relation type, use it and explain why.",
            f"- no_edge_rule: Use relation_type \"none\" unless the exact evidence quotes support a clear relation.",
        ]
    )

def _relation_intent_decision_rule(intent_name: str) -> str:
    rules = {
        "cross_source_study_scope_to_finding": "Do not transfer a study-specific population or design boundary onto another source's finding.",
        "cross_source_mechanism_scope_to_finding": "A mechanistic caveat from one source can support, challenge, or create tension with another finding only when the mechanism changes how that finding should be interpreted; do not call this refines.",
        "cross_source_general_scope_to_finding": "Use refines only when the scope boundary is portable to the other source's finding and names a specific population, endpoint, condition, or generalizability boundary.",
        "same_source_scope_to_finding": "Use refines when the scope card states the population, endpoint, intervention, or design boundary for the same source's finding.",
        "crux_to_decision_claim": "Use crux_for only when one claim would change the answer to the decision question or the interpretation of the other claim.",
        "implementation_to_guidance": "Use depends_on when practical implementation is a condition for using the evidence or recommendation.",
        "cross_source_agreement": "Use supports or similar_to for convergent evidence. If the exact quotes conflict on the same proposition, override to in_tension_with or challenges rather than none.",
        "same_source_agreement": "Use similar_to for redundant claims from the same source. If same-source claims conflict, override to in_tension_with rather than none.",
        "cross_source_disagreement": "Use in_tension_with or challenges only when the exact quotes point in conflicting directions on the same decision-relevant proposition.",
        "same_source_disagreement": "Use in_tension_with only when the source itself contains a real internal tension.",
        "mechanism_to_outcome": "Use supports, depends_on, or in_tension_with only when the mechanism changes the interpretation of the outcome claim.",
    }
    return rules.get(intent_name, "Use a relation only when the exact evidence quotes establish a clear decision-relevant edge.")

def _relation_evidence_quote(claim: dict[str, Any]) -> str:
    alignment = claim.get("source_alignment") if isinstance(claim.get("source_alignment"), dict) else {}
    for key in ("source_quote", "matched_text"):
        value = str(alignment.get(key, "")).strip()
        if value:
            return value
    for key in ("source_quote", "excerpt"):
        value = str(claim.get(key, "")).strip()
        if value:
            return value
    return ""

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
    source_quote = _proposal_source_quote(proposal)
    alignment = align_source_quote_to_span(source_quote=source_quote, proposed_span_id=span_id, span_lookup=span_lookup)
    if alignment is None:
        return None, "source_quote_unaligned" if source_quote else "unknown_span_id"
    span = span_lookup[alignment.span_id]
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
    question_relevance = _normalized_question_relevance(proposal.get("question_relevance"))
    if question_relevance == "irrelevant":
        return None, "question_irrelevant"
    scope_flags = _normalized_scope_flags(proposal.get("scope_flags"))
    importance = normalized_decision_importance(
        proposal,
        claim_text=claim_text,
        excerpt=span.text,
        role=role,
        question_relevance=question_relevance,
        scope_flags=scope_flags,
    )
    return (
        {
            "claim_id": "",
            "claim": claim_text,
            "source_id": span.source_id,
            "source_span": span.source_span,
            "excerpt": span.text,
            "source_quote": alignment.quote or _compact_metadata_text(proposal.get("source_quote")),
            "source_alignment": quote_alignment_metadata(alignment),
            "entailed_by_excerpt": entailed,
            "role": role,
            "question_relevance": question_relevance,
            "question_fit": question_fit_from_relevance(question_relevance, scope_flags),
            "relevance_rationale": _compact_metadata_text(proposal.get("relevance_rationale")),
            "scope_flags": scope_flags,
            "decision_importance": importance,
            "decision_importance_level": importance["calibrated_level"],
            "decision_function": importance["decision_function"],
            "default_use": importance["default_use"],
            "importance_rationale": importance["rationale"],
            "source_acronym_expansions": _metadata_dict(proposal.get("source_acronym_expansions")),
            "whole_doc_source_card": _metadata_dict(proposal.get("whole_doc_source_card")),
        },
        "",
    )


def _metadata_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}

def _proposal_source_quote(proposal: dict[str, Any]) -> str:
    direct = str(proposal.get("source_quote", proposal.get("sourceQuote", "")) or "").strip()
    if direct:
        return direct
    langextract = proposal.get("langextract")
    if isinstance(langextract, dict):
        return str(langextract.get("extraction_text", "") or "").strip()
    return str(proposal.get("extraction_text", "") or "").strip()

def _normalized_question_relevance(value: Any) -> str:
    relevance = str(value or "").strip().lower()
    if relevance in {"direct", "indirect", "scope_limit", "background", "irrelevant"}:
        return relevance
    return "unspecified"

def _normalized_scope_flags(value: Any) -> list[str]:
    if isinstance(value, list):
        flags = [str(item).strip().lower() for item in value if str(item).strip()]
    else:
        flags = [part.strip().lower() for part in re.split(r"[,;|]", str(value or "")) if part.strip()]
    allowed = {
        "target_population_mismatch",
        "outcome_mismatch",
        "intervention_or_exposure_mismatch",
        "mechanism_only",
        "administrative_context",
        "none",
    }
    normalized = [flag for flag in flags if flag in allowed]
    return normalized or ["none"]

def _compact_metadata_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:240]

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
        "source_quote": span.text,
        "entailed_by_excerpt": "yes",
        "role": _fallback_role(span.text),
        "span_id": span.span_id,
        "source_alignment": {
            "status": "deterministic_fallback_span",
            "method": "deterministic_fallback_span",
            "source_quote": span.text,
            "matched_text": span.text,
            "proposed_span_id": span.span_id,
            "resolved_span_id": span.span_id,
            "coverage": 1.0,
            "density": 1.0,
        },
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
    non_evidence_reason = _non_evidence_text_reason(stripped)
    if non_evidence_reason and not _allow_low_signal_coverage_fallback(stripped, non_evidence_reason):
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

def _looks_like_relation_reference_or_boilerplate(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"\bdoi\b|\bpmid\b|\bgoogle scholar\b|\bcrossref\b", lowered):
        return True
    if lowered.count("received ") >= 2 and len(lowered) > 400:
        return True
    return False

def _non_evidence_text_reason(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip(" -•*\t\r\n")
    lowered = compact.lower()
    if not compact:
        return "blank"
    if re.search(r"\b(?:doi|pmid|pmcid|issn|isbn|pubmed|crossref|google scholar|linkout|substances)\b", lowered):
        return "reference_or_metadata"
    if re.search(r"\b(?:privacy|cookie|copyright|terms of use|linking|whistleblower|conflict of interest|editorial guidelines|accessibility)\s+policy\b", lowered):
        return "navigation_or_policy_boilerplate"
    if re.search(r"\b(?:official website|https:// ensures|advanced search|email alerts|save citation|share this article)\b", lowered):
        return "site_navigation_or_security_boilerplate"
    if re.fullmatch(r"(?:[a-z][a-z\s/-]{2,40}\*?\s*){1,4}", lowered) and not _has_evidence_predicate(lowered):
        return "list_heading_or_index_term"
    if len(compact) < 18 and not re.search(r"\d|%|\b(risk|effect|recommend|should|found|showed)\b", lowered):
        return "too_short_without_evidence_signal"
    if lowered.count(";") + lowered.count(",") >= 7 and not _has_evidence_predicate(lowered):
        return "list_without_predicate"
    if re.fullmatch(r"[\w\s,./()%+\-*]+", compact) and len(_content_terms(compact)) <= 3 and not _has_evidence_predicate(lowered):
        return "low_content_fragment"
    return ""

def _has_evidence_predicate(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:is|are|was|were|found|showed|reported|associated|increased|decreased|reduced|lower|higher|recommend|recommended|should|must|may|can|depends|compared)\b",
            text,
        )
    )

def _allow_low_signal_coverage_fallback(text: str, reason: str) -> bool:
    if reason not in {"too_short_without_evidence_signal", "list_heading_or_index_term", "low_content_fragment"}:
        return False
    lowered = text.lower()
    if "policy" in lowered or "linkout" in lowered or "substances" in lowered:
        return False
    return True

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
from epistemic_case_mapper.staged_semantic_quality import _profile_relation_rule_text
