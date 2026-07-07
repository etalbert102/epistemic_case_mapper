from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_global_plan import build_global_memo_plan


def attach_global_memo_plan(
    scaffold: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> None:
    if canonical_projection_ready(scaffold):
        scaffold.update(deprecated_global_memo_plan_fields())
        return
    result = build_global_memo_plan(
        scaffold,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
    )
    scaffold["global_memo_plan"] = result["plan"]
    scaffold["global_memo_plan_validation"] = result["validation"]
    scaffold["global_memo_plan_prompt"] = result["prompt"]
    scaffold["global_memo_plan_raw"] = result["raw"]


def canonical_projection_ready(scaffold: dict[str, Any]) -> bool:
    readiness = scaffold.get("section_projection_readiness_report", {})
    return isinstance(readiness, dict) and readiness.get("status") in {"ready", "warning"}


def deprecated_global_memo_plan_fields() -> dict[str, Any]:
    return {
        "global_memo_plan": {
            "schema_id": "global_memo_plan_v1",
            "status": "deprecated_by_canonical_spine",
            "method": "canonical_spine_projection_primary",
            "bottom_line_narrative": "",
            "section_plans": [],
            "compression_priorities": [],
            "do_not_repeat": [],
            "style_rules": [],
        },
        "global_memo_plan_validation": {
            "schema_id": "global_memo_plan_validation_v1",
            "status": "deprecated_by_canonical_spine",
            "issues": [],
            "target_word_count": 0,
        },
        "global_memo_plan_prompt": "Skipped: canonical spine projections are the primary section plan.",
        "global_memo_plan_raw": "",
    }
