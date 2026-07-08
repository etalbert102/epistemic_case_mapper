from __future__ import annotations

import json
from pathlib import Path

from epistemic_case_mapper.map_briefing_editorial_pass import (
    build_decision_memo_editorial_brief,
    build_decision_memo_editorial_prompt,
    run_decision_memo_editorial_pass,
)
from epistemic_case_mapper.map_briefing_final_editor_artifacts import reader_memo_edit_artifact_paths
from epistemic_case_mapper.map_briefing_final_outputs import _final_reader_output_paths, _final_reader_summary_paths
from epistemic_case_mapper.model_backends import ModelBackendResult


def test_editorial_brief_flags_dense_opening_and_inventory_prose() -> None:
    brief = build_decision_memo_editorial_brief(_dense_memo(), {"question": _QUESTION})

    codes = {row["code"] for row in brief["findings"]}

    assert brief["schema_id"] == "decision_memo_editorial_brief_v1"
    assert "opening_answer_too_dense" in codes
    assert "inventory_shaped_prose" in codes
    assert brief["patch_budget"]["max_edits"] == 4


def test_editorial_brief_flags_source_boilerplate_and_pipeline_leakage() -> None:
    memo = (
        "## Decision Brief\n\n"
        f"**Decision question:** {_QUESTION}\n\n"
        "Use the option only under the tested conditions.\n\n"
        "**Confidence:** medium\n\n"
        "## Practical Scope and Exceptions\n\n"
        "The result applies to monitored programs. All health/medical information on this website has been reviewed and approved. "
        "Some high-priority evidence was excluded from this synthesis due to being malformed for review.\n\n"
        "## Sources\n\n"
        "- Source A\n"
    )
    brief = build_decision_memo_editorial_brief(memo, {"question": _QUESTION})

    codes = {row["code"] for row in brief["findings"]}

    assert "source_boilerplate_leakage" in codes
    assert "pipeline_leakage" in codes


def test_editorial_prompt_uses_local_edit_budget_and_forbids_new_claims() -> None:
    brief = build_decision_memo_editorial_brief(_dense_memo(), {"question": _QUESTION})
    prompt = build_decision_memo_editorial_prompt(_dense_memo(), brief)

    assert "Return JSON edits, not a rewritten memo." in prompt
    assert "Do not add new facts, numbers, sources" in prompt
    assert '"max_edits": 4' in prompt
    assert "allowed_edit_types" in prompt


def test_editorial_pass_accepts_local_edit_that_improves_readability(monkeypatch) -> None:
    replacement = (
        "Based on this document set, the decision should be treated as bounded rather than resolved. "
        "The strongest support is useful but conditional, and the main caveat is that implementation quality drives the result."
    )
    payload = {"edits": [{"target": _dense_opening(), "replacement": replacement, "target_section": "Decision Brief", "edit_type": "tighten_bluf"}]}

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        return ModelBackendResult(text=json.dumps(payload), backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_editorial_pass.run_model_backend", fake_backend)

    result = run_decision_memo_editorial_pass(
        _dense_memo(),
        {"question": _QUESTION},
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["report"]["status"] == "accepted"
    assert result["report"]["applied_edit_count"] == 1
    assert replacement in result["memo"]


def test_editorial_pass_rejects_edit_that_drops_required_packet_evidence(monkeypatch) -> None:
    target = (
        "The strongest observed estimate is 0.96 in Source A, which should remain visible because it anchors the decision, "
        "because it is the clearest quantitative anchor available, because the surrounding evidence is otherwise qualitative, "
        "because the decision maker needs to know whether the apparent benefit is large enough to matter, and because removing "
        "that anchor would leave the bottom line sounding more certain than the record supports."
    )
    replacement = "The strongest observed estimate should remain visible because it anchors the decision."
    memo = _memo_with_required_number(target)
    packet = {
        "must_retain_ledger": [
            {
                "item_id": "retain_1",
                "statement": "The strongest observed estimate is 0.96 in Source A.",
                "importance": "critical",
                "omission_policy": "must_include",
                "required_terms": ["0.96"],
                "source_ids": ["source_a"],
            }
        ],
        "source_trail": [{"source_id": "source_a", "source_label": "Source A"}],
    }
    payload = {"edits": [{"target": target, "replacement": replacement, "target_section": "Decision Brief", "edit_type": "tighten_bluf"}]}

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        return ModelBackendResult(text=json.dumps(payload), backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_editorial_pass.run_model_backend", fake_backend)

    result = run_decision_memo_editorial_pass(
        memo,
        {"question": _QUESTION, "decision_briefing_packet": packet},
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["report"]["status"] == "rejected_kept_original"
    assert "editorial edit increased critical packet-retention misses" in result["report"]["issues"]
    assert "0.96" in result["memo"]


def test_editorial_pass_allows_empty_replacement_for_boilerplate_removal(monkeypatch) -> None:
    target = "*All health/medical information on this website has been reviewed and approved.*"
    memo = (
        "## Decision Brief\n\n"
        f"**Decision question:** {_QUESTION}\n\n"
        "Use the option only under the tested conditions.\n\n"
        "**Confidence:** medium\n\n"
        "## Practical Scope and Exceptions\n\n"
        f"{target}\n\n"
        "## Sources\n\n"
        "- Source A\n"
    )
    payload = {"edits": [{"target": target, "replacement": "", "target_section": "Practical Scope and Exceptions", "edit_type": "remove_source_boilerplate"}]}

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        return ModelBackendResult(text=json.dumps(payload), backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_editorial_pass.run_model_backend", fake_backend)

    result = run_decision_memo_editorial_pass(
        memo,
        {"question": _QUESTION},
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["report"]["status"] == "accepted"
    assert target not in result["memo"]


def test_final_reader_summary_includes_editorial_artifacts(tmp_path: Path) -> None:
    paths = _final_reader_output_paths(tmp_path)
    summary = _final_reader_summary_paths(
        paths,
        rewrite_result={"report": {}},
        section_rewrite_result={},
        edit_artifact_paths=reader_memo_edit_artifact_paths(tmp_path),
        editorial_result={"prompt": "prompt", "raw": "raw"},
    )

    assert summary["decision_memo_editorial_brief"] == tmp_path / "decision_memo_editorial_brief.json"
    assert summary["decision_memo_editorial_report"] == tmp_path / "decision_memo_editorial_report.json"
    assert summary["decision_memo_editorial_prompt"] == tmp_path / "decision_memo_editorial_prompt.txt"
    assert summary["decision_memo_editorial_raw"] == tmp_path / "decision_memo_editorial_raw.txt"


_QUESTION = "Should the city adopt option A?"


def _dense_opening() -> str:
    return (
        "Based on this document set, the decision should be treated as bounded rather than resolved, because the strongest support "
        "is useful but conditional, the largest caveat is that implementation quality drives the result, the evidence base mixes "
        "direct estimates with contextual warnings, the operational burden remains uncertain, and the practical choice depends on "
        "whether the decision maker values a potentially helpful intervention enough to tolerate a residual risk of weak execution "
        "and uneven transfer across settings, while still preserving enough visibility into the core uncertainty that the opening "
        "does not sound more resolved than the evidence warrants."
    )


def _dense_memo() -> str:
    return (
        "## Decision Brief\n\n"
        f"**Decision question:** {_QUESTION}\n\n"
        f"{_dense_opening()}\n\n"
        "**Confidence:** medium\n\n"
        "## What the Evidence Supports\n\n"
        "Source A reports an effect estimate and Source B reports a second estimate, 25% and 30% respectively.\n\n"
        "## What Limits the Inference\n\n"
        "The limitation is site transfer; implementation varies; monitoring varies; budgets vary; and outcome definitions vary.\n\n"
        "## Sources\n\n"
        "- Source A\n"
    )


def _memo_with_required_number(target: str) -> str:
    return (
        "## Decision Brief\n\n"
        f"**Decision question:** {_QUESTION}\n\n"
        f"{target}\n\n"
        "**Confidence:** medium\n\n"
        "## Sources\n\n"
        "- Source A\n"
    )
