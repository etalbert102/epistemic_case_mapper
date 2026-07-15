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
from epistemic_case_mapper.map_briefing_memo_ready_prompt import build_memo_ready_section_synthesis_plan
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
        heading = _heading_from_section_prompt(prompt)
        if heading == "Why This Is the Best Current Read":
            body = "Outcome Study reports that Option A reduced flood losses by 25% in comparable river cities [s1]."
        elif heading == "What Could Change or Bound the Answer":
            body = "Counter Study and Boundary Report bound the read because maintenance cuts and a narrower setting could erase the benefit [s2, s3]."
        else:
            body = "Use Option A where the comparable-city conditions hold and maintenance protection is credible [s1, s2, s3]."
        return ModelBackendResult(text=f"## {heading}\n\n{body}\n", backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="fake", backend_timeout=30, backend_retries=0)

    assert len(calls) == 3
    assert all("section_role_contract" in prompt for prompt in calls)
    assert all("evidence_language_contracts" in prompt for prompt in calls)
    assert all("section_focus" in prompt for prompt in calls)
    assert all("current_read_reference" in prompt for prompt in calls)
    assert all("Use evidence_language_contracts" in prompt for prompt in calls)
    assert all("Use section_focus and section_role_contract as the controlling job" in prompt for prompt in calls)
    assert all("do not repeat it as the section opener" in prompt for prompt in calls)
    assert all("Follow section_role_contract as the controlling job" in prompt for prompt in calls)
    assert all("Section role discipline never overrides retention" in prompt for prompt in calls)
    assert any("translate_the_read_into_action" in prompt for prompt in calls)
    assert result["report"]["synthesis_mode"] == "parallel_section_synthesis"
    assert result["report"]["section_count"] == 3
    assert all(row["accepted"] for row in result["report"]["section_reports"])
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
    assert practical["evidence_context"]
    assert practical["source_weighting"]
    assert "balanced_answer_frame" not in practical["top_context"]
    assert "bluf_contract" not in practical["top_context"]
    assert "current_read_reference" in practical["top_context"]


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
    assert len(result["report"]["section_reports"]) == 3
    assert all(row["accepted"] for row in result["report"]["section_reports"])


def _heading_from_section_prompt(prompt: str) -> str:
    match = re.search(r"exactly: ## (.+)", prompt)
    return match.group(1).strip() if match else "Why This Is the Best Current Read"
