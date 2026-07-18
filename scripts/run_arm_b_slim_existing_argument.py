#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from epistemic_case_mapper.map_briefing_prioritized_argument_arm_b import run_arm_b_b0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Arm B slim existing-argument experiment.")
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
        help="Directory where Arm B B0 artifacts should be written.",
    )
    parser.add_argument(
        "--no-force-retry",
        action="store_true",
        help="Do not force a fake retry during deterministic prompt-submission audit.",
    )
    args = parser.parse_args()

    result = run_arm_b_b0(
        briefing_dir=args.briefing_dir,
        output_dir=args.output_dir,
        force_retry=not args.no_force_retry,
    )
    print(json.dumps(result["report"], indent=2, ensure_ascii=False))
    return 0 if result["report"].get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
