from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.config_profiles import infer_profile_id_from_text, profile_vocabulary
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
    vocabulary = _quantity_vocabulary(packet)
    for item in _list(_dict(packet).get("evidence_items")):
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("item_id") or "").strip()
        if not evidence_id or not _item_contract_eligible(item):
            continue
        candidates = [
            *_quantity_rows(item),
            *_numeric_must_preserve_rows(item, vocabulary=vocabulary),
        ]
        for candidate in candidates:
            if not _quantity_contract_eligible(candidate, item, vocabulary=vocabulary):
                continue
            rows.append(_contract_row(item, candidate, vocabulary=vocabulary))
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
        if row.get("required_if_claim_used") is True and not _related_claim_used(memo, row):
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


def _related_claim_used(memo: str, row: dict[str, Any]) -> bool:
    claim = str(row.get("claim") or "").strip()
    if not claim:
        return True
    memo_terms = set(_content_terms(str(memo or "")))
    claim_terms = _content_terms(claim)
    if not claim_terms:
        return True
    distinctive_terms = [
        term
        for term in claim_terms
        if term not in _GENERIC_CLAIM_TERMS and not re.fullmatch(r"\d+(?:\.\d+)?", term)
    ]
    if not distinctive_terms:
        distinctive_terms = claim_terms
    matched = [term for term in distinctive_terms if term in memo_terms]
    threshold = min(5, max(2, (len(distinctive_terms) + 2) // 3))
    return len(matched) >= threshold


def _content_terms(text: str) -> list[str]:
    terms = [
        term
        for term in re.findall(r"[a-z][a-z0-9-]{3,}", str(text or "").lower())
        if term not in _GENERIC_CLAIM_TERMS
    ]
    return _dedupe(terms)


def compact_priority_quantity_contracts_for_prompt(rows: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    compact = []
    for row in _prioritized_contract_rows(rows)[:limit]:
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


def _prioritized_contract_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped_count: dict[tuple[str, str], int] = {}
    selected = []
    for row in sorted([row for row in rows if isinstance(row, dict)], key=_contract_prompt_priority):
        key = (str(row.get("evidence_id") or ""), str(row.get("decision_role") or ""))
        grouped_count[key] = grouped_count.get(key, 0) + 1
        if grouped_count[key] > 3:
            continue
        selected.append(row)
    return selected


def _contract_prompt_priority(row: dict[str, Any]) -> tuple[int, int, str]:
    role = str(row.get("decision_role") or "")
    role_rank = {
        "scope_or_subgroup_boundary": 0,
        "comparator_context": 1,
        "risk_estimate": 2,
        "dose_boundary": 3,
        "biomarker_calibration": 4,
    }.get(role, 5)
    text = str(row.get("quantity_text") or "").lower()
    detail_rank = 0
    if "confidence interval" in text or "95% ci" in text or " ci:" in text:
        detail_rank = 1
    if re.fullmatch(r"(?:mean difference of\s+)?\d+(?:\.\d+)?", text.strip()):
        detail_rank = 2
    return (role_rank, detail_rank, str(row.get("contract_id") or row.get("quantity_text") or ""))


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


def _numeric_must_preserve_rows(item: dict[str, Any], *, vocabulary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    terms = _selected_numeric_must_preserve_terms(item, vocabulary=vocabulary)
    for term in terms:
        if not _term_has_decision_quantity(term, vocabulary=vocabulary):
            continue
        rows.append(
            _drop_empty(
                {
                    "quantity_text": term,
                    "decision_role": _decision_role_from_text(term, item, vocabulary=vocabulary),
                    "memo_inclusion": "must_use" if _item_required(item) else "supporting_context",
                }
            )
        )
    return rows


def _selected_numeric_must_preserve_terms(item: dict[str, Any], *, vocabulary: dict[str, Any]) -> list[str]:
    terms = _string_list(item.get("must_preserve_terms"))
    anchor_numbers = _analyst_quantity_numbers(item)
    if not anchor_numbers:
        return terms
    groups: list[tuple[list[str], set[str]]] = []
    current_group: list[str] = []
    current_group_numbers: set[str] = set()
    for term in terms:
        if _term_has_decision_quantity(term, vocabulary=vocabulary):
            current_group.append(term)
            current_group_numbers.update(_numbers(term))
            continue
        if current_group:
            groups.append((current_group, current_group_numbers))
            current_group = []
            current_group_numbers = set()
    if current_group:
        groups.append((current_group, current_group_numbers))
    selected = []
    for group, numbers in groups:
        if numbers.intersection(anchor_numbers):
            selected.extend(group)
        elif len(groups) == 1 and any(_looks_like_interval(term) for term in group):
            selected.extend(group)
    return selected


def _analyst_quantity_numbers(item: dict[str, Any]) -> set[str]:
    numbers: set[str] = set()
    for quantity in _list(item.get("quantities")):
        if not isinstance(quantity, dict):
            continue
        if quantity.get("must_retain") is True or _dict(quantity.get("analyst_quantity_relevance")):
            for value in (
                quantity.get("value"),
                quantity.get("interpretation"),
                quantity.get("retention_phrase"),
                _dict(quantity.get("analyst_quantity_relevance")).get("retention_phrase"),
            ):
                numbers.update(_numbers(str(value or "")))
    return numbers


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


def _contract_row(item: dict[str, Any], candidate: dict[str, Any], *, vocabulary: dict[str, Any]) -> dict[str, Any]:
    evidence_id = str(item.get("item_id") or "").strip()
    quantity_text = str(candidate.get("quantity_text") or "").strip()
    claim = str(item.get("reader_claim") or item.get("natural_bottom_line") or item.get("claim") or "").strip()
    candidate_role = str(candidate.get("decision_role") or "").strip()
    decision_role = candidate_role if candidate_role and candidate_role not in {"statistical_detail", "decision_anchor"} else _decision_role_from_text(quantity_text, item, vocabulary=vocabulary)
    return _drop_empty(
        {
            "contract_id": _contract_id(evidence_id, quantity_text),
            "evidence_id": evidence_id,
            "quantity_text": quantity_text,
            "decision_role": decision_role,
            "rationale": candidate.get("rationale"),
            "source_ids": _dedupe([*_string_list(candidate.get("source_ids")), *_string_list(item.get("source_ids"))]),
            "source_labels": item.get("source_labels") or ([item.get("source_label")] if item.get("source_label") else None),
            "claim": _short_text(claim, 360),
            "required_if_claim_used": True,
            "contract_level": "required_if_related_claim_used",
        }
    )


def _quantity_contract_eligible(candidate: dict[str, Any], item: dict[str, Any], *, vocabulary: dict[str, Any]) -> bool:
    text = str(candidate.get("quantity_text") or "").strip()
    if not text or not _term_has_decision_quantity(text, vocabulary=vocabulary):
        return False
    if _looks_like_background_context(item):
        return _high_priority_quantity_text(text, vocabulary=vocabulary)
    if candidate.get("must_retain") is True:
        return True
    inclusion = str(candidate.get("memo_inclusion") or "").strip().lower()
    if inclusion in {"must_use", "yes"}:
        return True
    return _high_priority_quantity_text(text, vocabulary=vocabulary) and _item_required(item)


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


def _term_has_decision_quantity(text: str, *, vocabulary: dict[str, Any]) -> bool:
    lowered = str(text or "").lower()
    if not re.search(r"\d", lowered):
        return False
    if re.fullmatch(r"(?:19|20)\d{2}(?:\s*[–-]\s*(?:19|20)\d{2})?", lowered.strip()):
        return False
    markers = _string_list(vocabulary.get("quantity_decision_markers"))
    return _high_priority_quantity_text(lowered, vocabulary=vocabulary) or _has_marker(lowered, markers)


def _high_priority_quantity_text(text: str, *, vocabulary: dict[str, Any] | None = None) -> bool:
    lowered = str(text or "").lower()
    markers = [
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
        *_string_list(_dict(vocabulary).get("quantity_decision_markers")),
    ]
    return _has_marker(lowered, markers)


def _looks_like_interval(text: str) -> bool:
    lowered = str(text or "").lower()
    return "confidence interval" in lowered or "95% ci" in lowered or " ci:" in lowered


def _decision_role_from_text(text: str, item: dict[str, Any], *, vocabulary: dict[str, Any]) -> str:
    combined = " ".join([str(text or ""), str(item.get("reader_claim") or ""), str(item.get("role") or ""), str(item.get("memo_function") or "")]).lower()
    role_markers = _dict(vocabulary.get("quantity_role_markers"))
    for role in [
        "scope_or_subgroup_boundary",
        "comparator_context",
        "risk_estimate",
        "biomarker_calibration",
        "dose_boundary",
    ]:
        if _has_marker(combined, _string_list(role_markers.get(role))):
            return role
    return "decision_relevant_quantity"


def _quantity_vocabulary(packet: dict[str, Any]) -> dict[str, Any]:
    profile_id = str(_dict(packet).get("profile_id") or _dict(_dict(packet).get("config_profile")).get("profile_id") or "").strip()
    if not profile_id:
        profile_id = infer_profile_id_from_text(_quantity_profile_detection_text(packet))
    return profile_vocabulary(profile_id)


def _quantity_profile_detection_text(packet: dict[str, Any]) -> str:
    parts = [str(_dict(packet).get("decision_question") or "")]
    for source in _list(_dict(packet).get("source_trail")):
        if isinstance(source, dict):
            parts.extend([str(source.get("source_label") or ""), str(source.get("citation_label") or "")])
    for item in _list(_dict(packet).get("evidence_items"))[:24]:
        if isinstance(item, dict):
            parts.extend([str(item.get("reader_claim") or ""), str(item.get("natural_bottom_line") or "")])
    return "\n".join(part for part in parts if part)


def _has_marker(text: str, markers: list[str]) -> bool:
    lowered = str(text or "").lower()
    for marker in markers:
        normalized = str(marker or "").strip().lower()
        if not normalized:
            continue
        if re.search(r"[a-z0-9]$", normalized) and re.search(r"^[a-z0-9]", normalized):
            if re.search(rf"\b{re.escape(normalized)}\b", lowered):
                return True
        elif normalized in lowered:
            return True
    return False


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


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", str(text or "")))


def _contract_id(evidence_id: str, quantity_text: str) -> str:
    key = _quantity_key(quantity_text)
    key = re.sub(r"[^a-z0-9]+", "_", key).strip("_")[:48]
    return f"{evidence_id}::{key}" if key else evidence_id


def _contract_rows(contracts: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(contracts, dict):
        return [row for row in _list(contracts.get("rows")) if isinstance(row, dict)]
    return [row for row in _list(contracts) if isinstance(row, dict)]


_GENERIC_CLAIM_TERMS = {
    "about",
    "against",
    "answer",
    "associated",
    "association",
    "claim",
    "claims",
    "conclusion",
    "decision",
    "evidence",
    "identifies",
    "increased",
    "levels",
    "memo",
    "rather",
    "relevant",
    "significant",
    "source",
    "specific",
    "supports",
    "tension",
    "that",
    "this",
    "with",
}


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}
