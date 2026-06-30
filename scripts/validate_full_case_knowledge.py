from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.submission_manifest import FullCaseScaffold, SubmissionCase, load_submission_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate broad full-case knowledge-base scaffolds.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    manifest = load_submission_manifest(repo_root, args.manifest)
    failures: list[str] = []
    for case, full_case in manifest.iter_full_cases():
        _validate_case(repo_root, case, full_case, failures)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Validated full-case knowledge scaffolds")
    return 0


def _validate_case(repo_root: Path, case: SubmissionCase, full_case: FullCaseScaffold, failures: list[str]) -> None:
    manifest = CaseManifest.model_validate(read_yaml(repo_root / case.case_path))
    index_path = repo_root / full_case.index_path
    map_path = repo_root / full_case.map_path
    worked_anchor = full_case.worked_anchor

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
    if len(clusters) < full_case.min_clusters:
        failures.append(f"too_few_full_case_clusters case={manifest.case_id} count={len(clusters)}")
    if len(relations) < full_case.min_relations:
        failures.append(f"too_few_full_case_relations case={manifest.case_id} count={len(relations)}")
    for required in ("Full-Case Thesis", "Knowledge Clusters", "Cross-Cluster Relations", "Full-Case Cruxes"):
        if required not in map_text:
            failures.append(f"full_case_missing_section case={manifest.case_id} section={required}")
    for cluster_id in clusters:
        if f"`{cluster_id}`" not in map_text and cluster_id not in map_text:
            failures.append(f"full_case_cluster_reference_issue case={manifest.case_id} cluster={cluster_id}")


if __name__ == "__main__":
    raise SystemExit(main())
