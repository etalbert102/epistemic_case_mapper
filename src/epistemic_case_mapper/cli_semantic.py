from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

from epistemic_case_mapper.io import read_yaml, write_markdown
from epistemic_case_mapper.map_briefing import run_map_briefing
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.semantic_pipeline import (
    build_critique_prompt,
    build_map_prompt,
    validate_critique_candidate,
    validate_map_candidate,
)
from epistemic_case_mapper.staged_semantic_pipeline import run_staged_map
from epistemic_case_mapper.submission_manifest import SubmissionManifest, load_submission_manifest


def _display_path(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _run_semantic_map(
    repo_root: Path,
    package: str,
    region_id: str,
    backend: str | None,
    output: str | None,
    no_validate: bool,
) -> int:
    manifest = load_submission_manifest(repo_root, package)
    try:
        region = manifest.region_for_id(region_id)
    except KeyError:
        print(f"semantic_run_failed unknown_region={region_id}", file=sys.stderr)
        return 1
    prompt = build_map_prompt(repo_root, package, region_id)
    return _write_backend_result(
        repo_root=repo_root,
        region_id=region_id,
        prompt=prompt,
        backend=backend or manifest.default_model_backend,
        output=output,
        default_candidate_path=region.map_path,
        prompt_path=f"prompts/{region_id}/map_prompt.txt",
        validate=lambda path: _validate_semantic_map(repo_root, package, region_id, str(path)),
        no_validate=no_validate,
    )
def _run_semantic_critique(
    repo_root: Path,
    package: str,
    region_id: str,
    backend: str | None,
    map_path: str | None,
    output: str | None,
    no_validate: bool,
) -> int:
    manifest = load_submission_manifest(repo_root, package)
    try:
        manifest.region_for_id(region_id)
    except KeyError:
        print(f"semantic_run_failed unknown_region={region_id}", file=sys.stderr)
        return 1
    prompt = build_critique_prompt(repo_root, package, region_id, map_path)
    return _write_backend_result(
        repo_root=repo_root,
        region_id=region_id,
        prompt=prompt,
        backend=backend or manifest.default_model_backend,
        output=output,
        default_candidate_path=f"artifacts/semantic/{region_id}_critique.json",
        prompt_path=f"prompts/{region_id}/critique_prompt.txt",
        validate=lambda path: _validate_semantic_critique(str(path)),
        no_validate=no_validate,
    )
def _run_staged_semantic_map(
    repo_root: Path,
    package: str,
    region_id: str,
    backend: str | None,
    question: str | None,
    output: str | None,
    artifact_dir: str | None,
    chunk_lines: int,
    chunk_overlap_lines: int,
    max_chunks_per_source: int,
    max_total_chunks: int,
    max_claims_per_source: int,
    claim_consolidation: str,
    max_relation_pairs: int,
    relation_batch_size: int,
    backend_timeout: int,
    backend_retries: int,
    repair_quality: bool,
    no_validate: bool,
    reuse_claim_cache: bool = True,
) -> int:
    if chunk_lines < 1:
        print("semantic_staged_failed chunk_lines_must_be_positive", file=sys.stderr)
        return 1
    if chunk_overlap_lines < 0 or chunk_overlap_lines >= chunk_lines:
        print("semantic_staged_failed chunk_overlap_lines_must_be_nonnegative_and_smaller_than_chunk_lines", file=sys.stderr)
        return 1
    if max_chunks_per_source < 0:
        print("semantic_staged_failed max_chunks_per_source_must_be_nonnegative", file=sys.stderr)
        return 1
    if max_total_chunks < 0:
        print("semantic_staged_failed max_total_chunks_must_be_nonnegative", file=sys.stderr)
        return 1
    if max_claims_per_source < 1:
        print("semantic_staged_failed max_claims_per_source_must_be_positive", file=sys.stderr)
        return 1
    if max_relation_pairs < 1:
        print("semantic_staged_failed max_relation_pairs_must_be_positive", file=sys.stderr)
        return 1
    if relation_batch_size < 1:
        print("semantic_staged_failed relation_batch_size_must_be_positive", file=sys.stderr)
        return 1
    if backend_timeout < 1:
        print("semantic_staged_failed backend_timeout_must_be_positive", file=sys.stderr)
        return 1
    if backend_retries < 0:
        print("semantic_staged_failed backend_retries_must_be_nonnegative", file=sys.stderr)
        return 1
    manifest = load_submission_manifest(repo_root, package)
    try:
        result = run_staged_map(
            repo_root=repo_root,
            manifest_path=package,
            region_id=region_id,
            backend=backend or manifest.default_model_backend,
            decision_question=question,
            output_path=output,
            artifact_dir=artifact_dir,
            chunk_lines=chunk_lines,
            chunk_overlap_lines=chunk_overlap_lines,
            max_chunks_per_source=max_chunks_per_source or None,
            max_total_chunks=max_total_chunks or None,
            max_claims_per_source=max_claims_per_source,
            claim_consolidation=claim_consolidation,
            max_relation_pairs=max_relation_pairs,
            relation_batch_size=relation_batch_size,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            validate=not no_validate,
            repair_quality=repair_quality,
            reuse_claim_cache=reuse_claim_cache,
        )
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"semantic_staged_failed region={region_id} error={exc}", file=sys.stderr)
        return 1
    print(
        "Staged map wrote "
        f"{_display_path(repo_root, result.output_path)} "
        f"claims={result.claim_count} relations={result.relation_count} "
        "claim_extraction_method=whole_doc_source_card "
        f"claim_consolidation={claim_consolidation} "
        f"rejected_claims={result.rejected_claim_count} rejected_relations={result.rejected_relation_count} "
        f"quality={result.quality_status} "
        f"repair_ran={str(result.quality_repair_ran).lower()} repair_accepted={str(result.quality_repaired).lower()} "
        f"artifacts={_display_path(repo_root, result.artifact_dir)}"
    )
    print(f"Map quality report: {_display_path(repo_root, result.artifact_dir / 'map_quality_report.json')}")
    if result.failures:
        for failure in result.failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    if no_validate:
        print("Semantic validation skipped.")
    else:
        print(f"Validated staged semantic map region={region_id} path={result.output_path}")
    return 0
def _run_map_briefing(
    *,
    repo_root: Path,
    package: str,
    map_path: str,
    quality_report_path: str,
    question: str | None,
    backend: str | None,
    output_dir: str | None,
    region_id: str | None,
    baseline_path: str | None,
    max_claims: int,
    backend_timeout: int,
    backend_retries: int,
) -> int:
    if max_claims < 0:
        print("map_briefing_failed max_claims_must_be_nonnegative", file=sys.stderr)
        return 1
    if backend_timeout < 1:
        print("map_briefing_failed backend_timeout_must_be_positive", file=sys.stderr)
        return 1
    if backend_retries < 0:
        print("map_briefing_failed backend_retries_must_be_nonnegative", file=sys.stderr)
        return 1
    try:
        manifest = load_submission_manifest(repo_root, package) if (backend is None or region_id) else None
        if backend is None and manifest is None:
            print("map_briefing_failed backend_required_without_manifest", file=sys.stderr)
            return 1
        selected_backend = backend or manifest.default_model_backend
        selected_question = question
        if not selected_question and manifest and region_id:
            selected_question = _case_question_for_region(repo_root, manifest, manifest.region_for_id(region_id))
        result = run_map_briefing(
            repo_root=repo_root,
            map_path=map_path,
            quality_report_path=quality_report_path,
            question=selected_question or "",
            backend=selected_backend,
            output_dir=output_dir,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            source_titles=_source_titles_for_region(repo_root, manifest, region_id) if manifest and region_id else None,
            source_urls=_source_urls_for_region(repo_root, manifest, region_id) if manifest and region_id else None,
            source_citation_labels=_source_citation_labels_for_region(repo_root, manifest, region_id) if manifest and region_id else None,
            max_claims=max_claims,
            baseline_path=baseline_path,
        )
    except (RuntimeError, ValueError, FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
        print(f"map_briefing_failed error={exc}", file=sys.stderr)
        return 1
    print(
        "Map briefing wrote "
        f"{_display_path(repo_root, result.briefing_path)} "
        f"backend={result.backend} "
        f"quality={result.map_quality_status} "
        f"confidence={result.model_confidence}->{result.calibrated_confidence}"
    )
    print(f"Summary: {_display_path(repo_root, result.summary_path)}")
    print(f"Final review packet: {_display_path(repo_root, result.summary_path.parent / 'FINAL_REVIEW_PACKET.md')}")
    print(f"Gap telemetry: {_display_path(repo_root, result.gap_diagnosis_path)}")
    print(f"Prompt: {_display_path(repo_root, result.prompt_path)}")
    return 0
def _run_staged_semantic_brief(
    repo_root: Path,
    package: str,
    region_id: str,
    backend: str | None,
    question: str | None,
    output: str | None,
    artifact_dir: str | None,
    briefing_dir: str | None,
    chunk_lines: int,
    chunk_overlap_lines: int,
    max_chunks_per_source: int,
    max_total_chunks: int,
    max_claims_per_source: int,
    claim_consolidation: str,
    max_relation_pairs: int,
    relation_batch_size: int,
    briefing_max_claims: int,
    backend_timeout: int,
    backend_retries: int,
    repair_quality: bool,
    no_validate: bool,
    reuse_claim_cache: bool = True,
) -> int:
    if chunk_lines < 1:
        print("semantic_staged_brief_failed chunk_lines_must_be_positive", file=sys.stderr)
        return 1
    if chunk_overlap_lines < 0 or chunk_overlap_lines >= chunk_lines:
        print("semantic_staged_brief_failed chunk_overlap_lines_must_be_nonnegative_and_smaller_than_chunk_lines", file=sys.stderr)
        return 1
    if max_chunks_per_source < 0:
        print("semantic_staged_brief_failed max_chunks_per_source_must_be_nonnegative", file=sys.stderr)
        return 1
    if max_total_chunks < 0:
        print("semantic_staged_brief_failed max_total_chunks_must_be_nonnegative", file=sys.stderr)
        return 1
    if max_claims_per_source < 1:
        print("semantic_staged_brief_failed max_claims_per_source_must_be_positive", file=sys.stderr)
        return 1
    if max_relation_pairs < 1:
        print("semantic_staged_brief_failed max_relation_pairs_must_be_positive", file=sys.stderr)
        return 1
    if relation_batch_size < 1:
        print("semantic_staged_brief_failed relation_batch_size_must_be_positive", file=sys.stderr)
        return 1
    if briefing_max_claims < 0:
        print("semantic_staged_brief_failed briefing_max_claims_must_be_nonnegative", file=sys.stderr)
        return 1
    if backend_timeout < 1:
        print("semantic_staged_brief_failed backend_timeout_must_be_positive", file=sys.stderr)
        return 1
    if backend_retries < 0:
        print("semantic_staged_brief_failed backend_retries_must_be_nonnegative", file=sys.stderr)
        return 1
    manifest = load_submission_manifest(repo_root, package)
    try:
        region = manifest.region_for_id(region_id)
        selected_backend = backend or manifest.default_model_backend
        selected_question = question or _case_question_for_region(repo_root, manifest, region)
        map_output = output or Path("artifacts") / "semantic" / region_id / "staged_brief" / "generated_map.json"
        map_artifacts = artifact_dir or Path("artifacts") / "semantic" / region_id / "staged_brief" / "map"
        result = run_staged_map(
            repo_root=repo_root,
            manifest_path=package,
            region_id=region_id,
            backend=selected_backend,
            decision_question=selected_question,
            output_path=map_output,
            artifact_dir=map_artifacts,
            chunk_lines=chunk_lines,
            chunk_overlap_lines=chunk_overlap_lines,
            max_chunks_per_source=max_chunks_per_source or None,
            max_total_chunks=max_total_chunks or None,
            max_claims_per_source=max_claims_per_source,
            claim_consolidation=claim_consolidation,
            max_relation_pairs=max_relation_pairs,
            relation_batch_size=relation_batch_size,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            validate=not no_validate,
            repair_quality=repair_quality,
            reuse_claim_cache=reuse_claim_cache,
        )
        if result.failures:
            for failure in result.failures:
                print(f"FAIL: {failure}", file=sys.stderr)
            return 1
        briefing_result = run_map_briefing(
            repo_root=repo_root,
            map_path=result.output_path,
            quality_report_path=result.artifact_dir / "map_quality_report.json",
            question=selected_question,
            backend=selected_backend,
            output_dir=briefing_dir or Path("artifacts") / "semantic" / region_id / "staged_brief" / "briefing",
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            source_titles=_source_titles_for_region(repo_root, manifest, region_id),
            source_urls=_source_urls_for_region(repo_root, manifest, region_id),
            source_citation_labels=_source_citation_labels_for_region(repo_root, manifest, region_id),
            max_claims=briefing_max_claims,
        )
    except (RuntimeError, ValueError, FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
        print(f"semantic_staged_brief_failed region={region_id} error={exc}", file=sys.stderr)
        return 1
    print(
        "Staged brief wrote "
        f"{_display_path(repo_root, briefing_result.briefing_path)} "
        f"map={_display_path(repo_root, result.output_path)} "
        f"claims={result.claim_count} relations={result.relation_count} "
        "claim_extraction_method=whole_doc_source_card "
        f"claim_consolidation={claim_consolidation} "
        f"quality={result.quality_status} "
        f"confidence={briefing_result.model_confidence}->{briefing_result.calibrated_confidence}"
    )
    print(f"Briefing summary: {_display_path(repo_root, briefing_result.summary_path)}")
    print(f"Final review packet: {_display_path(repo_root, briefing_result.summary_path.parent / 'FINAL_REVIEW_PACKET.md')}")
    print(f"Map run summary: {_display_path(repo_root, result.artifact_dir / 'run_summary.json')}")
    return 0


def _run_staged_semantic_resume(
    *,
    repo_root: Path,
    package: str,
    region_id: str,
    from_stage: str,
    backend: str | None,
    question: str | None,
    run_dir: str | None,
    map_path: str | None,
    quality_report_path: str | None,
    briefing_dir: str | None,
    briefing_max_claims: int,
    backend_timeout: int,
    backend_retries: int,
) -> int:
    if briefing_max_claims < 0:
        print("semantic_staged_resume_failed briefing_max_claims_must_be_nonnegative", file=sys.stderr)
        return 1
    if backend_timeout < 1:
        print("semantic_staged_resume_failed backend_timeout_must_be_positive", file=sys.stderr)
        return 1
    if backend_retries < 0:
        print("semantic_staged_resume_failed backend_retries_must_be_nonnegative", file=sys.stderr)
        return 1
    paths = _staged_resume_paths(
        repo_root=repo_root,
        region_id=region_id,
        run_dir=run_dir,
        map_path=map_path,
        quality_report_path=quality_report_path,
        briefing_dir=briefing_dir,
    )
    if from_stage == "documents":
        print("Resuming from documents: running map construction and memo synthesis.")
        return _run_staged_semantic_brief(
            repo_root=repo_root,
            package=package,
            region_id=region_id,
            backend=backend,
            question=question,
            output=str(paths["map_path"]),
            artifact_dir=str(paths["map_artifact_dir"]),
            briefing_dir=str(paths["briefing_dir"]),
            chunk_lines=40,
            chunk_overlap_lines=0,
            max_chunks_per_source=0,
            max_total_chunks=0,
            max_claims_per_source=8,
            claim_consolidation="deterministic",
            max_relation_pairs=12,
            relation_batch_size=4,
            briefing_max_claims=briefing_max_claims,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            repair_quality=True,
            no_validate=False,
            reuse_claim_cache=True,
        )
    if from_stage == "map":
        missing = _missing_paths([paths["map_path"], paths["quality_report_path"]])
        if missing:
            print("semantic_staged_resume_failed missing_map_artifacts:", file=sys.stderr)
            for item in _display_missing_paths(repo_root, missing):
                print(f"  - {item}", file=sys.stderr)
            print(f"Run: ecm semantic staged status --region {region_id}", file=sys.stderr)
            return 1
        print("Resuming from map artifacts: running memo synthesis only.")
        return _run_map_briefing(
            repo_root=repo_root,
            package=package,
            map_path=str(paths["map_path"]),
            quality_report_path=str(paths["quality_report_path"]),
            question=question,
            backend=backend,
            output_dir=str(paths["briefing_dir"]),
            region_id=region_id,
            baseline_path=None,
            max_claims=briefing_max_claims,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
        )
    if from_stage == "briefing":
        return _report_existing_briefing(repo_root=repo_root, package=package, region_id=region_id, paths=paths)
    print(f"semantic_staged_resume_failed unknown_from_stage={from_stage}", file=sys.stderr)
    return 2


def _run_staged_semantic_status(
    *,
    repo_root: Path,
    package: str,
    region_id: str,
    run_dir: str | None,
    map_path: str | None,
    quality_report_path: str | None,
    briefing_dir: str | None,
    verbose: bool,
) -> int:
    paths = _staged_resume_paths(
        repo_root=repo_root,
        region_id=region_id,
        run_dir=run_dir,
        map_path=map_path,
        quality_report_path=quality_report_path,
        briefing_dir=briefing_dir,
    )
    try:
        manifest = load_submission_manifest(repo_root, package)
        region = manifest.region_for_id(region_id)
        case_manifest = _case_manifest_for_region(repo_root, manifest, region)
    except (KeyError, FileNotFoundError, ValueError) as exc:
        print(f"semantic_staged_status_failed region={region_id} error={exc}", file=sys.stderr)
        return 1
    source_paths = _case_source_paths(repo_root, case_manifest)
    documents_ready = bool(case_manifest.sources) and all(path.exists() for path in source_paths)
    rows = [
        _stage_status_row(repo_root, "documents", documents_ready, [repo_root / manifest.case_for_key(region.case_key).case_path, *source_paths]),
        _stage_status_row(repo_root, "map", paths["map_path"].exists() and paths["quality_report_path"].exists(), [paths["map_path"], paths["quality_report_path"], paths["run_summary_path"], paths["pipeline_progress_path"]]),
        _stage_status_row(repo_root, "briefing", paths["briefing_path"].exists() and paths["briefing_summary_path"].exists() and paths["final_review_packet_path"].exists(), [paths["briefing_path"], paths["briefing_summary_path"], paths["final_review_packet_path"], paths["memo_progress_path"]]),
    ]
    print("Staged Pipeline")
    print(f"Region: {region_id}")
    print(f"Run dir: {_display_path(repo_root, paths['run_dir'])}")
    print("Flow: documents -> map -> briefing")
    print("")
    print("Stage       State       Summary")
    for row in rows:
        print(_stage_summary_line(row))
    if verbose:
        print("")
        print("Checked Artifacts")
        for row in rows:
            print(f"{row['stage']}:")
            for artifact in row["artifacts"]:
                marker = "ok" if artifact["exists"] else "missing"
                print(f"  [{marker}] {artifact['path']}")
    else:
        print("")
        print("Use --verbose to list every checked artifact path.")
    print("")
    _print_staged_next_actions(
        repo_root=repo_root,
        region_id=region_id,
        backend=manifest.default_model_backend,
        rows=rows,
        paths=paths,
    )
    return 0


def _report_existing_briefing(*, repo_root: Path, package: str, region_id: str, paths: dict[str, Path]) -> int:
    try:
        manifest = load_submission_manifest(repo_root, package)
        manifest.region_for_id(region_id)
    except (KeyError, FileNotFoundError, ValueError) as exc:
        print(f"semantic_staged_resume_failed region={region_id} error={exc}", file=sys.stderr)
        return 1
    missing = _missing_paths([paths["briefing_path"], paths["briefing_summary_path"], paths["final_review_packet_path"]])
    if missing:
        print("semantic_staged_resume_failed missing_briefing_artifacts:", file=sys.stderr)
        for item in _display_missing_paths(repo_root, missing):
            print(f"  - {item}", file=sys.stderr)
        print(f"Run: ecm semantic staged status --region {region_id}", file=sys.stderr)
        return 1
    print("Existing briefing artifacts are ready.")
    print(f"Briefing memo: {_display_path(repo_root, paths['briefing_path'])}")
    print(f"Briefing summary: {_display_path(repo_root, paths['briefing_summary_path'])}")
    print(f"Final review packet: {_display_path(repo_root, paths['final_review_packet_path'])}")
    if paths["memo_progress_path"].exists():
        print(f"Memo progress: {_display_path(repo_root, paths['memo_progress_path'])}")
    return 0


def _staged_resume_paths(
    *,
    repo_root: Path,
    region_id: str,
    run_dir: str | None,
    map_path: str | None,
    quality_report_path: str | None,
    briefing_dir: str | None,
) -> dict[str, Path]:
    root = _resolve_repo_path(repo_root, run_dir or Path("artifacts") / "semantic" / region_id / "staged_brief")
    map_file = _resolve_repo_path(repo_root, map_path) if map_path else root / "generated_map.json"
    map_artifacts = root / "map"
    quality_file = _resolve_repo_path(repo_root, quality_report_path) if quality_report_path else map_artifacts / "map_quality_report.json"
    briefing = _resolve_repo_path(repo_root, briefing_dir) if briefing_dir else root / "briefing"
    return {
        "run_dir": root,
        "map_path": map_file,
        "map_artifact_dir": map_artifacts,
        "quality_report_path": quality_file,
        "run_summary_path": map_artifacts / "run_summary.json",
        "pipeline_progress_path": map_artifacts / "pipeline_progress.json",
        "briefing_dir": briefing,
        "briefing_path": briefing / "BRIEFING.md",
        "briefing_summary_path": briefing / "briefing_summary.json",
        "final_review_packet_path": briefing / "FINAL_REVIEW_PACKET.md",
        "memo_progress_path": briefing / "memo_progress.json",
    }


def _resolve_repo_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def _missing_paths(paths: list[Path]) -> list[str]:
    return [str(path) for path in paths if not path.exists()]


def _display_missing_paths(repo_root: Path, paths: list[str]) -> list[str]:
    return [_display_path(repo_root, Path(path)) for path in paths]


def _case_source_paths(repo_root: Path, case_manifest: CaseManifest) -> list[Path]:
    return [repo_root / source.path for source in case_manifest.sources if source.path]


def _stage_status_row(repo_root: Path, stage: str, ready: bool, artifacts: list[Path]) -> dict[str, Any]:
    missing = [path for path in artifacts if not path.exists()]
    return {
        "stage": stage,
        "status": "ready" if ready else "incomplete",
        "missing_count": len(missing),
        "artifact_count": len(artifacts),
        "artifacts": [{"path": _display_path(repo_root, path), "exists": path.exists()} for path in artifacts],
    }


def _stage_summary_line(row: dict[str, Any]) -> str:
    stage = str(row["stage"])
    status = str(row["status"])
    artifacts = row.get("artifacts", []) if isinstance(row.get("artifacts"), list) else []
    if status == "ready":
        summary = _ready_stage_summary(stage, artifacts)
    else:
        missing = [item["path"] for item in artifacts if isinstance(item, dict) and not item.get("exists")]
        summary = _missing_stage_summary(stage, missing)
    return f"{stage:<11} {status:<11} {summary}"


def _ready_stage_summary(stage: str, artifacts: list[dict[str, Any]]) -> str:
    if stage == "documents":
        source_count = max(0, len(artifacts) - 1)
        return f"case manifest and {source_count} source file(s) available"
    if stage == "map":
        return "generated map and quality report available"
    if stage == "briefing":
        return "memo, summary, and final review packet available"
    return "ready"


def _missing_stage_summary(stage: str, missing: list[str]) -> str:
    if not missing:
        return "not ready"
    if stage == "documents":
        return f"{len(missing)} required document artifact(s) missing"
    if stage in {"map", "briefing"}:
        labels = [_artifact_basename(path) for path in missing[:2]]
        suffix = "" if len(missing) <= 2 else f" and {len(missing) - 2} more"
        return "missing " + ", ".join(labels) + suffix
    return f"{len(missing)} artifact(s) missing"


def _artifact_basename(path: str) -> str:
    return Path(path).name or path


def _print_staged_next_actions(
    *,
    repo_root: Path,
    region_id: str,
    backend: str,
    rows: list[dict[str, Any]],
    paths: dict[str, Path],
) -> None:
    status_by_stage = {str(row["stage"]): str(row["status"]) for row in rows}
    print("Next Actions")
    if status_by_stage.get("briefing") == "ready":
        print(f"  Read memo: {_display_path(repo_root, paths['briefing_path'])}")
        print(f"  Review packet: {_display_path(repo_root, paths['final_review_packet_path'])}")
        print(f"  Rebuild memo: ecm semantic staged resume --region {region_id} --from-stage map --backend {backend}")
        return
    if status_by_stage.get("map") == "ready":
        print(f"  Build memo: ecm semantic staged resume --region {region_id} --from-stage map --backend {backend}")
        print(f"  Existing map: {_display_path(repo_root, paths['map_path'])}")
        return
    if status_by_stage.get("documents") == "ready":
        print(f"  Build map and memo: ecm semantic staged resume --region {region_id} --from-stage documents --backend {backend}")
        print(f"  Or run directly: ecm semantic staged brief --region {region_id} --backend {backend}")
        return
    print(f"  Fix missing case/source files, then run: ecm semantic staged status --region {region_id} --verbose")


def _write_backend_result(
    repo_root: Path,
    region_id: str,
    prompt: str,
    backend: str,
    output: str | None,
    default_candidate_path: str,
    prompt_path: str,
    validate,
    no_validate: bool,
) -> int:
    try:
        result = run_model_backend(prompt, backend)
    except (RuntimeError, ValueError) as exc:
        print(f"semantic_run_failed region={region_id} backend={backend} error={exc}", file=sys.stderr)
        return 1
    relative_output = output or (prompt_path if result.prompt_only else default_candidate_path)
    output_path = Path(relative_output)
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_text = result.text if result.prompt_only else canonical_json_output(result.text)
    output_path.write_text(output_text, encoding="utf-8")
    print(f"Wrote {_display_path(repo_root, output_path)} backend={result.backend}")
    if result.prompt_only:
        print("Prompt backend selected; no JSON validation run.")
        return 0
    if no_validate:
        print("Semantic validation skipped.")
        return 0
    return validate(output_path)
def _source_titles_for_region(repo_root: Path, manifest: SubmissionManifest, region_id: str) -> dict[str, str]:
    region = manifest.region_for_id(region_id)
    case_manifest = _case_manifest_for_region(repo_root, manifest, region)
    return {source.source_id: source.title for source in case_manifest.sources}

def _source_urls_for_region(repo_root: Path, manifest: SubmissionManifest, region_id: str) -> dict[str, str]:
    region = manifest.region_for_id(region_id)
    case_manifest = _case_manifest_for_region(repo_root, manifest, region)
    return {source.source_id: source.url for source in case_manifest.sources if source.url}

def _source_citation_labels_for_region(repo_root: Path, manifest: SubmissionManifest, region_id: str) -> dict[str, str]:
    region = manifest.region_for_id(region_id)
    case_manifest = _case_manifest_for_region(repo_root, manifest, region)
    return {
        source.source_id: _source_citation_label(source.author, source.publication_date, source.title)
        for source in case_manifest.sources
    }

def _source_citation_label(author: str | None, publication_date: str | None, title: str) -> str:
    year_match = re.search(r"\b(?:19|20)\d{2}\b", str(publication_date or ""))
    year = year_match.group(0) if year_match else ""
    author_text = str(author or "").strip()
    if author_text:
        author_text = re.split(r";|,", author_text, maxsplit=1)[0].strip()
        if year:
            return f"{author_text} {year}".strip()
        return author_text
    return f"{title} {year}".strip() if year else title

def _case_question_for_region(repo_root: Path, manifest: SubmissionManifest, region) -> str:
    return _case_manifest_for_region(repo_root, manifest, region).question
def _case_manifest_for_region(repo_root: Path, manifest: SubmissionManifest, region) -> CaseManifest:
    case = manifest.case_for_key(region.case_key)
    return CaseManifest.model_validate(read_yaml(repo_root / case.case_path))
def _validate_semantic_map(repo_root: Path, package: str, region_id: str, path: str) -> int:
    failures = validate_map_candidate(repo_root, package, region_id, Path(path))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"Validated semantic map candidate region={region_id} path={path}")
    return 0
def _validate_semantic_critique(path: str) -> int:
    failures = validate_critique_candidate(Path(path))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"Validated semantic critique candidate path={path}")
    return 0
