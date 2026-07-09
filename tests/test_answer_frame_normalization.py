from __future__ import annotations

from epistemic_case_mapper.map_briefing_answer_frame import normalize_answer_frame
from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle

from test_decision_briefing_packet import _scaffold


def test_answer_frame_normalizes_stringified_dict() -> None:
    frame, report = normalize_answer_frame(
        canonical_decision_spine={"confidence": "medium", "default_answer": {"claim": "Fallback answer."}},
        argument_model={
            "proposed_answer": "{'classification': 'conditional', 'current_read': 'Option A is favored if maintenance is funded.'}"
        },
    )

    assert frame["default_answer"] == "Option A is favored if maintenance is funded."
    assert frame["classification"] == "conditional"
    assert report["status"] == "normalized_structured_text"
    assert report["changed"] is True


def test_answer_frame_recovers_current_read_from_malformed_text() -> None:
    frame, report = normalize_answer_frame(
        canonical_decision_spine={},
        argument_model={"proposed_answer": "{'classification': 'mixed', 'current_read': 'Use option A cautiously..."},
    )

    assert frame["default_answer"] == "Use option A cautiously..."
    assert report["status"] == "recovered_field_from_malformed_text"
    assert "{'classification'" not in frame["default_answer"]


def test_decision_packet_emits_clean_answer_frame_and_report() -> None:
    scaffold = _scaffold()
    scaffold["argument_model"]["proposed_answer"] = (
        "{'classification': 'conditional', 'current_read': 'Option A is favored when maintenance funding is protected.'}"
    )

    built = build_decision_briefing_packet_bundle(scaffold, question=scaffold["question"])
    packet = built["decision_briefing_packet"]
    report = built["answer_frame_normalization_report"]

    assert packet["answer_frame"]["default_answer"] == "Option A is favored when maintenance funding is protected."
    assert packet["answer_frame"]["classification"] == "conditional"
    assert report["schema_id"] == "answer_frame_normalization_report_v1"
    assert report["changed"] is True


def test_answer_frame_replaces_weak_generic_answer_with_grounded_fallback() -> None:
    frame, report = normalize_answer_frame(
        canonical_decision_spine={
            "confidence": "medium",
            "default_answer": {"claim": "Evidence supports a neutral or low-concern default under the stated conditions."},
            "strongest_support": [
                {
                    "claim": "Moderate egg consumption was not associated with incident cardiovascular disease in the pooled cohort evidence."
                }
            ],
            "strongest_counterevidence": [
                {"claim": "Some cohort evidence associated higher dietary cholesterol with higher cardiovascular risk."}
            ],
        },
        argument_model={
            "proposed_answer": "Evidence supports a neutral or low-concern default under the stated conditions."
        },
        question="Should eggs be treated as harmful, neutral, or beneficial dietary advice?",
    )

    assert "neutral or low-concern default under the stated conditions" not in frame["default_answer"]
    assert "Moderate egg consumption" in frame["default_answer"]
    assert report["status"].endswith("grounded_fallback")
