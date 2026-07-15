from __future__ import annotations

from typing import Any


def reader_evidence_role(row: dict[str, Any]) -> str:
    role = str(row.get("role") or "").strip()
    relation = str(row.get("answer_relation") or "").strip()
    function = str(row.get("memo_function") or "").strip()
    source_memo_role = str(row.get("source_memo_role") or "").strip()
    obligation = str(row.get("obligation_level") or "").strip()
    if role in {"off_question", "excluded"} or relation in {"off_question", "not_relevant"} or obligation in {"off_question", "not_relevant"}:
        return "excluded_from_answer"
    if role == "scope_boundary" or relation == "bounds_scope" or function == "scope_boundary" or source_memo_role == "scope_or_applicability":
        return "scope_boundary"
    if role == "decision_crux" or relation == "identifies_crux" or function == "crux" or source_memo_role == "decision_crux":
        return "decision_crux"
    if role == "quantitative_anchor" or function in {"quantity_anchor", "mechanism", "explanation"} or source_memo_role == "quantitative_anchor":
        return "effect_size_or_mechanism"
    if looks_like_calibrator(row) and relation != "bounds_scope":
        return "effect_size_or_mechanism"
    if role == "strongest_counterweight" or relation == "challenges_answer" or function == "counterweight" or source_memo_role == "load_bearing_counterweight":
        return "true_counterweight"
    if role == "strongest_support" or relation == "supports_answer" or function == "answer_anchor" or source_memo_role == "load_bearing_primary_support":
        return "main_answer_evidence"
    if role in {"mechanism_or_explanation", "context_only"} or relation == "contextualizes_answer" or source_memo_role == "mechanism_or_context":
        return "practical_translation"
    return "practical_translation"


def source_weight_lane(row: dict[str, Any]) -> str:
    reader_role = reader_evidence_role(row)
    if reader_role == "main_answer_evidence":
        return "primary_answer_drivers"
    if reader_role == "effect_size_or_mechanism":
        return "quantitative_or_interpretive_calibrators"
    if reader_role == "scope_boundary":
        return "scope_limiters"
    if reader_role == "true_counterweight":
        return "counterweights_or_tensions"
    if reader_role == "decision_crux":
        return "decision_cruxes"
    if reader_role == "excluded_from_answer":
        return "excluded_from_answer"
    return "context_only"


def looks_like_calibrator(row: dict[str, Any]) -> bool:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("reader_claim", "claim", "decision_relevance", "memo_function", "source_appraisal_note")
    ).lower()
    if not text:
        return False
    if any(term in text for term in ("inconsistent", "no association", "confound", "confounding", "contradict", "challenge")):
        return False
    return any(
        term in text
        for term in (
            "biomarker",
            "marker",
            "surrogate",
            "mechanism",
            "physiological",
            "intermediate endpoint",
            "effect size",
            "magnitude",
        )
    )
