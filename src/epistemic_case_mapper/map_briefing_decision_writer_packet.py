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
from epistemic_case_mapper.map_briefing_memo_obligations import build_memo_obligation_packet


ROLE_BY_GLOBAL_SECTION = {
    "strongest_support": "strongest_support",
    "strongest_counterargument": "strongest_counterweight",
    "scope_boundaries": "scope_boundary",
    "decision_cruxes": "decision_crux",
    "contextual_evidence": "context_only",
}

SECTION_BY_ROLE = {
    "strongest_support": "support",
    "strongest_counterweight": "counterweight",
    "decision_crux": "crux",
    "scope_boundary": "scope",
    "context_only": "context",
}


def build_decision_writer_packet_bundle(
    *,
    global_decision_model: dict[str, Any],
    ledger: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    packet = build_decision_writer_packet(global_decision_model=global_decision_model, ledger=ledger)
    quality = build_decision_writer_packet_quality_report(packet, global_decision_model=global_decision_model, ledger=ledger)
    traceability = build_evidence_unit_traceability_matrix(packet, ledger=ledger)
    packet["decision_writer_packet_quality_report"] = quality
    return {
        "decision_writer_packet": packet,
        "decision_writer_packet_quality_report": quality,
        "evidence_unit_traceability_matrix": traceability,
    }


def decision_writer_packet_to_memo_ready_packet(
    decision_writer_packet: dict[str, Any],
    *,
    quality_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    packet = decision_writer_packet if isinstance(decision_writer_packet, dict) else {}
    evidence_items = [
        _memo_ready_item_from_unit(index, unit)
        for index, unit in enumerate(_list(packet.get("evidence_units")), start=1)
        if isinstance(unit, dict)
    ]
    memo_obligations = build_memo_obligation_packet(evidence_items, {"warnings": []})
    memo_ready = {
        "schema_id": "memo_ready_packet_v1",
        "method": "global_decision_writer_packet_adapter",
        "decision_question": packet.get("decision_question"),
        "answer_spine": {
            "default_read": _dict(packet.get("answer")).get("bounded_answer"),
            "confidence": _dict(packet.get("answer")).get("confidence", "not_specified"),
            "why_this_read": "; ".join(_string_list(_dict(packet.get("answer")).get("confidence_reasons"))[:3]),
            "synthesis_strategy": "Write directly from the global decision writer packet.",
        },
        "source_trail": _list(packet.get("source_trail")),
        "memo_warning_packet": {},
        "analyst_decision_logic": _dict(packet.get("decision_logic")),
        "analyst_argument_plan": _list(packet.get("argument_plan")),
        "memo_obligations": memo_obligations,
        "decision_writer_packet_quality_report": quality_report or packet.get("decision_writer_packet_quality_report", {}),
        "evidence_items": evidence_items,
        "writer_packet": packet,
        "writer_packet_quality_report": quality_report or packet.get("decision_writer_packet_quality_report", {}),
        "decision_synthesis_contract": {
            "schema_id": "decision_synthesis_contract_v1",
            "method": "global_decision_writer_packet_adapter",
            "bounded_answer": _dict(packet.get("answer")).get("bounded_answer"),
            "must_preserve": _contract_must_preserve(evidence_items),
            "required_memo_obligations": [
                obligation for obligation in memo_obligations.get("obligations", []) if obligation.get("required")
            ],
            "warnings": _string_list(_dict(packet.get("global_reconciliation")).get("issues")),
        },
    }
    return memo_ready


def build_decision_writer_packet(*, global_decision_model: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    ledger_by_id = _ledger_by_id(ledger)
    evidence_units = _evidence_units(global_decision_model, ledger_by_id)
    return {
        "schema_id": "decision_writer_packet_v1",
        "method": "global_decision_model_projection",
        "decision_question": str(global_decision_model.get("decision_question") or ledger.get("decision_question") or "").strip(),
        "answer": {
            "bounded_answer": str(global_decision_model.get("bounded_answer") or "").strip(),
            "confidence": str(global_decision_model.get("confidence") or "not_specified").strip(),
            "confidence_reasons": _string_list(global_decision_model.get("confidence_reasons")),
        },
        "decision_logic": _dict(global_decision_model.get("decision_logic")),
        "argument_plan": _compact_argument_plan(global_decision_model),
        "evidence_units": evidence_units,
        "sections": _sections(evidence_units),
        "source_trail": _source_trail(evidence_units, ledger_by_id),
        "source_aliases": _source_aliases(evidence_units, ledger_by_id),
        "do_not_overstate": _string_list(_dict(global_decision_model.get("decision_logic")).get("do_not_overstate")),
        "missing_evidence": _string_list(global_decision_model.get("missing_evidence")),
        "global_reconciliation": _dict(global_decision_model.get("reconciliation")),
        "writer_guidance": [
            "Use the bounded answer as the stance.",
            "Weigh support, counterweights, scope boundaries, and cruxes as an argument.",
            "Use attached source labels and source-bound quantities when citing load-bearing claims.",
            "Treat missing evidence and reconciliation warnings as uncertainty to explain, not as prose metadata.",
        ],
    }


def _memo_ready_item_from_unit(index: int, unit: dict[str, Any]) -> dict[str, Any]:
    source_labels = _string_list(unit.get("source_labels"))
    return {
        "item_id": f"decision_writer_item_{index:03d}",
        "role": str(unit.get("role") or "context_only"),
        "reader_claim": str(unit.get("claim") or "").strip(),
        "source_label": source_labels[0] if source_labels else "",
        "source_labels": source_labels,
        "source_ids": [],
        "quantities": _memo_ready_quantities(unit),
        "lineage": _dict(unit.get("lineage")),
        "decision_relevance": str(unit.get("decision_relevance") or "").strip(),
        "caveat": str(unit.get("caveat") or "").strip(),
        "must_use": str(unit.get("role") or "") != "context_only",
    }


def _memo_ready_quantities(unit: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "value": str(quantity.get("value") or "").strip(),
            "interpretation": str(quantity.get("interpretation") or "").strip(),
            "source_evidence_item_id": str(quantity.get("source_evidence_item_id") or "").strip(),
            "source_labels": _string_list(quantity.get("source_label")) or _string_list(quantity.get("source_labels")),
        }
        for quantity in _list(unit.get("quantities"))
        if isinstance(quantity, dict) and str(quantity.get("value") or "").strip()
    ]


def _contract_must_preserve(evidence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "item_id": item.get("item_id"),
            "role": item.get("role"),
            "claim": item.get("reader_claim"),
            "source_labels": item.get("source_labels", []),
            "quantities": item.get("quantities", []),
        }
        for item in evidence_items
        if item.get("must_use")
    ]


def build_decision_writer_packet_quality_report(
    packet: dict[str, Any],
    *,
    global_decision_model: dict[str, Any],
    ledger: dict[str, Any],
) -> dict[str, Any]:
    units = [unit for unit in _list(packet.get("evidence_units")) if isinstance(unit, dict)]
    role_counts = Counter(str(unit.get("role") or "unknown") for unit in units)
    missing_source_units = [
        str(unit.get("unit_id") or "")
        for unit in units
        if not _string_list(unit.get("source_labels"))
    ]
    missing_critical = _missing_critical_evidence(global_decision_model)
    issues = [
        *(["empty_writer_packet"] if not units else []),
        *(["missing_support_unit"] if role_counts.get("strongest_support", 0) == 0 else []),
        *(["missing_counterweight_or_scope_unit"] if role_counts.get("strongest_counterweight", 0) == 0 and role_counts.get("scope_boundary", 0) == 0 else []),
        *(["source_trail_missing_for_units"] if missing_source_units else []),
        *(["critical_evidence_not_accounted"] if missing_critical else []),
        *(["global_model_has_reconciliation_warnings"] if _string_list(_dict(global_decision_model.get("reconciliation")).get("issues")) else []),
    ]
    return {
        "schema_id": "decision_writer_packet_quality_report_v1",
        "status": "ready" if not issues else "warning",
        "evidence_unit_count": len(units),
        "ledger_row_count": len(_list(ledger.get("rows"))),
        "role_counts": dict(role_counts),
        "source_trail_count": len(_list(packet.get("source_trail"))),
        "source_missing_unit_ids": missing_source_units,
        "missing_critical_evidence_item_ids": missing_critical,
        "global_reconciliation_issues": _string_list(_dict(global_decision_model.get("reconciliation")).get("issues")),
        "packet_is_smaller_than_full_ledger": len(str(packet)) < len(str(ledger)),
        "issues": issues,
    }


def build_evidence_unit_traceability_matrix(packet: dict[str, Any], *, ledger: dict[str, Any]) -> dict[str, Any]:
    units = [unit for unit in _list(packet.get("evidence_units")) if isinstance(unit, dict)]
    unit_by_evidence_id = {
        evidence_id: unit
        for unit in units
        for evidence_id in _string_list(_dict(unit.get("lineage")).get("covered_evidence_item_ids"))
    }
    rows = []
    for ledger_row in _list(ledger.get("rows")):
        if not isinstance(ledger_row, dict):
            continue
        evidence_id = str(ledger_row.get("evidence_item_id") or "").strip()
        unit = unit_by_evidence_id.get(evidence_id, {})
        rows.append(
            {
                "evidence_item_id": evidence_id,
                "claim_id": ledger_row.get("claim_id"),
                "in_writer_packet": bool(unit),
                "unit_id": unit.get("unit_id", ""),
                "role": unit.get("role", ""),
                "source_labels": _string_list(ledger_row.get("source_labels")),
            }
        )
    return {
        "schema_id": "evidence_unit_traceability_matrix_v1",
        "method": "ledger_row_to_decision_writer_packet_unit",
        "row_count": len(rows),
        "covered_row_count": sum(1 for row in rows if row.get("in_writer_packet")),
        "rows": rows,
    }


def _evidence_units(global_model: dict[str, Any], ledger_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    units = []
    for section, role in ROLE_BY_GLOBAL_SECTION.items():
        for group in _list(global_model.get(section)):
            if isinstance(group, dict):
                units.append(_unit_from_group(len(units) + 1, group, role=role, ledger_by_id=ledger_by_id))
    return [unit for unit in units if unit.get("claim")]


def _unit_from_group(index: int, group: dict[str, Any], *, role: str, ledger_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    evidence_ids = _string_list(group.get("covered_evidence_item_ids"))
    source_labels = _source_labels(evidence_ids, ledger_by_id)
    return {
        "unit_id": f"decision_unit_{index:03d}",
        "section": SECTION_BY_ROLE.get(role, "context"),
        "role": role,
        "claim": _short_text(str(group.get("proposition") or ""), 720),
        "decision_relevance": _short_text(str(group.get("answer_impact") or group.get("rationale") or ""), 520),
        "caveat": _short_text("; ".join(_string_list(group.get("applicability_limits"))), 360),
        "source_labels": source_labels,
        "primary_source_label": source_labels[0] if source_labels else "",
        "quantities": _quantities(evidence_ids, ledger_by_id),
        "source_excerpts": _source_excerpts(evidence_ids, ledger_by_id),
        "lineage": {
            "global_group_id": group.get("group_id"),
            "covered_evidence_item_ids": evidence_ids,
        },
    }


def _compact_argument_plan(global_model: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in _list(global_model.get("argument_plan")):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "step_id": row.get("step_id"),
                "section": row.get("section"),
                "writing_goal": row.get("writing_goal"),
                "required_points": _string_list(row.get("required_points"))[:6],
                "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:12],
                "transition_from_previous": row.get("transition_from_previous"),
            }
        )
    return rows


def _source_trail(evidence_units: list[dict[str, Any]], ledger_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_key: dict[str, dict[str, Any]] = {}
    for unit in evidence_units:
        role = str(unit.get("role") or "").strip()
        for evidence_id in _string_list(_dict(unit.get("lineage")).get("covered_evidence_item_ids")):
            for row in _source_rows(ledger_by_id.get(evidence_id, {})):
                key = _source_key(row)
                if not key:
                    continue
                existing = rows_by_key.setdefault(key, row | {"used_for": []})
                existing["used_for"] = _dedupe([*_string_list(existing.get("used_for")), role])
    return sorted(rows_by_key.values(), key=lambda row: (str(row.get("source_label") or ""), str(row.get("source_id") or "")))


def _source_aliases(evidence_units: list[dict[str, Any]], ledger_by_id: dict[str, dict[str, Any]]) -> dict[str, str]:
    trail = _source_trail(evidence_units, ledger_by_id)
    return {
        str(row.get("source_label") or row.get("source_id") or ""): str(row.get("display_label") or row.get("source_label") or row.get("source_id") or "")
        for row in trail
        if str(row.get("source_label") or row.get("source_id") or "").strip()
    }


def _source_labels(evidence_ids: list[str], ledger_by_id: dict[str, dict[str, Any]]) -> list[str]:
    labels = []
    for evidence_id in evidence_ids:
        row = ledger_by_id.get(evidence_id, {})
        labels.extend(_string_list(row.get("source_labels")) or _string_list(row.get("source_ids")))
    return _dedupe(labels)


def _quantities(evidence_ids: list[str], ledger_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for evidence_id in evidence_ids:
        ledger_row = ledger_by_id.get(evidence_id, {})
        labels = _string_list(ledger_row.get("source_labels"))
        for value in _string_list(ledger_row.get("quantity_values")):
            rows.append(
                {
                    "value": value,
                    "source_evidence_item_id": evidence_id,
                    "source_label": labels[0] if labels else "",
                    "interpretation": _short_text(str(ledger_row.get("why_it_matters") or ledger_row.get("claim") or ""), 360),
                }
            )
    return rows


def _source_excerpts(evidence_ids: list[str], ledger_by_id: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for evidence_id in evidence_ids:
        ledger_row = ledger_by_id.get(evidence_id, {})
        excerpt = str(ledger_row.get("source_excerpt") or "").strip()
        if excerpt:
            rows.append({"evidence_item_id": evidence_id, "source_excerpt": _short_text(excerpt, 420)})
    return rows


def _source_rows(ledger_row: dict[str, Any]) -> list[dict[str, str]]:
    source_ids = _string_list(ledger_row.get("source_ids"))
    source_labels = _string_list(ledger_row.get("source_labels"))
    count = max(len(source_ids), len(source_labels), 1)
    rows = []
    for index in range(count):
        source_id = source_ids[index] if index < len(source_ids) else ""
        source_label = source_labels[index] if index < len(source_labels) else source_id
        if source_id or source_label:
            rows.append(
                {
                    "source_id": source_id,
                    "source_label": source_label,
                    "display_label": source_label or source_id,
                }
            )
    return rows


def _source_key(row: dict[str, Any]) -> str:
    return str(row.get("source_id") or row.get("source_label") or "").strip().lower()


def _ledger_by_id(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("evidence_item_id") or "").strip(): row
        for row in _list(ledger.get("rows"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }


def _sections(evidence_units: list[dict[str, Any]]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    for unit in evidence_units:
        section = str(unit.get("section") or "context")
        sections.setdefault(section, []).append(str(unit.get("unit_id") or ""))
    return sections


def _missing_critical_evidence(global_model: dict[str, Any]) -> list[str]:
    accounting = _dict(global_model.get("evidence_accounting"))
    missing = _string_list(accounting.get("missing_accounting_ids"))
    omissions = _dict(accounting.get("obligation_omissions"))
    for value in omissions.values():
        missing.extend(_string_list(value))
    return _dedupe(missing)
