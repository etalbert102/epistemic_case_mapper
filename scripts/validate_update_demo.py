from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from artifact_utils import collect_ids
from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest, Relation
from epistemic_case_mapper.submission_manifest import SubmissionManifest, UpdateDemo, load_submission_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the judge-facing new-source update demo.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    parser.add_argument("--demo", help="Validate one update demo by manifest demo_id.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    manifest = load_submission_manifest(repo_root, args.manifest)
    failures: list[str] = []
    ids = collect_ids(repo_root)
    demos = [demo for demo in manifest.update_demos if args.demo in (None, demo.demo_id)]
    if args.demo is not None and not demos:
        failures.append(f"unknown_update_demo demo={args.demo}")
    for demo in demos:
        _validate_demo(repo_root, manifest, demo, ids, failures)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Validated new-source update demo")
    return 0


def _validate_demo(
    repo_root: Path,
    submission_manifest: SubmissionManifest,
    demo: UpdateDemo,
    ids: dict[str, set[str]],
    failures: list[str],
) -> None:
    path = repo_root / demo.path
    if not path.exists():
        failures.append(f"missing_update_demo demo={demo.demo_id} path={demo.path}")
        return

    try:
        submission_case = submission_manifest.case_for_key(demo.case_key)
    except KeyError:
        failures.append(f"unknown_update_demo_case demo={demo.demo_id} case={demo.case_key}")
        return
    case_manifest = CaseManifest.model_validate(read_yaml(repo_root / submission_case.case_path))
    source_ids = {source.source_id for source in case_manifest.sources}
    source_paths = {source.source_id: source.path for source in case_manifest.sources if source.path}
    text = path.read_text(encoding="utf-8")

    claims = _parse_blocks(text, "claim_id", demo.claim_id_prefix)
    relations = _parse_blocks(text, "relation_id", demo.relation_id_prefix)
    if not claims:
        failures.append(f"no_update_claims demo={demo.demo_id}")
    if not relations:
        failures.append(f"no_update_relations demo={demo.demo_id}")

    update_claim_ids = {claim.get("claim_id", "") for claim in claims}
    for claim in claims:
        claim_id = claim.get("claim_id", "")
        source_id = claim.get("source_id", "")
        span = claim.get("source_span", "")
        excerpt = claim.get("excerpt", "")
        entailed = claim.get("entailed_by_excerpt", "")
        if source_id not in source_ids:
            failures.append(f"unknown_update_source demo={demo.demo_id} claim={claim_id} source={source_id}")
            continue
        if entailed != "yes":
            failures.append(f"update_claim_not_entailed_yes demo={demo.demo_id} claim={claim_id} value={entailed}")
        _validate_span(repo_root, source_paths, claim_id, source_id, span, excerpt, failures)

    for relation in relations:
        relation_id = relation.get("relation_id", "")
        source_claim = relation.get("source_claim", "")
        target_claim = relation.get("target_claim", "")
        relation_type = relation.get("relation_type", "")
        if source_claim not in update_claim_ids:
            failures.append(
                f"unknown_relation_source_claim demo={demo.demo_id} relation={relation_id} claim={source_claim}"
            )
        if target_claim not in ids["claim"]:
            failures.append(
                f"unknown_relation_target_claim demo={demo.demo_id} relation={relation_id} claim={target_claim}"
            )
        try:
            Relation(
                relation_id=relation_id,
                source_claim_id=source_claim,
                target_claim_id=target_claim,
                relation_type=relation_type,
                rationale=relation.get("rationale", ""),
            )
        except Exception as exc:  # pragma: no cover - exact pydantic text is not part of the contract.
            failures.append(f"invalid_relation demo={demo.demo_id} relation={relation_id} error={exc}")


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
