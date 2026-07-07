from __future__ import annotations

from epistemic_case_mapper.map_briefing_classical_selection import build_classical_evidence_selection_report
from epistemic_case_mapper.map_briefing_section_input_compiler import compile_model_section_packet
from epistemic_case_mapper.map_briefing_spine_arbitration import arbitrate_canonical_decision_spine
from epistemic_case_mapper.map_briefing_spine_global_plan import attach_global_memo_plan
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
    assert bundle["section_projection_packets"]["sections"]
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


def test_spine_default_does_not_store_instruction_text_when_cards_exist() -> None:
    scaffold = _scaffold()
    scaffold["decision_synthesis_model"] = {"bottom_line": {}}
    scaffold["decision_model"]["default_answer"]["plain_language_instruction"] = "State the default as neutral under stated conditions."

    bundle = build_decision_spine_bundle(_candidate_map(), scaffold, question="Should the option be adopted?")

    assert not bundle["canonical_decision_spine"]["default_answer"]["claim"].lower().startswith("state ")
    assert bundle["canonical_decision_spine"]["default_answer"]["candidate_card_ids"]


def test_section_packet_prefers_canonical_projection_when_present() -> None:
    bundle = build_decision_spine_bundle(_candidate_map(), _scaffold(), question="Should the option be adopted?")
    contract = {
        "_section_synthesis_scaffold": {
            "section_projection_packets": bundle["section_projection_packets"],
        },
        "section_synthesis_packet": {},
        "required_evidence": [],
        "evidence_references": [],
        "owned_elsewhere_evidence": [],
    }

    packet = compile_model_section_packet("Why This Read", contract)

    assert packet["context_source"] == "canonical_spine_projection"
    assert packet["owned_evidence"]
    assert packet["section_reasoning_contract"]["owned_card_ids"]


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


def test_global_memo_plan_is_deprecated_when_spine_projections_are_ready() -> None:
    scaffold = {"section_projection_readiness_report": {"status": "ready"}}

    attach_global_memo_plan(scaffold, backend="prompt", backend_timeout=30, backend_retries=0)

    assert scaffold["global_memo_plan"]["status"] == "deprecated_by_canonical_spine"
    assert scaffold["global_memo_plan_prompt"].startswith("Skipped")


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
