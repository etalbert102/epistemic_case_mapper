from __future__ import annotations

import re

import pytest

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_decision_writer_packet import (
    build_decision_writer_packet_bundle,
    decision_writer_packet_to_memo_ready_packet,
)
from epistemic_case_mapper.map_briefing_memo_ready_finalization import run_memo_ready_packet_synthesis
from epistemic_case_mapper.map_briefing_memo_ready_packet import build_quality_synthesis_packet_bundle
from epistemic_case_mapper.map_briefing_memo_ready_prompt import build_memo_ready_section_synthesis_plan, build_memo_ready_section_synthesis_prompt
from epistemic_case_mapper.map_briefing_memo_ready_section_synthesis import (
    _repair_near_miss_source_ids,
    _unknown_section_source_ids,
)
from epistemic_case_mapper.map_briefing_memo_ready_prompt import _quantity_collision_warnings
from epistemic_case_mapper.model_backends import ModelBackendResult

from test_decision_briefing_packet import _scaffold
from test_decision_writer_packet import _global_model, _ledger


def test_live_memo_ready_synthesis_runs_sections_in_parallel_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    calls: list[str] = []

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        calls.append(prompt)
        assert kwargs["json_mode"] is False
        assert kwargs["num_predict"] == 4096
        heading = _heading_from_section_prompt(prompt)
        if heading == "Why This Is the Best Current Read":
            body = "Outcome Study reports that Option A reduced flood losses by 25% in comparable river cities [s1]."
        elif heading == "How to Weight the Evidence":
            body = "Weight Outcome Study most for the main read, while using Counter Study and Boundary Report to bound the answer [s1, s2, s3]."
        elif heading == "What Could Change or Bound the Answer":
            body = "Counter Study and Boundary Report bound the read because maintenance cuts and a narrower setting could erase the benefit [s2, s3]."
        else:
            body = "Use Option A where the comparable-city conditions hold and maintenance protection is credible [s1, s2, s3]."
        return ModelBackendResult(text=f"## {heading}\n\n{body}\n", backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert len(calls) == 4
    assert all("markdown analyst notes" in prompt for prompt in calls)
    assert all("### Section job" in prompt for prompt in calls)
    assert all("### Suggested paragraph flow" in prompt for prompt in calls)
    assert all("Current read:" in prompt for prompt in calls)
    assert all("Use parentheses, not square brackets, for confidence intervals" in prompt for prompt in calls)
    assert all("Reader question:" in prompt for prompt in calls)
    assert all("### Calibration limits" in prompt for prompt in calls)
    assert all("### Source language and use limits" in prompt for prompt in calls)
    assert any("### Required evidence points" in prompt for prompt in calls)
    assert any("### Source weighting notes" in prompt for prompt in calls)
    assert any("Translate the answer into action guidance" in prompt for prompt in calls)
    assert all("section_packet:" not in prompt for prompt in calls)
    assert result["report"]["synthesis_mode"] == "parallel_section_synthesis"
    assert result["report"]["section_count"] == 4
    assert result["report"]["num_predict"] == 4096
    assert all(row["accepted"] for row in result["report"]["section_reports"])
    assert all(row["num_predict"] == 4096 for row in result["report"]["section_reports"])
    assert "## How to Weight the Evidence" in result["memo"]
    assert "## Why This Is the Best Current Read" in result["memo"]
    assert "## What Could Change or Bound the Answer" in result["memo"]
    assert "## Practical Implication" in result["memo"]
    assert "25%" in result["memo"]


def test_section_packets_are_section_local_and_practical_gets_evidence() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    inventory = packet["canonical_decision_writer_packet"]["organized_evidence_inventory"]["lanes"]
    inventory.setdefault("interpretive_context", []).append(
        {
            "item_id": "practical_context",
            "role": "mechanism_or_explanation",
            "answer_relation": "contextualizes_answer",
            "claim": "Monitoring feasibility determines how the answer should be applied.",
            "source_ids": ["s1"],
            "decision_relevance": "Translates the answer into a concrete operating boundary.",
        }
    )

    plan = build_memo_ready_section_synthesis_plan(packet)
    sections = {row["section_id"]: row["packet"] for row in plan["sections"]}
    practical = sections["practical_implication"]

    assert practical["section_focus"]["use_current_read_as"] == "background_only"
    assert practical["section_focus"]["reader_question"] == "Given the answer and its limits, what should the decision-maker do next?"
    assert practical["section_focus"]["prose_lead"] == "Open with the usable stance inside scope, then name the condition that changes application."
    assert practical["section_focus"]["paragraph_shape"]
    assert "The decision-maker should" in practical["section_focus"]["stock_phrases_to_replace"]
    assert practical["source_bound_evidence_atoms"]
    assert all("excluded_quantity_tuples" not in atom for atom in practical["source_bound_evidence_atoms"])
    assert practical["evidence_context"]
    assert practical["source_weighting"]
    assert "balanced_answer_frame" not in practical["top_context"]
    assert "bluf_contract" not in practical["top_context"]
    assert "current_read_reference" in practical["top_context"]


def test_section_prompt_renders_sparse_top_context_markdown_notes() -> None:
    prompt = build_memo_ready_section_synthesis_prompt(
        {
            "heading": "What Could Change or Bound the Answer",
            "section_job": "Handle limiting evidence and cruxes.",
            "section_role_contract": {
                "role": "bound_or_change_the_answer",
                "do": ["explain what narrows the answer"],
                "avoid": ["repeating the full affirmative case"],
            },
            "section_focus": {
                "reader_question": "What could make this answer too broad?",
                "paragraph_shape": ["main limitation", "update trigger"],
            },
            "top_context": {
                "decision_question": "Should option A be adopted?",
                "current_read_reference": "Adopt option A in the supported population.",
                "confidence": "medium",
                "must_not_overstate": ["Do not ignore the lipid ratio concerns entirely."],
                "lightweight_writer_guidance": {
                    "quantity_wording_risks": [
                        {
                            "risk": "Mixing concentration and ratio endpoints.",
                            "safe_wording": "Use mean difference in LDL-c concentration for 8.14 mg/dL and mean difference in LDL-c/HDL-c ratio for 0.14.",
                            "quantities": ["8.14 mg/dL", "0.14"],
                            "source_ids": ["s_li"],
                        }
                    ],
                    "evidence_quality_caveats": [
                        {"caveat": "Study excludes some treated populations.", "source_ids": ["s_li"]}
                    ],
                },
                "decision_usefulness": {
                    "cruxes_and_thresholds": [
                        {
                            "crux": "Metabolic condition threshold",
                            "threshold": "Type 2 diabetes or high LDL",
                            "would_change_if": "Risk subgroup evidence strengthens.",
                            "source_ids": ["s_bmj"],
                        }
                    ],
                    "monitoring_triggers": [
                        {
                            "trigger": "New longitudinal data on subgroup outcomes.",
                            "would_update": "The conditional boundary.",
                            "source_ids": ["s_bmj"],
                        }
                    ],
                },
            },
        },
        known_source_ids=["s_li", "s_bmj"],
    )

    assert "section_packet:" not in prompt
    assert "### Writing guidance, caveats, and quantity risks" in prompt
    assert "8.14 mg/dL" in prompt
    assert "0.14" in prompt
    assert "mean difference in LDL-c/HDL-c ratio" in prompt
    assert "### Decision cruxes, thresholds, and update triggers" in prompt
    assert "Metabolic condition threshold" in prompt
    assert "[s_li]" in prompt
    assert "[s_bmj]" in prompt


def test_section_synthesis_num_predict_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]
    seen: list[int] = []
    monkeypatch.setenv("ECM_MEMO_READY_SECTION_NUM_PREDICT", "6144")

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        seen.append(kwargs["num_predict"])
        heading = _heading_from_section_prompt(prompt)
        return ModelBackendResult(text=f"## {heading}\n\nOutcome evidence supports the section [s1].\n", backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert seen and set(seen) == {6144}
    assert result["report"]["num_predict"] == 6144


def test_quantity_collision_warnings_keep_same_surface_scopes_separate() -> None:
    warnings = _quantity_collision_warnings(
        [
            {
                "claim": "Effect is larger in one subgroup.",
                "source_ids": ["s1"],
                "quantity_tuples": [
                    {
                        "value": "1.25 (HR)",
                        "interpretation": "risk in lower baseline group",
                        "source_ids": ["s1"],
                        "applicability_scope": "participants with lower baseline values",
                    }
                ],
            },
            {
                "claim": "Effect is larger in another subgroup.",
                "source_ids": ["s2"],
                "quantity_tuples": [
                    {
                        "value": "1.25 (0.99 to 1.59)",
                        "interpretation": "relative risk in diagnosed participants",
                        "source_ids": ["s2"],
                        "applicability_scope": "people with diagnosis",
                    }
                ],
            },
        ]
    )

    assert warnings
    assert warnings[0]["quantity_surface"] == "1.25"
    assert "Keep these entries separate" in warnings[0]["instruction"]


def test_section_synthesis_preserves_belief_question_use_read_heading() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="What should an investigator believe about option A?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    plan = build_memo_ready_section_synthesis_plan(packet)
    headings = [row["heading"] for row in plan["sections"]]

    assert "How to Use This Read" in headings
    assert "Why This Is the Best current answer" not in headings


def test_live_memo_ready_section_synthesis_rejects_unknown_source_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        heading = _heading_from_section_prompt(prompt)
        return ModelBackendResult(text=f"## {heading}\n\nA claim with a made-up source [not_a_source].\n", backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["memo"] == ""
    assert result["report"]["status"] == "section_synthesis_failed"
    assert result["report"]["accepted"] is False
    assert all(row["unknown_source_ids"] == ["not_a_source"] for row in result["report"]["section_reports"])


def test_live_memo_ready_section_synthesis_normalizes_statistical_brackets(monkeypatch: pytest.MonkeyPatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    packet = build_quality_synthesis_packet_bundle(built["decision_briefing_packet"])["memo_ready_packet"]

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        heading = _heading_from_section_prompt(prompt)
        return ModelBackendResult(
            text=f"## {heading}\n\nOutcome evidence reports a subgroup estimate [95% CI, 1.12-1.39] [s1].\n",
            backend="fake",
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["status"] in {"accepted", "accepted_with_retention_warnings"}
    assert "[95% CI, 1.12-1.39]" not in result["memo"]
    assert "(95% CI, 1.12-1.39)" in result["memo"]
    assert "[s1]" in result["memo"]


def test_section_synthesis_repairs_long_near_miss_source_id_but_not_unknowns() -> None:
    known = {"aha_2019_dietary_cholesterol_pubmed"}
    markdown = "The advisory supports the read [aha_2019_itary_cholesterol_pubmed]. Unknown remains [not_a_source]."

    repaired = _repair_near_miss_source_ids(markdown, known)

    assert "[aha_2019_dietary_cholesterol_pubmed]" in repaired
    assert "[aha_2019_itary_cholesterol_pubmed]" not in repaired
    assert _unknown_section_source_ids(repaired, known) == ["not_a_source"]


def test_decision_writer_packet_section_synthesis_warnings_are_not_marked_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    packet = decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
    )

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        heading = _heading_from_section_prompt(prompt)
        return ModelBackendResult(
            text=(
                f"## {heading}\n\n"
                "Outcome Review reports that Option A improves the main outcome by 20% improvement [s1]."
            ),
            backend="fake",
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["contract_mode"] == "strict_writer_packet"
    assert result["report"]["synthesis_mode"] == "parallel_section_synthesis"
    assert result["report"]["status"] == "accepted_with_retention_warnings"
    assert result["report"]["accepted"] is False
    assert result["report"]["missing_mandatory_count"] >= 1
    assert len(result["report"]["section_reports"]) == 4
    assert all(row["accepted"] for row in result["report"]["section_reports"])


def _heading_from_section_prompt(prompt: str) -> str:
    match = re.search(r"exactly(?: with)?: ## (.+)", prompt)
    return match.group(1).strip() if match else "Why This Is the Best Current Read"
