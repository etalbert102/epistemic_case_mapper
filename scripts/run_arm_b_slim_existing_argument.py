#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from epistemic_case_mapper.pipeline.briefing.map_briefing_prioritized_argument_arm_b import run_arm_b_b0, run_arm_b_b1
from epistemic_case_mapper.pipeline.briefing.map_briefing_prioritized_argument_arm_c import run_arm_c


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Arm B slim existing-argument experiment.")
    parser.add_argument(
        "--mode",
        choices=("b0", "b1", "arm-c"),
        default="b0",
        help="B0 runs deterministic prompt capture; B1 runs live Arm B; arm-c runs focused prioritization.",
    )
    parser.add_argument(
        "--briefing-dir",
        type=Path,
        default=Path("artifacts/truth_boundary_verification_eggs_live/briefing"),
        help="Directory containing frozen synthesis-stage briefing artifacts.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/arm_b_slim_existing_argument/b0_eggs"),
        help="Directory where Arm B artifacts should be written.",
    )
    parser.add_argument("--backend", default="prompt", help="Model backend for B1.")
    parser.add_argument("--backend-timeout", type=int, default=120)
    parser.add_argument("--backend-retries", type=int, default=0)
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument(
        "--no-force-retry",
        action="store_true",
        help="Do not force a fake retry during deterministic prompt-submission audit.",
    )
    args = parser.parse_args()

    if args.mode == "arm-c":
        result = run_arm_c(
            briefing_dir=args.briefing_dir,
            output_dir=args.output_dir,
            backend=args.backend,
            backend_timeout=args.backend_timeout,
            backend_retries=args.backend_retries,
            samples=args.samples,
        )
    elif args.mode == "b1":
        result = run_arm_b_b1(
            briefing_dir=args.briefing_dir,
            output_dir=args.output_dir,
            backend=args.backend,
            backend_timeout=args.backend_timeout,
            backend_retries=args.backend_retries,
            samples=args.samples,
        )
    else:
        result = run_arm_b_b0(
            briefing_dir=args.briefing_dir,
            output_dir=args.output_dir,
            force_retry=not args.no_force_retry,
        )
    print(json.dumps(result["report"], indent=2, ensure_ascii=False))
    return 0 if result["report"].get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
