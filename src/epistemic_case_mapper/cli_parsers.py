from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def build_parser(engine_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Epistemic Case Mapper engine CLI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Common paths:\n"
            "  ecm validate package\n"
            "  ecm semantic staged brief --region <region_id> --backend prompt\n"
            "  ecm case init --case-id my_case --title \"My Case\" --question \"What should we conclude?\" --docs doc_a.txt doc_b.md\n"
            "\n"
            "Backends: prompt, command:<cmd>, or ollama:<model>."
        ),
    )
    parser.add_argument("--repo-root", default=engine_root, help="Package root for relative paths.")
    parser.add_argument("--package", default="submission_manifest.yaml", help="Package manifest path.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_case_parsers(subparsers)
    _add_package_validate_export_ui_parsers(subparsers)
    _add_baseline_synthesize_review_parsers(subparsers)
    _add_quality_eval_parsers(subparsers)
    _add_semantic_parsers(subparsers)
    return parser
def _add_case_parsers(subparsers: Any) -> None:
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
def _add_package_validate_export_ui_parsers(subparsers: Any) -> None:
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
def _add_baseline_synthesize_review_parsers(subparsers: Any) -> None:
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
    map_briefing.add_argument("--question", help="Decision-relevant question to brief. Defaults to the case manifest question when --region is supplied.")
    map_briefing.add_argument("--backend", help="Backend for briefing generation. Defaults to manifest default_model_backend.")
    map_briefing.add_argument("--output-dir", help="Artifact directory. Defaults to artifacts/map_briefings/<map-stem>.")
    map_briefing.add_argument("--region", help="Optional region ID used only to load source display names.")
    map_briefing.add_argument("--baseline", help="Optional baseline memo path for deterministic gap telemetry.")
    map_briefing.add_argument("--max-claims", type=int, default=0, help="Briefing map claim budget after source-preserving prioritization. Use 0 for adaptive.")
    map_briefing.add_argument("--run-reader-memo-rewrite", action="store_true", help=argparse.SUPPRESS)
    map_briefing.add_argument("--backend-timeout", type=int, default=120)
    map_briefing.add_argument("--backend-retries", type=int, default=0)

    review_parser = subparsers.add_parser("review", help="Build review artifacts.")
    review_subparsers = review_parser.add_subparsers(dest="review_target", required=True)
    review_checklist = review_subparsers.add_parser("checklist", help="Build Tier 1 review checklist.")
    review_checklist.add_argument("--check", action="store_true")
def _add_quality_eval_parsers(subparsers: Any) -> None:
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
def _add_semantic_parsers(subparsers: Any) -> None:
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
    semantic_staged = semantic_subparsers.add_parser("staged", help="Run staged semantic mapping.")
    semantic_staged_subparsers = semantic_staged.add_subparsers(dest="semantic_staged_target", required=True)
    semantic_staged_map = semantic_staged_subparsers.add_parser("map", help="Extract claims, build relations, and assemble a map.")
    semantic_staged_map.add_argument("--region", required=True)
    semantic_staged_map.add_argument("--backend", help="Override manifest default backend.")
    semantic_staged_map.add_argument("--question", help="Decision question. Defaults to the region baseline question, then the case manifest question.")
    semantic_staged_map.add_argument("--output", help="Output path. Defaults to the region map path.")
    semantic_staged_map.add_argument("--artifact-dir", help="Directory for intermediate prompts and model outputs.")
    semantic_staged_map.add_argument("--chunk-lines", type=int, default=40)
    semantic_staged_map.add_argument("--chunk-overlap-lines", type=int, default=0)
    semantic_staged_map.add_argument("--max-chunks-per-source", type=int, default=0, help="0 means no per-source chunk cap.")
    semantic_staged_map.add_argument("--max-total-chunks", type=int, default=0, help="0 means no total chunk cap.")
    semantic_staged_map.add_argument("--max-claims-per-source", type=int, default=8, help="Max canonical claims extracted from each source document.")
    semantic_staged_map.add_argument("--claim-consolidation", choices=["deterministic", "vector-llm"], default="deterministic")
    semantic_staged_map.add_argument("--max-relation-pairs", type=int, default=12)
    semantic_staged_map.add_argument("--relation-batch-size", type=int, default=4)
    semantic_staged_map.add_argument("--backend-timeout", type=int, default=90, help="Seconds allowed for each backend call.")
    semantic_staged_map.add_argument("--backend-retries", type=int, default=1, help="Retries for transient backend failures.")
    semantic_staged_map.add_argument("--no-claim-cache", action="store_true", help="Ignore existing per-source canonical claim outputs and call the backend for every source.")
    semantic_staged_map.add_argument("--repair-quality", action="store_true", help="Run the map-quality repair prompt and accept it if it validates and preserves/improves quality.")
    semantic_staged_map.add_argument("--no-validate", action="store_true", help="Skip final semantic JSON validation.")
    semantic_staged_brief = semantic_staged_subparsers.add_parser(
        "brief",
        help="Run staged mapping and produce a readable map-anchored decision briefing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Dry run using prompt files and deterministic rendering:\n"
            "  ecm semantic staged brief --region my_case_initial_region --backend prompt\n"
            "\n"
            "  # Live local model run with reusable defaults:\n"
            "  ecm semantic staged brief --region my_case_initial_region --backend ollama:gemma4:26b --backend-timeout 120 --backend-retries 1\n"
            "\n"
            "  # Resume memo creation from an existing generated map and quality report:\n"
            "  ecm semantic staged resume --region my_case_initial_region --from-stage map --backend ollama:gemma4:26b\n"
            "\n"
            "Outputs include a generated map, briefing memo, summary JSON, progress logs, and FINAL_REVIEW_PACKET.md."
        ),
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
    semantic_staged_brief.add_argument("--max-claims-per-source", type=int, default=8, help="Max canonical claims extracted from each source document.")
    semantic_staged_brief.add_argument("--claim-consolidation", choices=["deterministic", "vector-llm"], default="deterministic")
    semantic_staged_brief.add_argument("--max-relation-pairs", type=int, default=12)
    semantic_staged_brief.add_argument("--relation-batch-size", type=int, default=4)
    semantic_staged_brief.add_argument("--briefing-max-claims", type=int, default=0, help="Briefing map claim budget. Use 0 for adaptive.")
    semantic_staged_brief.add_argument("--backend-timeout", type=int, default=90, help="Seconds allowed for each backend call.")
    semantic_staged_brief.add_argument("--backend-retries", type=int, default=1, help="Retries for transient backend failures.")
    semantic_staged_brief.add_argument("--no-claim-cache", action="store_true", help="Ignore existing per-source canonical claim outputs and call the backend for every source.")
    semantic_staged_brief.add_argument("--repair-quality", action="store_true", default=True, help="Run quality repair before briefing.")
    semantic_staged_brief.add_argument("--no-repair-quality", action="store_false", dest="repair_quality", help="Skip quality repair.")
    semantic_staged_brief.add_argument("--no-validate", action="store_true", help="Skip final semantic JSON validation.")
    semantic_staged_resume = semantic_staged_subparsers.add_parser(
        "resume",
        help="Resume the staged document-to-briefing pipeline from saved artifacts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Pipeline handoffs:\n"
            "  documents -> generated map + map quality report -> briefing memo + final review packet\n"
            "\n"
            "Examples:\n"
            "  # Show which default artifacts are present:\n"
            "  ecm semantic staged status --region my_case_initial_region\n"
            "\n"
            "  # Rebuild only the memo from an existing map artifact bundle:\n"
            "  ecm semantic staged resume --region my_case_initial_region --from-stage map --backend ollama:gemma4:26b\n"
            "\n"
            "  # Print the existing final memo/review paths without rerunning model calls:\n"
            "  ecm semantic staged resume --region my_case_initial_region --from-stage briefing\n"
        ),
    )
    semantic_staged_resume.add_argument("--region", required=True)
    semantic_staged_resume.add_argument("--from-stage", choices=["documents", "map", "briefing"], required=True)
    semantic_staged_resume.add_argument("--backend", help="Override manifest default backend.")
    semantic_staged_resume.add_argument("--question", help="Decision question. Defaults to the case manifest question.")
    semantic_staged_resume.add_argument("--run-dir", help="Root staged-brief artifact directory. Defaults to artifacts/semantic/<region>/staged_brief.")
    semantic_staged_resume.add_argument("--map", help="Existing generated map path. Defaults to <run-dir>/generated_map.json.")
    semantic_staged_resume.add_argument("--quality-report", help="Existing map quality report path. Defaults to <run-dir>/map/map_quality_report.json.")
    semantic_staged_resume.add_argument("--briefing-dir", help="Briefing artifact directory. Defaults to <run-dir>/briefing.")
    semantic_staged_resume.add_argument("--briefing-max-claims", type=int, default=0, help="Briefing map claim budget. Use 0 for adaptive.")
    semantic_staged_resume.add_argument("--backend-timeout", type=int, default=90)
    semantic_staged_resume.add_argument("--backend-retries", type=int, default=1)
    semantic_staged_status = semantic_staged_subparsers.add_parser(
        "status",
        help="Show the staged pipeline artifact handoffs for one region.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Stages:\n"
            "  documents: case manifest and required source files are available.\n"
            "  map: generated_map.json and map/map_quality_report.json are available.\n"
            "  briefing: briefing/BRIEFING.md, briefing_summary.json, and FINAL_REVIEW_PACKET.md are available."
        ),
    )
    semantic_staged_status.add_argument("--region", required=True)
    semantic_staged_status.add_argument("--run-dir", help="Root staged-brief artifact directory. Defaults to artifacts/semantic/<region>/staged_brief.")
    semantic_staged_status.add_argument("--map", help="Generated map path. Defaults to <run-dir>/generated_map.json.")
    semantic_staged_status.add_argument("--quality-report", help="Map quality report path. Defaults to <run-dir>/map/map_quality_report.json.")
    semantic_staged_status.add_argument("--briefing-dir", help="Briefing artifact directory. Defaults to <run-dir>/briefing.")
    semantic_validate = semantic_subparsers.add_parser("validate", help="Validate model-produced semantic JSON.")
    semantic_validate_subparsers = semantic_validate.add_subparsers(dest="semantic_validate_target", required=True)
    semantic_map_validate = semantic_validate_subparsers.add_parser("map", help="Validate a candidate JSON worked map.")
    semantic_map_validate.add_argument("--region", required=True)
    semantic_map_validate.add_argument("--path", required=True)
    semantic_critique_validate = semantic_validate_subparsers.add_parser("critique", help="Validate a candidate JSON critique.")
    semantic_critique_validate.add_argument("--path", required=True)
