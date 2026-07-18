from __future__ import annotations

from epistemic_case_mapper.evidence_bundles import (
    bundle_reconciliation_report,
    collect_assertion_bundles,
    normalize_assertion_bundles,
    semantic_realization_report,
)


def test_normalize_assertion_bundles_creates_stable_source_bound_identity() -> None:
    rows = normalize_assertion_bundles(
        [
            {
                "value": "RR 1.17 (95% CI 1.08 to 1.27)",
                "quantity_role": "effect_estimate",
                "measures": "cardiovascular disease",
                "local_interpretation": "Higher exposure was associated with higher cardiovascular disease risk.",
            }
        ],
        claim_id="c001",
        source_id="src001",
        source_span="lines 10-12",
        source_quote="Higher exposure was associated with RR 1.17 (95% CI 1.08 to 1.27).",
        claim_text="Higher exposure was associated with higher cardiovascular disease risk.",
    )

    assert len(rows) == 1
    bundle = rows[0]
    assert bundle["schema_id"] == "source_assertion_bundle_v1"
    assert bundle["evidence_bundle_id"].startswith("bundle_")
    assert bundle["claim_id"] == "c001"
    assert bundle["source_ids"] == ["src001"]
    assert bundle["source_span"] == "lines 10-12"
    assert bundle["estimate"] == "1.17"
    assert bundle["interval"] == "95% CI 1.08 to 1.27"
    assert bundle["statistic_type"] == "relative_risk"
    assert bundle["endpoint"] == "cardiovascular disease"


def test_semantic_realization_report_flags_quantity_distortion() -> None:
    bundles = normalize_assertion_bundles(
        [
            {
                "value": "RR 1.03 (95% CI 0.96 to 1.10)",
                "quantity_role": "effect_estimate",
                "measures": "mortality",
                "local_interpretation": "The interval crosses the null.",
            }
        ],
        claim_id="c002",
        source_id="src002",
        claim_text="Observed cohort association for mortality.",
    )

    report = semantic_realization_report(
        "The study reported HR 1.03 and a clear increase in mortality.",
        bundles,
    )

    assert report["status"] == "warning"
    codes = {issue["code"] for issue in report["issues"]}
    assert "statistic_swap_rr_as_hr" in codes
    assert "detached_or_missing_interval" in codes
    assert "null_crossing_interval_overstated" in codes


def test_bundle_reconciliation_report_indexes_nested_bundles_and_selected_ids() -> None:
    bundle = {
        "schema_id": "source_assertion_bundle_v1",
        "evidence_bundle_id": "bundle_demo_001",
        "value": "RR 1.03 (95% CI 0.96 to 1.10)",
        "estimate": "1.03",
        "interval": "95% CI 0.96 to 1.10",
        "statistic_type": "relative_risk",
        "endpoint": "mortality",
        "source_ids": ["src002"],
    }
    packet = {"evidence_items": [{"item_id": "E1", "assertion_bundles": [bundle]}]}

    assert collect_assertion_bundles(packet)[0]["evidence_bundle_id"] == "bundle_demo_001"

    report = bundle_reconciliation_report(
        memo="The memo reports HR 1.03 and a clear increase in mortality.",
        packet=packet,
        selected_bundle_ids=["bundle_demo_001", "missing_bundle"],
    )

    assert report["status"] == "warning"
    assert report["known_bundle_count"] == 1
    assert report["unknown_selected_bundle_ids"] == ["missing_bundle"]
    codes = {issue["code"] for issue in report["realization_report"]["issues"]}
    assert "statistic_swap_rr_as_hr" in codes


def test_duration_ranges_are_not_treated_as_missing_confidence_intervals() -> None:
    bundles = normalize_assertion_bundles(
        [
            {
                "value": "6 to 12 months",
                "quantity_role": "population_descriptor",
                "quantity_type": "duration",
                "measures": "age range",
            }
        ],
        claim_id="c003",
        source_id="src003",
    )

    assert "interval" not in bundles[0]
    report = semantic_realization_report("The guideline applies to infants 6 to 12 months old.", bundles)
    assert report["status"] == "pass"
