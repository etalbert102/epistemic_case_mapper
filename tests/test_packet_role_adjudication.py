from __future__ import annotations

from epistemic_case_mapper.map_briefing_role_adjudication import adjudicate_packet_roles


def test_role_adjudication_relabels_no_association_counterweight_as_support() -> None:
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

    assert updated["evidence_bundles"][0]["decision_role"] == "strongest_support"
    assert updated["evidence_bundles"][0]["directionality"] == "supports"
    assert report["applied_count"] == 1
    assert report["applied_role_updates"][0]["current_role"] == "counterweight"


def test_role_adjudication_relabels_conditional_support_as_scope_boundary() -> None:
    packet = {
        "answer_frame": {"default_answer": "Option A is promising in the default case."},
        "evidence_bundles": [
            {
                "bundle_id": "b1",
                "decision_role": "strongest_support",
                "claim": "The result only applies when implementation capacity is already present.",
                "source_ids": ["s1"],
            }
        ],
    }

    updated, report = adjudicate_packet_roles(packet)

    assert updated["evidence_bundles"][0]["decision_role"] == "scope_boundary"
    assert report["status"] == "changed"


def test_role_adjudication_does_not_flip_negated_support_with_risk_terms() -> None:
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
