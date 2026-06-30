from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from epistemic_case_mapper.submission_manifest import SubmissionManifest, load_submission_manifest

FORBIDDEN_TERMS = (
    "decision-space " + "compression",
    "decision space " + "compression",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the lightweight FLF reproducibility gate.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    parser.add_argument(
        "--include-worked-regions",
        action="store_true",
        help="Also require final worked-region artifacts to pass their validator.",
    )
    parser.add_argument(
        "--include-blinded-baselines",
        action="store_true",
        help="Also require checked-in blinded baseline artifacts to pass their validator.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    manifest = load_submission_manifest(repo_root, args.manifest)
    failures: list[str] = []

    _check_required_docs(repo_root, manifest, failures)
    _check_terms(repo_root, failures)
    _run_tests(repo_root, failures)
    _run([sys.executable, "scripts/validate_submission_manifest.py"], repo_root, failures)
    for case in manifest.iter_starter_cases():
        case_path = case.case_path
        examples_path = str(case.examples_path)
        _run([sys.executable, "scripts/build_case_map.py", "--case", case_path], repo_root, failures)
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
    if args.include_worked_regions:
        _run([sys.executable, "scripts/validate_worked_regions.py"], repo_root, failures)
    _run([sys.executable, "scripts/validate_full_case_knowledge.py"], repo_root, failures)
    _run([sys.executable, "scripts/validate_realism_artifacts.py"], repo_root, failures)
    if args.include_blinded_baselines:
        _run([sys.executable, "scripts/validate_blinded_baselines.py"], repo_root, failures)
    _run([sys.executable, "scripts/export_worked_region_json.py", "--check"], repo_root, failures)
    _run([sys.executable, "scripts/summarize_submission_artifacts.py", "--check"], repo_root, failures)
    _run([sys.executable, "scripts/build_tier1_review_checklist.py", "--check"], repo_root, failures)
    _run([sys.executable, "scripts/build_ui_data.py", "--check"], repo_root, failures)
    _run([sys.executable, "scripts/validate_ui.py"], repo_root, failures)
    _run([sys.executable, "scripts/validate_submission_references.py"], repo_root, failures)
    _run([sys.executable, "scripts/validate_update_demo.py"], repo_root, failures)
    _run([sys.executable, "scripts/judge_smoke_test.py"], repo_root, failures)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("FLF reproducibility gate passed")
    return 0


def _check_required_docs(repo_root: Path, manifest: SubmissionManifest, failures: list[str]) -> None:
    for relative_path in manifest.required_docs:
        if not (repo_root / relative_path).exists():
            failures.append(f"missing_required_doc path={relative_path}")


def _check_terms(repo_root: Path, failures: list[str]) -> None:
    search_roots = ("README.md", "docs", "src", "scripts")
    for relative_root in search_roots:
        root = repo_root / relative_root
        if not root.exists():
            continue
        paths = [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()]
        for path in paths:
            if path.suffix not in {"", ".md", ".py", ".yaml", ".yml", ".json", ".toml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            for term in FORBIDDEN_TERMS:
                if term in text:
                    failures.append(f"forbidden_term path={path.relative_to(repo_root)} term={term}")


def _run_tests(repo_root: Path, failures: list[str]) -> None:
    _run([sys.executable, "-m", "pytest", "-q"], repo_root, failures)


def _run(command: list[str], repo_root: Path, failures: list[str]) -> None:
    env = {**os.environ, "PYTHONPATH": "src"}
    result = subprocess.run(command, cwd=repo_root, env=env, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        failures.append(
            f"command_failed command={' '.join(command)} stdout={result.stdout.strip()} stderr={result.stderr.strip()}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
