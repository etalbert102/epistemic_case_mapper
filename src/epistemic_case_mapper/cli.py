from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ENGINE_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ENGINE_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from run_blinded_baselines import _configs_from_manifest, build_prompt  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Epistemic Case Mapper engine CLI.")
    parser.add_argument("--repo-root", default=ENGINE_ROOT, help="Package root for relative paths.")
    parser.add_argument("--package", default="submission_manifest.yaml", help="Package manifest path.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate a package or one region.")
    validate_subparsers = validate_parser.add_subparsers(dest="validate_target", required=True)
    validate_subparsers.add_parser("package", help="Validate package wiring, worked regions, and references.")
    region_parser = validate_subparsers.add_parser("region", help="Validate one worked region.")
    region_parser.add_argument("--region", required=True)

    export_parser = subparsers.add_parser("export", help="Export package artifacts.")
    export_subparsers = export_parser.add_subparsers(dest="export_target", required=True)
    export_json = export_subparsers.add_parser("json", help="Export worked regions as JSON.")
    export_json.add_argument("--check", action="store_true")

    ui_parser = subparsers.add_parser("ui", help="Build UI artifacts.")
    ui_subparsers = ui_parser.add_subparsers(dest="ui_target", required=True)
    ui_build = ui_subparsers.add_parser("build", help="Build UI data.")
    ui_build.add_argument("--check", action="store_true")

    baseline_parser = subparsers.add_parser("baseline", help="Inspect or run baseline configs.")
    baseline_subparsers = baseline_parser.add_subparsers(dest="baseline_target", required=True)
    baseline_prompt = baseline_subparsers.add_parser("prompt", help="Render a blinded baseline prompt.")
    baseline_prompt.add_argument("--baseline", required=True, help="Baseline ID or region ID.")

    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()

    if args.command == "validate" and args.validate_target == "package":
        return _run_many(
            repo_root,
            [
                ["scripts/validate_submission_manifest.py"],
                ["scripts/validate_worked_regions.py"],
                ["scripts/validate_submission_references.py"],
            ],
            args.package,
        )
    if args.command == "validate" and args.validate_target == "region":
        return _run(repo_root, ["scripts/validate_worked_regions.py", "--region", args.region], args.package)
    if args.command == "export" and args.export_target == "json":
        command = ["scripts/export_worked_region_json.py"]
        if args.check:
            command.append("--check")
        return _run(repo_root, command, args.package)
    if args.command == "ui" and args.ui_target == "build":
        command = ["scripts/build_ui_data.py"]
        if args.check:
            command.append("--check")
        return _run(repo_root, command, args.package)
    if args.command == "baseline" and args.baseline_target == "prompt":
        return _print_baseline_prompt(repo_root, args.package, args.baseline)

    parser.error("unknown command")
    return 2


def _run_many(repo_root: Path, commands: list[list[str]], package: str) -> int:
    for command in commands:
        result = _run(repo_root, command, package)
        if result != 0:
            return result
    return 0


def _run(repo_root: Path, command: list[str], package: str) -> int:
    env = {**os.environ, "PYTHONPATH": "src"}
    result = subprocess.run(
        [sys.executable, *command, "--repo-root", str(repo_root), "--manifest", package],
        cwd=ENGINE_ROOT,
        env=env,
        text=True,
        check=False,
    )
    return result.returncode


def _print_baseline_prompt(repo_root: Path, package: str, baseline_id: str) -> int:
    configs = _configs_from_manifest(repo_root, package)
    matches = [
        config
        for config_id, config in configs.items()
        if config_id == baseline_id or config.region_id == baseline_id
    ]
    if not matches:
        choices = sorted({*configs.keys(), *(config.region_id for config in configs.values())})
        print(f"unknown_baseline baseline={baseline_id} choices={','.join(choices)}", file=sys.stderr)
        return 1
    for config in matches:
        print(build_prompt(repo_root, config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
