from __future__ import annotations

import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator


PROGRESS_FILENAME = "memo_creation_progress.jsonl"


def memo_progress_path(artifacts: Path) -> Path:
    return Path(artifacts) / PROGRESS_FILENAME


def reset_memo_progress(artifacts: Path) -> Path:
    path = memo_progress_path(artifacts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def ensure_memo_progress(artifacts: Path) -> Path:
    path = memo_progress_path(artifacts)
    if not path.exists():
        reset_memo_progress(artifacts)
    return path


def record_memo_progress(
    artifacts: Path,
    stage: str,
    status: str,
    *,
    backend: str = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "schema_id": "memo_creation_progress_event_v1",
        "time_unix": round(time.time(), 3),
        "stage": stage,
        "status": status,
        "backend": backend,
        "details": details or {},
    }
    path = memo_progress_path(artifacts)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    _print_progress(row)
    return row


@contextmanager
def memo_progress_stage(
    artifacts: Path,
    stage: str,
    *,
    backend: str = "",
    details: dict[str, Any] | None = None,
    completion_details: Callable[[], dict[str, Any]] | None = None,
) -> Iterator[None]:
    record_memo_progress(artifacts, stage, "started", backend=backend, details=details)
    try:
        yield
    except Exception as exc:
        record_memo_progress(
            artifacts,
            stage,
            "failed",
            backend=backend,
            details={"error_type": type(exc).__name__, "error": str(exc)[:500]},
        )
        raise
    record_memo_progress(
        artifacts,
        stage,
        "completed",
        backend=backend,
        details=completion_details() if completion_details else {},
    )


def _print_progress(row: dict[str, Any]) -> None:
    backend = str(row.get("backend") or "")
    suffix = f" backend={backend}" if backend else ""
    details = row.get("details") if isinstance(row.get("details"), dict) else {}
    detail_text = _detail_text(details)
    if detail_text:
        detail_text = f" {detail_text}"
    print(f"[memo] {row.get('stage')}: {row.get('status')}{suffix}{detail_text}", file=sys.stderr, flush=True)


def _detail_text(details: dict[str, Any]) -> str:
    keys = (
        "status",
        "substage",
        "method",
        "bundle_count",
        "retain_item_count",
        "prompt_chars",
        "local_shard_count",
        "local_shards_completed",
        "chunk_count",
        "task_count",
        "parsed_count",
        "failed_count",
        "row_count",
        "accepted",
        "accepted_count",
        "warning_only_count",
        "missing_mandatory_count",
        "unresolved_warning_count",
        "memo_words",
        "issue_count",
    )
    parts = [f"{key}={details[key]}" for key in keys if key in details]
    return " ".join(parts)
