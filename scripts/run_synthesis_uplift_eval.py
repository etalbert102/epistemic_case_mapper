from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.llm_stress_eval import run_llm_stress_eval
from epistemic_case_mapper.submission_manifest import WorkedRegion, load_submission_manifest
from epistemic_case_mapper.synthesis_uplift_judgment import (
    _aggregate_summary,
    _markdown_report,
    _normalize_loss_judgment,
    _overall_from_loss_judgments,
    _region_summary,
)
from epistemic_case_mapper.synthesis_uplift_packet import (
    _accepted_synthesis,
    _as_text,
    _clean_reader_packet_metadata,
    _claim_lookup,
    _clean_required_phrase,
    _dedupe_text_items,
    _deterministic_requirement_coverage,
    _is_meta_loss_text,
    _needs_repair,
    _normalize_for_coverage,
    _packet_scaffold,
    _packet_scaffold_prompt_block,
    _parse_json,
    _phrase_present_in_synthesis,
    _read,
    _read_map_payload,
    _reader_claim_statement,
    _rel,
    _relation_lookup,
    _render_synthesis_packet,
    _render_unparsed_structured_packet,
    _requirement_dict,
    _requirements_prompt_block,
    _run_synthesis_backend,
    _run_text_backend,
    _short_text,
    _truncate,
    _worked_map_payload,
)
from epistemic_case_mapper.synthesis_uplift_repair import (
    _deterministic_patch_synthesis,
    _repair_synthesis_prompt,
    _requirements_markdown,
)
from epistemic_case_mapper.synthesis_uplift_requirements import (
    _compile_rewrite_requirements,
    _parse_losses,
    _synthesis_prompt,
)
from epistemic_case_mapper.synthesis_uplift_types import Loss, PacketSlot, RewriteRequirement








def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test whether LLM stress findings help produce better syntheses against erosion-audit losses."
    )
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    parser.add_argument("--region", action="append", required=True, help="Region ID. May be passed multiple times.")
    parser.add_argument("--backend", default="ollama:llama3.2:3b", help="Synthesis and stress backend.")
    parser.add_argument("--judge-backend", help="Judge backend. Defaults to --backend.")
    parser.add_argument("--output-dir", default="artifacts/synthesis_uplift_eval/latest")
    parser.add_argument("--backend-timeout", type=int, default=120)
    parser.add_argument("--backend-retries", type=int, default=0)
    parser.add_argument("--skip-stress-run", action="store_true", help="Reuse an existing stress report when present.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_submission_manifest(repo_root, args.manifest)

    rows = []
    for region_id in args.region:
        try:
            region = manifest.region_for_id(region_id)
        except KeyError:
            print(f"unknown_region {region_id}", file=sys.stderr)
            return 1
        row = _run_region(
            repo_root=repo_root,
            manifest_path=args.manifest,
            region=region,
            backend=args.backend,
            judge_backend=args.judge_backend or args.backend,
            output_dir=output_dir / region_id,
            timeout_seconds=args.backend_timeout,
            max_retries=args.backend_retries,
            skip_stress_run=args.skip_stress_run,
        )
        rows.append(row)
        print(
            f"{region_id}: stress_wins={row['summary']['stress_wins']} "
            f"map_only_wins={row['summary']['map_only_wins']} ties={row['summary']['ties']} "
            f"invalid_judgments={row['summary']['invalid_judgments']}"
        )

    report = {
        "schema_id": "synthesis_uplift_eval_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "backend": args.backend,
        "judge_backend": args.judge_backend or args.backend,
        "regions": rows,
        "summary": _aggregate_summary(rows),
    }
    write_json(output_dir / "synthesis_uplift_eval.json", report)
    write_markdown(output_dir / "SYNTHESIS_UPLIFT_EVAL.md", _markdown_report(report))
    print(f"Wrote {(output_dir / 'synthesis_uplift_eval.json').relative_to(repo_root).as_posix()}")
    print(f"Wrote {(output_dir / 'SYNTHESIS_UPLIFT_EVAL.md').relative_to(repo_root).as_posix()}")
    return 0


def _run_region(
    *,
    repo_root: Path,
    manifest_path: str,
    region: WorkedRegion,
    backend: str,
    judge_backend: str,
    output_dir: Path,
    timeout_seconds: int,
    max_retries: int,
    skip_stress_run: bool,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stress_dir = output_dir / "stress"
    stress_json = stress_dir / "llm_stress_eval.json"
    if not skip_stress_run or not stress_json.exists():
        run_llm_stress_eval(
            repo_root=repo_root,
            manifest_path=manifest_path,
            region_id=region.region_id,
            backend=backend,
            output_dir=stress_dir,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
    stress_report = json.loads(stress_json.read_text(encoding="utf-8"))
    losses = _parse_losses(repo_root / region.audit_path)
    baseline = _read(repo_root / region.baseline_path)
    map_payload = _read_map_payload(repo_root, region)
    map_text = json.dumps(map_payload, indent=2)
    requirements = _compile_rewrite_requirements(losses, map_payload, stress_report)
    write_json(output_dir / "rewrite_requirements.json", {"requirements": [_requirement_dict(req) for req in requirements]})
    write_markdown(output_dir / "REWRITE_REQUIREMENTS.md", _requirements_markdown(requirements))

    map_only_prompt = _synthesis_prompt(region, baseline, map_text, losses, requirements=(), stress_report=None)
    stress_prompt = _synthesis_prompt(region, baseline, map_text, losses, requirements=requirements, stress_report=stress_report)
    write_markdown(output_dir / "map_only_prompt.txt", map_only_prompt)
    write_markdown(output_dir / "stress_assisted_prompt.txt", stress_prompt)

    map_only = _run_synthesis_backend(map_only_prompt, backend, timeout_seconds, max_retries, map_payload, ())
    stress_assisted = _run_synthesis_backend(
        stress_prompt, backend, timeout_seconds, max_retries, map_payload, requirements
    )
    initial_stress_coverage = _deterministic_requirement_coverage(stress_assisted, requirements)
    if _needs_repair(initial_stress_coverage):
        write_markdown(output_dir / "stress_assisted_initial_synthesis.md", stress_assisted)
        repair_prompt = _repair_synthesis_prompt(region, stress_assisted, initial_stress_coverage, requirements)
        write_markdown(output_dir / "stress_assisted_repair_prompt.txt", repair_prompt)
        stress_assisted = _run_synthesis_backend(
            repair_prompt, backend, timeout_seconds, max_retries, map_payload, requirements
        )
        repaired_coverage = _deterministic_requirement_coverage(stress_assisted, requirements)
        if _needs_repair(repaired_coverage):
            write_markdown(output_dir / "stress_assisted_repaired_before_patch.md", stress_assisted)
            stress_assisted = _deterministic_patch_synthesis(stress_assisted, repaired_coverage, requirements)
    map_only = _clean_reader_packet_metadata(map_only)
    stress_assisted = _clean_reader_packet_metadata(stress_assisted)
    write_markdown(output_dir / "map_only_synthesis.md", map_only)
    write_markdown(output_dir / "stress_assisted_synthesis.md", stress_assisted)
    deterministic_coverage = {
        "map_only": _deterministic_requirement_coverage(map_only, requirements),
        "stress_assisted": _deterministic_requirement_coverage(stress_assisted, requirements),
    }
    write_json(output_dir / "deterministic_requirement_coverage.json", deterministic_coverage)

    judgments = []
    for loss in losses:
        judgment_prompt = _single_loss_judgment_prompt(region, loss, map_only, stress_assisted)
        write_markdown(output_dir / "judgment_prompts" / f"{loss.loss_id}.txt", judgment_prompt)
        judgment_raw = _run_text_backend(judgment_prompt, judge_backend, timeout_seconds, max_retries)
        write_markdown(output_dir / "judgment_raw" / f"{loss.loss_id}.txt", judgment_raw)
        parsed = _parse_json(judgment_raw)
        if parsed is None:
            judgments.append({"loss_id": loss.loss_id, "parse_error": "judge_returned_invalid_json"})
            continue
        judgments.append(_normalize_loss_judgment(loss.loss_id, parsed))
    judgment = {"loss_judgments": judgments, "overall": _overall_from_loss_judgments(judgments)}
    write_json(output_dir / "judgment.json", judgment)

    summary = _region_summary(losses, judgment)
    summary["deterministic_coverage"] = {
        "map_only_clear": deterministic_coverage["map_only"]["clear_count"],
        "stress_assisted_clear": deterministic_coverage["stress_assisted"]["clear_count"],
        "map_only_partial": deterministic_coverage["map_only"]["partial_count"],
        "stress_assisted_partial": deterministic_coverage["stress_assisted"]["partial_count"],
        "requirement_count": len(requirements),
        "accepted_synthesis": _accepted_synthesis(deterministic_coverage),
    }
    return {
        "region_id": region.region_id,
        "loss_count": len(losses),
        "requirement_count": len(requirements),
        "paths": {
            "stress_report": _rel(repo_root, stress_json),
            "rewrite_requirements": _rel(repo_root, output_dir / "rewrite_requirements.json"),
            "deterministic_requirement_coverage": _rel(repo_root, output_dir / "deterministic_requirement_coverage.json"),
            "map_only_synthesis": _rel(repo_root, output_dir / "map_only_synthesis.md"),
            "stress_assisted_synthesis": _rel(repo_root, output_dir / "stress_assisted_synthesis.md"),
            "judgment": _rel(repo_root, output_dir / "judgment.json"),
        },
        "stress_summary": stress_report.get("summary", {}),
        "summary": summary,
    }


def _single_loss_judgment_prompt(region: WorkedRegion, loss: Loss, map_only: str, stress_assisted: str) -> str:
    loss_payload = {
        "loss_id": loss.loss_id,
        "loss_type": loss.loss_type,
        "lost_item": loss.lost_item,
        "flat_baseline_omission": loss.flat_baseline_omission,
        "case_map_preserves": loss.case_map_preserves,
    }
    return "\n\n".join(
        (
            "You are evaluating whether a synthesis preserves known decision-space losses.",
            f"Region: {region.region_id}",
            "Compare Synthesis A and Synthesis B against exactly one loss. Return valid JSON only.",
            "Do not reward length. Reward the synthesis that makes the loss more inspectable for a thoughtful reader.",
            "Allowed winner values: A, B, tie, neither.",
            "Required JSON shape: {\"loss_id\": \"...\", \"winner\": \"A|B|tie|neither\", \"a_coverage\": \"none|partial|clear\", \"b_coverage\": \"none|partial|clear\", \"reason\": \"...\"}",
            "Loss:\n" + json.dumps(loss_payload, indent=2),
            "Synthesis A (map-only rewrite):\n" + map_only,
            "Synthesis B (stress-assisted rewrite):\n" + stress_assisted,
        )
    )




































































































































if __name__ == "__main__":
    raise SystemExit(main())
