from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json


class PipelineProgress:
    def __init__(self, path: Path, *, backend_timeout: int | None, metadata: dict[str, Any] | None = None) -> None:
        self.path = path
        self._started_monotonic = time.monotonic()
        self.payload: dict[str, Any] = {
            "schema_id": "staged_pipeline_progress_v1",
            "status": "in_progress",
            "started_at_utc": _now_utc(),
            "last_update_utc": _now_utc(),
            "elapsed_seconds": 0.0,
            "backend_timeout_seconds": backend_timeout,
            "backend_call_count": 0,
            "backend_error_count": 0,
            "cache_hit_count": 0,
            "current_stage": "",
            "active_backend_call": {},
            "last_backend_call": {},
            "stages": {},
            "metadata": metadata or {},
        }
        self.write()

    def start_stage(self, stage: str, **fields: Any) -> None:
        row = self._stage(stage)
        row.update(
            {
                "status": "in_progress",
                "started_at_utc": row.get("started_at_utc") or _now_utc(),
                "last_update_utc": _now_utc(),
            }
        )
        row.update(_clean_fields(fields))
        self.payload["current_stage"] = stage
        self.write()

    def update_stage(self, stage: str, **fields: Any) -> None:
        row = self._stage(stage)
        row.update(_clean_fields(fields))
        row["last_update_utc"] = _now_utc()
        self.payload["current_stage"] = stage
        self.write()

    def finish_stage(self, stage: str, **fields: Any) -> None:
        row = self._stage(stage)
        row.update(_clean_fields(fields))
        row["status"] = "completed"
        row["completed_at_utc"] = _now_utc()
        row["last_update_utc"] = row["completed_at_utc"]
        self.payload["current_stage"] = stage
        self.write()

    def start_backend_call(
        self,
        *,
        stage: str,
        item_id: str,
        item_index: int | None = None,
        total_items: int | None = None,
        timeout_seconds: int | None = None,
        **fields: Any,
    ) -> None:
        timeout = timeout_seconds if timeout_seconds is not None else self.payload.get("backend_timeout_seconds")
        started = datetime.now(UTC)
        active = {
            "stage": stage,
            "item_id": item_id,
            "item_index": item_index,
            "total_items": total_items,
            "started_at_utc": started.isoformat().replace("+00:00", "Z"),
            "timeout_seconds": timeout,
            "deadline_utc": _deadline_utc(started, timeout),
        }
        active.update(_clean_fields(fields))
        self.payload["active_backend_call"] = active
        self.payload["current_stage"] = stage
        self.payload["backend_call_count"] = int(self.payload.get("backend_call_count", 0)) + 1
        self.update_stage(stage, active_item_id=item_id, active_item_index=item_index, total_items=total_items)

    def finish_backend_call(self, *, status: str = "completed", error: str = "", cache_hit: bool = False, **fields: Any) -> None:
        active = self.payload.get("active_backend_call") if isinstance(self.payload.get("active_backend_call"), dict) else {}
        completed = {
            **active,
            "status": status,
            "completed_at_utc": _now_utc(),
            "elapsed_seconds": _elapsed_since(active.get("started_at_utc")),
        }
        completed.update(_clean_fields(fields))
        if error:
            completed["error"] = error
            self.payload["backend_error_count"] = int(self.payload.get("backend_error_count", 0)) + 1
        if cache_hit:
            completed["cache_hit"] = True
            self.payload["cache_hit_count"] = int(self.payload.get("cache_hit_count", 0)) + 1
        self.payload["last_backend_call"] = completed
        self.payload["active_backend_call"] = {}
        self.write()

    def complete(self, **fields: Any) -> None:
        self.payload.update(_clean_fields(fields))
        self.payload["status"] = "completed"
        self.payload["completed_at_utc"] = _now_utc()
        self.payload["active_backend_call"] = {}
        self.write()

    def fail(self, error: str) -> None:
        self.payload["status"] = "failed"
        self.payload["failed_at_utc"] = _now_utc()
        self.payload["error"] = error
        self.write()

    def write(self) -> None:
        self.payload["last_update_utc"] = _now_utc()
        self.payload["elapsed_seconds"] = round(time.monotonic() - self._started_monotonic, 3)
        write_json(self.path, self.payload)

    def _stage(self, stage: str) -> dict[str, Any]:
        stages = self.payload.setdefault("stages", {})
        if not isinstance(stages, dict):
            stages = {}
            self.payload["stages"] = stages
        row = stages.setdefault(stage, {"status": "pending"})
        if not isinstance(row, dict):
            row = {"status": "pending"}
            stages[stage] = row
        return row


def _now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _deadline_utc(started: datetime, timeout_seconds: Any) -> str:
    try:
        timeout = int(timeout_seconds)
    except (TypeError, ValueError):
        return ""
    if timeout <= 0:
        return ""
    return (started + timedelta(seconds=timeout)).isoformat().replace("+00:00", "Z")


def _elapsed_since(started_at: Any) -> float:
    if not started_at:
        return 0.0
    try:
        started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return round((datetime.now(UTC) - started).total_seconds(), 3)


def _clean_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not None}
