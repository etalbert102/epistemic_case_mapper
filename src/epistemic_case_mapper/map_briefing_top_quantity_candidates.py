from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_packet_eligibility import (
    decision_relevance_assessment,
    question_overlap_count,
)


def build_top_quantity_anchor_candidates(
    groups: list[dict[str, Any]],
    *,
    offset: int,
    question_terms: list[str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in groups:
        quantities = _string_list(group.get("quantity_values"))
        if not quantities:
            continue
        claim = _short_text(str(group.get("claim", "")), 420)
        rows.append(
            _drop_empty(
                {
                    "pool_id": f"pool_{offset+len(rows)+1:04d}",
                    "candidate_card_id": "",
                    "claim_ids": _string_list(group.get("claim_ids"))[:8],
                    "quantity_ids": _string_list(group.get("quantity_ids"))[:8],
                    "source_ids": _string_list(group.get("source_ids"))[:8],
                    "source_labels": _string_list(group.get("source_labels"))[:8],
                    "claim": claim,
                    "decision_role": "quantitative_anchor",
                    "raw_roles": ["quantity_ledger.top_quantitative_anchors"],
                    "quantity_values": quantities[:8],
                    "decision_relevance_score": 10,
                    "quality": "top_quantitative_anchor",
                    "why_it_matters": "Top quantitative anchor from the quantity ledger.",
                    "directionality": "quantifies",
                    "source_grounded": bool(_string_list(group.get("source_ids")) or _string_list(group.get("source_labels"))),
                    "pretrim_kind": "quantity_ledger.top_quantitative_anchor",
                    "protected_candidate": True,
                    "question_overlap_count": question_overlap_count(claim, question_terms or []),
                    "decision_relevance_assessment": decision_relevance_assessment(
                        " ".join([claim, " ".join(quantities)]),
                        question_terms=question_terms or [],
                        decision_role="quantitative_anchor",
                    ),
                }
            )
        )
    return rows


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", [], {}, None)}


def _short_text(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."
