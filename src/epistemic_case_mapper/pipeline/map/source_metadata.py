from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Iterable

from epistemic_case_mapper.schema import CaseManifest, Source


_MAX_METADATA_FILE_CHARS = 40_000


def build_source_metadata_bundle(
    *,
    repo_root: Path | None,
    case_manifest: CaseManifest,
    sources: Iterable[Source],
) -> dict[str, Any]:
    """Preserve manifest provenance and decision-relevant case metadata in a map.

    The staged map used to retain only source IDs.  That made the briefing stage
    guess source design and independence from titles.  This bundle is deliberately
    JSON-native so it survives the map artifact boundary without requiring access
    to the original manifest.
    """

    selected_sources = list(sources)
    source_ids = {source.source_id for source in selected_sources}
    if repo_root is None:
        metadata_files = [
            {"path": str(path), "status": "not_loaded_without_repo_root"}
            for path in case_manifest.metadata_files
        ]
        file_issues = ["metadata_files_not_loaded_without_repo_root"] if metadata_files else []
    else:
        metadata_files, file_issues = _read_metadata_files(
            repo_root=repo_root,
            relative_paths=case_manifest.metadata_files,
            source_ids=source_ids,
        )
    independence_clusters = _independence_clusters(metadata_files, source_ids)
    caveats_by_source: dict[str, list[str]] = {source_id: [] for source_id in source_ids}
    clusters_by_source: dict[str, list[str]] = {source_id: [] for source_id in source_ids}
    for cluster in independence_clusters:
        caveat = str(cluster.get("caveat") or "").strip()
        cluster_name = str(cluster.get("cluster") or "").strip()
        for source_id in cluster.get("source_ids", []):
            if source_id not in source_ids:
                continue
            if caveat and caveat not in caveats_by_source[source_id]:
                caveats_by_source[source_id].append(caveat)
            if cluster_name and cluster_name not in clusters_by_source[source_id]:
                clusters_by_source[source_id].append(cluster_name)

    records: list[dict[str, Any]] = []
    for source in selected_sources:
        # Preserve provenance and source identity, not a second copy of the raw
        # document. The claim/excerpt artifacts remain the bounded evidence path.
        record = source.model_dump(mode="json", exclude_none=True, exclude={"text"})
        record["independence_caveats"] = caveats_by_source.get(source.source_id, [])
        record["independence_clusters"] = clusters_by_source.get(source.source_id, [])
        records.append(record)

    return {
        "schema_id": "source_metadata_bundle_v1",
        "case_id": case_manifest.case_id,
        "evidence_mode": case_manifest.evidence_mode,
        "review_status": case_manifest.review_status,
        "sources": records,
        "source_by_id": {str(record["source_id"]): record for record in records},
        "metadata_files": metadata_files,
        "independence_clusters": independence_clusters,
        "issues": file_issues,
    }


def _read_metadata_files(
    *,
    repo_root: Path,
    relative_paths: Iterable[str],
    source_ids: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    resolved_root = repo_root.resolve()
    records: list[dict[str, Any]] = []
    issues: list[str] = []
    for raw_path in relative_paths:
        relative_path = str(raw_path).strip()
        if not relative_path:
            continue
        path = (resolved_root / relative_path).resolve()
        try:
            path.relative_to(resolved_root)
        except ValueError:
            issues.append(f"metadata_path_outside_repo:{relative_path}")
            continue
        if not path.is_file():
            issues.append(f"metadata_file_missing:{relative_path}")
            records.append({"path": relative_path, "status": "missing"})
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        retained = text[:_MAX_METADATA_FILE_CHARS]
        records.append(
            {
                "path": relative_path,
                "status": "retained" if len(text) <= _MAX_METADATA_FILE_CHARS else "retained_truncated",
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "content": retained,
                "source_ids_mentioned": sorted(source_id for source_id in source_ids if source_id in text),
            }
        )
        if len(text) > _MAX_METADATA_FILE_CHARS:
            issues.append(f"metadata_file_truncated:{relative_path}")
    return records, issues


def _independence_clusters(
    metadata_files: list[dict[str, Any]],
    known_source_ids: set[str],
) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    for record in metadata_files:
        path = str(record.get("path") or "")
        text = str(record.get("content") or "")
        if "independen" not in f"{path} {text}".lower():
            continue
        heading = "Unspecified independence cluster"
        current_ids: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("### "):
                heading = line[4:].strip()
                current_ids = []
                continue
            if line.startswith("## "):
                current_ids = []
                continue
            for candidate in re.findall(r"`([^`]+)`", line):
                if candidate in known_source_ids and candidate not in current_ids:
                    current_ids.append(candidate)
            if line.lower().startswith(("risk:", "caveat:", "independence:")) and current_ids:
                clusters.append(
                    {
                        "cluster": heading,
                        "source_ids": list(current_ids),
                        "caveat": line,
                        "metadata_path": path,
                    }
                )
    return clusters
