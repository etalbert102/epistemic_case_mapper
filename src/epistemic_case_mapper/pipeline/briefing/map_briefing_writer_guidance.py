from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


def build_writer_guidance_packet(
    *,
    critique_adjudication: dict[str, Any],
    sufficiency_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile packet critique output into memo-writer guidance.

    Packet critique often produces useful semantic warnings even when it does
    not produce accepted packet edits. This artifact preserves those warnings
    as writer-facing obligations and traps without changing packet semantics.
    """

    adjudication = critique_adjudication if isinstance(critique_adjudication, dict) else {}
    sufficiency = sufficiency_report if isinstance(sufficiency_report, dict) else {}
    guidance_rows = _guidance_rows(adjudication, sufficiency)
    obligations = [row for row in guidance_rows if row.get("memo_obligation_ready")]
    return {
        "schema_id": "writer_guidance_packet_v1",
        "method": "packet_critique_to_writer_guidance",
        "status": "ready" if guidance_rows else "empty",
        "judgment": adjudication.get("judgment", "unknown"),
        "accepted_packet_edit_count": int(adjudication.get("accepted_count", 0) or 0),
        "warning_or_guidance_count": len(guidance_rows),
        "required_obligation_count": len(obligations),
        "model_instruction_count": sum(1 for row in guidance_rows if row.get("model_instruction_ready")),
        "guidance": guidance_rows,
        "writer_obligations": obligations,
        "summary": _summary(guidance_rows),
    }


def attach_writer_guidance(packet: dict[str, Any], guidance_packet: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(packet, dict):
        return packet
    guidance = guidance_packet if isinstance(guidance_packet, dict) else {}
    if guidance.get("schema_id") == "writer_guidance_packet_v1":
        packet["writer_guidance_packet"] = guidance
    return packet


def compact_writer_guidance_for_model(guidance_packet: dict[str, Any] | None, *, limit: int = 10) -> dict[str, Any]:
    guidance = guidance_packet if isinstance(guidance_packet, dict) else {}
    rows = [row for row in _list(guidance.get("guidance")) if isinstance(row, dict) and row.get("model_instruction_ready")]
    if not rows:
        rows = _list(guidance.get("writer_obligations"))
    compact = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        compact.append(
            {
                "guidance_id": row.get("guidance_id"),
                "guidance_type": row.get("guidance_type"),
                "instruction": row.get("instruction"),
                "why_it_matters": row.get("why_it_matters"),
                "source_labels": _string_list(row.get("source_labels"))[:4],
                "target_ids": _string_list(row.get("target_ids"))[:6],
                "validation_terms": _string_list(row.get("validation_terms"))[:8],
            }
        )
    return {
        "schema_id": "compact_writer_guidance_v1",
        "status": guidance.get("status", "empty"),
        "judgment": guidance.get("judgment", "unknown"),
        "guidance": compact[:limit],
    }


def writer_guidance_memo_obligations(guidance_packet: dict[str, Any] | None, *, start_index: int = 1) -> list[dict[str, Any]]:
    guidance = guidance_packet if isinstance(guidance_packet, dict) else {}
    obligations = []
    for row in _list(guidance.get("writer_obligations")):
        if not isinstance(row, dict):
            continue
        if not row.get("memo_obligation_ready"):
            continue
        instruction = str(row.get("instruction") or "").strip()
        if not instruction:
            continue
        obligations.append(
            {
                "obligation_id": f"memo_obligation_{start_index + len(obligations):03d}",
                "obligation_type": _obligation_type(row),
                "required": True,
                "role": "critique_writer_guidance",
                "statement": instruction,
                "prose_instruction": _prose_instruction(row),
                "source_labels": _string_list(row.get("source_labels")),
                "source_label": _first(_string_list(row.get("source_labels"))),
                "quantities": [],
                "guidance_ids": [str(row.get("guidance_id") or "")],
                "target_ids": _string_list(row.get("target_ids")),
                "validation_mode": "claim_terms",
                "validation_terms": _string_list(row.get("validation_terms"))[:10],
                "audit_claim": instruction,
            }
        )
    return obligations


def _guidance_rows(adjudication: dict[str, Any], sufficiency: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(_rows_from_reader_guidance(_list(adjudication.get("reader_facing_guidance"))))
    rows.extend(
        _rows_from_issue_list(
            "answer_frame",
            _list(adjudication.get("answer_frame_issues")) + _list(adjudication.get("bad_answer_frame_risks")),
            default_instruction="Make the bottom-line answer direct, bounded, and source-backed.",
            required=True,
        )
    )
    rows.extend(
        _rows_from_issue_list(
            "synthesis_trap",
            _list(adjudication.get("misleading_synthesis_risks")),
            default_instruction="Prevent this synthesis risk from misleading the final memo.",
            required=True,
        )
    )
    rows.extend(
        _rows_from_issue_list(
            "source_quality_or_sufficiency",
            _list(adjudication.get("insufficiency_warnings")) + _list(adjudication.get("claim_quality_issues")),
            default_instruction="Surface this source or claim limitation when it affects confidence or scope.",
            required=True,
        )
    )
    rows.extend(
        _rows_from_issue_list(
            "section_routing",
            _list(adjudication.get("section_routing_issues")) + _list(adjudication.get("section_plan_risks")),
            default_instruction="Route this evidence to the memo section where it changes the decision read.",
            required=False,
        )
    )
    rows.extend(
        _rows_from_issue_list(
            "missing_decision_function",
            _list(adjudication.get("missing_decision_functions")),
            default_instruction="Address this missing decision function if the source packet supports it.",
            required=True,
        )
    )
    rows.extend(_rows_from_sufficiency(sufficiency))
    deduped = _dedupe_guidance(rows)
    for index, row in enumerate(deduped, start=1):
        row["guidance_id"] = f"writer_guidance_{index:03d}"
        _classify_guidance_row(row)
    return deduped[:24]


def _rows_from_reader_guidance(items: list[Any]) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        instruction = str(item.get("instruction") or item.get("guidance") or item.get("recommended_action") or "").strip()
        why = str(item.get("why_it_matters") or item.get("rationale") or item.get("reason") or "").strip()
        if not instruction and why:
            instruction = why
        if not instruction:
            continue
        rows.append(
            {
                "guidance_type": str(item.get("guidance_type") or "reader_facing_guidance"),
                "required": item.get("required", True) is not False,
                "instruction": _short_text(instruction, 360),
                "why_it_matters": _short_text(why, 300),
                "target_ids": _target_ids(item),
                "source_labels": _string_list(item.get("source_labels")),
                "validation_terms": _reader_guidance_terms(item, instruction, why),
                "source": "packet_critique_reader_guidance",
            }
        )
    return rows


def _reader_guidance_terms(item: dict[str, Any], instruction: str, why: str) -> list[str]:
    terms = _string_list(item.get("validation_terms"))
    return _validation_terms(*terms, instruction, why) if terms else _validation_terms(instruction, why)


def _rows_from_issue_list(
    guidance_type: str,
    issues: list[Any],
    *,
    default_instruction: str,
    required: bool,
) -> list[dict[str, Any]]:
    rows = []
    for issue in issues:
        text = _issue_text(issue)
        if not text:
            continue
        rec = _recommended_action(issue)
        instruction = _short_text(rec or f"{default_instruction} {text}", 360)
        rows.append(
            {
                "guidance_type": guidance_type,
                "required": required,
                "instruction": instruction,
                "why_it_matters": _short_text(text, 300),
                "target_ids": _target_ids(issue),
                "source_labels": _string_list(_dict(issue).get("source_labels")),
                "validation_terms": _validation_terms(instruction, text),
                "source": _dict(issue).get("source", "packet_critique"),
            }
        )
    return rows


def _rows_from_sufficiency(sufficiency: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for issue in _string_list(sufficiency.get("issues")):
        if not issue:
            continue
        rows.append(
            {
                "guidance_type": "packet_sufficiency",
                "required": issue in {"top_quantities_missing_from_must_retain", "compression_loss"},
                "instruction": _short_text(f"Account for packet sufficiency warning: {issue}.", 240),
                "why_it_matters": "The packet quality gate flagged a possible evidence-retention or compression problem.",
                "target_ids": [],
                "source_labels": [],
                "validation_terms": _validation_terms(issue, "packet sufficiency warning"),
                "source": "packet_sufficiency_report",
            }
        )
    return rows


def _classify_guidance_row(row: dict[str, Any]) -> None:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("instruction", "why_it_matters", "guidance_type", "source")
    ).lower()
    guidance_type = str(row.get("guidance_type") or "")
    row["model_instruction_ready"] = True
    row["memo_obligation_ready"] = _reader_facing_guidance(text, guidance_type=guidance_type)
    row["guidance_use"] = "memo_obligation" if row["memo_obligation_ready"] else "writer_instruction"


def _reader_facing_guidance(text: str, *, guidance_type: str) -> bool:
    if guidance_type == "reader_facing_guidance" or "reader_guidance" in guidance_type:
        return True
    if "distinction" in guidance_type or "caveat" in guidance_type:
        return True
    if guidance_type in {"packet_sufficiency", "section_routing", "answer_frame"}:
        return False
    if _meta_instruction(text):
        return False
    concrete_terms = (
        "distinguish",
        "surface",
        "explain",
        "acknowledge",
        "state",
        "clarify",
        "calibrate",
        "caveat",
        "limitation",
        "quality",
        "guidance",
        "direct outcome",
        "confidence",
        "scope",
    )
    return any(term in text for term in concrete_terms)


def _meta_instruction(text: str) -> bool:
    meta_terms = (
        "answer frame",
        "spine field",
        "evidence-backed spine",
        "plain text before synthesis",
        "normalize the answer",
        "packet sufficiency",
        "compression_loss",
        "top_quantities_missing",
        "target id",
        "bundle id",
        "section plan",
    )
    return any(term in text for term in meta_terms)


def _issue_text(issue: Any) -> str:
    if isinstance(issue, str):
        return issue.strip()
    if not isinstance(issue, dict):
        return ""
    for key in ("critique", "risk", "description", "issue", "reason", "warning", "comment", "decision_function"):
        text = str(issue.get(key) or "").strip()
        if text:
            return text
    return ""


def _recommended_action(issue: Any) -> str:
    if not isinstance(issue, dict):
        return ""
    return str(issue.get("recommended_action") or issue.get("prose_instruction") or "").strip()


def _target_ids(issue: Any) -> list[str]:
    if not isinstance(issue, dict):
        return []
    return _dedupe(
        [
            *_string_list(issue.get("target_ids")),
            *_string_list(issue.get("affected_bundle_ids")),
            str(issue.get("target_id") or "").strip(),
            str(issue.get("bundle_id") or "").strip(),
            str(issue.get("source_id") or "").strip(),
        ]
    )


def _validation_terms(*texts: str) -> list[str]:
    stop = {
        "about",
        "action",
        "answer",
        "claim",
        "decision",
        "evidence",
        "final",
        "memo",
        "packet",
        "source",
        "this",
        "when",
        "where",
        "which",
        "write",
    }
    terms = []
    for text in texts:
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", str(text).lower()):
            if token not in stop:
                terms.append(token)
    return _dedupe(terms)[:10]


def _dedupe_guidance(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        key = (
            tuple(_string_list(row.get("target_ids"))),
            " ".join(_string_list(row.get("validation_terms"))[:5]),
            _short_text(str(row.get("instruction") or ""), 120).lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("guidance_type") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return {"guidance_type_counts": counts}


def _obligation_type(row: dict[str, Any]) -> str:
    guidance_type = str(row.get("guidance_type") or "")
    if guidance_type == "answer_frame":
        return "must_answer_directly"
    if guidance_type == "synthesis_trap":
        return "must_avoid_synthesis_trap"
    if guidance_type == "source_quality_or_sufficiency":
        return "must_surface_evidence_quality"
    if guidance_type == "reader_facing_guidance" or "distinction" in guidance_type or "caveat" in guidance_type:
        return "must_apply_reader_guidance"
    if guidance_type == "missing_decision_function":
        return "must_address_decision_function"
    return "must_apply_critique_guidance"


def _prose_instruction(row: dict[str, Any]) -> str:
    guidance_type = str(row.get("guidance_type") or "")
    if guidance_type == "answer_frame":
        return "Use this to shape the opening answer and confidence, not as visible process commentary."
    if guidance_type == "synthesis_trap":
        return "Use this to preserve a tension, caveat, or distinction that could otherwise be smoothed over."
    if guidance_type == "source_quality_or_sufficiency":
        return "Use this to calibrate confidence, scope, or source-quality language."
    return "Use this only when it improves the decision reasoning."


def _first(values: list[str]) -> str:
    return values[0] if values else ""
