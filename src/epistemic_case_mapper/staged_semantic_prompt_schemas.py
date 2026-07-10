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
        "source_anchor_a": "short phrase from first evidence quote that supports the edge",
        "source_anchor_b": "short phrase from second evidence quote that supports the edge",
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
        {
            "input_hint": "Two outcome findings point in different directions on the same decision-relevant proposition.",
            "output": {
                "pair_id": "pair_003",
                "source_claim": "case_c004",
                "target_claim": "case_c005",
                "relation_type": "in_tension_with",
                "rationale": "case_c004 reports no meaningful difference on the target outcome, while case_c005 reports higher risk on the same outcome.",
                "relation_confidence": "high",
                "edge_basis": "source_explicit",
                "source_anchor_a": "no meaningful difference",
                "source_anchor_b": "higher risk",
                "why_decision_relevant": "The edge preserves the main evidential conflict instead of averaging it away.",
                "failure_condition": "The edge weakens if the outcomes, populations, or exposure definitions are not comparable.",
                "crux_candidates": ["Whether case_c004 and case_c005 are comparable is a crux for the decision read."],
                "similar_but_not_identical": [],
            },
        },
        {
            "input_hint": "A validity or method claim weakens confidence in a headline finding.",
            "output": {
                "pair_id": "pair_004",
                "source_claim": "case_c007",
                "target_claim": "case_c006",
                "relation_type": "challenges",
                "rationale": "case_c007 names a confounding or measurement problem that weakens the headline inference in case_c006.",
                "relation_confidence": "medium",
                "edge_basis": "source_inferred",
                "source_anchor_a": "unmeasured confounding",
                "source_anchor_b": "headline association",
                "why_decision_relevant": "The edge lowers how much the headline finding should drive the decision.",
                "failure_condition": "The edge weakens if the limitation was already handled by the target source's design or adjustment strategy.",
                "crux_candidates": ["Whether the limitation in case_c007 is serious enough would change how much to rely on case_c006."],
                "similar_but_not_identical": [],
            },
        },
        {
            "input_hint": "A scope claim names the population or condition where a finding applies.",
            "output": {
                "pair_id": "pair_005",
                "source_claim": "case_c009",
                "target_claim": "case_c008",
                "relation_type": "refines",
                "rationale": "case_c009 narrows case_c008 by naming the subgroup or condition where the finding is most applicable.",
                "relation_confidence": "medium",
                "edge_basis": "source_inferred",
                "source_anchor_a": "specific subgroup",
                "source_anchor_b": "broader finding",
                "why_decision_relevant": "The edge prevents applying the broad finding outside the population or condition where it is supported.",
                "failure_condition": "The edge weakens if the subgroup or condition is not relevant to the decision question.",
                "crux_candidates": [],
                "similar_but_not_identical": ["case_c009 is a boundary on case_c008, not a duplicate of it."],
            },
        },
        {
            "input_hint": "A subgroup or scope claim points in a materially different direction from a broad outcome finding.",
            "output": {
                "pair_id": "pair_006",
                "source_claim": "case_c012",
                "target_claim": "case_c013",
                "relation_type": "in_tension_with",
                "rationale": "case_c012 reports a subgroup exception that pulls against the broad neutral or favorable finding in case_c013.",
                "relation_confidence": "medium",
                "edge_basis": "source_inferred",
                "source_anchor_a": "subgroup exception",
                "source_anchor_b": "broad neutral finding",
                "why_decision_relevant": "The edge keeps the decision from treating the broad finding as equally applicable to the subgroup.",
                "failure_condition": "The edge weakens if the subgroup is not relevant to the decision or the direction does not actually differ.",
                "crux_candidates": ["Whether the subgroup exception applies would change the decision read."],
                "similar_but_not_identical": [],
            },
        },
        {
            "input_hint": "A mechanism or biomarker claim explains why an outcome finding might hold, but is not itself decisive.",
            "output": {
                "pair_id": "pair_007",
                "source_claim": "case_c010",
                "target_claim": "case_c011",
                "relation_type": "supports",
                "rationale": "case_c010 provides a plausible mechanism for the outcome pattern in case_c011, while the clinical outcome evidence remains the stronger anchor.",
                "relation_confidence": "medium",
                "edge_basis": "source_inferred",
                "source_anchor_a": "mechanism or biomarker change",
                "source_anchor_b": "outcome pattern",
                "why_decision_relevant": "The edge explains why the outcome finding might generalize, while keeping mechanism evidence separate from outcome evidence.",
                "failure_condition": "The edge weakens if the biomarker is not causally related to the outcome or moves in the wrong direction.",
                "crux_candidates": [],
                "similar_but_not_identical": [],
            },
        },
    ]
