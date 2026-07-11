from __future__ import annotations

from typing import Any, Callable


def packet_progress(
    progress: Callable[[str, str, dict[str, Any] | None], None] | None,
    substage: str,
    status: str,
    details: dict[str, Any] | None = None,
) -> None:
    if progress is not None:
        progress("decision_packet_substage", status, {"substage": substage, **(details or {})})


def packet_counts(packet: dict[str, Any]) -> dict[str, Any]:
    bundles = packet.get("evidence_bundles", [])
    retain = packet.get("must_retain_ledger", [])
    return {
        "bundle_count": len(bundles) if isinstance(bundles, list) else 0,
        "retain_item_count": len(retain) if isinstance(retain, list) else 0,
    }


def critique_progress_details(critique: dict[str, Any]) -> dict[str, Any]:
    report = critique.get("report") if isinstance(critique.get("report"), dict) else {}
    adjudication = critique.get("adjudication_report") if isinstance(critique.get("adjudication_report"), dict) else {}
    return {
        "status": report.get("status", "unknown"),
        "method": report.get("method", "unknown"),
        "prompt_chars": len(str(critique.get("prompt") or "")),
        "accepted_count": adjudication.get("accepted_count", 0),
        "warning_only_count": adjudication.get("warning_only_count", 0),
        **parallel_report_details(report),
    }


def refinement_progress_details(refined: dict[str, Any]) -> dict[str, Any]:
    report = refined.get("report") if isinstance(refined.get("report"), dict) else {}
    return {
        "status": report.get("status", "unknown"),
        "method": report.get("method", "unknown"),
        "prompt_chars": len(str(refined.get("prompt") or "")),
        "accepted_count": report.get("applied_update_count", 0),
    }


def parallel_report_details(report: dict[str, Any]) -> dict[str, Any]:
    parallel = report.get("parallelism") if isinstance(report.get("parallelism"), dict) else {}
    return {
        key: parallel[key]
        for key in ("local_shard_count", "local_shards_completed", "verification_task_count", "verification_tasks_completed")
        if key in parallel
    }
