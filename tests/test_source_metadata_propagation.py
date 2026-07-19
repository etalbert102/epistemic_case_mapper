from __future__ import annotations

from pathlib import Path

from epistemic_case_mapper.pipeline.briefing.map_briefing_context_reports import build_source_evidence_cards
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_appraisal import appraisal_for_sources, build_source_appraisal_report
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_appraisal_constraints import (
    constrain_source_hierarchy,
    source_constraints_from_context_rows,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_decision_model_global_tasks import (
    _source_weight_judgments_from_hierarchy,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_writer_packet import build_writer_packet
from epistemic_case_mapper.pipeline.map.source_metadata import build_source_metadata_bundle
from epistemic_case_mapper.schema import CaseManifest, Source


def test_manifest_metadata_and_independence_survive_into_source_appraisal(tmp_path: Path) -> None:
    metadata_path = tmp_path / "source_independence.md"
    metadata_path.write_text(
        "# Independence\n\n### Review cluster\n\n- `review_1`\n\n"
        "Risk: this review overlaps the primary studies and is not independent confirmation.\n",
        encoding="utf-8",
    )
    source = Source(
        source_id="review_1",
        title="Declared narrative review",
        source_type="narrative_review",
        provenance_level="peer_reviewed",
        evidence_role="context_and_synthesis",
    )
    manifest = CaseManifest(
        case_id="case_1",
        title="Case",
        question="What should be done?",
        case_type="test",
        evidence_mode="source_grounded",
        sources=[source],
        metadata_files=[metadata_path.name],
    )

    bundle = build_source_metadata_bundle(repo_root=tmp_path, case_manifest=manifest, sources=[source])
    source_metadata = bundle["source_by_id"]["review_1"]

    assert source_metadata["source_type"] == "narrative_review"
    assert source_metadata["independence_clusters"] == ["Review cluster"]
    assert "not independent confirmation" in source_metadata["independence_caveats"][0]

    candidate_map = {
        "sources": ["review_1"],
        "source_metadata": bundle["source_by_id"],
        "claims": [
            {
                "claim_id": "c1",
                "claim": "The review describes the evidence base.",
                "source_id": "review_1",
                "source_span": "lines 1-2",
                "excerpt": "The review describes the evidence base.",
                "entailed_by_excerpt": "yes",
                "decision_relevance_score": 8,
            }
        ],
    }
    cards = build_source_evidence_cards(candidate_map, source_lookup={})
    card = cards["cards"][0]
    assert card["source_title"] == "Declared narrative review"
    assert card["declared_source_type"] == "narrative_review"
    assert card["independence_caveats"]

    report = build_source_appraisal_report(
        source_evidence_cards=cards,
        evidence_quality_report={"quality_components": {"sc0001": {"directness": "direct", "overall": "usable"}}},
    )
    appraisal = report["appraisal_by_source_id"]["review_1"]
    assert appraisal["declared_source_type"] == "narrative_review"
    assert appraisal["recommended_use"] == "corroborate_or_bound"
    assert "independence_not_established" in appraisal["source_use_warnings"]
    assert "secondary_or_scoping_review" in appraisal["source_use_warnings"]


def test_unreviewed_manifest_provenance_cannot_be_load_bearing() -> None:
    source_cards = {
        "cards": [
            {
                "source_card_id": "sc1",
                "source_id": "local_1",
                "source_title": "Local note",
                "source_quote_or_excerpt": "The note recommends the option.",
                "source_metadata": {
                    "source_id": "local_1",
                    "source_type": "local_note",
                    "provenance_level": "local_note",
                    "needs_upgrade": True,
                },
                "anchor_confidence": "exact",
                "decision_relevance_score": 9,
            }
        ]
    }
    report = build_source_appraisal_report(
        source_evidence_cards=source_cards,
        evidence_quality_report={"quality_components": {"sc1": {"directness": "direct", "overall": "usable"}}},
    )

    appraisal = report["appraisal_by_source_id"]["local_1"]
    assert appraisal["recommended_use"] == "human_review_needed"
    assert "source_needs_upgrade" in appraisal["source_use_warnings"]
    assert "provenance_not_decision_grade" in appraisal["source_use_warnings"]

    packet = {
        "decision_question": "What should be done?",
        "answer_spine": {"default_read": "Use the option."},
        "source_trail": [{"source_id": "local_1", "source_label": "Local note"}],
        "evidence_items": [
            {
                "item_id": "item_1",
                "role": "strongest_support",
                "reader_claim": "The note recommends the option.",
                "source_ids": ["local_1"],
                "source_labels": ["Local note"],
                "source_appraisal": appraisal_for_sources(report, ["local_1"]),
                "source_use_warnings": appraisal["source_use_warnings"],
                "quantities": [],
            }
        ],
    }
    writer_packet = build_writer_packet(packet)
    quality = writer_packet["writer_packet_quality_report"]
    assert quality["status"] == "warning"
    assert quality["load_bearing_provenance_blocked"]
    assert "load_bearing_source_provenance_requires_review" in quality["issues"]


def test_global_source_hierarchy_cannot_promote_human_review_source() -> None:
    context = {
        "evidence_rows": [
            {
                "evidence_item_id": "item_1",
                "source_ids": ["local_1"],
                "source_quality": {
                    "recommended_uses": ["human_review_needed"],
                    "warnings": ["source_needs_upgrade", "independence_not_established"],
                    "interpretation_caveats": ["This source may overlap another source."],
                },
            }
        ]
    }
    hierarchy = {
        "schema_id": "source_weight_hierarchy_v1",
        "lanes": {
            "primary_answer_drivers": [
                {
                    "source_ids": ["local_1"],
                    "evidence_item_ids": ["item_1"],
                    "role": "answer driver",
                    "rationale": "The model proposed it as the driver.",
                }
            ],
            "contextual_sources": [],
        },
        "source_accounting": [
            {
                "source_id": "local_1",
                "primary_lane": "primary_answer_drivers",
                "rationale": "The model proposed it as the driver.",
            }
        ],
    }
    constraints = source_constraints_from_context_rows(context["evidence_rows"])

    constrained_hierarchy, constrained_report = constrain_source_hierarchy(
        hierarchy,
        {"status": "ready", "warnings": [], "primary_driver_source_count": 1},
        constraints,
    )
    judgments = _source_weight_judgments_from_hierarchy(
        context,
        constrained_hierarchy,
        source_constraints=constraints,
    )

    assert constrained_hierarchy["lanes"]["primary_answer_drivers"] == []
    assert constrained_hierarchy["lanes"]["contextual_sources"][0]["source_ids"] == ["local_1"]
    assert constrained_report["primary_driver_source_count"] == 0
    assert constrained_report["manifest_constrained_source_ids"] == ["local_1"]
    assert judgments[0]["main_use"] == "contextualizes"
    assert judgments[0]["confidence_effect"] == "neutral"
    assert "independence_not_established" in judgments[0]["source_appraisal_constraints"]
