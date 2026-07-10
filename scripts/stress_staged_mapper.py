from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from epistemic_case_mapper.case_initializer import init_case_package
from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.staged_semantic_pipeline import run_staged_map


DEFAULT_CASES = (
    "data/cases/covid_origins_slice/case.yaml",
    "data/cases/eggs/case.yaml",
    "data/cases/lhc_black_holes/case.yaml",
)

FIELDNAMES = (
    "run_id",
    "status",
    "validated",
    "case_id",
    "source_count",
    "backend",
    "timeout_seconds",
    "backend_retries",
    "chunk_lines",
    "chunk_overlap_lines",
    "max_chunks_per_source",
    "max_total_chunks",
    "max_claims_per_source",
    "claim_extraction_method",
    "max_relation_pairs",
    "relation_batch_size",
    "runtime_seconds",
    "all_chunk_count",
    "selected_chunk_count",
    "skipped_chunk_count",
    "relation_batch_count",
    "claim_count",
    "relation_count",
    "rejected_claim_count",
    "rejected_relation_count",
    "fallback_claim_count",
    "fallback_relation_count",
    "backend_error_count",
    "failure_count",
    "failures",
    "workspace",
    "artifact_dir",
    "output_path",
    "error",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stress-test the staged semantic mapper across cases and backends.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--cases", nargs="+", default=list(DEFAULT_CASES), help="Case manifest paths to run.")
    parser.add_argument(
        "--models",
        nargs="+",
        help="Ollama model names. Each value is converted to ollama:<model> unless already backend-prefixed.",
    )
    parser.add_argument(
        "--backends",
        nargs="+",
        help="Backend specs such as ollama:gemma4:26b, command:..., or prompt. Overrides --models when supplied.",
    )
    parser.add_argument("--timeouts", nargs="+", type=int, default=[20])
    parser.add_argument("--retries", nargs="+", type=int, default=[0])
    parser.add_argument("--relation-pairs", nargs="+", type=int, default=[4])
    parser.add_argument("--relation-batch-size", type=int, default=4)
    parser.add_argument("--runs-per-config", type=int, default=1)
    parser.add_argument("--chunk-lines", type=int, default=80)
    parser.add_argument("--chunk-overlap-lines", type=int, default=0)
    parser.add_argument("--max-chunks-per-source", type=int, default=0, help="0 means no per-source cap.")
    parser.add_argument("--max-total-chunks", type=int, default=0, help="0 means no total cap.")
    parser.add_argument("--max-claims-per-source", type=int, default=3)
    parser.add_argument(
        "--max-sources",
        type=int,
        help="Use only the first N sources from each case manifest; useful for quick smoke tests.",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for JSONL/CSV reports and disposable workspaces. Defaults to artifacts/stress/staged_mapper/<timestamp>.",
    )
    parser.add_argument("--fail-on-failure", action="store_true", help="Exit nonzero if any stress run fails validation.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_dir = _output_dir(repo_root, args.output_dir)
    workspaces_dir = output_dir / "workspaces"
    workspaces_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "runs.jsonl"
    csv_path = output_dir / "runs.csv"

    backends = _backends(args)
    cases = [_load_case(repo_root, path, args.max_sources) for path in args.cases]

    rows: list[dict[str, Any]] = []
    with jsonl_path.open("w", encoding="utf-8") as jsonl_file, csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for case_manifest, doc_paths in cases:
            for backend in backends:
                for timeout in args.timeouts:
                    for retries in args.retries:
                        for relation_pairs in args.relation_pairs:
                            for run_index in range(1, args.runs_per_config + 1):
                                row = _run_one(
                                    repo_root=repo_root,
                                    workspaces_dir=workspaces_dir,
                                    case_manifest=case_manifest,
                                    doc_paths=doc_paths,
                                    backend=backend,
                                    timeout=timeout,
                                    retries=retries,
                                    relation_pairs=relation_pairs,
                                    relation_batch_size=args.relation_batch_size,
                                    run_index=run_index,
                                    chunk_lines=args.chunk_lines,
                                    chunk_overlap_lines=args.chunk_overlap_lines,
                                    max_chunks_per_source=args.max_chunks_per_source,
                                    max_total_chunks=args.max_total_chunks,
                                    max_claims_per_source=args.max_claims_per_source,
                                )
                                rows.append(row)
                                jsonl_file.write(json.dumps(row, sort_keys=True) + "\n")
                                jsonl_file.flush()
                                writer.writerow({name: row.get(name, "") for name in FIELDNAMES})
                                csv_file.flush()
                                _print_row(row)

    _write_summary(output_dir / "summary.json", rows)
    print(f"Wrote {jsonl_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {output_dir / 'summary.json'}")
    if args.fail_on_failure and not all(row["status"] == "validated" for row in rows):
        return 1
    return 0


def _output_dir(repo_root: Path, output_dir: str | None) -> Path:
    if output_dir:
        path = Path(output_dir)
        if not path.is_absolute():
            path = repo_root / path
        path.mkdir(parents=True, exist_ok=True)
        return path
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = repo_root / "artifacts" / "stress" / "staged_mapper" / timestamp
    path.mkdir(parents=True, exist_ok=True)
    return path


def _backends(args: argparse.Namespace) -> list[str]:
    values = args.backends or args.models or ["ollama:gemma4:26b"]
    backends = []
    for value in values:
        spec = value.strip()
        if spec.startswith(("prompt", "command:", "ollama:")):
            backends.append(spec)
        else:
            backends.append(f"ollama:{spec}")
    return backends


def _load_case(repo_root: Path, case_path: str, max_sources: int | None) -> tuple[CaseManifest, list[Path]]:
    path = repo_root / case_path
    case_manifest = CaseManifest.model_validate(read_yaml(path))
    sources = case_manifest.sources[:max_sources] if max_sources else case_manifest.sources
    doc_paths = []
    for source in sources:
        if not source.path:
            raise ValueError(f"source has no path case={case_manifest.case_id} source={source.source_id}")
        doc_path = repo_root / source.path
        if not doc_path.exists():
            raise ValueError(f"source path missing case={case_manifest.case_id} path={source.path}")
        doc_paths.append(doc_path)
    return case_manifest, doc_paths


def _run_one(
    repo_root: Path,
    workspaces_dir: Path,
    case_manifest: CaseManifest,
    doc_paths: list[Path],
    backend: str,
    timeout: int,
    retries: int,
    relation_pairs: int,
    relation_batch_size: int,
    run_index: int,
    chunk_lines: int,
    chunk_overlap_lines: int,
    max_chunks_per_source: int,
    max_total_chunks: int,
    max_claims_per_source: int,
) -> dict[str, Any]:
    run_id = "_".join(
        (
            _safe(case_manifest.case_id),
            _safe(backend),
            f"t{timeout}",
            f"r{retries}",
            f"p{relation_pairs}",
            f"n{run_index:02d}",
        )
    )
    workspace = workspaces_dir / run_id
    package_root = workspace / "pkg"
    package_root.mkdir(parents=True, exist_ok=True)
    stress_case_id = _safe(f"stress_{run_id}")[:80]
    started = time.monotonic()
    base_row: dict[str, Any] = {
        "run_id": run_id,
        "case_id": case_manifest.case_id,
        "source_count": len(doc_paths),
        "backend": backend,
        "timeout_seconds": timeout,
        "backend_retries": retries,
        "chunk_lines": chunk_lines,
        "chunk_overlap_lines": chunk_overlap_lines,
        "max_chunks_per_source": max_chunks_per_source,
        "max_total_chunks": max_total_chunks,
        "max_claims_per_source": max_claims_per_source,
        "claim_extraction_method": "whole_doc_source_card",
        "max_relation_pairs": relation_pairs,
        "relation_batch_size": relation_batch_size,
        "workspace": package_root.as_posix(),
    }
    try:
        initialized = init_case_package(
            repo_root=package_root,
            package_path="package.yaml",
            case_id=stress_case_id,
            title=f"{case_manifest.title} Stress Run",
            question=case_manifest.question,
            doc_paths=doc_paths,
            model_backend=backend,
            force=True,
        )
        result = run_staged_map(
            repo_root=package_root,
            manifest_path="package.yaml",
            region_id=initialized.region_id,
            backend=backend,
            chunk_lines=chunk_lines,
            chunk_overlap_lines=chunk_overlap_lines,
            max_chunks_per_source=max_chunks_per_source or None,
            max_total_chunks=max_total_chunks or None,
            max_claims_per_source=max_claims_per_source,
            max_relation_pairs=relation_pairs,
            relation_batch_size=relation_batch_size,
            backend_timeout=timeout,
            backend_retries=retries,
            validate=True,
        )
        summary_path = result.artifact_dir / "run_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
        final_map = _read_map(result.output_path)
        runtime = time.monotonic() - started
        row = {
            **base_row,
            "status": "validated" if not result.failures else "validation_failed",
            "validated": not result.failures,
            "runtime_seconds": round(runtime, 3),
            "all_chunk_count": summary.get("all_chunk_count", ""),
            "selected_chunk_count": summary.get("selected_chunk_count", ""),
            "skipped_chunk_count": summary.get("skipped_chunk_count", ""),
            "relation_batch_count": summary.get("relation_batch_count", ""),
            "claim_count": result.claim_count,
            "relation_count": result.relation_count,
            "rejected_claim_count": result.rejected_claim_count,
            "rejected_relation_count": result.rejected_relation_count,
            "fallback_claim_count": _fallback_claim_count(final_map),
            "fallback_relation_count": _fallback_relation_count(final_map),
            "backend_error_count": _backend_error_count(summary),
            "failure_count": len(result.failures),
            "failures": ";".join(result.failures),
            "artifact_dir": result.artifact_dir.as_posix(),
            "output_path": result.output_path.as_posix(),
            "error": "",
        }
        return row
    except Exception as exc:  # noqa: BLE001
        runtime = time.monotonic() - started
        return {
            **base_row,
            "status": "exception",
            "validated": False,
            "runtime_seconds": round(runtime, 3),
            "all_chunk_count": 0,
            "selected_chunk_count": 0,
            "skipped_chunk_count": 0,
            "relation_batch_count": 0,
            "claim_count": 0,
            "relation_count": 0,
            "rejected_claim_count": 0,
            "rejected_relation_count": 0,
            "fallback_claim_count": 0,
            "fallback_relation_count": 0,
            "backend_error_count": 0,
            "failure_count": 1,
            "failures": "",
            "artifact_dir": "",
            "output_path": "",
            "error": str(exc),
        }


def _read_map(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _fallback_claim_count(final_map: dict[str, Any]) -> int:
    return sum(
        1
        for claim in final_map.get("claims", [])
        if isinstance(claim, dict) and str(claim.get("extraction_method", "")).startswith("deterministic_fallback")
    )


def _fallback_relation_count(final_map: dict[str, Any]) -> int:
    return sum(
        1
        for relation in final_map.get("relations", [])
        if isinstance(relation, dict) and str(relation.get("extraction_method", "")).startswith("deterministic_fallback")
    )


def _backend_error_count(summary: dict[str, Any]) -> int:
    errors = 0
    for key in ("rejected_claims", "rejected_relations"):
        for item in summary.get(key, []):
            if isinstance(item, dict) and "backend_error" in str(item.get("reason", "")):
                errors += 1
    return errors


def _write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    validated = sum(1 for row in rows if row["status"] == "validated")
    payload = {
        "run_count": len(rows),
        "validated_count": validated,
        "validation_rate": validated / len(rows) if rows else 0,
        "exception_count": sum(1 for row in rows if row["status"] == "exception"),
        "validation_failed_count": sum(1 for row in rows if row["status"] == "validation_failed"),
        "total_runtime_seconds": round(sum(float(row["runtime_seconds"]) for row in rows), 3),
        "total_selected_chunks": sum(int(row["selected_chunk_count"] or 0) for row in rows),
        "total_skipped_chunks": sum(int(row["skipped_chunk_count"] or 0) for row in rows),
        "total_fallback_claims": sum(int(row["fallback_claim_count"]) for row in rows),
        "total_fallback_relations": sum(int(row["fallback_relation_count"]) for row in rows),
        "total_backend_errors": sum(int(row["backend_error_count"]) for row in rows),
        "rows": rows,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _print_row(row: dict[str, Any]) -> None:
    print(
        "stress_run "
        f"status={row['status']} case={row['case_id']} backend={row['backend']} "
        f"timeout={row['timeout_seconds']} retries={row['backend_retries']} pairs={row['max_relation_pairs']} "
        f"batch={row['relation_batch_size']} "
        f"runtime={row['runtime_seconds']}s chunks={row['selected_chunk_count']}/{row['all_chunk_count']} "
        f"claims={row['claim_count']} relations={row['relation_count']} "
        f"fallback_claims={row['fallback_claim_count']} fallback_relations={row['fallback_relation_count']} "
        f"failures={row['failure_count']}"
    )


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_").lower()


if __name__ == "__main__":
    sys.exit(main())
