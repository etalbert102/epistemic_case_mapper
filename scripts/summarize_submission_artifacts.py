from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from artifact_utils import REGION_FILES, parse_erosion_audit, parse_worked_map


OUTPUT_PATH = "docs/SUBMISSION_ARTIFACT_SUMMARY.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize judge-facing FLF artifacts.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true", help="Check that the checked-in summary is current.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    rendered = render_summary(repo_root)
    output_path = repo_root / OUTPUT_PATH
    if args.check:
        if not output_path.exists():
            print(f"FAIL: missing_summary path={OUTPUT_PATH}")
            return 1
        if output_path.read_text(encoding="utf-8") != rendered:
            print(f"FAIL: stale_summary path={OUTPUT_PATH}")
            return 1
        print("Submission artifact summary is current")
        return 0
    output_path.write_text(rendered, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    return 0


def render_summary(repo_root: Path) -> str:
    lines = [
        "# Submission Artifact Summary",
        "",
        "Status: `generated`",
        "",
        "Purpose: provide quick counts for the FLF submission package. Regenerate with `PYTHONPATH=src python3 scripts/summarize_submission_artifacts.py`.",
        "",
        "| Case | Sources | Claims | Relations | Relation types | Cruxes | Erosion losses | Blinded baselines |",
        "| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |",
    ]
    totals = Counter()
    for region in REGION_FILES:
        worked_map = parse_worked_map(repo_root / region.map_path)
        audit = parse_erosion_audit(repo_root / region.audit_path)
        relation_types = Counter(str(relation.get("relation_type", "")) for relation in worked_map["relations"])
        baseline_count = len(list((repo_root / Path(region.baseline_path).parent).glob("blinded_flat_synthesis_baseline_*.md")))
        totals.update(
            {
                "sources": len(worked_map["sources"]),
                "claims": len(worked_map["claims"]),
                "relations": len(worked_map["relations"]),
                "cruxes": len(worked_map["crux_candidates"]),
                "losses": len(audit["losses"]),
                "baselines": baseline_count,
            }
        )
        relation_summary = ", ".join(f"{key}={value}" for key, value in sorted(relation_types.items()) if key)
        lines.append(
            f"| {region.case_label} | {len(worked_map['sources'])} | {len(worked_map['claims'])} | "
            f"{len(worked_map['relations'])} | {relation_summary} | {len(worked_map['crux_candidates'])} | "
            f"{len(audit['losses'])} | {baseline_count} |"
        )
    lines.extend(
        [
            "",
            "## Totals",
            "",
            f"- Sources represented in worked regions: `{totals['sources']}`",
            f"- Curated claims: `{totals['claims']}`",
            f"- Relations: `{totals['relations']}`",
            f"- Crux candidates: `{totals['cruxes']}`",
            f"- Erosion findings: `{totals['losses']}`",
            f"- Blinded local-model baselines: `{totals['baselines']}`",
            "",
            "## Interpretation",
            "",
            "These counts are not quality scores. They help judges verify that the submission includes source grounding, structured relations, cruxes, erosion findings, and multi-model comparators for both worked regions.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
