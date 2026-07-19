from __future__ import annotations

import os
from typing import Any


def final_polish_enabled() -> bool:
    mode = os.environ.get("ECM_FINAL_POLISH_MODE", "off").strip().lower()
    return bool(os.environ.get("ECM_FINAL_POLISH_BACKEND", "").strip()) or mode in {"on", "always", "true", "1"}


def disabled_final_polish_result(memo: str) -> dict[str, Any]:
    return {
        "memo": memo,
        "prompt": "",
        "raw": "",
        "repair_prompt": "",
        "repair_raw": "",
        "report": {
            "schema_id": "memo_ready_final_polish_report_v1",
            "method": "validated_decision_editor_rewrite",
            "status": "disabled_by_default",
            "accepted": True,
            "applied": False,
            "acceptance_basis": "optional_stage_disabled",
            "issues": [],
        },
    }


def run_optional_final_polish(
    memo: str,
    packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    if not final_polish_enabled():
        return disabled_final_polish_result(memo)
    from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_finalization import run_memo_ready_final_polish

    return run_memo_ready_final_polish(
        memo,
        packet,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
    )
