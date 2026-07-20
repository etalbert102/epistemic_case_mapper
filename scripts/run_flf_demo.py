from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from judge_paths import get_judge_paths
from epistemic_case_mapper.submission_manifest import load_submission_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the judge-facing FLF prototype demo checks.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Validate checked-in examples without regenerating deterministic starter artifacts.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    manifest = load_submission_manifest(repo_root, args.manifest)
    failures: list[str] = []

    if not args.skip_build:
        for case in manifest.iter_starter_cases():
            _run([sys.executable, "scripts/build_case_map.py", "--case", case.case_path], repo_root, failures)

        for case in manifest.iter_starter_cases():
            _run(
                [
                    sys.executable,
                    "scripts/validate_case_artifact.py",
                    "--case",
                    case.case_path,
                    "--examples",
                    str(case.examples_path),
                ],
                repo_root,
                failures,
            )

    manifest_args = ["--manifest", args.manifest]
    _run([sys.executable, "scripts/validate_submission_manifest.py", *manifest_args], repo_root, failures)
    _run([sys.executable, "scripts/validate_curated_submission.py", *manifest_args], repo_root, failures)
    _run([sys.executable, "scripts/validate_live_model_examples.py", *manifest_args], repo_root, failures)
    _run([sys.executable, "scripts/validate_worked_regions.py", *manifest_args], repo_root, failures)
    _run([sys.executable, "scripts/validate_full_case_knowledge.py", *manifest_args], repo_root, failures)
    _run([sys.executable, "scripts/validate_realism_artifacts.py", *manifest_args], repo_root, failures)
    _run([sys.executable, "scripts/validate_blinded_baselines.py", *manifest_args], repo_root, failures)
    _run([sys.executable, "scripts/export_worked_region_json.py", "--check", *manifest_args], repo_root, failures)
    _run([sys.executable, "scripts/summarize_submission_artifacts.py", "--check", *manifest_args], repo_root, failures)
    _run([sys.executable, "scripts/build_tier1_review_checklist.py", "--check", *manifest_args], repo_root, failures)
    _run([sys.executable, "scripts/build_ui_data.py", "--check", *manifest_args], repo_root, failures)
    _run([sys.executable, "scripts/validate_ui.py", *manifest_args], repo_root, failures)
    _run([sys.executable, "scripts/validate_submission_references.py", *manifest_args], repo_root, failures)
    _run([sys.executable, "scripts/validate_update_demo.py", *manifest_args], repo_root, failures)
    _run([sys.executable, "scripts/judge_smoke_test.py", *manifest_args], repo_root, failures)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print("FLF demo checks passed")
    print("")
    print("Judge-facing entry points:")
    for relative_path in get_judge_paths(repo_root, args.manifest):
        print(f"- {relative_path}")
    return 0


def _run(command: list[str], repo_root: Path, failures: list[str]) -> None:
    env = {**os.environ, "PYTHONPATH": "src"}
    result = subprocess.run(command, cwd=repo_root, env=env, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        failures.append(
            f"command_failed command={' '.join(command)} stdout={result.stdout.strip()} stderr={result.stderr.strip()}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
