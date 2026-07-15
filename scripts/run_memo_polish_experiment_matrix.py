from __future__ import annotations

import argparse
import json
from pathlib import Path

from epistemic_case_mapper.map_briefing_memo_polish_experiments import (
    DEFAULT_POLISH_EXPERIMENT_VARIANTS,
    run_memo_polish_experiment_matrix,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run memo polish variants against the same memo-ready packet.")
    parser.add_argument("--memo", required=True, help="Input memo markdown path.")
    parser.add_argument("--packet", required=True, help="Memo-ready packet JSON path.")
    parser.add_argument("--out", required=True, help="Output directory for experiment artifacts.")
    parser.add_argument("--backend", default="prompt", help="Model backend, e.g. prompt or ollama:gemma4:12b-mlx.")
    parser.add_argument("--backend-timeout", type=int, default=180)
    parser.add_argument("--backend-retries", type=int, default=0)
    parser.add_argument(
        "--variant",
        action="append",
        choices=DEFAULT_POLISH_EXPERIMENT_VARIANTS,
        help="Variant to run. May be repeated. Defaults to all variants.",
    )
    parser.add_argument("--reader-judge", action="store_true", help="Also run the model reader-judge evaluation.")
    args = parser.parse_args()

    memo_path = Path(args.memo)
    packet_path = Path(args.packet)
    out = Path(args.out)
    memo = memo_path.read_text()
    packet = json.loads(packet_path.read_text())
    result = run_memo_polish_experiment_matrix(
        memo,
        packet,
        backend=args.backend,
        backend_timeout=args.backend_timeout,
        backend_retries=args.backend_retries,
        variants=args.variant,
        output_dir=out,
        run_reader_judge=args.reader_judge,
    )
    summary = result["summary"]
    print(json.dumps({"out": str(out), "variant_count": summary.get("variant_count"), "promotion_candidates": summary.get("promotion_candidates", [])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
