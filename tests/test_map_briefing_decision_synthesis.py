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
from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_support_model import build_decision_support_model
from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_cruxes import build_decision_cruxes
from epistemic_case_mapper.pipeline.briefing.map_briefing_reader_polish import clean_reader_memo_text


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


def test_decision_support_normalizes_overlong_claims_before_synthesis() -> None:
    raw_claim = (
        "Overall, 521,120 participants were recruited from several sites and prospectively followed. "
        "Intakes of the exposure were assessed by a validated questionnaire. "
        "Whole exposure and related nutrient intakes were both positively associated with all-cause and cardiovascular mortality. "
        "Study limitations include observational design and residual confounding."
    )
    candidate_map = annotate_map_with_evidence_slots(
        {
            "claims": [
                {
                    "claim_id": "c001",
                    "claim": raw_claim,
                    "source_id": "cohort",
                    "role": "scope_limit",
                    "entailed_by_excerpt": "yes",
                },
                {
                    "claim_id": "c002",
                    "claim": "The associations were no longer significant after adjustment for a correlated dietary exposure.",
                    "source_id": "cohort",
                    "role": "crux",
                    "entailed_by_excerpt": "yes",
                },
                {
                    "claim_id": "c003",
                    "claim": "Population in other countries have increased outcome risk than the reference population.",
                    "source_id": "subgroup",
                    "role": "external_validity",
                    "entailed_by_excerpt": "yes",
                },
            ],
            "relations": [
                {
                    "relation_id": "r001",
                    "source_claim": "c001",
                    "target_claim": "c002",
                    "relation_type": "in_tension_with",
                    "rationale": "Claim A defines the specific population: Overall, 521,120 participants were recruited before the adjusted analysis weakens the broad association.",
                }
            ],
        }
    )

    model = build_decision_support_model(
        candidate_map=candidate_map,
        quality_report={"status": "usable_with_review", "score": 88, "issues": []},
        source_lookup={"cohort": "Cohort Study", "subgroup": "Subgroup Review"},
        erosion_audit={"items": []},
        question="Should the default advice treat the exposure as harmful?",
    )

    row_lookup = {row["claim_id"]: row for row in model["evidence_weighting_ledger"]["all_evidence"]}
    card_lookup = {card["claim_id"]: card for card in model["atomic_evidence_cards"]["cards"]}
    serialized_graph = json.dumps(model["graph_synthesis_packet"])
    serialized_synthesis = json.dumps(model["decision_synthesis_model"])

    assert "multi_finding_claim" in card_lookup["c001"]["noise_flags"]
    assert card_lookup["c001"]["raw_claim"] == raw_claim
    assert row_lookup["c001"]["claim"].startswith("Whole exposure")
    assert "participants were recruited" not in row_lookup["c001"]["claim"]
    assert "Whole exposure" in serialized_graph
    assert "participants were recruited" not in serialized_synthesis
    assert card_lookup["c003"]["appendix_only"] is True

    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 88, "issues": []},
        {"cohort": "Cohort Study", "subgroup": "Subgroup Review"},
        {"items": []},
        question="Should the default advice treat the exposure as harmful?",
    )
    prompt = build_map_briefing_prompt(
        candidate_map=candidate_map,
        quality_report={"status": "usable_with_review", "score": 88, "issues": []},
        question="Should the default advice treat the exposure as harmful?",
        source_lookup={"cohort": "Cohort Study", "subgroup": "Subgroup Review"},
        erosion_audit={"items": []},
        scaffold=scaffold,
    )
    assert "participants were recruited" not in prompt
    assert "Population in other countries have increased" not in prompt
    assert "raw_claim" not in prompt
    assert "Whole-memo JSON prompt retired." in prompt


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


def test_reader_polish_splits_heading_from_backslash_joined_body() -> None:
    cleaned = clean_reader_memo_text("### Map Quality and Gaps\\The map is usable but has known limits.")

    assert cleaned == "### Map Quality and Gaps\n\nThe map is usable but has known limits."


def test_reader_polish_translates_sufficiency_status_into_reader_facing_limit() -> None:
    rendered = """## Decision Brief

The bounded read is cautious.

**Confidence:** low
"""
    scaffold = {
        "confidence_cap": "low",
        "map_sufficiency_report": {"status": "usable_with_named_gaps"},
        "decision_synthesis_model": {"limits": []},
    }

    polished = polish_briefing_for_reader(rendered, scaffold)

    assert "map sufficiency status" not in polished.lower()
    assert "usable with named gaps" not in polished.lower()
    assert "named evidence gap" in polished
    assert "negative evidence" in polished


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


def test_graph_synthesis_does_not_promote_narrower_scope_representatives() -> None:
    candidate_map = {
        "claims": [
            _claim("c001", "The option helps the default adult population in the target decision.", "default", "conclusion_support"),
            _claim("c002", "The option showed a stronger effect only in a narrower high-risk subgroup.", "subgroup", "conclusion_support"),
            _claim("c003", "The subgroup finding is connected to several mechanism claims.", "mechanism", "crux"),
        ],
        "relations": [
            _relation("r001", "c002", "c001", "supports"),
            _relation("r002", "c003", "c002", "supports"),
        ],
    }
    default_row = _row("c001", "The option helps the default adult population in the target decision.", "medium", "cohort_or_observational")
    default_row["top_line_eligible"] = True
    default_row["appendix_only"] = False
    default_row["question_fit"] = {"status": "fits"}
    subgroup_row = _row("c002", "The option showed a stronger effect only in a narrower high-risk subgroup.", "high", "cohort_or_observational")
    subgroup_row["top_line_eligible"] = False
    subgroup_row["appendix_only"] = False
    subgroup_row["question_fit"] = {"status": "narrower_than_question"}
    mechanism_row = _row("c003", "The subgroup finding is connected to several mechanism claims.", "high", "mechanism_or_biomarker")
    mechanism_row["top_line_eligible"] = False
    mechanism_row["appendix_only"] = False
    mechanism_row["question_fit"] = {"status": "narrower_than_question"}
    scaffold = {
        "evidence_weighting_ledger": {"all_evidence": [default_row, subgroup_row, mechanism_row]},
        "decision_model": {"default_answer": {"classification": "conditional", "confidence_cap": "medium"}},
        "graph_synthesis_packet": build_graph_synthesis_packet(
            candidate_map,
            {"all_evidence": [default_row, subgroup_row, mechanism_row]},
            {"default": "Default Study", "subgroup": "Subgroup Study", "mechanism": "Mechanism Study"},
        ),
    }

    synthesis = build_decision_synthesis_model(scaffold)
    serialized = json.dumps(synthesis["evidence_lines"]).lower()

    assert "default adult population" in serialized
    assert "narrower high-risk subgroup" not in serialized


def test_decision_synthesis_builds_decision_changing_cruxes_from_graph_tensions() -> None:
    candidate_map = annotate_map_with_evidence_slots(
        {
            "claims": [
                _claim("c001", "The intervention improves hard outcome events in the default population.", "outcomes", "conclusion_support"),
                _claim("c002", "The intervention worsens a biomarker that may proxy long-term harm.", "biomarker", "crux"),
                _claim("c003", "A high-risk subgroup may respond differently than the default population.", "subgroup", "scope_limit"),
            ],
            "relations": [
                _relation("r001", "c002", "c001", "in_tension_with"),
                _relation("r002", "c003", "c001", "challenges"),
            ],
        }
    )
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 90, "issues": []},
        {"outcomes": "Outcome Study", "biomarker": "Biomarker Trial", "subgroup": "Subgroup Memo"},
        {"items": []},
        question="Should the intervention be recommended for the default population?",
    )

    cruxes = scaffold["decision_synthesis_model"]["cruxes"]

    assert len(cruxes) >= 2
    assert all("recommendation would change if" in row["would_change_if"].lower() for row in cruxes[:2])
    assert all(row.get("decision_effect") for row in cruxes[:2])
    assert any("biomarker" in row["crux"].lower() for row in cruxes)
    assert " versus " not in cruxes[0]["crux"].lower()
    assert len({row.get("crux_type") for row in cruxes[:2]}) == 2
    assert cruxes[0]["supporting_claim_ids"] != cruxes[0]["challenging_claim_ids"]


def test_decision_crux_builder_uses_generic_subgroup_concepts_and_valid_ids() -> None:
    scaffold = {
        "question": "Should the intervention be recommended for the default population?",
        "epistemic_config": {"profile_id": "general_decision_support"},
        "evidence_weighting_ledger": {
            "all_evidence": [
                {"claim_id": "c001", "claim": "The intervention improves hard outcomes in the default setting."},
                {"claim_id": "c002", "claim": "A high-risk operating group may respond differently."},
            ]
        },
        "graph_synthesis_packet": {
            "central_tensions": [
                {
                    "relation_id": "r001",
                    "left": {
                        "claim_id": "c002",
                        "claim": "A high-risk operating group may respond differently.",
                        "decision_concepts": ["custom_high_risk_group"],
                    },
                    "right": {
                        "claim_id": "c001",
                        "claim": "The intervention improves hard outcomes in the default setting.",
                        "decision_concepts": ["hard_outcome_endpoint"],
                    },
                }
            ],
            "bridge_claims": [
                {
                    "claim_id": "unknown",
                    "claim": "An untracked bridge claim should not keep an invalid ID.",
                    "decision_concepts": ["custom_high_risk_group"],
                }
            ],
        },
    }

    cruxes = build_decision_cruxes(scaffold=scaffold, central_tensions=[], scope_boundaries=[], exceptions=[])

    assert cruxes[0]["crux_type"] == "subgroup_exception"
    assert cruxes[0]["supporting_claim_ids"] == ["c002"]
    assert cruxes[0]["challenging_claim_ids"] == ["c001"]
    assert cruxes[0]["relation_ids"] == ["r001"]
    assert all("unknown" not in row.get("supporting_claim_ids", []) for row in cruxes)


def test_scope_boundary_crux_preserves_originating_claim_id() -> None:
    scaffold = {
        "question": "Should the intervention be recommended in the target setting?",
        "confidence_cap": "medium",
        "decision_model": {
            "default_answer": {
                "classification": "mixed_or_context_dependent",
                "plain_language_instruction": "Recommend only where the operating context matches the evidence.",
                "confidence_cap": "medium",
            },
            "decision_slots": {
                "setting_or_context": [
                    {
                        "value": "large public facilities with dedicated operations staff",
                        "claim": "The evidence comes from large public facilities with dedicated operations staff.",
                        "claim_id": "c010",
                        "source": "Facilities Study",
                    }
                ],
            },
        },
        "evidence_weighting_ledger": {
            "all_evidence": [
                {
                    "claim_id": "c010",
                    "claim": "The evidence comes from large public facilities with dedicated operations staff.",
                    "source": "Facilities Study",
                    "score": 80,
                    "weight": "high",
                    "evidence_family": "cohort_or_observational",
                    "decision_concepts": ["setting_or_context"],
                    "decision_slots": ["setting_or_context"],
                    "evidence_slots": ["setting_or_context"],
                }
            ]
        },
        "graph_synthesis_packet": {},
        "map_sufficiency_report": {},
        "quality_issues": [],
    }

    synthesis = build_decision_synthesis_model(scaffold)
    boundary = synthesis["scope_boundaries"][0]
    boundary_crux = next(row for row in synthesis["cruxes"] if row["crux_type"] == "scope_boundary")

    assert boundary["supporting_claim_ids"] == ["c010"]
    assert boundary_crux["supporting_claim_ids"] == ["c010"]


def test_map_briefing_prompt_points_to_section_first_artifacts() -> None:
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

    assert "Whole-memo JSON prompt retired." in prompt
    assert "section_synthesis_packets.json" in prompt
    assert "model_context_audit.json" in prompt
    assert "issue_clusters" not in prompt


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
