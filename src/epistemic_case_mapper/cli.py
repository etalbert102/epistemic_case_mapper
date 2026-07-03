from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from epistemic_case_mapper.blinded_baselines import _configs_from_manifest, build_prompt
from epistemic_case_mapper.case_initializer import init_case_package
from epistemic_case_mapper.config_profiles import (
    profile_for_id,
    profile_manifest_payload,
    recommend_config_profile,
    render_config_recommendation_markdown,
)
from epistemic_case_mapper.io import read_yaml, write_json, write_markdown
from epistemic_case_mapper.llm_stress_eval import run_llm_stress_eval
from epistemic_case_mapper.map_briefing import run_map_briefing
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.semantic_pipeline import (
    build_critique_prompt,
    build_map_prompt,
    validate_critique_candidate,
    validate_map_candidate,
)
from epistemic_case_mapper.staged_semantic_pipeline import run_staged_map
from epistemic_case_mapper.submission_manifest import SubmissionManifest, load_submission_manifest
from epistemic_case_mapper.unseen_quality import (
    quality_signals,
    quality_summary,
    init_quality_test,
    validate_quality_test,
    write_quality_risk_tasks,
)

ENGINE_ROOT = Path(__file__).resolve().parents[2]

from epistemic_case_mapper.cli_parsers import build_parser
from epistemic_case_mapper.cli_decision_packet import _run_decision_packet
from epistemic_case_mapper.cli_semantic import (
    _run_map_briefing,
    _run_semantic_critique,
    _run_semantic_map,
    _run_staged_semantic_brief,
    _run_staged_semantic_map,
    _validate_semantic_critique,
    _validate_semantic_map,
)
from epistemic_case_mapper.cli_package import (
    _check_quality,
    _init_quality,
    _prepare_package,
    _run,
    _run_many,
    _write_quality_tasks,
)


def main() -> int:
    parser = build_parser(ENGINE_ROOT)
    args = parser.parse_args()
    return _dispatch_cli(parser, args)














def _dispatch_cli(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    dispatchers = {
        "case": _dispatch_case_command,
        "package": _dispatch_package_command,
        "validate": _dispatch_validate_command,
        "export": _dispatch_export_command,
        "ui": _dispatch_ui_command,
        "baseline": _dispatch_baseline_command,
        "synthesize": _dispatch_synthesize_command,
        "review": _dispatch_review_command,
        "quality": _dispatch_quality_command,
        "eval": _dispatch_eval_command,
        "semantic": _dispatch_semantic_command,
    }
    dispatcher = dispatchers.get(args.command)
    if dispatcher:
        return dispatcher(repo_root, args)
    parser.error("unknown command")
    return 2


def _dispatch_case_command(repo_root: Path, args: argparse.Namespace) -> int:
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
            args.recommend_config,
            args.config_backend,
            args.config_timeout,
            args.config_retries,
            args.force,
        )
    if args.command == "case" and args.case_target == "recommend-config":
        return _recommend_config(
            repo_root=repo_root,
            question=args.question,
            docs=[Path(path) for path in args.docs],
            backend=args.backend,
            output_dir=args.output_dir,
            backend_timeout=args.backend_timeout,
            backend_retries=args.backend_retries,
        )
    return _unknown_cli_target("case", args.case_target)


def _dispatch_package_command(repo_root: Path, args: argparse.Namespace) -> int:
    if args.command == "package" and args.package_target == "prepare":
        return _prepare_package(repo_root, args.package)
    return _unknown_cli_target("package", args.package_target)


def _dispatch_validate_command(repo_root: Path, args: argparse.Namespace) -> int:
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
    return _unknown_cli_target("validate", args.validate_target)


def _dispatch_export_command(repo_root: Path, args: argparse.Namespace) -> int:
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
    return _unknown_cli_target("export", args.export_target)


def _dispatch_ui_command(repo_root: Path, args: argparse.Namespace) -> int:
    if args.command == "ui" and args.ui_target == "build":
        command = ["scripts/build_ui_data.py"]
        if args.check:
            command.append("--check")
        return _run(repo_root, command, args.package)
    return _unknown_cli_target("ui", args.ui_target)


def _dispatch_baseline_command(repo_root: Path, args: argparse.Namespace) -> int:
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
    return _unknown_cli_target("baseline", args.baseline_target)


def _dispatch_synthesize_command(repo_root: Path, args: argparse.Namespace) -> int:
    if args.command == "synthesize" and args.synthesize_target == "decision-packet":
        return _run_decision_packet(
            repo_root=repo_root,
            package=args.package,
            region_id=args.region,
            backend=args.backend,
            output_dir=args.output_dir,
            skip_stress_run=args.skip_stress_run,
            backend_timeout=args.backend_timeout,
            backend_retries=args.backend_retries,
        )
    if args.command == "synthesize" and args.synthesize_target == "map-briefing":
        return _run_map_briefing(
            repo_root=repo_root,
            package=args.package,
            map_path=args.map,
            quality_report_path=args.quality_report,
            question=args.question,
            backend=args.backend,
            output_dir=args.output_dir,
            region_id=args.region,
            baseline_path=args.baseline,
            max_claims=args.max_claims,
            backend_timeout=args.backend_timeout,
            backend_retries=args.backend_retries,
        )
    return _unknown_cli_target("synthesize", args.synthesize_target)


def _dispatch_review_command(repo_root: Path, args: argparse.Namespace) -> int:
    if args.command == "review" and args.review_target == "checklist":
        command = ["scripts/build_tier1_review_checklist.py"]
        if args.check:
            command.append("--check")
        return _run(repo_root, command, args.package)
    return _unknown_cli_target("review", args.review_target)


def _dispatch_quality_command(repo_root: Path, args: argparse.Namespace) -> int:
    if args.command == "quality" and args.quality_target == "init":
        return _init_quality(repo_root, args.case, args.title, args.question, args.force)
    if args.command == "quality" and args.quality_target == "check":
        return _check_quality(repo_root, args.case)
    if args.command == "quality" and args.quality_target == "gate":
        return _run_quality_gate(repo_root, args.package, args.case)
    return _unknown_cli_target("quality", args.quality_target)


def _run_quality_gate(repo_root: Path, package: str, case: str) -> int:
    result = _run_many(
        repo_root,
        [
            ["scripts/validate_submission_manifest.py"],
            ["scripts/validate_worked_regions.py"],
            ["scripts/validate_submission_references.py"],
            ["scripts/export_worked_region_json.py"],
        ],
        package,
    )
    if result != 0:
        return result
    result = _check_quality(repo_root, case)
    if result != 0:
        return result
    manifest = load_submission_manifest(repo_root, package)
    result = _write_quality_tasks(repo_root, manifest, case)
    if result != 0:
        return result
    result = _prepare_package(repo_root, package)
    if result != 0:
        return result
    return _run_many(
        repo_root,
        [
            ["scripts/validate_submission_manifest.py"],
            ["scripts/validate_worked_regions.py"],
            ["scripts/validate_submission_references.py"],
            ["scripts/export_worked_region_json.py", "--check"],
            ["scripts/build_ui_data.py", "--check"],
            ["scripts/build_tier1_review_checklist.py", "--check"],
        ],
        package,
    )


def _dispatch_eval_command(repo_root: Path, args: argparse.Namespace) -> int:
    if args.command == "eval" and args.eval_target == "llm-stress":
        return _run_llm_stress_eval(
            repo_root=repo_root,
            package=args.package,
            region_id=args.region,
            backend=args.backend,
            compare_backends=args.compare_backend,
            output_dir=args.output_dir,
            baseline_path=args.baseline_path,
            backend_timeout=args.backend_timeout,
            backend_retries=args.backend_retries,
        )
    return _unknown_cli_target("eval", args.eval_target)


def _dispatch_semantic_command(repo_root: Path, args: argparse.Namespace) -> int:
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
    if args.command == "semantic" and args.semantic_target == "staged" and args.semantic_staged_target == "map":
        return _run_staged_semantic_map(
            repo_root,
            args.package,
            args.region,
            args.backend,
            args.output,
            args.artifact_dir,
            args.chunk_lines,
            args.chunk_overlap_lines,
            args.max_chunks_per_source,
            args.max_total_chunks,
            args.max_claims_per_chunk,
            args.max_relation_pairs,
            args.relation_batch_size,
            args.backend_timeout,
            args.backend_retries,
            args.repair_quality,
            args.no_validate,
        )
    if args.command == "semantic" and args.semantic_target == "staged" and args.semantic_staged_target == "brief":
        return _run_staged_semantic_brief(
            repo_root,
            args.package,
            args.region,
            args.backend,
            args.question,
            args.output,
            args.artifact_dir,
            args.briefing_dir,
            args.chunk_lines,
            args.chunk_overlap_lines,
            args.max_chunks_per_source,
            args.max_total_chunks,
            args.max_claims_per_chunk,
            args.max_relation_pairs,
            args.relation_batch_size,
            args.briefing_max_claims,
            args.backend_timeout,
            args.backend_retries,
            args.repair_quality,
            args.no_validate,
        )
    if args.command == "semantic" and args.semantic_target == "validate" and args.semantic_validate_target == "map":
        return _validate_semantic_map(repo_root, args.package, args.region, args.path)
    if args.command == "semantic" and args.semantic_target == "validate" and args.semantic_validate_target == "critique":
        return _validate_semantic_critique(args.path)
    return _unknown_cli_target("semantic", args.semantic_target)


def _unknown_cli_target(command: str, target: object) -> int:
    print(f"unknown_cli_target command={command} target={target}", file=sys.stderr)
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
    recommend_config: bool,
    config_backend: str | None,
    config_timeout: int,
    config_retries: int,
    force: bool,
) -> int:
    if config_timeout < 1:
        print("case_init_failed config_timeout_must_be_positive", file=sys.stderr)
        return 1
    if config_retries < 0:
        print("case_init_failed config_retries_must_be_nonnegative", file=sys.stderr)
        return 1
    epistemic_config = None
    if recommend_config:
        try:
            config_run = recommend_config_profile(
                question=question,
                doc_paths=docs,
                backend=config_backend or model_backend,
                timeout_seconds=config_timeout,
                max_retries=config_retries,
            )
            selected_profile = profile_for_id(config_run.recommendation.profile_id)
            epistemic_config = profile_manifest_payload(selected_profile, config_run.recommendation)
        except (RuntimeError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
            print(f"case_init_failed config_recommendation_error={exc}", file=sys.stderr)
            return 1
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
            epistemic_config=epistemic_config,
            force=force,
        )
    except ValueError as exc:
        print(f"case_init_failed {exc}", file=sys.stderr)
        return 1
    print(f"Initialized case package case={initialized.case_id} region={initialized.region_id}")
    if epistemic_config:
        print(f"Selected epistemic config profile={epistemic_config.get('profile_id')} confidence={epistemic_config.get('confidence', 'low')}")
    for path in initialized.written_paths:
        print(f"Wrote {_display_path(repo_root, path)}")
    return 0


def _recommend_config(
    *,
    repo_root: Path,
    question: str,
    docs: list[Path],
    backend: str,
    output_dir: str | None,
    backend_timeout: int,
    backend_retries: int,
) -> int:
    if backend_timeout < 1:
        print("config_recommendation_failed backend_timeout_must_be_positive", file=sys.stderr)
        return 1
    if backend_retries < 0:
        print("config_recommendation_failed backend_retries_must_be_nonnegative", file=sys.stderr)
        return 1
    artifacts = Path(output_dir) if output_dir else Path("artifacts") / "config_recommendations" / _slugify_path_component(question)
    if not artifacts.is_absolute():
        artifacts = repo_root / artifacts
    try:
        run = recommend_config_profile(
            question=question,
            doc_paths=docs,
            backend=backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
        )
    except (RuntimeError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"config_recommendation_failed error={exc}", file=sys.stderr)
        return 1
    profile = profile_for_id(run.recommendation.profile_id)
    artifacts.mkdir(parents=True, exist_ok=True)
    write_markdown(artifacts / "config_recommendation_prompt.txt", run.prompt)
    write_markdown(artifacts / "config_recommendation_raw.txt", run.raw_output)
    write_json(
        artifacts / "config_recommendation.json",
        {
            "recommendation": run.recommendation.model_dump(),
            "epistemic_config": profile_manifest_payload(profile, run.recommendation),
        },
    )
    write_markdown(artifacts / "CONFIG_RECOMMENDATION.md", render_config_recommendation_markdown(run.recommendation, profile))
    print(
        "Config recommendation wrote "
        f"{_display_path(repo_root, artifacts / 'config_recommendation.json')} "
        f"profile={run.recommendation.profile_id} confidence={run.recommendation.confidence}"
    )
    if run.recommendation.fallback_reason:
        print(f"Fallback: {run.recommendation.fallback_reason}")
    return 0












def _run_llm_stress_eval(
    repo_root: Path,
    package: str,
    region_id: str,
    backend: str | None,
    compare_backends: list[str],
    output_dir: str | None,
    baseline_path: str | None,
    backend_timeout: int,
    backend_retries: int,
) -> int:
    if backend_timeout < 1:
        print("llm_stress_eval_failed backend_timeout_must_be_positive", file=sys.stderr)
        return 1
    if backend_retries < 0:
        print("llm_stress_eval_failed backend_retries_must_be_nonnegative", file=sys.stderr)
        return 1
    manifest = load_submission_manifest(repo_root, package)
    try:
        result = run_llm_stress_eval(
            repo_root=repo_root,
            manifest_path=package,
            region_id=region_id,
            backend=backend or manifest.default_model_backend,
            compare_backends=compare_backends,
            output_dir=output_dir,
            baseline_path=baseline_path,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
        )
    except (KeyError, RuntimeError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"llm_stress_eval_failed region={region_id} error={exc}", file=sys.stderr)
        return 1
    print(
        "LLM stress eval wrote "
        f"{_display_path(repo_root, result.json_path)} and {_display_path(repo_root, result.markdown_path)} "
        f"prompts={result.prompt_count} model_runs={result.model_run_count} "
        f"findings={result.finding_count} reference_issues={result.reference_issue_count}"
    )
    return 0
















def _display_path(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _slugify_path_component(text: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in text).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned[:80] or "config_recommendation"






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
