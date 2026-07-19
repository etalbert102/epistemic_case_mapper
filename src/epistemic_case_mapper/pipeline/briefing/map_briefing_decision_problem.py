from __future__ import annotations

import re
from typing import Any


FACET_TERMS = {
    "empirical_effect_or_association": {
        "associated",
        "association",
        "effect",
        "effects",
        "harmful",
        "beneficial",
        "neutral",
        "risk",
        "outcome",
        "increase",
        "decrease",
    },
    "intervention_or_policy_choice": {
        "adopt",
        "policy",
        "program",
        "intervention",
        "implement",
        "recommend",
        "guidance",
        "advice",
    },
    "risk_assessment": {"risk", "safety", "harm", "hazard", "danger", "safe", "harmful"},
    "causal_attribution": {"cause", "causal", "causes", "origin", "attribution", "because"},
    "forecast_or_prediction": {"forecast", "predict", "future", "likely", "probability", "will"},
    "threshold_or_compliance_judgment": {"threshold", "comply", "compliance", "legal", "standard", "requirement"},
    "preference_sensitive_tradeoff": {"tradeoff", "cost", "benefit", "preference", "values", "acceptable"},
    "comparative_option_choice": {"versus", "compare", "comparison", "better", "worse", "option", "alternative"},
    "information_sufficiency_or_due_diligence": {"enough", "sufficient", "uncertain", "evidence", "investigate"},
}

POLARITY_ANSWERS = (
    ("meaningfully_harmful", ("harmful", "harm", "risk")),
    ("neutral_or_not_meaningfully_harmful", ("neutral", "not harmful", "not associated")),
    ("beneficial", ("beneficial", "benefit", "protective")),
)


def build_decision_problem_report(scaffold: dict[str, Any], *, question: str) -> dict[str, Any]:
    text = _combined_text(question, scaffold)
    facets = _decision_facets(question, text)
    candidate_answers = _candidate_answers(question, facets)
    return {
        "schema_id": "decision_problem_report_v1",
        "method": "deterministic_question_facet_and_candidate_answer_report_only",
        "decision_question": question or str(scaffold.get("question", "")),
        "facets": facets,
        "primary_facets": [row["facet"] for row in facets if row.get("status") == "detected"][:4],
        "candidate_answer_count": len(candidate_answers),
        "candidate_answer_ids": [row["candidate_answer_id"] for row in candidate_answers],
        "warnings": _warnings(facets, candidate_answers),
    }


def build_candidate_answer_set(scaffold: dict[str, Any], *, question: str) -> dict[str, Any]:
    report = build_decision_problem_report(scaffold, question=question)
    answers = _candidate_answers(question, report["facets"])
    return {
        "schema_id": "candidate_answer_set_v1",
        "method": "deterministic_candidate_answers_from_question_and_answer_frame_report_only",
        "decision_question": question or str(scaffold.get("question", "")),
        "candidate_answers": answers,
        "candidate_answer_count": len(answers),
        "warnings": _answer_warnings(answers),
    }


def _decision_facets(question: str, text: str) -> list[dict[str, Any]]:
    question_terms = _terms(question)
    all_terms = _terms(text)
    facets = []
    for facet, indicators in FACET_TERMS.items():
        matched = sorted(term for term in indicators if term in question_terms or term in all_terms)
        if matched:
            facets.append(
                {
                    "facet": facet,
                    "status": "detected",
                    "confidence": "medium" if any(term in question_terms for term in matched) else "low",
                    "matched_terms": matched[:10],
                    "basis": "question_and_available_scaffold_terms",
                }
            )
    if not facets:
        facets.append(
            {
                "facet": "mixed_or_unclear",
                "status": "detected",
                "confidence": "low",
                "matched_terms": [],
                "basis": "no_specific_decision_facet_detected",
            }
        )
    return facets


def _candidate_answers(question: str, facets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    answers: list[dict[str, Any]] = []
    lowered = question.lower()
    for answer_id, triggers in POLARITY_ANSWERS:
        if any(trigger in lowered for trigger in triggers):
            answers.append(
                _answer(
                    answer_id,
                    label=answer_id.replace("_", " "),
                    stance=answer_id,
                    basis="explicit_or_implied_question_polarity",
                )
            )
    if "whether" in lowered or "should" in lowered:
        answers.extend(
            [
                _answer("yes_or_favor", label="yes / favor the proposition", stance="supports_proposition", basis="yes_no_question_shape"),
                _answer("no_or_reject", label="no / reject the proposition", stance="challenges_proposition", basis="yes_no_question_shape"),
            ]
        )
    if any(row.get("facet") == "comparative_option_choice" for row in facets):
        answers.append(_answer("depends_on_comparator", label="depends on comparator or alternative", stance="conditional", basis="comparative_question_facet"))
    if any(row.get("facet") in {"risk_assessment", "empirical_effect_or_association"} for row in facets):
        answers.append(_answer("subgroup_or_scope_dependent", label="depends on subgroup, dose, endpoint, or scope", stance="conditional", basis="risk_or_effect_question_facet"))
    if not answers:
        answers.append(_answer("insufficient_or_mixed", label="insufficient or mixed evidence", stance="uncertain", basis="fallback_for_unclear_question"))
    return _dedupe_answers(answers)


def _answer(candidate_answer_id: str, *, label: str, stance: str, basis: str) -> dict[str, Any]:
    return {
        "candidate_answer_id": candidate_answer_id,
        "label": label,
        "stance": stance,
        "basis": basis,
        "status": "report_only_candidate",
    }


def _combined_text(question: str, scaffold: dict[str, Any]) -> str:
    parts = [question, str(scaffold.get("question", ""))]
    answer_frame = scaffold.get("answer_frame") if isinstance(scaffold.get("answer_frame"), dict) else {}
    parts.extend(str(answer_frame.get(key, "")) for key in ("default_answer", "main_uncertainty"))
    argument = scaffold.get("argument_model") if isinstance(scaffold.get("argument_model"), dict) else {}
    for key in ("strongest_support", "strongest_counterarguments", "scope_boundaries", "cruxes", "quantitative_anchors"):
        for row in argument.get(key, []) if isinstance(argument.get(key), list) else []:
            if isinstance(row, dict):
                parts.append(str(row.get("statement", "")))
    return " ".join(parts)


def _warnings(facets: list[dict[str, Any]], answers: list[dict[str, Any]]) -> list[str]:
    warnings = []
    if not facets or facets[0].get("facet") == "mixed_or_unclear":
        warnings.append("decision_facets_unclear")
    if not answers:
        warnings.append("candidate_answers_empty")
    return warnings


def _answer_warnings(answers: list[dict[str, Any]]) -> list[str]:
    return ["candidate_answers_report_only"] if answers else ["candidate_answers_empty"]


def _dedupe_answers(answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for answer in answers:
        answer_id = str(answer.get("candidate_answer_id", "")).strip()
        if not answer_id or answer_id in seen:
            continue
        seen.add(answer_id)
        result.append(answer)
    return result


def _terms(text: str) -> set[str]:
    lowered = text.lower()
    terms = set(re.findall(r"[a-z][a-z0-9\-]{2,}", lowered))
    if "not associated" in lowered:
        terms.add("not associated")
    return terms
