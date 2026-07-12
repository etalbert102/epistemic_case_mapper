from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import dedupe as _dedupe


def deterministic_quantity_warnings(value: str, *, group: dict[str, Any], ledger_row: dict[str, Any]) -> list[str]:
    text = " ".join([value, str(ledger_row.get("claim") or ""), str(ledger_row.get("source_excerpt") or "")])
    lowered_group = _group_text(group).lower()
    warnings = []
    if _looks_like_age_scope(value) and not _group_about_age_scope(lowered_group):
        warnings.append("age_scope_quantity_not_group_measure")
    if _looks_like_heterogeneity(value) and "heterogeneity" not in lowered_group and "i2" not in lowered_group and "i²" not in lowered_group:
        warnings.append("heterogeneity_statistic_not_effect_measure")
    if _looks_like_p_value(value) and "statistical significance" not in lowered_group and "p-value" not in lowered_group:
        warnings.append("p_value_not_effect_measure")
    if _looks_like_non_quantity(value):
        warnings.append("non_numeric_quantity_value")
    if _looks_like_interval(value) and not _has_effect_pair_nearby(value, text):
        warnings.append("interval_without_local_effect_estimate")
    if _weak_quantity_claim_overlap(value, group=group, ledger_row=ledger_row):
        warnings.append("weak_quantity_proposition_overlap")
    if not str(ledger_row.get("claim") or "").strip() and not _quantity_in_group_text(value, lowered_group):
        warnings.append("quantity_without_source_claim")
    return _dedupe(warnings)


def deterministic_quantity_memo_use(
    value: str,
    *,
    group: dict[str, Any],
    ledger_row: dict[str, Any],
    warnings: list[str],
) -> str:
    lowered_group = _group_text(group).lower()
    if any(
        warning in warnings
        for warning in (
            "age_scope_quantity_not_group_measure",
            "heterogeneity_statistic_not_effect_measure",
            "p_value_not_effect_measure",
            "non_numeric_quantity_value",
        )
    ):
        return "no"
    if str(group.get("memo_role") or "") == "quantitative_anchor" and not warnings:
        return "yes"
    if _quantity_in_group_text(value, lowered_group):
        return "yes"
    if str(ledger_row.get("input_kind") or "") == "top_quantity_anchor" and not warnings:
        return "yes"
    if _looks_like_effect_quantity(value) and _source_claim_overlaps_group(group=group, ledger_row=ledger_row):
        return "yes" if not warnings else "context_only"
    return "context_only" if warnings else "yes"


def deterministic_quantity_interpretation(
    value: str,
    *,
    group: dict[str, Any],
    ledger_row: dict[str, Any],
    memo_use: str,
) -> str:
    if memo_use == "yes":
        source_claim = str(ledger_row.get("claim") or "").strip()
        if source_claim:
            return f"{value}: quantifies the source claim that {source_claim}"
        return f"{value}: quantifies the group proposition."
    if memo_use == "context_only":
        return f"{value}: retained as source context, not a required memo-facing quantitative anchor."
    return f"{value}: does not directly quantify the group proposition for the decision question."


def deterministic_quantity_rationale(
    value: str,
    *,
    group: dict[str, Any],
    ledger_row: dict[str, Any],
    memo_use: str,
    warnings: list[str],
) -> str:
    if warnings:
        return f"Deterministic binding classified as {memo_use} due to: {', '.join(warnings)}."
    if memo_use == "yes":
        return "Quantity appears semantically tied to the group proposition or a compatible source claim."
    if memo_use == "context_only":
        return "Quantity is preserved for traceability but is not clearly load-bearing for memo prose."
    return "Quantity does not quantify the group proposition."


def quantity_binding_confidence(candidate: dict[str, Any], *, memo_use: str, model_row: dict[str, Any]) -> str:
    if model_row:
        return "medium" if candidate.get("deterministic_warnings") else "high"
    if candidate.get("deterministic_warnings"):
        return "medium" if memo_use != "yes" else "low"
    return "medium"


def _group_text(group: dict[str, Any]) -> str:
    return " ".join([str(group.get("proposition") or ""), str(group.get("rationale") or ""), str(group.get("answer_impact") or "")])


def _looks_like_age_scope(value: str) -> bool:
    text = str(value or "").lower()
    return bool(
        re.search(r"\b(?:aged?\s*)?\d+(?:\.\d+)?\s*(?:to|-)\s*\d+(?:\.\d+)?\s*months?\s*old\b", text)
        or re.search(r"\b\d+(?:\.\d+)?\s*months?\s*old\b", text)
        or re.search(r"\b\d+(?:\.\d+)?\s*(?:to|-)\s*\d+(?:\.\d+)?\s*years?\s*old\b", text)
    )


def _group_about_age_scope(group_text: str) -> bool:
    terms = ("age", "infant", "child", "children", "toddler", "pediatric", "older adult", "elderly", "years old", "months old")
    return any(term in group_text for term in terms)


def _looks_like_heterogeneity(value: str) -> bool:
    return bool(re.search(r"\b(?:i2|i²)\s*=\s*\d+(?:\.\d+)?%", str(value or ""), flags=re.IGNORECASE))


def _looks_like_p_value(value: str) -> bool:
    return bool(re.search(r"\bp\s*(?:=|<|>|≤|>=|<=)\s*\d+(?:\.\d+)?\b", str(value or ""), flags=re.IGNORECASE))


def _looks_like_non_quantity(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    if re.search(r"\d", text):
        return False
    quantity_patterns = (
        r"\bincreas(?:e|ed|es|ing)\b",
        r"\bdecreas(?:e|ed|es|ing)\b",
        r"\bratio\b",
        r"\brisk\b",
        r"\bhazard\b",
        r"\bodds\b",
        r"\bpercent\b",
        r"\bper\s+(?:day|week|month|year)\b",
        r"/(?:day|week|month|year)\b",
    )
    return not any(re.search(pattern, text) for pattern in quantity_patterns)


def _looks_like_interval(value: str) -> bool:
    text = str(value or "").lower()
    return "confidence interval" in text or re.search(r"\bci\b", text) is not None


def _has_effect_pair_nearby(value: str, text: str) -> bool:
    lowered = " ".join([value, text]).lower()
    pattern = r"\b(?:hr|rr|or|md|hazard ratio|relative risk|odds ratio|mean difference|risk ratio)\b"
    return bool(re.search(pattern, lowered))


def _looks_like_effect_quantity(value: str) -> bool:
    text = str(value or "").lower()
    return bool(
        re.search(r"\b(?:hr|rr|or|md|ci|hazard ratio|relative risk|odds ratio|mean difference|confidence interval)\b", text)
        or "%" in text
        or "per day" in text
    )


def _weak_quantity_claim_overlap(value: str, *, group: dict[str, Any], ledger_row: dict[str, Any]) -> bool:
    if _quantity_in_group_text(value, " ".join([str(group.get("proposition") or ""), str(group.get("rationale") or "")]).lower()):
        return False
    quantity_terms = _content_terms(" ".join([value, str(ledger_row.get("claim") or ""), str(ledger_row.get("source_excerpt") or "")]))
    group_terms = _content_terms(_group_text(group))
    if not quantity_terms or not group_terms:
        return True
    return len(quantity_terms & group_terms) == 0


def _source_claim_overlaps_group(*, group: dict[str, Any], ledger_row: dict[str, Any]) -> bool:
    source_terms = _content_terms(" ".join([str(ledger_row.get("claim") or ""), str(ledger_row.get("source_excerpt") or "")]))
    group_terms = _content_terms(_group_text(group))
    return bool(source_terms and group_terms and source_terms & group_terms)


def _quantity_in_group_text(value: str, group_text: str) -> bool:
    value = str(value or "").strip().lower()
    if not value:
        return False
    if value in group_text:
        return True
    numbers = re.findall(r"\d+(?:\.\d+)?", value)
    return bool(numbers and all(number in group_text for number in numbers[:2]))


def _content_terms(text: str) -> set[str]:
    stop = {
        "about",
        "after",
        "also",
        "because",
        "before",
        "between",
        "could",
        "does",
        "from",
        "have",
        "into",
        "more",
        "most",
        "than",
        "that",
        "their",
        "there",
        "these",
        "this",
        "with",
        "without",
        "risk",
        "study",
        "source",
    }
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", str(text or "").lower())
        if token not in stop
    }
