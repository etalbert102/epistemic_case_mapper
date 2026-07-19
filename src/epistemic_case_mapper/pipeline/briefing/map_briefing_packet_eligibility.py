from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_claim_eligibility import claim_noise_profile


def packet_candidate_eligibility(row: dict[str, Any]) -> dict[str, Any]:
    """Return whether a broad candidate should be eligible for the reader memo."""

    reasons: list[str] = []
    warnings: list[str] = []
    inclusion = str(row.get("inclusion_recommendation") or "").strip().lower()
    limits = {item.lower() for item in _string_list(row.get("limits")) + _string_list(row.get("limitations"))}
    claim = str(row.get("claim") or "").strip()
    noise = claim_noise_profile({"claim": claim, "text": claim, "excerpt": row.get("source_excerpt", "")})
    if inclusion == "appendix_only":
        reasons.append("appendix_only_candidate")
    if "off_question_risk" in limits or row.get("off_question_risk"):
        reasons.append("off_question_risk")
    if "fragment_risk" in limits or row.get("fragment_risk"):
        reasons.append("fragment_risk")
    if int(noise.get("penalty", 0) or 0) >= 4:
        reasons.append(str(noise.get("kind") or "high_noise"))
    elif int(noise.get("penalty", 0) or 0) >= 2 and not row.get("quantity_values"):
        reasons.append(str(noise.get("kind") or "medium_noise"))
    if _looks_like_table_or_figure_caption(claim):
        reasons.append("table_or_figure_caption")
    if _quantity_anchor_off_question(row):
        warnings.append("quantity_anchor_question_mismatch")
    return {
        "main_memo_eligible": not reasons,
        "reasons": _dedupe(reasons),
        "warnings": _dedupe(warnings),
        "noise_kind": noise.get("kind"),
        "noise_penalty": noise.get("penalty", 0),
    }


def question_overlap_count(text: str, question_terms: list[str]) -> int:
    if not question_terms:
        return 1
    terms = set(question_content_terms(text))
    return sum(1 for term in question_terms if term in terms or _singular(term) in terms)


def question_content_terms(text: str) -> list[str]:
    generic = {
        "about",
        "advice",
        "adopt",
        "after",
        "beneficial",
        "because",
        "before",
        "classify",
        "decision",
        "decide",
        "during",
        "especially",
        "evidence",
        "generally",
        "harmful",
        "into",
        "meaningfully",
        "neutral",
        "overall",
        "prioritize",
        "question",
        "recommend",
        "respect",
        "risk",
        "risks",
        "should",
        "studies",
        "study",
        "treated",
        "treat",
        "whether",
        "while",
        "with",
        "within",
    }
    terms: list[str] = []
    for term in re.findall(r"[a-z][a-z0-9\-]{3,}", text.lower()):
        if term not in generic and term not in terms:
            terms.append(term)
    return terms


def decision_relevance_assessment(text: str, *, question_terms: list[str], decision_role: str = "") -> dict[str, Any]:
    overlap = question_overlap_count(text, question_terms)
    role = str(decision_role or "").strip()
    primary_roles = {"strongest_support", "counterweight", "quantitative_anchor", "decision_crux"}
    if not question_terms:
        status = "not_assessed"
    elif overlap >= min(2, len(question_terms)):
        status = "direct_question_overlap"
    elif overlap == 1:
        status = "partial_question_overlap"
    else:
        status = "low_question_overlap"
    warnings: list[str] = []
    if status == "low_question_overlap" and role in primary_roles:
        warnings.append("primary_evidence_low_question_overlap")
    return {
        "schema_id": "decision_relevance_assessment_v1",
        "method": "deterministic_question_term_overlap_report_only",
        "question_overlap_count": overlap,
        "question_relevance_status": status,
        "decision_axis": _decision_axis_for_role(role),
        "warnings": warnings,
    }


def _decision_axis_for_role(role: str) -> str:
    return {
        "strongest_support": "default_answer_support",
        "counterweight": "counterevidence",
        "scope_boundary": "scope_boundary",
        "decision_crux": "answer_changing_uncertainty",
        "quantitative_anchor": "quantitative_anchor",
        "mechanism": "mechanism_or_proxy",
        "context": "context",
    }.get(role, "unclassified")


def _looks_like_table_or_figure_caption(text: str) -> bool:
    stripped = text.strip()
    return bool(re.match(r"^(?:e?table|e?figure|fig\.?|table)\s+\d+[.:]", stripped, flags=re.IGNORECASE))


def _quantity_anchor_off_question(row: dict[str, Any]) -> bool:
    if str(row.get("decision_role") or "") != "quantitative_anchor":
        return False
    return int(row.get("question_overlap_count", 0) or 0) < 1


def _singular(term: str) -> str:
    if term.endswith("ies") and len(term) > 4:
        return term[:-3] + "y"
    if term.endswith("s") and len(term) > 4:
        return term[:-1]
    return term


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
