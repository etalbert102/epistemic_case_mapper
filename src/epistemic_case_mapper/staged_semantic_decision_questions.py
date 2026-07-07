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
    if "outcome_mismatch" in flags and not _question_allows_outcome_mismatch(question, claim_text):
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


def _question_allows_outcome_mismatch(question: str, claim_text: str) -> bool:
    return "outcome" in question or "endpoint" in question or bool(_content_terms(question) & _content_terms(claim_text))


def _mentions_child_population(text: str) -> bool:
    return bool(re.search(r"\b(?:infant|infants|toddler|toddlers|child|children|adolescent|adolescents|pediatric|paediatric)\b", text))


def _content_terms(text: str) -> set[str]:
    stopwords = {"about", "after", "also", "and", "are", "but", "for", "from", "has", "have", "into", "not", "that", "the", "their", "this", "with"}
    return {token for token in re.findall(r"[a-z0-9]{4,}", text.lower()) if token not in stopwords}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()
