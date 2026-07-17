from __future__ import annotations

from collections import Counter
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


SECTION_BY_MOVE_TYPE = {
    "answer": "bottom_line",
    "source_weighting": "source_weighting",
    "primary_support": "answer_evidence",
    "quantity_calibration": "answer_evidence",
    "counterweight_disposition": "counterweights",
    "scope_and_update": "counterweights",
    "practical_implication": "practical_implication",
}


def build_decision_argument_contract(canonical_packet: dict[str, Any]) -> dict[str, Any]:
    """Compile analyst judgment into the controlling memo argument contract."""

    packet = canonical_packet if isinstance(canonical_packet, dict) else {}
    moves = _argument_moves(packet)
    sections = _section_arguments(moves)
    report = build_decision_argument_contract_report(packet, moves, sections)
    return _drop_empty(
        {
            "schema_id": "decision_argument_contract_v1",
            "decision_question": packet.get("decision_question"),
            "answer_shape": _dict(packet.get("decision_answer_classification")).get("answer_shape"),
            "selected_answer": _selected_answer(packet),
            "answer_comparison": _answer_comparison(packet),
            "source_hierarchy_thesis": _source_hierarchy_thesis(packet),
            "argument_moves": moves,
            "section_arguments": sections,
            "report": report,
        }
    )


def build_decision_argument_contract_report(
    canonical_packet: dict[str, Any],
    moves: list[dict[str, Any]] | None = None,
    sections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    packet = canonical_packet if isinstance(canonical_packet, dict) else {}
    moves = moves if moves is not None else _argument_moves(packet)
    sections = sections if sections is not None else _section_arguments(moves)
    move_types = Counter(str(row.get("move_type") or "") for row in moves)
    warnings = []
    if not str(_selected_answer(packet).get("answer") or "").strip():
        warnings.append("missing_selected_answer")
    if not any(row.get("move_type") == "primary_support" for row in moves):
        warnings.append("missing_primary_support_move")
    if _has_counterweight_material(packet) and not any(row.get("move_type") == "counterweight_disposition" for row in moves):
        warnings.append("missing_counterweight_disposition_move")
    if _has_practical_material(packet) and not any(row.get("move_type") == "practical_implication" for row in moves):
        warnings.append("missing_practical_implication_move")
    if not any(row.get("move_type") == "source_weighting" for row in moves):
        warnings.append("missing_source_weighting_move")
    generic = [
        row.get("move_id")
        for row in moves
        if _generic_point(row.get("point")) and str(row.get("move_type") or "") not in {"answer"}
    ]
    if generic:
        warnings.append("generic_argument_move_points")
    missing_sections = [
        section_id
        for section_id in ("source_weighting", "answer_evidence", "counterweights", "practical_implication")
        if section_id not in {str(row.get("section_id") or "") for row in sections}
    ]
    if missing_sections:
        warnings.append("missing_section_arguments")
    return {
        "schema_id": "decision_argument_contract_report_v1",
        "status": "ready" if not warnings else "warning",
        "move_count": len(moves),
        "section_argument_count": len(sections),
        "move_type_counts": dict(move_types),
        "generic_move_ids": [value for value in generic if value],
        "missing_section_ids": missing_sections,
        "warnings": warnings,
    }


def compact_decision_argument_contract_for_prompt(contract: dict[str, Any]) -> dict[str, Any]:
    contract = contract if isinstance(contract, dict) else {}
    return _drop_empty(
        {
            "schema_id": contract.get("schema_id"),
            "decision_question": contract.get("decision_question"),
            "selected_answer": contract.get("selected_answer"),
            "answer_comparison": contract.get("answer_comparison"),
            "source_hierarchy_thesis": contract.get("source_hierarchy_thesis"),
            "section_arguments": [
                compact_decision_argument_section_for_prompt(row)
                for row in _list(contract.get("section_arguments"))
                if isinstance(row, dict)
            ],
            "report": _dict(contract.get("report")),
        }
    )


def compact_decision_argument_section_for_prompt(section: dict[str, Any]) -> dict[str, Any]:
    section = section if isinstance(section, dict) else {}
    moves = [
        _drop_empty(
            {
                "move_id": row.get("move_id"),
                "move_type": row.get("move_type"),
                "point": row.get("point"),
                "writing_job": row.get("writing_job"),
                "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:12],
                "source_ids": _string_list(row.get("source_ids"))[:10],
                "quantities": _string_list(row.get("quantities"))[:8],
                "disposition": row.get("disposition"),
                "would_change_if": row.get("would_change_if"),
            }
        )
        for row in _list(section.get("owned_moves"))
        if isinstance(row, dict)
    ]
    return _drop_empty(
        {
            "schema_id": "decision_argument_section_v1",
            "section_id": section.get("section_id"),
            "section_job": section.get("section_job"),
            "reader_question": section.get("reader_question"),
            "why_this_section_matters": section.get("why_this_section_matters"),
            "owned_moves": moves,
            "required_evidence_item_ids": _string_list(section.get("required_evidence_item_ids"))[:18],
            "required_source_ids": _string_list(section.get("required_source_ids"))[:14],
            "required_quantities": _string_list(section.get("required_quantities"))[:12],
        }
    )


def decision_argument_section(contract: dict[str, Any], section_id: str) -> dict[str, Any]:
    target = str(section_id or "").strip()
    for row in _list(_dict(contract).get("section_arguments")):
        if isinstance(row, dict) and str(row.get("section_id") or "") == target:
            return row
    return {}


def argument_move_ids_for_evidence(contract: dict[str, Any]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for move in _list(_dict(contract).get("argument_moves")):
        if not isinstance(move, dict):
            continue
        move_id = str(move.get("move_id") or "").strip()
        if not move_id:
            continue
        for evidence_id in _string_list(move.get("evidence_item_ids")):
            mapping.setdefault(evidence_id, []).append(move_id)
    return {key: _dedupe(values) for key, values in mapping.items()}


def _argument_moves(packet: dict[str, Any]) -> list[dict[str, Any]]:
    spine_moves = _moves_from_analyst_spine(packet)
    fallback_moves = _fallback_moves(packet)
    by_id: dict[str, dict[str, Any]] = {}
    for move in [*spine_moves, *fallback_moves]:
        if not _move_has_content(move):
            continue
        move_id = str(move.get("move_id") or "").strip()
        if not move_id:
            continue
        if move_id not in by_id:
            by_id[move_id] = move
        else:
            by_id[move_id] = _merge_move(by_id[move_id], move)
    ordered = ["answer", "source_weighting", "primary_support", "quantity_calibration", "counterweights", "scope_and_update", "practical_implication"]
    return [by_id[key] for key in ordered if key in by_id] + [
        row for key, row in by_id.items() if key not in set(ordered)
    ]


def _move_has_content(move: dict[str, Any]) -> bool:
    return bool(
        str(move.get("point") or "").strip()
        or _string_list(move.get("evidence_item_ids"))
        or _string_list(move.get("source_ids"))
        or _string_list(move.get("quantities"))
        or str(move.get("disposition") or "").strip()
        or str(move.get("would_change_if") or "").strip()
    )


def _moves_from_analyst_spine(packet: dict[str, Any]) -> list[dict[str, Any]]:
    spine = _dict(packet.get("analyst_decision_spine"))
    rows = []
    for row in _list(spine.get("decision_moves")):
        if not isinstance(row, dict):
            continue
        move_type = _canonical_move_type(row.get("move_type") or row.get("move_id"))
        move_id = str(row.get("move_id") or move_type or "").strip()
        rows.append(
            _drop_empty(
                {
                    "move_id": move_id,
                    "move_type": move_type,
                    "section_id": _canonical_section_id(row.get("primary_section_id"), move_type=move_type),
                    "point": _short_text(row.get("point"), 900),
                    "writing_job": _short_text(row.get("writing_job"), 420),
                    "evidence_item_ids": _string_list(row.get("evidence_item_ids")),
                    "source_ids": _string_list(row.get("source_ids")),
                    "quantities": _string_list(row.get("quantities")),
                }
            )
        )
    return rows


def _fallback_moves(packet: dict[str, Any]) -> list[dict[str, Any]]:
    skeleton = _dict(packet.get("decision_brief_skeleton"))
    balanced = _dict(packet.get("balanced_answer_frame"))
    reasoning = _dict(packet.get("analyst_reasoning_frame"))
    source_hierarchy = _dict(packet.get("source_hierarchy"))
    source_judgments = _list(packet.get("source_weight_judgments"))
    argument_spine = _dict(packet.get("evidence_weighted_argument_spine"))
    steps_by_job = _steps_by_job(argument_spine)
    return [
        _move(
            "answer",
            "answer",
            _first_text(
                [
                    skeleton.get("primary_answer"),
                    skeleton.get("direct_answer"),
                    balanced.get("best_current_read"),
                    reasoning.get("bottom_line"),
                ],
                limit=900,
            ),
            "State the bounded answer as the reference point for the memo.",
            SECTION_BY_MOVE_TYPE["answer"],
        ),
        _move(
            "source_weighting",
            "source_weighting",
            _first_text(
                [
                    source_hierarchy.get("hierarchy_thesis"),
                    _join_source_judgments(source_judgments),
                    balanced.get("source_weighting_thesis"),
                ],
                limit=900,
            ),
            "Explain which sources carry the answer, which calibrate it, and which bound it.",
            SECTION_BY_MOVE_TYPE["source_weighting"],
            support_rows=source_judgments,
        ),
        _move(
            "primary_support",
            "primary_support",
            _first_text(
                [
                    reasoning.get("support_summary"),
                    balanced.get("main_support"),
                    _join_step_points(steps_by_job.get("primary_driver", [])),
                ],
                limit=900,
            ),
            "Explain why the selected answer follows from the driver evidence.",
            SECTION_BY_MOVE_TYPE["primary_support"],
            support_rows=steps_by_job.get("primary_driver", []),
        ),
        _move(
            "quantity_calibration",
            "quantity_calibration",
            _quantity_point(packet, steps_by_job.get("calibrator", [])),
            "Use quantities to calibrate magnitude, threshold, endpoint, or scope.",
            SECTION_BY_MOVE_TYPE["quantity_calibration"],
            support_rows=steps_by_job.get("calibrator", []),
        ),
        _move(
            "counterweights",
            "counterweight_disposition",
            _first_text(
                [
                    reasoning.get("counterweight_weighting"),
                    balanced.get("main_counterweight"),
                    _join_step_points(steps_by_job.get("counterweight_or_boundary", [])),
                ],
                limit=900,
            ),
            "Explain whether limiting evidence overturns, weakens, bounds, or merely contextualizes the answer.",
            SECTION_BY_MOVE_TYPE["counterweight_disposition"],
            support_rows=[*_list(packet.get("counterweight_dispositions")), *steps_by_job.get("counterweight_or_boundary", [])],
            disposition=_first_text([reasoning.get("counterweight_weighting")], limit=420),
        ),
        _move(
            "scope_and_update",
            "scope_and_update",
            _scope_update_point(packet, reasoning, steps_by_job),
            "Name where the answer applies, where it stops applying, and what evidence would change it.",
            SECTION_BY_MOVE_TYPE["scope_and_update"],
            support_rows=[*_list(packet.get("scope_boundaries")), *_list(packet.get("decision_cruxes")), *steps_by_job.get("scope_boundary", []), *steps_by_job.get("crux", [])],
            would_change_if=_short_text("; ".join(_string_list(reasoning.get("reconciled_cruxes"))[:4]), 520),
        ),
        _move(
            "practical_implication",
            "practical_implication",
            _first_text(
                [
                    skeleton.get("practical_implication"),
                    " ".join(_string_list(reasoning.get("practical_implications"))[:3]),
                    _join_step_points(steps_by_job.get("practical_implication", [])),
                ],
                limit=900,
            ),
            "Translate the answer into reader action or use inside the stated scope.",
            SECTION_BY_MOVE_TYPE["practical_implication"],
            support_rows=steps_by_job.get("practical_implication", []),
        ),
    ]


def _move(
    move_id: str,
    move_type: str,
    point: str,
    writing_job: str,
    section_id: str,
    *,
    support_rows: list[Any] | None = None,
    disposition: str = "",
    would_change_if: str = "",
) -> dict[str, Any]:
    support_rows = [row for row in (support_rows or []) if isinstance(row, dict)]
    return _drop_empty(
        {
            "move_id": move_id,
            "move_type": move_type,
            "section_id": section_id,
            "point": _short_text(point, 900),
            "writing_job": _short_text(writing_job, 420),
            "evidence_item_ids": _dedupe(
                [
                    *[value for row in support_rows for value in _string_list(row.get("item_id"))],
                    *[value for row in support_rows for value in _string_list(row.get("evidence_item_ids"))],
                    *[value for row in support_rows for value in _string_list(_dict(row.get("lineage")).get("covered_evidence_item_ids"))],
                ]
            ),
            "source_ids": _dedupe([value for row in support_rows for value in _string_list(row.get("source_ids"))]),
            "quantities": _dedupe([value for row in support_rows for value in _quantity_values(row)]),
            "disposition": _short_text(disposition, 420),
            "would_change_if": _short_text(would_change_if, 520),
        }
    )


def _section_arguments(moves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_section: dict[str, list[dict[str, Any]]] = {}
    for move in moves:
        section_id = _canonical_section_id(move.get("section_id"), move_type=str(move.get("move_type") or ""))
        if not section_id or section_id == "bottom_line":
            continue
        by_section.setdefault(section_id, []).append(move)
    sections = []
    for section_id in ("source_weighting", "answer_evidence", "counterweights", "practical_implication"):
        section_moves = by_section.get(section_id, [])
        if not section_moves:
            continue
        sections.append(
            _drop_empty(
                {
                    "section_id": section_id,
                    "section_job": _section_job(section_id),
                    "reader_question": _reader_question(section_id),
                    "why_this_section_matters": _why_section_matters(section_id),
                    "owned_moves": section_moves,
                    "required_evidence_item_ids": _dedupe(
                        evidence_id
                        for move in section_moves
                        for evidence_id in _string_list(move.get("evidence_item_ids"))
                    ),
                    "required_source_ids": _dedupe(
                        source_id for move in section_moves for source_id in _string_list(move.get("source_ids"))
                    ),
                    "required_quantities": _dedupe(
                        quantity for move in section_moves for quantity in _string_list(move.get("quantities"))
                    ),
                }
            )
        )
    return sections


def _selected_answer(packet: dict[str, Any]) -> dict[str, Any]:
    skeleton = _dict(packet.get("decision_brief_skeleton"))
    balanced = _dict(packet.get("balanced_answer_frame"))
    return _drop_empty(
        {
            "answer": _first_text(
                [
                    skeleton.get("primary_answer"),
                    skeleton.get("direct_answer"),
                    balanced.get("best_current_read"),
                    _dict(packet.get("analyst_reasoning_frame")).get("bottom_line"),
                ],
                limit=900,
            ),
            "secondary_detail": _first_text([skeleton.get("secondary_detail")], limit=420),
            "secondary_detail_type": skeleton.get("secondary_detail_type"),
            "confidence": skeleton.get("confidence") or balanced.get("confidence"),
            "scope": _first_text([skeleton.get("scope"), balanced.get("scope")], limit=520),
        }
    )


def _canonical_section_id(value: Any, *, move_type: str = "") -> str:
    normalized_move_type = str(move_type or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized_move_type in {
        "primary_support",
        "quantity_calibration",
        "counterweight_disposition",
        "scope_and_update",
        "practical_implication",
        "answer",
    }:
        return SECTION_BY_MOVE_TYPE.get(normalized_move_type, "")
    text = str(value or "").strip().lower().replace("-", " ").replace("_", " ")
    if not text and move_type:
        return SECTION_BY_MOVE_TYPE.get(normalized_move_type, "")
    if text in {"source weighting", "how to weight the evidence"} or "weight" in text:
        return "source_weighting"
    if text in {"answer evidence", "why this is the best current read"} or "best current" in text:
        return "answer_evidence"
    if text in {"counterweights", "counterweight", "limiting evidence", "limits", "boundaries"}:
        return "counterweights"
    if "counter" in text or "bound" in text or "limit" in text or "change" in text:
        return "counterweights"
    if text in {"practical implication", "how to use this read"} or "practical" in text or "use this read" in text:
        return "practical_implication"
    if text in {"bottom line", "current read"}:
        return "bottom_line"
    return SECTION_BY_MOVE_TYPE.get(normalized_move_type, str(value or "").strip())


def _canonical_move_type(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "limiting_evidence": "counterweight_disposition",
        "counterweights": "counterweight_disposition",
        "counterweight": "counterweight_disposition",
        "scope": "scope_and_update",
        "scope_boundary": "scope_and_update",
        "source_hierarchy": "source_weighting",
    }
    return aliases.get(text, text)


def _answer_comparison(packet: dict[str, Any]) -> dict[str, Any]:
    classification = _dict(packet.get("decision_answer_classification"))
    reasoning = _dict(packet.get("analyst_reasoning_frame"))
    skeleton = _dict(packet.get("decision_brief_skeleton"))
    options = _string_list(classification.get("question_options"))
    return _drop_empty(
        {
            "plausible_answer_states": options,
            "why_selected_beats_alternatives": _first_text(
                [
                    reasoning.get("support_summary"),
                    skeleton.get("main_reason"),
                    _dict(packet.get("balanced_answer_frame")).get("main_support"),
                ],
                limit=700,
            ),
            "why_not_stronger_or_broader": _first_text(
                [
                    reasoning.get("counterweight_weighting"),
                    skeleton.get("strongest_counterweight"),
                    _dict(packet.get("balanced_answer_frame")).get("main_counterweight"),
                ],
                limit=700,
            ),
        }
    )


def _source_hierarchy_thesis(packet: dict[str, Any]) -> str:
    return _first_text(
        [
            _dict(packet.get("source_hierarchy")).get("hierarchy_thesis"),
            _join_source_judgments(_list(packet.get("source_weight_judgments"))),
        ],
        limit=900,
    )


def _steps_by_job(argument_spine: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in _list(argument_spine.get("steps")):
        if isinstance(row, dict):
            grouped.setdefault(str(row.get("memo_job") or ""), []).append(row)
    return grouped


def _join_step_points(rows: list[dict[str, Any]]) -> str:
    return _short_text(" ".join(str(row.get("point") or "") for row in rows if str(row.get("point") or "").strip()), 900)


def _join_source_judgments(rows: list[Any]) -> str:
    values = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        value = str(row.get("memo_weight_sentence") or row.get("why_weight_this_way") or "").strip()
        if value:
            values.append(value)
    return _short_text(" ".join(values[:4]), 900)


def _quantity_point(packet: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    values = []
    for row in rows:
        values.extend(_quantity_values(row))
    for row in _list(packet.get("mandatory_retention_checklist")):
        if isinstance(row, dict):
            values.extend(_quantity_values(row))
    return _short_text("; ".join(_dedupe(values)[:8]), 900)


def _scope_update_point(packet: dict[str, Any], reasoning: dict[str, Any], steps_by_job: dict[str, list[dict[str, Any]]]) -> str:
    values = [
        *reasoning.get("scope_boundaries", []),
        *reasoning.get("reconciled_cruxes", []),
        _join_step_points(steps_by_job.get("scope_boundary", [])),
        _join_step_points(steps_by_job.get("crux", [])),
    ]
    if not any(str(value or "").strip() for value in values):
        values.extend(str(row.get("claim") or row.get("statement") or "") for row in _list(packet.get("scope_boundaries")) if isinstance(row, dict))
        values.extend(str(row.get("claim") or row.get("statement") or "") for row in _list(packet.get("decision_cruxes")) if isinstance(row, dict))
    return _short_text(" ".join(str(value or "") for value in values if str(value or "").strip()), 900)


def _quantity_values(row: dict[str, Any]) -> list[str]:
    values = []
    for quantity in _list(row.get("quantities")) + _list(row.get("required_quantity_atoms")):
        if isinstance(quantity, dict):
            text = str(quantity.get("value") or quantity.get("retention_phrase") or "").strip()
        else:
            text = str(quantity or "").strip()
        if text:
            values.append(text)
    return _dedupe(values)


def _merge_move(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key in ("point", "writing_job", "disposition", "would_change_if"):
        if not str(merged.get(key) or "").strip() and str(right.get(key) or "").strip():
            merged[key] = right[key]
    for key in ("evidence_item_ids", "source_ids", "quantities"):
        merged[key] = _dedupe([*_string_list(merged.get(key)), *_string_list(right.get(key))])
    if not str(merged.get("section_id") or "").strip() and str(right.get("section_id") or "").strip():
        merged["section_id"] = right["section_id"]
    return _drop_empty(merged)


def _has_counterweight_material(packet: dict[str, Any]) -> bool:
    reasoning = _dict(packet.get("analyst_reasoning_frame"))
    return bool(
        _list(packet.get("counterweight_dispositions"))
        or _string_list(reasoning.get("scope_boundaries"))
        or str(reasoning.get("counterweight_weighting") or "").strip()
    )


def _has_practical_material(packet: dict[str, Any]) -> bool:
    reasoning = _dict(packet.get("analyst_reasoning_frame"))
    skeleton = _dict(packet.get("decision_brief_skeleton"))
    return bool(_string_list(reasoning.get("practical_implications")) or str(skeleton.get("practical_implication") or "").strip())


def _generic_point(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    generic = {
        "the evidence suggests",
        "implementation risk matters",
        "proceed carefully",
        "more research is needed",
    }
    return text in generic or len(text.split()) < 5


def _section_job(section_id: str) -> str:
    return {
        "source_weighting": "Explain which sources should carry the answer and which should mainly bound, calibrate, or contextualize it.",
        "answer_evidence": "Show why the selected answer beats a flatter or stronger reading of the evidence.",
        "counterweights": "Explain what narrows, weakens, or would change the selected answer.",
        "practical_implication": "Translate the bounded answer into action or use inside the stated scope.",
    }.get(section_id, "Explain the relevant decision argument.")


def _reader_question(section_id: str) -> str:
    return {
        "source_weighting": "Which sources should I trust for which part of the answer?",
        "answer_evidence": "Why is this the best current answer rather than a different answer state?",
        "counterweights": "What could make the answer too strong, too broad, or wrong in some cases?",
        "practical_implication": "What should I do with this answer, and when should I update it?",
    }.get(section_id, "What decision-relevant point does this section add?")


def _why_section_matters(section_id: str) -> str:
    return {
        "source_weighting": "Prevents the memo from treating all sources as equally decision-bearing.",
        "answer_evidence": "Gives the reader the positive case for the selected answer.",
        "counterweights": "Keeps uncertainty and boundaries connected to the answer rather than as generic caveats.",
        "practical_implication": "Converts the analysis into reader action, use, or monitoring guidance.",
    }.get(section_id, "Keeps the section tied to the decision.")


def _first_text(values: list[Any], *, limit: int) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return _short_text(text, limit)
    return ""


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", [], {}, None)}
