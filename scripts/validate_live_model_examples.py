from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath


SCHEMA_ID = "live_model_example_artifact_manifest_v1"
PACKET_ROOT = Path("examples/live_model_runs")
ARTIFACT_MANIFEST = PACKET_ROOT / "artifact_manifest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the paired live-model map examples.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    parser.add_argument("--write", action="store_true", help="Regenerate the packet hash manifest.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    packet_root = repo_root / PACKET_ROOT
    artifact_manifest_path = repo_root / ARTIFACT_MANIFEST
    if args.write:
        artifact_manifest_path.write_text(
            json.dumps(build_artifact_manifest(packet_root), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {ARTIFACT_MANIFEST}")
        return 0

    failures = validate_packet(repo_root, args.manifest)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Validated paired live-model examples")
    return 0


def build_artifact_manifest(packet_root: Path) -> dict[str, object]:
    paths = sorted(_packet_paths(packet_root))
    return {
        "schema_id": SCHEMA_ID,
        "interpretation": (
            "Hashes bind live-run outputs, transcripts, reports, and packet guides; "
            "recorded artifact paths may be normalized to repository-root-relative form."
        ),
        "sha256": {path: _sha256(packet_root / path) for path in paths},
    }


def validate_packet(repo_root: Path, submission_manifest_path: str) -> list[str]:
    packet_root = repo_root / PACKET_ROOT
    artifact_manifest_path = repo_root / ARTIFACT_MANIFEST
    failures = _validate_hashes(packet_root, artifact_manifest_path)

    success_root = packet_root / "eggs_success"
    failure_root = packet_root / "lhc_failure"
    success_summary = _read_json(success_root / "records/run_summary.json", failures)
    success_progress = _read_json(success_root / "records/pipeline_progress.json", failures)
    success_map = _read_json(success_root / "generated_map.json", failures)
    failure_summary = _read_json(failure_root / "records/run_summary.json", failures)
    failure_progress = _read_json(failure_root / "records/pipeline_progress.json", failures)
    failure_map = _read_json(failure_root / "generated_map.json", failures)

    _require_equal(success_summary, "backend", "ollama:gemma4:12b-mlx", "success_backend", failures)
    _require_equal(success_summary, "quality_status", "usable_with_review", "success_quality", failures)
    _require_equal(success_summary, "quality_score", 78, "success_score", failures)
    _require_equal(success_progress, "backend_error_count", 0, "success_backend_errors", failures)
    _require_map_counts(success_map, 26, 22, 15, "success", failures)

    _require_equal(failure_summary, "backend", "ollama:gemma4:12b-mlx", "failure_backend", failures)
    _require_equal(failure_summary, "quality_status", "needs_repair", "failure_quality", failures)
    _require_equal(failure_summary, "quality_score", 0, "failure_score", failures)
    _require_equal(failure_progress, "backend_error_count", 2, "failure_backend_errors", failures)
    _require_map_counts(failure_map, 1, 0, 0, "failure", failures)

    _validate_transcript_set(success_root / "transcripts/claim_sources", 7, "success_claim", failures)
    _validate_transcript_set(success_root / "transcripts/relation_batches", 5, "success_relation", failures)
    _validate_transcript_set(success_root / "transcripts/map_repair_relations", 8, "success_repair", failures)
    _validate_transcript_set(failure_root / "transcripts/claim_sources", 5, "failure_claim", failures)

    success_result = _semantic_validation(
        repo_root,
        submission_manifest_path,
        "eggs_observational_vs_rct",
        success_root / "generated_map.json",
    )
    if success_result.returncode != 0:
        failures.append(f"live_success_semantic_validation_failed stderr={success_result.stderr.strip()}")

    failure_result = _semantic_validation(
        repo_root,
        submission_manifest_path,
        "lhc_cosmic_ray_argument",
        failure_root / "generated_map.json",
    )
    expected_failure_markers = {
        "semantic_map_missing_relations",
        "semantic_map_too_few_cruxes count=0",
        "semantic_map_evidence_check_too_short rows=1",
    }
    if failure_result.returncode == 0:
        failures.append("live_failure_semantic_validation_unexpectedly_passed")
    for marker in sorted(expected_failure_markers):
        if marker not in failure_result.stderr:
            failures.append(f"live_failure_missing_expected_diagnostic marker={marker}")
    return failures


def _validate_hashes(packet_root: Path, artifact_manifest_path: Path) -> list[str]:
    if not artifact_manifest_path.is_file():
        return [f"live_artifact_manifest_missing path={ARTIFACT_MANIFEST}"]
    artifact = json.loads(artifact_manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    if artifact.get("schema_id") != SCHEMA_ID:
        failures.append(f"live_artifact_schema_invalid value={artifact.get('schema_id')!r}")
    hashes = artifact.get("sha256")
    if not isinstance(hashes, dict):
        return [*failures, "live_artifact_hashes_invalid"]
    expected_paths = _packet_paths(packet_root)
    listed_paths = set(hashes)
    for path in sorted(expected_paths - listed_paths):
        failures.append(f"live_artifact_hash_missing path={path}")
    for path in sorted(listed_paths - expected_paths):
        failures.append(f"live_artifact_hash_unexpected path={path}")
    for path, digest in sorted(hashes.items()):
        if not _is_safe_relative_path(path):
            failures.append(f"live_artifact_path_unsafe path={path}")
            continue
        absolute_path = packet_root / path
        if not absolute_path.is_file():
            failures.append(f"live_artifact_file_missing path={path}")
        elif digest != _sha256(absolute_path):
            failures.append(f"live_artifact_hash_mismatch path={path}")
    return failures


def _packet_paths(packet_root: Path) -> set[str]:
    return {
        path.relative_to(packet_root).as_posix()
        for path in packet_root.rglob("*")
        if path.is_file() and path.name != ARTIFACT_MANIFEST.name
    }


def _read_json(path: Path, failures: list[str]) -> dict[str, object]:
    if not path.is_file():
        failures.append(f"live_example_file_missing path={path}")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        failures.append(f"live_example_json_invalid path={path} error={exc}")
        return {}
    return value if isinstance(value, dict) else {}


def _require_equal(
    value: dict[str, object], key: str, expected: object, label: str, failures: list[str]
) -> None:
    if value.get(key) != expected:
        failures.append(f"live_example_{label} expected={expected!r} actual={value.get(key)!r}")


def _require_map_counts(
    value: dict[str, object], claims: int, relations: int, cruxes: int, label: str, failures: list[str]
) -> None:
    for key, expected in (("claims", claims), ("relations", relations), ("crux_candidates", cruxes)):
        actual = len(value.get(key, [])) if isinstance(value.get(key), list) else -1
        if actual != expected:
            failures.append(f"live_example_{label}_{key}_count expected={expected} actual={actual}")


def _validate_transcript_set(path: Path, expected: int, label: str, failures: list[str]) -> None:
    prompts = list(path.glob("*_prompt.txt"))
    raws = list(path.glob("*_raw.txt"))
    canonicals = list(path.glob("*_canonical.json"))
    counts = (len(prompts), len(raws), len(canonicals))
    if counts != (expected, expected, expected):
        failures.append(f"live_example_{label}_transcript_counts expected={expected} actual={counts}")


def _semantic_validation(
    repo_root: Path, manifest: str, region: str, map_path: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "epistemic_case_mapper.cli",
            "--repo-root",
            str(repo_root),
            "--package",
            manifest,
            "semantic",
            "validate",
            "map",
            "--region",
            region,
            "--path",
            str(map_path),
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )


def _is_safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts and str(path) == value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
