from __future__ import annotations

from epistemic_case_mapper.map_briefing import (
    build_decision_slots,
    build_evidence_weighting_ledger,
    partition_map_evidence,
    validate_briefing_against_scaffold,
)


def test_adult_question_routes_child_only_evidence_to_appendix() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The Committee recommended providing infants and toddlers with eggs beginning at 6 to 12 months old.",
                "source_id": "guidance",
                "role": "implementation_constraint",
                "entailed_by_excerpt": "yes",
            },
            {
                "claim_id": "c002",
                "claim": "Moderate egg consumption was not associated with higher cardiovascular disease risk in generally healthy adults.",
                "source_id": "cohort",
                "role": "conclusion_support",
                "entailed_by_excerpt": "yes",
            },
        ],
        "relations": [],
    }
    source_lookup = {"guidance": "Guidance", "cohort": "Cohort"}
    partition = partition_map_evidence(candidate_map, source_lookup)
    ledger = build_evidence_weighting_ledger(
        candidate_map,
        partition,
        {"status": "usable_with_review", "score": 90, "issues": []},
        source_lookup,
        question="For generally healthy adults, should eggs be treated as harmful, neutral, or beneficial for cardiovascular risk?",
    )
    rows = {row["claim_id"]: row for row in ledger["all_evidence"]}

    assert rows["c001"]["appendix_only"] is True
    assert rows["c001"]["eligibility"]["question_fit"]["status"] == "mismatch"
    assert rows["c001"]["eligibility"]["top_line_eligible"] is False
    assert rows["c002"]["top_line_eligible"] is True


def test_general_population_question_keeps_narrower_health_subgroup_off_top_line() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "High use was associated with higher cardiovascular risk in people with type 2 diabetes.",
                "source_id": "subgroup",
                "role": "conclusion_support",
                "entailed_by_excerpt": "yes",
            },
            {
                "claim_id": "c002",
                "claim": "Moderate use was not associated with higher cardiovascular risk in generally healthy adults.",
                "source_id": "cohort",
                "role": "conclusion_support",
                "entailed_by_excerpt": "yes",
            },
        ],
        "relations": [],
    }
    source_lookup = {"subgroup": "Subgroup Study", "cohort": "Cohort"}
    partition = partition_map_evidence(candidate_map, source_lookup)
    ledger = build_evidence_weighting_ledger(
        candidate_map,
        partition,
        {"status": "usable_with_review", "score": 90, "issues": []},
        source_lookup,
        question="For generally healthy adults, should moderate use be treated as harmful, neutral, or beneficial for cardiovascular risk?",
    )
    rows = {row["claim_id"]: row for row in ledger["all_evidence"]}

    assert rows["c001"]["appendix_only"] is False
    assert rows["c001"]["eligibility"]["question_fit"]["status"] == "narrower_than_question"
    assert rows["c001"]["top_line_eligible"] is False
    assert rows["c001"]["eligibility"]["section_eligibility"]["decision_brief"] is False
    assert rows["c002"]["top_line_eligible"] is True


def test_decision_slots_reject_person_time_as_default_population() -> None:
    ledger = {
        "profile_id": "general_decision_support",
        "all_evidence": [
            {
                "claim_id": "c001",
                "claim": "236,084 person-years of follow-up.",
                "decision_slots": ["default_population"],
                "score": 9,
                "weight": "high",
                "evidence_family": "cohort_or_observational",
                "source": "Cohort",
            },
            {
                "claim_id": "c002",
                "claim": "Generally healthy adults without cardiovascular disease were the default population.",
                "decision_slots": ["default_population"],
                "score": 8,
                "weight": "high",
                "evidence_family": "cohort_or_observational",
                "source": "Cohort",
            },
        ],
    }

    slots = build_decision_slots(ledger)

    assert [entry["claim_id"] for entry in slots["default_population"]] == ["c002"]


def test_person_time_study_scale_context_is_appendix_only() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The follow-up period for the study participants was 236,084 person-years.",
                "source_id": "cohort",
                "role": "scope_limit",
                "entailed_by_excerpt": "yes",
            }
        ],
        "relations": [],
    }
    source_lookup = {"cohort": "Cohort"}
    partition = partition_map_evidence(candidate_map, source_lookup)
    ledger = build_evidence_weighting_ledger(
        candidate_map,
        partition,
        {"status": "usable_with_review", "score": 90, "issues": []},
        source_lookup,
        question="For generally healthy adults, should eggs be treated as harmful, neutral, or beneficial for cardiovascular risk?",
    )
    row = ledger["all_evidence"][0]

    assert row["appendix_only"] is True
    assert row["eligibility"]["noise_severity"] == "high"
    assert row["noise"]["kind"] == "administrative_study_context"


def test_briefing_validation_flags_wrong_scope_and_sparse_graph() -> None:
    candidate_map = {
        "claims": [{"claim_id": f"c{index:03d}", "claim": f"Claim {index} has evidence."} for index in range(1, 41)],
        "relations": [],
    }
    scaffold = {
        "evidence_weighting_ledger": {
            "all_evidence": [
                {
                    "claim_id": "c001",
                    "claim": "The Committee recommended providing infants and toddlers with eggs beginning at 6 to 12 months old.",
                    "section": "main_support",
                    "appendix_only": True,
                    "question_fit": {"status": "mismatch", "scope_mismatch_flags": ["target_population_age_mismatch"]},
                }
            ]
        },
        "map_sufficiency_report": {"output_obligations": []},
    }

    validation = validate_briefing_against_scaffold(
        "## Decision Brief\n\nThe Committee recommended providing infants and toddlers with eggs beginning at 6 to 12 months old.",
        scaffold,
        candidate_map,
    )

    issue_types = {issue["issue_type"] for issue in validation["issues"]}
    assert "briefing_mentions_wrong_scope_evidence" in issue_types
    assert "briefing_uses_appendix_only_evidence" in issue_types
    assert "sparse_relation_graph" in issue_types


def test_briefing_validation_does_not_flag_generic_overlap_with_excluded_evidence() -> None:
    candidate_map = {
        "claims": [{"claim_id": f"c{index:03d}", "claim": f"Claim {index} has evidence."} for index in range(1, 41)],
        "relations": [{"relation_id": f"r{index:03d}", "source_claim": "c001", "target_claim": "c002"} for index in range(1, 4)],
    }
    scaffold = {
        "evidence_weighting_ledger": {
            "all_evidence": [
                {
                    "claim_id": "c001",
                    "claim": "Higher egg intake in infants was associated with allergy outcomes in a pediatric feeding trial.",
                    "section": "main_support",
                    "appendix_only": True,
                    "question_fit": {"status": "mismatch", "scope_mismatch_flags": ["target_population_age_mismatch"]},
                }
            ]
        },
        "map_sufficiency_report": {"output_obligations": []},
    }

    validation = validate_briefing_against_scaffold(
        "## Decision Brief\n\nModerate egg consumption in generally healthy adults is treated as neutral for cardiovascular risk.",
        scaffold,
        candidate_map,
    )

    issue_types = {issue["issue_type"] for issue in validation["issues"]}
    assert "briefing_mentions_wrong_scope_evidence" not in issue_types
    assert "briefing_uses_appendix_only_evidence" not in issue_types


def test_briefing_validation_requires_distinctive_phrase_for_appendix_only_claims() -> None:
    candidate_map = {
        "claims": [{"claim_id": f"c{index:03d}", "claim": f"Claim {index} has evidence."} for index in range(1, 41)],
        "relations": [{"relation_id": f"r{index:03d}", "source_claim": "c001", "target_claim": "c002"} for index in range(1, 4)],
    }
    scaffold = {
        "evidence_weighting_ledger": {
            "all_evidence": [
                {
                    "claim_id": "c001",
                    "claim": "The association between dietary cholesterol consumption and all-cause mortality was stronger in women than in men.",
                    "section": "conflicting_evidence",
                    "appendix_only": True,
                    "question_fit": {"status": "uncertain"},
                }
            ]
        },
        "map_sufficiency_report": {"output_obligations": []},
    }

    validation = validate_briefing_against_scaffold(
        "## Decision Brief\n\nThe associations between egg consumption and incident CVD or all-cause mortality were no longer significant after adjusting for dietary cholesterol consumption.",
        scaffold,
        candidate_map,
    )

    issue_types = {issue["issue_type"] for issue in validation["issues"]}
    assert "briefing_uses_appendix_only_evidence" not in issue_types
