from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.submission_manifest import SubmissionCase, TaskQueue, load_submission_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate operational realism artifacts.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    manifest = load_submission_manifest(repo_root, args.manifest)
    failures: list[str] = []

    realism_docs = ["docs/methodology/OPERATIONAL_WORKFLOW.md"] + [
        queue.path for _case, queue in manifest.iter_task_queues()
    ]
    for relative_path in realism_docs:
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
    for case, queue in manifest.iter_task_queues():
        _validate_task_queue(repo_root, case, queue, failures)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Validated operational realism artifacts")
    return 0


def _validate_playbook(repo_root: Path, failures: list[str]) -> None:
    text = (repo_root / "docs/methodology/OPERATIONAL_WORKFLOW.md").read_text(encoding="utf-8")
    for required in ("Roles", "Realistic Workflow", "Full-Case Scaffold Design", "Realism Verdict"):
        if required not in text:
            failures.append(f"playbook_missing_section section={required}")


def _validate_realism_audit(repo_root: Path, failures: list[str]) -> None:
    text = (repo_root / "docs/methodology/OPERATIONAL_WORKFLOW.md").read_text(encoding="utf-8")
    for required in ("What Is Realistic Now", "Remaining Gaps", "Realism Verdict"):
        if required not in text:
            failures.append(f"realism_audit_missing_section section={required}")


def _validate_task_queue(repo_root: Path, case: SubmissionCase, queue: TaskQueue, failures: list[str]) -> None:
    manifest = CaseManifest.model_validate(read_yaml(repo_root / case.case_path))
    text = (repo_root / queue.path).read_text(encoding="utf-8")
    task_ids = re.findall(r"^task_id:\s*([A-Za-z0-9_\\-]+)", text, flags=re.MULTILINE)
    if len(task_ids) < queue.min_tasks:
        failures.append(f"task_queue_too_few_tasks case={manifest.case_id} count={len(task_ids)}")
    for task_id in task_ids:
        if not task_id.startswith(queue.prefix):
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
