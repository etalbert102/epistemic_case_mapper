from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

from artifact_utils import REGION_FILES, parse_erosion_audit, parse_worked_map
from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest


OUTPUT_PATH = "docs/SUBMISSION_ARTIFACT_SUMMARY.md"
FULL_CASES = (
    {
        "label": "LHC black holes",
        "case_path": "data/cases/lhc_black_holes/case.yaml",
        "map_path": "examples/lhc_black_holes/full_case_map.md",
        "index_path": "examples/lhc_black_holes/full_case_index.md",
    },
    {
        "label": "Eggs and health",
        "case_path": "data/cases/eggs/case.yaml",
        "map_path": "examples/eggs/full_case_map.md",
        "index_path": "examples/eggs/full_case_index.md",
    },
)
EXTENSION_ARTIFACTS = (
    {
        "artifact": "Full-case flat baseline",
        "case": "LHC black holes",
        "path": "examples/lhc_black_holes/full_case_flat_synthesis_baseline.md",
        "status": "illustrative, non-blinded",
    },
    {
        "artifact": "Full-case flat baseline",
        "case": "Eggs and health",
        "path": "examples/eggs/full_case_flat_synthesis_baseline.md",
        "status": "illustrative, non-blinded",
    },
    {
        "artifact": "Draft public-risk worked region",
        "case": "LHC black holes",
        "path": "examples/lhc_black_holes/worked_region_public_risk_framing_map.md",
        "status": "draft extension, not canonical counts",
    },
    {
        "artifact": "New-to-map source update demo",
        "case": "LHC black holes",
        "path": "docs/NEW_SOURCE_UPDATE_DEMO.md",
        "status": "demo from already acquired source",
    },
    {
        "artifact": "Self-assessment and limitations",
        "case": "Submission",
        "path": "docs/FLF_SELF_ASSESSMENT_AND_LIMITATIONS.md",
        "status": "human-review-needed",
    },
    {
        "artifact": "Human audit guide",
        "case": "Submission",
        "path": "docs/HUMAN_AUDIT_GUIDE.md",
        "status": "human-review-needed",
    },
    {
        "artifact": "Operational workflow and realism",
        "case": "Submission",
        "path": "docs/OPERATIONAL_WORKFLOW_AND_REALISM.md",
        "status": "human-review-needed",
    },
)


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
            "## Full-Case Coverage",
            "",
            "| Case | Manifest sources | Full-case clusters | Full-case relations | Full-case files |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for full_case in FULL_CASES:
        manifest = CaseManifest.model_validate(read_yaml(repo_root / str(full_case["case_path"])))
        map_text = (repo_root / str(full_case["map_path"])).read_text(encoding="utf-8")
        cluster_count = len(re.findall(r"^cluster_id:\s*", map_text, flags=re.MULTILINE))
        relation_count = len(re.findall(r"^relation_id:\s*", map_text, flags=re.MULTILINE))
        lines.append(
            f"| {full_case['label']} | {len(manifest.sources)} | {cluster_count} | {relation_count} | "
            f"`{full_case['index_path']}`, `{full_case['map_path']}` |"
        )
    lines.extend(
        [
            "",
            "## Extension Artifacts",
            "",
            "| Artifact | Case | File | Status |",
            "| --- | --- | --- | --- |",
        ]
    )
    for artifact in EXTENSION_ARTIFACTS:
        lines.append(
            f"| {artifact['artifact']} | {artifact['case']} | `{artifact['path']}` | {artifact['status']} |"
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
            f"- Investigator task queue items: `{_task_count(repo_root)}`",
            "",
            "## Interpretation",
            "",
            "These counts are not quality scores. They help judges verify that the submission includes source grounding, structured relations, cruxes, erosion findings, and multi-model comparators for the worked regions. Full-case coverage remains limited to LHC and eggs; the COVID artifact is a narrow worked region.",
            "",
        ]
    )
    return "\n".join(lines)


def _task_count(repo_root: Path) -> int:
    count = 0
    for relative_path in (
        "examples/lhc_black_holes/investigator_task_queue.md",
        "examples/eggs/investigator_task_queue.md",
    ):
        path = repo_root / relative_path
        if path.exists():
            count += len(re.findall(r"^task_id:\s*", path.read_text(encoding="utf-8"), flags=re.MULTILINE))
    return count


if __name__ == "__main__":
    raise SystemExit(main())
