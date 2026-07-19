from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_role_adjudication import adjudicate_packet_roles


def test_role_adjudication_does_not_infer_role_from_claim_text() -> None:
    packet = {
        "answer_frame": {"default_answer": "The default read is neutral because clear harm is not established."},
        "evidence_bundles": [
            {
                "bundle_id": "b1",
                "decision_role": "counterweight",
                "claim": "Studies have not generally supported an association between the exposure and worse outcomes.",
                "source_ids": ["s1"],
            }
        ],
    }

    updated, report = adjudicate_packet_roles(packet)

    assert updated["evidence_bundles"][0]["decision_role"] == "counterweight"
    assert report["status"] == "unchanged"
    assert report["applied_count"] == 0
    assert report["applied_role_updates"] == []
    assert report["role_conflict_candidates"] == []
    assert "does not infer or recommend semantic roles from text" in report["semantic_boundary"]


def test_role_adjudication_reports_explicit_metadata_conflict_without_relabeling() -> None:
    packet = {
        "answer_frame": {"default_answer": "Option A is promising in the default case."},
        "evidence_bundles": [
            {
                "bundle_id": "b1",
                "decision_role": "strongest_support",
                "evidence_role": "counterweight",
                "claim": "The result only applies when implementation capacity is already present.",
                "source_ids": ["s1"],
            }
        ],
    }

    updated, report = adjudicate_packet_roles(packet)

    assert updated["evidence_bundles"][0]["decision_role"] == "strongest_support"
    assert report["status"] == "report_only_warning"
    assert report["applied_count"] == 0
    assert report["role_conflict_candidates"][0]["current_role"] == "strongest_support"
    assert "recommended_role" not in report["role_conflict_candidates"][0]
    assert report["role_conflict_candidates"][0]["conflict_types"] == ["explicit_support_counterweight_label_conflict"]


def test_role_adjudication_reports_role_directionality_contract_mismatch() -> None:
    packet = {
        "answer_frame": {"default_answer": "The default read is neutral for moderate use."},
        "evidence_bundles": [
            {
                "bundle_id": "b1",
                "decision_role": "strongest_support",
                "directionality": "challenges",
                "claim": "Moderate use is not associated with increased risk in the general population.",
                "source_ids": ["s1"],
            }
        ],
    }

    updated, report = adjudicate_packet_roles(packet)

    assert updated["evidence_bundles"][0]["decision_role"] == "strongest_support"
    assert report["applied_count"] == 0
    assert report["role_conflict_candidates"][0]["expected_directionality_for_current_role"] == "supports"
    assert report["role_conflict_candidates"][0]["conflict_types"] == ["role_directionality_contract_mismatch"]


def test_role_adjudication_allows_semantically_surprising_but_internally_consistent_claim() -> None:
    packet = {
        "answer_frame": {"default_answer": "The default read is neutral for moderate use."},
        "evidence_bundles": [
            {
                "bundle_id": "b1",
                "decision_role": "strongest_support",
                "claim": "Moderate use is not associated with increased risk in the general population.",
                "source_ids": ["s1"],
            }
        ],
    }

    updated, report = adjudicate_packet_roles(packet)

    assert updated["evidence_bundles"][0]["decision_role"] == "strongest_support"
    assert report["applied_count"] == 0
    assert report["role_conflict_candidates"] == []
