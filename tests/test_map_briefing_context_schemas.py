from __future__ import annotations

from epistemic_case_mapper.map_briefing_context_schemas import (
    CandidateEvidenceCardsReport,
    SOURCE_EVIDENCE_CARD_OWNERSHIP,
    SourceEvidenceCardReport,
    SourceMapReconciliationReport,
    validate_artifact_ownership,
)
from epistemic_case_mapper.map_briefing_context_curation import build_decision_ready_context_bundle
from epistemic_case_mapper.map_briefing_context_curation import build_source_coverage_report
from epistemic_case_mapper.map_briefing_context_reports import (
    build_evidence_quality_report,
    build_final_brief_evaluation,
    build_memo_coherence_report,
    build_pipeline_migration_ledger,
    build_runtime_budget_report,
    build_section_context_acceptance_report,
    build_source_evidence_cards,
    build_source_sufficiency_report,
)
from epistemic_case_mapper.map_briefing_section_input_compiler import compile_model_section_packet


def test_source_evidence_card_schema_accepts_exact_anchored_card() -> None:
    report = SourceEvidenceCardReport.model_validate(
        {
            "source_card_count": 1,
            "anchored_card_count": 1,
            "cards": [
                {
                    "source_card_id": "sc0001",
                    "source_id": "s1",
                    "source_title": "Study",
                    "source_span": "10:40",
                    "source_quote_or_excerpt": "A source-backed claim.",
                    "anchor_confidence": "exact",
                }
            ],
        }
    )

    assert report.cards[0].source_id == "s1"


def test_ownership_validation_rejects_model_generated_source_identity() -> None:
    artifact = {
        "source_card_count": 1,
        "cards": [
            {
                "source_card_id": "sc0001",
                "source_id": "s1",
                "source_title": "Study",
                "anchor_confidence": "missing",
            }
        ],
    }

    validation = validate_artifact_ownership(
        "source_evidence_cards",
        artifact,
        schema=SourceEvidenceCardReport,
        field_ownership=SOURCE_EVIDENCE_CARD_OWNERSHIP,
        model_generated_fields=["source_id", "endpoint_match"],
    )

    assert validation["status"] == "invalid"
    assert validation["schema_parse_ok"] is True
    assert validation["deterministic_only_violations"] == [
        {"path": "source_id", "ownership": "deterministic_only"}
    ]
    assert validation["fallback_behavior"] == "quarantine_invalid_artifact"


def test_ownership_validation_reports_schema_errors() -> None:
    validation = validate_artifact_ownership(
        "source_evidence_cards",
        {"cards": [{"source_card_id": "sc0001"}]},
        schema=SourceEvidenceCardReport,
        field_ownership=SOURCE_EVIDENCE_CARD_OWNERSHIP,
    )

    assert validation["status"] == "invalid"
    assert validation["schema_parse_ok"] is False
    assert any(error["path"].endswith("source_id") for error in validation["validation_errors"])


def test_source_sufficiency_and_quality_reports_from_claim_anchors() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c1",
                "claim": "Moderate use directly changes the decision-relevant outcome.",
                "source_id": "s1",
                "source_span": "10:55",
                "role": "conclusion_support",
                "decision_relevance_score": 8,
                "evidence_family": "cohort_study",
            },
            {
                "claim_id": "c2",
                "claim": "A high-risk subgroup is an important exception.",
                "source_id": "s2",
                "role": "scope_limit",
                "decision_relevance_score": 5,
            },
        ]
    }

    source_cards = build_source_evidence_cards(
        candidate_map,
        source_lookup={"s1": "Source One", "s2": "Source Two"},
        source_urls={"s1": "https://example.org/source-one"},
    )
    sufficiency = build_source_sufficiency_report(
        decision_question="Should moderate use change the decision-relevant outcome?",
        source_evidence_cards=source_cards,
        scaffold={"map_sufficiency_report": {}},
    )
    quality = build_evidence_quality_report(source_cards)

    assert source_cards["schema_id"] == "source_evidence_cards_v1"
    assert source_cards["source_card_count"] == 2
    assert source_cards["anchored_card_count"] == 2
    assert sufficiency["schema_id"] == "source_sufficiency_report_v1"
    assert sufficiency["status"] == "sufficient_for_bounded_answer"
    assert "counterweight_evidence" in sufficiency["missing_source_categories"]
    assert quality["schema_id"] == "evidence_quality_report_v1"
    assert quality["card_count"] == 2
    assert quality["quality_components"]["sc0001"]["directness"] == "direct"


def test_source_role_assignment_does_not_treat_lower_mortality_as_challenge() -> None:
    source_cards = build_source_evidence_cards(
        {
            "claims": [
                {
                    "claim_id": "c1",
                    "claim": "Higher intake was associated with lower mortality in the default population.",
                    "source_id": "s1",
                    "source_span": "lines 1-2",
                    "excerpt": "Higher intake was associated with lower mortality in the default population.",
                    "role": "risk_estimate",
                    "decision_relevance_score": 8,
                }
            ]
        },
        source_lookup={"s1": "Cohort Study"},
    )

    assert source_cards["cards"][0]["supports_challenges_or_scopes"] != "challenges"


def test_source_sufficiency_reconciles_counterweight_relations() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c1",
                "claim": "The intervention was not associated with worse outcomes.",
                "source_id": "s1",
                "source_span": "lines 1-2",
                "role": "conclusion_support",
                "decision_relevance_score": 8,
            },
            {
                "claim_id": "c2",
                "claim": "A narrower subgroup showed higher risk.",
                "source_id": "s2",
                "source_span": "lines 3-4",
                "role": "scope_limit",
                "decision_relevance_score": 8,
            },
        ],
        "relations": [
            {
                "relation_id": "r1",
                "source_claim": "c2",
                "target_claim": "c1",
                "relation_type": "in_tension_with",
            }
        ],
    }
    source_cards = build_source_evidence_cards(candidate_map, source_lookup={"s1": "S1", "s2": "S2"})

    sufficiency = build_source_sufficiency_report(
        decision_question="Should the intervention be treated as low concern?",
        source_evidence_cards=source_cards,
        scaffold={"map_sufficiency_report": {}},
        candidate_map=candidate_map,
    )

    assert sufficiency["coverage"]["has_counterweight"] is True
    assert "counterweight_evidence" not in sufficiency["missing_source_categories"]
    assert any(
        source.startswith("relation:in_tension_with")
        for source in sufficiency["semantic_signal_report"]["counterweight_signal_sources"]
    )


def test_decision_ready_context_bundle_builds_plan_artifacts() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c1",
                "claim": "The default option improves the decision outcome by 12 percent.",
                "source_id": "s1",
                "source_span": "lines 1-2",
                "excerpt": "The default option improves the decision outcome by 12 percent.",
                "role": "conclusion_support",
                "decision_relevance_score": 8,
                "evidence_family": "trial",
                "quantity_values": ["12 percent"],
            },
            {
                "claim_id": "c2",
                "claim": "The effect is uncertain for the high-risk subgroup.",
                "source_id": "s2",
                "source_span": "lines 3-4",
                "excerpt": "The effect is uncertain for the high-risk subgroup.",
                "role": "scope_limit",
                "decision_relevance_score": 7,
            },
            {
                "claim_id": "c3",
                "claim": "A competing source reports implementation burden.",
                "source_id": "s3",
                "source_span": "lines 5-6",
                "excerpt": "A competing source reports implementation burden.",
                "role": "conflicting_evidence",
                "decision_relevance_score": 6,
            },
        ]
    }

    bundle = build_decision_ready_context_bundle(
        candidate_map,
        scaffold={"map_sufficiency_report": {}},
        question="Should the default option be adopted?",
        source_lookup={"s1": "Trial", "s2": "Subgroup Study", "s3": "Implementation Report"},
    )

    reconciliation = SourceMapReconciliationReport.model_validate(bundle["source_map_reconciliation"])
    candidates = CandidateEvidenceCardsReport.model_validate(bundle["candidate_evidence_cards"])

    assert reconciliation.source_backed_count == 3
    assert candidates.main_text_count >= 2
    assert bundle["source_coverage_report"]["schema_id"] == "source_coverage_report_v1"
    assert bundle["source_coverage_report"]["assignment_basis"] == "pending_final_projection"


def test_model_section_packet_prefers_section_context_decision_packets() -> None:
    contract = {
        "_section_synthesis_scaffold": {
            "section_context_decision_packets": {
                "sections": [
                    {
                        "section": "Evidence Carrying the Conclusion",
                        "section_thesis": "Use the curated card, not the legacy obligation.",
                        "decision_move": "Explain the load-bearing evidence.",
                        "context_status": "ready",
                        "owned_evidence": [
                            {
                                "candidate_card_id": "ec0001",
                                "source_card_ids": ["sc0001"],
                                "claim": "The curated source-backed card is load-bearing.",
                                "source": "Curated Source",
                                "intended_role": "support",
                                "reason_for_inclusion": "It is assigned to this section.",
                            }
                        ],
                        "reference_only_evidence": [],
                        "do_not_use_cards": ["ec0099"],
                    }
                ]
            }
        },
        "required_evidence": [
            {"claim": "Legacy obligation should not be primary.", "source": "Legacy Source", "slot": "support"}
        ],
        "section_synthesis_packet": {},
    }

    packet = compile_model_section_packet("Evidence Carrying the Conclusion", contract)

    assert packet["context_source"] == "section_context_decision_packet"
    assert packet["section_thesis"] == "Use the curated card, not the legacy obligation."
    assert packet["owned_evidence"][0]["candidate_card_id"] == "ec0001"
    assert packet["do_not_use_cards"] == ["ec0099"]


def test_context_bundle_preserves_counterweight_role_on_narrower_scope_cards() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c1",
                "claim": "Moderate use improves the decision-relevant outcome in the default adult population.",
                "source_id": "s1",
                "source_span": "lines 1-2",
                "excerpt": "Moderate use improves the decision-relevant outcome in the default adult population.",
                "role": "conclusion_support",
                "decision_relevance_score": 8,
            },
            {
                "claim_id": "c2",
                "claim": "High use increased risk in a narrower high-risk subgroup.",
                "source_id": "s2",
                "source_span": "lines 3-4",
                "excerpt": "High use increased risk in a narrower high-risk subgroup.",
                "role": "conflicting_evidence",
                "decision_relevance_score": 9,
            },
        ]
    }
    scaffold = {
        "map_sufficiency_report": {},
        "evidence_weighting_ledger": {
            "all_evidence": [
                {
                    "claim_id": "c1",
                    "appendix_only": False,
                    "top_line_eligible": True,
                    "question_fit": {"status": "fits"},
                },
                {
                    "claim_id": "c2",
                    "appendix_only": False,
                    "top_line_eligible": False,
                    "question_fit": {"status": "narrower_than_question"},
                },
            ]
        },
    }

    bundle = build_decision_ready_context_bundle(
        candidate_map,
        scaffold=scaffold,
        question="Should moderate use be adopted for the default adult population?",
        source_lookup={"s1": "Default Study", "s2": "Subgroup Study"},
    )
    cards = {card["claim_ids"][0]: card for card in bundle["candidate_evidence_cards"]["cards"]}

    assert cards["c2"]["role"] == "counterweight"
    assert "counterweight" in cards["c2"]["evidence_roles"]
    assert "scope" in cards["c2"]["evidence_roles"]
    assert "Evidence Carrying the Conclusion" in cards["c2"]["section_candidates"]
    assert "Practical Scope and Exceptions" in cards["c2"]["section_candidates"]


def test_scope_labeled_quantitative_cards_remain_evidence_carrying() -> None:
    candidate_map = {
        "claims": [
            {
                "claim_id": "c1",
                "claim": "In adults, the default option changed the decision outcome by 18 percent.",
                "source_id": "s1",
                "source_span": "lines 1-2",
                "excerpt": "In adults, the default option changed the decision outcome by 18 percent.",
                "role": "scope_limit",
                "decision_relevance_score": 8,
                "quantity_values": ["18 percent"],
            }
        ]
    }

    bundle = build_decision_ready_context_bundle(
        candidate_map,
        scaffold={"map_sufficiency_report": {}},
        question="Should the default option be adopted for adults?",
        source_lookup={"s1": "Quantitative Scope Study"},
    )
    card = bundle["candidate_evidence_cards"]["cards"][0]

    assert card["role"] == "quantity"
    assert card["evidence_roles"] == ["quantity", "scope"]
    assert "Evidence Carrying the Conclusion" in card["section_candidates"]


def test_source_coverage_prefers_final_projection_assignments() -> None:
    source_cards = {"source_card_count": 2}
    candidates = {
        "cards": [
            {
                "candidate_card_id": "ec0001",
                "decision_relevance_score": 9,
                "inclusion_recommendation": "main_text",
            },
            {
                "candidate_card_id": "ec0002",
                "decision_relevance_score": 9,
                "inclusion_recommendation": "main_text",
            },
        ]
    }
    final_packets = {
        "sections": [
            {
                "section": "Evidence Carrying the Conclusion",
                "owned_evidence": [{"candidate_card_id": "ec0002"}],
            }
        ]
    }

    report = build_source_coverage_report(
        source_evidence_cards=source_cards,
        candidate_evidence_cards=candidates,
        source_map_reconciliation={"rows": []},
        section_context_decision_packets=final_packets,
    )

    assert report["assignment_basis"] == "final_projection_or_context_packets"
    assert report["assigned_main_card_count"] == 1
    assert report["final_assigned_main_card_count"] == 1
    assert report["omitted_high_relevance_card_ids"] == ["ec0001"]


def test_section_context_acceptance_requires_roles_and_reasons() -> None:
    report = build_section_context_acceptance_report(
        [
            {
                "title": "Evidence Carrying the Conclusion",
                "section_job": "Explain the main evidence.",
                "model_packet": {
                    "section_thesis": "The section can explain the main evidence.",
                    "owned_evidence": [
                        {
                            "claim": "Claim one.",
                            "source": "Source",
                            "intended_role": "support",
                            "reason_for_inclusion": "This is the section's support card.",
                        },
                        {
                            "claim": "Claim two.",
                            "source": "Source",
                            "intended_role": "counterweight",
                            "reason_for_inclusion": "This is the section's counterweight card.",
                        },
                        {
                            "claim": "Claim three.",
                            "source": "Source",
                            "intended_role": "scope boundary",
                            "reason_for_inclusion": "This is the section's scope card.",
                        },
                    ],
                },
                "packet": {},
            },
            {
                "title": "Why This Read",
                "section_job": "Explain the read.",
                "model_packet": {"owned_evidence": [{"claim": "Unexplained claim."}]},
                "packet": {},
            },
        ]
    )

    assert report["schema_id"] == "section_context_acceptance_report_v1"
    assert report["status"] == "warning"
    assert report["sections"][0]["status"] == "ready"
    assert report["sections"][1]["card_budget_status"] == "under_budget"
    assert any("missing intended_role" in issue for issue in report["sections"][1]["issues"])


def test_final_diagnostic_reports_are_deterministic() -> None:
    scaffold = {
        "question": "Should the decision change?",
        "source_display_names": {"s1": "Source One"},
        "source_sufficiency_report": {"bounded_answer_required": True},
        "evidence_quality_report": {"weak_or_indirect_count": 1},
    }
    memo = """## Decision Brief

**Decision question:** Should the decision change?

The current map supports a bounded read over the provided documents, with limited evidence quality.

**Confidence:** medium

## Sources

- Source One
"""

    coherence = build_memo_coherence_report(
        memo_markdown=memo,
        decision_question="Should the decision change?",
        scaffold=scaffold,
    )
    migration = build_pipeline_migration_ledger(section_context_acceptance_path="section_context_acceptance_report.json")
    runtime = build_runtime_budget_report(
        section_rewrite_report={"sections": [{"attempt_count": 2}, {"attempt_count": 1}]},
        reader_rewrite_report={"status": "skipped_prompt_backend"},
    )
    evaluation = build_final_brief_evaluation(
        memo_markdown=memo,
        memo_path="BRIEFING.md",
        decision_question="Should the decision change?",
        coherence_report=coherence,
        scaffold=scaffold,
    )

    assert coherence["schema_id"] == "memo_coherence_report_v1"
    assert coherence["status"] == "pass"
    assert migration["schema_id"] == "pipeline_migration_ledger_v1"
    assert migration["status"] == "warning"
    assert runtime["schema_id"] == "runtime_budget_report_v1"
    assert runtime["model_call_count"] == 3
    assert runtime["most_expensive_stage"] == "section_rewrite"
    assert evaluation["schema_id"] == "final_brief_evaluation_v1"
    assert evaluation["status"] == "pass"
