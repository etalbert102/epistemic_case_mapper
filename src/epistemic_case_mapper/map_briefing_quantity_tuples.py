from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    norm as _norm,
    short_text as _short_text,
    string_list as _string_list,
)


def quantity_tuples(cluster: dict[str, Any], quantities: list[str]) -> list[dict[str, str]]:
    context = _quantity_context(cluster)
    if not context:
        return []
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    patterns = [
        re.compile(
            r"(?P<label>.{0,140}?)(?P<estimate>\b(?:adjusted\s+)?(?:pooled\s+)?(?:hazard ratio|relative risk|HR|RR|OR)\s*(?:=|,)?\s*\d+(?:\.\d+)?)\s*(?:\(|,)?\s*(?P<interval>95\s*%?\s*(?:confidence interval|CI)[\s,:]*(?:\[)?[-]?\d+(?:\.\d+)?\s*(?:to|[-])\s*[-]?\d+(?:\.\d+)?)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?P<label>.{0,140}?)(?P<estimate>\b\d+(?:\.\d+)?)\s*\(\s*(?P<interval>95\s*%?\s*(?:confidence interval|CI)[\s,:]*[-]?\d+(?:\.\d+)?\s*(?:to|[-])\s*[-]?\d+(?:\.\d+)?)\s*\)",
            re.IGNORECASE,
        ),
    ]
    for pattern in patterns:
        for match in pattern.finditer(context.replace("−", "-").replace("–", "-")):
            estimate = clean_quantity(match.group("estimate"))
            interval = clean_quantity(match.group("interval"))
            if not estimate or not interval:
                continue
            key = (_norm(estimate), _norm(interval))
            if key in seen:
                continue
            seen.add(key)
            label = _quantity_tuple_label(match.group("label"))
            rows.append(
                {
                    "tuple_id": f"qt{len(rows)+1:03d}",
                    "label": label or "source-local estimate",
                    "estimate": estimate,
                    "interval": interval,
                    "source_text": _short_text(match.group(0), 280),
                    "binding_rule": "estimate_and_interval_adjacent_in_source_excerpt",
                }
            )
    if not rows:
        return []
    requested = {_norm(quantity) for quantity in quantities}
    if not requested:
        return rows[:12]
    matching = [
        row
        for row in rows
        if _norm(row["estimate"]) in requested or _norm(row["interval"]) in requested
    ]
    return (matching or rows)[:12]


def tuple_for_quantity(quantity: str, tuples: list[dict[str, str]]) -> dict[str, str]:
    q = _norm(clean_quantity(quantity))
    for row in tuples:
        if q and q in {_norm(row.get("estimate", "")), _norm(row.get("interval", ""))}:
            return row
    return {}


def unsafe_quantity_pairings(
    cluster: dict[str, Any],
    quantities: list[dict[str, str]],
    quantity_tuples: list[dict[str, str]],
) -> list[dict[str, Any]]:
    paired = {
        _norm(value)
        for row in quantity_tuples
        for value in (row.get("estimate"), row.get("interval"))
        if value
    }
    warnings = []
    for quantity in quantities:
        value = str(quantity.get("value") or "")
        if not is_effect_or_interval(value):
            continue
        if _norm(value) in paired:
            continue
        warnings.append(
            {
                "cluster_id": cluster.get("cluster_id"),
                "quantity": value,
                "warning": "quantity_not_locally_paired_in_source_excerpt",
                "instruction": "Do not combine this quantity with another estimate or interval in prose unless the source-local tuple is explicit.",
            }
        )
    if len(quantity_tuples) >= 2 and any(is_effect_or_interval(str(row.get("value") or "")) for row in quantities):
        warnings.append(
            {
                "cluster_id": cluster.get("cluster_id"),
                "warning": "multiple_source_local_quantity_tuples",
                "instruction": "Use tuple labels or describe the result as multiple reported estimates rather than selecting an arbitrary estimate/interval pair.",
            }
        )
    return warnings[:8]


def is_effect_or_interval(quantity: str) -> bool:
    text = str(quantity or "").lower()
    return bool(re.search(r"\b(hr|rr|or)\b|hazard ratio|relative risk|confidence interval|\bci\b", text))


def clean_quantity(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip(" ,.;()[]")
    cleaned = cleaned.replace("confidence interval", "CI")
    cleaned = re.sub(r"95\s*%?\s*CI", "95% CI", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("−", "-").replace("–", "-")
    return cleaned


def _quantity_context(cluster: dict[str, Any]) -> str:
    return " ".join(
        text
        for text in (
            str(cluster.get("source_excerpt") or ""),
            str(cluster.get("representative_claim") or ""),
        )
        if text
    )


def _quantity_tuple_label(label: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(label or "")).strip(" ;,.:")
    if not cleaned:
        return ""
    fragments = re.split(r"(?:\.|;|\brespectively\b|\bwere\b|\bwas\b)", cleaned)
    candidate = fragments[-1].strip(" ;,.:") if fragments else cleaned
    return _short_text(candidate or cleaned, 120)
