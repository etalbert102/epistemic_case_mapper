from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from epistemic_case_mapper.case_initializer import init_case_package
from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.semantic_pipeline import (
    build_critique_prompt,
    build_map_prompt,
    validate_critique_candidate,
    validate_map_candidate,
)
from epistemic_case_mapper.submission_manifest import SubmissionManifest, load_submission_manifest
from epistemic_case_mapper.unseen_quality import (
    quality_signals,
    quality_summary,
    init_quality_test,
    validate_quality_test,
    write_quality_risk_tasks,
)

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

    case_parser = subparsers.add_parser("case", help="Initialize reusable case packages from documents.")
    case_subparsers = case_parser.add_subparsers(dest="case_target", required=True)
    case_init = case_subparsers.add_parser("init", help="Create a package skeleton from documents and a question.")
    case_init.add_argument("--case-id", required=True, help="Stable case slug.")
    case_init.add_argument("--title", required=True, help="Human-readable case title.")
    case_init.add_argument("--question", required=True, help="Case question.")
    case_init.add_argument("--docs", nargs="+", required=True, help="Document files to import.")
    case_init.add_argument("--region", help="Worked-region ID. Defaults to <case-id>_initial_region.")
    case_init.add_argument("--model-backend", default="prompt", help="Default backend: prompt, command:<cmd>, or ollama:<model>.")
    case_init.add_argument("--force", action="store_true", help="Overwrite initializer-managed files.")

    package_parser = subparsers.add_parser("package", help="Prepare package-facing generated assets.")
    package_subparsers = package_parser.add_subparsers(dest="package_target", required=True)
    package_subparsers.add_parser("prepare", help="Build UI data, copy UI shell, checklist, and reviewer start page.")

    validate_parser = subparsers.add_parser("validate", help="Validate a package or one region.")
    validate_subparsers = validate_parser.add_subparsers(dest="validate_target", required=True)
    validate_subparsers.add_parser("package", help="Validate package wiring, worked regions, and references.")
    region_parser = validate_subparsers.add_parser("region", help="Validate one worked region.")
    region_parser.add_argument("--region", required=True)

    export_parser = subparsers.add_parser("export", help="Export package artifacts.")
    export_subparsers = export_parser.add_subparsers(dest="export_target", required=True)
    export_json = export_subparsers.add_parser("json", help="Export worked regions as JSON.")
    export_json.add_argument("--check", action="store_true")
    export_region = export_subparsers.add_parser("region", help="Export one worked region as JSON.")
    export_region.add_argument("--region", required=True)
    export_region.add_argument("--check", action="store_true")

    ui_parser = subparsers.add_parser("ui", help="Build UI artifacts.")
    ui_subparsers = ui_parser.add_subparsers(dest="ui_target", required=True)
    ui_build = ui_subparsers.add_parser("build", help="Build UI data.")
    ui_build.add_argument("--check", action="store_true")

    baseline_parser = subparsers.add_parser("baseline", help="Inspect or run baseline configs.")
    baseline_subparsers = baseline_parser.add_subparsers(dest="baseline_target", required=True)
    baseline_prompt = baseline_subparsers.add_parser("prompt", help="Render a blinded baseline prompt.")
    baseline_prompt.add_argument("--baseline", required=True, help="Baseline ID or region ID.")
    baseline_run = baseline_subparsers.add_parser("run", help="Run or dry-run blinded baseline generation.")
    baseline_run.add_argument("--region", help="Region ID or baseline ID.")
    baseline_run.add_argument("--case", help="Case key grouping selector.")
    baseline_run.add_argument("--model", default="gemma4:e4b")
    baseline_run.add_argument("--output-label")
    baseline_run.add_argument("--dry-run", action="store_true")

    review_parser = subparsers.add_parser("review", help="Build review artifacts.")
    review_subparsers = review_parser.add_subparsers(dest="review_target", required=True)
    review_checklist = review_subparsers.add_parser("checklist", help="Build Tier 1 review checklist.")
    review_checklist.add_argument("--check", action="store_true")

    quality_parser = subparsers.add_parser("quality", help="Initialize and check unseen-case quality reviews.")
    quality_subparsers = quality_parser.add_subparsers(dest="quality_target", required=True)
    quality_init = quality_subparsers.add_parser("init", help="Create unseen-case quality review templates.")
    quality_init.add_argument("--case", required=True, help="Unseen-case slug.")
    quality_init.add_argument("--title", required=True, help="Human-readable case title.")
    quality_init.add_argument("--question", required=True, help="Case question.")
    quality_init.add_argument("--force", action="store_true", help="Overwrite existing quality review files.")
    quality_check = quality_subparsers.add_parser("check", help="Check completed unseen-case quality review files.")
    quality_check.add_argument("--case", required=True, help="Unseen-case slug.")
    quality_gate = quality_subparsers.add_parser(
        "gate",
        help="Prepare package assets, run package gates, then check unseen-case quality review files.",
    )
    quality_gate.add_argument("--case", required=True, help="Unseen-case slug.")

    semantic_parser = subparsers.add_parser("semantic", help="Build and validate model-assisted semantic work.")
    semantic_subparsers = semantic_parser.add_subparsers(dest="semantic_target", required=True)
    semantic_prompt = semantic_subparsers.add_parser("prompt", help="Render source-bounded prompts for LLM work.")
    semantic_prompt_subparsers = semantic_prompt.add_subparsers(dest="semantic_prompt_target", required=True)
    semantic_map_prompt = semantic_prompt_subparsers.add_parser("map", help="Render a JSON map-generation prompt.")
    semantic_map_prompt.add_argument("--region", required=True)
    semantic_critique_prompt = semantic_prompt_subparsers.add_parser("critique", help="Render a JSON critique prompt.")
    semantic_critique_prompt.add_argument("--region", required=True)
    semantic_critique_prompt.add_argument("--map-path", help="Candidate map path. Defaults to the region map path.")
    semantic_run = semantic_subparsers.add_parser("run", help="Run source-bounded prompts through a swappable model backend.")
    semantic_run_subparsers = semantic_run.add_subparsers(dest="semantic_run_target", required=True)
    semantic_map_run = semantic_run_subparsers.add_parser("map", help="Generate or render a candidate JSON worked map.")
    semantic_map_run.add_argument("--region", required=True)
    semantic_map_run.add_argument("--backend", help="Override manifest default backend.")
    semantic_map_run.add_argument("--output", help="Output path. Defaults to prompt file for prompt backend, else region map path.")
    semantic_map_run.add_argument("--no-validate", action="store_true", help="Skip semantic JSON validation.")
    semantic_critique_run = semantic_run_subparsers.add_parser("critique", help="Generate or render semantic critique JSON.")
    semantic_critique_run.add_argument("--region", required=True)
    semantic_critique_run.add_argument("--backend", help="Override manifest default backend.")
    semantic_critique_run.add_argument("--map-path", help="Candidate map path. Defaults to the region map path.")
    semantic_critique_run.add_argument("--output", help="Output path. Defaults to prompt file for prompt backend, else artifacts/semantic.")
    semantic_critique_run.add_argument("--no-validate", action="store_true", help="Skip semantic JSON validation.")
    semantic_validate = semantic_subparsers.add_parser("validate", help="Validate model-produced semantic JSON.")
    semantic_validate_subparsers = semantic_validate.add_subparsers(dest="semantic_validate_target", required=True)
    semantic_map_validate = semantic_validate_subparsers.add_parser("map", help="Validate a candidate JSON worked map.")
    semantic_map_validate.add_argument("--region", required=True)
    semantic_map_validate.add_argument("--path", required=True)
    semantic_critique_validate = semantic_validate_subparsers.add_parser("critique", help="Validate a candidate JSON critique.")
    semantic_critique_validate.add_argument("--path", required=True)

    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()

    if args.command == "case" and args.case_target == "init":
        return _init_case_package(
            repo_root,
            args.package,
            args.case_id,
            args.title,
            args.question,
            [Path(path) for path in args.docs],
            args.region,
            args.model_backend,
            args.force,
        )
    if args.command == "package" and args.package_target == "prepare":
        return _prepare_package(repo_root, args.package)
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
    if args.command == "export" and args.export_target == "region":
        command = ["scripts/export_worked_region_json.py", "--region", args.region]
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
    if args.command == "baseline" and args.baseline_target == "run":
        command = ["scripts/run_blinded_baselines.py", "--model", args.model]
        if args.region:
            command.extend(["--region", args.region])
        if args.case:
            command.extend(["--case", args.case])
        if args.output_label:
            command.extend(["--output-label", args.output_label])
        if args.dry_run:
            command.append("--dry-run")
        return _run(repo_root, command, args.package)
    if args.command == "review" and args.review_target == "checklist":
        command = ["scripts/build_tier1_review_checklist.py"]
        if args.check:
            command.append("--check")
        return _run(repo_root, command, args.package)
    if args.command == "quality" and args.quality_target == "init":
        return _init_quality(repo_root, args.case, args.title, args.question, args.force)
    if args.command == "quality" and args.quality_target == "check":
        return _check_quality(repo_root, args.case)
    if args.command == "quality" and args.quality_target == "gate":
        result = _run_many(
            repo_root,
            [
                ["scripts/validate_submission_manifest.py"],
                ["scripts/validate_worked_regions.py"],
                ["scripts/validate_submission_references.py"],
                ["scripts/export_worked_region_json.py"],
            ],
            args.package,
        )
        if result != 0:
            return result
        result = _check_quality(repo_root, args.case)
        if result != 0:
            return result
        manifest = load_submission_manifest(repo_root, args.package)
        result = _write_quality_tasks(repo_root, manifest, args.case)
        if result != 0:
            return result
        result = _prepare_package(repo_root, args.package)
        if result != 0:
            return result
        result = _run_many(
            repo_root,
            [
                ["scripts/validate_submission_manifest.py"],
                ["scripts/validate_worked_regions.py"],
                ["scripts/validate_submission_references.py"],
                ["scripts/export_worked_region_json.py", "--check"],
                ["scripts/build_ui_data.py", "--check"],
                ["scripts/build_tier1_review_checklist.py", "--check"],
            ],
            args.package,
        )
        if result != 0:
            return result
        return 0
    if args.command == "semantic" and args.semantic_target == "prompt" and args.semantic_prompt_target == "map":
        print(build_map_prompt(repo_root, args.package, args.region), end="")
        return 0
    if args.command == "semantic" and args.semantic_target == "prompt" and args.semantic_prompt_target == "critique":
        print(build_critique_prompt(repo_root, args.package, args.region, args.map_path), end="")
        return 0
    if args.command == "semantic" and args.semantic_target == "run" and args.semantic_run_target == "map":
        return _run_semantic_map(repo_root, args.package, args.region, args.backend, args.output, args.no_validate)
    if args.command == "semantic" and args.semantic_target == "run" and args.semantic_run_target == "critique":
        return _run_semantic_critique(
            repo_root,
            args.package,
            args.region,
            args.backend,
            args.map_path,
            args.output,
            args.no_validate,
        )
    if args.command == "semantic" and args.semantic_target == "validate" and args.semantic_validate_target == "map":
        return _validate_semantic_map(repo_root, args.package, args.region, args.path)
    if args.command == "semantic" and args.semantic_target == "validate" and args.semantic_validate_target == "critique":
        return _validate_semantic_critique(args.path)

    parser.error("unknown command")
    return 2


def _init_case_package(
    repo_root: Path,
    package: str,
    case_id: str,
    title: str,
    question: str,
    docs: list[Path],
    region: str | None,
    model_backend: str,
    force: bool,
) -> int:
    try:
        initialized = init_case_package(
            repo_root=repo_root,
            package_path=package,
            case_id=case_id,
            title=title,
            question=question,
            doc_paths=docs,
            region_id=region,
            model_backend=model_backend,
            force=force,
        )
    except ValueError as exc:
        print(f"case_init_failed {exc}", file=sys.stderr)
        return 1
    print(f"Initialized case package case={initialized.case_id} region={initialized.region_id}")
    for path in initialized.written_paths:
        print(f"Wrote {_display_path(repo_root, path)}")
    return 0


def _run_semantic_map(
    repo_root: Path,
    package: str,
    region_id: str,
    backend: str | None,
    output: str | None,
    no_validate: bool,
) -> int:
    manifest = load_submission_manifest(repo_root, package)
    try:
        region = manifest.region_for_id(region_id)
    except KeyError:
        print(f"semantic_run_failed unknown_region={region_id}", file=sys.stderr)
        return 1
    prompt = build_map_prompt(repo_root, package, region_id)
    return _write_backend_result(
        repo_root=repo_root,
        region_id=region_id,
        prompt=prompt,
        backend=backend or manifest.default_model_backend,
        output=output,
        default_candidate_path=region.map_path,
        prompt_path=f"prompts/{region_id}/map_prompt.txt",
        validate=lambda path: _validate_semantic_map(repo_root, package, region_id, str(path)),
        no_validate=no_validate,
    )


def _run_semantic_critique(
    repo_root: Path,
    package: str,
    region_id: str,
    backend: str | None,
    map_path: str | None,
    output: str | None,
    no_validate: bool,
) -> int:
    manifest = load_submission_manifest(repo_root, package)
    try:
        manifest.region_for_id(region_id)
    except KeyError:
        print(f"semantic_run_failed unknown_region={region_id}", file=sys.stderr)
        return 1
    prompt = build_critique_prompt(repo_root, package, region_id, map_path)
    return _write_backend_result(
        repo_root=repo_root,
        region_id=region_id,
        prompt=prompt,
        backend=backend or manifest.default_model_backend,
        output=output,
        default_candidate_path=f"artifacts/semantic/{region_id}_critique.json",
        prompt_path=f"prompts/{region_id}/critique_prompt.txt",
        validate=lambda path: _validate_semantic_critique(str(path)),
        no_validate=no_validate,
    )


def _write_backend_result(
    repo_root: Path,
    region_id: str,
    prompt: str,
    backend: str,
    output: str | None,
    default_candidate_path: str,
    prompt_path: str,
    validate,
    no_validate: bool,
) -> int:
    try:
        result = run_model_backend(prompt, backend)
    except (RuntimeError, ValueError) as exc:
        print(f"semantic_run_failed region={region_id} backend={backend} error={exc}", file=sys.stderr)
        return 1
    relative_output = output or (prompt_path if result.prompt_only else default_candidate_path)
    output_path = Path(relative_output)
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.text, encoding="utf-8")
    print(f"Wrote {_display_path(repo_root, output_path)} backend={result.backend}")
    if result.prompt_only:
        print("Prompt backend selected; no JSON validation run.")
        return 0
    if no_validate:
        print("Semantic validation skipped.")
        return 0
    return validate(output_path)


def _display_path(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


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


def _prepare_package(repo_root: Path, package: str) -> int:
    result = _run_many(
        repo_root,
        [
            ["scripts/build_ui_data.py"],
            ["scripts/build_tier1_review_checklist.py"],
        ],
        package,
    )
    if result != 0:
        return result
    _copy_ui_shell(repo_root)
    manifest = load_submission_manifest(repo_root, package)
    _write_reviewer_start(repo_root, manifest)
    print("Prepared package assets")
    return 0


def _copy_ui_shell(repo_root: Path) -> None:
    target_dir = repo_root / "ui"
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "styles.css", "app.js"):
        shutil.copyfile(ENGINE_ROOT / "ui" / name, target_dir / name)


def _write_reviewer_start(repo_root: Path, manifest: SubmissionManifest) -> None:
    output_path = repo_root / "docs/review/REVIEWER_START_HERE.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {manifest.package_label} Reviewer Start",
        "",
        "Status: `generated`",
        "",
        "Use this page to orient to the package artifacts generated by the Epistemic Case Mapper engine.",
        "",
        "## Fast Path",
        "",
    ]
    if manifest.ui_hero.links:
        for link in manifest.ui_hero.links:
            lines.append(f"- {link.label}: `{link.path}`")
    else:
        for path in manifest.judge_paths:
            lines.append(f"- `{path}`")
    lines.extend(["", "## Cases", ""])
    for case in manifest.cases:
        case_manifest = CaseManifest.model_validate(read_yaml(repo_root / case.case_path))
        lines.append(f"### {case.label}")
        lines.append("")
        lines.append(f"- Question: {case_manifest.question}")
        lines.append(f"- Case manifest: `{case.case_path}`")
        for region in case.worked_regions:
            lines.append(f"- Worked region `{region.region_id}`: `{region.map_path}`")
            lines.append(f"- Erosion audit `{region.region_id}`: `{region.audit_path}`")
        if case.task_queue is not None:
            lines.append(f"- Task queue: `{case.task_queue.path}`")
        quality = quality_summary(repo_root, case.case_key)
        if quality["paths"]["scorecard"]:
            lines.append(f"- Quality scorecard: `{quality['paths']['scorecard']}`")
        if quality["paths"]["riskTasks"]:
            lines.append(f"- Generated quality tasks: `{quality['paths']['riskTasks']}`")
        signals = quality_signals(repo_root, case.case_key, case_manifest)
        if signals:
            lines.append("")
            lines.append("Quality warnings:")
            for signal in signals[:8]:
                lines.append(f"- {signal.severity}: {signal.label} - {signal.evidence}")
        lines.append("")
    lines.extend(
        [
            "## Generated Assets",
            "",
            "- Static UI: `ui/index.html`",
            "- UI data: `ui/data.json`",
            "- Tier 1 checklist: `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv`",
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _init_quality(repo_root: Path, case_slug: str, title: str, question: str, force: bool) -> int:
    try:
        written = init_quality_test(repo_root, case_slug, title, question, force=force)
    except ValueError as exc:
        print(f"quality_init_failed {exc}", file=sys.stderr)
        return 1
    for path in written:
        print(f"Wrote {path.relative_to(repo_root).as_posix()}")
    if not written:
        print("No quality files changed")
    return 0


def _check_quality(repo_root: Path, case_slug: str) -> int:
    try:
        failures = validate_quality_test(repo_root, case_slug)
    except ValueError as exc:
        print(f"quality_check_failed {exc}", file=sys.stderr)
        return 1
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"Validated unseen-case quality review case={case_slug}")
    return 0


def _write_quality_tasks(repo_root: Path, manifest: SubmissionManifest, case_slug: str) -> int:
    try:
        case = manifest.case_for_key(case_slug)
    except KeyError:
        if len(manifest.cases) != 1:
            print(f"quality_task_failed unknown_case={case_slug}", file=sys.stderr)
            return 1
        case = manifest.cases[0]
    case_manifest = CaseManifest.model_validate(read_yaml(repo_root / case.case_path))
    path = write_quality_risk_tasks(repo_root, case_slug, case_manifest)
    print(f"Wrote {path.relative_to(repo_root).as_posix()}")
    return 0


def _validate_semantic_map(repo_root: Path, package: str, region_id: str, path: str) -> int:
    failures = validate_map_candidate(repo_root, package, region_id, Path(path))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"Validated semantic map candidate region={region_id} path={path}")
    return 0


def _validate_semantic_critique(path: str) -> int:
    failures = validate_critique_candidate(Path(path))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"Validated semantic critique candidate path={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
