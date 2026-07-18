from __future__ import annotations

import json
from pathlib import Path

from epistemic_case_mapper.staged_semantic_progress import PipelineProgress


def test_pipeline_progress_tracks_multiple_active_backend_calls(tmp_path: Path) -> None:
    progress = PipelineProgress(tmp_path / "pipeline_progress.json", backend_timeout=30)
    progress.start_stage("claim_extraction", total_items=2)

    first = progress.start_backend_call(stage="claim_extraction", item_id="source_a", call_id="call_a", item_index=1, total_items=2)
    second = progress.start_backend_call(stage="claim_extraction", item_id="source_b", call_id="call_b", item_index=2, total_items=2)

    payload = json.loads((tmp_path / "pipeline_progress.json").read_text(encoding="utf-8"))
    assert first == "call_a"
    assert second == "call_b"
    assert payload["active_backend_call_count"] == 2
    assert sorted(payload["active_backend_calls"]) == ["call_a", "call_b"]
    assert "active_backend_calls=2" in payload["monitor_summary"]

    progress.finish_backend_call(call_id="call_a", status="completed", output_claim_count=2)
    payload = json.loads((tmp_path / "pipeline_progress.json").read_text(encoding="utf-8"))
    assert payload["active_backend_call_count"] == 1
    assert sorted(payload["active_backend_calls"]) == ["call_b"]
    assert payload["last_backend_call"]["item_id"] == "source_a"
    assert payload["recent_backend_calls"][-1]["item_id"] == "source_a"

    progress.finish_backend_call(call_id="call_b", status="backend_error", error="timeout")
    payload = json.loads((tmp_path / "pipeline_progress.json").read_text(encoding="utf-8"))
    assert payload["active_backend_call_count"] == 0
    assert payload["active_backend_calls"] == {}
    assert payload["backend_error_count"] == 1
    assert payload["recent_backend_calls"][-1]["status"] == "backend_error"
