from __future__ import annotations

from pathlib import Path

from epistemic_case_mapper.map_briefing_prioritized_argument_arm_b import (
    audit_prompt_submissions,
    build_arm_b_projection,
    load_frozen_arm_b_inputs,
    run_arm_b_b0,
)


FROZEN_EGGS = Path("artifacts/truth_boundary_verification_eggs_live/briefing")


def test_arm_b_projection_resolves_eggs_writer_ownership() -> None:
    projection = build_arm_b_projection(load_frozen_arm_b_inputs(FROZEN_EGGS))

    assert projection["status"] == "pass"
    required = projection["section_contract_overlap_report"]["required_by_section"]
    assert required["answer_evidence"] == [
        "decision_writer_item_001",
        "decision_writer_item_002",
        "decision_writer_item_003",
        "decision_writer_item_011",
    ]
    assert required["counterweights"] == [
        "decision_writer_item_004",
        "decision_writer_item_005",
        "decision_writer_item_007",
        "decision_writer_item_008",
    ]
    assert required["practical_implication"] == []
    assert projection["projection_evaluation_packet"]["lineage_fanout"]["claim:eggs_c024"] == [
        "decision_writer_item_001",
        "decision_writer_item_002",
    ]
    assert projection["projection_evaluation_packet"]["ownership"]["decision_writer_item_004"] == "counterweights"
    assert projection["projection_evaluation_packet"]["ownership"]["decision_writer_item_005"] == "counterweights"


def test_arm_b_projection_suppresses_source_weighting_and_legacy_packet_roots() -> None:
    projection = build_arm_b_projection(load_frozen_arm_b_inputs(FROZEN_EGGS))
    section_ids = [row["section_id"] for row in projection["section_packets"]]
    serialized = str(projection["section_packets"])

    assert section_ids == ["answer_evidence", "counterweights", "practical_implication"]
    assert "source_weighting" not in section_ids
    assert "balanced_answer_frame" not in serialized
    assert "bluf_contract" not in serialized
    assert "analyst_decision_spine" not in serialized
    assert "reader_judgment_packet" not in serialized


def test_arm_b_b0_captures_initial_and_retry_prompts(tmp_path) -> None:
    result = run_arm_b_b0(briefing_dir=FROZEN_EGGS, output_dir=tmp_path, force_retry=True)

    assert result["report"]["status"] == "pass"
    assert result["generation"]["report"]["status"] == "accepted"
    assert result["prompt_submission_audit"]["status"] == "pass"
    assert result["prompt_submission_audit"]["retry_prompt_count"] >= 1
    assert (tmp_path / "prompt_submission_audit.json").exists()
    assert (tmp_path / "projection_evaluation_packet.json").exists()
    assert (tmp_path / "frozen_inputs" / "input_hashes.json").exists()
    assert result["warning_adjudication_report"]["unadjudicated_count"] == 0


def test_arm_b_prompt_audit_flags_legacy_context() -> None:
    audit = audit_prompt_submissions(
        [
            {
                "section_id": "answer_evidence",
                "attempt": 1,
                "prompt": '### Slim argument packet\n{"balanced_answer_frame": {}}\n',
            }
        ]
    )

    assert audit["status"] == "fail"
    assert any("balanced_answer_frame" in issue for issue in audit["issues"])
