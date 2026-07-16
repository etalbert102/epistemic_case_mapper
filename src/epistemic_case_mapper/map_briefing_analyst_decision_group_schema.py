from __future__ import annotations

from typing import Any


DECISION_GROUP_FIELDS = {
    "group_id",
    "proposition",
    "memo_role",
    "source_memo_role",
    "importance_rank",
    "covered_evidence_item_ids",
    "answer_relation",
    "target_answer_option",
    "effect_on_final_answer",
    "tension_type",
    "rationale",
    "evidence_strength",
    "answer_impact",
    "uncertainty_type",
    "applicability_limits",
    "conflict_note",
}


def normalize_decision_group_aliases(group: dict[str, Any]) -> None:
    if not group.get("answer_relation"):
        for alias in ("answer_relation_type", "relation_to_answer", "answer_relation_to_default"):
            if group.get(alias):
                group["answer_relation"] = group.get(alias)
                break
    if not group.get("target_answer_option"):
        for alias in ("target_answer_precedence", "target_answer_con_option", "target_answer", "answer_option"):
            if group.get(alias):
                group["target_answer_option"] = group.get(alias)
                break
    if not group.get("memo_role"):
        for alias in ("memo_relevance", "role", "evidence_role"):
            if group.get(alias):
                group["memo_role"] = group.get(alias)
                break
    for key in list(group.keys()):
        if key not in DECISION_GROUP_FIELDS:
            group.pop(key, None)


def schema_safe_decision_group(group: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(group)
    normalize_decision_group_aliases(normalized)
    return normalized
