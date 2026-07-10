from __future__ import annotations

import json
import re
from typing import Any


def relation_routing_context_lines(claim: dict[str, Any]) -> list[str]:
    role_reasons = claim.get("decision_edge_role_reasons")
    if not isinstance(role_reasons, list):
        role_reasons = [role_reasons] if role_reasons else []
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
    }
    visible = {key: value for key, value in fields.items() if value not in (None, "", [])}
    if not visible:
        return []
    return [f"- routing_context: {json.dumps(visible, ensure_ascii=False, sort_keys=True)}"]


def _compact_text(text: str, *, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip(" ,.;") + "..."
