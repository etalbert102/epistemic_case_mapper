from __future__ import annotations

from typing import Any

from epistemic_case_mapper.main_memo_obligations import section_obligations_for_title


def section_main_memo_obligations(title: str, full_contract: dict[str, Any]) -> list[dict[str, Any]]:
    obligations = [row for row in full_contract.get("_main_memo_obligation_plan", []) if isinstance(row, dict)]
    category_allowed = section_obligations_for_title(title, obligations, limit=16)
    return category_allowed[:8]


def _compact_section_obligation(obligation: dict[str, Any], *, first_page_required: bool) -> dict[str, Any]:
    return {
        "obligation_id": obligation.get("obligation_id"),
        "category": obligation.get("category"),
        "priority": obligation.get("priority"),
        "statement": obligation.get("statement"),
        "search_terms": _string_list(obligation.get("search_terms"))[:6],
        "reason": obligation.get("reason"),
        "first_page_required": first_page_required,
        "source_ids": _string_list(obligation.get("source_ids"))[:4],
        "claim_ids": _string_list(obligation.get("claim_ids"))[:4],
        "relation_ids": _string_list(obligation.get("relation_ids"))[:4],
        "quantity_ids": _string_list(obligation.get("quantity_ids"))[:4],
        "eligibility": obligation.get("eligibility", {}) if isinstance(obligation.get("eligibility"), dict) else {},
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
