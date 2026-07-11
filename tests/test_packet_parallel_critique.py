from __future__ import annotations

import json
import time

from epistemic_case_mapper.map_briefing_packet_critique_index import build_packet_critique_index, build_packet_critique_shards
from epistemic_case_mapper.map_briefing_packet_parallel_critique import run_parallel_packet_critique
from epistemic_case_mapper.map_briefing_packet_refinement import PacketCritiqueOutput, _adjudication_report, run_packet_critique


class FakeResult:
    def __init__(self, text: str) -> None:
        self.text = text


def _packet(count: int = 10) -> dict:
    return {
        "decision_question": "Should the city adopt option A?",
        "answer_frame": {"default_answer": "Adopt option A with safeguards."},
        "evidence_bundles": [
            {
                "bundle_id": f"bundle_{index:03d}",
                "decision_role": "strongest_support",
                "directionality": "supports" if index != 4 else "challenges",
                "claim": f"Evidence item {index} bears on option A.",
                "why_it_matters": "It affects the decision.",
                "section_targets": ["Decision evidence"],
                "source_ids": [f"s{index}"],
                "source_labels": [f"Source {index}"],
            }
            for index in range(1, count + 1)
        ],
        "must_retain_ledger": [],
        "coverage_report": {},
    }


def _critique_json(*, target: str = "", role: str = "counterweight") -> str:
    edits = []
    if target:
        edits.append({"edit_type": "relabel", "target_ids": [target], "recommended_role": role, "rationale": "Direction challenges the answer."})
    return json.dumps(
        {
            "schema_id": "packet_critique_v1",
            "packet_sufficiency_judgment": "needs_repair" if edits else "ready",
            "recommended_packet_edits": edits,
            "bundle_role_checks": [
                {
                    "bundle_id": target,
                    "current_role": "strongest_support",
                    "directionality": "challenges",
                    "role_matches_claim_and_direction": False,
                    "recommended_role": role,
                    "rationale": "Direction challenges the answer.",
                }
            ]
            if target
            else [],
        }
    )


def test_packet_critique_index_shards_large_packet() -> None:
    index = build_packet_critique_index(_packet(13), {"status": "warning"})
    shards = build_packet_critique_shards(index, max_bundles_per_shard=6)

    assert index["bundle_count"] == 13
    assert len(shards) == 3
    assert [len(row["bundles"]) for row in shards] == [6, 6, 1]
    assert shards[0]["bundle_ids"][0] == "bundle_001"


def test_parallel_packet_critique_merges_and_verifies_recommendations() -> None:
    calls = []

    def fake_backend(prompt: str, *args, **kwargs) -> FakeResult:
        calls.append(prompt)
        if "Verify whether this critique recommendation" in prompt:
            return FakeResult(
                json.dumps(
                    {
                        "schema_id": "packet_critique_verification_v1",
                        "verification_decision": "accept",
                        "rationale": "The affected target is directionally inconsistent.",
                    }
                )
            )
        if "compact global critique" in prompt:
            return FakeResult(_critique_json())
        if "bundle_004" in prompt:
            return FakeResult(_critique_json(target="bundle_004"))
        return FakeResult(_critique_json())

    result = run_parallel_packet_critique(
        _packet(10),
        {"status": "warning"},
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        run_backend=fake_backend,
        critique_schema=PacketCritiqueOutput,
        adjudicate=_adjudication_report,
    )

    adjudication = result["adjudication_report"]
    assert result["report"]["status"] == "parsed"
    assert result["report"]["method"] == "parallel_hierarchical_packet_critique"
    assert result["report"]["parallelism"]["local_shard_count"] == 2
    assert adjudication["accepted_count"] == 1
    assert adjudication["accepted_recommendations"][0]["target_ids"] == ["bundle_004"]
    assert any("bundle_004" in prompt and "Verify whether" in prompt for prompt in calls)


def test_parallel_packet_critique_shard_timeout_degrades_to_partial_report() -> None:
    def fake_backend(prompt: str, *args, **kwargs) -> FakeResult:
        if "bundle_001" in prompt and "Critique this shard" in prompt:
            raise RuntimeError("timeout")
        if "Verify whether this critique recommendation" in prompt:
            return FakeResult(
                json.dumps(
                    {
                        "schema_id": "packet_critique_verification_v1",
                        "verification_decision": "warning_only",
                        "rationale": "Plausible but not enough for automatic edit.",
                    }
                )
            )
        return FakeResult(_critique_json(target="bundle_010"))

    result = run_parallel_packet_critique(
        _packet(10),
        {"status": "warning"},
        backend="fake",
        backend_timeout=1,
        backend_retries=0,
        run_backend=fake_backend,
        critique_schema=PacketCritiqueOutput,
        adjudicate=_adjudication_report,
    )

    assert result["report"]["status"] == "parsed"
    assert result["report"]["parallelism"]["local_shards_failed"] == 1
    assert result["adjudication_report"]["accepted_count"] == 0
    assert result["adjudication_report"]["warning_only_count"] >= 1


def test_parallel_packet_critique_uses_parallel_workers() -> None:
    starts = []

    def fake_backend(prompt: str, *args, **kwargs) -> FakeResult:
        if "Critique this shard" in prompt:
            starts.append(time.monotonic())
            time.sleep(0.05)
        if "Verify whether this critique recommendation" in prompt:
            return FakeResult(
                json.dumps(
                    {
                        "schema_id": "packet_critique_verification_v1",
                        "verification_decision": "accept",
                        "rationale": "Verified.",
                    }
                )
            )
        return FakeResult(_critique_json())

    started = time.monotonic()
    result = run_parallel_packet_critique(
        _packet(18),
        {"status": "warning"},
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        run_backend=fake_backend,
        critique_schema=PacketCritiqueOutput,
        adjudicate=_adjudication_report,
    )

    assert result["report"]["parallelism"]["local_shard_count"] == 3
    assert time.monotonic() - started < 0.14
    assert len(starts) == 3


def test_run_packet_critique_selects_parallel_path_for_large_packets(monkeypatch) -> None:
    events = []

    def fake_backend(prompt: str, *args, **kwargs) -> FakeResult:
        if "Verify whether this critique recommendation" in prompt:
            return FakeResult(
                json.dumps(
                    {
                        "schema_id": "packet_critique_verification_v1",
                        "verification_decision": "accept",
                        "rationale": "Verified.",
                    }
                )
            )
        return FakeResult(_critique_json())

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_packet_refinement.run_model_backend", fake_backend)

    result = run_packet_critique(
        _packet(10),
        {"status": "warning"},
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        progress=lambda stage, status, details=None: events.append({"stage": stage, "status": status, "details": details or {}}),
    )

    assert result["report"]["method"] == "parallel_hierarchical_packet_critique"
    assert result["report"]["parallelism"]["local_shard_count"] == 2
    substages = [(event["details"].get("substage"), event["status"]) for event in events]
    assert ("packet_critique_index", "completed") in substages
    assert ("packet_critique_local_shards", "started") in substages
    assert ("packet_critique_local_shards", "completed") in substages
    assert ("packet_critique_global", "started") in substages
    assert ("packet_critique_global", "completed") in substages
