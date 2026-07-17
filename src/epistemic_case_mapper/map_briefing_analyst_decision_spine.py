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


def build_analyst_decision_spine(packet: dict[str, Any], writer_interface: dict[str, Any]) -> dict[str, Any]:
    """Compile model adjudication into the controlling writer-facing decision plan."""

    packet = packet if isinstance(packet, dict) else {}
    interface = writer_interface if isinstance(writer_interface, dict) else {}
    answer_frame = _dict(interface.get("answer_frame"))
    logic = _dict(packet.get("analyst_decision_logic"))
    support_rows = _support_rows(interface)
    counterweight_rows = _counterweight_rows(interface)
    quantity_lookup = _quantity_binding_lookup(packet)
    quantity_rows = _quantity_rows(packet, interface, quantity_lookup=quantity_lookup)
    source_weight_moves = _source_weight_moves(packet)
    section_plan = _section_plan(
        packet=packet,
        interface=interface,
        support_rows=support_rows,
        counterweight_rows=counterweight_rows,
        quantity_rows=quantity_rows,
        source_weight_moves=source_weight_moves,
        quantity_lookup=quantity_lookup,
    )
    moves = _decision_moves(
        packet=packet,
        answer_frame=answer_frame,
        logic=logic,
        support_rows=support_rows,
        counterweight_rows=counterweight_rows,
        quantity_rows=quantity_rows,
        source_weight_moves=source_weight_moves,
        section_plan=section_plan,
        quantity_lookup=quantity_lookup,
    )
    return {
        "schema_id": "analyst_decision_spine_v1",
        "method": "deterministic_projection_from_post_adjudication_model_judgments",
        "decision_question": packet.get("decision_question") or interface.get("decision_question"),
        "direct_answer": _first_text(
            [
                interface.get("bottom_line"),
                answer_frame.get("direct_answer"),
                _dict(packet.get("answer_spine")).get("default_read"),
                logic.get("bounded_bottom_line"),
            ],
            limit=900,
        ),
        "confidence": interface.get("confidence") or answer_frame.get("confidence"),
        "controlling_thesis": _controlling_thesis(answer_frame, logic, source_weight_moves),
        "source_weight_moves": source_weight_moves,
        "decision_moves": moves,
        "section_plan": section_plan,
        "mandatory_quantities": quantity_rows,
        "update_triggers": _update_triggers(packet, logic),
        "quality_report": _quality_report(moves, section_plan, support_rows, counterweight_rows, quantity_rows, source_weight_moves),
    }


def compact_analyst_decision_spine_for_prompt(spine: dict[str, Any]) -> dict[str, Any]:
    spine = spine if isinstance(spine, dict) else {}
    return _drop_empty(
        {
            "schema_id": spine.get("schema_id"),
            "decision_question": spine.get("decision_question"),
            "direct_answer": spine.get("direct_answer"),
            "confidence": spine.get("confidence"),
            "controlling_thesis": spine.get("controlling_thesis"),
            "source_weight_moves": _list(spine.get("source_weight_moves"))[:8],
            "decision_moves": _list(spine.get("decision_moves"))[:12],
            "section_plan": _list(spine.get("section_plan")),
            "mandatory_quantities": _list(spine.get("mandatory_quantities"))[:12],
            "update_triggers": _string_list(spine.get("update_triggers"))[:8],
            "quality_report": _dict(spine.get("quality_report")),
        }
    )


def section_spine_for_prompt(spine: dict[str, Any], section_id: str) -> dict[str, Any]:
    spine = spine if isinstance(spine, dict) else {}
    section_id = str(section_id or "").strip()
    section = next(
        (row for row in _list(spine.get("section_plan")) if isinstance(row, dict) and row.get("section_id") == section_id),
        {},
    )
    owned_move_ids = set(_string_list(_dict(section).get("owned_move_ids")))
    moves = [
        row
        for row in _list(spine.get("decision_moves"))
        if isinstance(row, dict) and str(row.get("move_id") or "") in owned_move_ids
    ]
    return _drop_empty(
        {
            "schema_id": "analyst_section_decision_spine_v1",
            "section_id": section_id,
            "section": section,
            "owned_moves": moves,
        }
    )


def _decision_moves(
    *,
    packet: dict[str, Any],
    answer_frame: dict[str, Any],
    logic: dict[str, Any],
    support_rows: list[dict[str, Any]],
    counterweight_rows: list[dict[str, Any]],
    quantity_rows: list[dict[str, Any]],
    source_weight_moves: list[dict[str, Any]],
    section_plan: list[dict[str, Any]],
    quantity_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    section_by_move = {
        move_id: str(section.get("section_id") or "")
        for section in section_plan
        for move_id in _string_list(section.get("owned_move_ids"))
    }
    moves = [
        _move(
            "answer",
            "answer",
            _first_text([answer_frame.get("direct_answer"), logic.get("bounded_bottom_line")], limit=900),
            "State the bounded answer, scope, and confidence as the reference point for the rest of the memo.",
            section_by_move=section_by_move,
            support_rows=[],
            quantity_lookup=quantity_lookup,
        ),
        _move(
            "source_weighting",
            "source_weighting",
            _source_weighting_point(source_weight_moves),
            "Explain which sources carry the answer, which calibrate it, and which mainly bound it.",
            section_by_move=section_by_move,
            support_rows=source_weight_moves,
            quantity_lookup=quantity_lookup,
        ),
        _move(
            "primary_support",
            "primary_support",
            _first_text([answer_frame.get("main_support"), logic.get("support_summary"), _join_claims(support_rows[:2])], limit=900),
            "Show why the current answer is the best read of the source hierarchy.",
            section_by_move=section_by_move,
            support_rows=support_rows,
            quantity_lookup=quantity_lookup,
        ),
        _move(
            "quantity_calibration",
            "quantity_calibration",
            _quantity_point(quantity_rows),
            "Use only the decision-relevant quantities to calibrate magnitude, threshold, endpoint, or scope.",
            section_by_move=section_by_move,
            support_rows=quantity_rows,
            quantity_lookup=quantity_lookup,
        ),
        _move(
            "counterweights",
            "counterweight_disposition",
            _first_text([answer_frame.get("main_counterweight"), logic.get("counterweight_weighting"), _join_claims(counterweight_rows[:2])], limit=900),
            "Explain whether the limiting evidence overturns, weakens, bounds, or merely contextualizes the answer.",
            section_by_move=section_by_move,
            support_rows=counterweight_rows,
            quantity_lookup=quantity_lookup,
        ),
        _move(
            "scope_and_update",
            "scope_and_update",
            _scope_point(packet, answer_frame, logic),
            "Name where the answer applies, where it stops applying, and what evidence would change it.",
            section_by_move=section_by_move,
            support_rows=[],
            quantity_lookup=quantity_lookup,
        ),
        _move(
            "practical_implication",
            "practical_implication",
            _first_text([answer_frame.get("decision_application"), *_string_list(logic.get("practical_implications"))], limit=900),
            "Translate the answer into action inside the stated scope.",
            section_by_move=section_by_move,
            support_rows=_list(packet.get("practical_implication_cards")),
            quantity_lookup=quantity_lookup,
        ),
    ]
    return [move for move in moves if move.get("point") or move.get("evidence_item_ids") or move.get("source_ids")]


def _move(
    move_id: str,
    move_type: str,
    point: str,
    writing_job: str,
    *,
    section_by_move: dict[str, str],
    support_rows: list[dict[str, Any]],
    quantity_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return _drop_empty(
        {
            "move_id": move_id,
            "move_type": move_type,
            "primary_section_id": section_by_move.get(move_id),
            "point": point,
            "writing_job": writing_job,
            "evidence_item_ids": _dedupe(
                [
                    *[item_id for row in support_rows for item_id in _string_list(row.get("item_id"))],
                    *[item_id for row in support_rows for item_id in _string_list(row.get("evidence_item_ids"))],
                    *[item_id for row in support_rows for item_id in _string_list(_dict(row.get("lineage")).get("covered_evidence_item_ids"))],
                ]
            ),
            "source_ids": _dedupe([source_id for row in support_rows for source_id in _string_list(row.get("source_ids"))]),
            "source_labels": _dedupe([label for row in support_rows for label in _string_list(row.get("source_labels"))]),
            "quantities": _dedupe([quantity for row in support_rows for quantity in _quantity_surfaces(row, quantity_lookup=quantity_lookup)]),
        }
    )


def _section_plan(
    *,
    packet: dict[str, Any],
    interface: dict[str, Any],
    support_rows: list[dict[str, Any]],
    counterweight_rows: list[dict[str, Any]],
    quantity_rows: list[dict[str, Any]],
    source_weight_moves: list[dict[str, Any]],
    quantity_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    sections = [
        (
            "source_weighting",
            "How to Weight the Evidence",
            "Give the reader the source hierarchy before the evidence argument.",
            ["source_weighting"],
            source_weight_moves,
        ),
        (
            "answer_evidence",
            "Why This Is the Best Current Read",
            "Use the support and calibrators to explain why the answer follows.",
            ["primary_support", "quantity_calibration"],
            [*support_rows, *quantity_rows],
        ),
        (
            "counterweights",
            "What Could Change or Bound the Answer",
            "Use counterweights, scope boundaries, and update triggers to bound the answer.",
            ["counterweights", "scope_and_update"],
            counterweight_rows,
        ),
        (
            "practical_implication",
            "Practical Implication",
            "Translate the bounded answer into action guidance.",
            ["practical_implication"],
            _list(interface.get("practical_implication_cards")),
        ),
    ]
    rows = []
    for section_id, heading, writing_job, move_ids, evidence_rows in sections:
        rows.append(
            _drop_empty(
                {
                    "section_id": section_id,
                    "heading": heading,
                    "writing_job": writing_job,
                    "owned_move_ids": move_ids,
                    "owned_evidence_item_ids": _dedupe(
                        [
                            *[item_id for row in evidence_rows for item_id in _string_list(row.get("item_id"))],
                            *[item_id for row in evidence_rows for item_id in _string_list(row.get("evidence_item_ids"))],
                        ]
                    ),
                    "required_quantities": _dedupe([quantity for row in evidence_rows for quantity in _quantity_surfaces(row, quantity_lookup=quantity_lookup)]),
                    "source_ids": _dedupe([source_id for row in evidence_rows for source_id in _string_list(row.get("source_ids"))]),
                    "source_labels": _dedupe([label for row in evidence_rows for label in _string_list(row.get("source_labels"))]),
                }
            )
        )
    return rows


def _support_rows(interface: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in _list(interface.get("support_that_drives_answer")) if isinstance(row, dict)]
    if rows:
        return rows[:6]
    return [
        row
        for row in _list(interface.get("decision_evidence_table"))
        if isinstance(row, dict) and str(row.get("role") or "") in {"strongest_support", "quantitative_anchor"}
    ][:6]


def _counterweight_rows(interface: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in _list(interface.get("counterweights_and_disposition")) if isinstance(row, dict)]
    if rows:
        return rows[:8]
    return [
        row
        for row in _list(interface.get("decision_evidence_table"))
        if isinstance(row, dict) and str(row.get("role") or "") in {"strongest_counterweight", "scope_boundary", "decision_crux"}
    ][:8]


def _quantity_rows(packet: dict[str, Any], interface: dict[str, Any], *, quantity_lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in _list(interface.get("quantity_anchors")):
        if not isinstance(row, dict):
            continue
        binding = _quantity_binding_for_row(row, quantity_lookup)
        rows.append(
            _drop_empty(
                {
                    "item_id": row.get("evidence_item_id"),
                    "value": binding.get("value") or row.get("value"),
                    "interpretation": binding.get("retention_phrase") or binding.get("interpretation") or row.get("interpretation"),
                    "source_ids": binding.get("source_ids") or row.get("source_ids"),
                    "source_labels": binding.get("source_labels") or row.get("source_labels"),
                    "role": row.get("role"),
                }
            )
        )
    return rows[:12]


def _source_weight_moves(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in _list(packet.get("analyst_source_weight_judgments")):
        if not isinstance(row, dict):
            continue
        rows.append(
            _drop_empty(
                {
                    "source_ids": row.get("source_ids"),
                    "source_labels": row.get("source_labels"),
                    "main_use": row.get("main_use"),
                    "confidence_effect": row.get("confidence_effect"),
                    "point": _first_text([row.get("memo_weight_sentence"), row.get("why_weight_this_way")], limit=520),
                    "reader_facing_limit": _short_text(row.get("reader_facing_limit"), 360),
                    "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:12],
                }
            )
        )
    return rows[:10]


def _controlling_thesis(answer_frame: dict[str, Any], logic: dict[str, Any], source_weight_moves: list[dict[str, Any]]) -> str:
    parts = [
        _first_text([answer_frame.get("direct_answer"), logic.get("bounded_bottom_line")], limit=520),
        _first_text([answer_frame.get("main_support"), logic.get("support_summary")], limit=420),
        _first_text([answer_frame.get("main_counterweight"), logic.get("counterweight_weighting")], limit=420),
    ]
    if source_weight_moves:
        parts.append(_short_text(source_weight_moves[0].get("point"), 360))
    return _short_text(" ".join(part for part in parts if part), 1400)


def _source_weighting_point(source_weight_moves: list[dict[str, Any]]) -> str:
    if not source_weight_moves:
        return ""
    drivers = [row.get("point") for row in source_weight_moves if str(row.get("main_use") or "") in {"drives_answer", "calibrates_magnitude"}]
    bounds = [row.get("point") for row in source_weight_moves if str(row.get("main_use") or "") in {"bounds_answer", "defines_scope", "identifies_crux"}]
    return _first_text(
        [
            " ".join([_first_text(drivers, limit=420), _first_text(bounds, limit=420)]),
            source_weight_moves[0].get("point"),
        ],
        limit=900,
    )


def _quantity_point(quantity_rows: list[dict[str, Any]]) -> str:
    if not quantity_rows:
        return ""
    rendered = []
    for row in quantity_rows[:5]:
        value = str(row.get("value") or "").strip()
        interpretation = str(row.get("interpretation") or "").strip()
        rendered.append(f"{value}: {interpretation}" if interpretation else value)
    return _short_text("; ".join(rendered), 900)


def _scope_point(packet: dict[str, Any], answer_frame: dict[str, Any], logic: dict[str, Any]) -> str:
    triggers = _update_triggers(packet, logic)
    return _short_text(
        " ".join(
            [
                str(answer_frame.get("scope_note") or ""),
                " ".join(_string_list(logic.get("scope_boundaries"))[:3]),
                " ".join(triggers[:3]),
            ]
        ),
        900,
    )


def _update_triggers(packet: dict[str, Any], logic: dict[str, Any]) -> list[str]:
    return _dedupe(
        [
            *_string_list(logic.get("reconciled_cruxes")),
            *_string_list(_dict(packet.get("decision_memo_contract")).get("missing_evidence")),
            *_string_list(_dict(packet.get("writer_packet")).get("missing_evidence")),
        ]
    )[:8]


def _join_claims(rows: list[dict[str, Any]]) -> str:
    return _short_text(" ".join(str(row.get("claim") or row.get("point") or row.get("statement") or "") for row in rows), 900)


def _quantity_surfaces(row: dict[str, Any], *, quantity_lookup: dict[str, dict[str, Any]] | None = None) -> list[str]:
    quantity_lookup = quantity_lookup or {}
    rows = []
    if row.get("value"):
        binding = _quantity_binding_for_row(row, quantity_lookup)
        value = str(binding.get("value") or row.get("value") or "").strip()
        interpretation = str(binding.get("retention_phrase") or binding.get("interpretation") or row.get("interpretation") or "").strip()
        rows.append(f"{value}: {interpretation}" if value and interpretation else value)
    for quantity in _list(row.get("quantities")):
        if isinstance(quantity, dict):
            binding = _quantity_binding_for_row(quantity, quantity_lookup)
            value = str(quantity.get("value") or "").strip()
            value = str(binding.get("value") or value).strip()
            interpretation = str(binding.get("retention_phrase") or binding.get("interpretation") or quantity.get("interpretation") or "").strip()
            rows.append(f"{value}: {interpretation}" if value and interpretation else value)
        elif str(quantity).strip():
            rows.append(str(quantity).strip())
    return _dedupe(rows)


def _quantity_binding_lookup(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    report = _dict(packet.get("analyst_quantity_binding_report"))
    rows = [
        *_list(report.get("approved_bindings")),
        *_list(report.get("candidate_bindings")),
        *_list(_dict(packet.get("quantity_obligation_plan")).get("rows")),
    ]
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in _quantity_binding_keys(row):
            lookup.setdefault(key, row)
    return lookup


def _quantity_binding_for_row(row: dict[str, Any], lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for key in _quantity_binding_keys(row):
        if key in lookup:
            return lookup[key]
    return {}


def _quantity_binding_keys(row: dict[str, Any]) -> list[str]:
    value = str(row.get("value") or row.get("quantity_value") or "").strip()
    source_evidence_item_id = str(row.get("source_evidence_item_id") or row.get("evidence_item_id") or "").strip()
    keys = [
        str(row.get("quantity_id") or "").strip(),
        str(row.get("candidate_id") or "").strip(),
        f"{source_evidence_item_id}::{value}" if source_evidence_item_id and value else "",
        value,
    ]
    return [key for key in keys if key]


def _first_text(values: list[Any], *, limit: int) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return _short_text(text, limit)
    return ""


def _quality_report(
    moves: list[dict[str, Any]],
    section_plan: list[dict[str, Any]],
    support_rows: list[dict[str, Any]],
    counterweight_rows: list[dict[str, Any]],
    quantity_rows: list[dict[str, Any]],
    source_weight_moves: list[dict[str, Any]],
) -> dict[str, Any]:
    move_types = Counter(str(row.get("move_type") or "") for row in moves)
    warnings = []
    if not support_rows:
        warnings.append("missing_support_move_evidence")
    if not counterweight_rows:
        warnings.append("missing_counterweight_move_evidence")
    if not source_weight_moves:
        warnings.append("missing_source_weight_moves")
    if quantity_rows and not any(row.get("move_type") == "quantity_calibration" for row in moves):
        warnings.append("quantity_rows_not_represented_as_move")
    if not section_plan:
        warnings.append("missing_section_plan")
    return {
        "schema_id": "analyst_decision_spine_quality_report_v1",
        "status": "ready" if not warnings else "warning",
        "move_count": len(moves),
        "move_type_counts": dict(move_types),
        "section_count": len(section_plan),
        "support_row_count": len(support_rows),
        "counterweight_row_count": len(counterweight_rows),
        "quantity_row_count": len(quantity_rows),
        "source_weight_move_count": len(source_weight_moves),
        "warnings": warnings,
    }


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", [], {}, None)}
