from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

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
    case_init.add_argument("--recommend-config", action="store_true", help="Use the model backend to select an epistemic config profile for this packet.")
    case_init.add_argument("--config-backend", help="Backend for config recommendation. Defaults to --model-backend.")
    case_init.add_argument("--config-timeout", type=int, default=60, help="Seconds allowed for config recommendation backend call.")
    case_init.add_argument("--config-retries", type=int, default=0, help="Retries for config recommendation backend failures.")
    case_init.add_argument("--force", action="store_true", help="Overwrite initializer-managed files.")
    case_config = case_subparsers.add_parser("recommend-config", help="Recommend an epistemic config profile for documents and a question.")
    case_config.add_argument("--question", required=True, help="Decision-relevant question.")
    case_config.add_argument("--docs", nargs="+", required=True, help="Document files to inspect.")
    case_config.add_argument("--backend", default="prompt", help="Backend: prompt, command:<cmd>, or ollama:<model>.")
    case_config.add_argument("--output-dir", help="Artifact directory. Defaults to artifacts/config_recommendations/<question-slug>.")
    case_config.add_argument("--backend-timeout", type=int, default=60)
    case_config.add_argument("--backend-retries", type=int, default=0)

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

    synthesize_parser = subparsers.add_parser("synthesize", help="Build product-facing synthesis artifacts.")
    synthesize_subparsers = synthesize_parser.add_subparsers(dest="synthesize_target", required=True)
    decision_packet = synthesize_subparsers.add_parser(
        "decision-packet",
        help="Build a hybrid stress-assisted decision packet for one worked region.",
    )
    decision_packet.add_argument("--region", required=True)
    decision_packet.add_argument("--backend", help="Backend for stress, synthesis, and repair. Defaults to manifest default_model_backend.")
    decision_packet.add_argument("--output-dir", help="Artifact directory. Defaults to artifacts/decision_packets/<region>.")
    decision_packet.add_argument("--skip-stress-run", action="store_true", help="Reuse an existing stress report when present.")
    decision_packet.add_argument("--backend-timeout", type=int, default=120)
    decision_packet.add_argument("--backend-retries", type=int, default=0)
    map_briefing = synthesize_subparsers.add_parser(
        "map-briefing",
        help="Build a readable decision briefing from a generated epistemic map and quality report.",
    )
    map_briefing.add_argument("--map", required=True, help="Generated map JSON path.")
    map_briefing.add_argument("--quality-report", required=True, help="Map quality report JSON path.")
    map_briefing.add_argument("--question", required=True, help="Decision-relevant question to brief.")
    map_briefing.add_argument("--backend", help="Backend for briefing generation. Defaults to manifest default_model_backend.")
    map_briefing.add_argument("--output-dir", help="Artifact directory. Defaults to artifacts/map_briefings/<map-stem>.")
    map_briefing.add_argument("--region", help="Optional region ID used only to load source display names.")
    map_briefing.add_argument("--max-claims", type=int, default=18, help="Briefing map claim budget after source-preserving prioritization.")
    map_briefing.add_argument("--backend-timeout", type=int, default=120)
    map_briefing.add_argument("--backend-retries", type=int, default=0)

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

    eval_parser = subparsers.add_parser("eval", help="Run automated quality and robustness evaluations.")
    eval_subparsers = eval_parser.add_subparsers(dest="eval_target", required=True)
    llm_stress = eval_subparsers.add_parser(
        "llm-stress",
        help="Run LLM-assisted baseline, critique, relation, and metamorphic stress checks.",
    )
    llm_stress.add_argument("--region", required=True)
    llm_stress.add_argument("--backend", help="Primary backend. Defaults to manifest default_model_backend.")
    llm_stress.add_argument(
        "--compare-backend",
        action="append",
        default=[],
        help="Additional backend to run on the same prompts. May be passed multiple times.",
    )
    llm_stress.add_argument("--output-dir", help="Artifact directory. Defaults to artifacts/llm_stress_eval/<region>.")
    llm_stress.add_argument("--baseline-path", help="Override flat baseline path.")
    llm_stress.add_argument("--backend-timeout", type=int, default=90)
    llm_stress.add_argument("--backend-retries", type=int, default=0)

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
    semantic_staged = semantic_subparsers.add_parser("staged", help="Run chunked staged semantic mapping.")
    semantic_staged_subparsers = semantic_staged.add_subparsers(dest="semantic_staged_target", required=True)
    semantic_staged_map = semantic_staged_subparsers.add_parser("map", help="Extract claims by chunk, build relations, and assemble a map.")
    semantic_staged_map.add_argument("--region", required=True)
    semantic_staged_map.add_argument("--backend", help="Override manifest default backend.")
    semantic_staged_map.add_argument("--output", help="Output path. Defaults to the region map path.")
    semantic_staged_map.add_argument("--artifact-dir", help="Directory for intermediate prompts and model outputs.")
    semantic_staged_map.add_argument("--chunk-lines", type=int, default=40)
    semantic_staged_map.add_argument("--chunk-overlap-lines", type=int, default=0)
    semantic_staged_map.add_argument("--max-chunks-per-source", type=int, default=0, help="0 means no per-source chunk cap.")
    semantic_staged_map.add_argument("--max-total-chunks", type=int, default=0, help="0 means no total chunk cap.")
    semantic_staged_map.add_argument("--max-claims-per-chunk", type=int, default=4)
    semantic_staged_map.add_argument("--max-relation-pairs", type=int, default=12)
    semantic_staged_map.add_argument("--relation-batch-size", type=int, default=4)
    semantic_staged_map.add_argument("--backend-timeout", type=int, default=90, help="Seconds allowed for each backend call.")
    semantic_staged_map.add_argument("--backend-retries", type=int, default=1, help="Retries for transient backend failures.")
    semantic_staged_map.add_argument("--repair-quality", action="store_true", help="Run the map-quality repair prompt and accept it if it validates and preserves/improves quality.")
    semantic_staged_map.add_argument("--no-validate", action="store_true", help="Skip final semantic JSON validation.")
    semantic_staged_brief = semantic_staged_subparsers.add_parser(
        "brief",
        help="Run staged mapping and produce a readable map-anchored decision briefing.",
    )
    semantic_staged_brief.add_argument("--region", required=True)
    semantic_staged_brief.add_argument("--backend", help="Override manifest default backend.")
    semantic_staged_brief.add_argument("--question", help="Decision question. Defaults to the case manifest question.")
    semantic_staged_brief.add_argument("--output", help="Generated map path. Defaults to artifacts/semantic/<region>/staged_brief/generated_map.json.")
    semantic_staged_brief.add_argument("--artifact-dir", help="Directory for staged-map intermediate artifacts.")
    semantic_staged_brief.add_argument("--briefing-dir", help="Directory for briefing artifacts.")
    semantic_staged_brief.add_argument("--chunk-lines", type=int, default=40)
    semantic_staged_brief.add_argument("--chunk-overlap-lines", type=int, default=0)
    semantic_staged_brief.add_argument("--max-chunks-per-source", type=int, default=0, help="0 means no per-source chunk cap.")
    semantic_staged_brief.add_argument("--max-total-chunks", type=int, default=0, help="0 means no total chunk cap.")
    semantic_staged_brief.add_argument("--max-claims-per-chunk", type=int, default=4)
    semantic_staged_brief.add_argument("--max-relation-pairs", type=int, default=12)
    semantic_staged_brief.add_argument("--relation-batch-size", type=int, default=4)
    semantic_staged_brief.add_argument("--briefing-max-claims", type=int, default=18)
    semantic_staged_brief.add_argument("--backend-timeout", type=int, default=90, help="Seconds allowed for each backend call.")
    semantic_staged_brief.add_argument("--backend-retries", type=int, default=1, help="Retries for transient backend failures.")
    semantic_staged_brief.add_argument("--repair-quality", action="store_true", default=True, help="Run quality repair before briefing.")
    semantic_staged_brief.add_argument("--no-repair-quality", action="store_false", dest="repair_quality", help="Skip quality repair.")
    semantic_staged_brief.add_argument("--no-validate", action="store_true", help="Skip final semantic JSON validation.")
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
            max_claims=args.max_claims,
            backend_timeout=args.backend_timeout,
            backend_retries=args.backend_retries,
        )
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


def _run_staged_semantic_map(
    repo_root: Path,
    package: str,
    region_id: str,
    backend: str | None,
    output: str | None,
    artifact_dir: str | None,
    chunk_lines: int,
    chunk_overlap_lines: int,
    max_chunks_per_source: int,
    max_total_chunks: int,
    max_claims_per_chunk: int,
    max_relation_pairs: int,
    relation_batch_size: int,
    backend_timeout: int,
    backend_retries: int,
    repair_quality: bool,
    no_validate: bool,
) -> int:
    if chunk_lines < 1:
        print("semantic_staged_failed chunk_lines_must_be_positive", file=sys.stderr)
        return 1
    if chunk_overlap_lines < 0 or chunk_overlap_lines >= chunk_lines:
        print("semantic_staged_failed chunk_overlap_lines_must_be_nonnegative_and_smaller_than_chunk_lines", file=sys.stderr)
        return 1
    if max_chunks_per_source < 0:
        print("semantic_staged_failed max_chunks_per_source_must_be_nonnegative", file=sys.stderr)
        return 1
    if max_total_chunks < 0:
        print("semantic_staged_failed max_total_chunks_must_be_nonnegative", file=sys.stderr)
        return 1
    if max_claims_per_chunk < 1:
        print("semantic_staged_failed max_claims_per_chunk_must_be_positive", file=sys.stderr)
        return 1
    if max_relation_pairs < 1:
        print("semantic_staged_failed max_relation_pairs_must_be_positive", file=sys.stderr)
        return 1
    if relation_batch_size < 1:
        print("semantic_staged_failed relation_batch_size_must_be_positive", file=sys.stderr)
        return 1
    if backend_timeout < 1:
        print("semantic_staged_failed backend_timeout_must_be_positive", file=sys.stderr)
        return 1
    if backend_retries < 0:
        print("semantic_staged_failed backend_retries_must_be_nonnegative", file=sys.stderr)
        return 1
    manifest = load_submission_manifest(repo_root, package)
    try:
        result = run_staged_map(
            repo_root=repo_root,
            manifest_path=package,
            region_id=region_id,
            backend=backend or manifest.default_model_backend,
            output_path=output,
            artifact_dir=artifact_dir,
            chunk_lines=chunk_lines,
            chunk_overlap_lines=chunk_overlap_lines,
            max_chunks_per_source=max_chunks_per_source or None,
            max_total_chunks=max_total_chunks or None,
            max_claims_per_chunk=max_claims_per_chunk,
            max_relation_pairs=max_relation_pairs,
            relation_batch_size=relation_batch_size,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            validate=not no_validate,
            repair_quality=repair_quality,
        )
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"semantic_staged_failed region={region_id} error={exc}", file=sys.stderr)
        return 1
    print(
        "Staged map wrote "
        f"{_display_path(repo_root, result.output_path)} "
        f"claims={result.claim_count} relations={result.relation_count} "
        f"rejected_claims={result.rejected_claim_count} rejected_relations={result.rejected_relation_count} "
        f"quality={result.quality_status} "
        f"repair_ran={str(result.quality_repair_ran).lower()} repair_accepted={str(result.quality_repaired).lower()} "
        f"artifacts={_display_path(repo_root, result.artifact_dir)}"
    )
    print(f"Map quality report: {_display_path(repo_root, result.artifact_dir / 'map_quality_report.json')}")
    if result.failures:
        for failure in result.failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    if no_validate:
        print("Semantic validation skipped.")
    else:
        print(f"Validated staged semantic map region={region_id} path={result.output_path}")
    return 0


def _run_map_briefing(
    *,
    repo_root: Path,
    package: str,
    map_path: str,
    quality_report_path: str,
    question: str,
    backend: str | None,
    output_dir: str | None,
    region_id: str | None,
    max_claims: int,
    backend_timeout: int,
    backend_retries: int,
) -> int:
    if max_claims < 1:
        print("map_briefing_failed max_claims_must_be_positive", file=sys.stderr)
        return 1
    if backend_timeout < 1:
        print("map_briefing_failed backend_timeout_must_be_positive", file=sys.stderr)
        return 1
    if backend_retries < 0:
        print("map_briefing_failed backend_retries_must_be_nonnegative", file=sys.stderr)
        return 1
    try:
        manifest = load_submission_manifest(repo_root, package) if (backend is None or region_id) else None
        if backend is None and manifest is None:
            print("map_briefing_failed backend_required_without_manifest", file=sys.stderr)
            return 1
        selected_backend = backend or manifest.default_model_backend
        result = run_map_briefing(
            repo_root=repo_root,
            map_path=map_path,
            quality_report_path=quality_report_path,
            question=question,
            backend=selected_backend,
            output_dir=output_dir,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            source_titles=_source_titles_for_region(repo_root, manifest, region_id) if manifest and region_id else None,
            max_claims=max_claims,
        )
    except (RuntimeError, ValueError, FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
        print(f"map_briefing_failed error={exc}", file=sys.stderr)
        return 1
    print(
        "Map briefing wrote "
        f"{_display_path(repo_root, result.briefing_path)} "
        f"backend={result.backend} "
        f"quality={result.map_quality_status} "
        f"confidence={result.model_confidence}->{result.calibrated_confidence}"
    )
    print(f"Summary: {_display_path(repo_root, result.summary_path)}")
    print(f"Prompt: {_display_path(repo_root, result.prompt_path)}")
    return 0


def _run_staged_semantic_brief(
    repo_root: Path,
    package: str,
    region_id: str,
    backend: str | None,
    question: str | None,
    output: str | None,
    artifact_dir: str | None,
    briefing_dir: str | None,
    chunk_lines: int,
    chunk_overlap_lines: int,
    max_chunks_per_source: int,
    max_total_chunks: int,
    max_claims_per_chunk: int,
    max_relation_pairs: int,
    relation_batch_size: int,
    briefing_max_claims: int,
    backend_timeout: int,
    backend_retries: int,
    repair_quality: bool,
    no_validate: bool,
) -> int:
    if chunk_lines < 1:
        print("semantic_staged_brief_failed chunk_lines_must_be_positive", file=sys.stderr)
        return 1
    if chunk_overlap_lines < 0 or chunk_overlap_lines >= chunk_lines:
        print("semantic_staged_brief_failed chunk_overlap_lines_must_be_nonnegative_and_smaller_than_chunk_lines", file=sys.stderr)
        return 1
    if max_chunks_per_source < 0:
        print("semantic_staged_brief_failed max_chunks_per_source_must_be_nonnegative", file=sys.stderr)
        return 1
    if max_total_chunks < 0:
        print("semantic_staged_brief_failed max_total_chunks_must_be_nonnegative", file=sys.stderr)
        return 1
    if max_claims_per_chunk < 1:
        print("semantic_staged_brief_failed max_claims_per_chunk_must_be_positive", file=sys.stderr)
        return 1
    if max_relation_pairs < 1:
        print("semantic_staged_brief_failed max_relation_pairs_must_be_positive", file=sys.stderr)
        return 1
    if relation_batch_size < 1:
        print("semantic_staged_brief_failed relation_batch_size_must_be_positive", file=sys.stderr)
        return 1
    if briefing_max_claims < 1:
        print("semantic_staged_brief_failed briefing_max_claims_must_be_positive", file=sys.stderr)
        return 1
    if backend_timeout < 1:
        print("semantic_staged_brief_failed backend_timeout_must_be_positive", file=sys.stderr)
        return 1
    if backend_retries < 0:
        print("semantic_staged_brief_failed backend_retries_must_be_nonnegative", file=sys.stderr)
        return 1
    manifest = load_submission_manifest(repo_root, package)
    try:
        region = manifest.region_for_id(region_id)
        selected_backend = backend or manifest.default_model_backend
        map_output = output or Path("artifacts") / "semantic" / region_id / "staged_brief" / "generated_map.json"
        map_artifacts = artifact_dir or Path("artifacts") / "semantic" / region_id / "staged_brief" / "map"
        result = run_staged_map(
            repo_root=repo_root,
            manifest_path=package,
            region_id=region_id,
            backend=selected_backend,
            output_path=map_output,
            artifact_dir=map_artifacts,
            chunk_lines=chunk_lines,
            chunk_overlap_lines=chunk_overlap_lines,
            max_chunks_per_source=max_chunks_per_source or None,
            max_total_chunks=max_total_chunks or None,
            max_claims_per_chunk=max_claims_per_chunk,
            max_relation_pairs=max_relation_pairs,
            relation_batch_size=relation_batch_size,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            validate=not no_validate,
            repair_quality=repair_quality,
        )
        if result.failures:
            for failure in result.failures:
                print(f"FAIL: {failure}", file=sys.stderr)
            return 1
        briefing_result = run_map_briefing(
            repo_root=repo_root,
            map_path=result.output_path,
            quality_report_path=result.artifact_dir / "map_quality_report.json",
            question=question or _case_question_for_region(repo_root, manifest, region),
            backend=selected_backend,
            output_dir=briefing_dir or Path("artifacts") / "semantic" / region_id / "staged_brief" / "briefing",
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            source_titles=_source_titles_for_region(repo_root, manifest, region_id),
            max_claims=briefing_max_claims,
        )
    except (RuntimeError, ValueError, FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
        print(f"semantic_staged_brief_failed region={region_id} error={exc}", file=sys.stderr)
        return 1
    print(
        "Staged brief wrote "
        f"{_display_path(repo_root, briefing_result.briefing_path)} "
        f"map={_display_path(repo_root, result.output_path)} "
        f"claims={result.claim_count} relations={result.relation_count} "
        f"quality={result.quality_status} "
        f"confidence={briefing_result.model_confidence}->{briefing_result.calibrated_confidence}"
    )
    print(f"Briefing summary: {_display_path(repo_root, briefing_result.summary_path)}")
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


def _run_decision_packet(
    repo_root: Path,
    package: str,
    region_id: str,
    backend: str | None,
    output_dir: str | None,
    skip_stress_run: bool,
    backend_timeout: int,
    backend_retries: int,
) -> int:
    if backend_timeout < 1:
        print("decision_packet_failed backend_timeout_must_be_positive", file=sys.stderr)
        return 1
    if backend_retries < 0:
        print("decision_packet_failed backend_retries_must_be_nonnegative", file=sys.stderr)
        return 1

    from run_synthesis_uplift_eval import (  # noqa: PLC0415
        _clean_reader_packet_metadata,
        _compile_rewrite_requirements,
        _deterministic_patch_synthesis,
        _deterministic_requirement_coverage,
        _needs_repair,
        _parse_losses,
        _read,
        _read_map_payload,
        _repair_synthesis_prompt,
        _requirement_dict,
        _requirements_markdown,
        _run_synthesis_backend,
        _synthesis_prompt,
    )

    manifest = load_submission_manifest(repo_root, package)
    try:
        region = manifest.region_for_id(region_id)
    except KeyError:
        print(f"decision_packet_failed unknown_region={region_id}", file=sys.stderr)
        return 1

    selected_backend = backend or manifest.default_model_backend
    artifacts = Path(output_dir) if output_dir else Path("artifacts") / "decision_packets" / region_id
    if not artifacts.is_absolute():
        artifacts = repo_root / artifacts
    artifacts.mkdir(parents=True, exist_ok=True)

    stress_dir = artifacts / "stress"
    stress_json = stress_dir / "llm_stress_eval.json"
    try:
        if not skip_stress_run or not stress_json.exists():
            run_llm_stress_eval(
                repo_root=repo_root,
                manifest_path=package,
                region_id=region_id,
                backend=selected_backend,
                output_dir=stress_dir,
                timeout_seconds=backend_timeout,
                max_retries=backend_retries,
            )
        stress_report = json.loads(stress_json.read_text(encoding="utf-8"))
        losses = _parse_losses(repo_root / region.audit_path)
        baseline = _read(repo_root / region.baseline_path)
        map_payload = _read_map_payload(repo_root, region)
        map_text = json.dumps(map_payload, indent=2)
        requirements = _compile_rewrite_requirements(losses, map_payload, stress_report)

        write_json(artifacts / "rewrite_requirements.json", {"requirements": [_requirement_dict(req) for req in requirements]})
        write_markdown(artifacts / "REWRITE_REQUIREMENTS.md", _requirements_markdown(requirements))

        prompt = _synthesis_prompt(region, baseline, map_text, losses, requirements=requirements, stress_report=stress_report)
        write_markdown(artifacts / "decision_packet_prompt.txt", prompt)
        packet = _run_synthesis_backend(
            prompt,
            selected_backend,
            backend_timeout,
            backend_retries,
            map_payload,
            requirements,
        )
        initial_coverage = _deterministic_requirement_coverage(packet, requirements)
        repair_ran = False
        deterministic_patch_ran = False
        if _needs_repair(initial_coverage):
            repair_ran = True
            write_markdown(artifacts / "decision_packet_initial.md", packet)
            repair_prompt = _repair_synthesis_prompt(region, packet, initial_coverage, requirements)
            write_markdown(artifacts / "decision_packet_repair_prompt.txt", repair_prompt)
            packet = _run_synthesis_backend(
                repair_prompt,
                selected_backend,
                backend_timeout,
                backend_retries,
                map_payload,
                requirements,
            )
            repaired_coverage = _deterministic_requirement_coverage(packet, requirements)
            if _needs_repair(repaired_coverage):
                deterministic_patch_ran = True
                write_markdown(artifacts / "decision_packet_repaired_before_patch.md", packet)
                packet = _deterministic_patch_synthesis(packet, repaired_coverage, requirements)
        packet = _clean_reader_packet_metadata(packet)
        coverage = _deterministic_requirement_coverage(packet, requirements)
    except (RuntimeError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"decision_packet_failed region={region_id} error={exc}", file=sys.stderr)
        return 1

    packet_path = artifacts / "DECISION_PACKET.md"
    coverage_path = artifacts / "deterministic_requirement_coverage.json"
    summary_path = artifacts / "decision_packet.json"
    write_markdown(packet_path, packet)
    write_json(coverage_path, coverage)
    write_json(
        summary_path,
        {
            "schema_id": "decision_packet_v1",
            "region_id": region_id,
            "backend": selected_backend,
            "paths": {
                "decision_packet": _display_path(repo_root, packet_path),
                "deterministic_requirement_coverage": _display_path(repo_root, coverage_path),
                "rewrite_requirements": _display_path(repo_root, artifacts / "rewrite_requirements.json"),
                "stress_report": _display_path(repo_root, stress_json),
            },
            "requirement_count": len(requirements),
            "deterministic_coverage": {
                "clear": coverage["clear_count"],
                "partial": coverage["partial_count"],
                "missing": coverage["missing_count"],
            },
            "repair_ran": repair_ran,
            "deterministic_patch_ran": deterministic_patch_ran,
        },
    )
    print(
        "Decision packet wrote "
        f"{_display_path(repo_root, packet_path)} "
        f"backend={selected_backend} "
        f"coverage={coverage['clear_count']}/{len(requirements)} clear "
        f"repair_ran={str(repair_ran).lower()} patch_ran={str(deterministic_patch_ran).lower()}"
    )
    print(f"Coverage: {_display_path(repo_root, coverage_path)}")
    print(f"Summary: {_display_path(repo_root, summary_path)}")
    return 0


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
    output_text = result.text if result.prompt_only else canonical_json_output(result.text)
    output_path.write_text(output_text, encoding="utf-8")
    print(f"Wrote {_display_path(repo_root, output_path)} backend={result.backend}")
    if result.prompt_only:
        print("Prompt backend selected; no JSON validation run.")
        return 0
    if no_validate:
        print("Semantic validation skipped.")
        return 0
    return validate(output_path)


def _source_titles_for_region(repo_root: Path, manifest: SubmissionManifest, region_id: str) -> dict[str, str]:
    region = manifest.region_for_id(region_id)
    case_manifest = _case_manifest_for_region(repo_root, manifest, region)
    return {source.source_id: source.title for source in case_manifest.sources}


def _case_question_for_region(repo_root: Path, manifest: SubmissionManifest, region) -> str:
    return _case_manifest_for_region(repo_root, manifest, region).question


def _case_manifest_for_region(repo_root: Path, manifest: SubmissionManifest, region) -> CaseManifest:
    case = manifest.case_for_key(region.case_key)
    return CaseManifest.model_validate(read_yaml(repo_root / case.case_path))


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
