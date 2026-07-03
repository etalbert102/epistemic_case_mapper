from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest, CaseMap
from epistemic_case_mapper.starter_mapper import build_starter_case_map


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated case-map artifacts.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--case", required=True, help="Path to case.yaml")
    parser.add_argument("--artifacts-root", default="artifacts")
    parser.add_argument("--examples", help="Checked-in example directory to compare against")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    manifest_path = (repo_root / args.case).resolve()
    manifest = CaseManifest.model_validate(read_yaml(manifest_path))
    artifact_dir = repo_root / args.artifacts_root / manifest.case_id

    failures: list[str] = []
    case_map = _load_case_map(artifact_dir / "case_map.json", failures)
    if case_map is not None:
        _validate_manifest_alignment(manifest, case_map, failures)
        _validate_case_map(case_map, failures)
        _validate_preservation_metadata(manifest, case_map, repo_root, failures)
        _validate_workflow_telemetry(case_map, failures)
        _validate_determinism(manifest, repo_root, failures)
    _validate_markdown(artifact_dir, manifest, failures)
    if args.examples:
        _validate_snapshot_parity(artifact_dir, repo_root / args.examples, failures)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"Validated {manifest.case_id}")
    return 0


def _load_case_map(path: Path, failures: list[str]) -> CaseMap | None:
    if not path.exists():
        failures.append(f"missing_artifact path={path} next=run scripts/build_case_map.py")
        return None
    try:
        return CaseMap.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001
        failures.append(f"invalid_case_map path={path} error={exc}")
        return None


def _validate_manifest_alignment(manifest: CaseManifest, case_map: CaseMap, failures: list[str]) -> None:
    if case_map.case_id != manifest.case_id:
        failures.append(f"case_id_mismatch expected={manifest.case_id} actual={case_map.case_id}")
    if case_map.evidence_mode != manifest.evidence_mode:
        failures.append(f"evidence_mode_mismatch expected={manifest.evidence_mode} actual={case_map.evidence_mode}")
    if case_map.review_status != manifest.review_status:
        failures.append(f"review_status_mismatch expected={manifest.review_status} actual={case_map.review_status}")


def _validate_case_map(case_map: CaseMap, failures: list[str]) -> None:
    if case_map.evidence_mode not in {"seed", "source_grounded"}:
        failures.append(f"invalid_evidence_mode case={case_map.case_id} value={case_map.evidence_mode}")
    if case_map.review_status not in {"draft", "agent-reviewed", "human-review-needed", "human-reviewed"}:
        failures.append(f"invalid_review_status case={case_map.case_id} value={case_map.review_status}")
    if not case_map.sources:
        failures.append(f"missing_sources case={case_map.case_id}")
    if not case_map.claims:
        failures.append(f"missing_claims case={case_map.case_id}")
    if len(case_map.open_questions) < 3:
        failures.append(f"too_few_open_questions case={case_map.case_id} count={len(case_map.open_questions)} min=3")

    source_ids = {source.source_id for source in case_map.sources}
    claim_ids = {claim.claim_id for claim in case_map.claims}
    _validate_sources(case_map, failures)
    _validate_claims(case_map, source_ids, failures)
    _validate_relations(case_map, claim_ids, failures)
    _validate_open_questions(case_map, failures)


def _validate_sources(case_map: CaseMap, failures: list[str]) -> None:
    for source in case_map.sources:
        if not source.title:
            failures.append(f"missing_source_title source={source.source_id}")
        if not source.source_type:
            failures.append(f"missing_source_type source={source.source_id}")
        if case_map.evidence_mode == "source_grounded":
            if source.url and not source.retrieval_date:
                failures.append(f"missing_retrieval_date source={source.source_id} url={source.url}")
            if not (source.excerpt or source.text or source.path):
                failures.append(f"missing_source_excerpt source={source.source_id}")


def _validate_claims(case_map: CaseMap, source_ids: set[str], failures: list[str]) -> None:
    for claim in case_map.claims:
        if claim.source_id not in source_ids:
            failures.append(f"unknown_claim_source claim={claim.claim_id} source={claim.source_id}")
        if not claim.text:
            failures.append(f"missing_claim_text claim={claim.claim_id}")
        if not claim.source_span:
            failures.append(f"missing_claim_span claim={claim.claim_id}")
        if claim.source_start is None or claim.source_end is None:
            failures.append(f"missing_claim_offsets claim={claim.claim_id}")
        elif claim.source_start < 0 or claim.source_end <= claim.source_start:
            failures.append(
                f"invalid_claim_offsets claim={claim.claim_id} start={claim.source_start} end={claim.source_end}"
            )
        if not claim.source_text_hash:
            failures.append(f"missing_claim_source_text_hash claim={claim.claim_id}")
        if not claim.excerpt_hash:
            failures.append(f"missing_claim_excerpt_hash claim={claim.claim_id}")
        if claim.extraction_method == "unspecified":
            failures.append(f"missing_claim_extraction_method claim={claim.claim_id}")
        if claim.provenance_tag not in {"local_source_text", "local_seed_note", "user_provided", "model_generated_proposal"}:
            failures.append(f"invalid_claim_provenance_tag claim={claim.claim_id} tag={claim.provenance_tag}")
        if claim.review_state == "human_reviewed" and claim.entailed_by_excerpt != "yes":
            failures.append(f"human_reviewed_claim_not_entailed claim={claim.claim_id}")
        if not claim.confidence:
            failures.append(f"missing_claim_confidence claim={claim.claim_id}")


def _validate_relations(case_map: CaseMap, claim_ids: set[str], failures: list[str]) -> None:
    for relation in case_map.relations:
        if relation.source_claim_id not in claim_ids:
            failures.append(f"unknown_relation_source relation={relation.relation_id} claim={relation.source_claim_id}")
        if relation.target_claim_id not in claim_ids:
            failures.append(f"unknown_relation_target relation={relation.relation_id} claim={relation.target_claim_id}")
        if not relation.rationale:
            failures.append(f"missing_relation_rationale relation={relation.relation_id}")


def _validate_open_questions(case_map: CaseMap, failures: list[str]) -> None:
    for question in case_map.open_questions:
        if not question.text:
            failures.append(f"missing_open_question_text question={question.question_id}")
        if not (question.linked_claim_ids or question.linked_source_ids or question.gap_type == "missing source needed"):
            failures.append(f"unlinked_open_question question={question.question_id}")
        for claim_id in question.linked_claim_ids:
            if claim_id not in claim_ids:
                failures.append(f"unknown_open_question_claim question={question.question_id} claim={claim_id}")
        for source_id in question.linked_source_ids:
            if source_id not in source_ids:
                failures.append(f"unknown_open_question_source question={question.question_id} source={source_id}")


def _validate_preservation_metadata(
    manifest: CaseManifest, case_map: CaseMap, repo_root: Path, failures: list[str]
) -> None:
    for relative_path in manifest.metadata_files:
        path = repo_root / relative_path
        if not path.exists():
            failures.append(f"missing_manifest_metadata_file path={path}")
    if not manifest.metadata_files:
        return
    preservation_metadata = case_map.metadata.get("preservation_metadata")
    if not isinstance(preservation_metadata, dict):
        failures.append(f"missing_preservation_metadata case={case_map.case_id}")
        return
    files = preservation_metadata.get("files")
    if not isinstance(files, list) or len(files) != len(manifest.metadata_files):
        failures.append(
            f"metadata_file_count_mismatch case={case_map.case_id} expected={len(manifest.metadata_files)} actual={len(files) if isinstance(files, list) else 'missing'}"
        )
        return
    indexed = {item.get("path") for item in files if isinstance(item, dict)}
    for relative_path in manifest.metadata_files:
        if relative_path not in indexed:
            failures.append(f"metadata_file_not_in_case_map case={case_map.case_id} path={relative_path}")
    missing = [item.get("path") for item in files if isinstance(item, dict) and not item.get("exists")]
    for relative_path in missing:
        failures.append(f"metadata_file_marked_missing case={case_map.case_id} path={relative_path}")


def _validate_workflow_telemetry(case_map: CaseMap, failures: list[str]) -> None:
    telemetry = case_map.metadata.get("workflow_telemetry")
    if not isinstance(telemetry, dict):
        failures.append(f"missing_workflow_telemetry case={case_map.case_id}")
        return
    extraction = telemetry.get("extraction")
    if not isinstance(extraction, dict):
        failures.append(f"missing_extraction_telemetry case={case_map.case_id}")
        return
    if extraction.get("total_claims_created") != len(case_map.claims):
        failures.append(
            f"claim_telemetry_mismatch case={case_map.case_id} telemetry={extraction.get('total_claims_created')} actual={len(case_map.claims)}"
        )
    sources = extraction.get("sources")
    if not isinstance(sources, list) or len(sources) != len(case_map.sources):
        failures.append(
            f"source_telemetry_count_mismatch case={case_map.case_id} telemetry={len(sources) if isinstance(sources, list) else 'missing'} actual={len(case_map.sources)}"
        )
    if "relation_mapping" not in telemetry:
        failures.append(f"missing_relation_mapping_telemetry case={case_map.case_id}")
    if "open_question_mapping" not in telemetry:
        failures.append(f"missing_open_question_mapping_telemetry case={case_map.case_id}")


def _validate_markdown(artifact_dir: Path, manifest: CaseManifest, failures: list[str]) -> None:
    for name in ("report.md", "audit.md"):
        path = artifact_dir / name
        if not path.exists():
            failures.append(f"missing_markdown path={path}")
            continue
        text = path.read_text(encoding="utf-8")
        if name == "audit.md" and "Artifact Evidence Check" not in text:
            failures.append(f"missing_audit_evidence_check path={path}")
        if name == "report.md" and "Open Questions" not in text:
            failures.append(f"missing_report_open_questions path={path}")
        if manifest.metadata_files and "Preservation Metadata" not in text:
            failures.append(f"missing_preservation_metadata_section path={path}")
        if "Workflow Telemetry" not in text:
            failures.append(f"missing_workflow_telemetry_section path={path}")


def _validate_determinism(manifest: CaseManifest, repo_root: Path, failures: list[str]) -> None:
    first = build_starter_case_map(manifest, repo_root=repo_root)
    second = build_starter_case_map(manifest, repo_root=repo_root)
    first_ids = _identity_snapshot(first)
    second_ids = _identity_snapshot(second)
    if first_ids != second_ids:
        failures.append("unstable_ids category=determinism next=compare repeated build outputs")


def _identity_snapshot(case_map: CaseMap) -> dict[str, list[str]]:
    return {
        "sources": [source.source_id for source in case_map.sources],
        "claims": [claim.claim_id for claim in case_map.claims],
        "relations": [relation.relation_id for relation in case_map.relations],
        "open_questions": [question.question_id for question in case_map.open_questions],
    }


def _validate_snapshot_parity(artifact_dir: Path, examples_dir: Path, failures: list[str]) -> None:
    if not examples_dir.exists():
        failures.append(f"missing_examples_dir path={examples_dir} next=create curated snapshot")
        return
    for name in ("case_map.json", "report.md", "audit.md", "README.md"):
        path = examples_dir / name
        if not path.exists():
            failures.append(f"missing_example_file path={path}")
    for name in ("case_map.json", "report.md", "audit.md"):
        artifact_path = artifact_dir / name
        example_path = examples_dir / name
        if not artifact_path.exists() or not example_path.exists():
            continue
        if artifact_path.read_text(encoding="utf-8") != example_path.read_text(encoding="utf-8"):
            failures.append(f"snapshot_mismatch artifact={artifact_path} example={example_path}")


if __name__ == "__main__":
    raise SystemExit(main())
