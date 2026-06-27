from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest


REGIONS = (
    {
        "region_id": "lhc_cosmic_ray_argument",
        "case_path": "data/cases/lhc_black_holes/case.yaml",
        "definition": "docs/worked_regions/lhc_cosmic_ray_argument.md",
        "map": "examples/lhc_black_holes/worked_region_cosmic_ray_map.md",
        "baseline": "examples/lhc_black_holes/flat_synthesis_baseline.md",
        "audit": "examples/lhc_black_holes/decision_space_erosion_audit.md",
        "best": "examples/lhc_black_holes/BEST_REGIONS.md",
        "required_sources": {
            "lsag_2008_safety_review",
            "spc_2008_lsag_review",
            "giddings_mangano_2008_stable_black_holes",
            "plaga_2008_metastable_black_holes",
            "giddings_mangano_2008_comments_plaga",
        },
    },
    {
        "region_id": "eggs_observational_vs_rct",
        "case_path": "data/cases/eggs/case.yaml",
        "definition": "docs/worked_regions/eggs_observational_vs_rct.md",
        "map": "examples/eggs/worked_region_observational_vs_rct_map.md",
        "baseline": "examples/eggs/flat_synthesis_baseline.md",
        "audit": "examples/eggs/decision_space_erosion_audit.md",
        "best": "examples/eggs/BEST_REGIONS.md",
        "required_sources": {
            "dga_2020_2025_pmc_summary",
            "aha_2019_dietary_cholesterol_pubmed",
            "aha_2023_dietary_cholesterol_news",
            "bmj_2020_egg_consumption_cvd",
            "jama_2019_dietary_cholesterol_eggs",
            "li_2020_egg_cholesterol_rct_meta",
            "nnr_2023_eggs_scoping_review",
        },
    },
)

REQUIRED_GLOBAL_FILES = (
    "docs/ARCHITECTURE.md",
    "docs/FLF_BEFORE_AFTER_COMPARISON.md",
    "docs/FLF_JUDGE_INDEX.md",
    "docs/FLF_JUDGE_WALKTHROUGH.md",
    "docs/FLF_SUBMISSION_DRAFT.md",
    "docs/HUMAN_REVIEW_CHECKLIST.md",
    "docs/SUBMISSION_ARTIFACT_SUMMARY.md",
    "docs/SUBMISSION_LIMITATIONS.md",
    "docs/SUBMISSION_PACKET.md",
    "docs/review/EGGS_HUMAN_AUDIT_CHECKLIST.csv",
    "docs/review/EGGS_HUMAN_AUDIT_PACKET.md",
    "docs/review/LHC_HUMAN_AUDIT_CHECKLIST.csv",
    "docs/review/LHC_HUMAN_AUDIT_PACKET.md",
    "docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate curated FLF worked-region artifacts.")
    parser.add_argument(
        "--region",
        choices=[str(region["region_id"]) for region in REGIONS],
        help="Validate one worked region instead of all regions.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    failures: list[str] = []
    if args.region is None:
        for relative_path in REQUIRED_GLOBAL_FILES:
            _require_file(repo_root / relative_path, failures)
            _require_no_template_status(repo_root / relative_path, failures)
            _require_no_todo(repo_root / relative_path, failures)
    selected_regions = [region for region in REGIONS if args.region in (None, region["region_id"])]
    for region in selected_regions:
        _validate_region(repo_root, region, failures)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Validated worked regions")
    return 0


def _validate_region(repo_root: Path, region: dict, failures: list[str]) -> None:
    manifest = CaseManifest.model_validate(read_yaml(repo_root / str(region["case_path"])))
    source_ids = {source.source_id for source in manifest.sources}
    required_sources = set(region["required_sources"])
    missing_manifest_sources = required_sources - source_ids
    for source_id in sorted(missing_manifest_sources):
        failures.append(f"required_source_missing region={region['region_id']} source={source_id}")

    definition = repo_root / str(region["definition"])
    map_path = repo_root / str(region["map"])
    baseline = repo_root / str(region["baseline"])
    audit = repo_root / str(region["audit"])
    best = repo_root / str(region["best"])
    for path in (definition, map_path, baseline, audit, best):
        _require_file(path, failures)
        _require_no_template_status(path, failures)
        _require_no_todo(path, failures)

    if definition.exists():
        definition_text = definition.read_text(encoding="utf-8")
        for source_id in required_sources:
            if f"`{source_id}`" not in definition_text and source_id not in definition_text:
                failures.append(f"definition_missing_source region={region['region_id']} source={source_id}")

    if map_path.exists():
        _validate_map(region["region_id"], map_path, source_ids, failures)
    if baseline.exists():
        _validate_baseline(region["region_id"], baseline, required_sources, failures)
    if audit.exists():
        _validate_audit(region["region_id"], audit, failures)
    if best.exists():
        _validate_best(region["region_id"], best, failures)


def _validate_map(region_id: str, path: Path, source_ids: set[str], failures: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    claim_ids = re.findall(r"claim_id:\s*([A-Za-z0-9_\\-]+)", text)
    relation_types = set(re.findall(r"relation_type:\s*([A-Za-z0-9_\\-]+)", text))
    crux_count = len(re.findall(r"(?i)crux", text))
    if not 12 <= len(claim_ids) <= 25:
        failures.append(f"worked_map_claim_count region={region_id} count={len(claim_ids)} expected=12..25 path={path}")
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
    if len(relation_types) < 3:
        failures.append(f"worked_map_too_few_relation_types region={region_id} count={len(relation_types)} path={path}")
    if text.count("rationale:") < len(re.findall(r"relation_id:\s*([A-Za-z0-9_\\-]+)", text)):
        failures.append(f"worked_map_missing_relation_rationales region={region_id} path={path}")
    if crux_count < 2:
        failures.append(f"worked_map_too_few_cruxes region={region_id} count={crux_count} path={path}")
    scores = []
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[1].isdigit():
            scores.append(int(cells[1]))
    if len(scores) < 4:
        failures.append(f"worked_map_missing_flf_scores region={region_id} path={path}")
    elif min(scores[:4]) == 0:
        failures.append(f"worked_map_flf_score_zero region={region_id} scores={scores[:4]} path={path}")


def _validate_baseline(region_id: str, path: Path, required_sources: set[str], failures: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    if "flat_baseline_prompt_v1" not in text:
        failures.append(f"baseline_missing_prompt_version region={region_id} path={path}")
    if "baseline_writer_had_access_to_curated_map" not in text:
        failures.append(f"baseline_missing_isolation_note region={region_id} path={path}")
    for source_id in required_sources:
        if source_id not in text:
            failures.append(f"baseline_missing_source region={region_id} source={source_id} path={path}")
    if len(text.split()) < 250:
        failures.append(f"baseline_too_short region={region_id} words={len(text.split())} path={path}")


def _validate_audit(region_id: str, path: Path, failures: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    losses = re.findall(r"loss_id:\s*([A-Za-z0-9_\\-]+)", text)
    if len(losses) < 5:
        failures.append(f"erosion_audit_too_few_losses region={region_id} count={len(losses)} path={path}")
    if text.count("adversarial_check: survives") < 5:
        failures.append(f"erosion_audit_too_few_surviving_checks region={region_id} path={path}")
    for required in ("lost_item:", "source_support:", "flat_baseline_omission:", "case_map_preserves:"):
        if text.count(required) < 5:
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
