from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_quantity_retention import quantity_retained


def build_priority_quantity_contracts(packet: dict[str, Any]) -> dict[str, Any]:
    """Build compact decision-useful quantity contracts from the memo-ready packet."""

    rows = []
    for item in _list(_dict(packet).get("evidence_items")):
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("item_id") or "").strip()
        if not evidence_id or not _item_contract_eligible(item):
            continue
        candidates = [
            *_quantity_rows(item),
            *_numeric_must_preserve_rows(item),
        ]
        for candidate in candidates:
            if not _quantity_contract_eligible(candidate, item):
                continue
            rows.append(_contract_row(item, candidate))
    rows = _dedupe_contract_rows(rows)
    return {
        "schema_id": "priority_quantity_contracts_v1",
        "selection_method": "analyst_quantity_relevance_plus_numeric_must_preserve_terms",
        "rule": (
            "When a memo uses the related evidence claim, preserve the quantity with the same "
            "subgroup, comparator, endpoint, and decision role."
        ),
        "rows": rows,
        "contract_count": len(rows),
        "evidence_item_count": len({row.get("evidence_id") for row in rows}),
    }


def contracts_for_evidence_ids(contracts: dict[str, Any] | list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    rows = _contract_rows(contracts)
    wanted = {str(evidence_id).strip() for evidence_id in evidence_ids if str(evidence_id).strip()}
    if not wanted:
        return []
    return [row for row in rows if str(row.get("evidence_id") or "").strip() in wanted]


def build_priority_quantity_contract_coverage_report(memo: str, contracts: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    rows = _contract_rows(contracts)
    warnings = []
    for row in rows:
        quantity = str(row.get("quantity_text") or "").strip()
        if not quantity:
            continue
        if not quantity_retained(memo, {"value": quantity, "retention_phrase": quantity, "interpretation": row.get("decision_role", "")}):
            warnings.append(
                {
                    "evidence_id": row.get("evidence_id"),
                    "missing_quantity": quantity,
                    "decision_role": row.get("decision_role"),
                    "claim": row.get("claim"),
                }
            )
    return {
        "schema_id": "priority_quantity_contract_coverage_report_v1",
        "status": "ready" if not warnings else "warning",
        "contract_count": len(rows),
        "missing_contract_count": len(warnings),
        "warnings": warnings,
    }


def compact_priority_quantity_contracts_for_prompt(rows: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    compact = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        compact.append(
            _drop_empty(
                {
                    "evidence_id": row.get("evidence_id"),
                    "quantity": row.get("quantity_text"),
                    "decision_role": row.get("decision_role"),
                    "claim": row.get("claim"),
                    "source_ids": row.get("source_ids"),
                    "required_if_claim_used": row.get("required_if_claim_used", True),
                }
            )
        )
    return compact


def _quantity_rows(item: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for quantity in _list(item.get("quantities")):
        if not isinstance(quantity, dict):
            continue
        text = _quantity_text(quantity)
        if not text:
            continue
        analyst = _dict(quantity.get("analyst_quantity_relevance"))
        rows.append(
            _drop_empty(
                {
                    "quantity_text": text,
                    "decision_role": analyst.get("quantity_role") or quantity.get("quantity_role"),
                    "rationale": analyst.get("rationale"),
                    "memo_inclusion": analyst.get("memo_inclusion") or quantity.get("memo_use"),
                    "must_retain": quantity.get("must_retain"),
                    "source_ids": quantity.get("source_ids"),
                }
            )
        )
    return rows


def _numeric_must_preserve_rows(item: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for term in _string_list(item.get("must_preserve_terms")):
        if not _term_has_decision_quantity(term):
            continue
        rows.append(
            _drop_empty(
                {
                    "quantity_text": term,
                    "decision_role": _decision_role_from_text(term, item),
                    "memo_inclusion": "must_use" if _item_required(item) else "supporting_context",
                }
            )
        )
    return rows


def _quantity_text(quantity: dict[str, Any]) -> str:
    analyst = _dict(quantity.get("analyst_quantity_relevance"))
    for value in (
        analyst.get("retention_phrase"),
        quantity.get("retention_phrase"),
        quantity.get("interpretation"),
        quantity.get("value"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _contract_row(item: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    evidence_id = str(item.get("item_id") or "").strip()
    quantity_text = str(candidate.get("quantity_text") or "").strip()
    claim = str(item.get("reader_claim") or item.get("natural_bottom_line") or item.get("claim") or "").strip()
    return _drop_empty(
        {
            "contract_id": _contract_id(evidence_id, quantity_text),
            "evidence_id": evidence_id,
            "quantity_text": quantity_text,
            "decision_role": candidate.get("decision_role") or _decision_role_from_text(quantity_text, item),
            "rationale": candidate.get("rationale"),
            "source_ids": _dedupe([*_string_list(candidate.get("source_ids")), *_string_list(item.get("source_ids"))]),
            "source_labels": item.get("source_labels") or ([item.get("source_label")] if item.get("source_label") else None),
            "claim": _short_text(claim, 360),
            "required_if_claim_used": True,
            "contract_level": "required_if_related_claim_used",
        }
    )


def _quantity_contract_eligible(candidate: dict[str, Any], item: dict[str, Any]) -> bool:
    text = str(candidate.get("quantity_text") or "").strip()
    if not text or not _term_has_decision_quantity(text):
        return False
    if _looks_like_background_context(item):
        return _high_priority_quantity_text(text)
    if candidate.get("must_retain") is True:
        return True
    inclusion = str(candidate.get("memo_inclusion") or "").strip().lower()
    if inclusion in {"must_use", "yes"}:
        return True
    return _high_priority_quantity_text(text) and _item_required(item)


def _item_contract_eligible(item: dict[str, Any]) -> bool:
    if _looks_like_background_context(item):
        return False
    relation = str(item.get("answer_relation") or "").lower()
    obligation = str(item.get("obligation_level") or "").lower()
    memo_inclusion = str(item.get("memo_inclusion") or "").lower()
    if relation in {"off_question", "not_relevant", "not_decision_relevant"}:
        return False
    if obligation in {"optional_context", "off_question", "not_relevant"}:
        return False
    if memo_inclusion in {"omit", "off_question", "not_relevant"}:
        return False
    return True


def _item_required(item: dict[str, Any]) -> bool:
    return bool(item.get("must_use")) or str(item.get("obligation_level") or "") in {"must_include", "should_include"}


def _looks_like_background_context(item: dict[str, Any]) -> bool:
    role = str(item.get("role") or "").lower()
    memo_function = str(item.get("memo_function") or "").lower()
    rank = item.get("importance_rank")
    return role == "background" or memo_function == "background" or (isinstance(rank, int) and rank > 12)


def _term_has_decision_quantity(text: str) -> bool:
    lowered = str(text or "").lower()
    if not re.search(r"\d", lowered):
        return False
    if re.fullmatch(r"(?:19|20)\d{2}(?:\s*[–-]\s*(?:19|20)\d{2})?", lowered.strip()):
        return False
    return _high_priority_quantity_text(lowered) or bool(re.search(r"\b(?:per day|/day|daily|egg|serving|mg|%|percent)\b", lowered))


def _high_priority_quantity_text(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(
        token in lowered
        for token in (
            "hazard ratio",
            "relative risk",
            "odds ratio",
            "confidence interval",
            "95% ci",
            " ci:",
            "md =",
            "mean difference",
            "i2",
            "per day",
            "/day",
            "dose",
            "subgroup",
        )
    )


def _decision_role_from_text(text: str, item: dict[str, Any]) -> str:
    combined = " ".join([str(text or ""), str(item.get("reader_claim") or ""), str(item.get("role") or ""), str(item.get("memo_function") or "")]).lower()
    if any(token in combined for token in ("subgroup", "diabetes", "high ldl", "older", "boundary", "scope")):
        return "scope_or_subgroup_boundary"
    if any(token in combined for token in ("replace", "substitution", "comparator", "processed", "full fat")):
        return "comparator_context"
    if any(token in combined for token in ("ldl", "hdl", "biomarker", "ratio", "mean difference", "md =")):
        return "biomarker_calibration"
    if any(token in combined for token in ("hazard ratio", "relative risk", "risk", "incident")):
        return "risk_estimate"
    if any(token in combined for token in ("per day", "/day", "egg")):
        return "dose_boundary"
    return "decision_relevant_quantity"


def _dedupe_contract_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for row in rows:
        evidence_id = str(row.get("evidence_id") or "").strip()
        quantity = str(row.get("quantity_text") or "").strip()
        key = (evidence_id, _quantity_key(quantity))
        if not evidence_id or not quantity or key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result[:64]


def _quantity_key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9.%/-]+", " ", str(text or "").lower())).strip()


def _contract_id(evidence_id: str, quantity_text: str) -> str:
    key = _quantity_key(quantity_text)
    key = re.sub(r"[^a-z0-9]+", "_", key).strip("_")[:48]
    return f"{evidence_id}::{key}" if key else evidence_id


def _contract_rows(contracts: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(contracts, dict):
        return [row for row in _list(contracts.get("rows")) if isinstance(row, dict)]
    return [row for row in _list(contracts) if isinstance(row, dict)]


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}
