from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Callable

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
    max_claims_per_chunk: int,
    claim_extractor: str,
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
    if max_claims_per_chunk < 1:
        print("semantic_staged_failed max_claims_per_chunk_must_be_positive", file=sys.stderr)
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
            max_claims_per_chunk=max_claims_per_chunk,
            claim_extractor=claim_extractor,
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
        f"claim_extractor={claim_extractor} "
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
    run_reader_memo_rewrite: bool = False,
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
            run_reader_memo_rewrite=run_reader_memo_rewrite,
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
    max_claims_per_chunk: int,
    claim_extractor: str,
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
    if max_claims_per_chunk < 1:
        print("semantic_staged_brief_failed max_claims_per_chunk_must_be_positive", file=sys.stderr)
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
            max_claims_per_chunk=max_claims_per_chunk,
            claim_extractor=claim_extractor,
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
        f"claim_extractor={claim_extractor} "
        f"claim_consolidation={claim_consolidation} "
        f"quality={result.quality_status} "
        f"confidence={briefing_result.model_confidence}->{briefing_result.calibrated_confidence}"
    )
    print(f"Briefing summary: {_display_path(repo_root, briefing_result.summary_path)}")
    return 0
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
