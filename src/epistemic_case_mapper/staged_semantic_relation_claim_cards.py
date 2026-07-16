from __future__ import annotations

import json
import re
from typing import Any


def relation_routing_context_lines(claim: dict[str, Any]) -> list[str]:
    role_reasons = claim.get("decision_edge_role_reasons")
    if not isinstance(role_reasons, list):
        role_reasons = [role_reasons] if role_reasons else []
    source_card = claim.get("whole_doc_source_card") if isinstance(claim.get("whole_doc_source_card"), dict) else {}
    claim_context = source_card.get("claim_context") if isinstance(source_card.get("claim_context"), dict) else {}
    fields = {
        "decision_edge_role": claim.get("decision_edge_role") or claim.get("map_relation_role"),
        "decision_edge_role_confidence": claim.get("decision_edge_role_confidence"),
        "decision_edge_role_source": claim.get("decision_edge_role_source"),
        "decision_edge_role_reasons": [
            _compact_text(str(reason), max_chars=140)
            for reason in role_reasons
            if str(reason).strip()
        ][:3],
        "decision_function": claim.get("decision_function"),
        "question_relevance": claim.get("question_relevance"),
        "decision_importance_level": claim.get("decision_importance_level"),
        "default_use": claim.get("default_use"),
        "source_local_context": _source_local_context(claim_context),
        "natural_bottom_line": _compact_text(str(source_card.get("natural_bottom_line") or ""), max_chars=160),
        "must_preserve_terms": [
            _compact_text(str(term), max_chars=80)
            for term in (source_card.get("must_preserve_terms") if isinstance(source_card.get("must_preserve_terms"), list) else [])
            if str(term).strip()
        ][:6],
    }
    visible = {key: value for key, value in fields.items() if value not in (None, "", [])}
    if not visible:
        return []
    return [f"- routing_context: {json.dumps(visible, ensure_ascii=False, sort_keys=True)}"]


def _source_local_context(context: dict[str, Any]) -> dict[str, str]:
    fields = (
        "population",
        "exposure_or_option",
        "outcome_or_endpoint",
        "evidence_design",
        "stated_dose_or_threshold",
        "stated_scope",
        "stated_limitations",
        "applicability_limits",
    )
    return {
        field: _compact_text(str(context.get(field) or ""), max_chars=160)
        for field in fields
        if str(context.get(field) or "").strip()
    }


def _compact_text(text: str, *, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip(" ,.;") + "..."
