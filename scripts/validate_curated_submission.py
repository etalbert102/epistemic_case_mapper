from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath

from epistemic_case_mapper.submission_manifest import SubmissionManifest, load_submission_manifest


SCHEMA_ID = "curated_submission_artifact_manifest_v1"
DEFAULT_ARTIFACT_MANIFEST = "curated_submission_manifest.json"
CURATION_SUPPORT_PATHS = {
    "LICENSE",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "pyproject.toml",
    "scripts/run_blinded_baselines.py",
    "scripts/run_flf_demo.py",
    "scripts/run_investigator_challenge.py",
    "scripts/validate_live_model_examples.py",
    "scripts/validate_worked_regions.py",
    "examples/live_model_runs/artifact_manifest.json",
    "ui/data.json",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the curated FLF submission evidence boundary.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    parser.add_argument("--artifact-manifest", default=DEFAULT_ARTIFACT_MANIFEST)
    parser.add_argument("--write", action="store_true", help="Regenerate hashes from the configured evidence set.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    manifest = load_submission_manifest(repo_root, args.manifest)
    artifact_path = repo_root / args.artifact_manifest
    if args.write:
        artifact = build_artifact_manifest(repo_root, args.manifest, manifest)
        artifact_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.artifact_manifest}")
        return 0

    failures = validate_artifact_manifest(repo_root, args.manifest, manifest, artifact_path)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    count = len(_required_primary_paths(repo_root, args.manifest, manifest))
    print(f"Validated curated submission artifacts files={count}")
    return 0


def build_artifact_manifest(
    repo_root: Path,
    submission_manifest_path: str,
    manifest: SubmissionManifest,
) -> dict[str, object]:
    paths = sorted(_required_primary_paths(repo_root, submission_manifest_path, manifest))
    return {
        "schema_id": SCHEMA_ID,
        "interpretation": (
            "Hashes bind the curated judge path and its primary source-grounded evidence. "
            "Illustrative same-context baselines are intentionally outside this evidence set."
        ),
        "primary_evidence_paths": paths,
        "sha256": {path: _sha256(repo_root / path) for path in paths},
    }


def validate_artifact_manifest(
    repo_root: Path,
    submission_manifest_path: str,
    manifest: SubmissionManifest,
    artifact_path: Path,
) -> list[str]:
    if not artifact_path.is_file():
        return [f"curated_artifact_manifest_missing path={artifact_path.relative_to(repo_root)}"]
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"curated_artifact_manifest_invalid error={exc}"]

    failures: list[str] = []
    if artifact.get("schema_id") != SCHEMA_ID:
        failures.append(f"curated_artifact_schema_invalid value={artifact.get('schema_id')!r}")
    paths = artifact.get("primary_evidence_paths")
    hashes = artifact.get("sha256")
    if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
        return [*failures, "curated_artifact_paths_invalid"]
    if not isinstance(hashes, dict) or not all(
        isinstance(path, str) and isinstance(digest, str) for path, digest in hashes.items()
    ):
        return [*failures, "curated_artifact_hashes_invalid"]

    expected = _required_primary_paths(repo_root, submission_manifest_path, manifest)
    listed = set(paths)
    for path in sorted(expected - listed):
        failures.append(f"curated_artifact_required_path_missing path={path}")
    for path in sorted(listed - expected):
        failures.append(f"curated_artifact_unexpected_path path={path}")
    if listed != set(hashes):
        failures.append("curated_artifact_path_hash_keys_mismatch")

    illustrative_paths = {region.baseline_path for region in manifest.iter_worked_regions()}
    for path in sorted(listed & illustrative_paths):
        failures.append(f"illustrative_baseline_marked_primary path={path}")

    for path in sorted(listed):
        if not _is_safe_relative_path(path):
            failures.append(f"curated_artifact_path_unsafe path={path}")
            continue
        absolute_path = repo_root / path
        if not absolute_path.is_file():
            failures.append(f"curated_artifact_file_missing path={path}")
            continue
        expected_digest = hashes.get(path)
        if expected_digest != _sha256(absolute_path):
            failures.append(f"curated_artifact_hash_mismatch path={path}")
    return failures


def _required_primary_paths(
    repo_root: Path, submission_manifest_path: str, manifest: SubmissionManifest
) -> set[str]:
    paths = {
        submission_manifest_path,
        *CURATION_SUPPORT_PATHS,
        *manifest.judge_paths,
        *manifest.required_docs,
    }
    for case in manifest.cases:
        paths.add(case.case_path)
    for region in manifest.iter_worked_regions():
        paths.update({region.definition_path, region.map_path, region.output_json_path, region.audit_path})
        if region.best_path:
            paths.add(region.best_path)
        if region.blinded_baseline:
            paths.add(region.blinded_baseline.output_path)
            paths.update(span.path for span in region.blinded_baseline.spans)
            output_dir = (repo_root / region.blinded_baseline.output_path).parent
            paths.update(
                path.relative_to(repo_root).as_posix()
                for path in output_dir.glob("blinded_flat_synthesis_baseline_*.md")
            )
    return paths


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
