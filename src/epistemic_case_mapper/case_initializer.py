from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from epistemic_case_mapper.io import write_json, write_markdown, write_yaml


STARTER_PROMPT_PROCEDURE = "case_initializer_starter_v1"


@dataclass(frozen=True)
class InitializedCase:
    case_id: str
    region_id: str
    written_paths: tuple[Path, ...]


def init_case_package(
    repo_root: Path,
    package_path: str,
    case_id: str,
    title: str,
    question: str,
    doc_paths: list[Path],
    region_id: str | None = None,
    model_backend: str = "prompt",
    epistemic_config: dict | None = None,
    force: bool = False,
) -> InitializedCase:
    slug = _slugify(case_id)
    if not slug:
        raise ValueError("case_id must contain at least one letter or number")
    region_slug = _slugify(region_id or f"{slug}_initial_region")
    if not region_slug:
        raise ValueError("region_id must contain at least one letter or number")
    if not doc_paths:
        raise ValueError("at least one document path is required")

    package_file = repo_root / package_path
    managed_paths = [
        package_file,
        repo_root / f"data/cases/{slug}/case.yaml",
        repo_root / f"docs/worked_regions/{region_slug}.md",
        repo_root / "docs/START.md",
        repo_root / f"examples/{slug}/worked_map.json",
        repo_root / f"examples/{slug}/decision_space_erosion_audit.json",
        repo_root / f"examples/{slug}/flat_synthesis_baseline.md",
        repo_root / f"examples/{slug}/full_case_index.md",
        repo_root / f"examples/{slug}/full_case_map.md",
        repo_root / f"examples/{slug}/task_queue.md",
    ]
    existing = [path for path in managed_paths if path.exists()]
    if existing and not force:
        joined = ", ".join(path.relative_to(repo_root).as_posix() for path in existing)
        raise ValueError(f"refusing to overwrite existing files without --force: {joined}")

    source_records = _copy_sources(repo_root, slug, doc_paths, force=force)
    manifest = _manifest(slug, title, question, region_slug, source_records, model_backend)
    case_manifest = _case_manifest(slug, title, question, source_records, epistemic_config)
    worked_map = _starter_map(repo_root, slug, title, source_records)
    audit = _starter_audit(slug)

    written: list[Path] = []
    write_yaml(package_file, manifest)
    written.append(package_file)
    case_path = repo_root / f"data/cases/{slug}/case.yaml"
    write_yaml(case_path, case_manifest)
    written.append(case_path)
    for record in source_records:
        written.append(repo_root / record["path"])

    region_path = repo_root / f"docs/worked_regions/{region_slug}.md"
    write_markdown(region_path, _region_definition(title, question, source_records))
    written.append(region_path)

    start_path = repo_root / "docs/START.md"
    write_markdown(start_path, _start_doc(slug, title, question, region_slug, package_path, model_backend))
    written.append(start_path)

    map_path = repo_root / f"examples/{slug}/worked_map.json"
    write_json(map_path, worked_map)
    written.append(map_path)
    audit_path = repo_root / f"examples/{slug}/decision_space_erosion_audit.json"
    write_json(audit_path, audit)
    written.append(audit_path)
    baseline_path = repo_root / f"examples/{slug}/flat_synthesis_baseline.md"
    write_markdown(baseline_path, _baseline(title, question, source_records))
    written.append(baseline_path)
    full_index_path = repo_root / f"examples/{slug}/full_case_index.md"
    write_markdown(full_index_path, _full_case_index(title, question, source_records))
    written.append(full_index_path)
    full_map_path = repo_root / f"examples/{slug}/full_case_map.md"
    write_markdown(full_map_path, _full_case_map(slug, title, source_records))
    written.append(full_map_path)
    task_path = repo_root / f"examples/{slug}/task_queue.md"
    write_markdown(task_path, _task_queue(slug, source_records))
    written.append(task_path)

    return InitializedCase(case_id=slug, region_id=region_slug, written_paths=tuple(written))


def _copy_sources(repo_root: Path, case_id: str, doc_paths: list[Path], force: bool) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    used_ids: set[str] = set()
    for index, input_path in enumerate(doc_paths, start=1):
        source_path = input_path.expanduser().resolve()
        if not source_path.exists() or not source_path.is_file():
            raise ValueError(f"document does not exist or is not a file: {input_path}")
        if not _first_nonempty_line(source_path):
            raise ValueError(f"document has no readable non-empty text: {input_path}")
        source_id = _unique_source_id(case_id, source_path, used_ids, index)
        target_name = f"{source_id}{source_path.suffix or '.txt'}"
        relative = Path("data") / "cases" / case_id / "sources" / "text" / target_name
        target_path = repo_root / relative
        if target_path.exists() and not force:
            raise ValueError(f"refusing to overwrite existing source without --force: {relative.as_posix()}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target_path)
        records.append(
            {
                "source_id": source_id,
                "title": _title_from_path(source_path),
                "path": relative.as_posix(),
            }
        )
    return records


def _manifest(
    case_id: str,
    title: str,
    question: str,
    region_id: str,
    sources: list[dict[str, str]],
    model_backend: str,
) -> dict:
    source_ids = [source["source_id"] for source in sources]
    return {
        "schema_version": 1,
        "package_id": f"{case_id}_package",
        "package_label": title,
        "default_model_backend": model_backend,
        "id_patterns": {
            "claim": rf"{re.escape(case_id)}_c[0-9]+",
            "relation": rf"{re.escape(case_id)}_r[0-9]+",
            "loss": rf"{re.escape(case_id)}_loss_[0-9]+",
        },
        "ui_hero": {
            "eyebrow": "Case Review",
            "title": title,
            "body": question,
            "links": [
                {"label": "Start", "path": "docs/START.md", "primary": True},
                {"label": "Worked region", "path": f"docs/worked_regions/{region_id}.md"},
            ],
            "cards": [
                {"label": "Source packet", "text": f"{len(sources)} imported documents"},
                {"label": "Default backend", "text": model_backend},
            ],
        },
        "judge_paths": ["docs/START.md", f"docs/worked_regions/{region_id}.md"],
        "required_docs": ["docs/START.md"],
        "reference_scan_paths": ["docs/START.md", f"docs/worked_regions/{region_id}.md"],
        "cases": [
            {
                "case_key": case_id,
                "case_id": case_id,
                "label": title,
                "case_path": f"data/cases/{case_id}/case.yaml",
                "full_case": {
                    "index_path": f"examples/{case_id}/full_case_index.md",
                    "map_path": f"examples/{case_id}/full_case_map.md",
                    "worked_anchor": f"examples/{case_id}/worked_map.json",
                    "min_clusters": 1,
                    "min_relations": 0,
                },
                "task_queue": {
                    "path": f"examples/{case_id}/task_queue.md",
                    "prefix": f"{case_id}_task_",
                    "min_tasks": 1,
                },
                "ui": {"include": True, "label": title},
                "worked_regions": [
                    {
                        "case_key": case_id,
                        "case_label": title,
                        "region_id": region_id,
                        "id_prefix": case_id,
                        "definition_path": f"docs/worked_regions/{region_id}.md",
                        "map_path": f"examples/{case_id}/worked_map.json",
                        "map_format": "json_case_map_v1",
                        "audit_path": f"examples/{case_id}/decision_space_erosion_audit.json",
                        "audit_format": "json_case_map_v1",
                        "baseline_path": f"examples/{case_id}/flat_synthesis_baseline.md",
                        "output_json_path": f"examples/{case_id}/worked_map_export.json",
                        "required_sources": source_ids,
                        "thresholds": {
                            "min_claims": 1,
                            "max_claims": 40,
                            "min_relation_types": 0,
                            "min_crux_mentions": 0,
                            "min_evidence_rows": 1,
                            "min_losses": 0,
                            "min_surviving_checks": 0,
                            "min_baseline_words": 20,
                            "require_best_sections": False,
                        },
                    }
                ],
            }
        ],
    }


def _case_manifest(
    case_id: str,
    title: str,
    question: str,
    sources: list[dict[str, str]],
    epistemic_config: dict | None = None,
) -> dict:
    return {
        "case_id": case_id,
        "title": title,
        "question": question,
        "case_type": "user supplied document packet",
        "evidence_mode": "source_grounded",
        "review_status": "human-review-needed",
        "status": "in_progress",
        "sources": [
            {
                "source_id": source["source_id"],
                "title": source["title"],
                "source_type": "document",
                "path": source["path"],
                "provenance_level": "unspecified",
                "evidence_role": "provided_document",
                "limitations": [
                    "Imported by the case initializer; provenance and completeness have not been independently audited."
                ],
                "needs_upgrade": True,
            }
            for source in sources
        ],
        "epistemic_config": epistemic_config or {},
    }


def _starter_map(repo_root: Path, case_id: str, title: str, sources: list[dict[str, str]]) -> dict:
    claims = []
    evidence_rows = []
    for index, source in enumerate(sources, start=1):
        excerpt = _first_nonempty_line(repo_root / source["path"])
        claims.append(
            {
                "claim_id": f"{case_id}_c{index:03d}",
                "claim": f"The imported document `{source['source_id']}` contains the quoted excerpt and needs substantive interpretation.",
                "source_id": source["source_id"],
                "source_span": "first non-empty line",
                "excerpt": excerpt,
                "entailed_by_excerpt": "yes",
                "role": "source_inventory",
            }
        )
        evidence_rows.append(
            [
                f"Imported source {source['source_id']}",
                "Needs review",
                "Starter map records source availability; it does not resolve the case question.",
            ]
        )
    return {
        "title": f"{title} Starter Map",
        "status": "human-review-needed",
        "prompt_procedure": STARTER_PROMPT_PROCEDURE,
        "evidence_mode": "source_grounded",
        "sources": [source["source_id"] for source in sources],
        "claims": claims,
        "relations": [],
        "crux_candidates": [],
        "similar_but_not_identical": [],
        "evidence_check": evidence_rows,
    }


def _starter_audit(case_id: str) -> dict:
    return {
        "title": f"{case_id} Starter Erosion Audit",
        "status": "human-review-needed",
        "prompt_procedure": STARTER_PROMPT_PROCEDURE,
        "baseline_comparator": f"examples/{case_id}/flat_synthesis_baseline.md",
        "map_comparator": f"examples/{case_id}/worked_map.json",
        "losses": [],
        "borderline_or_rejected": [
            "No flat-synthesis losses have been claimed yet; run a model or human review before treating this as analysis."
        ],
    }


def _region_definition(title: str, question: str, sources: list[dict[str, str]]) -> str:
    source_lines = "\n".join(f"- `{source['source_id']}`: {source['title']}" for source in sources)
    return f"""# {title} Initial Worked Region

Status: `human-review-needed`

Question: {question}

## Source Subset

{source_lines}

## Scope

This starter region asks the mapper to identify source-grounded claims, relation edges, crux candidates, and evidence checks from the imported document packet.
"""


def _start_doc(case_id: str, title: str, question: str, region_id: str, package_path: str, model_backend: str) -> str:
    return f"""# {title}

Status: `human-review-needed`

Question: {question}

This package was initialized from a document packet. The included starter map is only a source inventory; replace it with a source-grounded model or human map before using the package as analysis.

## Run

- Inspect the package: `ecm --repo-root . --package {package_path} package prepare`
- Render a map prompt with the configured backend: `ecm --repo-root . --package {package_path} semantic run map --region {region_id}`
- Generate with a local command backend: `ecm --repo-root . --package {package_path} semantic run map --region {region_id} --backend command:'your-model-command'`

Configured default model backend: `{model_backend}`
Case key: `{case_id}`
Region: `{region_id}`
"""


def _baseline(title: str, question: str, sources: list[dict[str, str]]) -> str:
    source_ids = ", ".join(source["source_id"] for source in sources)
    return f"""# {title} Flat Baseline
Prompt version: `flat_baseline_prompt_v1`
Isolation: `baseline_writer_had_access_to_curated_map=false`

This starter baseline records the imported source packet for the question: {question}

It cites the available sources ({source_ids}) but does not yet make a substantive synthesized answer. Use it as a placeholder comparator until a real flat synthesis is generated or written.
"""


def _full_case_index(title: str, question: str, sources: list[dict[str, str]]) -> str:
    source_lines = "\n".join(f"- {source['source_id']}" for source in sources)
    return f"""# {title} Full Case Index

Status: `broad-scaffold`

Question: {question}

## Imported Sources

{source_lines}

Remaining Expansion Work

- Replace the starter map with a substantive source-grounded map.
- Add missing perspectives, source provenance checks, and adversarial review.
"""


def _full_case_map(case_id: str, title: str, sources: list[dict[str, str]]) -> str:
    source_refs = "`, `".join(source["source_id"] for source in sources)
    return f"""# {title} Full Case Map

Status: `broad-scaffold`

cluster_id: {case_id}_cluster_001
topic: Imported source packet
cluster_claim: The package has imported sources ready for source-grounded mapping.
map_status: broad scaffold
sources: `{source_refs}`

Remaining Expansion Work

- Add claim clusters after semantic mapping.
"""


def _task_queue(case_id: str, sources: list[dict[str, str]]) -> str:
    source_refs = "`, `".join(source["source_id"] for source in sources)
    return f"""# {case_id} Task Queue

task_id: {case_id}_task_001
task_type: source_check
priority: high
cluster: {case_id}_cluster_001
sources: `{source_refs}`
task: Verify that the imported sources are the right document packet for the case question before treating model output as analysis.
realism_value: Prevents the reusable engine from silently mapping an incomplete or wrong source bundle.
"""


def _first_nonempty_line(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _unique_source_id(case_id: str, path: Path, used_ids: set[str], index: int) -> str:
    base = _slugify(path.stem) or f"source_{index}"
    candidate = f"{case_id}_{base}"
    while candidate in used_ids:
        index += 1
        candidate = f"{case_id}_{base}_{index}"
    used_ids.add(candidate)
    return candidate


def _slugify(value: str | None) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return re.sub(r"_+", "_", slug)


def _title_from_path(path: Path) -> str:
    return re.sub(r"\s+", " ", path.stem.replace("_", " ").replace("-", " ")).strip().title()
