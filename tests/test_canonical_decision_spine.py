from __future__ import annotations

from epistemic_case_mapper.map_briefing_classical_selection import build_classical_evidence_selection_report
from epistemic_case_mapper.map_briefing_context_reconciliation import (
    build_section_context_decision_packets,
    build_section_context_quality_report,
    build_slot_reconciliation_report,
)
from epistemic_case_mapper.map_briefing_section_input_compiler import compile_model_section_packet
from epistemic_case_mapper.map_briefing_spine_arbitration import arbitrate_canonical_decision_spine
from epistemic_case_mapper.map_briefing_spine_projection import (
    build_section_projection_packets,
    build_section_projection_readiness_report,
)
from epistemic_case_mapper.map_briefing_validation import validate_briefing_against_scaffold
from epistemic_case_mapper.map_briefing_spine_bundle import build_decision_spine_bundle
from epistemic_case_mapper.map_briefing_spine_validation import validate_canonical_decision_spine
from epistemic_case_mapper.model_backends import ModelBackendResult


def test_classical_selection_reports_duplicates_centrality_and_quantities() -> None:
    report = build_classical_evidence_selection_report(_candidate_map(), _scaffold(), question="Should the option be adopted?")

    assert report["schema_id"] == "classical_evidence_selection_report_v1"
    assert report["claim_cluster_report"]["duplicate_pair_count"] >= 1
    assert report["evidence_centrality_report"]["top_claim_ids"]
    assert report["coverage_balance_report"]["source_counts"] == {"s1": 1, "s2": 1, "s3": 1}
    assert report["quantity_outlier_report"]["outlier_count"] >= 1


def test_spine_bundle_builds_valid_traceable_spine_and_projection_packets() -> None:
    bundle = build_decision_spine_bundle(_candidate_map(), _scaffold(), question="Should the option be adopted?")

    spine = bundle["canonical_decision_spine"]
    assert spine["schema_id"] == "canonical_decision_spine_v1"
    assert spine["status"] in {"ready", "bounded"}
    assert spine["default_answer"]["candidate_card_ids"]
    assert bundle["canonical_decision_spine_validation"]["status"] == "valid"
    assert bundle["decision_spine_consistency_report"]["status"] == "pass"
    assert bundle["slot_eligibility_audit"]["slots"]
    assert bundle["slot_reconciliation_report"]["rows"]
    assert bundle["section_projection_packets"]["sections"]
    assert bundle["section_context_decision_packets"]["sections"]
    assert bundle["section_context_quality_report"]["status"] in {"ready", "warning"}
    assert bundle["section_projection_readiness_report"]["status"] in {"ready", "warning"}


def test_spine_validation_rejects_unanchored_evidence_field() -> None:
    validation = validate_canonical_decision_spine(
        {
            "schema_id": "canonical_decision_spine_v1",
            "decision_question": "Q?",
            "default_answer": {
                "field_id": "default_answer",
                "claim": "Answer with no provenance.",
                "role": "default_answer",
            },
        }
    )

    assert validation["status"] == "invalid"


def test_spine_bundle_marks_empty_candidate_pool_insufficient() -> None:
    scaffold = _scaffold()
    scaffold["candidate_evidence_cards"] = {"cards": []}

    bundle = build_decision_spine_bundle(_candidate_map(), scaffold, question="Should the option be adopted?")

    assert bundle["canonical_decision_spine"]["status"] == "insufficient"
    assert bundle["canonical_decision_spine_validation"]["status"] in {"valid", "warning"}


def test_spine_uses_anchored_appendix_cards_as_bounded_fallback() -> None:
    scaffold = _scaffold()
    for card in scaffold["candidate_evidence_cards"]["cards"]:
        card["inclusion_recommendation"] = "appendix_only"
        card["quality"] = "indirect"

    bundle = build_decision_spine_bundle(_candidate_map(), scaffold, question="Should the option be adopted?")
    spine = bundle["canonical_decision_spine"]

    assert spine["status"] == "bounded"
    assert spine["default_answer"]["candidate_card_ids"]
    assert spine["construction_report"]["candidate_card_count"] == 3


def test_spine_infers_evidence_carriers_when_upstream_roles_are_coarse() -> None:
    scaffold = _scaffold()
    cards = scaffold["candidate_evidence_cards"]["cards"]
    for card in cards:
        card["role"] = "scope"
        card["inclusion_recommendation"] = "appendix_only"
        card["quality"] = "indirect"
    cards[0]["claim"] = "The option was not associated with higher adverse-event risk in the available evidence."
    cards[1]["claim"] = "The option improved the primary outcome in a source-backed cohort."
    cards[2]["claim"] = "The option was associated with higher risk in a narrower subgroup."

    bundle = build_decision_spine_bundle(_candidate_map(), scaffold, question="Should the option be adopted?")
    spine = bundle["canonical_decision_spine"]
    evidence_section = next(
        section
        for section in bundle["section_projection_readiness_report"]["sections"]
        if section["section"] == "Evidence Carrying the Conclusion"
    )

    assert spine["strongest_support"]
    assert spine["strongest_counterevidence"]
    assert "role_inferred_from_claim_text" in spine["strongest_support"][0]["limits"]
    assert evidence_section["context_status"] in {"ready", "warning"}
    assert bundle["section_projection_readiness_report"]["status"] in {"ready", "warning"}


def test_spine_groups_cards_by_secondary_evidence_roles() -> None:
    scaffold = _scaffold()
    cards = scaffold["candidate_evidence_cards"]["cards"]
    cards[0]["role"] = "scope"
    cards[0]["evidence_roles"] = ["support", "scope", "quantity"]
    cards[0]["section_candidates"] = [
        "Evidence Carrying the Conclusion",
        "Practical Scope and Exceptions",
        "Practical Read",
    ]

    bundle = build_decision_spine_bundle(_candidate_map(), scaffold, question="Should the option be adopted?")
    spine = bundle["canonical_decision_spine"]
    support_ids = {
        candidate_id
        for field in spine["strongest_support"]
        for candidate_id in field.get("candidate_card_ids", [])
    }
    default_ids = set(spine["default_answer"].get("candidate_card_ids", []))

    assert "ec1" in support_ids
    assert "ec1" in default_ids


def test_projection_adds_high_relevance_section_supplements() -> None:
    spine = {
        "schema_id": "canonical_decision_spine_v1",
        "decision_question": "Should the option be adopted?",
        "status": "ready",
        "default_answer": {
            "field_id": "default_answer",
            "claim": "The option is supported by source-backed outcome evidence.",
            "role": "default_answer",
            "source_ids": ["s1"],
            "candidate_card_ids": ["ec1"],
            "claim_ids": ["c1"],
            "confidence": "medium",
        },
        "strongest_support": [
            {
                "field_id": "strongest_support_1",
                "claim": "The option improves the primary outcome.",
                "role": "support",
                "source_ids": ["s1"],
                "candidate_card_ids": ["ec1"],
                "claim_ids": ["c1"],
            }
        ],
        "strongest_counterevidence": [],
        "exception_answers": [],
        "dose_or_intensity_boundaries": [],
        "population_boundaries": [],
        "mechanism_or_proxy_evidence": [],
        "comparator_or_substitution": [],
        "evidence_quality_limits": [],
        "missing_decision_slots": [],
    }
    scaffold = {
        "candidate_evidence_cards": {
            "cards": [
                {
                    "candidate_card_id": "ec1",
                    "claim": "The option improves the primary outcome.",
                    "source_ids": ["s1"],
                    "claim_ids": ["c1"],
                    "role": "support",
                    "decision_relevance_score": 8,
                    "inclusion_recommendation": "main_text",
                    "anchor_confidence": "exact",
                    "section_candidates": ["Evidence Carrying the Conclusion"],
                },
                {
                    "candidate_card_id": "ec2",
                    "claim": "A second anchored study reports an 18 percent improvement.",
                    "source_ids": ["s2"],
                    "claim_ids": ["c2"],
                    "role": "scope",
                    "evidence_roles": ["support", "scope", "quantity"],
                    "decision_relevance_score": 10,
                    "inclusion_recommendation": "main_text",
                    "anchor_confidence": "exact",
                    "section_candidates": ["Evidence Carrying the Conclusion"],
                    "quantity_values": ["18 percent"],
                },
            ]
        }
    }

    projection = build_section_projection_packets(spine, scaffold)
    evidence_section = next(
        section for section in projection["sections"] if section["section"] == "Evidence Carrying the Conclusion"
    )
    owned_ids = [row.get("candidate_card_id") for row in evidence_section["owned_evidence"]]

    assert "ec2" in owned_ids
    assert evidence_section["coverage_supplement_count"] == 1


def test_limit_section_can_use_telemetry_substitute_without_blocking_projection() -> None:
    spine = {
        "schema_id": "canonical_decision_spine_v1",
        "decision_question": "Should the option be adopted?",
        "status": "ready",
        "default_answer": {
            "field_id": "default_answer",
            "claim": "The option is supported by source-backed outcome evidence.",
            "role": "default_answer",
            "source_ids": ["s1"],
            "candidate_card_ids": ["ec1"],
            "claim_ids": ["c1"],
            "confidence": "medium",
        },
        "strongest_support": [
            {
                "field_id": "strongest_support_1",
                "claim": "The option is supported by source-backed outcome evidence.",
                "role": "support",
                "source_ids": ["s1"],
                "candidate_card_ids": ["ec1"],
                "claim_ids": ["c1"],
            }
        ],
        "strongest_counterevidence": [
            {
                "field_id": "strongest_counterevidence_1",
                "claim": "The option may have narrower-setting implementation risks.",
                "role": "counterweight",
                "source_ids": ["s1"],
                "candidate_card_ids": ["ec1"],
                "claim_ids": ["c1"],
            }
        ],
        "exception_answers": [
            {
                "field_id": "exception_answer_1",
                "claim": "Narrower settings may require caution.",
                "role": "exception",
                "source_ids": ["s1"],
                "candidate_card_ids": ["ec1"],
                "claim_ids": ["c1"],
            }
        ],
        "dose_or_intensity_boundaries": [],
        "population_boundaries": [
            {
                "field_id": "population_boundary_1",
                "claim": "The evidence applies to the mapped population.",
                "role": "scope",
                "source_ids": ["s1"],
                "candidate_card_ids": ["ec1"],
                "claim_ids": ["c1"],
            }
        ],
        "mechanism_or_proxy_evidence": [
            {
                "field_id": "mechanism_proxy_1",
                "claim": "Outcome evidence is more decision-relevant than proxy evidence.",
                "role": "mechanism_or_proxy",
                "source_ids": ["s1"],
                "candidate_card_ids": ["ec1"],
                "claim_ids": ["c1"],
            }
        ],
        "comparator_or_substitution": [],
        "evidence_quality_limits": [],
        "missing_decision_slots": [],
        "canonical_decision_spine_validation": {"status": "valid"},
        "construction_report": {"candidate_card_count": 1, "source_anchor_count": 1},
    }
    scaffold = {
        "candidate_evidence_cards": {
            "cards": [
                {
                    "candidate_card_id": "ec1",
                    "claim": "The option is supported by source-backed outcome evidence.",
                    "source_ids": ["s1"],
                    "claim_ids": ["c1"],
                }
            ]
        }
    }

    projections = build_section_projection_packets(spine, scaffold)
    readiness = build_section_projection_readiness_report(projections)
    limits = next(section for section in projections["sections"] if section["section"] == "Limits of the Current Map")

    assert limits["context_status"] == "ready"
    assert limits["telemetry_context"]
    assert readiness["status"] in {"ready", "warning"}


def test_spine_default_does_not_store_instruction_text_when_cards_exist() -> None:
    scaffold = _scaffold()
    scaffold["decision_synthesis_model"] = {"bottom_line": {}}
    scaffold["decision_model"]["default_answer"]["plain_language_instruction"] = "State the default as neutral under stated conditions."

    bundle = build_decision_spine_bundle(_candidate_map(), scaffold, question="Should the option be adopted?")

    assert not bundle["canonical_decision_spine"]["default_answer"]["claim"].lower().startswith("state ")
    assert bundle["canonical_decision_spine"]["default_answer"]["candidate_card_ids"]


def test_spine_does_not_use_title_like_claim_as_default_answer_carrier() -> None:
    scaffold = _scaffold()
    cards = scaffold["candidate_evidence_cards"]["cards"]
    cards[0]["candidate_card_id"] = "title_card"
    cards[0]["role"] = "support"
    cards[0]["claim"] = "Cardiovascular Harm From Intervention: More Than One Mechanism."
    cards[0]["source_excerpt"] = cards[0]["claim"]
    cards[0]["decision_relevance_score"] = 10
    cards[1]["candidate_card_id"] = "substantive_card"
    cards[1]["role"] = "scope"
    cards[1]["claim"] = "CONCLUSIONS: The intervention was not associated with higher adverse-event risk in the available source-backed cohort."
    cards[1]["source_excerpt"] = cards[1]["claim"]
    cards[1]["decision_relevance_score"] = 8
    scaffold["decision_synthesis_model"] = {
        "bottom_line": {
            "classification": "neutral_or_low_concern_under_stated_conditions",
            "current_read": "State the default as neutral under stated conditions.",
            "why_this_frame": "The strongest support is source-backed while the evidence remains bounded.",
        }
    }

    bundle = build_decision_spine_bundle(_candidate_map(), scaffold, question="Should the option be adopted?")
    spine = bundle["canonical_decision_spine"]

    assert "title_card" not in spine["default_answer"]["candidate_card_ids"]
    assert spine["default_answer"]["candidate_card_ids"][0] == "substantive_card"
    assert "neutral or low concern" in spine["default_answer"]["claim"]
    assert all("Cardiovascular Harm From Intervention" not in row["claim"] for row in spine["strongest_support"])
    assert spine["strongest_support"][0]["candidate_card_ids"] == ["substantive_card"]


def test_section_packet_prefers_canonical_projection_when_present() -> None:
    bundle = build_decision_spine_bundle(_candidate_map(), _scaffold(), question="Should the option be adopted?")
    contract = {
        "_section_synthesis_scaffold": {
            "section_projection_packets": bundle["section_projection_packets"],
            "section_context_decision_packets": bundle["section_context_decision_packets"],
        },
        "section_synthesis_packet": {},
        "required_evidence": [],
        "evidence_references": [],
        "owned_elsewhere_evidence": [],
    }

    packet = compile_model_section_packet("Why This Read", contract)

    assert packet["context_source"] == "section_context_decision_packet"
    assert packet["owned_evidence"]
    assert packet["owned_evidence"][0]["reason_for_inclusion"]
    assert packet["owned_evidence"][0]["section_use"]
    assert packet["owned_evidence"][0]["slot_status"]
    assert packet["section_reasoning_contract"]["owned_card_ids"]


def test_reconciliation_keeps_rejected_comparator_contextual_not_load_bearing() -> None:
    scaffold = {
        "candidate_evidence_cards": {
            "cards": [
                {
                    "candidate_card_id": "ec_comp",
                    "claim": "The intervention was compared with a lower-intensity alternative in a narrow subgroup.",
                    "source_ids": ["s1"],
                    "source_card_ids": ["sc1"],
                    "claim_ids": ["c1"],
                    "quality": "indirect",
                    "inclusion_recommendation": "appendix_only",
                }
            ]
        }
    }
    spine = {
        "comparator_or_substitution": [
            {
                "field_id": "comparator_substitution_1",
                "role": "comparator_or_substitution",
                "candidate_card_ids": ["ec_comp"],
                "claim": "The intervention was compared with a lower-intensity alternative.",
                "source_ids": ["s1"],
            }
        ],
        "missing_decision_slots": [
            {
                "field_id": "missing_comparator_substitution",
                "slot_id": "comparator_substitution",
                "role": "missing_slot",
                "claim": "The map lacks clean comparator evidence.",
            }
        ],
    }
    audit = {
        "slots": [
            {
                "slot_id": "comparator_substitution",
                "label": "Comparator or substitution",
                "status": "missing",
                "required": True,
                "missing_message": "The map lacks clean comparator evidence.",
                "rejected_candidate_cards": [
                    {
                        "candidate_card_id": "ec_comp",
                        "rejection_reasons": ["appendix_only_candidate", "off_question_risk"],
                    }
                ],
            }
        ]
    }
    projection = {
        "sections": [
            {
                "section": "Practical Read",
                "section_thesis": "Old first-card summary.",
                "decision_move": "Translate the answer into practical decision implications.",
                "context_status": "ready",
                "owned_evidence": [
                    {
                        "candidate_card_id": "ec_comp",
                        "spine_field_id": "comparator_substitution_1",
                        "claim": "The intervention was compared with a lower-intensity alternative in a narrow subgroup.",
                        "intended_role": "comparator_or_substitution",
                    }
                ],
            }
        ]
    }

    reconciliation = build_slot_reconciliation_report(spine, audit, scaffold)
    packets = build_section_context_decision_packets(projection, reconciliation, scaffold)
    quality = build_section_context_quality_report(packets)
    card = packets["sections"][0]["owned_evidence"][0]

    assert card["slot_status"] == "mention_only"
    assert "load-bearing" in card["how_not_to_use"]
    assert card["reason_for_inclusion"]
    assert packets["sections"][0]["section_thesis"].startswith("Translate the answer")
    assert quality["sections"][0]["missing_reason_count"] == 0


def test_final_validation_flags_decision_brief_drift_from_canonical_spine() -> None:
    bundle = build_decision_spine_bundle(_candidate_map(), _scaffold(), question="Should the option be adopted?")
    scaffold = {**_scaffold(), **bundle}
    rendered = (
        "## Decision Brief\n\n"
        "**Decision question:** Should the option be adopted?\n\n"
        "Reject the option because unrelated cost concerns dominate.\n\n"
        "**Confidence:** medium\n\n"
        "## Evidence Roles\n\n### Main Support\n\n- Evidence.\n"
    )

    report = validate_briefing_against_scaffold(rendered, scaffold, _candidate_map())

    assert any(issue["issue_type"] == "canonical_default_answer_not_visible" for issue in report["issues"])


def test_final_validation_fails_when_spine_projection_not_ready() -> None:
    bundle = build_decision_spine_bundle(_candidate_map(), _scaffold(), question="Should the option be adopted?")
    scaffold = {
        **_scaffold(),
        **bundle,
        "section_projection_readiness_report": {"status": "not_synthesis_ready"},
    }

    report = validate_briefing_against_scaffold("## Decision Brief\n\nUse it.\n\n## Evidence Roles\n\n- Evidence.", scaffold, _candidate_map())

    assert report["status"] == "fails_contract"
    assert any(issue["issue_type"] == "spine_projection_not_synthesis_ready" for issue in report["issues"])


def test_model_spine_arbitration_accepts_only_existing_field_ids(monkeypatch) -> None:
    spine = build_decision_spine_bundle(_candidate_map(), _scaffold(), question="Should the option be adopted?")["canonical_decision_spine"]

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0, response_schema=None):
        return ModelBackendResult(
            text='{"default_answer_field_id":"default_answer","support_field_ids":["strongest_support_1"],"counterevidence_field_ids":[],"boundary_field_ids":[],"rationale":"Default and support are source-backed."}',
            backend=backend,
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_spine_arbitration.run_model_backend", fake_backend)

    result = arbitrate_canonical_decision_spine(spine, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["status"] == "accepted"
    assert result["spine"]["model_arbitration"]["support_field_ids"] == ["strongest_support_1"]


def test_model_spine_arbitration_accepts_grounded_default_answer_claim(monkeypatch) -> None:
    spine = build_decision_spine_bundle(_candidate_map(), _scaffold(), question="Should the option be adopted?")["canonical_decision_spine"]

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0, response_schema=None):
        return ModelBackendResult(
            text=(
                '{"default_answer_field_id":"default_answer",'
                '"default_answer_claim":"The option should be adopted as a bounded default because available evidence reports improved primary outcomes while implementation risks remain possible in narrower settings.",'
                '"support_field_ids":["strongest_support_1"],'
                '"counterevidence_field_ids":["strongest_counterevidence_1"],'
                '"boundary_field_ids":[],'
                '"rationale":"The answer uses the listed support and counterevidence fields."}'
            ),
            backend=backend,
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_spine_arbitration.run_model_backend", fake_backend)

    result = arbitrate_canonical_decision_spine(spine, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["status"] == "accepted"
    assert "accepted_default_answer_claim" in result["spine"]["model_arbitration"]
    assert result["spine"]["default_answer"]["claim"].startswith("The option should be adopted as a bounded default")
    assert result["spine"]["default_answer"]["candidate_card_ids"]


def test_model_spine_arbitration_rejects_invented_field_ids(monkeypatch) -> None:
    spine = build_decision_spine_bundle(_candidate_map(), _scaffold(), question="Should the option be adopted?")["canonical_decision_spine"]

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0, response_schema=None):
        return ModelBackendResult(
            text='{"default_answer_field_id":"invented_field","support_field_ids":[],"counterevidence_field_ids":[],"boundary_field_ids":[],"rationale":"Bad id."}',
            backend=backend,
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_spine_arbitration.run_model_backend", fake_backend)

    result = arbitrate_canonical_decision_spine(spine, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["status"] == "rejected_invalid_ids"
    assert "model_arbitration" not in result["spine"]


def _candidate_map() -> dict:
    return {
        "claims": [
            {"claim_id": "c1", "claim": "The option improves the primary outcome in the available evidence.", "source_ids": ["s1"]},
            {"claim_id": "c2", "claim": "Available evidence reports improved primary outcomes for the option.", "source_ids": ["s2"]},
            {"claim_id": "c3", "claim": "The option may create implementation risks in narrower settings.", "source_ids": ["s3"]},
        ],
        "relations": [
            {"source_claim": "c1", "target_claim": "c3", "relation_type": "in_tension_with"},
            {"source_claim": "c1", "target_claim": "c2", "relation_type": "supports"},
        ],
    }


def _scaffold() -> dict:
    return {
        "question": "Should the option be adopted?",
        "source_display_names": {"s1": "Trial A", "s2": "Review B", "s3": "Field C"},
        "decision_model": {
            "default_answer": {
                "plain_language_instruction": "Adopt the option only as a bounded default.",
                "confidence_cap": "medium",
            }
        },
        "decision_synthesis_model": {
            "bottom_line": {"current_read": "The source packet supports a bounded adoption read."}
        },
        "candidate_evidence_cards": {
            "cards": [
                {
                    "candidate_card_id": "ec1",
                    "source_card_ids": ["sc1"],
                    "claim_ids": ["c1"],
                    "source_ids": ["s1"],
                    "source_titles": ["Trial A"],
                    "claim": "The option improves the primary outcome in the available evidence.",
                    "source_excerpt": "The option improves the primary outcome.",
                    "role": "support",
                    "decision_relevance_score": 9,
                    "quality": "usable",
                    "inclusion_recommendation": "main_text",
                    "section_candidates": ["Why This Read", "Evidence Carrying the Conclusion", "Practical Read"],
                    "quantity_values": ["12%"],
                    "anchor_confidence": "exact",
                },
                {
                    "candidate_card_id": "ec2",
                    "source_card_ids": ["sc2"],
                    "claim_ids": ["c2"],
                    "source_ids": ["s2"],
                    "source_titles": ["Review B"],
                    "claim": "Available evidence reports improved primary outcomes for the option.",
                    "source_excerpt": "Evidence reports improved outcomes.",
                    "role": "support",
                    "decision_relevance_score": 8,
                    "quality": "usable",
                    "inclusion_recommendation": "main_text",
                    "section_candidates": ["Why This Read", "Evidence Carrying the Conclusion"],
                    "anchor_confidence": "exact",
                },
                {
                    "candidate_card_id": "ec3",
                    "source_card_ids": ["sc3"],
                    "claim_ids": ["c3"],
                    "source_ids": ["s3"],
                    "source_titles": ["Field C"],
                    "claim": "The option may create implementation risks in narrower settings.",
                    "source_excerpt": "Implementation risks were visible in narrower settings.",
                    "role": "counterweight",
                    "decision_relevance_score": 7,
                    "quality": "usable",
                    "inclusion_recommendation": "main_text",
                    "section_candidates": ["Decision Cruxes", "Practical Scope and Exceptions"],
                    "limitations": ["narrower setting"],
                    "anchor_confidence": "exact",
                },
            ]
        },
        "curated_evidence_packets": {
            "packets": [
                {
                    "concept": "default_population",
                    "rows": [
                        {
                            "source": "Trial A",
                            "claim": "The option improves the primary outcome in the available evidence.",
                            "section": "main_support",
                            "weight": "high",
                            "score": 8,
                            "decision_concepts": ["default_population"],
                        }
                    ],
                }
            ]
        },
        "evidence_weighting_ledger": {
            "all_evidence": [
                {
                    "claim_id": "c1",
                    "claim": "The option improves the primary outcome in the available evidence.",
                    "section": "main_support",
                    "score": 8,
                    "evidence_family": "outcome",
                    "decision_concepts": ["default_population"],
                },
                {
                    "claim_id": "c3",
                    "claim": "The option may create implementation risks in narrower settings.",
                    "section": "conflicting_evidence",
                    "score": 7,
                    "evidence_family": "implementation",
                    "decision_concepts": ["setting_or_context"],
                },
            ]
        },
        "quantity_ledger": {
            "quantities": [
                {"normalized": "12%", "source_id": "s1"},
                {"normalized": "3 months", "source_id": "s3"},
            ]
        },
        "source_sufficiency_report": {
            "status": "sufficient_for_bounded_answer",
            "missing_source_categories": [],
        },
    }
