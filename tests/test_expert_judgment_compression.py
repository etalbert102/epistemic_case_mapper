from __future__ import annotations

import json
import re

import pytest

from epistemic_case_mapper.map_briefing_decision_writer_packet import (
    build_decision_writer_packet_bundle,
    decision_writer_packet_to_memo_ready_packet,
)
from epistemic_case_mapper.map_briefing_expert_judgment_compression import (
    build_expert_judgment_compression_input,
    build_expert_judgment_compression_report,
    expert_judgment_section,
    parse_expert_judgment_compression,
)
from epistemic_case_mapper.map_briefing_memo_ready_finalization import run_memo_ready_packet_synthesis
from epistemic_case_mapper.map_briefing_memo_ready_prompt import build_memo_ready_section_synthesis_plan
from epistemic_case_mapper.model_backends import ModelBackendResult
from test_decision_writer_packet import _global_model, _ledger


def _packet() -> dict:
    bundle = build_decision_writer_packet_bundle(global_decision_model=_global_model(), ledger=_ledger())
    analyst_model = {
        "schema_id": "analyst_decision_model_v1",
        "direct_answer": (
            "Adopt option A where the narrower setting is not decisive; "
            "settings with unresolved transport risk need separate review."
        ),
        "primary_answer": "Adopt option A where the narrower setting is not decisive.",
        "secondary_detail": "Settings with unresolved transport risk need separate review.",
        "secondary_detail_type": "scope_boundary",
        "full_direct_answer": (
            "Adopt option A where the narrower setting is not decisive; "
            "settings with unresolved transport risk need separate review."
        ),
        "decision_logic": {
            "bounded_bottom_line": "Adopt option A only where the narrower setting is not decisive.",
            "support_summary": "Outcome Review carries the main outcome finding.",
            "counterweight_weighting": "Scope Review bounds the answer rather than overturning it.",
            "practical_implications": ["Adopt option A only in settings matching the outcome evidence."],
        },
        "source_weight_judgments": [
            {
                "judgment_id": "analyst_source_weight_001",
                "source_ids": ["s1"],
                "main_use": "drives_answer",
                "why_weight_this_way": "Outcome Review carries the answer because it covers the main outcome.",
                "memo_weight_sentence": "Outcome Review carries the main answer.",
                "method": "parallel_global_analyst_source_weighting",
                "evidence_item_ids": ["decision_writer_item_001"],
            },
            {
                "judgment_id": "analyst_source_weight_002",
                "source_ids": ["s2"],
                "main_use": "defines_scope",
                "why_weight_this_way": "Scope Review defines where the result stops applying.",
                "memo_weight_sentence": "Scope Review bounds application to matching settings.",
                "method": "parallel_global_analyst_source_weighting",
                "evidence_item_ids": ["decision_writer_item_002"],
            },
        ],
        "source_weight_judgment_report": {"schema_id": "parallel_global_source_weight_judgment_report_v1", "status": "ready"},
    }
    return decision_writer_packet_to_memo_ready_packet(
        bundle["decision_writer_packet"],
        quality_report=bundle["decision_writer_packet_quality_report"],
        analyst_decision_model=analyst_model,
    )


def _valid_compression_payload() -> dict:
    return {
        "schema_id": "expert_judgment_compression_v1",
        "governing_judgment": "Option A is the best current read inside the studied setting, but scope evidence prevents broader use.",
        "source_weighting_logic": [
            {
                "point": "Outcome Review carries the answer; Scope Review bounds where it applies.",
                "decision_function": "source hierarchy",
                "evidence_item_ids": ["decision_writer_item_001", "decision_writer_item_002"],
                "source_ids": ["s1", "s2"],
            }
        ],
        "primary_reasoning_chain": [
            {
                "point": "The 20% improvement supports adopting Option A in matching settings.",
                "decision_function": "primary support",
                "evidence_item_ids": ["decision_writer_item_001"],
                "source_ids": ["s1"],
                "quantity_values": ["20% improvement"],
            }
        ],
        "counterweight_dispositions": [
            {
                "point": "The narrower setting evidence bounds rather than overturns the answer.",
                "decision_function": "scope boundary",
                "evidence_item_ids": ["decision_writer_item_002"],
                "source_ids": ["s2"],
            }
        ],
        "decision_boundaries": [
            {
                "point": "Use the answer only where the studied setting is relevant.",
                "decision_function": "application boundary",
                "evidence_item_ids": ["decision_writer_item_001", "decision_writer_item_002"],
                "source_ids": ["s1", "s2"],
            }
        ],
        "quantities_to_preserve": [
            {
                "value": "20% improvement",
                "interpretation": "effect size carrying the main answer",
                "evidence_item_ids": ["decision_writer_item_001"],
                "source_ids": ["s1"],
            }
        ],
        "what_to_subordinate": [
            {
                "point": "Unaccounted open questions should not drive the memo.",
                "decision_function": "subordinate",
            }
        ],
        "memo_voice_guidance": ["Write the answer as a bounded recommendation, not a source inventory."],
        "section_briefs": [
            {
                "section_id": "source_weighting",
                "governing_point": "Outcome Review carries the answer; Scope Review bounds application.",
                "paragraph_strategy": ["name the hierarchy", "explain what each source can decide"],
                "lead_with": "Lead with source roles.",
                "evidence_item_ids": ["decision_writer_item_001", "decision_writer_item_002"],
                "source_ids": ["s1", "s2"],
            },
            {
                "section_id": "answer_evidence",
                "governing_point": "The 20% improvement is enough to adopt where the evidence applies.",
                "paragraph_strategy": ["state the driver evidence", "interpret the effect size"],
                "lead_with": "Lead with the outcome gain.",
                "evidence_item_ids": ["decision_writer_item_001"],
                "source_ids": ["s1"],
                "quantity_values": ["20% improvement"],
            },
            {
                "section_id": "counterweights",
                "governing_point": "The narrower setting evidence bounds the answer rather than reversing it.",
                "paragraph_strategy": ["start with scope", "state what would change"],
                "lead_with": "Lead with the scope boundary.",
                "evidence_item_ids": ["decision_writer_item_002"],
                "source_ids": ["s2"],
            },
            {
                "section_id": "practical_implication",
                "governing_point": "Adopt Option A only where the studied setting applies.",
                "paragraph_strategy": ["state action", "state boundary"],
                "lead_with": "Lead with the usable recommendation.",
                "evidence_item_ids": ["decision_writer_item_001", "decision_writer_item_002"],
                "source_ids": ["s1", "s2"],
                "quantity_values": ["20% improvement"],
            },
        ],
    }


def test_expert_judgment_compression_validates_traceability() -> None:
    compression_input = build_expert_judgment_compression_input(_packet())
    compression, issues = parse_expert_judgment_compression(json.dumps(_valid_compression_payload()))
    report = build_expert_judgment_compression_report(compression_input, compression)

    assert issues == []
    assert report["status"] == "ready"
    assert report["missing_mandatory_evidence_item_ids"] == []
    assert report["unknown_source_ids"] == []
    assert expert_judgment_section(compression, "answer_evidence")["governing_point"].startswith("The 20% improvement")


def test_section_plan_surfaces_expert_judgment_brief() -> None:
    packet = _packet()
    packet["canonical_decision_writer_packet"]["expert_judgment_compression"] = _valid_compression_payload()

    plan = build_memo_ready_section_synthesis_plan(packet)
    prompts = [section["prompt"] for section in plan["sections"]]

    assert all("### Expert judgment brief" in prompt for prompt in prompts)
    assert any("The 20% improvement is enough to adopt" in prompt for prompt in prompts)
    assert all("Use the Expert judgment brief as the first-order analytical framing" in prompt for prompt in prompts)


def test_live_synthesis_runs_expert_judgment_compression_before_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    packet = _packet()
    calls: list[str] = []
    monkeypatch.setenv("ECM_EXPERT_JUDGMENT_COMPRESSION", "1")

    def fake_backend(prompt: str, *args, **kwargs) -> ModelBackendResult:
        calls.append(prompt)
        if "compact expert-judgment brief" in prompt:
            assert kwargs["json_mode"] is True
            return ModelBackendResult(text=json.dumps(_valid_compression_payload()), backend="fake")
        assert kwargs["json_mode"] is False
        heading = _heading_from_section_prompt(prompt)
        ids = re.findall(r'"evidence_id": "([^"]+)"', prompt)
        tags = " ".join(f"{{E:{evidence_id}}}" for evidence_id in ids)
        if heading == "How to Weight the Evidence":
            body = "Outcome Review carries the answer, while Scope Review bounds application [s1, s2]."
        elif heading == "Why This Is the Best Current Read":
            body = f"The 20% improvement supports adopting Option A where the studied setting applies {tags}."
        elif heading == "What Could Change or Bound the Answer":
            body = f"The narrower setting evidence bounds rather than overturns the answer {tags}."
        else:
            body = f"Adopt Option A only where the 20% improvement evidence applies and the scope boundary is acceptable {tags}."
        return ModelBackendResult(text=f"## {heading}\n\n{body}\n", backend="fake")

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_memo_ready_finalization.run_model_backend", fake_backend)

    result = run_memo_ready_packet_synthesis(packet, backend="ollama:test", backend_timeout=30, backend_retries=0)

    assert "compact expert-judgment brief" in calls[0]
    assert any("### Expert judgment brief" in prompt for prompt in calls[1:])
    assert result["report"]["expert_judgment_compression_report"]["status"] == "accepted"
    assert result["report"]["expert_judgment_utilization_report"]["schema_id"] == "expert_judgment_utilization_report_v1"


def _heading_from_section_prompt(prompt: str) -> str:
    match = re.search(r"Output must start exactly with: ## ([^\n]+)", prompt)
    if match:
        return match.group(1)
    match = re.search(r"## Section to Write: ([^\n]+)", prompt)
    if match:
        return match.group(1)
    return "Practical Implication"
