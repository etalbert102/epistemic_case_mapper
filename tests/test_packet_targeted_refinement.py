from __future__ import annotations

from epistemic_case_mapper.map_briefing_packet_refinement import PacketRefinementOutput, apply_adjudicated_relabel_cleanup, apply_packet_refinement
from epistemic_case_mapper.map_briefing_packet_quality_repair import repair_packet_for_synthesis
from epistemic_case_mapper.map_briefing_packet_targeted_refinement import (
    build_targeted_refinement_tasks,
    run_targeted_packet_refinement,
)


class FakeResult:
    def __init__(self, text: str) -> None:
        self.text = text


def _packet() -> dict:
    return {
        "decision_question": "Should the city adopt option A?",
        "evidence_bundles": [
            {
                "bundle_id": "bundle_001",
                "decision_role": "strongest_support",
                "directionality": "challenges",
                "claim": "Option A may shift risk downstream.",
                "why_it_matters": "Currently miscast as support.",
                "section_use": "Use as primary support.",
                "source_ids": ["s1"],
            },
            {
                "bundle_id": "bundle_002",
                "decision_role": "strongest_support",
                "claim": "Option A reduces flood losses.",
                "why_it_matters": "Primary benefit.",
                "source_ids": ["s2"],
            },
        ],
        "must_retain_ledger": [],
        "coverage_report": {},
    }


def _adjudication() -> dict:
    return {
        "accepted_recommendations": [
            {
                "edit_type": "relabel",
                "target_ids": ["bundle_001"],
                "recommended_role": "counterweight",
                "rationale": "The claim challenges the answer.",
            }
        ]
    }


def test_targeted_refinement_builds_local_task_context() -> None:
    tasks = build_targeted_refinement_tasks(_packet(), {"status": "warning"}, _adjudication())

    assert len(tasks) == 1
    assert tasks[0]["target_ids"] == ["bundle_001"]
    assert [row["bundle_id"] for row in tasks[0]["bundles"]] == ["bundle_001"]
    assert "bundle_002" not in str(tasks[0])


def test_targeted_refinement_applies_parallel_task_update() -> None:
    calls = []

    def fake_backend(prompt: str, *args, **kwargs) -> FakeResult:
        calls.append(prompt)
        return FakeResult(
            """
            {
              "schema_id": "decision_briefing_packet_refinement_v1",
              "packet_ready_for_synthesis": true,
              "bundle_updates": [
                {
                  "bundle_id": "bundle_001",
                  "decision_role": "counterweight",
                  "why_it_matters": "This is the main risk-shifting counterweight.",
                  "section_use": "Use as contrary evidence that bounds the answer."
                }
              ],
              "warnings": []
            }
            """
        )

    result = run_targeted_packet_refinement(
        packet=_packet(),
        sufficiency_report={"status": "warning"},
        critique_adjudication=_adjudication(),
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        run_backend=fake_backend,
        refinement_schema=PacketRefinementOutput,
        apply_refinement=apply_packet_refinement,
        apply_cleanup=apply_adjudicated_relabel_cleanup,
        repair_packet=repair_packet_for_synthesis,
    )

    updated = {row["bundle_id"]: row for row in result["packet"]["evidence_bundles"]}["bundle_001"]
    assert result["report"]["status"] == "targeted_applied"
    assert result["report"]["task_count"] == 1
    assert updated["decision_role"] == "counterweight"
    assert "bundle_002" not in calls[0]


def test_targeted_refinement_timeout_degrades_to_deterministic_cleanup() -> None:
    def failing_backend(*args, **kwargs) -> FakeResult:
        raise RuntimeError("timeout")

    result = run_targeted_packet_refinement(
        packet=_packet(),
        sufficiency_report={"status": "warning"},
        critique_adjudication=_adjudication(),
        backend="fake",
        backend_timeout=1,
        backend_retries=0,
        run_backend=failing_backend,
        refinement_schema=PacketRefinementOutput,
        apply_refinement=apply_packet_refinement,
        apply_cleanup=apply_adjudicated_relabel_cleanup,
        repair_packet=repair_packet_for_synthesis,
    )

    updated = {row["bundle_id"]: row for row in result["packet"]["evidence_bundles"]}["bundle_001"]
    assert result["report"]["status"] == "targeted_partial_backend_error"
    assert result["report"]["task_reports"][0]["status"] == "backend_error"
    assert updated["decision_role"] == "counterweight"
