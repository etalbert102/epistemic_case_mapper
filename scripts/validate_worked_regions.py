from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from artifact_utils import parse_erosion_audit, parse_worked_map
from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.submission_manifest import SubmissionManifest, ValidationThresholds, WorkedRegion, load_submission_manifest

VALUE_PATTERN = r"([^\n\r]+)"


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
    source_paths = {
        source.source_id: source.path
        for source in case_manifest.sources
        if source.path
    }
    required_sources = set(region.required_sources)
    missing_manifest_sources = required_sources - source_ids
    for source_id in sorted(missing_manifest_sources):
        failures.append(f"required_source_missing region={region.region_id} source={source_id}")

    definition = repo_root / region.definition_path
    map_path = repo_root / region.map_path
    baseline = repo_root / region.baseline_path
    audit = repo_root / region.audit_path
    paths = [definition, map_path, baseline, audit]
    if region.thresholds.require_best_sections:
        if region.best_path is None:
            failures.append(f"missing_best_regions region={region.region_id}")
        else:
            paths.append(repo_root / region.best_path)
    for path in paths:
        _require_file(path, failures)
        _require_no_template_status(path, failures)
        _require_no_todo(path, failures)

    if definition.exists():
        definition_text = definition.read_text(encoding="utf-8")
        for source_id in required_sources:
            if f"`{source_id}`" not in definition_text and source_id not in definition_text:
                failures.append(f"definition_missing_source region={region.region_id} source={source_id}")

    if map_path.exists():
        _validate_map(
            region.region_id,
            map_path,
            region.map_format,
            source_ids,
            source_paths,
            case_manifest.evidence_mode == "source_grounded",
            region.thresholds,
            manifest,
            repo_root,
            failures,
        )
    if baseline.exists():
        _validate_baseline(region.region_id, baseline, required_sources, region.thresholds, failures)
    if audit.exists():
        _validate_audit(region.region_id, audit, region.audit_format, region.thresholds, failures)
    if region.best_path and (repo_root / region.best_path).exists() and region.thresholds.require_best_sections:
        _validate_best(region.region_id, repo_root / region.best_path, failures)


def _validate_map(
    region_id: str,
    path: Path,
    artifact_format: str,
    source_ids: set[str],
    source_paths: dict[str, str],
    require_source_grounding: bool,
    thresholds: ValidationThresholds,
    manifest: SubmissionManifest,
    repo_root: Path,
    failures: list[str],
) -> None:
    worked_map = parse_worked_map(path, artifact_format)
    claims = worked_map["claims"]
    relations = worked_map["relations"]
    claim_ids = [str(claim.get("claim_id", "")) for claim in claims]
    relation_ids = [str(relation.get("relation_id", "")) for relation in relations]
    relation_types = {str(relation.get("relation_type", "")) for relation in relations if relation.get("relation_type")}
    crux_count = len(worked_map.get("crux_candidates", []))
    if not thresholds.min_claims <= len(claim_ids) <= thresholds.max_claims:
        failures.append(
            f"worked_map_claim_count region={region_id} count={len(claim_ids)} "
            f"expected={thresholds.min_claims}..{thresholds.max_claims} path={path}"
        )
    if len(set(claim_ids)) != len(claim_ids):
        failures.append(f"duplicate_claim_ids region={region_id} path={path}")
    source_refs = [str(claim.get("source_id", "")) for claim in claims if claim.get("source_id")]
    if len(source_refs) < len(claim_ids):
        failures.append(f"worked_map_missing_source_ids region={region_id} path={path}")
    for source_id in source_refs:
        if source_id not in source_ids:
            failures.append(f"unknown_worked_map_source region={region_id} source={source_id} path={path}")
    if sum(1 for claim in claims if claim.get("excerpt")) < len(claim_ids):
        failures.append(f"worked_map_missing_excerpts region={region_id} path={path}")
    if sum(1 for claim in claims if claim.get("entailed_by_excerpt")) < len(claim_ids):
        failures.append(f"worked_map_missing_entailment_checks region={region_id} path={path}")
    if require_source_grounding:
        for claim in claims:
            _validate_claim_source_span(
                repo_root,
                region_id,
                claim,
                source_paths,
                failures,
            )
    text = path.read_text(encoding="utf-8")
    if any(str(claim.get("entailed_by_excerpt", "")).lower() == "no" for claim in claims) and "audit concern" not in text.lower():
        failures.append(f"unsupported_claim_not_moved_to_audit region={region_id} path={path}")
    if thresholds.min_relation_types > 0 and len(relation_ids) == 0:
        failures.append(f"worked_map_missing_relations region={region_id} path={path}")
    if len(relation_types) < thresholds.min_relation_types:
        failures.append(f"worked_map_too_few_relation_types region={region_id} count={len(relation_types)} path={path}")
    permitted_relation_types = manifest.relation_ontology.permitted_types()
    for relation_type in sorted(relation_types):
        if relation_type not in permitted_relation_types:
            failures.append(f"worked_map_unknown_relation_type region={region_id} type={relation_type} path={path}")
    if sum(1 for relation in relations if relation.get("rationale")) < len(relation_ids):
        failures.append(f"worked_map_missing_relation_rationales region={region_id} path={path}")
    if crux_count < thresholds.min_crux_mentions:
        failures.append(f"worked_map_too_few_cruxes region={region_id} count={crux_count} path={path}")
    evidence_rows = worked_map.get("evidence_check", [])
    if not evidence_rows:
        failures.append(f"worked_map_missing_evidence_check region={region_id} path={path}")
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


def _validate_audit(region_id: str, path: Path, artifact_format: str, thresholds: ValidationThresholds, failures: list[str]) -> None:
    audit = parse_erosion_audit(path, artifact_format)
    losses = audit["losses"]
    if len(losses) < thresholds.min_losses:
        failures.append(f"erosion_audit_too_few_losses region={region_id} count={len(losses)} path={path}")
    if sum(1 for loss in losses if str(loss.get("adversarial_check", "")).lower().startswith("survives")) < thresholds.min_surviving_checks:
        failures.append(f"erosion_audit_too_few_surviving_checks region={region_id} path={path}")
    for required in ("lost_item", "source_support", "flat_baseline_omission", "case_map_preserves"):
        if sum(1 for loss in losses if loss.get(required)) < thresholds.min_losses:
            failures.append(f"erosion_audit_missing_field region={region_id} field={required}: path={path}")


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


def _validate_claim_source_span(
    repo_root: Path,
    region_id: str,
    claim: dict[str, object],
    source_paths: dict[str, str],
    failures: list[str],
) -> None:
    claim_id = str(claim.get("claim_id", "<unknown>"))
    source_id = str(claim.get("source_id", ""))
    relative_path = source_paths.get(source_id)
    if not relative_path:
        failures.append(
            f"worked_map_source_path_missing region={region_id} claim={claim_id} source={source_id}"
        )
        return
    source_path = repo_root / relative_path
    if not source_path.is_file():
        failures.append(
            f"worked_map_source_file_missing region={region_id} claim={claim_id} path={relative_path}"
        )
        return
    lines = source_path.read_text(encoding="utf-8").split("\n")
    source_span = str(claim.get("source_span", ""))
    if source_span == "first non-empty line":
        ranges = [
            (line_number, line_number)
            for line_number, line in enumerate(lines, start=1)
            if line.strip()
        ][:1]
    else:
        ranges = _parse_line_ranges(source_span)
    if not ranges:
        failures.append(
            f"worked_map_source_span_invalid region={region_id} claim={claim_id}"
        )
        return
    for start, end in ranges:
        if start < 1 or end < start or end > len(lines):
            failures.append(
                f"worked_map_source_span_out_of_range region={region_id} "
                f"claim={claim_id} span={start}-{end}"
            )
            return
    span_tokens = _ordered_tokens(
        "\n".join(
            line
            for start, end in ranges
            for line in lines[start - 1 : end]
        )
    )
    excerpt = str(claim.get("excerpt", "")).strip('"')
    fragments = [
        tokens
        for fragment in re.split(r"\.\.\.", excerpt)
        if (tokens := _ordered_tokens(fragment))
    ]
    if sum(map(len, fragments)) < 2 or any(
        not _is_subsequence(fragment, span_tokens) for fragment in fragments
    ):
        failures.append(
            f"worked_map_excerpt_not_grounded region={region_id} claim={claim_id}"
        )


def _parse_line_ranges(value: str) -> list[tuple[int, int]]:
    if not re.fullmatch(r"(?:lines? )?\d+(?:-\d+)?(?: and \d+(?:-\d+)?)*", value):
        return []
    ranges: list[tuple[int, int]] = []
    for start_text, end_text in re.findall(r"(\d+)(?:-(\d+))?", value):
        start = int(start_text)
        ranges.append((start, int(end_text) if end_text else start))
    return ranges


def _ordered_tokens(value: str) -> list[str]:
    stop_words = {
        "a", "an", "and", "are", "as", "be", "by", "for", "has", "have",
        "in", "is", "of", "on", "or", "some", "that", "the", "this", "to",
        "were", "will", "with", "would",
    }
    value = re.sub(r"10\s*\^\s*(\d+)", r"10\1", value)
    value = re.sub(r"-\s*\n\s*", " ", value)
    value = re.sub(r"\btern\b", "term", value, flags=re.IGNORECASE)
    return [
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if token not in stop_words
    ]


def _is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    needle_position = 0
    haystack_position = 0
    while needle_position < len(needle) and haystack_position < len(haystack):
        if needle[needle_position] == haystack[haystack_position]:
            needle_position += 1
            haystack_position += 1
        elif (
            haystack_position + 1 < len(haystack)
            and needle[needle_position]
            == haystack[haystack_position] + haystack[haystack_position + 1]
        ):
            needle_position += 1
            haystack_position += 2
        elif (
            needle_position + 1 < len(needle)
            and needle[needle_position] + needle[needle_position + 1]
            == haystack[haystack_position]
        ):
            needle_position += 2
            haystack_position += 1
        else:
            haystack_position += 1
    return needle_position == len(needle)


def _require_file(path: Path, failures: list[str]) -> None:
    if not path.exists():
        failures.append(f"missing_file path={path}")


def _require_no_template_status(path: Path, failures: list[str]) -> None:
    if path.exists() and "Status: `template`" in path.read_text(encoding="utf-8"):
        failures.append(f"template_not_filled path={path}")


def _require_no_todo(path: Path, failures: list[str]) -> None:
    if path.exists() and "TODO" in path.read_text(encoding="utf-8"):
        failures.append(f"todo_remaining path={path}")


def _clean_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
