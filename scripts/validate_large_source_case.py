#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest


def _query_from_notes(notes: str | None) -> str:
    if not notes or "query:" not in notes:
        return ""
    return notes.split("query:", 1)[1].strip()


def validate_large_source_case(
    case_path: Path,
    *,
    min_sources: int,
    min_words: int,
    min_estimated_tokens: int,
    min_queries: int,
) -> list[str]:
    errors: list[str] = []
    case = CaseManifest.model_validate(read_yaml(case_path))
    root = case_path.parents[3] if case_path.as_posix().endswith("data/cases/" + case.case_id + "/case.yaml") else Path.cwd()
    source_ids = [source.source_id for source in case.sources]
    if len(case.sources) < min_sources:
        errors.append(f"source count {len(case.sources)} is below required minimum {min_sources}")
    if len(source_ids) != len(set(source_ids)):
        errors.append("source IDs are not unique")

    total_words = 0
    queries: set[str] = set()
    for source in case.sources:
        if not source.path:
            errors.append(f"{source.source_id} has no text path")
            continue
        text_path = root / source.path
        raw_path = root / "data" / "cases" / case.case_id / "sources" / "raw" / f"{source.source_id}.xml"
        if not text_path.exists():
            errors.append(f"{source.source_id} text path is missing: {text_path}")
            continue
        if not raw_path.exists():
            errors.append(f"{source.source_id} raw XML is missing: {raw_path}")
        if not source.url or "pmc.ncbi.nlm.nih.gov/articles/PMC" not in source.url:
            errors.append(f"{source.source_id} URL is not a PMC article URL")
        if source.provenance_level != "peer_reviewed":
            errors.append(f"{source.source_id} provenance_level is {source.provenance_level!r}, expected peer_reviewed")
        text = text_path.read_text(encoding="utf-8")
        total_words += len(re.findall(r"\b\w+\b", text))
        query = _query_from_notes(source.notes)
        if query:
            queries.add(query)

    estimated_tokens = int(total_words * 1.33)
    if total_words < min_words:
        errors.append(f"word count {total_words:,} is below required minimum {min_words:,}")
    if estimated_tokens < min_estimated_tokens:
        errors.append(f"estimated token count {estimated_tokens:,} is below required minimum {min_estimated_tokens:,}")
    if len(queries) < min_queries:
        errors.append(f"query diversity {len(queries)} is below required minimum {min_queries}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a large source stress-case corpus.")
    parser.add_argument("--case", default="data/cases/eggs_large_source_stress/case.yaml")
    parser.add_argument("--min-sources", type=int, default=40)
    parser.add_argument("--min-words", type=int, default=250_000)
    parser.add_argument("--min-estimated-tokens", type=int, default=256_000)
    parser.add_argument("--min-queries", type=int, default=3)
    args = parser.parse_args()

    errors = validate_large_source_case(
        Path(args.case),
        min_sources=args.min_sources,
        min_words=args.min_words,
        min_estimated_tokens=args.min_estimated_tokens,
        min_queries=args.min_queries,
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: {args.case}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
