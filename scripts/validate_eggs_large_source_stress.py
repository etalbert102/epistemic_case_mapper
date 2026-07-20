from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PACKET_ROOT = Path("examples/eggs_large_source_stress")
CORPUS_ROOT = Path("data/cases/eggs_large_source_stress/sources/text")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the public 50-source eggs stress packet.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    failures = validate_packet(Path(args.repo_root).resolve())
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Validated 50-source eggs stress packet")
    return 0


def validate_packet(repo_root: Path) -> list[str]:
    failures: list[str] = []
    packet_root = repo_root / PACKET_ROOT
    profile = _read_json(packet_root / "run_profile.json", failures)
    generated_map = _read_json(packet_root / "generated_map.json", failures)
    readiness = _read_json(packet_root / "final_decision_readiness_report.json", failures)
    adjudication = _read_json(packet_root / "analyst_adjudication_chunk_reports.json", failures)

    _require_equal(profile, "backend", "ollama:gemma4:12b-mlx", failures)
    _require_equal(profile, "publication_ready", False, failures)
    _require_equal(profile, "publication_status", "blocked_not_decision_ready", failures)

    source_count = len(list((repo_root / CORPUS_ROOT).glob("*.txt")))
    _compare_profile(profile, "source_count", source_count, failures)
    for profile_key, map_key in (
        ("initial_claim_count", "claims"),
        ("initial_relation_count", "relations"),
        ("initial_crux_count", "crux_candidates"),
    ):
        value = generated_map.get(map_key)
        actual = len(value) if isinstance(value, list) else -1
        _compare_profile(profile, profile_key, actual, failures)

    chunks = adjudication.get("chunks")
    chunk_rows = sum(
        chunk.get("row_count", 0)
        for chunk in chunks
        if isinstance(chunk, dict) and isinstance(chunk.get("row_count"), int)
    ) if isinstance(chunks, list) else -1
    _compare_profile(profile, "analyst_adjudication_chunk_count", adjudication.get("chunk_count"), failures)
    _compare_profile(profile, "analyst_adjudication_failed_chunk_count", adjudication.get("failed_chunk_count"), failures)
    _compare_profile(profile, "analyst_adjudication_parallelism", adjudication.get("parallelism"), failures)
    _compare_profile(profile, "analyst_adjudication_row_count", chunk_rows, failures)

    _require_equal(readiness, "decision_ready", False, failures)
    _require_equal(readiness, "status", "not_decision_ready", failures)
    blocker_types = {
        issue.get("issue_type")
        for issue in readiness.get("issues", [])
        if isinstance(issue, dict) and issue.get("severity") == "blocker"
    }
    required_blockers = {
        "critical_packet_evidence_missing_from_memo",
        "source_binding_validation_failed",
        "briefing_validation_failed",
    }
    for blocker in sorted(required_blockers - blocker_types):
        failures.append(f"stress_packet_required_blocker_missing blocker={blocker}")

    blocked_memo = packet_root / "blocked_memo.md"
    if not blocked_memo.is_file() or not blocked_memo.read_text(encoding="utf-8").startswith("# Decision Memo:"):
        failures.append("stress_packet_blocked_memo_missing_or_invalid")
    return failures


def _read_json(path: Path, failures: list[str]) -> dict[str, object]:
    if not path.is_file():
        failures.append(f"stress_packet_file_missing path={path}")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        failures.append(f"stress_packet_json_invalid path={path} error={exc}")
        return {}
    if not isinstance(value, dict):
        failures.append(f"stress_packet_json_object_required path={path}")
        return {}
    return value


def _require_equal(
    value: dict[str, object], key: str, expected: object, failures: list[str]
) -> None:
    if value.get(key) != expected:
        failures.append(
            f"stress_packet_value_mismatch key={key} expected={expected!r} actual={value.get(key)!r}"
        )


def _compare_profile(
    profile: dict[str, object], key: str, actual: object, failures: list[str]
) -> None:
    if profile.get(key) != actual:
        failures.append(
            f"stress_packet_profile_mismatch key={key} expected={profile.get(key)!r} actual={actual!r}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
