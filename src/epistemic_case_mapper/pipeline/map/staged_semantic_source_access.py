from __future__ import annotations

import re
from pathlib import Path

from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest, Source
from epistemic_case_mapper.submission_manifest import (
    SubmissionManifest,
    WorkedRegion,
    load_submission_manifest,
    resolve_required_source_ids,
)


def _load_context(
    repo_root: Path,
    manifest_path: str,
    region_id: str,
) -> tuple[SubmissionManifest, WorkedRegion, CaseManifest]:
    manifest = load_submission_manifest(repo_root, manifest_path)
    region = manifest.region_for_id(region_id)
    case = manifest.case_for_key(region.case_key)
    case_manifest = CaseManifest.model_validate(read_yaml(repo_root / case.case_path))
    return manifest, region, case_manifest


def _required_sources(case_manifest: CaseManifest, region: WorkedRegion) -> list[Source]:
    lookup = {source.source_id: source for source in case_manifest.sources}
    source_ids = resolve_required_source_ids(region, list(lookup))
    return [lookup[source_id] for source_id in source_ids]


def _source_text(repo_root: Path, source: Source) -> str:
    if source.text:
        return source.text
    if source.path:
        path = repo_root / source.path
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return source.excerpt or source.notes or ""


def _artifact_dir(repo_root: Path, region_id: str, artifact_dir: str | Path | None) -> Path:
    path = Path(artifact_dir or f"artifacts/semantic/{region_id}/staged")
    return path if path.is_absolute() else repo_root / path


def _relative(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()
