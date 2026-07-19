from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_quantity_slots import build_quantity_slot_report, build_quantity_slots


def test_quantity_slots_separate_effect_interval_sample_followup_and_dose() -> None:
    slots = build_quantity_slots(
        [
            {"value": "relative risk 0.98", "quantity_type": "effect_estimate"},
            {"value": "95% confidence interval 0.93 to 1.03", "quantity_type": "interval_or_estimate"},
            {"value": "1,720 participants", "quantity_type": "effect_estimate"},
            {"value": "32 years", "quantity_type": "effect_estimate"},
            {"value": "one unit per day", "quantity_type": "effect_estimate"},
        ]
    )

    assert slots["effect_estimate"][0]["value"] == "relative risk 0.98"
    assert slots["interval"][0]["value"].startswith("95% confidence")
    assert slots["sample_size"][0]["value"] == "1,720 participants"
    assert slots["follow_up"][0]["value"] == "32 years"
    assert slots["dose_or_exposure"][0]["value"] == "one unit per day"


def test_quantity_slot_report_flags_missing_slots() -> None:
    report = build_quantity_slot_report(
        {
            "evidence_items": [
                {
                    "item_id": "q1",
                    "role": "quantitative_anchor",
                    "quantities": [{"value": "25%", "quantity_type": "effect_estimate"}],
                }
            ]
        }
    )

    assert report["status"] == "warning"
    assert report["quantitative_anchor_missing_slots"] == ["q1"]
