from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing import (
    annotate_map_with_evidence_slots,
    briefing_scaffold,
    build_decision_synthesis_model,
    polish_briefing_for_reader,
)


def test_generic_decision_synthesis_model_shapes_non_egg_brief() -> None:
    candidate_map = annotate_map_with_evidence_slots(
        {
            "claims": [
                {
                    "claim_id": "c001",
                    "claim": "Protected lanes reduced severe injury crashes by 30% on high-speed corridors.",
                    "source_id": "safety",
                    "role": "conclusion_support",
                    "entailed_by_excerpt": "yes",
                },
                {
                    "claim_id": "c002",
                    "claim": "Painted lanes cost less and can be installed faster than protected lanes.",
                    "source_id": "cost",
                    "role": "cost_feasibility",
                    "entailed_by_excerpt": "yes",
                },
                {
                    "claim_id": "c003",
                    "claim": "Protected lanes require maintenance capacity to remain usable after snow or debris.",
                    "source_id": "ops",
                    "role": "implementation_constraint",
                    "entailed_by_excerpt": "yes",
                },
            ],
            "relations": [
                {
                    "relation_id": "r001",
                    "source_claim": "c003",
                    "target_claim": "c001",
                    "relation_type": "depends_on",
                    "rationale": "Safety benefits depend on maintaining the protected lane after installation.",
                }
            ],
        }
    )
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 92, "issues": []},
        {"safety": "Safety Study", "cost": "Cost Memo", "ops": "Operations Memo"},
        {"items": []},
        question="Should the city prioritize protected bike lanes over painted lanes?",
    )

    synthesis = scaffold["decision_synthesis_model"]
    assert synthesis["schema_id"] == "decision_synthesis_model_v1"
    assert synthesis["evidence_lines"]
    assert synthesis["central_tensions"]
    assert synthesis["scope_boundaries"] or synthesis["recommendations"]
    assert synthesis["cruxes"]
    assert "relation marks" not in json.dumps(synthesis).lower()


def test_decision_synthesis_filters_fragmented_generic_slot_values() -> None:
    scaffold = {
        "question": "Should a city replace painted bike lanes with protected lanes?",
        "confidence_cap": "medium",
        "decision_model": {
            "default_answer": {
                "classification": "mixed_or_context_dependent",
                "plain_language_instruction": "Prefer protected lanes where operating capacity exists.",
                "confidence_cap": "medium",
            },
            "decision_slots": {
                "default_population": [
                    {"value": "commuters on high-speed corridors", "source": "Safety Study"},
                    {"value": "respectively. In site-specific analyses, copied table fragment", "source": "Table Note"},
                ],
                "endpoint_type": [
                    {"value": "risk", "source": "Fragment"},
                    {"value": "severe injury crashes", "source": "Safety Study"},
                ],
                "high_risk_subgroup": [
                    {"value": "people with limited snow-clearance capacity", "source": "Ops Memo"},
                    {"value": "Protected lanes significantly increase maintenance workload", "source": "Ops Memo"},
                ],
            },
            "practical_recommendations": [
                "Use protected lanes on high-speed corridors.",
                "Name this subgroup separately: Protected lanes significantly increase maintenance workload.",
            ],
        },
        "evidence_weighting_ledger": {
            "all_evidence": [
                {
                    "claim": "Protected lanes reduced severe injury crashes by 30% on high-speed corridors.",
                    "claim_id": "c1",
                    "source": "Safety Study",
                    "score": 100,
                    "weight": "high",
                    "evidence_family": "cohort_or_observational",
                    "decision_concepts": ["hard_outcome_endpoint"],
                    "decision_slots": [],
                    "evidence_slots": ["outcome_or_endpoint"],
                },
                {
                    "claim": "CVD = cardiovascular disease; CHD = coronary heart disease; CI = confidence interval.",
                    "claim_id": "glossary",
                    "source": "Glossary",
                    "score": 99,
                    "weight": "medium",
                    "evidence_family": "general_evidence",
                    "decision_concepts": [],
                    "decision_slots": [],
                    "evidence_slots": [],
                },
            ]
        },
    }

    synthesis = build_decision_synthesis_model(scaffold)
    serialized = json.dumps(synthesis).lower()

    assert "respectively" not in serialized
    assert "copied table fragment" not in serialized
    assert '"current_read": "risk"' not in serialized
    assert "cardiovascular disease; chd" not in serialized
    assert "name this subgroup separately: protected lanes" not in serialized
    assert "people with limited snow-clearance capacity" in serialized
    assert "severe injury crashes" in serialized


def test_reader_polish_cleans_relation_artifacts_in_rendered_crux_table() -> None:
    rendered = """## Decision Brief

Prefer protected lanes where feasible.

**Confidence:** medium

## What Could Change the Decision

| Crux | Current read | Would change if |
|---|---|---|
| Whether the stated concern changes the interpretation | This challenges relation marks a condition that can change the interpretation of the evidence. | New evidence showed that this concern is false. |
"""
    scaffold = {
        "confidence_cap": "medium",
        "decision_synthesis_model": {
            "cruxes": [
                {
                    "crux": "Maintenance capacity",
                    "current_read": "Protected lanes need reliable maintenance to preserve benefits.",
                    "would_change_if": "Maintenance constraints were absent or immaterial.",
                }
            ],
            "evidence_lines": [],
            "limits": [],
        },
    }

    polished = polish_briefing_for_reader(rendered, scaffold)

    assert "Whether the stated concern changes the interpretation" in polished
    assert "relation marks" not in polished
