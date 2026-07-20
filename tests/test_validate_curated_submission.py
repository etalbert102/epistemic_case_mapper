from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_curated_submission import (
    _is_safe_relative_path,
    build_artifact_manifest,
    validate_artifact_manifest,
)
from epistemic_case_mapper.submission_manifest import load_submission_manifest


def test_checked_in_curated_artifact_manifest_is_current() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    manifest = load_submission_manifest(repo_root, "submission_manifest.yaml")

    assert validate_artifact_manifest(
        repo_root,
        "submission_manifest.yaml",
        manifest,
        repo_root / "curated_submission_manifest.json",
    ) == []


def test_curated_artifact_validator_detects_hash_mismatch(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    manifest = load_submission_manifest(repo_root, "submission_manifest.yaml")
    artifact = build_artifact_manifest(repo_root, "submission_manifest.yaml", manifest)
    first_path = artifact["primary_evidence_paths"][0]
    artifact["sha256"][first_path] = "0" * 64
    artifact_path = tmp_path / "curated.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    failures = validate_artifact_manifest(
        repo_root,
        "submission_manifest.yaml",
        manifest,
        artifact_path,
    )

    assert f"curated_artifact_hash_mismatch path={first_path}" in failures


def test_curated_artifact_paths_must_be_normalized_and_relative() -> None:
    assert _is_safe_relative_path("docs/START_HERE.md")
    assert not _is_safe_relative_path("../outside.md")
    assert not _is_safe_relative_path("/absolute.md")
    assert not _is_safe_relative_path("docs/../README.md")
