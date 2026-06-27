from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from artifact_utils import collect_ids


DOCS_TO_SCAN = (
    "README.md",
    "docs/FLF_JUDGE_INDEX.md",
    "docs/FLF_JUDGE_WALKTHROUGH.md",
    "docs/FLF_BEFORE_AFTER_COMPARISON.md",
    "docs/FLF_SUBMISSION_DRAFT.md",
    "docs/FULL_CASE_KNOWLEDGE_BASE_PLAN.md",
    "docs/INVESTIGATOR_WORKFLOW_PLAYBOOK.md",
    "docs/OPERATIONAL_REALISM_AUDIT.md",
    "docs/SUBMISSION_PACKET.md",
    "docs/SUBMISSION_LIMITATIONS.md",
    "docs/ARCHITECTURE.md",
    "docs/SUBMISSION_ARTIFACT_SUMMARY.md",
    "docs/review/LHC_HUMAN_AUDIT_PACKET.md",
    "docs/review/EGGS_HUMAN_AUDIT_PACKET.md",
    "docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md",
    "examples/lhc_black_holes/full_case_index.md",
    "examples/lhc_black_holes/full_case_map.md",
    "examples/lhc_black_holes/investigator_task_queue.md",
    "examples/eggs/full_case_index.md",
    "examples/eggs/full_case_map.md",
    "examples/eggs/investigator_task_queue.md",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate judge-facing file and ID references.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    ids = collect_ids(repo_root)
    failures: list[str] = []
    for relative_path in DOCS_TO_SCAN:
        path = repo_root / relative_path
        if not path.exists():
            failures.append(f"missing_doc path={relative_path}")
            continue
        text = path.read_text(encoding="utf-8")
        _validate_paths(repo_root, relative_path, text, failures)
        _validate_ids(relative_path, text, ids, failures)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Validated submission references")
    return 0


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


def _validate_ids(relative_path: str, text: str, ids: dict[str, set[str]], failures: list[str]) -> None:
    for claim_id in sorted(set(re.findall(r"`(lhc_c\d+|eggs_c\d+)`", text))):
        if claim_id not in ids["claim"]:
            failures.append(f"missing_claim_reference doc={relative_path} id={claim_id}")
    for relation_id in sorted(set(re.findall(r"`(lhc_r\d+|eggs_r\d+)`", text))):
        if relation_id not in ids["relation"]:
            failures.append(f"missing_relation_reference doc={relative_path} id={relation_id}")
    for loss_id in sorted(set(re.findall(r"`(lhc_loss_\d+|eggs_loss_\d+)`", text))):
        if loss_id not in ids["loss"]:
            failures.append(f"missing_loss_reference doc={relative_path} id={loss_id}")


if __name__ == "__main__":
    raise SystemExit(main())
