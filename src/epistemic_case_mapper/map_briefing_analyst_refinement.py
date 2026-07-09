from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from epistemic_case_mapper.map_briefing_analyst_schemas import AnalystPacketRefinement
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.model_backends import run_model_backend


def run_analyst_packet_refinement(
    *,
    synthesis_packet: dict[str, Any],
    warning_packet: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    prompt = build_analyst_packet_refinement_prompt(synthesis_packet=synthesis_packet, warning_packet=warning_packet)
    scaffold = deterministic_packet_refinement_scaffold(synthesis_packet=synthesis_packet, warning_packet=warning_packet)
    if backend.strip() == "prompt":
        parse_report = build_analyst_packet_refinement_parse_report(scaffold, warning_packet)
        return {
            "analyst_packet_refinement": scaffold,
            "analyst_packet_refinement_prompt": prompt,
            "analyst_packet_refinement_raw": "",
            "analyst_packet_refinement_parse_report": parse_report,
            "analyst_packet_refinement_report": _report("prompt_backend_scaffold", parse_report),
        }
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        parse_report = build_analyst_packet_refinement_parse_report(scaffold, warning_packet)
        return {
            "analyst_packet_refinement": scaffold,
            "analyst_packet_refinement_prompt": prompt,
            "analyst_packet_refinement_raw": "",
            "analyst_packet_refinement_parse_report": parse_report,
            "analyst_packet_refinement_report": _report("backend_error_scaffold", parse_report, issues=[str(exc)]),
        }
    raw = result.text
    payload = _extract_json(raw)
    parse_report = build_analyst_packet_refinement_parse_report(payload, warning_packet)
    if not parse_report.get("valid"):
        return {
            "analyst_packet_refinement": scaffold,
            "analyst_packet_refinement_prompt": prompt,
            "analyst_packet_refinement_raw": raw,
            "analyst_packet_refinement_parse_report": parse_report,
            "analyst_packet_refinement_report": _report(
                "model_output_invalid_scaffold",
                parse_report,
                issues=["model refinement failed schema or warning accounting checks"],
            ),
        }
    parsed = AnalystPacketRefinement.model_validate(payload).model_dump()
    return {
        "analyst_packet_refinement": parsed,
        "analyst_packet_refinement_prompt": prompt,
        "analyst_packet_refinement_raw": raw,
        "analyst_packet_refinement_parse_report": parse_report,
        "analyst_packet_refinement_report": _report("accepted", parse_report),
    }


def build_analyst_packet_refinement_prompt(
    *,
    synthesis_packet: dict[str, Any],
    warning_packet: dict[str, Any],
) -> str:
    packet = {
        "decision_question": synthesis_packet.get("decision_question"),
        "task": [
            "Produce a direct answer frame and clean memo obligations for warnings.",
            "Produce an ordered argument plan for the memo.",
            "Do not write the memo.",
            "Do not invent evidence or sources.",
            "Use the evidence hierarchy to answer the decision question in one sentence.",
            "Plan how the memo should integrate the strongest support, strongest counterweight, scope, cruxes, and practical implication.",
            "Convert raw warning excerpts into analyst obligations: what the memo should do with the warning.",
        ],
        "current_bottom_line": synthesis_packet.get("bottom_line"),
        "primary_support": _prompt_groups(synthesis_packet.get("primary_reasoning_chain"), limit=5),
        "counterweights": _prompt_groups(synthesis_packet.get("main_counterweights"), limit=5),
        "scope": _prompt_groups(synthesis_packet.get("scope_and_applicability"), limit=4),
        "cruxes": _prompt_groups(synthesis_packet.get("decision_cruxes"), limit=4),
        "warnings": [
            {
                "warning_id": warning.get("warning_id"),
                "severity": warning.get("severity"),
                "warning_type": warning.get("warning_type"),
                "source_labels": warning.get("source_labels", []),
                "claim": _short_text(str(warning.get("claim") or ""), 420),
                "quantity_values": warning.get("quantity_values", []),
            }
            for warning in _list(warning_packet.get("warnings"))
            if isinstance(warning, dict)
        ],
        "allowed_memo_action": [
            "incorporate_as_counterweight",
            "bound_scope_or_confidence",
            "background_context",
            "not_needed_for_memo",
        ],
        "required_output_schema": {
            "schema_id": "analyst_packet_refinement_v1",
            "decision_question": synthesis_packet.get("decision_question"),
            "direct_answer": "one sentence that directly answers the decision question",
            "answer_rationale": "why that answer follows from primary support, counterweights, scope, and cruxes",
            "warning_obligations": [
                {
                    "warning_id": "warning ID copied exactly",
                    "memo_action": "one allowed_memo_action value",
                    "obligation": "clear memo-facing obligation, not a raw excerpt",
                    "rationale": "why the warning should be incorporated, bounded, backgrounded, or omitted",
                    "source_labels": ["source labels copied from warning"],
                    "key_terms": ["short terms that should appear if the memo addresses this obligation"],
                }
            ],
            "argument_plan": [
                {
                    "step_id": "stable step label",
                    "section": "memo section this step belongs in",
                    "writing_goal": "what this paragraph or bullet must accomplish",
                    "required_points": ["specific claims, quantities, caveats, or comparisons to include"],
                    "evidence_item_ids": ["covered evidence IDs or warning IDs from the packet"],
                    "source_labels": ["source labels to cite"],
                    "transition_from_previous": "how this step should connect to the prior step",
                }
            ],
        },
    }
    return (
        "You are refining an analyst synthesis packet before memo writing.\n"
        "Return strict JSON only. Do not return Markdown.\n\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n"
    )


def deterministic_packet_refinement_scaffold(
    *,
    synthesis_packet: dict[str, Any],
    warning_packet: dict[str, Any],
) -> dict[str, Any]:
    direct = str(synthesis_packet.get("bottom_line") or "").strip()
    return {
        "schema_id": "analyst_packet_refinement_v1",
        "decision_question": str(synthesis_packet.get("decision_question") or "").strip(),
        "direct_answer": direct or "Use the analyst synthesis packet to answer the decision question directly.",
        "answer_rationale": "Scaffold only; live model refinement was not accepted.",
        "warning_obligations": [
            _scaffold_warning_obligation(warning)
            for warning in _list(warning_packet.get("warnings"))
            if isinstance(warning, dict) and warning.get("warning_id")
        ],
        "argument_plan": _scaffold_argument_plan(synthesis_packet, warning_packet),
    }


def build_analyst_packet_refinement_parse_report(payload: Any, warning_packet: dict[str, Any]) -> dict[str, Any]:
    expected_warning_ids = _warning_ids(warning_packet)
    try:
        parsed = AnalystPacketRefinement.model_validate(payload)
    except ValidationError as exc:
        return {
            "schema_id": "analyst_packet_refinement_parse_report_v1",
            "status": "invalid_schema",
            "valid": False,
            "errors": _jsonable_errors(exc),
            "expected_warning_ids": expected_warning_ids,
            "missing_warning_ids": expected_warning_ids,
            "unknown_warning_ids": [],
        }
    row_ids = [row.warning_id for row in parsed.warning_obligations]
    missing = sorted(set(expected_warning_ids) - set(row_ids))
    unknown = sorted(set(row_ids) - set(expected_warning_ids))
    issues = [
        *(["missing_warning_obligations"] if missing else []),
        *(["unknown_warning_ids"] if unknown else []),
    ]
    return {
        "schema_id": "analyst_packet_refinement_parse_report_v1",
        "status": "ready" if not issues else "warning",
        "valid": not issues,
        "warning_obligation_count": len(row_ids),
        "expected_warning_ids": expected_warning_ids,
        "missing_warning_ids": missing,
        "unknown_warning_ids": unknown,
        "issues": issues,
    }


def _prompt_groups(groups: Any, *, limit: int) -> list[dict[str, Any]]:
    rows = []
    for group in _list(groups)[:limit]:
        if not isinstance(group, dict):
            continue
        rows.append(
            {
                "group_id": group.get("group_id"),
                "proposition": group.get("proposition"),
                "memo_role": group.get("memo_role"),
                "source_labels": group.get("source_labels", []),
                "quantity_values": group.get("quantity_values", []),
                "rationale": group.get("rationale"),
            }
        )
    return rows


def _scaffold_warning_obligation(warning: dict[str, Any]) -> dict[str, Any]:
    claim = str(warning.get("claim") or "").strip()
    action = "bound_scope_or_confidence" if warning.get("severity") == "critical" else "background_context"
    return {
        "warning_id": str(warning.get("warning_id") or ""),
        "memo_action": action,
        "obligation": _short_text(claim, 260) or "Account for this warning if it changes the memo scope or confidence.",
        "rationale": "Scaffold from warning packet; live model refinement was not accepted.",
        "source_labels": _string_list(warning.get("source_labels")),
        "key_terms": _content_terms(claim)[:6],
    }


def _scaffold_argument_plan(synthesis_packet: dict[str, Any], warning_packet: dict[str, Any]) -> list[dict[str, Any]]:
    steps = []
    for step_id, section, key, goal in (
        ("answer", "Decision Brief", "primary_reasoning_chain", "State the direct answer and summarize the main support."),
        ("counterweight", "Why This Is the Best Current Read", "main_counterweights", "Acknowledge the strongest counterweight and explain how it bounds the answer."),
        ("crux", "What Could Change the Answer", "decision_cruxes", "Name the cruxes that would change the answer."),
        ("scope", "Decision-Relevant Evidence", "scope_and_applicability", "State the population and applicability boundaries."),
    ):
        groups = [group for group in _list(synthesis_packet.get(key)) if isinstance(group, dict)]
        if not groups:
            continue
        steps.append(
            {
                "step_id": step_id,
                "section": section,
                "writing_goal": goal,
                "required_points": [_short_text(str(group.get("proposition") or ""), 220) for group in groups[:3] if group.get("proposition")],
                "evidence_item_ids": [
                    evidence_id
                    for group in groups[:3]
                    for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
                ],
                "source_labels": list(
                    dict.fromkeys(
                        source
                        for group in groups[:3]
                        for source in _string_list(group.get("source_labels"))
                    )
                ),
                "transition_from_previous": "Connect this step to the prior reasoning rather than listing it as an unrelated fact.",
            }
        )
    warning_ids = [
        str(warning.get("warning_id") or "")
        for warning in _list(warning_packet.get("warnings"))
        if isinstance(warning, dict) and str(warning.get("warning_id") or "").strip()
    ]
    if warning_ids:
        steps.append(
            {
                "step_id": "warning_obligations",
                "section": "Decision-Relevant Evidence",
                "writing_goal": "Integrate warning obligations as scope, context, or confidence bounds.",
                "required_points": ["Use warning obligations naturally; do not expose warning IDs."],
                "evidence_item_ids": warning_ids,
                "source_labels": [],
                "transition_from_previous": "Use these as bounds on the answer, not as a separate validation checklist.",
            }
        )
    return steps


def _warning_ids(warning_packet: dict[str, Any]) -> list[str]:
    return [
        str(warning.get("warning_id") or "")
        for warning in _list(warning_packet.get("warnings"))
        if isinstance(warning, dict) and str(warning.get("warning_id") or "").strip()
    ]


def _extract_json(raw: str) -> Any:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        text = match.group(0)
    for candidate in (text, re.sub(r",\s*([\]}])", r"\1", text)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return {}


def _content_terms(text: str) -> list[str]:
    stop = {
        "about",
        "after",
        "also",
        "because",
        "before",
        "between",
        "could",
        "from",
        "have",
        "into",
        "only",
        "should",
        "that",
        "their",
        "there",
        "this",
        "when",
        "where",
        "with",
        "would",
    }
    terms = [
        term.lower()
        for term in re.findall(r"[A-Za-z][A-Za-z-]{3,}", text)
        if term.lower() not in stop
    ]
    return list(dict.fromkeys(terms))


def _jsonable_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {
            "type": str(error.get("type") or ""),
            "loc": [str(part) for part in error.get("loc", [])],
            "msg": str(error.get("msg") or ""),
            "input": repr(error.get("input"))[:240],
        }
        for error in exc.errors()
    ]


def _report(status: str, parse_report: dict[str, Any], *, issues: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema_id": "analyst_packet_refinement_report_v1",
        "status": status,
        "accepted": status == "accepted",
        "parse_status": parse_report.get("status"),
        "warning_obligation_count": parse_report.get("warning_obligation_count", 0),
        "issues": [*(issues or []), *[str(issue) for issue in parse_report.get("issues", [])]],
    }
