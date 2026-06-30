from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.submission_manifest import SubmissionManifest, ValidationThresholds, WorkedRegion, load_submission_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate curated FLF worked-region artifacts.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    parser.add_argument(
        "--region",
        help="Validate one worked region instead of all regions.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    manifest = load_submission_manifest(repo_root, args.manifest)
    failures: list[str] = []
    if args.region is None:
        for relative_path in manifest.required_docs:
            _require_file(repo_root / relative_path, failures)
            _require_no_template_status(repo_root / relative_path, failures)
            _require_no_todo(repo_root / relative_path, failures)
    selected_regions = [region for region in manifest.iter_worked_regions() if args.region in (None, region.region_id)]
    if args.region is not None and not selected_regions:
        failures.append(f"unknown_region region={args.region}")
    for region in selected_regions:
        _validate_region(repo_root, manifest, region, failures)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Validated worked regions")
    return 0


def _validate_region(repo_root: Path, manifest: SubmissionManifest, region: WorkedRegion, failures: list[str]) -> None:
    case = manifest.case_for_key(region.case_key)
    case_manifest = CaseManifest.model_validate(read_yaml(repo_root / case.case_path))
    source_ids = {source.source_id for source in case_manifest.sources}
    required_sources = set(region.required_sources)
    missing_manifest_sources = required_sources - source_ids
    for source_id in sorted(missing_manifest_sources):
        failures.append(f"required_source_missing region={region.region_id} source={source_id}")

    definition = repo_root / region.definition_path
    map_path = repo_root / region.map_path
    baseline = repo_root / region.baseline_path
    audit = repo_root / region.audit_path
    best = repo_root / region.best_path
    for path in (definition, map_path, baseline, audit, best):
        _require_file(path, failures)
        _require_no_template_status(path, failures)
        _require_no_todo(path, failures)

    if definition.exists():
        definition_text = definition.read_text(encoding="utf-8")
        for source_id in required_sources:
            if f"`{source_id}`" not in definition_text and source_id not in definition_text:
                failures.append(f"definition_missing_source region={region.region_id} source={source_id}")

    if map_path.exists():
        _validate_map(region.region_id, map_path, source_ids, region.thresholds, failures)
    if baseline.exists():
        _validate_baseline(region.region_id, baseline, required_sources, region.thresholds, failures)
    if audit.exists():
        _validate_audit(region.region_id, audit, region.thresholds, failures)
    if best.exists():
        _validate_best(region.region_id, best, failures)


def _validate_map(
    region_id: str, path: Path, source_ids: set[str], thresholds: ValidationThresholds, failures: list[str]
) -> None:
    text = path.read_text(encoding="utf-8")
    claim_ids = re.findall(r"claim_id:\s*([A-Za-z0-9_\\-]+)", text)
    relation_types = set(re.findall(r"relation_type:\s*([A-Za-z0-9_\\-]+)", text))
    crux_count = len(re.findall(r"(?i)crux", text))
    if not thresholds.min_claims <= len(claim_ids) <= thresholds.max_claims:
        failures.append(
            f"worked_map_claim_count region={region_id} count={len(claim_ids)} "
            f"expected={thresholds.min_claims}..{thresholds.max_claims} path={path}"
        )
    if len(set(claim_ids)) != len(claim_ids):
        failures.append(f"duplicate_claim_ids region={region_id} path={path}")
    if len(re.findall(r"source_id:\s*([A-Za-z0-9_\\-]+)", text)) < len(claim_ids):
        failures.append(f"worked_map_missing_source_ids region={region_id} path={path}")
    for source_id in re.findall(r"source_id:\s*([A-Za-z0-9_\\-]+)", text):
        if source_id not in source_ids:
            failures.append(f"unknown_worked_map_source region={region_id} source={source_id} path={path}")
    if text.count("excerpt:") < len(claim_ids):
        failures.append(f"worked_map_missing_excerpts region={region_id} path={path}")
    if text.count("entailed_by_excerpt:") < len(claim_ids):
        failures.append(f"worked_map_missing_entailment_checks region={region_id} path={path}")
    if re.search(r"entailed_by_excerpt:\s*no", text) and "audit concern" not in text.lower():
        failures.append(f"unsupported_claim_not_moved_to_audit region={region_id} path={path}")
    if len(re.findall(r"relation_id:\s*([A-Za-z0-9_\\-]+)", text)) == 0:
        failures.append(f"worked_map_missing_relations region={region_id} path={path}")
    if len(relation_types) < thresholds.min_relation_types:
        failures.append(f"worked_map_too_few_relation_types region={region_id} count={len(relation_types)} path={path}")
    if text.count("rationale:") < len(re.findall(r"relation_id:\s*([A-Za-z0-9_\\-]+)", text)):
        failures.append(f"worked_map_missing_relation_rationales region={region_id} path={path}")
    if crux_count < thresholds.min_crux_mentions:
        failures.append(f"worked_map_too_few_cruxes region={region_id} count={crux_count} path={path}")
    if "## Evidence Check" not in text:
        failures.append(f"worked_map_missing_evidence_check region={region_id} path={path}")
    evidence_rows = []
    in_evidence_check = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_evidence_check = line == "## Evidence Check"
            continue
        if not in_evidence_check or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0] not in {"Probe", "---"} and not set(cells[0]) <= {"-", ":"}:
            evidence_rows.append(cells)
    if len(evidence_rows) < thresholds.min_evidence_rows:
        failures.append(f"worked_map_evidence_check_too_short region={region_id} rows={len(evidence_rows)} path={path}")


def _validate_baseline(
    region_id: str, path: Path, required_sources: set[str], thresholds: ValidationThresholds, failures: list[str]
) -> None:
    text = path.read_text(encoding="utf-8")
    if "flat_baseline_prompt_v1" not in text:
        failures.append(f"baseline_missing_prompt_version region={region_id} path={path}")
    if "baseline_writer_had_access_to_curated_map" not in text:
        failures.append(f"baseline_missing_isolation_note region={region_id} path={path}")
    for source_id in required_sources:
        if source_id not in text:
            failures.append(f"baseline_missing_source region={region_id} source={source_id} path={path}")
    if len(text.split()) < thresholds.min_baseline_words:
        failures.append(f"baseline_too_short region={region_id} words={len(text.split())} path={path}")


def _validate_audit(region_id: str, path: Path, thresholds: ValidationThresholds, failures: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    losses = re.findall(r"loss_id:\s*([A-Za-z0-9_\\-]+)", text)
    if len(losses) < thresholds.min_losses:
        failures.append(f"erosion_audit_too_few_losses region={region_id} count={len(losses)} path={path}")
    if text.count("adversarial_check: survives") < thresholds.min_surviving_checks:
        failures.append(f"erosion_audit_too_few_surviving_checks region={region_id} path={path}")
    for required in ("lost_item:", "source_support:", "flat_baseline_omission:", "case_map_preserves:"):
        if text.count(required) < thresholds.min_losses:
            failures.append(f"erosion_audit_missing_field region={region_id} field={required} path={path}")


def _validate_best(region_id: str, path: Path, failures: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    required_sections = (
        "Strongest Claim Cluster",
        "Strongest Relation Cluster",
        "Strongest Crux",
        "Strongest Preserved Caveat Or Disagreement",
        "Strongest Flat-Synthesis Loss",
    )
    for section in required_sections:
        if section not in text:
            failures.append(f"best_regions_missing_section region={region_id} section={section} path={path}")


def _require_file(path: Path, failures: list[str]) -> None:
    if not path.exists():
        failures.append(f"missing_file path={path}")


def _require_no_template_status(path: Path, failures: list[str]) -> None:
    if path.exists() and "Status: `template`" in path.read_text(encoding="utf-8"):
        failures.append(f"template_not_filled path={path}")


def _require_no_todo(path: Path, failures: list[str]) -> None:
    if path.exists() and "TODO" in path.read_text(encoding="utf-8"):
        failures.append(f"todo_remaining path={path}")


if __name__ == "__main__":
    raise SystemExit(main())
