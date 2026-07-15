from __future__ import annotations

from epistemic_case_mapper.map_briefing_memo_json_polish import (
    collect_parallel_memo_ready_json_polish_proposals,
    candidate_for_json_polish_edit,
    memo_ready_json_polish_lenses,
    parse_memo_ready_json_polish_response,
)
from epistemic_case_mapper.model_backends import ModelBackendResult


def test_json_polish_parse_accepts_fenced_json() -> None:
    report = parse_memo_ready_json_polish_response(
        '```json\n{"edits": [{"target_text": "A", "replacement_text": "B"}]}\n```'
    )

    assert report["status"] == "parsed"
    assert report["edits"][0]["replacement_text"] == "B"


def test_json_polish_candidate_rejects_ambiguous_target() -> None:
    memo = "Repeated sentence [s1].\n\nRepeated sentence [s1]."
    packet = {"source_trail": [{"source_id": "s1"}]}

    result = candidate_for_json_polish_edit(
        memo,
        {"target_text": "Repeated sentence [s1].", "replacement_text": "Clearer sentence [s1]."},
        packet,
    )

    assert result["mechanically_applicable"] is False
    assert result["issue"] == "target_not_unique"


def test_json_polish_candidate_rejects_unknown_source_id() -> None:
    memo = "The finding is bounded [s1]."
    packet = {"source_trail": [{"source_id": "s1"}]}

    result = candidate_for_json_polish_edit(
        memo,
        {"target_text": memo, "replacement_text": "The finding is bounded [s99]."},
        packet,
    )

    assert result["mechanically_applicable"] is False
    assert result["issue"] == "unknown_source_id:s99"


def test_json_polish_candidate_accepts_exact_safe_replacement() -> None:
    memo = "The finding is bounded [s1]."
    packet = {"source_trail": [{"source_id": "s1"}]}

    result = candidate_for_json_polish_edit(
        memo,
        {"target_text": memo, "replacement_text": "The finding remains bounded [s1]."},
        packet,
    )

    assert result["mechanically_applicable"] is True
    assert result["memo"] == "The finding remains bounded [s1]."


def test_parallel_json_polish_collects_lens_prompts_and_dedupes_edits() -> None:
    memo = "The finding is bounded [s1]."
    packet = {"source_trail": [{"source_id": "s1"}]}
    prompts: list[str] = []

    def fake_runner(prompt: str, *args, **kwargs) -> ModelBackendResult:
        prompts.append(prompt)
        return ModelBackendResult(
            text='{"edits": [{"target_text": "The finding is bounded [s1].", "replacement_text": "The finding remains bounded [s1]."}]}',
            backend="fake",
        )

    result = collect_parallel_memo_ready_json_polish_proposals(
        memo,
        packet,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        run_model=fake_runner,
    )

    lens_ids = [lens["lens_id"] for lens in memo_ready_json_polish_lenses()]
    assert len(prompts) == len(lens_ids)
    assert all(any(f"lens_id: {lens_id}" in prompt for prompt in prompts) for lens_id in lens_ids)
    assert result["parse_report"]["edit_count_before_dedupe"] == len(lens_ids)
    assert result["parse_report"]["edit_count"] == 1
    assert result["edits"][0]["polish_lens_id"] == lens_ids[0]


def test_parallel_json_polish_uses_valid_lenses_when_one_backend_call_fails() -> None:
    memo = "The finding is bounded [s1]."
    packet = {"source_trail": [{"source_id": "s1"}]}

    def fake_runner(prompt: str, *args, **kwargs) -> ModelBackendResult:
        if "lens_id: completion_integrity" in prompt:
            raise RuntimeError("backend timeout")
        return ModelBackendResult(
            text='{"edits": [{"target_text": "The finding is bounded [s1].", "replacement_text": "The finding remains bounded [s1]."}]}',
            backend="fake",
        )

    result = collect_parallel_memo_ready_json_polish_proposals(
        memo,
        packet,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        run_model=fake_runner,
    )

    assert result["parse_report"]["status"] == "parsed"
    assert result["parse_report"]["failed_lens_count"] == 1
    assert result["parse_report"]["parsed_lens_count"] == len(memo_ready_json_polish_lenses()) - 1
    assert result["edits"]
