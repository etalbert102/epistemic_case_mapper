from __future__ import annotations

import argparse
import json
from pathlib import Path

from epistemic_case_mapper.pipeline.briefing.map_briefing_editorial_brief_experiment import (
    run_editorial_brief_memo_generation,
    run_editorial_brief_instruction_experiment,
    run_source_weighted_pipeline_fit_experiment,
    run_source_weighted_narrative_outline_experiment,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare instruction variants for projecting section packets into concise editorial briefs."
    )
    parser.add_argument(
        "--memo-ready-packet",
        default="artifacts/tmp_resume_test/briefing/memo_ready_packet.json",
        help="Path to memo_ready_packet.json.",
    )
    parser.add_argument("--backend", default="prompt", help="Backend for live editorial-brief generation. Use prompt for no model calls.")
    parser.add_argument("--backend-timeout", type=int, default=120)
    parser.add_argument("--backend-retries", type=int, default=0)
    parser.add_argument("--generate-memos", action="store_true", help="Also generate full memos from selected editorial-brief variants.")
    parser.add_argument("--memo-backend", help="Backend for memo generation. Defaults to --backend.")
    parser.add_argument(
        "--memo-variant",
        action="append",
        default=[],
        help="Editorial-brief variant to use for memo generation. May be passed multiple times.",
    )
    parser.add_argument("--memo-timeout", type=int, default=240)
    parser.add_argument(
        "--generate-outline-memo",
        action="store_true",
        help="Also generate a memo through the source-weighted narrative outline experiment.",
    )
    parser.add_argument(
        "--outline-variant",
        default="source_weighted",
        help="Editorial-brief variant used as the outline input.",
    )
    parser.add_argument("--outline-backend", help="Backend for outline and outline-guided memo generation. Defaults to --memo-backend or --backend.")
    parser.add_argument("--outline-timeout", type=int, default=240)
    parser.add_argument(
        "--pipeline-fit",
        action="store_true",
        help="Run the source-weighted outline through the actual production parallel section synthesis path.",
    )
    parser.add_argument(
        "--pipeline-fit-baseline",
        action="store_true",
        help="Also run the current production synthesis path for comparison.",
    )
    parser.add_argument(
        "--pipeline-fit-outline-owned-contracts",
        action="store_true",
        help="In pipeline-fit mode, demote non-outline evidence in an experimental packet copy so prompts and validation use the same contract set.",
    )
    parser.add_argument(
        "--pipeline-fit-no-protect-critical",
        action="store_true",
        help="In outline-owned pipeline-fit mode, test pure outline ownership without preserving analyst-critical crux/counterweight evidence.",
    )
    parser.add_argument(
        "--pipeline-fit-opinionated-sections",
        action="store_true",
        help="In pipeline-fit mode, add an experimental opinionated prose plan to each section before synthesis.",
    )
    parser.add_argument(
        "--out",
        default="artifacts/editorial_brief_instruction_experiment",
        help="Output directory for prompts, generated briefs, and score matrix.",
    )
    args = parser.parse_args()

    packet_path = Path(args.memo_ready_packet)
    memo_ready_packet = json.loads(packet_path.read_text(encoding="utf-8"))
    summary = run_editorial_brief_instruction_experiment(
        memo_ready_packet,
        output_dir=args.out,
        backend=args.backend,
        backend_timeout=args.backend_timeout,
        backend_retries=args.backend_retries,
    )
    memo_summary = None
    outline_summary = None
    pipeline_fit_summary = None
    if args.generate_memos:
        variants = args.memo_variant or [summary.get("recommended_variant"), "source_weighted"]
        variants = [variant for variant in dict.fromkeys(variants) if variant]
        memo_summary = run_editorial_brief_memo_generation(
            memo_ready_packet,
            output_dir=Path(args.out) / "memo_generation",
            variant_ids=variants,
            backend=args.memo_backend or args.backend,
            backend_timeout=args.memo_timeout,
            backend_retries=args.backend_retries,
        )
    if args.generate_outline_memo:
        outline_summary = run_source_weighted_narrative_outline_experiment(
            memo_ready_packet,
            output_dir=Path(args.out) / "source_weighted_outline",
            variant_id=args.outline_variant,
            backend=args.outline_backend or args.memo_backend or args.backend,
            backend_timeout=args.outline_timeout,
            backend_retries=args.backend_retries,
        )
    if args.pipeline_fit:
        pipeline_fit_summary = run_source_weighted_pipeline_fit_experiment(
            memo_ready_packet,
            output_dir=Path(args.out) / "source_weighted_pipeline_fit",
            variant_id=args.outline_variant,
            backend=args.outline_backend or args.memo_backend or args.backend,
            backend_timeout=args.outline_timeout,
            backend_retries=args.backend_retries,
            compare_baseline=args.pipeline_fit_baseline,
            outline_owned_contracts=args.pipeline_fit_outline_owned_contracts,
            protect_critical_evidence=not args.pipeline_fit_no_protect_critical,
            opinionated_section_plan=args.pipeline_fit_opinionated_sections,
        )
    print(
        json.dumps(
            {
                "status": "ok",
                "out": args.out,
                "recommended_variant": summary.get("recommended_variant"),
                "section_count": summary.get("section_count"),
                "variant_count": summary.get("variant_count"),
                "memo_generation": {
                    "best_by_proxy": memo_summary.get("best_by_proxy"),
                    "variant_count": memo_summary.get("variant_count"),
                }
                if memo_summary
                else None,
                "outline_memo": {
                    "score": outline_summary.get("score", {}).get("score"),
                    "outline_status": outline_summary.get("outline_status"),
                    "memo_status": outline_summary.get("memo_status"),
                    "memo_path": str(Path(args.out) / "source_weighted_outline" / outline_summary.get("memo_path", "")),
                }
                if outline_summary
                else None,
                "pipeline_fit": {
                    "score": pipeline_fit_summary.get("score", {}).get("score"),
                    "outline_status": pipeline_fit_summary.get("outline_status"),
                    "outline_owned_contracts": pipeline_fit_summary.get("outline_owned_contracts"),
                    "protect_critical_evidence": pipeline_fit_summary.get("protect_critical_evidence"),
                    "opinionated_section_plan": pipeline_fit_summary.get("opinionated_section_plan"),
                    "section_generation_status": pipeline_fit_summary.get("section_generation_report", {}).get("status"),
                    "memo_path": str(Path(args.out) / "source_weighted_pipeline_fit" / pipeline_fit_summary.get("memo_path", "")),
                }
                if pipeline_fit_summary
                else None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
