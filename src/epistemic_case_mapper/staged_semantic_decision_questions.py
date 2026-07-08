from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.schema import CaseManifest


def region_decision_question(region: Any, case_manifest: CaseManifest, override: str | None = None) -> str:
    if str(override or "").strip():
        return str(override).strip()
    blinded_baseline = getattr(region, "blinded_baseline", None)
    question = getattr(blinded_baseline, "question", "") if blinded_baseline is not None else ""
    if str(question).strip():
        return str(question).strip()
    return case_manifest.question


def claim_decision_relevance_rejection_reason(claim: dict[str, Any], decision_question: str) -> str:
    question = _normalize_text(decision_question)
    claim_text = _normalize_text(f"{claim.get('claim', '')} {claim.get('excerpt', '')}")
    flags = {str(flag).strip().lower() for flag in claim.get("scope_flags", []) if str(flag).strip()}
    if "administrative_context" in flags:
        return "question_administrative_context"
    if (
        "target_population_mismatch" in flags
        and not _question_allows_population_mismatch(question, claim_text)
        and not _claim_can_bound_population_mismatch(claim)
    ):
        return "question_population_mismatch"
    if "outcome_mismatch" in flags and not _claim_has_explicit_question_bridge(claim, question):
        return "question_outcome_mismatch"
    if _inferred_outcome_mismatch_without_bridge(claim, question, claim_text):
        return "question_outcome_mismatch"
    if _mentions_child_population(claim_text) and not _mentions_child_population(question):
        return "question_population_mismatch"
    return ""


def _question_allows_population_mismatch(question: str, claim_text: str) -> bool:
    return _mentions_child_population(question) or (
        ("population" in question or "subgroup" in question or "context" in question)
        and _mentions_child_population(claim_text)
    )


def _claim_can_bound_population_mismatch(claim: dict[str, Any]) -> bool:
    relevance = str(claim.get("question_relevance", "")).strip().lower()
    role = str(claim.get("role", "")).strip().lower()
    text = _normalize_text(f"{claim.get('claim', '')} {claim.get('excerpt', '')}")
    if _mentions_child_population(text):
        return False
    if relevance in {"direct", "indirect", "scope_limit"}:
        return True
    return role in {
        "scope_limit",
        "external_validity",
        "measurement_validity",
        "implementation_constraint",
        "crux",
    }


def _inferred_outcome_mismatch_without_bridge(claim: dict[str, Any], question: str, claim_text: str) -> bool:
    target_terms = _decision_target_terms(question)
    if not target_terms:
        return False
    claim_statement = _normalize_text(str(claim.get("claim", ""))) or claim_text
    claim_outcome_terms = _claim_outcome_terms(claim_statement)
    if not claim_outcome_terms:
        return False
    if target_terms & _target_content_terms(claim_statement):
        return False
    if target_terms & claim_outcome_terms:
        return False
    return not _claim_has_explicit_question_bridge(claim, question)


def _claim_has_explicit_question_bridge(claim: dict[str, Any], question: str) -> bool:
    target_terms = _decision_target_terms(question) or _target_content_terms(question)
    if not target_terms:
        return False
    bridge_text = _normalize_text(
        " ".join(
            [
                str(claim.get("claim", "")),
                str(claim.get("relevance_rationale", "")),
            ]
        )
    )
    return bool(target_terms & _target_content_terms(bridge_text))


def _decision_target_terms(question: str) -> set[str]:
    terms: set[str] = set()
    terms.update(_terms_near_outcome_anchors(question))
    terms.update(_terms_after_change_verbs(question))
    return terms


def _claim_outcome_terms(claim_text: str) -> set[str]:
    terms: set[str] = set()
    terms.update(_terms_near_outcome_anchors(claim_text))
    for match in re.finditer(r"\brisk\s+of\s+([a-z0-9][a-z0-9\-/ ]{2,80})", claim_text):
        terms.update(_target_content_terms(match.group(1)))
    for match in re.finditer(r"\b(?:associated\s+with|linked\s+to)\s+(?:higher|lower|increased|decreased)?\s*([a-z0-9][a-z0-9\-/ ]{2,80})", claim_text):
        terms.update(_target_content_terms(match.group(1)))
    for match in re.finditer(r"\bassociation\s+between\s+[a-z0-9][a-z0-9\-/ ]{2,80}?\s+and\s+([a-z0-9][a-z0-9\-/ ]{2,80})", claim_text):
        terms.update(_target_content_terms(match.group(1)))
    for match in re.finditer(r"\bassociation\s+with\s+([a-z0-9][a-z0-9\-/ ]{2,80})", claim_text):
        terms.update(_target_content_terms(match.group(1)))
    return terms


def _terms_near_outcome_anchors(text: str) -> set[str]:
    anchors = {
        "benefit",
        "benefits",
        "cost",
        "costs",
        "disease",
        "endpoint",
        "endpoints",
        "event",
        "events",
        "harm",
        "harms",
        "illness",
        "incidence",
        "injury",
        "mortality",
        "outcome",
        "outcomes",
        "rate",
        "rates",
        "reliability",
        "risk",
        "risks",
        "safety",
        "symptom",
        "symptoms",
    }
    tokens = re.findall(r"[a-z0-9][a-z0-9\-]*", text.lower())
    terms: set[str] = set()
    for index, token in enumerate(tokens):
        if token not in anchors:
            continue
        window = tokens[max(0, index - 3) : min(len(tokens), index + 5)]
        terms.update(_target_content_terms(" ".join(window)))
    return terms


def _terms_after_change_verbs(text: str) -> set[str]:
    verbs = r"affect|change|decrease|improve|increase|lower|mitigate|prevent|raise|reduce"
    terms: set[str] = set()
    for match in re.finditer(rf"\b(?:{verbs})\s+([a-z0-9][a-z0-9\-/ ]{{2,80}})", text.lower()):
        terms.update(_target_content_terms(match.group(1)))
    return terms


def _target_content_terms(text: str) -> set[str]:
    stopwords = {
        "about",
        "adopt",
        "adults",
        "after",
        "also",
        "answer",
        "associated",
        "beneficial",
        "because",
        "before",
        "change",
        "decision",
        "decrease",
        "does",
        "effect",
        "effects",
        "evidence",
        "from",
        "generally",
        "harmful",
        "higher",
        "increase",
        "intake",
        "lower",
        "neutral",
        "overall",
        "question",
        "reduce",
        "reduced",
        "risk",
        "risks",
        "should",
        "treated",
        "treat",
        "whether",
        "while",
        "with",
    }
    return {token for token in re.findall(r"[a-z0-9]{4,}", text.lower()) if token not in stopwords}


def _mentions_child_population(text: str) -> bool:
    return bool(re.search(r"\b(?:infant|infants|toddler|toddlers|child|children|adolescent|adolescents|pediatric|paediatric)\b", text))


def _content_terms(text: str) -> set[str]:
    stopwords = {"about", "after", "also", "and", "are", "but", "for", "from", "has", "have", "into", "not", "that", "the", "their", "this", "with"}
    return {token for token in re.findall(r"[a-z0-9]{4,}", text.lower()) if token not in stopwords}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()
