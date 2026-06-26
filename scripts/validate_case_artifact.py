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
        _validate_determinism(manifest, repo_root, failures)
    _validate_markdown(artifact_dir, failures)
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

    for claim in case_map.claims:
        if claim.source_id not in source_ids:
            failures.append(f"unknown_claim_source claim={claim.claim_id} source={claim.source_id}")
        if not claim.text:
            failures.append(f"missing_claim_text claim={claim.claim_id}")
        if not claim.source_span:
            failures.append(f"missing_claim_span claim={claim.claim_id}")
        if not claim.confidence:
            failures.append(f"missing_claim_confidence claim={claim.claim_id}")

    for relation in case_map.relations:
        if relation.source_claim_id not in claim_ids:
            failures.append(f"unknown_relation_source relation={relation.relation_id} claim={relation.source_claim_id}")
        if relation.target_claim_id not in claim_ids:
            failures.append(f"unknown_relation_target relation={relation.relation_id} claim={relation.target_claim_id}")
        if not relation.rationale:
            failures.append(f"missing_relation_rationale relation={relation.relation_id}")

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


def _validate_markdown(artifact_dir: Path, failures: list[str]) -> None:
    for name in ("report.md", "audit.md"):
        path = artifact_dir / name
        if not path.exists():
            failures.append(f"missing_markdown path={path}")
            continue
        text = path.read_text(encoding="utf-8")
        if name == "audit.md" and "FLF Criteria Score" not in text:
            failures.append(f"missing_audit_score_table path={path}")
        if name == "report.md" and "Open Questions" not in text:
            failures.append(f"missing_report_open_questions path={path}")


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
