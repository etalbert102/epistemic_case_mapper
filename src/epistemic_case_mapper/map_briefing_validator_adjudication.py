from __future__ import annotations

import json
import re
from typing import Any, Callable

from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.synthesis_uplift_packet import _parse_json


def adjudicate_section_validation_issues(
    *,
    section_title: str,
    candidate_markdown: str,
    deterministic_issues: list[str],
    validation_context: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_backend: Callable[..., Any] = run_model_backend,
) -> dict[str, Any]:
    """Ask a secondary model whether validator issues are truly blocking."""
    issues = [str(issue).strip() for issue in deterministic_issues if str(issue).strip()]
    if not issues:
        return _report("not_needed", [], [], [], raw="")
    if not backend.strip() or backend.strip() == "prompt":
        return _report("adjudication_unavailable_prompt_backend", [], issues, ["secondary model unavailable"], raw="")
    prompt = _adjudication_prompt(
        section_title=section_title,
        candidate_markdown=candidate_markdown,
        deterministic_issues=issues,
        validation_context=validation_context,
    )
    try:
        result = run_backend(
            prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            response_schema=_adjudication_schema(),
        )
    except Exception as exc:
        return _report("adjudication_unavailable_backend_error", [], issues, [str(exc)], raw="")
    payload = _parse_json(result.text)
    if not isinstance(payload, dict):
        return _report("adjudication_unavailable_parse_error", [], issues, ["judge response was not valid JSON"], raw=result.text)
    return _normalize_adjudication(payload, issues, raw=result.text)


def _adjudication_prompt(
    *,
    section_title: str,
    candidate_markdown: str,
    deterministic_issues: list[str],
    validation_context: dict[str, Any],
) -> str:
    indexed = [{"issue_index": index, "issue": issue} for index, issue in enumerate(deterministic_issues)]
    compact_context = _compact_validation_context(validation_context)
    return (
        "You are a validation adjudicator for one section of a source-grounded decision memo.\n"
        "A deterministic validator flagged candidate blocking issues. Your job is to decide which issues are truly blocking.\n"
        "Use only the validation context and candidate section below as the source of truth.\n"
        "Confirm an issue only if the candidate materially changes the answer, invents facts, drops a required source-grounded obligation, changes required structure, or breaks source grounding.\n"
        "Do not confirm an issue just because wording differs, a citation label is absent but the evidence is faithfully paraphrased, or a heuristic is overly strict.\n"
        "If an issue is real but easy to repair, mark it blocking and give a repair instruction. If it is not actually blocking, mark it not blocking and explain briefly.\n"
        "Return only JSON matching the schema. Preserve issue_index values from the provided list.\n\n"
        f"Section title: {section_title}\n\n"
        "Candidate validator issues:\n"
        f"{json.dumps(indexed, indent=2, ensure_ascii=False)}\n\n"
        "Validation context:\n"
        f"{json.dumps(compact_context, indent=2, ensure_ascii=False)}\n\n"
        "Candidate section:\n"
        f"{candidate_markdown.strip()}\n"
    )


def _compact_validation_context(context: dict[str, Any]) -> dict[str, Any]:
    model_packet = context.get("model_section_packet", {}) if isinstance(context.get("model_section_packet"), dict) else {}
    obligations = context.get("validation_obligations", {}) if isinstance(context.get("validation_obligations"), dict) else {}
    return _drop_empty(
        {
            "original_markdown": _short_text(str(context.get("original_markdown", "")), 1200),
            "model_section_packet": _compact_model_packet(model_packet),
            "validation_obligations": _compact_obligations(obligations),
        }
    )


def _compact_model_packet(packet: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "schema_id",
        "context_source",
        "section_thesis",
        "decision_move",
        "target_shape",
        "section_use_guidance",
        "context_readiness_status",
        "style_instruction",
    }
    compact = {key: packet.get(key) for key in keep if packet.get(key) not in ({}, [], "", None)}
    compact["owned_evidence"] = [_compact_evidence_row(row) for row in _list(packet.get("owned_evidence"))[:7] if isinstance(row, dict)]
    compact["reference_only_evidence"] = [
        _compact_evidence_row(row) for row in _list(packet.get("reference_only_evidence"))[:4] if isinstance(row, dict)
    ]
    compact["section_use_projections"] = [
        _drop_empty(
            {
                "candidate_card_id": row.get("candidate_card_id"),
                "source_role": row.get("source_role"),
                "section_use": row.get("section_use"),
                "expected_section_value": row.get("expected_section_value"),
            }
        )
        for row in _list(packet.get("section_use_projections"))[:8]
        if isinstance(row, dict)
    ]
    compact["must_include_quantities"] = [
        _drop_empty(
            {
                "obligation_id": row.get("obligation_id"),
                "statement": _short_text(str(row.get("statement", "")), 220),
                "key_terms": _list(row.get("key_terms"))[:4],
            }
        )
        for row in _list(packet.get("must_include_quantities"))[:4]
        if isinstance(row, dict)
    ]
    compact["canonical_cruxes"] = [
        _drop_empty(
            {
                "crux": _short_text(str(row.get("crux", "")), 220),
                "current_read": _short_text(str(row.get("current_read", "")), 220),
                "would_change_if": _short_text(str(row.get("would_change_if", "")), 220),
            }
        )
        for row in _list(packet.get("canonical_cruxes"))[:3]
        if isinstance(row, dict)
    ]
    return _drop_empty(compact)


def _compact_obligations(obligations: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "required_evidence": [_compact_evidence_row(row) for row in _list(obligations.get("required_evidence"))[:6] if isinstance(row, dict)],
            "evidence_references": [
                _compact_evidence_row(row) for row in _list(obligations.get("evidence_references"))[:4] if isinstance(row, dict)
            ],
            "required_gaps": [str(row) for row in _list(obligations.get("required_gaps"))[:4]],
            "required_cruxes": [
                _drop_empty(
                    {
                        "crux": _short_text(str(row.get("crux", "")), 220),
                        "current_read": _short_text(str(row.get("current_read", "")), 220),
                        "would_change_if": _short_text(str(row.get("would_change_if", "")), 220),
                    }
                )
                for row in _list(obligations.get("required_cruxes"))[:4]
                if isinstance(row, dict)
            ],
            "required_main_memo_obligations": [
                _drop_empty(
                    {
                        "obligation_id": row.get("obligation_id"),
                        "category": row.get("category"),
                        "statement": _short_text(str(row.get("statement", "")), 260),
                        "search_terms": _list(row.get("search_terms"))[:5],
                    }
                )
                for row in _list(obligations.get("required_main_memo_obligations"))[:6]
                if isinstance(row, dict)
            ],
        }
    )


def _compact_evidence_row(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "candidate_card_id": row.get("candidate_card_id"),
            "claim_ids": _list(row.get("claim_ids"))[:4],
            "source_ids": _list(row.get("source_ids"))[:4],
            "source": row.get("source"),
            "claim": _short_text(str(row.get("claim", "")), 280),
            "source_excerpt": _short_text(str(row.get("source_excerpt", "")), 280),
            "intended_role": row.get("intended_role") or row.get("slot"),
            "quality": row.get("quality"),
            "quantity_values": _list(row.get("quantity_values"))[:4],
            "limitations": _list(row.get("limitations"))[:4],
            "use": row.get("use"),
        }
    )


def _normalize_adjudication(payload: dict[str, Any], issues: list[str], *, raw: str) -> dict[str, Any]:
    assessments = payload.get("issue_assessments", [])
    if not isinstance(assessments, list):
        return _report("adjudication_unavailable_schema_error", [], issues, ["missing issue_assessments"], raw=raw)
    confirmed: list[str] = []
    unconfirmed: list[str] = []
    repair: list[str] = []
    normalized_assessments: list[dict[str, Any]] = []
    seen: set[int] = set()
    for assessment in assessments:
        if not isinstance(assessment, dict):
            continue
        index = _issue_index(assessment)
        if index < 0 or index >= len(issues):
            continue
        seen.add(index)
        issue = issues[index]
        blocking = bool(assessment.get("blocking"))
        row = _drop_empty(
            {
                "issue_index": index,
                "issue": issue,
                "blocking": blocking,
                "reason": _short_text(str(assessment.get("reason", "")), 240),
                "repair_instruction": _short_text(str(assessment.get("repair_instruction", "")), 240),
            }
        )
        normalized_assessments.append(row)
        if blocking:
            confirmed.append(issue)
            if row.get("repair_instruction"):
                repair.append(str(row["repair_instruction"]))
        else:
            unconfirmed.append(issue)
    for index, issue in enumerate(issues):
        if index not in seen:
            unconfirmed.append(issue)
            normalized_assessments.append({"issue_index": index, "issue": issue, "blocking": False, "reason": "No secondary-model confirmation."})
    status = "confirmed_blocking_issues" if confirmed else "no_confirmed_blocking_issues"
    return {
        "schema_id": "section_validation_adjudication_v1",
        "status": status,
        "confirmed_issues": _dedupe(confirmed),
        "unconfirmed_issues": _dedupe(unconfirmed),
        "repair_instructions": _dedupe(repair),
        "issue_assessments": normalized_assessments,
        "raw": raw,
    }


def _issue_index(assessment: dict[str, Any]) -> int:
    try:
        return int(assessment.get("issue_index"))
    except (TypeError, ValueError):
        text = str(assessment.get("issue", ""))
        match = re.search(r"\b(\d+)\b", text)
        return int(match.group(1)) if match else -1


def _report(status: str, confirmed: list[str], unconfirmed: list[str], repair: list[str], *, raw: str) -> dict[str, Any]:
    return {
        "schema_id": "section_validation_adjudication_v1",
        "status": status,
        "confirmed_issues": _dedupe(confirmed),
        "unconfirmed_issues": _dedupe(unconfirmed),
        "repair_instructions": _dedupe(repair),
        "issue_assessments": [
            {"issue_index": index, "issue": issue, "blocking": False, "reason": status}
            for index, issue in enumerate(unconfirmed)
        ],
        "raw": raw,
    }


def _adjudication_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "issue_assessments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "issue_index": {"type": "integer"},
                        "blocking": {"type": "boolean"},
                        "reason": {"type": "string"},
                        "repair_instruction": {"type": "string"},
                    },
                    "required": ["issue_index", "blocking", "reason"],
                },
            }
        },
        "required": ["issue_assessments"],
    }


def _short_text(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    return cleaned if len(cleaned) <= max_chars else cleaned[: max_chars - 3].rstrip(" ,.;") + "..."


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ({}, [], "", None)}


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out
