from __future__ import annotations

import argparse
import json
from pathlib import Path

from epistemic_case_mapper.map_briefing_gap_closer_experiment import (
    VARIANT_IDS,
    run_gap_closer_live_experiment,
    write_gap_closer_experiment_inputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Experiment with BLUF and source-weighted thesis variants for memo synthesis before production promotion."
    )
    parser.add_argument("--packet", required=True, help="Path to memo_ready_packet.json.")
    parser.add_argument("--out", required=True, help="Output directory for experiment artifacts.")
    parser.add_argument("--backend", default="prompt", help="Model backend, for example prompt or ollama:gemma4:12b-mlx.")
    parser.add_argument("--backend-timeout", type=int, default=420)
    parser.add_argument("--backend-retries", type=int, default=1)
    parser.add_argument("--variant", action="append", choices=VARIANT_IDS, help="Variant to run. Repeatable. Defaults to all variants.")
    parser.add_argument("--live", action="store_true", help="Run live synthesis. Without this, only writes packet and prompt inputs.")
    parser.add_argument("--no-polish", action="store_true", help="Skip final polish during live runs.")
    args = parser.parse_args()

    packet_path = Path(args.packet)
    out = Path(args.out)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    inputs = write_gap_closer_experiment_inputs(packet, out)
    if not args.live:
        print(json.dumps({"status": "inputs_written", "out": str(out), "variants": list(inputs["variants"])}, indent=2))
        return 0
    report = run_gap_closer_live_experiment(
        packet,
        backend=args.backend,
        backend_timeout=args.backend_timeout,
        backend_retries=args.backend_retries,
        out_dir=out,
        variants=args.variant,
        run_polish=not args.no_polish,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
