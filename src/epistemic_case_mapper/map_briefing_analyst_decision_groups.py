from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


SECTION_BY_MEMO_USE = {
    "load_bearing_primary_support": "primary_reasoning_chain",
    "load_bearing_counterweight": "main_counterweights",
    "decision_crux": "decision_cruxes",
    "scope_or_applicability": "scope_and_applicability",
    "quantitative_anchor": "quantitative_anchors",
    "mechanism_or_context": "background_context",
    "background_only": "background_context",
    "needs_human_or_model_review": "background_context",
}

FOREGROUND_MEMO_USES = {
    "load_bearing_primary_support",
    "load_bearing_counterweight",
    "quantitative_anchor",
    "scope_or_applicability",
    "decision_crux",
    "mechanism_or_context",
}


def build_groups_from_decision_model(
    decision_model: dict[str, Any],
    ledger_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if str(decision_model.get("schema_id") or "") != "analyst_decision_model_v1":
        return [], {}
    groups = []
    covered_ids: set[str] = set()
    unknown_ids: set[str] = set()
    for index, row in enumerate(_list(decision_model.get("evidence_groups")), start=1):
        if not isinstance(row, dict):
            continue
        requested_ids = _string_list(row.get("covered_evidence_item_ids"))
        evidence_ids = _dedupe([evidence_id for evidence_id in requested_ids if evidence_id in ledger_by_id])
        unknown_ids.update(evidence_id for evidence_id in requested_ids if evidence_id not in ledger_by_id)
        if not evidence_ids:
            continue
        groups.append(_group_from_decision_model_row(index, row, evidence_ids, ledger_by_id))
        covered_ids.update(evidence_ids)
    grouped_quantity_ids = _attach_uncovered_quantity_rows(groups, ledger_by_id, covered_ids)
    unbound_quantity_ids = _append_unbound_quantity_groups(groups, ledger_by_id, covered_ids)
    disposition_accounted = {
        str(row.get("evidence_item_id") or "")
        for row in _list(decision_model.get("evidence_dispositions"))
        if isinstance(row, dict)
        and str(row.get("evidence_item_id") or "").strip()
        and str(row.get("evidence_item_id") or "") in ledger_by_id
        and str(row.get("disposition") or "") in {"background", "not_decision_relevant", "covered_by_group", "needs_review"}
    }
    explicitly_downgraded = {
        str(row.get("evidence_item_id") or "")
        for row in _list(decision_model.get("evidence_dispositions"))
        if isinstance(row, dict)
        and str(row.get("disposition") or "") == "not_decision_relevant"
        and str(row.get("evidence_item_id") or "") in ledger_by_id
    }
    return sorted(groups, key=lambda item: (int(item.get("importance_rank", 100) or 100), str(item.get("group_id") or ""))), {
        "schema_id": "analyst_group_accounting_v1",
        "method": "global_analyst_decision_model_grouping",
        "grouped_quantity_row_ids": grouped_quantity_ids,
        "unbound_quantity_group_ids": unbound_quantity_ids,
        "group_count": len(groups),
        "covered_evidence_item_ids": sorted(covered_ids),
        "accounted_evidence_item_ids": sorted(covered_ids | disposition_accounted | explicitly_downgraded),
        "explicitly_downgraded_evidence_item_ids": sorted(explicitly_downgraded),
        "unknown_evidence_item_ids": sorted(unknown_ids),
        "foreground_group_count": sum(1 for group in groups if group.get("memo_role") in FOREGROUND_MEMO_USES),
    }


def _group_from_decision_model_row(
    index: int,
    row: dict[str, Any],
    evidence_ids: list[str],
    ledger_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    memo_role = str(row.get("memo_role") or "needs_human_or_model_review")
    return _drop_empty(
        {
            "group_id": str(row.get("group_id") or f"analyst_decision_group_{index:03d}"),
            "proposition": _short_text(str(row.get("proposition") or _first_ledger_claim(evidence_ids, ledger_by_id)), 620),
            "memo_role": memo_role if memo_role in SECTION_BY_MEMO_USE else "needs_human_or_model_review",
            "importance_rank": int(row.get("importance_rank", 100) or 100),
            "covered_evidence_item_ids": evidence_ids,
            "source_ids": _dedupe([source_id for evidence_id in evidence_ids for source_id in _string_list(ledger_by_id[evidence_id].get("source_ids"))]),
            "source_labels": _dedupe([source for evidence_id in evidence_ids for source in _string_list(ledger_by_id[evidence_id].get("source_labels"))]),
            "quantity_values": _dedupe(
                [
                    *_string_list(row.get("quantity_values")),
                    *[
                        quantity
                        for evidence_id in evidence_ids
                        for quantity in _string_list(ledger_by_id[evidence_id].get("quantity_values"))
                    ],
                ]
            ),
            "applicability_limits": _dedupe([*_string_list(row.get("applicability_limits"))])[:8],
            "rationale": _short_text(str(row.get("rationale") or row.get("answer_impact") or "Analyst decision model grouped this evidence."), 420),
            "conflict_note": _short_text(str(row.get("conflict_note") or ""), 320),
            "evidence_strength": _short_text(str(row.get("evidence_strength") or ""), 180),
            "answer_impact": _short_text(str(row.get("answer_impact") or ""), 260),
            "uncertainty_type": _short_text(str(row.get("uncertainty_type") or ""), 160),
        }
    )


def _attach_uncovered_quantity_rows(
    groups: list[dict[str, Any]],
    ledger_by_id: dict[str, dict[str, Any]],
    covered_ids: set[str],
) -> list[str]:
    grouped = []
    for evidence_id, row in ledger_by_id.items():
        if evidence_id in covered_ids or str(row.get("input_kind") or "") != "top_quantity_anchor":
            continue
        target = _quantity_target_group(row, groups)
        if target is None:
            continue
        target["covered_evidence_item_ids"] = _dedupe([*_string_list(target.get("covered_evidence_item_ids")), evidence_id])
        target["quantity_values"] = _dedupe([*_string_list(target.get("quantity_values")), *_string_list(row.get("quantity_values"))])
        target["source_ids"] = _dedupe([*_string_list(target.get("source_ids")), *_string_list(row.get("source_ids"))])
        target["source_labels"] = _dedupe([*_string_list(target.get("source_labels")), *_string_list(row.get("source_labels"))])
        covered_ids.add(evidence_id)
        grouped.append(evidence_id)
    return grouped


def _quantity_target_group(row: dict[str, Any], groups: list[dict[str, Any]]) -> dict[str, Any] | None:
    source_ids = set(_string_list(row.get("source_ids")))
    source_labels = _string_list(row.get("source_labels"))
    quantity_values = set(_string_list(row.get("quantity_values")))
    best: tuple[float, dict[str, Any] | None] = (0.0, None)
    for group in groups:
        if group.get("memo_role") not in FOREGROUND_MEMO_USES:
            continue
        group_sources = set(_string_list(group.get("source_ids")))
        group_quantities = set(_string_list(group.get("quantity_values")))
        if quantity_values and (
            quantity_values & group_quantities or _quantity_signature_overlap(quantity_values, group_quantities)
        ):
            return group
        if source_ids and source_ids & group_sources and _quantity_compatible_with_group(row, group):
            return group
        score = _source_label_match_score(source_labels, _string_list(group.get("source_labels")))
        if score > best[0] and _quantity_compatible_with_group(row, group):
            best = (score, group)
    return best[1] if best[0] >= 0.34 else None


def _append_unbound_quantity_groups(
    groups: list[dict[str, Any]],
    ledger_by_id: dict[str, dict[str, Any]],
    covered_ids: set[str],
) -> list[str]:
    unbound = []
    for evidence_id, row in ledger_by_id.items():
        if evidence_id in covered_ids or str(row.get("input_kind") or "") != "top_quantity_anchor":
            continue
        groups.append(
            _drop_empty(
                {
                    "group_id": f"analyst_unbound_quantity_{len(unbound) + 1:03d}",
                    "proposition": _short_text(str(row.get("claim") or evidence_id), 320),
                    "memo_role": "quantitative_anchor",
                    "importance_rank": int(row.get("current_priority", 80) or 80),
                    "covered_evidence_item_ids": [evidence_id],
                    "source_ids": _string_list(row.get("source_ids")),
                    "source_labels": _string_list(row.get("source_labels")),
                    "quantity_values": _string_list(row.get("quantity_values")),
                    "rationale": "Retained as a separate quantitative anchor because no semantically compatible analyst group was available.",
                    "uncertainty_type": "needs_context",
                }
            )
        )
        covered_ids.add(evidence_id)
        unbound.append(evidence_id)
    return unbound


def _quantity_compatible_with_group(row: dict[str, Any], group: dict[str, Any]) -> bool:
    quantity_terms = _content_terms(
        " ".join(
            [
                str(row.get("claim") or ""),
                " ".join(_string_list(row.get("quantity_values"))),
                str(row.get("quantity_type") or ""),
            ]
        )
    )
    group_terms = _content_terms(
        " ".join(
            [
                str(group.get("proposition") or ""),
                str(group.get("rationale") or ""),
                str(group.get("answer_impact") or ""),
                str(group.get("conflict_note") or ""),
            ]
        )
    )
    if not quantity_terms or not group_terms:
        return False
    overlap = quantity_terms & group_terms
    if overlap:
        return True
    if _numeric_only_quantity(row):
        return False
    return False


def _numeric_only_quantity(row: dict[str, Any]) -> bool:
    text = " ".join([str(row.get("claim") or ""), " ".join(_string_list(row.get("quantity_values")))])
    terms = _content_terms(text)
    return not terms or all(re.fullmatch(r"\d+(?:\.\d+)?", term) for term in terms)


def _quantity_signature_overlap(left_values: set[str], right_values: set[str]) -> bool:
    left = {_quantity_signature(value) for value in left_values}
    right = {_quantity_signature(value) for value in right_values}
    left.discard("")
    right.discard("")
    return bool(left & right)


def _quantity_signature(value: str) -> str:
    text = str(value or "").lower()
    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    if not numbers:
        return ""
    prefix = "ci" if "ci" in text or "confidence interval" in text else ""
    if re.search(r"\bhr\b|hazard ratio", text):
        prefix = "hr"
    elif re.search(r"\brr\b|relative risk", text):
        prefix = "rr"
    elif re.search(r"\bor\b|odds ratio", text):
        prefix = "or"
    return f"{prefix}:{','.join(numbers[:4])}"


def _source_label_match_score(left_labels: list[str], right_labels: list[str]) -> float:
    best = 0.0
    for left in left_labels:
        left_terms = _label_terms(left)
        if not left_terms:
            continue
        for right in right_labels:
            right_terms = _label_terms(right)
            if not right_terms:
                continue
            overlap = len(left_terms & right_terms) / max(1, min(len(left_terms), len(right_terms)))
            best = max(best, overlap)
    return best


def _label_terms(label: str) -> set[str]:
    stop = {"and", "the", "for", "with", "from", "study", "review", "authors", "evidence", "risk"}
    return {
        term
        for term in re.findall(r"[a-z0-9]+", str(label or "").lower())
        if len(term) > 2 and term not in stop
    }


def _content_terms(text: str) -> set[str]:
    stop = {
        "and",
        "are",
        "can",
        "confidence",
        "consumption",
        "effect",
        "evidence",
        "for",
        "from",
        "has",
        "have",
        "interval",
        "may",
        "not",
        "per",
        "ratio",
        "risk",
        "study",
        "the",
        "this",
        "with",
    }
    return {
        term
        for term in re.findall(r"[a-z0-9]+", str(text or "").lower())
        if len(term) > 2 and term not in stop
    }


def _first_ledger_claim(evidence_ids: list[str], ledger_by_id: dict[str, dict[str, Any]]) -> str:
    for evidence_id in evidence_ids:
        claim = str(ledger_by_id.get(evidence_id, {}).get("claim") or "").strip()
        if claim:
            return claim
    return evidence_ids[0] if evidence_ids else ""


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}
