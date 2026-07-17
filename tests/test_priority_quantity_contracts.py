from __future__ import annotations

from epistemic_case_mapper.map_briefing_priority_quantity_contracts import (
    build_priority_quantity_contract_coverage_report,
    build_priority_quantity_contracts,
    contracts_for_evidence_ids,
)


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
