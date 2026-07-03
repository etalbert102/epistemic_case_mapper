from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing import (
    annotate_map_with_evidence_slots,
    briefing_scaffold,
    build_graph_synthesis_packet,
    build_decision_synthesis_model,
    build_map_briefing_prompt,
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
    assert scaffold["graph_synthesis_packet"]["schema_id"] == "graph_synthesis_packet_v1"
    assert scaffold["decision_synthesis_model"]["graph_summary"]["issue_cluster_count"] >= 1


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


def test_graph_synthesis_packet_extracts_generic_network_structure() -> None:
    candidate_map = {
        "claims": [
            _claim("c001", "Protected lanes reduce severe crashes on high-speed corridors.", "safety", "conclusion_support"),
            _claim("c002", "Painted lanes can be installed faster and at lower upfront cost.", "cost", "cost_feasibility"),
            _claim("c003", "Protected lanes need reliable maintenance after snow or debris.", "ops", "implementation_constraint"),
            _claim("c004", "Crash reduction benefits depend on keeping the protected lane usable.", "ops", "scope_limit"),
        ],
        "relations": [
            _relation("r001", "c004", "c001", "depends_on"),
            _relation("r002", "c002", "c001", "in_tension_with"),
            _relation("r003", "c003", "c004", "supports"),
        ],
    }
    evidence_ledger = {
        "all_evidence": [
            _row("c001", "Protected lanes reduce severe crashes on high-speed corridors.", "high", "cohort_or_observational"),
            _row("c002", "Painted lanes can be installed faster and at lower upfront cost.", "medium", "implementation"),
            _row("c003", "Protected lanes need reliable maintenance after snow or debris.", "medium", "implementation"),
            _row("c004", "Crash reduction benefits depend on keeping the protected lane usable.", "high", "method_or_validity"),
        ]
    }

    packet = build_graph_synthesis_packet(candidate_map, evidence_ledger, {"safety": "Safety Study", "cost": "Cost Memo", "ops": "Ops Memo"})
    serialized = json.dumps(packet).lower()

    assert packet["schema_id"] == "graph_synthesis_packet_v1"
    assert packet["graph_summary"]["tension_edge_count"] == 1
    assert packet["issue_clusters"]
    assert packet["central_tensions"]
    assert packet["load_bearing_claims"]
    assert packet["central_tensions"][0]["left"]["claim_id"].startswith("c")
    assert packet["central_tensions"][0]["relation_id"].startswith("r")
    assert "protected lanes" in serialized
    assert "relation marks" not in serialized


def test_map_briefing_prompt_uses_graph_synthesis_packet() -> None:
    candidate_map = annotate_map_with_evidence_slots(
        {
            "claims": [
                _claim("c001", "Protected lanes reduce severe crashes on high-speed corridors.", "safety", "conclusion_support"),
                _claim("c002", "Painted lanes can be installed faster and at lower upfront cost.", "cost", "cost_feasibility"),
            ],
            "relations": [_relation("r001", "c002", "c001", "in_tension_with")],
        }
    )
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 90, "issues": []},
        {"safety": "Safety Study", "cost": "Cost Memo"},
        {"items": []},
        question="Should the city prioritize protected bike lanes over painted lanes?",
    )

    prompt = build_map_briefing_prompt(
        candidate_map=candidate_map,
        quality_report={"status": "usable_with_review", "score": 90, "issues": []},
        question="Should the city prioritize protected bike lanes over painted lanes?",
        source_lookup={"safety": "Safety Study", "cost": "Cost Memo"},
        erosion_audit={"items": []},
        scaffold=scaffold,
    )

    assert "graph_synthesis_packet" in prompt
    assert "issue_clusters" in prompt
    assert "load-bearing claims" in prompt


def _claim(claim_id: str, claim: str, source_id: str, role: str) -> dict[str, str]:
    return {
        "claim_id": claim_id,
        "claim": claim,
        "source_id": source_id,
        "role": role,
        "entailed_by_excerpt": "yes",
    }


def _relation(relation_id: str, source_claim: str, target_claim: str, relation_type: str) -> dict[str, str]:
    return {
        "relation_id": relation_id,
        "source_claim": source_claim,
        "target_claim": target_claim,
        "relation_type": relation_type,
        "rationale": "The claims affect the same decision under different conditions.",
    }


def _row(claim_id: str, claim: str, weight: str, evidence_family: str) -> dict[str, object]:
    return {
        "claim_id": claim_id,
        "claim": claim,
        "weight": weight,
        "score": 80 if weight == "high" else 50,
        "source": "Generic Source",
        "section": "main_support",
        "evidence_family": evidence_family,
        "decision_concepts": ["implementation_condition"] if evidence_family == "implementation" else ["hard_outcome_endpoint"],
        "decision_slots": [],
        "evidence_slots": [],
    }
