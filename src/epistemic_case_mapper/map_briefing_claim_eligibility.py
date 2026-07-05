from __future__ import annotations

import re
from typing import Any


def claim_noise_profile(claim: dict[str, Any]) -> dict[str, Any]:
    compact = re.sub(r"\s+", " ", _claim_text_bundle(claim)).strip()
    if _looks_like_glossary_or_abbreviation_row(compact):
        return {"kind": "glossary_or_abbreviation_row", "penalty": 5}
    if _looks_like_reference_or_metadata_row(compact):
        return {"kind": "reference_or_metadata_row", "penalty": 5}
    if _looks_like_boilerplate_disclosure(compact):
        return {"kind": "boilerplate_disclosure", "penalty": 4}
    if _looks_like_publisher_or_license_boilerplate(compact):
        return {"kind": "publisher_or_license_boilerplate", "penalty": 4}
    if _looks_like_statistical_method_trivia(compact):
        return {"kind": "statistical_method_trivia", "penalty": 2}
    if _looks_like_truncated_or_orphan_fragment(compact):
        return {"kind": "truncated_or_orphan_fragment", "penalty": 3}
    if len(compact) > 900:
        return {"kind": "overlong_claim", "penalty": 2}
    return {"kind": "none", "penalty": 0}


def claim_eligibility_profile(
    *,
    claim: dict[str, Any],
    section: str,
    score: int,
    weight: str,
    concepts: list[str],
    decision_slots: list[str],
    evidence_slots: list[str],
    noise: dict[str, Any],
    question: str = "",
) -> dict[str, Any]:
    question_alignment = _question_alignment(_claim_text_bundle(claim), question)
    noise_severity = _noise_severity(noise)
    relevance = _decision_relevance_score(
        section=section,
        score=score,
        weight=weight,
        concepts=concepts,
        decision_slots=decision_slots,
        evidence_slots=evidence_slots,
        noise_severity=noise_severity,
        question_alignment=question_alignment,
    )
    appendix_only = noise_severity == "high" or relevance <= 2
    question_fit = question_alignment["status"] in {"strong", "not_supplied"}
    section_eligibility = {
        "decision_brief": (
            not appendix_only
            and section in {"main_support", "conflicting_evidence", "scope_limits"}
            and relevance >= 5
            and question_fit
        ),
        "practical_read": not appendix_only and section in {"main_support", "scope_limits"} and relevance >= 4 and question_fit,
        "why_this_read": not appendix_only and relevance >= 3,
        "evidence_carrying_conclusion": not appendix_only and relevance >= 3,
        "scope_and_exceptions": not appendix_only and section == "scope_limits" and relevance >= 3 and question_fit,
        "decision_cruxes": not appendix_only and section in {"main_support", "conflicting_evidence", "scope_limits"} and relevance >= 4 and question_fit,
        "limits": noise_severity in {"medium", "high"} or section == "method_limits",
    }
    return {
        "schema_id": "claim_eligibility_v1",
        "decision_relevance_score": relevance,
        "question_alignment": question_alignment,
        "noise_severity": noise_severity,
        "section_eligibility": section_eligibility,
        "top_line_eligible": bool(section_eligibility["decision_brief"]),
        "crux_eligible": bool(section_eligibility["decision_cruxes"]),
        "appendix_only": appendix_only,
        "reasons": _eligibility_reasons(section, relevance, noise_severity, question_alignment, concepts, decision_slots),
    }


def _claim_text_bundle(claim: dict[str, Any]) -> str:
    return " ".join(str(claim.get(key, "") or "") for key in ("claim", "text", "excerpt", "source_span", "role")).lower()


def _decision_relevance_score(
    *,
    section: str,
    score: int,
    weight: str,
    concepts: list[str],
    decision_slots: list[str],
    evidence_slots: list[str],
    noise_severity: str,
    question_alignment: dict[str, Any],
) -> int:
    relevance = min(4, max(0, int(score)))
    relevance += 2 if weight == "high" else 1 if weight == "medium" else 0
    if section in {"main_support", "conflicting_evidence", "scope_limits"}:
        relevance += 1
    relevance += 2 if decision_slots else 0
    relevance += 1 if evidence_slots else 0
    relevance += min(2, len(concepts)) if concepts else 0
    overlap_count = int(question_alignment.get("overlap_count", 0) or 0)
    if question_alignment.get("status") == "not_supplied":
        relevance += 1
    elif overlap_count >= 2:
        relevance += 2
    elif overlap_count == 0:
        relevance -= 2
    if section == "method_limits":
        relevance -= 1
    relevance -= 2 if noise_severity == "medium" else 5 if noise_severity == "high" else 0
    return max(0, min(10, relevance))


def _question_alignment(text: str, question: str) -> dict[str, Any]:
    terms = _question_terms(question)
    if not terms:
        return {"status": "not_supplied", "overlap_count": 0, "matched_terms": [], "question_terms": []}
    text_terms = set(_content_terms(text))
    matched = [term for term in terms if term in text_terms or _singular(term) in text_terms]
    status = "strong" if len(matched) >= 2 else "weak" if matched else "none"
    return {"status": status, "overlap_count": len(matched), "matched_terms": matched[:8], "question_terms": terms[:12]}


def _question_terms(question: str) -> list[str]:
    generic = {
        "about", "advice", "adopt", "beneficial", "classify", "decision", "decide", "generally",
        "harmful", "meaningfully", "neutral", "prioritize", "question", "recommend", "risk", "risks",
        "should", "treated", "treat", "whether",
    }
    return [term for term in _content_terms(question) if term not in generic]


def _content_terms(text: str) -> list[str]:
    stopwords = {"about", "after", "also", "claim", "claims", "does", "evidence", "from", "have", "into", "more", "source", "than", "that", "this", "with"}
    terms: list[str] = []
    for term in re.findall(r"[a-z][a-z0-9\-]{3,}", text.lower()):
        if term not in stopwords and term not in terms:
            terms.append(term)
    return terms


def _singular(term: str) -> str:
    if term.endswith("ies") and len(term) > 4:
        return term[:-3] + "y"
    if term.endswith("s") and len(term) > 4:
        return term[:-1]
    return term


def _noise_severity(noise: dict[str, Any]) -> str:
    penalty = int(noise.get("penalty", 0) or 0) if isinstance(noise, dict) else 0
    return "high" if penalty >= 4 else "medium" if penalty >= 2 else "low" if penalty else "none"


def _eligibility_reasons(
    section: str,
    relevance: int,
    noise_severity: str,
    question_alignment: dict[str, Any],
    concepts: list[str],
    decision_slots: list[str],
) -> list[str]:
    reasons = [f"section={section}", f"relevance={relevance}", f"noise={noise_severity}", f"question_alignment={question_alignment.get('status')}"]
    if concepts:
        reasons.append(f"concepts={len(concepts)}")
    if decision_slots:
        reasons.append(f"decision_slots={len(decision_slots)}")
    return reasons


def _looks_like_glossary_or_abbreviation_row(text: str) -> bool:
    lowered = text.lower().strip()
    if re.match(r"^(?:abbreviations?|acronyms?|definitions?|legend)\s*[:;]", lowered):
        return True
    separators = lowered.count(";") + lowered.count(",")
    return separators >= 8 and not re.search(r"\b(increase|decrease|associated|risk|effect|reduced|improved|worse|better)\b", lowered)


def _looks_like_reference_or_metadata_row(text: str) -> bool:
    lowered = text.lower()
    return bool(re.search(r"\b(?:doi|pmid|pmcid|issn|isbn|copyright|received|accepted|published|correspondence)\b", lowered)) or any(
        marker in lowered for marker in ("[google scholar]", "[pubmed]", "[crossref]")
    )


def _looks_like_truncated_or_orphan_fragment(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip()
    return "..." in compact or (len(compact) > 120 and bool(re.search(r"\b[a-z]\.?$", compact)))


def _looks_like_boilerplate_disclosure(text: str) -> bool:
    markers = (
        "received research grants", "received research support", "speaker fees", "honoraria",
        "scientific advisory board", "consultant to", "conflict of interest", "competing interests",
        "disclosures", "funding and travel support", "corresponding author on request",
    )
    return sum(1 for marker in markers if marker in text) >= 2 or ("professor" in text and "received" in text and len(text) > 700)


def _looks_like_publisher_or_license_boilerplate(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "all rights reserved",
            "creative commons",
            "copyright",
            "license",
            "linked-to entity",
            "not an endorsement",
            "product or service",
            "provided for convenience",
            "publisher",
            "terms of use",
        )
    )


def _looks_like_statistical_method_trivia(text: str) -> bool:
    markers = ("competing risk regression", "cox proportional hazards", "statistical software", "sensitivity analysis was performed using", "model was adjusted for")
    return any(marker in text for marker in markers) and not re.search(r"\b(mortality|death|event|cardiovascular|stroke|failure rate|outcome)\b", text)
