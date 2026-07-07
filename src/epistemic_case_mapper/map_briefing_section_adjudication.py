from __future__ import annotations

from typing import Any, Callable

from epistemic_case_mapper.main_memo_obligations import section_obligations_for_title
from epistemic_case_mapper.map_briefing_decision_brief_last import (
    decision_brief_last_packet,
    deterministic_final_decision_brief,
)
from epistemic_case_mapper.map_briefing_validator_adjudication import adjudicate_section_validation_issues


def adjudicate_section_issues(
    *,
    section_title: str,
    rewritten: str,
    issues: list[str],
    validation_context: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_backend: Callable[..., Any],
) -> dict[str, Any]:
    return adjudicate_section_validation_issues(
        section_title=section_title,
        candidate_markdown=rewritten,
        deterministic_issues=issues,
        validation_context=validation_context,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        run_backend=run_backend,
    )


def adjudicate_decision_brief_issues(
    *,
    contract: dict[str, Any],
    body_memo: str,
    rewritten: str,
    issues: list[str],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_backend: Callable[..., Any],
) -> dict[str, Any]:
    return adjudicate_section_validation_issues(
        section_title="Decision Brief",
        candidate_markdown=rewritten,
        deterministic_issues=issues,
        validation_context={
            "original_markdown": deterministic_final_decision_brief(contract, body_memo),
            "model_section_packet": decision_brief_last_packet(contract, body_memo),
            "validation_obligations": {
                "required_main_memo_obligations": section_obligations_for_title(
                    "Decision Brief",
                    contract.get("_main_memo_obligation_plan", []),
                    limit=4,
                ),
                "answer_frame": contract.get("answer_frame"),
            },
        },
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        run_backend=run_backend,
    )
