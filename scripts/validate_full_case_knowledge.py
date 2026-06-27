from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest


CASES = (
    {
        "case_path": "data/cases/lhc_black_holes/case.yaml",
        "index_path": "examples/lhc_black_holes/full_case_index.md",
        "map_path": "examples/lhc_black_holes/full_case_map.md",
        "worked_anchor": "examples/lhc_black_holes/worked_region_cosmic_ray_map.md",
        "min_clusters": 8,
    },
    {
        "case_path": "data/cases/eggs/case.yaml",
        "index_path": "examples/eggs/full_case_index.md",
        "map_path": "examples/eggs/full_case_map.md",
        "worked_anchor": "examples/eggs/worked_region_observational_vs_rct_map.md",
        "min_clusters": 7,
    },
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate broad full-case knowledge-base scaffolds.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    failures: list[str] = []
    for case in CASES:
        _validate_case(repo_root, case, failures)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Validated full-case knowledge scaffolds")
    return 0


def _validate_case(repo_root: Path, case: dict[str, object], failures: list[str]) -> None:
    manifest = CaseManifest.model_validate(read_yaml(repo_root / str(case["case_path"])))
    index_path = repo_root / str(case["index_path"])
    map_path = repo_root / str(case["map_path"])
    worked_anchor = str(case["worked_anchor"])

    for path in (index_path, map_path):
        if not path.exists():
            failures.append(f"missing_full_case_file case={manifest.case_id} path={path.relative_to(repo_root)}")
            return
        text = path.read_text(encoding="utf-8")
        if "Status: `broad-source-scaffold`" not in text:
            failures.append(f"missing_broad_scaffold_status case={manifest.case_id} path={path.relative_to(repo_root)}")
        if worked_anchor not in text:
            failures.append(f"missing_worked_anchor case={manifest.case_id} path={path.relative_to(repo_root)}")
        if "Remaining Expansion Work" not in text and path == map_path:
            failures.append(f"missing_remaining_expansion_work case={manifest.case_id} path={path.relative_to(repo_root)}")
        for source in manifest.sources:
            if f"`{source.source_id}`" not in text:
                failures.append(
                    f"full_case_missing_source case={manifest.case_id} source={source.source_id} "
                    f"path={path.relative_to(repo_root)}"
                )

    map_text = map_path.read_text(encoding="utf-8")
    clusters = re.findall(r"^cluster_id:\s*([A-Za-z0-9_\\-]+)", map_text, flags=re.MULTILINE)
    relations = re.findall(r"^relation_id:\s*([A-Za-z0-9_\\-]+)", map_text, flags=re.MULTILINE)
    if len(clusters) < int(case["min_clusters"]):
        failures.append(f"too_few_full_case_clusters case={manifest.case_id} count={len(clusters)}")
    if len(relations) < 4:
        failures.append(f"too_few_full_case_relations case={manifest.case_id} count={len(relations)}")
    for required in ("Full-Case Thesis", "Knowledge Clusters", "Cross-Cluster Relations", "Full-Case Cruxes"):
        if required not in map_text:
            failures.append(f"full_case_missing_section case={manifest.case_id} section={required}")
    for cluster_id in clusters:
        if f"`{cluster_id}`" not in map_text and cluster_id not in map_text:
            failures.append(f"full_case_cluster_reference_issue case={manifest.case_id} cluster={cluster_id}")


if __name__ == "__main__":
    raise SystemExit(main())
