from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from artifact_utils import collect_ids
from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest, Relation


UPDATE_DEMO_PATH = "docs/NEW_SOURCE_UPDATE_DEMO.md"
CASE_PATH = "data/cases/lhc_black_holes/case.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the judge-facing new-source update demo.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    failures: list[str] = []
    path = repo_root / UPDATE_DEMO_PATH
    if not path.exists():
        print(f"FAIL: missing_update_demo path={UPDATE_DEMO_PATH}", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8")
    manifest = CaseManifest.model_validate(read_yaml(repo_root / CASE_PATH))
    source_ids = {source.source_id for source in manifest.sources}
    source_paths = {source.source_id: source.path for source in manifest.sources if source.path}
    ids = collect_ids(repo_root)

    claims = _parse_blocks(text, "claim_id", "lhc_update_c")
    relations = _parse_blocks(text, "relation_id", "lhc_update_r")
    if not claims:
        failures.append("no_update_claims")
    if not relations:
        failures.append("no_update_relations")

    update_claim_ids = {claim.get("claim_id", "") for claim in claims}
    for claim in claims:
        claim_id = claim.get("claim_id", "")
        source_id = claim.get("source_id", "")
        span = claim.get("source_span", "")
        excerpt = claim.get("excerpt", "")
        entailed = claim.get("entailed_by_excerpt", "")
        if source_id not in source_ids:
            failures.append(f"unknown_update_source claim={claim_id} source={source_id}")
            continue
        if entailed != "yes":
            failures.append(f"update_claim_not_entailed_yes claim={claim_id} value={entailed}")
        _validate_span(repo_root, source_paths, claim_id, source_id, span, excerpt, failures)

    for relation in relations:
        relation_id = relation.get("relation_id", "")
        source_claim = relation.get("source_claim", "")
        target_claim = relation.get("target_claim", "")
        relation_type = relation.get("relation_type", "")
        if source_claim not in update_claim_ids:
            failures.append(f"unknown_relation_source_claim relation={relation_id} claim={source_claim}")
        if target_claim not in ids["claim"]:
            failures.append(f"unknown_relation_target_claim relation={relation_id} claim={target_claim}")
        try:
            Relation(
                relation_id=relation_id,
                source_claim_id=source_claim,
                target_claim_id=target_claim,
                relation_type=relation_type,
                rationale=relation.get("rationale", ""),
            )
        except Exception as exc:  # pragma: no cover - exact pydantic text is not part of the contract.
            failures.append(f"invalid_relation relation={relation_id} error={exc}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Validated new-source update demo")
    return 0


def _parse_blocks(text: str, id_field: str, id_prefix: str) -> list[dict[str, str]]:
    pattern = rf"(?ms)^{re.escape(id_field)}:\s*{re.escape(id_prefix)}.+?(?=^{re.escape(id_field)}:\s|\n## |\Z)"
    return [_parse_block(match.group(0).strip()) for match in re.finditer(pattern, text)]


def _parse_block(block: str) -> dict[str, str]:
    result: dict[str, str] = {}
    current_key: str | None = None
    current_value: list[str] = []
    for line in block.splitlines():
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if match:
            if current_key:
                result[current_key] = _strip(" ".join(current_value).strip())
            current_key = match.group(1)
            current_value = [match.group(2).strip()]
        elif current_key:
            current_value.append(line.strip())
    if current_key:
        result[current_key] = _strip(" ".join(current_value).strip())
    return result


def _validate_span(
    repo_root: Path,
    source_paths: dict[str, str],
    claim_id: str,
    source_id: str,
    span: str,
    excerpt: str,
    failures: list[str],
) -> None:
    match = re.fullmatch(r"lines\s+(\d+)-(\d+)", span)
    if not match:
        failures.append(f"invalid_update_span claim={claim_id} span={span}")
        return
    start, end = (int(match.group(1)), int(match.group(2)))
    source_path = source_paths.get(source_id)
    if not source_path:
        failures.append(f"missing_update_source_path claim={claim_id} source={source_id}")
        return
    source_file = repo_root / source_path
    if not source_file.exists():
        failures.append(f"missing_update_source_file claim={claim_id} path={source_path}")
        return
    lines = source_file.read_text(encoding="utf-8").splitlines()
    if start < 1 or end > len(lines) or start > end:
        failures.append(f"update_span_out_of_range claim={claim_id} span={span}")
        return
    span_text = _normalize(" ".join(lines[start - 1 : end]))
    for fragment in _excerpt_fragments(excerpt):
        if _normalize(fragment) not in span_text:
            failures.append(f"update_excerpt_not_in_span claim={claim_id} fragment={fragment}")


def _excerpt_fragments(excerpt: str) -> list[str]:
    return [fragment.strip(" .") for fragment in excerpt.split("...") if len(fragment.strip(" .")) >= 12]


def _strip(value: str) -> str:
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def _normalize(value: str) -> str:
    return (
        value.replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
        .lower()
    )


if __name__ == "__main__":
    raise SystemExit(main())
