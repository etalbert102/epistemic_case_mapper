from __future__ import annotations

import json
import sys
from pathlib import Path

from epistemic_case_mapper import cli
from epistemic_case_mapper.map_briefing import (
    adaptive_briefing_claim_budget,
    append_evidence_by_decision_lever,
    append_map_coverage_snapshot,
    annotate_map_with_evidence_slots,
    briefing_scaffold,
    build_crux_contract,
    build_briefing_contract,
    build_map_briefing_prompt,
    build_decision_model,
    build_decision_slots,
    build_concept_evidence_packets,
    build_decision_memo_slots,
    build_evidence_compression_table,
    build_evidence_slot_ledger,
    build_evidence_weighting_ledger,
    build_map_sufficiency_report,
    build_option_comparison,
    build_reader_memo_rewrite_contract,
    build_proposition_clusters,
    build_curated_evidence_packets,
    calibrate_confidence,
    briefing_reader_polish_report,
    clean_reader_briefing_text,
    compose_final_reader_memo_package,
    expand_reader_map_references,
    model_parse_diagnostics,
    partition_map_evidence,
    polish_briefing_for_reader,
    prioritize_map_for_briefing,
    repair_briefing_payload,
    repair_reader_memo_rewrite_candidate,
    reader_memo_rewrite_issues,
    run_map_briefing,
    validate_briefing_against_scaffold,
    _rewrite_mentions_anchor_row,
)
from epistemic_case_mapper.staged_semantic_pipeline import CLAIM_EXTRACTION_PROMPT_VERSION, RELATION_PROMPT_VERSION


def test_decision_memo_slots_force_core_evidence_into_memo() -> None:
    scaffold = {
        "confidence_cap": "medium",
        "quality_status": "usable_with_review",
        "map_sufficiency_report": {"status": "sufficient_for_scaffolded_briefing"},
        "concept_evidence_packets": {
            "packets": [
                {
                    "concept": "default_population",
                    "rows": [
                        {
                            "claim": "The study included generally healthy adults without cardiovascular disease at baseline.",
                            "source": "demo_sources_population_2020_full",
                            "section": "scope_limits",
                            "weight": "high",
                            "score": 8,
                        }
                    ],
                },
                {
                    "concept": "dose_or_threshold",
                    "rows": [
                        {
                            "claim": "Moderate intake up to one egg per day was the mapped dose boundary.",
                            "source": "demo_sources_dose_2020_full",
                            "section": "main_support",
                            "weight": "high",
                            "score": 8,
                        }
                    ],
                },
                {
                    "concept": "hard_outcome_endpoint",
                    "rows": [
                        {
                            "claim": "A cohort study found no increase in cardiovascular mortality at moderate intake.",
                            "source": "demo_sources_outcome_2020_full",
                            "section": "main_support",
                            "weight": "high",
                            "score": 8,
                        },
                        {
                            "claim": "A pooled cohort found higher all-cause mortality at higher egg intake.",
                            "source": "demo_sources_counter_2019_full",
                            "section": "conflicting_evidence",
                            "weight": "high",
                            "score": 8,
                        },
                    ],
                },
                {
                    "concept": "mechanism_ldl_apob",
                    "rows": [
                        {
                            "claim": "LDL and ApoB biomarkers determine whether the neutral outcome read is biologically plausible.",
                            "source": "demo_sources_lipid_2025_full",
                            "section": "method_limits",
                            "weight": "high",
                            "score": 8,
                        }
                    ],
                },
                {
                    "concept": "substitution_or_comparator",
                    "rows": [
                        {
                            "claim": "Replacing whole eggs with egg whites or other protein sources can change practical dietary advice.",
                            "source": "demo_sources_substitution_2021_full",
                            "section": "main_support",
                            "weight": "high",
                            "score": 8,
                        }
                    ],
                },
                {
                    "concept": "subgroup_diabetes_or_metabolic_risk",
                    "rows": [
                        {
                            "claim": "People with type 2 diabetes may not inherit the default-population answer.",
                            "source": "demo_sources_diabetes_2020_full",
                            "section": "scope_limits",
                            "weight": "high",
                            "score": 8,
                        }
                    ],
                },
            ]
        },
    }
    rendered = "## Decision Brief\n\nNeutral at moderate intake.\n\n**Confidence:** medium\n"

    package = compose_final_reader_memo_package(rendered, scaffold)
    slots = build_decision_memo_slots(package["scaffold"], rendered=rendered)
    memo = package["memo"]

    assert slots["coverage"]["missing_required_slots"] == []
    assert "LDL and ApoB" in memo
    assert "Replacing whole eggs" in memo
    assert "type 2 diabetes" in memo
    assert "higher all-cause mortality" in memo


def test_slot_extraction_recognizes_population_and_comparator_without_verbs() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The study included participants who were free of cardiovascular disease, type 2 diabetes, and cancer at baseline.",
                "source_id": "cohort",
                "role": "scope_limit",
            },
            {
                "claim_id": "c002",
                "claim": "Egg whites and plant protein are relevant replacement options for interpreting practical dietary advice.",
                "source_id": "diet",
                "role": "implementation_constraint",
            },
        ],
        "relations": [],
    }
    source_lookup = {"cohort": "Cohort", "diet": "Diet"}
    partition = partition_map_evidence(candidate_map, source_lookup)
    ledger = build_evidence_weighting_ledger(
        candidate_map,
        partition,
        {"status": "usable_with_review", "score": 90, "issues": []},
        source_lookup,
    )
    slots = build_decision_slots(ledger)

    assert slots["default_population"]
    assert slots["substitution_or_comparator"]


def test_decision_slots_keep_narrower_subgroups_out_of_default_slots() -> None:
    ledger = {
        "all_evidence": [
            {
                "claim_id": "c001",
                "claim": "The effect was stronger in people with a high-risk condition.",
                "source": "Subgroup Study",
                "weight": "high",
                "score": 9,
                "appendix_only": False,
                "top_line_eligible": False,
                "question_fit": {"status": "narrower_than_question"},
                "decision_slots": [
                    "default_population",
                    "high_risk_subgroup",
                    "substitution_or_comparator",
                    "safety_or_risk",
                ],
            }
        ]
    }

    slots = build_decision_slots(ledger)

    assert slots["default_population"] == []
    assert slots["substitution_or_comparator"] == []
    assert slots["high_risk_subgroup"]
    assert slots["safety_or_risk"]


def test_evidence_weighting_marks_noise_and_weak_question_alignment_not_top_line() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "Moderate egg consumption was not associated with higher cardiovascular disease risk in generally healthy adults.",
                "source_id": "cohort",
                "role": "conclusion_support",
                "entailed_by_excerpt": "yes",
            },
            {
                "claim_id": "c002",
                "claim": "Abbreviations: BMI, body mass index; CI, confidence interval; HR, hazard ratio; RR, relative risk.",
                "source_id": "cohort",
                "role": "scope_limit",
                "entailed_by_excerpt": "yes",
            },
            {
                "claim_id": "c003",
                "claim": "Eating too many amino acids may increase cardiovascular disease and death risk.",
                "source_id": "guidance",
                "role": "scope_limit",
                "entailed_by_excerpt": "yes",
            },
            {
                "claim_id": "c004",
                "claim": "This link is provided for convenience only and is not an endorsement of either the linked-to entity or any product or service.",
                "source_id": "guidance",
                "role": "background",
                "entailed_by_excerpt": "yes",
            },
        ],
        "relations": [],
    }
    source_lookup = {"cohort": "Cohort Study", "guidance": "Guidance"}
    partition = partition_map_evidence(candidate_map, source_lookup)
    ledger = build_evidence_weighting_ledger(
        candidate_map,
        partition,
        {"status": "usable_with_review", "score": 90, "issues": []},
        source_lookup,
        question="For generally healthy adults, should eggs be treated as harmful, neutral, or beneficial for cardiovascular risk?",
    )
    rows = {row["claim_id"]: row for row in ledger["all_evidence"]}

    assert rows["c001"]["top_line_eligible"] is True
    assert rows["c002"]["appendix_only"] is True
    assert rows["c002"]["eligibility"]["noise_severity"] == "high"
    assert rows["c003"]["top_line_eligible"] is False
    assert rows["c003"]["eligibility"]["question_alignment"]["status"] == "weak"
    assert rows["c003"]["eligibility"]["section_eligibility"]["scope_and_exceptions"] is False
    assert rows["c003"]["eligibility"]["section_eligibility"]["decision_cruxes"] is False
    assert rows["c004"]["appendix_only"] is True
    assert rows["c004"]["eligibility"]["noise_severity"] == "high"


def test_typed_evidence_slots_option_comparison_and_crux_contract_are_built() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "Protected bike lanes reduced cyclist injury crashes by 34% on high-injury arterial corridors.",
                "source_id": "evaluation",
                "role": "conclusion_support",
                "entailed_by_excerpt": "yes",
            },
            {
                "claim_id": "c002",
                "claim": "Painted lanes are quicker and cheaper to implement but may not prevent encroachment on arterial streets.",
                "source_id": "paint",
                "role": "implementation_constraint",
                "entailed_by_excerpt": "yes",
            },
            {
                "claim_id": "c003",
                "claim": "Protected lane safety benefits depend on intersection design, turning conflicts, and maintenance capacity.",
                "source_id": "design",
                "role": "crux",
                "entailed_by_excerpt": "yes",
            },
        ],
        "relations": [
            {
                "relation_id": "r001",
                "source_claim": "c003",
                "target_claim": "c001",
                "relation_type": "depends_on",
                "rationale": "The observed safety benefit depends on intersection design and maintenance capacity.",
            },
            {
                "relation_id": "r002",
                "source_claim": "c002",
                "target_claim": "c001",
                "relation_type": "in_tension_with",
                "rationale": "Paint is easier to deploy, while protection has stronger safety logic on arterials.",
            },
        ],
    }
    source_lookup = {"evaluation": "Evaluation", "paint": "Paint Memo", "design": "Design Guidance"}

    enriched = annotate_map_with_evidence_slots(candidate_map)
    assert "evidence_slots" in enriched["claims"][0]
    assert "outcome_or_endpoint" in enriched["claims"][0]["evidence_slots"]
    assert "cost_or_feasibility" in enriched["claims"][1]["evidence_slots"]
    assert "implementation_condition" in enriched["claims"][2]["evidence_slots"]

    partition = partition_map_evidence(enriched, source_lookup)
    ledger = build_evidence_weighting_ledger(
        enriched,
        partition,
        {"status": "usable_with_review", "score": 95, "issues": []},
        source_lookup,
    )
    slot_ledger = build_evidence_slot_ledger(ledger)
    option_comparison = build_option_comparison(
        "Should a city prioritize protected bike lanes over painted bike lanes?",
        ledger,
        enriched,
    )
    crux_contract = build_crux_contract(enriched, ledger, option_comparison)

    assert slot_ledger["slot_counts"]["implementation_condition"] >= 1
    assert [row["option"] for row in option_comparison["options"]] == ["protected bike lanes", "painted bike lanes"]
    assert any(row["criterion"] == "cost_feasibility" for row in option_comparison["tradeoffs"])
    cost_tradeoff = next(row for row in option_comparison["tradeoffs"] if row["criterion"] == "cost_feasibility")
    assert cost_tradeoff["evidence_by_option"]["painted bike lanes"]
    assert cost_tradeoff["evidence_by_option"]["protected bike lanes"] == []
    crux_text = json.dumps(crux_contract).lower()
    assert "maintenance" in crux_text or "intersection" in crux_text
    assert crux_contract["crux_count"] >= 2


def test_briefing_scaffold_exposes_option_comparison_and_crux_contract() -> None:
    candidate_map = annotate_map_with_evidence_slots(
        {
            "claims": [
                {
                    "claim_id": "c001",
                    "claim": "Protected lanes are most relevant where traffic stress makes paint insufficient.",
                    "source_id": "design",
                    "role": "conclusion_support",
                    "entailed_by_excerpt": "yes",
                },
                {
                    "claim_id": "c002",
                    "claim": "Maintenance capacity determines whether protected lanes remain usable after installation.",
                    "source_id": "ops",
                    "role": "crux",
                    "entailed_by_excerpt": "yes",
                },
            ],
            "relations": [
                {
                    "relation_id": "r001",
                    "source_claim": "c002",
                    "target_claim": "c001",
                    "relation_type": "crux_for",
                    "rationale": "Maintenance capacity gates whether physical protection can deliver the intended effect.",
                }
            ],
        }
    )

    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 95, "issues": []},
        {"design": "Design Guidance", "ops": "Operations Memo"},
        {"items": []},
        question="Should a city prioritize protected lanes over painted lanes?",
    )

    assert scaffold["option_comparison"]["options"]
    assert scaffold["crux_contract"]["cruxes"]
    assert scaffold["evidence_slot_ledger"]["slot_counts"]
    slots = build_decision_memo_slots(scaffold, rendered="## Decision Brief\n\nPrioritize protected lanes.\n")
    assert "alternatives_or_comparators" not in slots["coverage"]["missing_required_slots"]
    comparator_slot = next(slot for slot in slots["slots"] if slot["slot_id"] == "alternatives_or_comparators")
    assert len(comparator_slot["rows"]) == 1
    assert "Comparator evidence" in comparator_slot["rows"][0]["claim"]
    assert "lacks clean evidence" in comparator_slot["rows"][0]["claim"]
    assert "protected lanes versus painted lanes" in comparator_slot["rows"][0]["claim"]
    assert "..." not in comparator_slot["rows"][0]["claim"]
    crux_rows = scaffold["crux_contract"]["cruxes"]
    assert any("Maintenance" in row["crux"] for row in crux_rows)


def test_repair_briefing_payload_replaces_source_only_evidence_roles() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "Portable cleaners should be supplemental when targeted filtration is needed.",
                "source_id": "epa_school",
                "role": "crux",
            },
            {
                "claim_id": "c002",
                "claim": "HVAC systems must still meet ventilation code requirements.",
                "source_id": "cdc_school",
                "role": "implementation_constraint",
            },
        ],
        "relations": [
            {
                "relation_id": "r001",
                "source_claim": "c002",
                "target_claim": "c001",
                "relation_type": "depends_on",
                "rationale": "Portable cleaner deployment depends on maintaining baseline HVAC ventilation.",
            }
        ],
    }
    source_lookup = {"epa_school": "EPA School Guidance", "cdc_school": "CDC School Guidance"}
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 95, "issues": []},
        source_lookup,
        {"items": []},
    )
    payload = {
        "decision_brief": "Use portable cleaners as supplements.",
        "confidence": "medium",
        "evidence_roles": {
            "main_support": ["EPA School Guidance"],
            "conflicting_evidence": [],
            "scope_limits": [],
            "method_limits": ["CDC School Guidance"],
        },
        "audit_trail": [],
    }

    repaired = repair_briefing_payload(payload, scaffold, source_lookup)

    assert repaired["evidence_roles"]["main_support"] != ["EPA School Guidance"]
    role_text = "\n".join(repaired["evidence_roles"]["scope_limits"] + repaired["evidence_roles"]["method_limits"])
    assert "HVAC systems must still meet ventilation code requirements" in role_text
    assert "Portable cleaner deployment depends on maintaining baseline HVAC ventilation" in "\n".join(
        repaired["audit_trail"]
    )


def test_partition_map_evidence_keeps_concern_out_of_main_support() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "eggs_c001",
                "claim": "Higher consumption of dietary cholesterol or eggs was associated with higher risk of incident CVD.",
                "source_id": "zhong_jama_2019",
                "role": "conclusion_support",
            },
            {
                "claim_id": "eggs_c002",
                "claim": "Moderate egg consumption was not associated with cardiovascular disease risk.",
                "source_id": "drouin_bmj_2020",
                "role": "conclusion_support",
            },
            {
                "claim_id": "eggs_c003",
                "claim": "The diabetes subgroup has a more uncertain risk profile.",
                "source_id": "li_2013",
                "role": "scope_limit",
            },
            {
                "claim_id": "eggs_c004",
                "claim": "The source document contains PubMed abstract text rather than the full article.",
                "source_id": "abstract_record",
                "role": "background",
            },
            {
                "claim_id": "eggs_c005",
                "claim": "Daily egg consumption was associated with lower risk among Chinese middle-aged adults.",
                "source_id": "qin_2018",
                "role": "measurement_validity",
            },
            {
                "claim_id": "eggs_c006",
                "claim": "High egg consumption was associated with higher cardiovascular risk among people with type 2 diabetes.",
                "source_id": "diabetes_meta",
                "role": "scope_limit",
            },
        ],
        "relations": [
            {
                "relation_id": "eggs_r001",
                "source_claim": "eggs_c001",
                "target_claim": "eggs_c002",
                "relation_type": "in_tension_with",
                "rationale": "Positive US cohort findings remain in tension with neutral adjusted/meta-analytic evidence.",
            }
        ],
    }

    partition = partition_map_evidence(
        candidate_map,
        {
            "zhong_jama_2019": "Zhong JAMA 2019",
            "drouin_bmj_2020": "Drouin BMJ 2020",
            "li_2013": "Li 2013",
            "abstract_record": "Abstract Record",
            "qin_2018": "Qin 2018",
            "diabetes_meta": "Diabetes Meta-analysis",
        },
    )

    main_support = "\n".join(partition["evidence_roles"]["main_support"])
    conflicts = "\n".join(partition["evidence_roles"]["conflicting_evidence"])
    scope = "\n".join(partition["evidence_roles"]["scope_limits"])
    methods = "\n".join(partition["evidence_roles"]["method_limits"])
    assert "Higher consumption" not in main_support
    assert "Higher consumption" in conflicts
    assert "not associated" in main_support
    assert "lower risk among Chinese" in main_support
    assert "High egg consumption" in conflicts
    assert "diabetes subgroup" in scope
    assert "abstract text" in methods
    assert "Daily egg consumption" not in methods


def test_repair_briefing_payload_moves_missectioned_concern_evidence() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "eggs_c001",
                "claim": "Higher egg consumption was associated with increased CVD risk.",
                "source_id": "zhong",
                "role": "conclusion_support",
            },
            {
                "claim_id": "eggs_c002",
                "claim": "Moderate egg consumption was not associated with CVD risk.",
                "source_id": "bmj",
                "role": "conclusion_support",
            },
        ],
        "relations": [],
    }
    source_lookup = {"zhong": "Zhong", "bmj": "BMJ"}
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 90, "issues": []},
        source_lookup,
        {"items": []},
    )
    payload = {
        "confidence": "medium",
        "evidence_roles": {
            "main_support": ["Higher egg consumption was associated with increased CVD risk. (Zhong)"],
            "conflicting_evidence": [],
            "scope_limits": [],
            "method_limits": ["Higher egg consumption was associated with increased CVD risk. (Zhong)"],
        },
    }

    repaired = repair_briefing_payload(payload, scaffold, source_lookup, candidate_map)

    assert "Higher egg consumption" not in "\n".join(repaired["evidence_roles"]["main_support"])
    assert "Higher egg consumption" not in "\n".join(repaired["evidence_roles"]["method_limits"])
    assert "Higher egg consumption" in "\n".join(repaired["evidence_roles"]["conflicting_evidence"])


def test_briefing_contract_is_domain_neutral_and_flags_overstatement_risks() -> None:
    partition = {
        "evidence_roles": {
            "main_support": [
                "The intervention was not associated with worse long-term outcomes.",
                "The short trial showed no adverse biomarker effects.",
            ],
            "conflicting_evidence": ["A cohort found higher risk in one subgroup."],
            "scope_limits": ["The evidence applies to high-intensity use in adults over 4 months."],
            "method_limits": ["The source contains abstract text and surrogate biomarker endpoints."],
        },
        "audit_trail": [],
    }

    contract = build_briefing_contract(
        partition,
        {"status": "usable_with_review", "score": 88, "issues": [{"severity": "risk", "issue_type": "abstract_only"}]},
    )

    lint_ids = {item["lint_id"] for item in contract["overstatement_lint"]}
    assert "null_evidence_not_benefit" in lint_ids
    assert "counterposition_visibility" in lint_ids
    assert "subgroup_to_generalization" in lint_ids
    assert "surrogate_to_hard_outcome" in lint_ids
    assert contract["scope_ledger"]["population_or_actor"]
    assert contract["scope_ledger"]["measurement_endpoint"]
    assert "low-concern" in contract["answer_frame"]["default_stance_instruction"]


def test_evidence_weighting_ledger_and_plan_prioritize_direct_evidence() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The intervention reduced hospitalization risk in adults.",
                "source_id": "trial_full",
                "source_span": "lines 1-1",
                "excerpt": "The intervention reduced hospitalization risk in adults.",
                "entailed_by_excerpt": "yes",
                "role": "conclusion_support",
                "supporting_sources": ["trial_full", "replication_full"],
            },
            {
                "claim_id": "c002",
                "claim": "The intervention improved a biomarker in a short abstract-only report.",
                "source_id": "abstract_only",
                "source_span": "lines 1-1",
                "excerpt": "The intervention improved a biomarker in a short abstract-only report.",
                "entailed_by_excerpt": "yes",
                "role": "measurement_validity",
                "extraction_method": "deterministic_coverage_backfill",
            },
        ],
        "relations": [],
    }
    source_lookup = {
        "trial_full": "Trial Full Text",
        "replication_full": "Replication Full Text",
        "abstract_only": "Abstract Only PubMed",
    }
    quality_report = {"status": "usable_with_review", "score": 90, "issues": []}
    partition = partition_map_evidence(candidate_map, source_lookup)
    ledger = build_evidence_weighting_ledger(candidate_map, partition, quality_report, source_lookup)
    scaffold = briefing_scaffold(candidate_map, quality_report, source_lookup, {"items": []})

    support_rows = ledger["top_evidence_by_section"]["main_support"]
    method_rows = ledger["top_evidence_by_section"]["method_limits"]
    assert support_rows[0]["claim_id"] == "c001"
    assert support_rows[0]["weight"] == "high"
    assert method_rows[0]["claim_id"] == "c002"
    assert method_rows[0]["weight"] in {"low", "medium"}
    assert "coverage_backfill_lower_weight" in method_rows[0]["modifiers"]
    assert scaffold["briefing_plan"]["paragraph_order"][0]["section"] == "bottom_line"
    assert "evidence_weighting_ledger" in scaffold


def test_decision_slots_extract_thresholds_subgroups_and_families() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "For generally healthy adults, moderate use up to 1 per day was not associated with worse CVD outcomes in a cohort study.",
                "source_id": "cohort_full",
                "source_span": "lines 1-1",
                "excerpt": "For generally healthy adults, moderate use up to 1 per day was not associated with worse CVD outcomes in a cohort study.",
                "entailed_by_excerpt": "yes",
                "role": "conclusion_support",
            },
            {
                "claim_id": "c002",
                "claim": "People with type 2 diabetes may have higher risk at high intake due to LDL cholesterol homeostasis.",
                "source_id": "mechanism_full",
                "source_span": "lines 1-1",
                "excerpt": "People with type 2 diabetes may have higher risk at high intake due to LDL cholesterol homeostasis.",
                "entailed_by_excerpt": "yes",
                "role": "scope_limit",
            },
            {
                "claim_id": "c003",
                "claim": "Guideline recommendations should focus on healthy dietary patterns rather than a single food.",
                "source_id": "guideline",
                "source_span": "lines 1-1",
                "excerpt": "Guideline recommendations should focus on healthy dietary patterns rather than a single food.",
                "entailed_by_excerpt": "yes",
                "role": "implementation_constraint",
            },
        ],
        "relations": [],
    }
    source_lookup = {"cohort_full": "Cohort Full", "mechanism_full": "Mechanism Full", "guideline": "Guideline"}
    quality_report = {"status": "usable_with_review", "score": 90, "issues": []}
    partition = partition_map_evidence(candidate_map, source_lookup)
    ledger = build_evidence_weighting_ledger(candidate_map, partition, quality_report, source_lookup)
    slots = build_decision_slots(ledger)
    scaffold = briefing_scaffold(candidate_map, quality_report, source_lookup, {"items": []})

    assert ledger["family_counts"]["cohort_or_observational"] >= 1
    assert ledger["family_counts"]["guideline_or_recommendation"] >= 1
    assert slots["dose_or_intensity_threshold"]
    assert slots["high_risk_subgroup"]
    assert slots["mechanism"]
    assert scaffold["decision_model"]["decision_slots"]["dose_or_intensity_threshold"]
    assert "evidence_families" in scaffold["decision_model"]


def test_map_sufficiency_report_tracks_present_and_missing_decision_contract() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "For generally healthy adults, moderate use up to one per day was not associated with worse CVD outcomes in a cohort study.",
                "source_id": "cohort_full",
                "source_span": "lines 1-1",
                "excerpt": "For generally healthy adults, moderate use up to one per day was not associated with worse CVD outcomes in a cohort study.",
                "entailed_by_excerpt": "yes",
                "role": "conclusion_support",
            }
        ],
        "relations": [],
    }
    source_lookup = {"cohort_full": "Cohort Full"}
    quality_report = {"status": "usable_with_review", "score": 90, "issues": []}
    partition = partition_map_evidence(candidate_map, source_lookup)
    contract = build_briefing_contract(partition, quality_report)
    ledger = build_evidence_weighting_ledger(candidate_map, partition, quality_report, source_lookup)
    clusters = build_proposition_clusters(candidate_map, ledger, source_lookup)
    decision_model = build_decision_model(clusters, contract, quality_report, ledger)

    report = build_map_sufficiency_report(
        candidate_map,
        question="For generally healthy adults, should this exposure be recommended compared with alternatives?",
        evidence_ledger=ledger,
        decision_model=decision_model,
        quality_report=quality_report,
    )

    assert report["schema_id"] == "map_sufficiency_report_v1"
    assert "dose_or_intensity_threshold" in report["present_decision_slots"]
    assert "substitution_or_comparator" in report["missing_expected_decision_slots"]
    assert any(item["kind"] == "acknowledge_missing_slot" for item in report["output_obligations"])
    assert report["status"] == "usable_with_named_gaps"


def test_decision_slots_ignore_appendix_only_extraction_placeholder_values() -> None:
    ledger = {
        "profile_id": "default",
        "all_evidence": [
            {
                "claim_id": "c001",
                "claim": "Appendix-only extraction with malformed or fragmentary prose; consult the source before using it as evidence.",
                "decision_slots": ["setting_or_context"],
                "score": 10,
            }
        ],
    }

    slots = build_decision_slots(ledger)

    assert slots["setting_or_context"] == []


def test_briefing_validation_checks_sufficiency_obligations() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "For generally healthy adults, moderate use up to one per day was not associated with worse CVD outcomes in a cohort study.",
                "source_id": "cohort_full",
                "role": "conclusion_support",
            }
        ],
        "relations": [],
    }
    source_lookup = {"cohort_full": "Cohort Full"}
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 90, "issues": []},
        source_lookup,
        {"items": []},
        question="For generally healthy adults, should this exposure be recommended compared with alternatives?",
    )

    incomplete = validate_briefing_against_scaffold("## Decision Brief\n\nUse it.\n", scaffold, candidate_map)
    complete = validate_briefing_against_scaffold(
        "## Decision Brief\n\nUse it only up to one per day. The map does not expose a substitution or comparator.\n\n## Evidence Roles\n\n### Main Support\n\n- Evidence.",
        scaffold,
        candidate_map,
    )

    assert incomplete["status"] in {"passes_with_warnings", "needs_review"}
    assert incomplete["issues"]
    assert complete["score"] > incomplete["score"]


def test_map_briefing_prompt_uses_compact_model_contract() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "Moderate use up to one per day was not associated with worse outcomes.",
                "source_id": "doc",
                "role": "conclusion_support",
            }
        ],
        "relations": [],
    }
    source_lookup = {"doc": "Doc"}
    quality_report = {"status": "usable_with_review", "score": 90, "issues": []}
    scaffold = briefing_scaffold(candidate_map, quality_report, source_lookup, {"items": []}, question="Should this be recommended?")

    prompt = build_map_briefing_prompt(
        candidate_map=candidate_map,
        quality_report=quality_report,
        question="Should this be recommended?",
        source_lookup=source_lookup,
        erosion_audit={"items": []},
        scaffold=scaffold,
    )

    assert "Return valid compact JSON only" in prompt
    assert "Do not return evidence_roles or audit_trail" in prompt
    assert "Prioritized map artifact:" not in prompt
    assert "evidence_roles_for_deterministic_attachment" in prompt


def test_model_parse_diagnostics_flags_truncated_fenced_json() -> None:
    diagnostics = model_parse_diagnostics('```json\n{"decision_brief": "x", "audit_trail": ["unfinished"', parse_ok=False)

    assert diagnostics["starts_with_json_fence"] is True
    assert diagnostics["looks_truncated"] is True
    assert diagnostics["brace_balance"] > 0
