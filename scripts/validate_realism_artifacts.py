from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest


REALISM_DOCS = (
    "docs/OPERATIONAL_WORKFLOW_AND_REALISM.md",
    "examples/lhc_black_holes/investigator_task_queue.md",
    "examples/eggs/investigator_task_queue.md",
)

TASK_QUEUES = (
    {
        "case_path": "data/cases/lhc_black_holes/case.yaml",
        "task_path": "examples/lhc_black_holes/investigator_task_queue.md",
        "prefix": "lhc_task_",
    },
    {
        "case_path": "data/cases/eggs/case.yaml",
        "task_path": "examples/eggs/investigator_task_queue.md",
        "prefix": "eggs_task_",
    },
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate operational realism artifacts.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    failures: list[str] = []

    for relative_path in REALISM_DOCS:
        path = repo_root / relative_path
        if not path.exists():
            failures.append(f"missing_realism_doc path={relative_path}")
            continue
        text = path.read_text(encoding="utf-8")
        if "Status: `human-review-needed`" not in text:
            failures.append(f"realism_doc_missing_status path={relative_path}")
        if len(text.split()) < 250:
            failures.append(f"realism_doc_too_short path={relative_path} words={len(text.split())}")

    _validate_playbook(repo_root, failures)
    _validate_realism_audit(repo_root, failures)
    for queue in TASK_QUEUES:
        _validate_task_queue(repo_root, queue, failures)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Validated operational realism artifacts")
    return 0


def _validate_playbook(repo_root: Path, failures: list[str]) -> None:
    text = (repo_root / "docs/OPERATIONAL_WORKFLOW_AND_REALISM.md").read_text(encoding="utf-8")
    for required in ("Roles", "Realistic Workflow", "Full-Case Scaffold Design", "Realism Verdict"):
        if required not in text:
            failures.append(f"playbook_missing_section section={required}")


def _validate_realism_audit(repo_root: Path, failures: list[str]) -> None:
    text = (repo_root / "docs/OPERATIONAL_WORKFLOW_AND_REALISM.md").read_text(encoding="utf-8")
    for required in ("What Is Realistic Now", "Remaining Gaps", "Realism Verdict"):
        if required not in text:
            failures.append(f"realism_audit_missing_section section={required}")


def _validate_task_queue(repo_root: Path, queue: dict[str, str], failures: list[str]) -> None:
    manifest = CaseManifest.model_validate(read_yaml(repo_root / queue["case_path"]))
    text = (repo_root / queue["task_path"]).read_text(encoding="utf-8")
    task_ids = re.findall(r"^task_id:\s*([A-Za-z0-9_\\-]+)", text, flags=re.MULTILINE)
    if len(task_ids) < 5:
        failures.append(f"task_queue_too_few_tasks case={manifest.case_id} count={len(task_ids)}")
    for task_id in task_ids:
        if not task_id.startswith(queue["prefix"]):
            failures.append(f"task_queue_bad_prefix case={manifest.case_id} task_id={task_id}")
    for required in ("task_type:", "priority:", "cluster:", "sources:", "realism_value:", "done_when:"):
        if text.count(required) < len(task_ids):
            failures.append(f"task_queue_missing_field case={manifest.case_id} field={required}")
    source_ids = {source.source_id for source in manifest.sources}
    referenced_sources = set(re.findall(r"`([A-Za-z0-9_\\-]+)`", text))
    missing = sorted(item for item in referenced_sources if item.endswith("_review") and item not in source_ids)
    for source_id in missing:
        failures.append(f"task_queue_unknown_source case={manifest.case_id} source={source_id}")


if __name__ == "__main__":
    raise SystemExit(main())
