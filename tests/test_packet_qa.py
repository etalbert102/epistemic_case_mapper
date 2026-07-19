from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet import build_quality_synthesis_packet_bundle
from epistemic_case_mapper.pipeline.briefing.map_briefing_packet_qa import build_packet_qa_report

from test_decision_briefing_packet import _scaffold


def test_packet_qa_passes_clean_small_packet() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    bundle = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])

    report = bundle["packet_qa_report"]

    assert report["schema_id"] == "packet_qa_report_v1"
    assert report["summary"]["answer_frame_clean"] is True
    assert report["summary"]["truncated_claim_count"] == 0


def test_packet_qa_flags_stringified_answer_frame_and_missing_lineage() -> None:
    packet = {
        "answer_frame": {"default_answer": "{'classification': 'mixed', 'current_read': 'unclear'}"},
        "evidence_bundles": [
            {
                "bundle_id": "b1",
                "decision_role": "strongest_support",
                "claim": "The option reduces losses.",
            }
        ],
    }

    report = build_packet_qa_report(packet)
    check_ids = {check["check_id"] for check in report["checks"]}

    assert report["status"] == "warning"
    assert "answer_frame_not_plain_text" in check_ids
    assert "missing_source_lineage" in check_ids


def test_packet_qa_flags_generic_answer_frame_without_repairing_it() -> None:
    report = build_packet_qa_report(
        {
            "decision_question": "Should the city adopt option A for flood protection?",
            "answer_frame": {
                "default_answer": "The available evidence supports the default answer under stated conditions."
            },
            "evidence_bundles": [
                {
                    "bundle_id": "b1",
                    "claim": "Option A has a narrower but source-grounded benefit claim.",
                    "source_ids": ["s1"],
                }
            ],
        }
    )

    check_ids = {check["check_id"] for check in report["checks"]}

    assert report["status"] == "warning"
    assert report["summary"]["answer_frame_clean"] is False
    assert report["summary"]["generic_answer_frame_warning_count"] == 1
    assert "answer_frame_generic_or_artifact_language" in check_ids


def test_packet_qa_flags_clean_but_weak_answer_frame() -> None:
    report = build_packet_qa_report(
        {
            "decision_question": (
                "For generally healthy adults, should eggs be treated as meaningfully harmful, "
                "neutral, or beneficial in dietary advice?"
            ),
            "answer_frame": {
                "default_answer": "Evidence supports a neutral or low-concern default under the stated conditions."
            },
            "evidence_bundles": [
                {
                    "bundle_id": "b1",
                    "claim": "Moderate egg consumption was not associated with incident cardiovascular disease.",
                    "source_ids": ["s1"],
                }
            ],
        }
    )

    assert report["status"] == "warning"
    assert report["summary"]["answer_frame_clean"] is False
    assert any(check["check_id"] == "answer_frame_generic_or_artifact_language" for check in report["checks"])


def test_packet_qa_accepts_concrete_answer_frame() -> None:
    report = build_packet_qa_report(
        {
            "answer_frame": {
                "default_answer": (
                    "Option A is conditionally favorable when maintenance funding is protected "
                    "and flood exposure remains high."
                )
            },
            "evidence_bundles": [
                {
                    "bundle_id": "b1",
                    "claim": "Option A has a narrower but source-grounded benefit claim.",
                    "source_ids": ["s1"],
                }
            ],
        }
    )

    assert report["status"] == "pass"
    assert report["summary"]["answer_frame_clean"] is True
    assert report["summary"]["generic_answer_frame_warning_count"] == 0


def test_packet_qa_flags_role_dominance_weak_crux_and_quantity_blob() -> None:
    packet = {
        "answer_frame": {"default_answer": "Option A is conditionally favorable."},
        "evidence_bundles": [
            {
                "bundle_id": "b1",
                "decision_role": "decision_crux",
                "claim": "Maintenance failures in tension with budget savings.",
                "source_ids": ["s1"],
            }
        ],
    }
    memo_ready = {
        "evidence_items": [
            {
                "item_id": "q1",
                "role": "quantitative_anchor",
                "reader_claim": "Option A reduced losses.",
                "source_label": "Outcome Study",
                "quantities": [
                    {"value": "25%", "quantity_type": "effect_estimate"},
                    {"value": "95% CI 10 to 40", "quantity_type": "interval_or_estimate"},
                    {"value": "1,000 homes", "quantity_type": "sample_size"},
                    {"value": "10 years", "quantity_type": "duration"},
                ],
            },
            *[
                {
                    "item_id": f"c{i}",
                    "role": "strongest_counterweight",
                    "reader_claim": f"Counterweight {i}.",
                    "source_label": "Counter Study",
                }
                for i in range(8)
            ],
            {
                "item_id": "crux1",
                "role": "decision_crux",
                "reader_claim": "Maintenance failures in tension with budget savings.",
                "source_label": "Boundary Report",
            },
        ]
    }

    report = build_packet_qa_report(packet, memo_ready_packet=memo_ready)
    check_ids = {check["check_id"] for check in report["checks"]}

    assert "weak_or_topical_crux" in check_ids
    assert "unjustified_role_dominance" in check_ids
    assert "unstructured_quantity_blob" in check_ids


def test_packet_qa_flags_primary_bundle_with_low_question_fit() -> None:
    packet = {
        "decision_question": "Should the city adopt option A for flood protection?",
        "answer_frame": {"default_answer": "Option A is conditionally favorable when maintenance funding is protected."},
        "evidence_bundles": [
            {
                "bundle_id": "b_low_fit",
                "decision_role": "strongest_support",
                "claim": "Cancer screening participation increased in unrelated clinic settings.",
                "source_ids": ["s1"],
                "decision_relevance_assessment": {
                    "question_relevance_status": "low_question_overlap",
                    "question_overlap_count": 0,
                },
            }
        ],
    }

    report = build_packet_qa_report(packet)

    assert report["status"] == "warning"
    assert report["summary"]["primary_low_question_fit_warning_count"] == 1
    assert any(check["check_id"] == "primary_bundle_low_question_fit" for check in report["checks"])


def test_packet_qa_flags_truncated_claims() -> None:
    report = build_packet_qa_report(
        {
            "answer_frame": {"default_answer": "Option A is uncertain."},
            "evidence_bundles": [
                {"bundle_id": "b1", "claim": "The evidence shows benefit (approx.", "source_ids": ["s1"]}
            ],
        }
    )

    assert report["summary"]["truncated_claim_count"] == 1
