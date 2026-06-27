from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


CASES = (
    ("data/cases/lhc_black_holes/case.yaml", "examples/lhc_black_holes"),
    ("data/cases/eggs/case.yaml", "examples/eggs"),
)

JUDGE_PATHS = (
    "docs/SUBMISSION_PACKET.md",
    "docs/FLF_JUDGE_INDEX.md",
    "docs/FLF_JUDGE_WALKTHROUGH.md",
    "docs/FLF_BEFORE_AFTER_COMPARISON.md",
    "docs/FLF_CONTEST_CRITERIA_SELF_ASSESSMENT.md",
    "docs/FAILURE_MODES_AND_COUNTEREXAMPLES.md",
    "docs/FLF_WORKED_JUDGE_EXAMPLE.md",
    "docs/NEW_SOURCE_UPDATE_DEMO.md",
    "docs/FLF_SUBMISSION_DRAFT.md",
    "docs/ARCHITECTURE.md",
    "docs/FULL_CASE_KNOWLEDGE_BASE_PLAN.md",
    "docs/INVESTIGATOR_WORKFLOW_PLAYBOOK.md",
    "docs/OPERATIONAL_REALISM_AUDIT.md",
    "docs/SUBMISSION_ARTIFACT_SUMMARY.md",
    "docs/SUBMISSION_LIMITATIONS.md",
    "ui/index.html",
    "docs/review/LHC_HUMAN_AUDIT_PACKET.md",
    "docs/review/EGGS_HUMAN_AUDIT_PACKET.md",
    "docs/review/LHC_HUMAN_AUDIT_CHECKLIST.csv",
    "docs/review/EGGS_HUMAN_AUDIT_CHECKLIST.csv",
    "docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md",
    "examples/lhc_black_holes/full_case_index.md",
    "examples/lhc_black_holes/full_case_map.md",
    "examples/lhc_black_holes/full_case_flat_synthesis_baseline.md",
    "examples/lhc_black_holes/worked_region_public_risk_framing_map.md",
    "examples/lhc_black_holes/investigator_task_queue.md",
    "examples/eggs/full_case_index.md",
    "examples/eggs/full_case_map.md",
    "examples/eggs/full_case_flat_synthesis_baseline.md",
    "examples/eggs/investigator_task_queue.md",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the judge-facing FLF prototype demo checks.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Validate checked-in examples without regenerating deterministic starter artifacts.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    failures: list[str] = []

    if not args.skip_build:
        for case_path, _examples_path in CASES:
            _run([sys.executable, "scripts/build_case_map.py", "--case", case_path], repo_root, failures)

    for case_path, examples_path in CASES:
        _run(
            [
                sys.executable,
                "scripts/validate_case_artifact.py",
                "--case",
                case_path,
                "--examples",
                examples_path,
            ],
            repo_root,
            failures,
        )

    _run([sys.executable, "scripts/validate_worked_regions.py"], repo_root, failures)
    _run([sys.executable, "scripts/validate_full_case_knowledge.py"], repo_root, failures)
    _run([sys.executable, "scripts/validate_realism_artifacts.py"], repo_root, failures)
    _run([sys.executable, "scripts/validate_blinded_baselines.py"], repo_root, failures)
    _run([sys.executable, "scripts/export_worked_region_json.py", "--check"], repo_root, failures)
    _run([sys.executable, "scripts/summarize_submission_artifacts.py", "--check"], repo_root, failures)
    _run([sys.executable, "scripts/build_ui_data.py", "--check"], repo_root, failures)
    _run([sys.executable, "scripts/validate_ui.py"], repo_root, failures)
    _run([sys.executable, "scripts/validate_submission_references.py"], repo_root, failures)
    _run([sys.executable, "scripts/judge_smoke_test.py"], repo_root, failures)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print("FLF demo checks passed")
    print("")
    print("Judge-facing entry points:")
    for relative_path in JUDGE_PATHS:
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
