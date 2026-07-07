from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing import (
    briefing_scaffold,
    build_compact_decision_model,
    build_source_display_lookup,
    generated_map_erosion_audit,
    render_decision_model_brief,
)
from epistemic_case_mapper.map_briefing_reader_contracts import compose_final_reader_memo_package
from epistemic_case_mapper.map_briefing_section_rewrite import rewrite_reader_memo_by_section
from epistemic_case_mapper.model_backends import ModelBackendResult
from tests.test_decision_model_vertical_slice import _arbitrary_candidate_map, _quality_report


def _confirming_adjudication() -> str:
    return json.dumps(
        {
            "issue_assessments": [
                {
                    "issue_index": 0,
                    "blocking": True,
                    "reason": "The deterministic issue is material for this test case.",
                    "repair_instruction": "Repair the confirmed validation failure.",
                }
            ]
        }
    )


def test_section_rewrite_rejects_section_that_drops_main_memo_obligation(monkeypatch) -> None:
    memo, appendix, scaffold, candidate_map = _memo_package()
    scaffold["argument_model"]["quantitative_anchors"] = [
        {
            "statement": "The tracked estimate was 42 units in the main comparison.",
            "why_it_matters": "This estimate is the main quantitative anchor.",
            "quantities": ["42 units"],
            "source_ids": [],
            "claim_ids": [],
            "quantity_ids": [],
        }
    ]
    seen_prompt = ""

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0, response_schema=None):
        nonlocal seen_prompt
        if prompt.startswith("You are a validation adjudicator"):
            return ModelBackendResult(text=_confirming_adjudication(), backend=backend)
        section = prompt.split("Section to rewrite:\n", 1)[1].strip()
        if prompt.startswith("You are an analyst producing decision-ready analysis") and section.startswith("## Evidence Carrying the Conclusion"):
            seen_prompt = prompt
            return ModelBackendResult(
                text=json.dumps({"section_markdown": "## Evidence Carrying the Conclusion\n\nThe answer follows from the source packet."}),
                backend=backend,
            )
        return ModelBackendResult(text=json.dumps({"section_markdown": section}), backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_section_rewrite.run_model_backend", fake_backend)

    result = rewrite_reader_memo_by_section(memo, appendix, scaffold, candidate_map, backend="fake", backend_timeout=30, backend_retries=0)

    why_report = next(section for section in result["report"]["sections"] if section["title"] == "Evidence Carrying the Conclusion")
    assert "validation_obligations" in seen_prompt
    assert "required_main_memo_obligations" in seen_prompt
    assert why_report["status"] == "accepted_structured_fallback"
    first_attempt = why_report["attempts"][0]
    assert first_attempt["status"] == "rejected"
    assert any("dropped required main-memo obligation" in issue for issue in first_attempt["issues"])


def test_section_rewrite_generates_decision_brief_last_with_model_bluf(monkeypatch) -> None:
    memo, appendix, scaffold, candidate_map = _memo_package()
    calls: list[str] = []

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0, response_schema=None):
        calls.append(prompt)
        if "opening BLUF" in prompt:
            markdown = (
                "## Decision Brief\n\n"
                f"**Decision question:** {scaffold['question']}\n\n"
                "Use the pilot as the default for small building projects because the accepted body sections show the practical case and the main caveat. "
                "Keep the rollout bounded to projects where review capacity remains adequate.\n\n"
                "**Confidence:** medium"
            )
            return ModelBackendResult(text=json.dumps({"section_markdown": markdown}), backend=backend)
        section = prompt.split("Section to rewrite:\n", 1)[1].strip()
        return ModelBackendResult(text=json.dumps({"section_markdown": section}), backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_section_rewrite.run_model_backend", fake_backend)

    result = rewrite_reader_memo_by_section(memo, appendix, scaffold, candidate_map, backend="fake", backend_timeout=30, backend_retries=0)

    brief_report = next(section for section in result["report"]["sections"] if section["title"] == "Decision Brief")
    assert brief_report["status"] == "accepted_model_bluf"
    assert "Use the pilot as the default" in result["memo"]
    assert any("opening BLUF" in prompt for prompt in calls)
    assert any("Canonical decision spine packet" in prompt for prompt in calls)


def test_section_rewrite_repairs_rejected_decision_brief_before_fallback(monkeypatch) -> None:
    memo, appendix, scaffold, candidate_map = _memo_package()
    calls: list[str] = []

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0, response_schema=None):
        calls.append(prompt)
        if prompt.startswith("You are a validation adjudicator"):
            return ModelBackendResult(text=_confirming_adjudication(), backend=backend)
        if prompt.startswith("You are correcting a rejected Decision Brief"):
            markdown = (
                "## Decision Brief\n\n"
                f"**Decision question:** {scaffold['question']}\n\n"
                "For the default case, the current read is neutral or low-concern under the stated conditions. "
                "Key caveat: keep the decision limited to cases where review capacity remains adequate.\n\n"
                "**Confidence:** medium"
            )
            return ModelBackendResult(text=json.dumps({"section_markdown": markdown}), backend=backend)
        if "opening BLUF" in prompt:
            return ModelBackendResult(
                text=json.dumps({"section_markdown": "## Decision Brief\n\nThis is a clearly beneficial default.\n\n**Confidence:** medium"}),
                backend=backend,
            )
        section = prompt.split("Section to rewrite:\n", 1)[1].strip()
        return ModelBackendResult(text=json.dumps({"section_markdown": section}), backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_section_rewrite.run_model_backend", fake_backend)

    result = rewrite_reader_memo_by_section(memo, appendix, scaffold, candidate_map, backend="fake", backend_timeout=30, backend_retries=0)

    brief_report = next(section for section in result["report"]["sections"] if section["title"] == "Decision Brief")
    assert brief_report["status"] == "accepted_model_bluf_repair"
    assert brief_report["fallback_used"] is False
    assert "current read is neutral or low-concern" in result["memo"]
    assert any(prompt.startswith("You are correcting a rejected Decision Brief") for prompt in calls)


def test_section_rewrite_falls_back_when_decision_brief_bluf_is_rejected(monkeypatch) -> None:
    memo, appendix, scaffold, candidate_map = _memo_package()

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0, response_schema=None):
        if prompt.startswith("You are a validation adjudicator"):
            return ModelBackendResult(text=_confirming_adjudication(), backend=backend)
        if "opening BLUF" in prompt:
            return ModelBackendResult(text='{"section_markdown": "## Decision Brief\\n\\nToo thin."}', backend=backend)
        section = prompt.split("Section to rewrite:\n", 1)[1].strip()
        return ModelBackendResult(text=json.dumps({"section_markdown": section}), backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_section_rewrite.run_model_backend", fake_backend)

    result = rewrite_reader_memo_by_section(memo, appendix, scaffold, candidate_map, backend="fake", backend_timeout=30, backend_retries=0)

    brief_report = next(section for section in result["report"]["sections"] if section["title"] == "Decision Brief")
    assert brief_report["status"] == "accepted_deterministic_fallback_after_model"
    assert brief_report["fallback_used"] is True
    assert "Key evidence:" in result["memo"]


def _memo_package() -> tuple[str, str, dict, dict]:
    candidate_map = _arbitrary_candidate_map()
    quality_report = _quality_report()
    question = "Should the city pilot remote permitting for small building projects?"
    source_lookup = build_source_display_lookup(candidate_map)
    scaffold = briefing_scaffold(
        candidate_map,
        quality_report,
        source_lookup,
        generated_map_erosion_audit(candidate_map),
        question=question,
    )
    compact = build_compact_decision_model(
        candidate_map,
        quality_report,
        question=question,
        scaffold=scaffold,
    )
    rendered = render_decision_model_brief(compact)
    package = compose_final_reader_memo_package(rendered, scaffold)
    return str(package["memo"]), str(package["appendix"]), package["scaffold"], candidate_map
