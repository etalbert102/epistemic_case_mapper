from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CLEAN_CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("worked_regions", ("scripts/validate_worked_regions.py",)),
    ("blinded_baselines", ("scripts/validate_blinded_baselines.py",)),
    ("new_source_update", ("scripts/validate_update_demo.py",)),
    ("structured_exports", ("scripts/export_worked_region_json.py", "--check")),
    ("artifact_summary", ("scripts/summarize_submission_artifacts.py", "--check")),
    ("submission_references", ("scripts/validate_submission_references.py",)),
    ("judge_path", ("scripts/judge_smoke_test.py",)),
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the inspectable proof-by-example checks and an expected-failure integrity probe."
    )
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", default="artifacts/proof_by_example/latest")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    results = [_run_check(repo_root, name, command) for name, command in CLEAN_CHECKS]
    mutation_probe = _run_invalid_source_probe(repo_root)
    passed = all(result["passed"] for result in results) and mutation_probe["passed"]

    report = {
        "schema_id": "proof_by_example_run_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "failed",
        "interpretation": (
            "These checks establish package consistency, artifact availability, and detection of one injected "
            "provenance failure. They do not establish domain correctness or human usefulness."
        ),
        "clean_checks": results,
        "expected_failure_probe": mutation_probe,
    }

    json_path = output_dir / "proof_by_example_run.json"
    markdown_path = output_dir / "PROOF_BY_EXAMPLE_RUN.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")

    for result in results:
        outcome = "PASS" if result["passed"] else "FAIL"
        print(f"{outcome} {result['name']} duration_seconds={result['duration_seconds']}")
    probe_outcome = "PASS" if mutation_probe["passed"] else "FAIL"
    print(f"{probe_outcome} expected_failure_invalid_source duration_seconds={mutation_probe['duration_seconds']}")
    print(f"Wrote {json_path.relative_to(repo_root)}")
    print(f"Wrote {markdown_path.relative_to(repo_root)}")
    return 0 if passed else 1


def _run_check(repo_root: Path, name: str, command_tail: tuple[str, ...]) -> dict[str, Any]:
    command = [sys.executable, *command_tail]
    started = time.perf_counter()
    result = subprocess.run(
        command,
        cwd=repo_root,
        env={**os.environ, "PYTHONPATH": "src"},
        text=True,
        capture_output=True,
        check=False,
    )
    duration = round(time.perf_counter() - started, 3)
    return {
        "name": name,
        "command": _display_command(command_tail),
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "duration_seconds": duration,
        "stdout_excerpt": _bounded(result.stdout),
        "stderr_excerpt": _bounded(result.stderr),
    }


def _run_invalid_source_probe(repo_root: Path) -> dict[str, Any]:
    expected_diagnostic = "unknown_claim_source claim=claim_0001 source=proof_probe_missing_source"
    with tempfile.TemporaryDirectory(prefix="ecm-proof-probe-") as temp_name:
        temp_root = Path(temp_name)
        artifact_root = temp_root / "artifacts"
        case_dir = artifact_root / "lhc_black_holes"
        case_dir.mkdir(parents=True)
        for name in ("case_map.json", "report.md", "audit.md"):
            shutil.copy2(repo_root / "examples" / "starter_snapshots" / "lhc_black_holes" / name, case_dir / name)

        case_map_path = case_dir / "case_map.json"
        payload = json.loads(case_map_path.read_text(encoding="utf-8"))
        payload["claims"][0]["source_id"] = "proof_probe_missing_source"
        case_map_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        command_tail = (
            "scripts/validate_case_artifact.py",
            "--case",
            "data/cases/lhc_black_holes/case.yaml",
            "--artifacts-root",
            str(artifact_root),
        )
        command = [sys.executable, *command_tail]
        started = time.perf_counter()
        result = subprocess.run(
            command,
            cwd=repo_root,
            env={**os.environ, "PYTHONPATH": "src"},
            text=True,
            capture_output=True,
            check=False,
        )
        duration = round(time.perf_counter() - started, 3)
        combined = "\n".join((result.stdout, result.stderr))
        detected = result.returncode != 0 and expected_diagnostic in combined
        return {
            "name": "invalid_source_reference",
            "mutation": "Changed claim_0001.source_id to proof_probe_missing_source in a temporary artifact copy.",
            "command": _display_command(command_tail),
            "passed": detected,
            "validator_rejected_artifact": result.returncode != 0,
            "expected_diagnostic_found": expected_diagnostic in combined,
            "expected_diagnostic": expected_diagnostic,
            "returncode": result.returncode,
            "duration_seconds": duration,
            "stdout_excerpt": _bounded(result.stdout),
            "stderr_excerpt": _bounded(result.stderr),
        }


def _display_command(command_tail: tuple[str, ...]) -> str:
    return "PYTHONPATH=src python3 " + " ".join(command_tail)


def _bounded(value: str, limit: int = 1200) -> str:
    stripped = value.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 3] + "..."


def _render_markdown(report: dict[str, Any]) -> str:
    rows = []
    for result in report["clean_checks"]:
        rows.append(
            f"| {result['name']} | {'pass' if result['passed'] else 'fail'} | "
            f"`{result['duration_seconds']}` | `{result['command']}` |"
        )
    probe = report["expected_failure_probe"]
    rows.append(
        f"| expected failure: invalid source reference | {'pass' if probe['passed'] else 'fail'} | "
        f"`{probe['duration_seconds']}` | `{probe['command']}` |"
    )
    return "\n".join(
        (
            "# Proof-By-Example Run",
            "",
            f"Status: `{report['status']}`",
            "",
            f"Created: `{report['created_at_utc']}`",
            "",
            "## Results",
            "",
            "| Check | Result | Seconds | Command |",
            "| --- | --- | ---: | --- |",
            *rows,
            "",
            "## Expected-Failure Probe",
            "",
            probe["mutation"],
            "",
            f"Expected diagnostic: `{probe['expected_diagnostic']}`",
            "",
            "## Interpretation Boundary",
            "",
            report["interpretation"],
            "",
            "Durations are operational observations from this run, not stable performance benchmarks.",
            "",
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

