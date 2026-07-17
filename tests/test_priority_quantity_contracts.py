from __future__ import annotations

from epistemic_case_mapper.map_briefing_priority_quantity_contracts import (
    build_priority_quantity_contract_coverage_report,
    build_priority_quantity_contracts,
    contracts_for_evidence_ids,
)
from epistemic_case_mapper.map_briefing_memo_ready_prompt import build_memo_ready_section_synthesis_plan


def test_priority_quantity_contracts_use_analyst_relevance_and_numeric_terms() -> None:
    packet = {
        "evidence_items": [
            {
                "item_id": "e1",
                "reader_claim": "Moderate use is not associated with higher incident risk.",
                "role": "answer_anchor",
                "obligation_level": "must_include",
                "source_ids": ["s1"],
                "quantities": [
                    {
                        "value": "0.93",
                        "interpretation": "hazard ratio",
                        "must_retain": True,
                        "analyst_quantity_relevance": {
                            "quantity_role": "decision_anchor",
                            "retention_phrase": "hazard ratio 0.93",
                            "rationale": "Calibrates the primary answer.",
                        },
                    }
                ],
                "must_preserve_terms": [
                    "95% confidence interval 0.82 to 1.05",
                    "observational evidence",
                ],
            }
        ]
    }

    contracts = build_priority_quantity_contracts(packet)
    rows = contracts["rows"]

    assert contracts["schema_id"] == "priority_quantity_contracts_v1"
    assert [row["evidence_id"] for row in rows] == ["e1", "e1"]
    assert "hazard ratio 0.93" in [row["quantity_text"] for row in rows]
    assert "95% confidence interval 0.82 to 1.05" in [row["quantity_text"] for row in rows]
    assert rows[0]["required_if_claim_used"] is True
    assert rows[0]["decision_role"] == "risk_estimate"


def test_priority_quantity_contracts_exclude_background_noise() -> None:
    packet = {
        "evidence_items": [
            {
                "item_id": "background",
                "reader_claim": "Background context mentions several statistics.",
                "role": "background",
                "memo_function": "background",
                "obligation_level": "should_include",
                "must_preserve_terms": ["relative risk 0.92", "I2=44.8%"],
            },
            {
                "item_id": "boundary",
                "reader_claim": "Subgroup risk bounds the answer.",
                "role": "scope_boundary",
                "obligation_level": "should_include",
                "must_preserve_terms": ["pooled relative risk 1.25 (95% confidence interval 0.99 to 1.59)"],
            },
        ]
    }

    contracts = build_priority_quantity_contracts(packet)

    assert [row["evidence_id"] for row in contracts["rows"]] == ["boundary"]
    assert "1.25" in contracts["rows"][0]["quantity_text"]


def test_priority_quantity_contracts_do_not_promote_secondary_must_preserve_quantity_groups() -> None:
    packet = {
        "evidence_items": [
            {
                "item_id": "e1",
                "reader_claim": "The biomarker ratio bounds the answer.",
                "role": "counterweight",
                "obligation_level": "should_include",
                "quantities": [
                    {
                        "value": "0.14",
                        "interpretation": "mean difference of 0.14",
                        "must_retain": True,
                        "analyst_quantity_relevance": {
                            "quantity_role": "biomarker_calibration",
                            "retention_phrase": "mean difference of 0.14",
                        },
                    }
                ],
                "must_preserve_terms": [
                    "LDL-c/HDL-c ratio",
                    "MD = 0.14",
                    "95% CI: 0.05 to 0.22",
                    "healthy subjects",
                    "LDL-c",
                    "MD = 8.14",
                    "95% CI: 4.46 to 11.82",
                ],
            }
        ]
    }

    contracts = build_priority_quantity_contracts(packet)
    quantities = [row["quantity_text"] for row in contracts["rows"]]

    assert "MD = 0.14" in quantities
    assert "95% CI: 0.05 to 0.22" in quantities
    assert "MD = 8.14" not in quantities
    assert "95% CI: 4.46 to 11.82" not in quantities


def test_priority_quantity_contracts_can_be_filtered_by_evidence_id() -> None:
    contracts = {
        "rows": [
            {"evidence_id": "e1", "quantity_text": "25%"},
            {"evidence_id": "e2", "quantity_text": "10%"},
        ]
    }

    assert contracts_for_evidence_ids(contracts, ["e2"]) == [{"evidence_id": "e2", "quantity_text": "10%"}]


def test_priority_quantity_contract_coverage_accepts_equivalent_interval_wording() -> None:
    contracts = {
        "rows": [
            {"evidence_id": "e1", "quantity_text": "95% confidence interval 0.82 to 1.05"},
            {"evidence_id": "e2", "quantity_text": "hazard ratio 0.93"},
        ]
    }
    memo = "The estimate was a hazard ratio of 0.93 (95% CI 0.82-1.05)."

    report = build_priority_quantity_contract_coverage_report(memo, contracts)

    assert report["status"] == "ready"
    assert report["missing_contract_count"] == 0


def test_priority_quantity_contracts_are_routed_to_section_packets() -> None:
    packet = {
        "evidence_items": [
            {
                "item_id": "e1",
                "reader_claim": "Moderate use is neutral.",
                "role": "answer_anchor",
                "obligation_level": "must_include",
                "source_ids": ["s1"],
                "must_preserve_terms": ["hazard ratio 0.93 (95% confidence interval 0.82 to 1.05)"],
            },
            {
                "item_id": "e2",
                "reader_claim": "A boundary applies elsewhere.",
                "role": "scope_boundary",
                "obligation_level": "should_include",
                "source_ids": ["s2"],
                "must_preserve_terms": ["relative risk 1.25"],
            },
        ],
        "source_trail": [{"source_id": "s1"}, {"source_id": "s2"}],
        "canonical_decision_writer_packet": {
            "decision_question": "Should option A be treated as neutral?",
            "balanced_answer_frame": {"best_current_read": "Neutral in scope."},
            "evidence_weighted_argument_spine": {
                "section_plan": [
                    {
                        "section": "Why This Is the Best Current Read",
                        "owned_evidence_item_ids": ["e1"],
                        "owned_step_ids": ["step1"],
                    },
                    {
                        "section": "What Could Change or Bound the Answer",
                        "owned_evidence_item_ids": [],
                        "owned_step_ids": ["step2"],
                    }
                ],
                "steps": [
                    {
                        "step_id": "step1",
                        "primary_section": "Why This Is the Best Current Read",
                        "evidence_item_ids": ["e1"],
                        "point": "The main estimate supports neutrality.",
                    },
                    {
                        "step_id": "step2",
                        "primary_section": "What Could Change or Bound the Answer",
                        "evidence_item_ids": [],
                        "point": "Boundary evidence narrows the answer.",
                    }
                ],
            },
            "priority_evidence": [{"item_id": "e1", "claim": "Moderate use is neutral.", "source_ids": ["s1"]}],
        },
    }

    plan = build_memo_ready_section_synthesis_plan(packet)
    section = plan["sections"][0]

    assert section["packet"]["priority_quantity_contracts"][0]["evidence_id"] == "e1"
    assert "0.93" in section["packet"]["priority_quantity_contracts"][0]["quantity"]
    assert "relative risk 1.25" not in section["prompt"]
    assert "### Priority quantity contracts" in section["prompt"]
    assert "Use Priority quantity contracts" in section["prompt"]
    counterweight = next(row for row in plan["sections"] if row["section_id"] == "counterweights")
    assert "relative risk 1.25" in counterweight["prompt"]
