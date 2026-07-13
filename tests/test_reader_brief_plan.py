from __future__ import annotations

from epistemic_case_mapper.map_briefing_reader_brief_plan import build_reader_brief_plan


def test_reader_brief_plan_builds_rhetorical_jobs_from_writer_context() -> None:
    context = {
        "bottom_line": "Option A is supported but bounded.",
        "answer_frame": {"direct_answer": "Adopt option A with monitoring.", "confidence_basis": "Outcome evidence is strongest."},
        "decision_evidence_table": [
            {"role": "strongest_support", "claim": "Option A reduced losses.", "source_id": "support", "quantities": [{"value": "25%", "interpretation": "loss reduction"}]},
            {"role": "strongest_counterweight", "claim": "Operating costs may erase benefits.", "source_id": "risk"},
        ],
        "mandatory_evidence_ledger": [
            {"role": "scope_boundary", "claim": "Evidence applies to river cities.", "source_id": "scope"}
        ],
        "decision_interpretation_plan": {
            "interpretations": [
                {
                    "item_id": "support",
                    "reader_use": "main_reason",
                    "answer_effect": "supports_default_answer",
                    "decision_interpretation": "Use this as the main reason the answer follows.",
                    "quantity_meanings": [{"value": "25%", "meaning": "large enough to matter"}],
                    "source_id": "support",
                },
                {
                    "item_id": "risk",
                    "reader_use": "counterweight_disposition",
                    "answer_effect": "tests_or_weakens_default_answer",
                    "decision_interpretation": "Use this to explain the main caution.",
                },
            ]
        },
        "practical_implications": ["Adopt only where monitoring is feasible."],
    }

    plan = build_reader_brief_plan(context)

    assert plan["schema_id"] == "reader_brief_plan_v2"
    assert plan["opening_answer"] == "Adopt option A with monitoring."
    assert plan["why_sentence"] == "Outcome evidence is strongest."
    assert plan["paragraph_jobs"][1]["section"] == "why_this_read"
    assert plan["paragraph_jobs"][1]["use_interpretations"][0]["item_id"] == "support"
    assert plan["paragraph_jobs"][2]["use_interpretations"][0]["decision_interpretation"] == "Use this to explain the main caution."
    assert plan["hero_evidence"][0]["source_id"] == "support"
    assert plan["hero_evidence"][0]["quantities"][0]["value"] == "25%"
    assert plan["caveats"][0]["claim"] == "Operating costs may erase benefits."
    assert plan["supporting_detail"][0]["claim"] == "Evidence applies to river cities."
    assert plan["practical_takeaway"] == "Adopt only where monitoring is feasible."
