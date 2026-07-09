from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing_packet_refinement import PacketCritiqueOutput
from epistemic_case_mapper.model_schemas import parse_model_output_report


def test_packet_critique_accepts_string_missing_decision_functions() -> None:
    raw = json.dumps(
        {
            "schema_id": "packet_critique_v1",
            "decision_adequate": False,
            "packet_sufficiency_judgment": "needs_repair",
            "missing_decision_functions": [
                "No clear mechanism is provided to weigh support against counterevidence."
            ],
            "missing_or_weak_cruxes": [
                {"description": "The crux is under-specified."}
            ],
            "section_plan_risks": [
                {"description": "Quantity interpretation may be overstated."}
            ],
        }
    )

    report = parse_model_output_report(raw, PacketCritiqueOutput)

    assert report["ok"] is True
    data = report["data"]
    assert data["missing_decision_functions"][0]["decision_function"].startswith("No clear mechanism")
    assert data["missing_or_weak_cruxes"] == ["The crux is under-specified."]
    assert data["section_plan_risks"] == ["Quantity interpretation may be overstated."]
