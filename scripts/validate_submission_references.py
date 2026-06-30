from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from artifact_utils import collect_ids
from epistemic_case_mapper.submission_manifest import SubmissionManifest, load_submission_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate judge-facing file and ID references.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    manifest = load_submission_manifest(repo_root, args.manifest)
    ids = collect_ids(repo_root, manifest)
    failures: list[str] = []
    for relative_path in _docs_to_scan(manifest):
        path = repo_root / relative_path
        if not path.exists():
            failures.append(f"missing_doc path={relative_path}")
            continue
        text = path.read_text(encoding="utf-8")
        _validate_paths(repo_root, relative_path, text, failures)
        _validate_ids(relative_path, text, manifest, ids, failures)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Validated submission references")
    return 0


def _docs_to_scan(manifest: SubmissionManifest) -> list[str]:
    docs = list(manifest.reference_scan_paths)
    for region in manifest.iter_worked_regions():
        docs.extend([region.best_path, region.map_path, region.baseline_path, region.audit_path])
    for case in manifest.cases:
        if case.full_case is not None:
            docs.extend([case.full_case.index_path, case.full_case.map_path])
            if case.full_case.baseline_path:
                docs.append(case.full_case.baseline_path)
        if case.task_queue is not None:
            docs.append(case.task_queue.path)
    return sorted(dict.fromkeys(docs))


def _validate_paths(repo_root: Path, relative_path: str, text: str, failures: list[str]) -> None:
    for reference in sorted(set(re.findall(r"`((?:docs|examples|scripts|data|artifacts|src|tests)/[^`]+)`", text))):
        if "<" in reference or ">" in reference:
            continue
        reference = reference.split()[0]
        if "*" in reference:
            if not list(repo_root.glob(reference)):
                failures.append(f"missing_glob_reference doc={relative_path} reference={reference}")
            continue
        if not (repo_root / reference).exists():
            failures.append(f"missing_path_reference doc={relative_path} reference={reference}")


def _validate_ids(
    relative_path: str,
    text: str,
    manifest: SubmissionManifest,
    ids: dict[str, set[str]],
    failures: list[str],
) -> None:
    prefixes = sorted(re.escape(prefix) for prefix in manifest.known_id_prefixes())
    if not prefixes:
        return
    prefix_pattern = "|".join(prefixes)
    for match in sorted(set(re.findall(rf"`(({prefix_pattern})_c\d+)`", text))):
        claim_id = match[0]
        if claim_id not in ids["claim"]:
            failures.append(f"missing_claim_reference doc={relative_path} id={claim_id}")
    for match in sorted(set(re.findall(rf"`(({prefix_pattern})_r\d+)`", text))):
        relation_id = match[0]
        if relation_id not in ids["relation"]:
            failures.append(f"missing_relation_reference doc={relative_path} id={relation_id}")
    for match in sorted(set(re.findall(rf"`(({prefix_pattern})_loss_\d+)`", text))):
        loss_id = match[0]
        if loss_id not in ids["loss"]:
            failures.append(f"missing_loss_reference doc={relative_path} id={loss_id}")


if __name__ == "__main__":
    raise SystemExit(main())
