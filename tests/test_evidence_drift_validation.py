from __future__ import annotations

from epistemic_case_mapper.evidence_drift_validation import evidence_drift_issues


def test_metric_prefixed_quantity_matches_source_sentence_inherited_metric() -> None:
    memo = "Replacement with unprocessed red meat (HR 1.10) or full-fat milk (HR 1.11) also showed increased risk."
    allowed = {
        "source_excerpt": (
            "We found a higher risk of cardiovascular disease when eggs were replaced with processed red meat "
            "(hazard ratio 1.15, 95% confidence interval 1.05 to 1.27), unprocessed red meat "
            "(1.10, 1.02 to 1.18), or full fat milk (1.11, 1.03 to 1.20)."
        )
    }

    assert evidence_drift_issues(memo, allowed, subject="briefing") == []


def test_metric_prefixed_quantity_matches_metric_after_value_variant() -> None:
    memo = "The bounded counterweight is HR 1.17 for the relevant dietary cholesterol contrast."
    allowed = {"quantities": [{"value": "1.17 (HR)", "interpretation": "Relative risk of incident CVD."}]}

    assert evidence_drift_issues(memo, allowed, subject="briefing") == []


def test_absent_metric_quantity_still_warns() -> None:
    memo = "The memo invents a very large unsupported estimate of HR 9.99."
    allowed = {"quantities": [{"value": "1.17 (HR)", "interpretation": "Relative risk of incident CVD."}]}

    issues = evidence_drift_issues(memo, allowed, subject="briefing")

    assert "briefing introduces unsupported quantity `hr 9.99`" in issues
