from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Callable

from epistemic_case_mapper.classical_ml import diverse_ranked_edges, tfidf_pair_similarities
from epistemic_case_mapper.model_backends import ModelBackendResult, run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output


ROLE_OUTCOME = "outcome_finding"
ROLE_MECHANISM = "mechanism_or_biomarker"
ROLE_SCOPE = "scope_or_subgroup_boundary"
ROLE_METHOD = "method_or_validity_limit"
ROLE_GUIDANCE = "guidance_or_recommendation"
ROLE_COMPARATOR = "comparator_or_substitution"
ROLE_BACKGROUND = "background_or_context"

DECISION_EDGE_ROLES = {
    ROLE_OUTCOME,
    ROLE_MECHANISM,
    ROLE_SCOPE,
    ROLE_METHOD,
    ROLE_GUIDANCE,
    ROLE_COMPARATOR,
    ROLE_BACKGROUND,
}

VALUABLE_CONTRACTS = {
    "outcome_disagreement",
    "mechanism_to_outcome",
    "scope_bounds_outcome",
    "method_limits_headline",
    "comparator_contextualizes_outcome",
    "guidance_supported_or_bounded_by_evidence",
    "scope_bounds_guidance",
    "method_limits_guidance",
}

DEFAULT_DECISION_EDGE_BUDGET = 18
ROLE_PREP_PROMPT_VERSION = "decision_edge_role_prep_v1"


def build_decision_edge_relation_inputs(
    claims: list[dict[str, Any]],
    *,
    requested_max_pairs: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Prepare high-precision relation inputs before model adjudication.

    The model should adjudicate a small set of decision-relevant edge
    candidates. This function keeps semantic discovery in deterministic,
    inspectable reports and leaves final relation meaning to the relation model.
    """

    role_report = claim_relation_role_report(claims)
    pair_budget = decision_edge_pair_budget(requested_max_pairs)
    candidates, candidate_report = propose_decision_edge_candidates(claims, max_pairs=pair_budget)
    candidate_report["requested_max_pairs"] = requested_max_pairs
    candidate_report["effective_max_pairs"] = pair_budget
    return candidates, role_report, candidate_report


def prepare_claim_decision_edge_roles(
    claims: list[dict[str, Any]],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    decision_question: str | None = None,
    run_backend: Callable[..., ModelBackendResult] = run_model_backend,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Ask the model to prep relation-building roles before candidate scoring.

    Deterministic code validates shape and fills gaps, but it does not override
    a valid model role just because the local heuristic would choose differently.
    """

    deterministic = {str(claim.get("claim_id", "")): infer_decision_edge_role(claim) for claim in claims}
    prompt = decision_edge_role_prep_prompt(claims, decision_question=decision_question)
    report: dict[str, Any] = {
        "schema_id": "claim_relation_model_role_prep_report_v1",
        "prompt_version": ROLE_PREP_PROMPT_VERSION,
        "backend": backend,
        "claim_count": len(claims),
        "prompt": prompt,
        "status": "not_run",
        "raw": "",
        "accepted_model_role_count": 0,
        "fallback_claim_count": len(claims),
        "invalid_model_rows": [],
        "model_deterministic_disagreements": [],
    }
    accepted_rows: dict[str, dict[str, Any]] = {}
    if backend.strip() == "prompt":
        report["status"] = "skipped_prompt_backend"
    elif claims:
        try:
            result = run_backend(
                prompt,
                backend,
                timeout_seconds=backend_timeout,
                max_retries=backend_retries,
            )
            report["raw"] = canonical_json_output(result.text)
            if result.prompt_only:
                report["status"] = "skipped_prompt_backend"
            else:
                accepted_rows, invalid_rows = _parse_model_role_rows(report["raw"], {str(claim.get("claim_id", "")) for claim in claims})
                report["status"] = "completed"
                report["invalid_model_rows"] = invalid_rows
        except Exception as exc:  # pragma: no cover - exercised by backend integration tests.
            report["status"] = "backend_error_fell_back_to_deterministic"
            report["backend_error"] = str(exc)

    prepared: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    role_source_counts: Counter[str] = Counter()
    for claim in claims:
        claim_id = str(claim.get("claim_id", ""))
        deterministic_role, deterministic_confidence, deterministic_reasons = deterministic.get(
            claim_id,
            (ROLE_BACKGROUND, "low", ["missing_claim_id"]),
        )
        model_row = accepted_rows.get(claim_id)
        prepared_claim = dict(claim)
        prepared_claim["original_role"] = claim.get("role")
        prepared_claim["decision_edge_role_deterministic"] = deterministic_role
        prepared_claim["decision_edge_role_deterministic_confidence"] = deterministic_confidence
        prepared_claim["decision_edge_role_deterministic_reasons"] = deterministic_reasons
        if model_row:
            role = str(model_row["decision_edge_role"])
            confidence = str(model_row["role_confidence"])
            rationale = str(model_row.get("rationale", "")).strip()
            prepared_claim["role"] = role
            prepared_claim["decision_edge_role"] = role
            prepared_claim["decision_edge_role_confidence"] = confidence
            prepared_claim["decision_edge_role_reasons"] = [reason for reason in [rationale or "model_role_prep"] if reason]
            prepared_claim["decision_edge_role_source"] = "model"
            if role != deterministic_role:
                disagreements.append(
                    {
                        "claim_id": claim_id,
                        "model_role": role,
                        "deterministic_role": deterministic_role,
                        "model_confidence": confidence,
                        "deterministic_confidence": deterministic_confidence,
                        "rationale": rationale,
                    }
                )
            role_source_counts["model"] += 1
        else:
            prepared_claim["role"] = deterministic_role
            prepared_claim["decision_edge_role"] = deterministic_role
            prepared_claim["decision_edge_role_confidence"] = deterministic_confidence
            prepared_claim["decision_edge_role_reasons"] = deterministic_reasons
            prepared_claim["decision_edge_role_source"] = "deterministic_fallback"
            role_source_counts["deterministic_fallback"] += 1
        prepared.append(prepared_claim)

    role_counts = Counter(str(claim.get("decision_edge_role", "")) for claim in prepared)
    report["accepted_model_role_count"] = role_source_counts.get("model", 0)
    report["fallback_claim_count"] = role_source_counts.get("deterministic_fallback", 0)
    report["role_source_counts"] = dict(sorted(role_source_counts.items()))
    report["role_counts"] = dict(sorted(role_counts.items()))
    report["model_deterministic_disagreements"] = disagreements
    return prepared, report


def decision_edge_role_prep_prompt(claims: list[dict[str, Any]], *, decision_question: str | None = None) -> str:
    role_lines = "\n".join(f"- {role}: {_role_definition(role)}" for role in sorted(DECISION_EDGE_ROLES))
    cards = "\n".join(_role_prep_claim_card(index, claim) for index, claim in enumerate(claims, start=1))
    question = (decision_question or "").strip() or "Not specified."
    return f"""You are preparing claims for relation-building in an epistemic decision map.

Decision question:
{question}

Assign each claim the role it should play when deciding which claim pairs are worth relation adjudication.

Allowed decision_edge_role values:
{role_lines}

Return JSON only:
{{
  "roles": [
    {{
      "claim_id": "claim id from the input",
      "decision_edge_role": "one allowed value",
      "role_confidence": "low|medium|high",
      "rationale": "short reason based on the claim's decision function"
    }}
  ]
}}

Claims:
{cards}
"""


def _parse_model_role_rows(raw: str, known_claim_ids: set[str]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    try:
        payload = json.loads(canonical_json_output(raw))
    except json.JSONDecodeError as exc:
        return {}, [{"reason": "invalid_json", "message": str(exc), "raw": _short(raw, 500)}]
    rows = payload.get("roles") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return {}, [{"reason": "missing_roles_array", "payload_type": type(payload).__name__}]
    accepted: dict[str, dict[str, Any]] = {}
    invalid: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            invalid.append({"index": index, "reason": "row_not_object", "row": row})
            continue
        claim_id = str(row.get("claim_id", "")).strip()
        role = str(row.get("decision_edge_role") or row.get("role") or "").strip()
        confidence = str(row.get("role_confidence") or row.get("confidence") or "").strip().lower()
        if claim_id not in known_claim_ids:
            invalid.append({"index": index, "reason": "unknown_claim_id", "claim_id": claim_id})
            continue
        if role not in DECISION_EDGE_ROLES:
            invalid.append({"index": index, "reason": "invalid_role", "claim_id": claim_id, "role": role})
            continue
        if confidence not in {"medium", "high"}:
            invalid.append({"index": index, "reason": "low_or_missing_confidence", "claim_id": claim_id, "confidence": confidence})
            continue
        accepted[claim_id] = {
            "claim_id": claim_id,
            "decision_edge_role": role,
            "role_confidence": confidence,
            "rationale": _short(str(row.get("rationale", "")).strip(), 300),
        }
    return accepted, invalid


def _role_definition(role: str) -> str:
    return {
        ROLE_BACKGROUND: "context that should usually not anchor relation edges",
        ROLE_COMPARATOR: "replacement, substitution, alternative, or comparator information",
        ROLE_GUIDANCE: "practical advice, policy, guideline, or recommendation",
        ROLE_MECHANISM: "biomarker, mechanism, surrogate marker, or causal pathway",
        ROLE_METHOD: "study design, measurement, confounding, adjustment, bias, or validity limit",
        ROLE_OUTCOME: "direct finding about a decision-relevant outcome or effect",
        ROLE_SCOPE: "population, subgroup, setting, boundary condition, or applicability limit",
    }.get(role, "decision-relevant role")


def _role_prep_claim_card(index: int, claim: dict[str, Any]) -> str:
    fields = {
        "claim_id": claim.get("claim_id"),
        "source_id": claim.get("source_id"),
        "claim": _short(str(claim.get("claim", "")), 360),
        "excerpt": _short(str(claim.get("excerpt") or claim.get("source_quote") or ""), 280),
        "question_relevance": claim.get("question_relevance"),
        "decision_importance_level": claim.get("decision_importance_level"),
        "decision_function": claim.get("decision_function"),
        "default_use": claim.get("default_use"),
    }
    return f"{index}. {json.dumps(fields, ensure_ascii=False, sort_keys=True)}"


def decision_edge_pair_budget(requested_max_pairs: int) -> int:
    if requested_max_pairs <= 0:
        return 0
    if requested_max_pairs < 12:
        return requested_max_pairs
    return min(requested_max_pairs, DEFAULT_DECISION_EDGE_BUDGET)


def claim_relation_role_report(claims: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [_claim_role_row(claim) for claim in claims]
    role_counts = Counter(str(row.get("decision_edge_role", "")) for row in rows)
    confidence_counts = Counter(str(row.get("role_confidence", "")) for row in rows)
    return {
        "schema_id": "claim_relation_role_report_v1",
        "method": "deterministic_role_preparation_from_model_labels_and_claim_text",
        "claim_count": len(claims),
        "role_counts": dict(sorted(role_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "low_confidence_claim_count": sum(1 for row in rows if row.get("role_confidence") == "low"),
        "roles": rows,
    }


def propose_decision_edge_candidates(
    claims: list[dict[str, Any]],
    *,
    max_pairs: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if max_pairs <= 0:
        return [], _candidate_report(claims, [], [], max_pairs=max_pairs)
    enriched = [_enriched_claim(claim) for claim in claims if _usable_claim(claim)]
    if len(enriched) < 2:
        return [], _candidate_report(claims, enriched, [], max_pairs=max_pairs)

    tfidf_scores = _tfidf_scores(enriched)
    scored: list[tuple[str, str, float, str]] = []
    lookup = {str(claim.get("claim_id", "")): claim for claim in enriched if claim.get("claim_id")}
    all_pairs: list[dict[str, Any]] = []
    rejected_pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(enriched):
        for right in enriched[left_index + 1 :]:
            row = _score_decision_edge_pair(left, right, tfidf_scores)
            if row["contract"] not in VALUABLE_CONTRACTS or row["score"] < 7:
                rejected_pairs.append(_pair_report_row(left, right, row, selected=False))
                continue
            all_pairs.append(_pair_report_row(left, right, row, selected=False))
            scored.append((left["claim_id"], right["claim_id"], float(row["score"]), str(row["reason"])))

    selected_edges = diverse_ranked_edges(
        [str(claim.get("claim_id", "")) for claim in enriched if claim.get("claim_id")],
        scored,
        limit=max_pairs,
    )
    selected_keys = {tuple(sorted((left_id, right_id))) for left_id, right_id, _score, _reason in selected_edges}
    pair_packets: list[dict[str, Any]] = []
    for index, (left_id, right_id, score, reason) in enumerate(
        sorted(selected_edges, key=lambda item: (-item[2], item[0], item[1])),
        start=1,
    ):
        left = lookup[left_id]
        right = lookup[right_id]
        scored_row = _score_decision_edge_pair(left, right, tfidf_scores)
        pair_packets.append(
            {
                "pair_id": f"pair_{index:03d}",
                "left": left,
                "right": right,
                "candidate_score": round(float(score), 4),
                "candidate_reason": reason,
                "decision_edge_contract": scored_row["contract"],
                "pair_intent": _pair_intent_for_contract(str(scored_row["contract"])),
            }
        )
    selected_report_rows = []
    for row in all_pairs:
        key = tuple(sorted((str(row["left_claim_id"]), str(row["right_claim_id"]))))
        if key in selected_keys:
            selected_report_rows.append({**row, "selected": True})
    report = _candidate_report(
        claims,
        enriched,
        selected_report_rows,
        max_pairs=max_pairs,
        considered_pair_count=len(all_pairs) + len(rejected_pairs),
        viable_pair_count=len(all_pairs),
        rejected_pair_examples=sorted(rejected_pairs, key=lambda item: (-float(item["score"]), item["left_claim_id"], item["right_claim_id"]))[:40],
    )
    return pair_packets, report


def decision_edge_quality_report(
    *,
    pair_packets: list[dict[str, Any]],
    accepted: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
) -> dict[str, Any]:
    accepted_pair_ids = {
        str(relation.get("candidate_pair", {}).get("pair_id", ""))
        for relation in accepted
        if isinstance(relation.get("candidate_pair"), dict)
    }
    packet_by_pair = {str(packet.get("pair_id", "")): packet for packet in pair_packets}
    accepted_rows = []
    for relation in accepted:
        pair_id = str(relation.get("candidate_pair", {}).get("pair_id", "")) if isinstance(relation.get("candidate_pair"), dict) else ""
        packet = packet_by_pair.get(pair_id, {})
        accepted_rows.append(
            {
                "relation_id": relation.get("relation_id"),
                "pair_id": pair_id,
                "relation_type": relation.get("relation_type"),
                "relation_confidence": relation.get("relation_confidence"),
                "decision_edge_contract": packet.get("decision_edge_contract"),
                "source_claim": relation.get("source_claim"),
                "target_claim": relation.get("target_claim"),
                "why_decision_relevant": _contract_field(relation, "why_decision_relevant"),
                "failure_condition": _contract_field(relation, "failure_condition"),
            }
        )
    return {
        "schema_id": "decision_edge_quality_report_v1",
        "method": "accepted_relation_edges_from_high_precision_candidate_graph",
        "candidate_pair_count": len(pair_packets),
        "accepted_relation_count": len(accepted),
        "rejected_relation_count": len(rejected),
        "accepted_pair_count": len(accepted_pair_ids),
        "unresolved_candidate_pair_count": max(0, len(pair_packets) - len(accepted_pair_ids)),
        "accepted_relation_type_counts": dict(Counter(str(row.get("relation_type", "")) for row in accepted_rows)),
        "accepted_confidence_counts": dict(Counter(str(row.get("relation_confidence", "")) for row in accepted_rows)),
        "accepted_edges": accepted_rows,
        "rejection_reason_counts": dict(Counter(str(row.get("reason", "")) for row in rejected if isinstance(row, dict))),
        "rejected_examples": [row for row in rejected[:40] if isinstance(row, dict)],
    }


def low_confidence_decision_edge_reason(relation: dict[str, Any], packet: dict[str, Any]) -> str:
    confidence = str(relation.get("relation_confidence", "")).strip().lower()
    if confidence == "low":
        return "low_confidence_decision_edge"
    contract = str(packet.get("decision_edge_contract", "")).strip()
    if contract in VALUABLE_CONTRACTS and not _contract_field(relation, "why_decision_relevant"):
        return "missing_decision_use"
    return ""


def _claim_role_row(claim: dict[str, Any]) -> dict[str, Any]:
    role, confidence, reasons = _prepared_or_inferred_role(claim)
    return {
        "claim_id": claim.get("claim_id"),
        "source_id": claim.get("source_id"),
        "decision_edge_role": role,
        "role_confidence": confidence,
        "role_source": claim.get("decision_edge_role_source") or "deterministic_inference",
        "reasons": reasons,
        "claim": _short(str(claim.get("claim", "")), 240),
    }


def infer_decision_edge_role(claim: dict[str, Any]) -> tuple[str, str, list[str]]:
    text = _claim_surface_text(claim)
    decision_function = str(claim.get("decision_function") or "").strip().lower()
    default_use = str(claim.get("default_use") or "").strip().lower()
    relevance = str(claim.get("question_relevance") or "").strip().lower()
    audit = claim.get("label_audit") if isinstance(claim.get("label_audit"), dict) else {}
    audit_role = str(audit.get("routing_role") or "").strip().lower()
    reasons: list[str] = []

    if default_use in {"appendix", "exclude_unless_gap"} or relevance in {"background", "low", "irrelevant", "not_relevant"}:
        if _text_matches(text, _SCOPE_PATTERNS | _METHOD_PATTERNS | _COMPARATOR_PATTERNS):
            reasons.append("appendix_but_structural_signal")
        else:
            return ROLE_BACKGROUND, "medium", ["appendix_or_low_relevance"]
    if decision_function in {"scope_boundary", "scope", "context", "constraint"} or audit_role in {"scope_limit", "external_validity"}:
        reasons.append("model_scope_label")
        return ROLE_SCOPE, "high", reasons
    if decision_function in {"confounder_or_bias", "source_quality_caveat", "method_limit"} or audit_role == "measurement_validity":
        reasons.append("model_method_label")
        return ROLE_METHOD, "high", reasons
    if decision_function in {"implementation_constraint", "practical_recommendation"}:
        reasons.append("model_guidance_or_constraint_label")
        return ROLE_GUIDANCE, "medium", reasons
    if decision_function in {"answer_bearing", "crux"}:
        reasons.append("model_answer_bearing_label")
        if _text_matches(text, _MECHANISM_PATTERNS):
            return ROLE_MECHANISM, "medium", [*reasons, "mechanism_text_signal"]
        if _looks_like_context_only_source_claim(text):
            return ROLE_BACKGROUND, "medium", [*reasons, "context_only_source_claim"]
        return ROLE_OUTCOME, "high", reasons

    if _looks_like_context_only_source_claim(text):
        return ROLE_BACKGROUND, "medium", ["context_only_source_claim"]

    text_roles = [
        (ROLE_COMPARATOR, _COMPARATOR_PATTERNS, "comparator_text_signal"),
        (ROLE_METHOD, _METHOD_PATTERNS, "method_text_signal"),
        (ROLE_SCOPE, _SCOPE_PATTERNS, "scope_text_signal"),
        (ROLE_GUIDANCE, _GUIDANCE_PATTERNS, "guidance_text_signal"),
        (ROLE_MECHANISM, _MECHANISM_PATTERNS, "mechanism_text_signal"),
        (ROLE_OUTCOME, _OUTCOME_PATTERNS, "outcome_text_signal"),
    ]
    for role, patterns, reason in text_roles:
        if _text_matches(text, patterns):
            return role, "medium", [reason]
    return ROLE_BACKGROUND, "low", ["no_decision_edge_role_signal"]


def _enriched_claim(claim: dict[str, Any]) -> dict[str, Any]:
    role, confidence, reasons = _prepared_or_inferred_role(claim)
    enriched = dict(claim)
    enriched["original_role"] = claim.get("role")
    enriched["role"] = role
    enriched["decision_edge_role"] = role
    enriched["decision_edge_role_confidence"] = confidence
    enriched["decision_edge_role_reasons"] = reasons
    return enriched


def _usable_claim(claim: dict[str, Any]) -> bool:
    claim_id = str(claim.get("claim_id", "")).strip()
    if not claim_id:
        return False
    if claim.get("appendix_only"):
        return False
    role, confidence, _reasons = _prepared_or_inferred_role(claim)
    if role == ROLE_BACKGROUND and confidence != "high":
        return False
    return True


def _prepared_or_inferred_role(claim: dict[str, Any]) -> tuple[str, str, list[str]]:
    role = str(claim.get("decision_edge_role") or "").strip()
    confidence = str(claim.get("decision_edge_role_confidence") or "").strip().lower()
    if role in DECISION_EDGE_ROLES and confidence in {"low", "medium", "high"}:
        reasons = claim.get("decision_edge_role_reasons")
        if not isinstance(reasons, list):
            reasons = [str(reasons).strip()] if reasons else []
        return role, confidence, [str(reason) for reason in reasons if str(reason).strip()]
    return infer_decision_edge_role(claim)


def _score_decision_edge_pair(
    left: dict[str, Any],
    right: dict[str, Any],
    tfidf_scores: dict[tuple[str, str], float],
) -> dict[str, Any]:
    left_role = str(left.get("decision_edge_role") or left.get("role") or ROLE_BACKGROUND)
    right_role = str(right.get("decision_edge_role") or right.get("role") or ROLE_BACKGROUND)
    contract = _contract_for_roles(left_role, right_role)
    score = 0.0
    reasons: list[str] = []
    if contract in VALUABLE_CONTRACTS:
        score += _contract_score(contract)
        reasons.append(contract)
    if left.get("source_id") != right.get("source_id"):
        score += 2.0
        reasons.append("cross_source")
    polarity = {_polarity(left), _polarity(right)}
    if contract == "outcome_disagreement" and polarity >= {"positive_or_null", "negative_or_concern"}:
        score += 5.0
        reasons.append("opposite_outcome_polarity")
    elif contract == "outcome_disagreement" and "mixed" in polarity:
        score += 1.5
        reasons.append("ambiguous_polarity")
    if _importance(left) in {"critical", "high"}:
        score += 1.5
        reasons.append("left_high_importance")
    if _importance(right) in {"critical", "high"}:
        score += 1.5
        reasons.append("right_high_importance")
    shared = _salient_shared_terms(left, right)
    if shared:
        score += min(3.0, len(shared))
        reasons.append("shared_decision_terms")
    semantic = _semantic_pair_score(left, right, tfidf_scores)
    if semantic >= 0.08:
        score += min(2.5, semantic * 5.0)
        reasons.append("tfidf_similarity")
    if _both_same_source_outcomes(left, right):
        score -= 5.0
        reasons.append("same_source_outcome_penalty")
    if _population_scope_mismatch(left, right):
        score -= 6.0
        reasons.append("scope_mismatch_penalty")
    if left_role == right_role == ROLE_BACKGROUND:
        score -= 20.0
        reasons.append("background_pair_penalty")
    return {
        "score": round(score, 4),
        "contract": contract,
        "reason": "+".join(reasons) or "low_signal",
    }


def _contract_for_roles(left_role: str, right_role: str) -> str:
    roles = {left_role, right_role}
    if roles == {ROLE_OUTCOME}:
        return "outcome_disagreement"
    if ROLE_MECHANISM in roles and ROLE_OUTCOME in roles:
        return "mechanism_to_outcome"
    if ROLE_SCOPE in roles and ROLE_OUTCOME in roles:
        return "scope_bounds_outcome"
    if ROLE_METHOD in roles and ROLE_OUTCOME in roles:
        return "method_limits_headline"
    if ROLE_COMPARATOR in roles and (ROLE_OUTCOME in roles or ROLE_GUIDANCE in roles):
        return "comparator_contextualizes_outcome"
    if ROLE_GUIDANCE in roles and ROLE_OUTCOME in roles:
        return "guidance_supported_or_bounded_by_evidence"
    if ROLE_SCOPE in roles and ROLE_GUIDANCE in roles:
        return "scope_bounds_guidance"
    if ROLE_METHOD in roles and ROLE_GUIDANCE in roles:
        return "method_limits_guidance"
    return "no_high_value_contract"


def _contract_score(contract: str) -> float:
    return {
        "outcome_disagreement": 8.0,
        "mechanism_to_outcome": 7.0,
        "scope_bounds_outcome": 8.0,
        "method_limits_headline": 8.0,
        "comparator_contextualizes_outcome": 8.0,
        "guidance_supported_or_bounded_by_evidence": 7.0,
        "scope_bounds_guidance": 7.0,
        "method_limits_guidance": 7.0,
    }.get(contract, 0.0)


def _pair_intent_for_contract(contract: str) -> dict[str, Any]:
    allowed = {
        "outcome_disagreement": ["in_tension_with", "challenges", "none"],
        "mechanism_to_outcome": ["supports", "depends_on", "in_tension_with", "challenges", "none"],
        "scope_bounds_outcome": ["refines", "depends_on", "in_tension_with", "none"],
        "method_limits_headline": ["challenges", "refines", "depends_on", "none"],
        "comparator_contextualizes_outcome": ["contextualizes", "refines", "supports", "in_tension_with", "none"],
        "guidance_supported_or_bounded_by_evidence": ["supports", "contextualizes", "refines", "depends_on", "none"],
        "scope_bounds_guidance": ["depends_on", "refines", "none"],
        "method_limits_guidance": ["challenges", "refines", "none"],
    }.get(contract, ["none"])
    return {"intent": contract, "allowed_relation_types": allowed}


def _candidate_report(
    claims: list[dict[str, Any]],
    enriched: list[dict[str, Any]],
    selected_rows: list[dict[str, Any]],
    *,
    max_pairs: int,
    considered_pair_count: int = 0,
    viable_pair_count: int = 0,
    rejected_pair_examples: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_id": "decision_edge_candidate_report_v1",
        "method": "role_contract_candidate_generation_before_model_adjudication",
        "input_claim_count": len(claims),
        "eligible_endpoint_count": len(enriched),
        "max_pairs": max_pairs,
        "considered_pair_count": considered_pair_count,
        "viable_pair_count": viable_pair_count,
        "selected_pair_count": len(selected_rows),
        "eligible_role_counts": dict(Counter(str(row.get("decision_edge_role", "")) for row in enriched)),
        "selected_contract_counts": dict(Counter(str(row.get("contract", "")) for row in selected_rows)),
        "selected_pairs": selected_rows,
        "rejected_pair_examples": rejected_pair_examples or [],
        "eligible_claims": [_claim_role_row(row) for row in enriched],
    }


def _pair_report_row(left: dict[str, Any], right: dict[str, Any], row: dict[str, Any], *, selected: bool) -> dict[str, Any]:
    return {
        "left_claim_id": left.get("claim_id"),
        "right_claim_id": right.get("claim_id"),
        "left_role": left.get("decision_edge_role"),
        "right_role": right.get("decision_edge_role"),
        "left_source_id": left.get("source_id"),
        "right_source_id": right.get("source_id"),
        "contract": row.get("contract"),
        "score": row.get("score"),
        "reason": row.get("reason"),
        "selected": selected,
        "left_claim": _short(str(left.get("claim", "")), 180),
        "right_claim": _short(str(right.get("claim", "")), 180),
    }


def _tfidf_scores(claims: list[dict[str, Any]]) -> dict[tuple[str, str], float]:
    ids = [str(claim.get("claim_id", "")) for claim in claims]
    texts = [_normalized_claim_text(claim) for claim in claims]
    return tfidf_pair_similarities(texts, ids)


def _semantic_pair_score(left: dict[str, Any], right: dict[str, Any], scores: dict[tuple[str, str], float]) -> float:
    left_id, right_id = sorted((str(left.get("claim_id", "")), str(right.get("claim_id", ""))))
    return float(scores.get((left_id, right_id), 0.0))


def _contract_field(relation: dict[str, Any], key: str) -> str:
    contract = relation.get("relation_contract") if isinstance(relation.get("relation_contract"), dict) else {}
    return str(contract.get(key) or relation.get(key) or "").strip()


def _importance(claim: dict[str, Any]) -> str:
    audit = claim.get("label_audit") if isinstance(claim.get("label_audit"), dict) else {}
    routed = str(audit.get("routing_importance_level", "")).lower()
    if routed:
        return routed
    importance = claim.get("decision_importance") if isinstance(claim.get("decision_importance"), dict) else {}
    return str(importance.get("calibrated_level") or claim.get("decision_importance_level") or claim.get("importance") or "").lower()


def _polarity(claim: dict[str, Any]) -> str:
    text = f" {_normalized_claim_text(claim)} "
    positive = any(marker in text for marker in (" lower risk ", " reduced risk ", " no association ", " not associated ", " neutral ", " beneficial ", " safely ", " appropriate "))
    negative = any(marker in text for marker in (" higher risk ", " increased risk ", " harmful ", " adverse ", " mortality ", " concern ", " restrict "))
    if positive and not negative:
        return "positive_or_null"
    if negative and not positive:
        return "negative_or_concern"
    return "mixed"


def _salient_shared_terms(left: dict[str, Any], right: dict[str, Any]) -> set[str]:
    generic = {
        "claim",
        "claims",
        "source",
        "study",
        "studies",
        "evidence",
        "finding",
        "findings",
        "associated",
        "association",
        "risk",
        "effect",
        "intake",
        "consumption",
        "people",
        "individuals",
    }
    return (_content_terms(str(left.get("claim", ""))) - generic) & (_content_terms(str(right.get("claim", ""))) - generic)


def _content_terms(text: str) -> set[str]:
    stop = {
        "about",
        "after",
        "also",
        "and",
        "are",
        "because",
        "been",
        "but",
        "can",
        "could",
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
        "without",
    }
    return {token for token in re.findall(r"[a-z][a-z0-9_-]{3,}", text.lower()) if token not in stop}


def _both_same_source_outcomes(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left.get("source_id") == right.get("source_id")
        and left.get("decision_edge_role") == right.get("decision_edge_role") == ROLE_OUTCOME
    )


def _population_scope_mismatch(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_scope = _population_terms(_normalized_claim_text(left))
    right_scope = _population_terms(_normalized_claim_text(right))
    if not left_scope or not right_scope:
        return False
    if "child" in left_scope ^ right_scope:
        return True
    return False


def _population_terms(text: str) -> set[str]:
    terms: set[str] = set()
    if re.search(r"\b(?:infant|toddler|child|children|adolescent|pediatric|paediatric)\b", text):
        terms.add("child")
    if re.search(r"\b(?:adult|adults|men|women|participant|participants|cohort)\b", text):
        terms.add("adult_or_general")
    if re.search(r"\b(?:subgroup|high risk|high-risk|baseline risk|condition|patients?)\b", text):
        terms.add("risk_subgroup")
    return terms


def _normalized_claim_text(claim: dict[str, Any]) -> str:
    return re.sub(
        r"\s+",
        " ",
        " ".join(str(claim.get(key, "")) for key in ("claim", "excerpt", "source_quote", "relevance_rationale", "importance_rationale")).lower(),
    ).strip()


def _claim_surface_text(claim: dict[str, Any]) -> str:
    return re.sub(
        r"\s+",
        " ",
        " ".join(str(claim.get(key, "")) for key in ("claim", "relevance_rationale", "importance_rationale")).lower(),
    ).strip()


def _looks_like_context_only_source_claim(text: str) -> bool:
    if not re.search(r"\b(?:source of|provides?|contains?|includes?|background|context)\b", text):
        return False
    return not _text_matches(text, _OUTCOME_PATTERNS | _MECHANISM_PATTERNS | _COMPARATOR_PATTERNS | _METHOD_PATTERNS)


def _text_matches(text: str, patterns: set[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _short(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max(0, max_chars - 1)].rstrip() + "..."


_OUTCOME_PATTERNS = {
    r"\b(?:risk|mortality|event|events|outcome|incidence|incident|associated|association|increased|decreased|reduced|lower|higher)\b",
}

_MECHANISM_PATTERNS = {
    r"\b(?:mechanism|biomarker|marker|surrogate|mediated|driven by|pathway|physiolog|concentration|ratio|level|levels)\b",
}

_SCOPE_PATTERNS = {
    r"\b(?:subgroup|population|applies|generaliz|only applies|only in|only for|healthy|high[- ]risk|patients?|participants?|adults?|children|men|women)\b",
}

_METHOD_PATTERNS = {
    r"\b(?:adjusted|adjustment|confound|bias|observational|randomized|trial|cohort|meta-analysis|heterogeneity|uncertain|limitation|measured|unmeasured)\b",
}

_GUIDANCE_PATTERNS = {
    r"\b(?:recommend|guidance|guideline|advice|should|prioritize|include|restrict|avoid|consume)\b",
}

_COMPARATOR_PATTERNS = {
    r"\b(?:replace|replacing|substitut|instead of|compared with|compared to|versus|relative to|alternative|comparator)\b",
}
