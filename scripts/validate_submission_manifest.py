from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from artifact_utils import parse_erosion_audit, parse_worked_map
from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.submission_manifest import (
    BlindedBaseline,
    SourceSpan,
    SubmissionCase,
    SubmissionManifest,
    UpdateDemo,
    WorkedRegion,
    load_submission_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the submission manifest wiring.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    manifest = load_submission_manifest(repo_root, args.manifest)
    failures: list[str] = []

    _validate_uniqueness(manifest, failures)
    _validate_id_patterns(manifest, failures)
    _validate_top_level_paths(repo_root, manifest, failures)
    for case in manifest.cases:
        _validate_case(repo_root, manifest, case, failures)
    for artifact in manifest.extension_artifacts:
        _require_path(repo_root, artifact.path, failures, "extension_artifact_missing")
    for update_demo in manifest.update_demos:
        _validate_update_demo_config(repo_root, manifest, update_demo, failures)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Validated submission manifest")
    return 0


def _validate_uniqueness(manifest: SubmissionManifest, failures: list[str]) -> None:
    _require_unique("case_key", [case.case_key for case in manifest.cases], failures)
    _require_unique("case_id", [case.case_id for case in manifest.cases], failures)
    _require_unique("region_id", [region.region_id for region in manifest.iter_worked_regions()], failures)
    _require_unique(
        "baseline_id",
        [manifest.baseline_id_for(region, baseline) for region, baseline in manifest.iter_blinded_baselines()],
        failures,
    )


def _require_unique(label: str, values: list[str], failures: list[str]) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            failures.append(f"duplicate_manifest_{label} value={value}")
        seen.add(value)


def _validate_id_patterns(manifest: SubmissionManifest, failures: list[str]) -> None:
    for label, pattern in (
        ("claim", manifest.id_patterns.claim),
        ("relation", manifest.id_patterns.relation),
        ("loss", manifest.id_patterns.loss),
    ):
        try:
            re.compile(pattern)
        except re.error as exc:
            failures.append(f"invalid_id_pattern kind={label} error={exc}")


def _validate_top_level_paths(repo_root: Path, manifest: SubmissionManifest, failures: list[str]) -> None:
    for relative_path in manifest.judge_paths:
        _require_path(repo_root, relative_path, failures, "judge_path_missing")
    for relative_path in manifest.required_docs:
        _require_path(repo_root, relative_path, failures, "required_doc_missing")
    for relative_path in manifest.reference_scan_paths:
        _require_path(repo_root, relative_path, failures, "reference_scan_path_missing")


def _validate_case(
    repo_root: Path,
    manifest: SubmissionManifest,
    case: SubmissionCase,
    failures: list[str],
) -> None:
    if not _require_path(repo_root, case.case_path, failures, "case_manifest_missing"):
        return
    if case.examples_path is not None:
        _require_path(repo_root, case.examples_path, failures, "examples_path_missing")

    case_manifest = CaseManifest.model_validate(read_yaml(repo_root / case.case_path))
    source_ids = {source.source_id for source in case_manifest.sources}
    for region in case.worked_regions:
        if region.case_key != case.case_key:
            failures.append(
                f"worked_region_case_key_mismatch region={region.region_id} "
                f"parent={case.case_key} child={region.case_key}"
            )
        _validate_region(repo_root, manifest, case, source_ids, region, failures)

    if case.ui.include and not case.worked_regions:
        failures.append(f"ui_case_has_no_worked_region case={case.case_key}")
    if case.ui.review_packet_path is not None:
        _require_path(repo_root, case.ui.review_packet_path, failures, "ui_review_packet_missing")
    if case.ui.review_checklist_path is not None:
        _require_path(repo_root, case.ui.review_checklist_path, failures, "ui_review_checklist_missing")
    if case.ui.multi_model_audit_path is not None:
        _require_path(repo_root, case.ui.multi_model_audit_path, failures, "ui_multi_model_audit_missing")

    if case.full_case is not None:
        _require_path(repo_root, case.full_case.index_path, failures, "full_case_index_missing")
        _require_path(repo_root, case.full_case.map_path, failures, "full_case_map_missing")
        _require_path(repo_root, case.full_case.worked_anchor, failures, "full_case_anchor_missing")
        if case.full_case.baseline_path is not None:
            _require_path(repo_root, case.full_case.baseline_path, failures, "full_case_baseline_missing")

    if case.task_queue is not None:
        _require_path(repo_root, case.task_queue.path, failures, "task_queue_missing")


def _validate_region(
    repo_root: Path,
    manifest: SubmissionManifest,
    case: SubmissionCase,
    source_ids: set[str],
    region: WorkedRegion,
    failures: list[str],
) -> None:
    if region.case_label != case.label:
        failures.append(
            f"worked_region_case_label_mismatch region={region.region_id} "
            f"parent={case.label!r} child={region.case_label!r}"
        )
    for source_id in region.required_sources:
        if source_id not in source_ids:
            failures.append(f"region_required_source_unknown region={region.region_id} source={source_id}")
    paths = (
        ("region_definition_missing", region.definition_path),
        ("worked_map_missing", region.map_path),
        ("region_baseline_missing", region.baseline_path),
        ("region_audit_missing", region.audit_path),
    )
    for failure_label, relative_path in paths:
        _require_path(repo_root, relative_path, failures, failure_label)
    if region.thresholds.require_best_sections:
        if region.best_path is None:
            failures.append(f"region_best_missing region={region.region_id}")
        else:
            _require_path(repo_root, region.best_path, failures, "region_best_missing")

    if region.review is not None:
        _validate_review_ids(repo_root, manifest, region, failures)
    if region.blinded_baseline is not None:
        _validate_blinded_baseline(repo_root, source_ids, region, region.blinded_baseline, failures)


def _validate_review_ids(
    repo_root: Path,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    failures: list[str],
) -> None:
    if region.review is None:
        return
    if region.review.worked_region_id != region.region_id:
        failures.append(
            f"review_region_id_mismatch region={region.region_id} review={region.review.worked_region_id}"
        )
    try:
        worked_map = parse_worked_map(repo_root / region.map_path, region.map_format)
        audit = parse_erosion_audit(repo_root / region.audit_path, region.audit_format)
    except FileNotFoundError:
        return

    claim_ids = {claim.get("claim_id", "") for claim in worked_map["claims"]}
    relation_ids = {relation.get("relation_id", "") for relation in worked_map["relations"]}
    loss_ids = {loss.get("loss_id", "") for loss in audit["losses"]}
    for claim_id in region.review.claim_ids:
        if claim_id not in claim_ids:
            failures.append(f"review_unknown_claim_id region={region.region_id} claim={claim_id}")
    for relation_id in region.review.relation_ids:
        if relation_id not in relation_ids:
            failures.append(f"review_unknown_relation_id region={region.region_id} relation={relation_id}")
    for loss_id in region.review.loss_ids:
        if loss_id not in loss_ids:
            failures.append(f"review_unknown_loss_id region={region.region_id} loss={loss_id}")

    prefix = region.id_prefix
    known_prefixes = manifest.known_id_prefixes()
    if prefix not in known_prefixes:
        failures.append(f"review_unknown_id_prefix region={region.region_id} prefix={prefix}")


def _validate_blinded_baseline(
    repo_root: Path,
    case_source_ids: set[str],
    region: WorkedRegion,
    baseline: BlindedBaseline,
    failures: list[str],
) -> None:
    for source_id in baseline.required_sources:
        if source_id not in case_source_ids:
            failures.append(f"blinded_baseline_required_source_unknown region={region.region_id} source={source_id}")
    span_sources = {span.source_id for span in baseline.spans}
    for source_id in baseline.required_sources:
        if source_id not in span_sources:
            failures.append(f"blinded_baseline_missing_span region={region.region_id} source={source_id}")
    for span in baseline.spans:
        _validate_source_span(repo_root, case_source_ids, region, span, failures)


def _validate_source_span(
    repo_root: Path,
    case_source_ids: set[str],
    region: WorkedRegion,
    span: SourceSpan,
    failures: list[str],
) -> None:
    if span.source_id not in case_source_ids:
        failures.append(f"blinded_baseline_span_source_unknown region={region.region_id} source={span.source_id}")
    if not _require_path(repo_root, span.path, failures, "blinded_baseline_span_path_missing"):
        return
    line_count = len((repo_root / span.path).read_text(encoding="utf-8").splitlines())
    for start, end in span.ranges:
        if start < 1 or end < start or end > line_count:
            failures.append(
                f"blinded_baseline_span_out_of_range region={region.region_id} "
                f"source={span.source_id} range={start}-{end} lines={line_count}"
            )


def _validate_update_demo_config(
    repo_root: Path,
    manifest: SubmissionManifest,
    update_demo: UpdateDemo,
    failures: list[str],
) -> None:
    try:
        manifest.case_for_key(update_demo.case_key)
    except KeyError:
        failures.append(f"update_demo_unknown_case demo={update_demo.demo_id} case={update_demo.case_key}")
    _require_path(repo_root, update_demo.path, failures, "update_demo_path_missing")
    if not update_demo.claim_id_prefix:
        failures.append(f"update_demo_missing_claim_prefix demo={update_demo.demo_id}")
    if not update_demo.relation_id_prefix:
        failures.append(f"update_demo_missing_relation_prefix demo={update_demo.demo_id}")


def _require_path(repo_root: Path, relative_path: str, failures: list[str], failure_label: str) -> bool:
    if not (repo_root / relative_path).exists():
        failures.append(f"{failure_label} path={relative_path}")
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
