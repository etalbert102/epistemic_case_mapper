from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any


PROGRESS_FILENAME = "memo_creation_progress.jsonl"


def memo_progress_path(artifacts: Path) -> Path:
    return Path(artifacts) / PROGRESS_FILENAME


def reset_memo_progress(artifacts: Path) -> Path:
    path = memo_progress_path(artifacts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
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


def _print_progress(row: dict[str, Any]) -> None:
    backend = str(row.get("backend") or "")
    suffix = f" backend={backend}" if backend else ""
    details = row.get("details") if isinstance(row.get("details"), dict) else {}
    detail_text = _detail_text(details)
    if detail_text:
        detail_text = f" {detail_text}"
    print(f"[memo] {row.get('stage')}: {row.get('status')}{suffix}{detail_text}", file=sys.stderr, flush=True)


def _detail_text(details: dict[str, Any]) -> str:
    keys = ("status", "accepted", "missing_mandatory_count", "unresolved_warning_count", "memo_words", "issue_count")
    parts = [f"{key}={details[key]}" for key in keys if key in details]
    return " ".join(parts)
