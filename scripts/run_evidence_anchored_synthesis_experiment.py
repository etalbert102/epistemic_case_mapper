from __future__ import annotations

import argparse
import json
from pathlib import Path

from epistemic_case_mapper.evidence_anchored_synthesis_experiment import run_evidence_anchored_synthesis_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the evidence-anchored memo synthesis experiment on a saved memo-ready packet.")
    parser.add_argument("--packet", required=True, help="Path to memo_ready_packet.json")
    parser.add_argument("--baseline-memo", default="", help="Optional path to the current production memo for comparison")
    parser.add_argument("--output-dir", required=True, help="Directory for experiment artifacts")
    parser.add_argument("--backend", default="prompt", help="Model backend, e.g. prompt or ollama:gemma4:12b-mlx")
    parser.add_argument("--backend-timeout", type=int, default=240)
    parser.add_argument("--backend-retries", type=int, default=1)
    args = parser.parse_args()

    packet_path = Path(args.packet)
    output_dir = Path(args.output_dir)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    baseline = Path(args.baseline_memo).read_text(encoding="utf-8") if args.baseline_memo else ""
    result = run_evidence_anchored_synthesis_experiment(
        packet,
        backend=args.backend,
        backend_timeout=args.backend_timeout,
        backend_retries=args.backend_retries,
        baseline_memo=baseline,
        output_dir=output_dir,
    )
    report = result["report"]
    print(f"output_dir={output_dir}")
    print(f"status={report.get('status')}")
    print(f"section_count={report.get('section_count')}")
    print(f"accepted_section_count={report.get('accepted_section_count')}")
    print(f"contract_count={report.get('contract_count')}")
    print(f"required_contract_count={report.get('required_contract_count')}")
    print(f"reconciliation_status={report.get('reconciliation_status')}")
    print(f"missing_mandatory_count={report.get('missing_mandatory_count')}")
    print(f"missing_quantity_count={report.get('missing_quantity_count')}")
    print(f"source_binding_warning_count={report.get('source_binding_warning_count')}")


if __name__ == "__main__":
    main()
