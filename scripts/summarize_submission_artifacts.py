from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

from artifact_utils import load_region_files, parse_erosion_audit, parse_worked_map
from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.submission_manifest import SubmissionManifest, load_submission_manifest


OUTPUT_PATH = "docs/SUBMISSION_ARTIFACT_SUMMARY.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize judge-facing FLF artifacts.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    parser.add_argument("--check", action="store_true", help="Check that the checked-in summary is current.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    rendered = render_summary(repo_root, args.manifest)
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


def render_summary(repo_root: Path, manifest_path: str = "submission_manifest.yaml") -> str:
    manifest = load_submission_manifest(repo_root, manifest_path)
    region_files = load_region_files(repo_root, manifest_path)
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
    for region in region_files:
        worked_map = parse_worked_map(repo_root / region.map_path, region.map_format)
        audit = parse_erosion_audit(repo_root / region.audit_path, region.audit_format)
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
    for case, full_case in manifest.iter_full_cases():
        case_manifest = CaseManifest.model_validate(read_yaml(repo_root / case.case_path))
        map_text = (repo_root / full_case.map_path).read_text(encoding="utf-8")
        cluster_count = len(re.findall(r"^cluster_id:\s*", map_text, flags=re.MULTILINE))
        relation_count = len(re.findall(r"^relation_id:\s*", map_text, flags=re.MULTILINE))
        lines.append(
            f"| {case.label} | {len(case_manifest.sources)} | {cluster_count} | {relation_count} | "
            f"`{full_case.index_path}`, `{full_case.map_path}` |"
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
    for artifact in manifest.extension_artifacts:
        lines.append(
            f"| {artifact.artifact} | {artifact.case} | `{artifact.path}` | {artifact.status} |"
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
            f"- Investigator task queue items: `{_task_count(repo_root, manifest)}`",
            "",
            "## Interpretation",
            "",
            "These counts are not quality scores. They help judges verify that the submission includes source grounding, structured relations, cruxes, erosion findings, and multi-model comparators for the worked regions. Full-case coverage remains limited to LHC and eggs; the COVID artifact is a narrow worked region.",
            "",
        ]
    )
    return "\n".join(lines)


def _task_count(repo_root: Path, manifest: SubmissionManifest) -> int:
    count = 0
    for _case, queue in manifest.iter_task_queues():
        path = repo_root / queue.path
        if path.exists():
            count += len(re.findall(r"^task_id:\s*", path.read_text(encoding="utf-8"), flags=re.MULTILINE))
    return count


if __name__ == "__main__":
    raise SystemExit(main())
