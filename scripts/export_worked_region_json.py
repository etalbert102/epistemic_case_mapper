from __future__ import annotations

import argparse
import json
from pathlib import Path

from artifact_utils import load_region_files, parse_erosion_audit, parse_worked_map


def main() -> int:
    parser = argparse.ArgumentParser(description="Export curated worked-region Markdown maps to structured JSON.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    parser.add_argument("--region", help="Export one worked region instead of all regions.")
    parser.add_argument("--check", action="store_true", help="Check that checked-in JSON exports are current.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    failures: list[str] = []
    selected_regions = [region for region in load_region_files(repo_root, args.manifest) if args.region in (None, region.region_id)]
    if args.region is not None and not selected_regions:
        failures.append(f"unknown_region region={args.region}")
    for region in selected_regions:
        payload = {
            "case_key": region.case_key,
            "case_label": region.case_label,
            "region_id": region.region_id,
            "worked_map": parse_worked_map(repo_root / region.map_path, region.map_format),
            "erosion_audit": parse_erosion_audit(repo_root / region.audit_path, region.audit_format),
        }
        rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        output_path = repo_root / region.output_json_path
        if args.check:
            if not output_path.exists():
                failures.append(f"missing_export path={region.output_json_path}")
            elif output_path.read_text(encoding="utf-8") != rendered:
                failures.append(f"stale_export path={region.output_json_path}")
        else:
            output_path.write_text(rendered, encoding="utf-8")
            print(f"Wrote {region.output_json_path}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    if args.check:
        print("Structured worked-region exports are current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
