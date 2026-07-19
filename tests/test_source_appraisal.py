from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_context_curation import build_candidate_evidence_cards
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_appraisal import (
    appraisal_for_sources,
    build_source_appraisal_decision_grade_report,
    build_source_appraisal_report,
    run_source_caveat_appraisal,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_writer_packet import build_writer_packet


def test_source_appraisal_calibrates_generic_source_use() -> None:
    source_cards = {
        "schema_id": "source_evidence_cards_v1",
        "cards": [
            {
                "source_card_id": "sc1",
                "source_id": "observational_source",
                "source_title": "Large cohort study",
                "source_quote_or_excerpt": "A cohort reports lower event rates.",
                "anchor_confidence": "exact",
                "decision_relevance_score": 8,
                "evidence_type": "cohort observational study",
                "outcome_or_endpoint": "final outcome",
                "claim_ids": ["c1"],
            },
            {
                "source_card_id": "sc2",
                "source_id": "guidance_source",
                "source_title": "Official guidance",
                "source_quote_or_excerpt": "The guidance recommends a cautious default.",
                "anchor_confidence": "exact",
                "decision_relevance_score": 7,
                "evidence_type": "guideline advisory recommendation",
                "outcome_or_endpoint": "decision guidance",
                "claim_ids": ["c2"],
            },
            {
                "source_card_id": "sc3",
                "source_id": "surrogate_source",
                "source_title": "Randomized intervention trial",
                "source_quote_or_excerpt": "The intervention changed a biomarker.",
                "anchor_confidence": "exact",
                "decision_relevance_score": 7,
                "evidence_type": "randomized trial",
                "outcome_or_endpoint": "surrogate biomarker",
                "claim_ids": ["c3"],
            },
        ],
    }
    quality = {
        "schema_id": "evidence_quality_report_v1",
        "quality_components": {
            "sc1": {"directness": "direct", "overall": "usable"},
            "sc2": {"directness": "partial", "overall": "usable"},
            "sc3": {"directness": "direct", "overall": "usable"},
        },
    }

    report = build_source_appraisal_report(source_evidence_cards=source_cards, evidence_quality_report=quality)

    observational = appraisal_for_sources(report, ["observational_source"])
    assert "association_not_causation" in observational["source_use_warnings"]
    assert observational["allowed_wording"]["causal_language_allowed"] is False
    assert "observational evidence" in observational["allowed_wording"]["must_qualify_with"]

    guidance = appraisal_for_sources(report, ["guidance_source"])
    assert guidance["recommended_uses"] == ["decision_context_or_corroboration"]
    assert "guidance_not_independent_empirical_evidence" in guidance["source_use_warnings"]

    surrogate = appraisal_for_sources(report, ["surrogate_source"])
    assert surrogate["decision_directness"] == "partial"
    assert "indirect_endpoint" in surrogate["source_use_warnings"]


def test_candidate_cards_and_writer_packet_expose_source_appraisal() -> None:
    source_cards = {
        "schema_id": "source_evidence_cards_v1",
        "cards": [
            {
                "source_card_id": "sc1",
                "source_id": "s1",
                "source_title": "Cohort source",
                "source_quote_or_excerpt": "A cohort reports no clear increase in events.",
                "anchor_confidence": "exact",
                "decision_relevance_score": 9,
                "evidence_type": "cohort observational study",
                "outcome_or_endpoint": "final outcome",
                "supports_challenges_or_scopes": "supports",
                "claim_ids": ["c1"],
            }
        ],
    }
    quality = {
        "schema_id": "evidence_quality_report_v1",
        "quality_components": {"sc1": {"directness": "direct", "overall": "usable"}},
    }
    appraisal = build_source_appraisal_report(source_evidence_cards=source_cards, evidence_quality_report=quality)
    reconciliation = {
        "schema_id": "source_map_reconciliation_v1",
        "rows": [{"claim_id": "c1", "status": "source_backed"}],
    }

    candidates = build_candidate_evidence_cards(
        source_evidence_cards=source_cards,
        source_map_reconciliation=reconciliation,
        evidence_quality_report=quality,
        source_appraisal_report=appraisal,
        question="Should the intervention be treated as beneficial?",
    )

    card = candidates["cards"][0]
    assert card["source_appraisal"]["status"] == "ready"
    assert "association_not_causation" in card["source_use_warnings"]

    memo_ready_packet = {
        "decision_question": "Should the intervention be treated as beneficial?",
        "answer_spine": {"default_read": "Treat it as promising but not proven."},
        "source_trail": [{"source_id": "s1", "source_label": "Cohort source"}],
        "evidence_items": [
            {
                "item_id": "item_1",
                "role": "strongest_support",
                "reader_claim": "Cohort evidence is consistent with lower event risk.",
                "source_ids": ["s1"],
                "source_labels": ["Cohort source"],
                "source_appraisal": card["source_appraisal"],
                "source_use_warnings": card["source_use_warnings"],
                "allowed_wording": card["allowed_wording"],
                "quantities": [],
                "lineage": {},
            }
        ],
    }

    writer_packet = build_writer_packet(memo_ready_packet)

    unit = writer_packet["evidence_units"][0]
    assert unit["source_appraisal"]["status"] == "ready"
    assert unit["allowed_wording"]["causal_language_allowed"] is False
    assert writer_packet["writer_packet_quality_report"]["source_appraised_unit_count"] == 1
    assert "load_bearing_units_missing_source_appraisal" not in writer_packet["writer_packet_quality_report"]["issues"]

    decision_grade = build_source_appraisal_decision_grade_report(writer_packet)
    assert decision_grade["status"] == "improved_decision_grade_scaffold"
    assert decision_grade["decision_grade_handles"]["association_language_handles"] == 1


def test_model_caveat_appraisal_merges_into_source_use_report() -> None:
    source_cards = {
        "schema_id": "source_evidence_cards_v1",
        "cards": [
            {
                "source_card_id": "sc1",
                "source_id": "s1",
                "source_title": "Ambiguous evidence source",
                "source_quote_or_excerpt": "The report describes an endpoint that may be only indirectly connected.",
                "anchor_confidence": "exact",
                "decision_relevance_score": 8,
                "evidence_type": "other evidence",
                "outcome_or_endpoint": "endpoint",
                "claim_ids": ["c1"],
            }
        ],
    }
    quality = {
        "schema_id": "evidence_quality_report_v1",
        "quality_components": {"sc1": {"directness": "direct", "overall": "usable"}},
    }
    model_report = {
        "schema_id": "source_caveat_appraisal_report_v1",
        "appraisals": [
            {
                "source_id": "s1",
                "document_type": "empirical_study",
                "evidence_proximity": "primary",
                "decision_directness": "partial",
                "recommended_use": "load_bearing_with_qualification",
                "caveat_summary": "The endpoint is a surrogate, so outcome language should be qualified.",
                "interpretation_caveats": ["Treat the biomarker as indirect endpoint evidence."],
                "claim_scope_limits": ["Endpoint is indirect."],
                "model_appraised": True,
            }
        ],
    }

    report = build_source_appraisal_report(
        source_evidence_cards=source_cards,
        evidence_quality_report=quality,
        source_caveat_appraisal_report=model_report,
    )

    appraisal = appraisal_for_sources(report, ["s1"])
    assert "indirect_endpoint" in appraisal["source_use_warnings"]
    assert appraisal["allowed_wording"]["causal_language_allowed"] is False
    assert "Treat the biomarker as indirect endpoint evidence." in appraisal["interpretation_caveats"]


def test_source_caveat_appraisal_prompt_backend_emits_audit_artifacts() -> None:
    source_cards = {
        "schema_id": "source_evidence_cards_v1",
        "cards": [
            {
                "source_card_id": "sc1",
                "source_id": "s1",
                "source_title": "Guidance source",
                "source_quote_or_excerpt": "The advisory recommends caution.",
                "anchor_confidence": "exact",
                "decision_relevance_score": 7,
                "evidence_type": "guideline advisory",
                "claim_ids": ["c1"],
            }
        ],
    }
    quality = {
        "schema_id": "evidence_quality_report_v1",
        "quality_components": {"sc1": {"directness": "partial", "overall": "usable"}},
    }

    result = run_source_caveat_appraisal(
        source_evidence_cards=source_cards,
        evidence_quality_report=quality,
        backend="prompt",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["source_appraisal_packets"]["packets"][0]["source_id"] == "s1"
    assert result["source_caveat_appraisal_report"]["schema_id"] == "source_caveat_appraisal_report_v1"
    assert result["source_caveat_appraisal_run_report"]["status"] == "prompt_backend_scaffold"


def test_appraisal_lookup_matches_readable_source_label_aliases() -> None:
    report = {
        "schema_id": "source_appraisal_report_v1",
        "appraisals": [
            {
                "source_id": "nnr_2023_eggs_scoping_review",
                "source_label": "NNR 2023 Eggs Scoping Review",
                "appraisal_flags": ["synthesis_depends_on_included_sources"],
                "source_use_warnings": ["quality_limit"],
                "interpretation_caveats": ["Do not double count synthesis evidence."],
                "recommended_use": "corroborate_or_bound",
                "decision_directness": "partial",
            }
        ],
    }

    appraisal = appraisal_for_sources(report, ["Eggs - a scoping review for Nordic Nutrition Recommendations 2023"])

    assert appraisal["status"] == "ready"
    assert appraisal["recommended_uses"] == ["corroborate_or_bound"]
