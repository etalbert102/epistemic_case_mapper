from __future__ import annotations

from typing import Any


def relation_prompt_schema(pair_ids: str, relation_types: str) -> dict[str, Any]:
    return {
        "pair_id": f"one of: {pair_ids}",
        "source_claim": "claim_id or null",
        "target_claim": "claim_id or null",
        "relation_type": f"one of: {relation_types}; or none",
        "rationale": "why this edge improves reasoning without overstating support, or why no edge is warranted",
        "relation_confidence": "low|medium|high",
        "edge_basis": "source_explicit|source_inferred|role_template|uncertain",
        "source_anchor_a": "short phrase from first excerpt that supports the edge",
        "source_anchor_b": "short phrase from second excerpt that supports the edge",
        "why_decision_relevant": "what this edge changes for the decision question",
        "failure_condition": "what would make this edge invalid or much weaker",
        "crux_candidates": ["crux text naming claim IDs"],
        "similar_but_not_identical": ["distinction text naming claim IDs"],
    }


def relation_batch_prompt_schema(pair_ids: str, relation_types: str) -> dict[str, Any]:
    return {"relations": [relation_prompt_schema(pair_ids, relation_types)]}


def relation_json_schema(batch: bool = False) -> dict[str, Any]:
    item = {
        "type": "object",
        "properties": {
            "pair_id": {"type": "string"},
            "source_claim": {"type": ["string", "null"]},
            "target_claim": {"type": ["string", "null"]},
            "relation_type": {"type": "string"},
            "rationale": {"type": "string"},
            "relation_confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "edge_basis": {"type": "string"},
            "source_anchor_a": {"type": "string"},
            "source_anchor_b": {"type": "string"},
            "why_decision_relevant": {"type": "string"},
            "failure_condition": {"type": "string"},
            "crux_candidates": {"type": "array", "items": {"type": "string"}},
            "similar_but_not_identical": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["pair_id", "source_claim", "target_claim", "relation_type", "rationale"],
    }
    if not batch:
        return item
    return {"type": "object", "properties": {"relations": {"type": "array", "items": item}}, "required": ["relations"]}


def relation_examples() -> list[dict[str, Any]]:
    return [
        {
            "input_hint": "One claim states a condition required for another claim to hold.",
            "output": {
                "pair_id": "pair_001",
                "source_claim": "case_c002",
                "target_claim": "case_c001",
                "relation_type": "depends_on",
                "rationale": "case_c001 only holds if the condition in case_c002 is satisfied.",
                "relation_confidence": "medium",
                "edge_basis": "source_inferred",
                "source_anchor_a": "condition named in the source",
                "source_anchor_b": "recommendation depends on that condition",
                "why_decision_relevant": "The edge turns a broad recommendation into a scoped one.",
                "failure_condition": "The condition is not required in the target setting.",
                "crux_candidates": ["case_c002 is a crux for case_c001."],
                "similar_but_not_identical": [],
            },
        },
        {
            "input_hint": "The pair has no defensible decision-relevant edge.",
            "output": {
                "pair_id": "pair_002",
                "source_claim": None,
                "target_claim": None,
                "relation_type": "none",
                "rationale": "The claims concern different parts of the source packet.",
                "relation_confidence": "low",
                "edge_basis": "uncertain",
                "source_anchor_a": "",
                "source_anchor_b": "",
                "why_decision_relevant": "",
                "failure_condition": "",
                "crux_candidates": [],
                "similar_but_not_identical": [],
            },
        },
    ]
