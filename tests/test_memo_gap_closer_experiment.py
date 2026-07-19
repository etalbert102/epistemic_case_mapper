from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.pipeline.briefing.map_briefing_gap_closer_experiment import (
    build_gap_closer_experiment_variants,
    score_gap_closer_memo,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet import build_quality_synthesis_packet_bundle

from test_decision_briefing_packet import _scaffold


def _packet() -> dict:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    return build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]


def test_gap_closer_richer_bluf_changes_bottom_line_context() -> None:
    variants = build_gap_closer_experiment_variants(_packet())

    baseline = variants["baseline"]["section_plan"]["bottom_line"]
    richer = variants["richer_bluf"]["section_plan"]["bottom_line"]

    assert baseline
    assert "Confidence:" in baseline
    assert "Scope:" in baseline
    assert "Confidence:" in richer
    assert "Scope:" in richer
    assert variants["richer_bluf"]["packet"]["canonical_decision_writer_packet"]["bluf_contract"]["decision_grade_bluf_context"]


def test_gap_closer_source_weighted_thesis_reaches_section_prompts() -> None:
    variants = build_gap_closer_experiment_variants(_packet())
    section_plan = variants["source_weighted_theses"]["section_plan"]

    answer = next(section for section in section_plan["sections"] if section["section_id"] == "answer_evidence")
    counterweights = next(section for section in section_plan["sections"] if section["section_id"] == "counterweights")

    assert "Source hierarchy thesis:" in answer["prompt"]
    assert "Make the affirmative case from the evidence that carries the answer first" in answer["prompt"]
    assert "Use boundary and counterweight evidence" in counterweights["prompt"]
    assert answer["packet"]["analyst_argument_moves"][0]["step_id"] == "source_weighted_answer_evidence"


def test_gap_closer_source_use_limits_reach_section_prompts() -> None:
    packet = _packet()
    packet["canonical_decision_writer_packet"]["source_weight_judgments"] = [
        {
            "source_ids": ["s1"],
            "main_use": "drives_answer",
            "reader_facing_limit": "Use only for the central flood-protection claim, not for subgroup exceptions.",
            "what_not_to_use_it_for": ["Subgroup exceptions."],
        }
    ]
    variants = build_gap_closer_experiment_variants(packet)
    section_plan = variants["source_use_limits"]["section_plan"]

    changed_sections = {
        row["section_id"]
        for row in variants["source_use_limits"]["input_changes"]
        if row.get("source_use_limit_count")
    }

    assert changed_sections
    for section in section_plan["sections"]:
        if section["section_id"] not in changed_sections:
            continue
        prompt = section["prompt"]
        assert "source use limit" in prompt.lower()
        assert "Allowed use:" in prompt
        assert "Not enough for:" in prompt


def test_gap_closer_counterweight_disposition_reaches_counterweight_prompt() -> None:
    variants = build_gap_closer_experiment_variants(_packet())
    section_plan = variants["counterweight_disposition"]["section_plan"]
    counterweights = next(section for section in section_plan["sections"] if section["section_id"] == "counterweights")

    assert variants["counterweight_disposition"]["input_changes"]
    assert counterweights["packet"]["analyst_argument_moves"][0]["step_id"] == "experiment_counterweight_disposition"
    assert "whether the limiting evidence overturns, narrows, or only calibrates the answer" in counterweights["prompt"]


def test_gap_closer_analyst_routed_sections_adds_counterweight_evidence() -> None:
    packet = _packet()
    canonical = packet["canonical_decision_writer_packet"]
    lanes = canonical["organized_evidence_inventory"]["lanes"]
    counterweight_item = {
        **canonical["priority_evidence"][0],
        "item_id": "decision_writer_counterweight_test",
        "claim": "A high-risk subgroup bounds the default answer.",
        "source_ids": ["s2"],
        "role": "scope_boundary",
        "answer_relation": "bounds_scope",
    }
    lanes["scope_and_applicability"] = [counterweight_item]
    for section in canonical["evidence_weighted_argument_spine"]["section_plan"]:
        if section["section"] == "What Could Change or Bound the Answer":
            section["owned_evidence_item_ids"] = []

    variants = build_gap_closer_experiment_variants(packet)
    routed = variants["analyst_routed_sections"]
    section_plan = routed["section_plan"]
    counterweights = next(section for section in section_plan["sections"] if section["section_id"] == "counterweights")

    assert "decision_writer_counterweight_test" in routed["packet"]["canonical_decision_writer_packet"]["evidence_weighted_argument_spine"]["section_plan"][2]["owned_evidence_item_ids"]
    assert counterweights["packet"]["source_bound_evidence_atoms"]
    assert "A high-risk subgroup bounds the default answer" in counterweights["prompt"]


def test_gap_closer_role_organized_handoff_reaches_section_packets() -> None:
    variants = build_gap_closer_experiment_variants(_packet())
    section_plan = variants["role_organized_handoff"]["section_plan"]

    changed = {
        row["section_id"]
        for row in variants["role_organized_handoff"]["input_changes"]
        if row.get("section_local_evidence_job_count")
    }
    assert {"answer_evidence", "counterweights", "practical_implication"}.intersection(changed)
    for section in section_plan["sections"]:
        if section["section_id"] not in changed:
            continue
        jobs = section["packet"].get("section_local_evidence_jobs")
        assert jobs
        assert all(job.get("allowed_evidence_ids") for job in jobs)


def test_gap_closer_role_bound_citations_narrows_mixed_atoms() -> None:
    packet = _packet()
    canonical = packet["canonical_decision_writer_packet"]
    canonical["source_weight_judgments"] = [
        {"source_ids": ["s1"], "main_use": "drives_answer"},
        {"source_ids": ["s2"], "main_use": "calibrates_magnitude"},
    ]
    canonical["priority_evidence"][0]["source_ids"] = ["s1", "s2"]
    variants = build_gap_closer_experiment_variants(packet)
    section_plan = variants["role_bound_citations"]["section_plan"]

    assert any(row.get("role_bound_atom_count") for row in variants["role_bound_citations"]["input_changes"])
    answer = next(section for section in section_plan["sections"] if section["section_id"] == "answer_evidence")
    mixed_atom = next(atom for atom in answer["packet"]["source_bound_evidence_atoms"] if atom["source_ids"] == ["s2"])
    assert mixed_atom["citation_role"] == "calibration"


def test_gap_closer_role_bound_existing_structure_does_not_add_section_jobs() -> None:
    packet = _packet()
    canonical = packet["canonical_decision_writer_packet"]
    canonical["source_weight_judgments"] = [
        {"source_ids": ["s1"], "main_use": "drives_answer"},
        {"source_ids": ["s2"], "main_use": "calibrates_magnitude"},
    ]
    canonical["priority_evidence"][0]["source_ids"] = ["s1", "s2"]
    variants = build_gap_closer_experiment_variants(packet)
    variant = variants["role_bound_existing_structure"]
    section_plan = variant["section_plan"]

    assert any(row.get("role_bound_atom_count") for row in variant["input_changes"])
    assert not any(
        section["packet"].get("section_local_evidence_jobs")
        for section in section_plan["sections"]
    )
    answer = next(section for section in section_plan["sections"] if section["section_id"] == "answer_evidence")
    mixed_atom = next(atom for atom in answer["packet"]["source_bound_evidence_atoms"] if atom["source_ids"] == ["s2"])
    assert mixed_atom["citation_role"] == "calibration"


def test_gap_closer_score_surfaces_decision_usefulness_proxies() -> None:
    packet = _packet()
    memo = """# Decision Memo

**Decision Question:** Should the city adopt option A?

**Bottom Line:** Adopt option A for the scoped case. Confidence: medium. Main boundary: revisit if flood frequency changes.

## Why This Is the Best Current Read
The source hierarchy carries the answer through driver evidence and bounds it through scope evidence [s1].

## What Could Change or Bound the Answer
The answer would change if the key crux no longer holds.

## Practical Implication
The city should use the read as an action guide.
"""

    score = score_gap_closer_memo(memo, packet, original_memo=memo)

    assert score["headline"]["decision_proxy_score"] >= 4
    assert "validation_warning_count" in score["headline"]
