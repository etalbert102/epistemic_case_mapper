from __future__ import annotations

from pathlib import Path

from epistemic_case_mapper.submission_manifest import load_submission_manifest


def get_judge_paths(repo_root: Path | None = None, manifest_path: str = "submission_manifest.yaml") -> tuple[str, ...]:
    root = repo_root or Path(__file__).resolve().parents[1]
    return tuple(load_submission_manifest(root, manifest_path).judge_paths)


JUDGE_PATHS = get_judge_paths()
