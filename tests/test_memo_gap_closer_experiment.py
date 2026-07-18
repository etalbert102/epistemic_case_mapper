from __future__ import annotations

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_gap_closer_experiment import (
    build_gap_closer_experiment_variants,
    score_gap_closer_memo,
)
from epistemic_case_mapper.map_briefing_memo_ready_packet import build_quality_synthesis_packet_bundle

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
