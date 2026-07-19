from __future__ import annotations

import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any

from epistemic_case_mapper.io import write_json


class PipelineProgress:
    def __init__(self, path: Path, *, backend_timeout: int | None, metadata: dict[str, Any] | None = None) -> None:
        self.path = path
        self._started_monotonic = time.monotonic()
        self._lock = RLock()
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
            "active_backend_calls": {},
            "active_backend_call_count": 0,
            "last_backend_call": {},
            "recent_backend_calls": [],
            "monitor_summary": "",
            "stages": {},
            "metadata": metadata or {},
        }
        self.write()

    def start_stage(self, stage: str, **fields: Any) -> None:
        with self._lock:
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
            self._print_event(stage, "started", fields)

    def update_stage(self, stage: str, **fields: Any) -> None:
        with self._lock:
            row = self._stage(stage)
            row.update(_clean_fields(fields))
            row["last_update_utc"] = _now_utc()
            self.payload["current_stage"] = stage
            self.write()

    def finish_stage(self, stage: str, **fields: Any) -> None:
        with self._lock:
            row = self._stage(stage)
            row.update(_clean_fields(fields))
            row["status"] = "completed"
            row["completed_at_utc"] = _now_utc()
            row["last_update_utc"] = row["completed_at_utc"]
            self.payload["current_stage"] = stage
            self.write()
            self._print_event(stage, "completed", fields)

    def start_backend_call(
        self,
        *,
        stage: str,
        item_id: str,
        call_id: str | None = None,
        item_index: int | None = None,
        total_items: int | None = None,
        timeout_seconds: int | None = None,
        **fields: Any,
    ) -> str:
        with self._lock:
            timeout = timeout_seconds if timeout_seconds is not None else self.payload.get("backend_timeout_seconds")
            started = datetime.now(UTC)
            resolved_call_id = call_id or _call_id(stage, item_id)
            active = {
                "call_id": resolved_call_id,
                "stage": stage,
                "item_id": item_id,
                "item_index": item_index,
                "total_items": total_items,
                "started_at_utc": started.isoformat().replace("+00:00", "Z"),
                "timeout_seconds": timeout,
                "deadline_utc": _deadline_utc(started, timeout),
            }
            active.update(_clean_fields(fields))
            calls = self._active_backend_calls()
            calls[resolved_call_id] = active
            self.payload["active_backend_call"] = active
            self.payload["active_backend_call_count"] = len(calls)
            self.payload["current_stage"] = stage
            self.payload["backend_call_count"] = int(self.payload.get("backend_call_count", 0)) + 1
            self.update_stage(
                stage,
                active_item_id=item_id,
                active_item_index=item_index,
                total_items=total_items,
                active_backend_call_count=len(calls),
            )
            self._print_event(stage, "backend_started", active)
            return resolved_call_id

    def finish_backend_call(
        self,
        *,
        call_id: str | None = None,
        status: str = "completed",
        error: str = "",
        cache_hit: bool = False,
        **fields: Any,
    ) -> None:
        with self._lock:
            calls = self._active_backend_calls()
            active: dict[str, Any] = {}
            if call_id and call_id in calls:
                active = calls.pop(call_id)
            elif calls:
                _, active = calls.popitem()
            else:
                current = self.payload.get("active_backend_call")
                active = current if isinstance(current, dict) else {}
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
            self._append_recent_backend_call(completed)
            self.payload["active_backend_calls"] = calls
            self.payload["active_backend_call_count"] = len(calls)
            self.payload["active_backend_call"] = _latest_active_call(calls)
            stage = str(completed.get("stage") or self.payload.get("current_stage") or "")
            if stage:
                self.update_stage(stage, active_backend_call_count=len(calls), last_item_id=completed.get("item_id"))
            else:
                self.write()
            self._print_event(stage or "backend", _backend_event_status(status), completed)

    def complete(self, **fields: Any) -> None:
        with self._lock:
            self.payload.update(_clean_fields(fields))
            self.payload["status"] = "completed"
            self.payload["completed_at_utc"] = _now_utc()
            self.payload["active_backend_call"] = {}
            self.payload["active_backend_calls"] = {}
            self.payload["active_backend_call_count"] = 0
            self.write()
            self._print_event("pipeline", "completed", fields)

    def fail(self, error: str) -> None:
        with self._lock:
            self.payload["status"] = "failed"
            self.payload["failed_at_utc"] = _now_utc()
            self.payload["error"] = error
            self.write()
            self._print_event("pipeline", "failed", {"error": error})

    def write(self) -> None:
        with self._lock:
            self.payload["last_update_utc"] = _now_utc()
            self.payload["elapsed_seconds"] = round(time.monotonic() - self._started_monotonic, 3)
            self.payload["monitor_summary"] = self.monitor_summary()
            write_json(self.path, self.payload)

    def monitor_summary(self) -> str:
        stage = str(self.payload.get("current_stage") or "not_started")
        status = str(self.payload.get("status") or "unknown")
        active_count = int(self.payload.get("active_backend_call_count") or 0)
        backend_count = int(self.payload.get("backend_call_count") or 0)
        error_count = int(self.payload.get("backend_error_count") or 0)
        return (
            f"status={status} stage={stage} elapsed={self.payload.get('elapsed_seconds', 0)}s "
            f"active_backend_calls={active_count} backend_calls={backend_count} backend_errors={error_count}"
        )

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

    def _active_backend_calls(self) -> dict[str, Any]:
        calls = self.payload.setdefault("active_backend_calls", {})
        if not isinstance(calls, dict):
            calls = {}
            self.payload["active_backend_calls"] = calls
        return calls

    def _append_recent_backend_call(self, completed: dict[str, Any]) -> None:
        recent = self.payload.setdefault("recent_backend_calls", [])
        if not isinstance(recent, list):
            recent = []
            self.payload["recent_backend_calls"] = recent
        recent.append(completed)
        del recent[:-10]

    def _print_event(self, stage: str, status: str, fields: dict[str, Any]) -> None:
        print(f"[pipeline] {stage}: {status} {_detail_text(fields)}".rstrip(), file=sys.stderr, flush=True)


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


def _call_id(stage: str, item_id: str) -> str:
    return f"{stage}:{item_id}:{int(time.time() * 1000)}"


def _latest_active_call(calls: dict[str, Any]) -> dict[str, Any]:
    if not calls:
        return {}
    latest = max(calls.values(), key=lambda row: str(row.get("started_at_utc") or ""))
    return latest if isinstance(latest, dict) else {}


def _detail_text(fields: dict[str, Any]) -> str:
    keys = (
        "item_id",
        "item_index",
        "total_items",
        "active_backend_call_count",
        "accepted_claim_count",
        "rejected_claim_count",
        "claim_count",
        "relation_count",
        "status",
        "output_path",
        "error",
    )
    parts = []
    for key in keys:
        if key in fields and fields[key] not in (None, ""):
            value = str(fields[key])
            if key == "error" and len(value) > 160:
                value = value[:157] + "..."
            parts.append(f"{key}={value}")
    return " ".join(parts)


def _backend_event_status(status: str) -> str:
    return "backend_completed" if status == "completed" else status
