from __future__ import annotations

from pathlib import Path
from typing import Any


def publication_state(
    diagnostics: dict[str, Any],
    rewrite_result: dict[str, Any],
) -> dict[str, Any]:
    readiness = _dict(diagnostics.get("final_readiness"))
    semantic_acceptance = _dict(diagnostics.get("semantic_acceptance"))
    rewrite_report = _dict(rewrite_result.get("report"))
    fallback_not_ready = bool(rewrite_report.get("reader_output_fallback")) and (
        rewrite_report.get("reader_output_fallback_decision_ready") is not True
    )
    decision_ready = readiness.get("decision_ready") is True
    decision_ready_with_warnings = readiness.get("decision_ready_with_warnings") is True
    accepted_for_decision_use = semantic_acceptance.get("accepted_for_decision_use") is True
    publication_ready = decision_ready_with_warnings and accepted_for_decision_use and not fallback_not_ready
    if fallback_not_ready:
        status = "fallback_not_decision_ready"
    elif publication_ready:
        status = "published"
    else:
        status = "blocked_not_decision_ready"
    return {
        "status": status,
        "publication_ready": publication_ready,
        "readiness_status": str(readiness.get("status") or "missing"),
        "decision_ready": decision_ready,
        "decision_ready_with_warnings": decision_ready_with_warnings,
        "accepted_for_decision_use": accepted_for_decision_use,
    }


def publication_block_notice(reader_memo_path: Path, publication: dict[str, Any]) -> str:
    return (
        "# Briefing Publication Blocked\n\n"
        f"Status: `{publication.get('status', 'blocked_not_decision_ready')}`\n\n"
        "No official decision briefing was published because the fail-closed readiness gate did not pass. "
        f"The inspectable, non-official memo is available at `{reader_memo_path.name}`.\n\n"
        "Review `final_decision_readiness_report.json`, `memo_semantic_acceptance_report.json`, and "
        "`briefing_validation_report.json` before publication.\n"
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
