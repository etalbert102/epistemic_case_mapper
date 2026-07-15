from __future__ import annotations

from epistemic_case_mapper.map_briefing_memo_ready_finalization import build_memo_ready_packet_retention_report
from epistemic_case_mapper.map_briefing_source_bound_evidence import build_source_bound_evidence_atoms


def test_source_bound_atoms_exclude_quantities_not_found_in_local_excerpt() -> None:
    rows = [
        {
            "item_id": "lipid_ratio",
            "claim": "Higher egg intake changed lipid markers.",
            "source_ids": ["li_2020"],
            "quantities": [
                {
                    "value": "MD = 8.14",
                    "interpretation": "Mean Difference of 8.14 in the LDL-c/HDL-c ratio",
                    "source_ids": ["li_2020"],
                    "source_excerpt": "The MEC group had a higher LDL-c/HDL-c ratio than control (MD = 0.14, p = 0.001).",
                },
                {
                    "value": "0.14",
                    "interpretation": "Mean difference in the LDL-c/HDL-c ratio",
                    "source_ids": ["li_2020"],
                    "source_excerpt": "The MEC group had a higher LDL-c/HDL-c ratio than control (MD = 0.14, p = 0.001).",
                },
            ],
        }
    ]

    atoms = build_source_bound_evidence_atoms(rows)

    assert atoms[0]["quantity_tuples"][0]["value"] == "0.14"
    assert atoms[0]["excluded_quantity_tuples"][0]["value"] == "MD = 8.14"
    assert atoms[0]["excluded_quantity_tuples"][0]["warning_type"] == "quantity_not_found_in_source_excerpt"


def test_retention_report_flags_quantity_without_bound_source_nearby() -> None:
    packet = {
        "source_trail": [
            {"source_id": "s1", "source_label": "Outcome Study"},
            {"source_id": "s2", "source_label": "Context Review"},
        ],
        "canonical_decision_writer_packet": {
            "mandatory_retention_checklist": [
                {
                    "statement": "Option A reduced losses by 25%.",
                    "source_ids": ["s1"],
                    "quantities": [
                        {
                            "value": "25%",
                            "interpretation": "loss reduction",
                            "source_ids": ["s1"],
                            "source_excerpt": "Option A reduced losses by 25%.",
                        }
                    ],
                }
            ]
        },
    }
    memo = "Option A reduced losses by 25% [s2]."

    report = build_memo_ready_packet_retention_report(memo, packet)

    binding = report["source_binding_report"]
    assert binding["quantity_source_adjacency_warning_count"] == 1
    assert binding["quantity_source_adjacency_warnings"][0]["quantity"] == "25%"
    assert binding["quantity_source_adjacency_warnings"][0]["expected_source_ids"] == ["s1"]


def test_retention_report_accepts_quantity_with_bound_source_nearby() -> None:
    packet = {
        "source_trail": [{"source_id": "s1", "source_label": "Outcome Study"}],
        "canonical_decision_writer_packet": {
            "mandatory_retention_checklist": [
                {
                    "statement": "Option A reduced losses by 25%.",
                    "source_ids": ["s1"],
                    "quantities": [
                        {
                            "value": "25%",
                            "interpretation": "loss reduction",
                            "source_ids": ["s1"],
                            "source_excerpt": "Option A reduced losses by 25%.",
                        }
                    ],
                }
            ]
        },
    }
    memo = "Option A reduced losses by 25% [s1]."

    report = build_memo_ready_packet_retention_report(memo, packet)

    assert report["source_binding_report"]["quantity_source_adjacency_warning_count"] == 0
