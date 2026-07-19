from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_decision_logic import naturalize_decision_logic_payload
from epistemic_case_mapper.pipeline.briefing.map_briefing_analyst_schemas import AnalystPacketRefinement
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dict_value as _dict,
    dedupe as _dedupe,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_identity import source_id_alias_map, source_ids_for_labels
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_stage_retry import model_stage_attempts


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
    retry_reports: list[dict[str, Any]] = []
    raw = ""
    payload: Any = {}
    parse_report: dict[str, Any] = {}
    attempts = model_stage_attempts()
    for attempt in range(1, attempts + 1):
        try:
            result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
        except RuntimeError as exc:
            parse_report = build_analyst_packet_refinement_parse_report({}, warning_packet)
            retry_reports.append(_retry_report(attempt, "backend_error", parse_report, str(exc)))
            if attempt < attempts:
                continue
            return {
                "analyst_packet_refinement": _invalid_packet_refinement(synthesis_packet),
                "analyst_packet_refinement_prompt": prompt,
                "analyst_packet_refinement_raw": "",
                "analyst_packet_refinement_parse_report": parse_report,
                "analyst_packet_refinement_report": _report("backend_error", parse_report, issues=[str(exc)], retry_reports=retry_reports),
            }
        raw = result.text
        payload = _extract_json(raw)
        parse_report = build_analyst_packet_refinement_parse_report(payload, warning_packet)
        retry_reports.append(_retry_report(attempt, "accepted" if parse_report.get("valid") else "invalid", parse_report))
        if parse_report.get("valid"):
            break
    if not parse_report.get("valid"):
        return {
            "analyst_packet_refinement": payload if isinstance(payload, dict) else _invalid_packet_refinement(synthesis_packet),
            "analyst_packet_refinement_prompt": prompt,
            "analyst_packet_refinement_raw": raw,
            "analyst_packet_refinement_parse_report": parse_report,
            "analyst_packet_refinement_report": _report(
                "model_output_invalid",
                parse_report,
                issues=["model refinement failed schema or warning accounting checks"],
                retry_reports=retry_reports,
            ),
        }
    parsed = AnalystPacketRefinement.model_validate(payload).model_dump()
    parsed["decision_logic"] = naturalize_decision_logic_payload(_dict(parsed.get("decision_logic")))
    return {
        "analyst_packet_refinement": parsed,
        "analyst_packet_refinement_prompt": prompt,
        "analyst_packet_refinement_raw": raw,
        "analyst_packet_refinement_parse_report": parse_report,
        "analyst_packet_refinement_report": _report("accepted", parse_report, retry_reports=retry_reports),
    }


def _invalid_packet_refinement(synthesis_packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": "analyst_packet_refinement_v1",
        "decision_question": synthesis_packet.get("decision_question"),
        "direct_answer": "",
        "confidence": "not_specified",
        "evidence_groups": [],
        "warning_resolutions": [],
        "decision_logic": {},
        "argument_plan": [],
    }


def build_analyst_packet_refinement_prompt(
    *,
    synthesis_packet: dict[str, Any],
    warning_packet: dict[str, Any],
) -> str:
    source_trail = _list(synthesis_packet.get("source_trail"))
    aliases = source_id_alias_map(source_trail)
    packet = {
        "decision_question": synthesis_packet.get("decision_question"),
        "task": [
            "Produce a direct answer frame and clean memo obligations for warnings.",
            "Produce an ordered argument plan for the memo.",
            "Produce a compact decision_logic object that tells the final writer how to weigh evidence, reconcile cruxes, bound scope, and state practical implications.",
            "Write decision_logic fields as natural analyst guidance in ordinary prose, not as artifact labels, raw claim text, or map metadata.",
            "Use calibrated language for causal and weighting claims.",
            "Return planning JSON for a later writer, with every claim grounded in supplied packet evidence.",
            "Use the evidence hierarchy to answer the decision question in one sentence.",
            "Plan how the memo should integrate the strongest support, strongest counterweight, scope, cruxes, and practical implication.",
            "Explain why the strongest counterweight does or does not change the bottom-line answer.",
            "Reconcile apparent tensions among cruxes instead of listing conflicting claims side by side.",
            "Convert raw warning excerpts into analyst obligations: what the memo should do with the warning.",
        ],
        "current_bottom_line": synthesis_packet.get("bottom_line"),
        "primary_support": _prompt_groups(synthesis_packet.get("primary_reasoning_chain"), limit=5, source_trail=source_trail),
        "counterweights": _prompt_groups(synthesis_packet.get("main_counterweights"), limit=5, source_trail=source_trail),
        "scope": _prompt_groups(synthesis_packet.get("scope_and_applicability"), limit=4, source_trail=source_trail),
        "cruxes": _prompt_groups(synthesis_packet.get("decision_cruxes"), limit=4, source_trail=source_trail),
        "warnings": [
            {
                "warning_id": warning.get("warning_id"),
                "severity": warning.get("severity"),
                "warning_type": warning.get("warning_type"),
                "source_ids": _source_ids(warning, source_trail, aliases),
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
            "decision_logic": {
                "bounded_bottom_line": "specific answer with population, dose/context, and confidence boundary",
                "support_summary": "the load-bearing support in one or two sentences",
                "strongest_counterweight": "the strongest evidence or consideration against the bottom line",
                "counterweight_weighting": "why that counterweight bounds, weakens, or changes the answer",
                "reconciled_cruxes": ["what would change the answer, written without unresolved contradiction"],
                "scope_boundaries": ["population, comparator, dose, duration, or context boundaries"],
                "practical_implications": ["advice/action implications that follow from the weighted read"],
                "do_not_overstate": ["claims outside the supported conclusion"],
            },
            "warning_obligations": [
                {
                    "warning_id": "warning ID copied exactly",
                    "memo_action": "one allowed_memo_action value",
                    "obligation": "clear memo-facing obligation, not a raw excerpt",
                    "rationale": "why the warning should be incorporated, bounded, backgrounded, or omitted",
                    "source_ids": ["source IDs copied from warning when available"],
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
                    "source_ids": ["source IDs to cite"],
                    "transition_from_previous": "how this step should connect to the prior step",
                }
            ],
        },
    }
    return (
        "You are refining an analyst synthesis packet before memo writing.\n"
        "Return a strict JSON object only.\n\n"
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
        "decision_logic": _scaffold_decision_logic(synthesis_packet),
        "warning_obligations": [
            _scaffold_warning_obligation(warning)
            for warning in _list(warning_packet.get("warnings"))
            if isinstance(warning, dict) and warning.get("warning_id")
        ],
        "argument_plan": _scaffold_argument_plan(synthesis_packet, warning_packet),
    }


def _scaffold_decision_logic(synthesis_packet: dict[str, Any]) -> dict[str, Any]:
    support = _first_group_text(synthesis_packet, "primary_reasoning_chain")
    counter = _first_group_text(synthesis_packet, "main_counterweights")
    scope = [_short_text(str(group.get("proposition") or ""), 220) for group in _list(synthesis_packet.get("scope_and_applicability"))[:3] if isinstance(group, dict)]
    cruxes = [_short_text(str(group.get("proposition") or ""), 220) for group in _list(synthesis_packet.get("decision_cruxes"))[:3] if isinstance(group, dict)]
    bottom = str(synthesis_packet.get("bottom_line") or "").strip()
    return naturalize_decision_logic_payload({
        "bounded_bottom_line": bottom or "Answer the decision question from the weighted support and counterweights.",
        "support_summary": support,
        "strongest_counterweight": counter,
        "counterweight_weighting": "Weigh the strongest counterweight against the support; use it to bound the answer if it does not overturn it.",
        "reconciled_cruxes": cruxes,
        "scope_boundaries": scope,
        "practical_implications": [
            "State the practical implication that follows from the weighted read.",
            "Translate scope boundaries into conditions on the recommendation.",
        ],
        "do_not_overstate": _string_list(synthesis_packet.get("must_not_overstate"))[:6],
    })


def _first_group_text(synthesis_packet: dict[str, Any], key: str) -> str:
    for group in _list(synthesis_packet.get(key)):
        if isinstance(group, dict) and str(group.get("proposition") or "").strip():
            return _short_text(str(group.get("proposition") or ""), 260)
    return ""


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


def _prompt_groups(groups: Any, *, limit: int, source_trail: list[Any]) -> list[dict[str, Any]]:
    aliases = source_id_alias_map(source_trail)
    rows = []
    for group in _list(groups)[:limit]:
        if not isinstance(group, dict):
            continue
        rows.append(
            {
                "group_id": group.get("group_id"),
                "proposition": group.get("proposition"),
                "memo_role": group.get("memo_role"),
                "source_ids": _source_ids(group, source_trail, aliases),
                "quantity_values": group.get("quantity_values", []),
                "rationale": group.get("rationale"),
            }
        )
    return rows


def _source_ids(row: dict[str, Any], source_trail: list[Any], aliases: dict[str, str]) -> list[str]:
    ids = _string_list(row.get("source_ids"))
    labels = _string_list(row.get("source_labels"))
    if labels and source_trail:
        ids.extend(source_ids_for_labels(labels, source_trail))
    if not ids and labels:
        ids.extend(source_id for source_id in (aliases.get(label) for label in labels) if source_id)
    return _dedupe(ids)


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
                "required_points": ["Use warning obligations naturally with reader-facing wording."],
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


def _retry_report(attempt: int, status: str, parse_report: dict[str, Any], error: str = "") -> dict[str, Any]:
    return {
        "attempt": attempt,
        "status": status,
        "parse_status": parse_report.get("status"),
        "valid": parse_report.get("valid", False),
        "issues": [str(issue) for issue in parse_report.get("issues", [])],
        **({"error": error} if error else {}),
    }


def _report(
    status: str,
    parse_report: dict[str, Any],
    *,
    issues: list[str] | None = None,
    retry_reports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_id": "analyst_packet_refinement_report_v1",
        "status": status,
        "accepted": status == "accepted",
        "parse_status": parse_report.get("status"),
        "warning_obligation_count": parse_report.get("warning_obligation_count", 0),
        "issues": [*(issues or []), *[str(issue) for issue in parse_report.get("issues", [])]],
        "attempt_count": len(retry_reports or []),
        "retry_reports": retry_reports or [],
    }
