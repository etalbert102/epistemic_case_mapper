from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing_section_rewrite import rewrite_reader_memo_by_section
from epistemic_case_mapper.model_backends import ModelBackendResult


def test_section_rewrite_blocks_model_calls_when_spine_projection_not_ready(monkeypatch) -> None:
    memo = "## Decision Brief\n\nUse the bounded read.\n\n## Why This Read\n\nThe evidence supports it.\n"
    appendix = "## Evidence Appendix\n\n- Source."
    scaffold = {
        "question": "Use it?",
        "confidence": "medium",
        "section_projection_readiness_report": {"status": "not_synthesis_ready"},
    }
    candidate_map = {"claims": [], "relations": []}
    calls: list[str] = []

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        calls.append(prompt)
        return ModelBackendResult(text=json.dumps({"section_markdown": "## Decision Brief\n\nShould not run."}), backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_section_rewrite.run_model_backend", fake_backend)

    result = rewrite_reader_memo_by_section(memo, appendix, scaffold, candidate_map, backend="fake", backend_timeout=30, backend_retries=0)

    assert result["report"]["status"] == "blocked_by_spine_projection_readiness"
    assert result["report"]["section_context_acceptance_status"] == "not_synthesis_ready"
    assert calls == []
