from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_quantity_retention import (
    contains_quantity,
    quantity_required_for_retention,
    quantity_retained,
    retention_quantity_rows,
)


def test_interval_quantity_requires_numeric_endpoints_not_interpretation_match() -> None:
    memo = "Moderate intake around one egg per day had a hazard ratio of 0.93."
    quantity = {
        "value": "0.82 to 1.05",
        "interpretation": "Confidence interval for the hazard ratio of one egg per day",
    }

    assert not quantity_retained(memo, quantity)


def test_interval_quantity_retained_when_endpoints_appear() -> None:
    memo = "Moderate intake had a hazard ratio of 0.93, with a 95% CI of 0.82 to 1.05."
    quantity = {
        "value": "0.82 to 1.05",
        "interpretation": "Confidence interval for the hazard ratio of one egg per day",
    }

    assert quantity_retained(memo, quantity)


def test_confidence_interval_text_retained_when_endpoints_appear_with_dash() -> None:
    memo = "The pooled estimate was imprecise: HR 0.93, confidence interval 0.82-1.05."
    quantity = {"value": "95% confidence interval 0.82 to 1.05"}

    assert quantity_retained(memo, quantity)


def test_frequency_quantity_still_uses_signature_matching() -> None:
    assert contains_quantity("The practical threshold is about one egg per day.", "1 egg/day")


def test_fractional_frequency_quantity_matches_word_form() -> None:
    assert contains_quantity("The estimate is reported for each additional half egg per day.", "0.5 egg/day")


def test_fractional_frequency_quantity_matches_generic_units() -> None:
    assert contains_quantity("The program added a quarter serving per week.", "0.25 serving/week")
    assert contains_quantity("The treatment added seven visits per month.", "7 visits/month")


def test_explicit_analyst_must_retain_overrides_lexical_quantity_heuristic() -> None:
    row = {
        "role": "strongest_support",
        "statement": "The source reports a hazard ratio, but the analyst judged it as trace-only here.",
        "quantities": [
            {
                "value": "HR 0.98",
                "interpretation": "hazard ratio for a secondary outcome",
                "must_retain": False,
                "analyst_quantity_relevance": {"memo_inclusion": "trace_only"},
            }
        ],
    }

    assert retention_quantity_rows(row) == []


def test_analyst_must_use_marks_quantity_mandatory_without_keyword_fallback() -> None:
    quantity = {
        "value": "0.14",
        "interpretation": "calibrates the size of the practical difference",
        "analyst_quantity_relevance": {"memo_inclusion": "must_use"},
    }

    assert quantity_required_for_retention(quantity, {"role": "strongest_support"}) is True


def test_quantity_retention_keeps_legacy_fallback_when_analyst_judgment_absent() -> None:
    quantity = {"value": "HR 0.98", "interpretation": "hazard ratio for main outcome"}

    assert quantity_required_for_retention(quantity, {"role": "strongest_support"}) is True
