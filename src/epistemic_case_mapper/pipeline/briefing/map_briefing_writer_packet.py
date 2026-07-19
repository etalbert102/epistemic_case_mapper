from __future__ import annotations

import re
from collections import Counter
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


ROLE_SECTION = {
    "strongest_support": "support",
    "strongest_counterweight": "counterweight",
    "decision_crux": "crux",
    "scope_boundary": "scope",
    "quantitative_anchor": "support",
    "mechanism_or_explanation": "context",
    "context_only": "context",
    "uncertain_role": "context",
}


QUANTITY_BUDGET_BY_ROLE = {
    "strongest_support": 3,
    "strongest_counterweight": 3,
    "decision_crux": 4,
    "scope_boundary": 4,
    "quantitative_anchor": 4,
    "mechanism_or_explanation": 2,
    "context_only": 1,
    "uncertain_role": 1,
}


def build_writer_packet(memo_ready_packet: dict[str, Any]) -> dict[str, Any]:
    packet = memo_ready_packet if isinstance(memo_ready_packet, dict) else {}
    source_lookup = _source_lookup(packet)
    evidence_units = [
        _writer_evidence_unit(item, source_lookup=source_lookup)
        for item in _list(packet.get("evidence_items"))
        if isinstance(item, dict)
    ]
    evidence_units = [unit for unit in evidence_units if unit]
    writer_packet = {
        "schema_id": "writer_packet_v1",
        "decision_question": str(packet.get("decision_question") or "").strip(),
        "answer": _answer(packet),
        "decision_logic": _writer_decision_logic(packet),
        "argument_plan": _writer_argument_plan(packet),
        "evidence_units": evidence_units,
        "sections": _sections(evidence_units),
        "source_aliases": _source_aliases(packet),
        "source_trail": _source_trail(packet),
        "do_not_overstate": _do_not_overstate(packet),
        "excluded_quantity_values": _excluded_quantity_values(packet),
        "writer_guidance": [
            "Answer directly, then explain why the support outweighs or is bounded by counterweights.",
            "Use only source-bound quantities from evidence_units.",
            "Use excluded_quantity_values only to avoid reintroducing rejected quantities.",
            "Use source_appraisal, allowed_wording, and source_use_warnings to calibrate claim strength.",
            "Treat scope and crux units as calibration, not as a list of every interesting subgroup.",
        ],
    }
    writer_packet["writer_packet_quality_report"] = build_writer_packet_quality_report(writer_packet)
    return writer_packet


def build_writer_packet_quality_report(writer_packet: dict[str, Any]) -> dict[str, Any]:
    units = [row for row in _list(writer_packet.get("evidence_units")) if isinstance(row, dict)]
    quantities = [
        quantity
        for unit in units
        for quantity in _list(unit.get("quantities"))
        if isinstance(quantity, dict)
    ]
    source_missing = [
        quantity
        for quantity in quantities
        if not quantity.get("source_label") and not quantity.get("source_evidence_item_id")
    ]
    budget_violations = [
        {
            "unit_id": unit.get("unit_id"),
            "role": unit.get("role"),
            "quantity_count": len(_list(unit.get("quantities"))),
            "budget": int(unit.get("quantity_budget", 0) or 0),
        }
        for unit in units
        if int(unit.get("quantity_budget", 0) or 0) and len(_list(unit.get("quantities"))) > int(unit.get("quantity_budget", 0) or 0)
    ]
    role_counts = Counter(str(unit.get("role") or "unknown") for unit in units)
    appraised_units = [unit for unit in units if _dict(unit.get("source_appraisal")).get("status") == "ready"]
    load_bearing_without_appraisal = [
        str(unit.get("unit_id") or "")
        for unit in units
        if unit.get("role") in {"strongest_support", "strongest_counterweight", "decision_crux", "scope_boundary"}
        and _dict(unit.get("source_appraisal")).get("status") != "ready"
    ]
    issues = [
        *(["no_support_unit"] if role_counts.get("strongest_support", 0) == 0 else []),
        *(["no_counterweight_or_scope_unit"] if role_counts.get("strongest_counterweight", 0) == 0 and role_counts.get("scope_boundary", 0) == 0 else []),
        *(["source_missing_quantities"] if source_missing else []),
        *(["quantity_budget_violations"] if budget_violations else []),
    ]
    return {
        "schema_id": "writer_packet_quality_report_v1",
        "status": "ready" if not issues else "warning",
        "evidence_unit_count": len(units),
        "quantity_count": len(quantities),
        "source_bound_quantity_count": len(quantities) - len(source_missing),
        "source_missing_quantity_count": len(source_missing),
        "source_appraised_unit_count": len(appraised_units),
        "load_bearing_without_appraisal": load_bearing_without_appraisal,
        "source_appraisal_warnings": (
            ["load_bearing_units_missing_source_appraisal"] if load_bearing_without_appraisal else []
        ),
        "role_counts": dict(role_counts),
        "budget_violations": budget_violations,
        "excluded_quantity_count": len(_list(writer_packet.get("excluded_quantity_values"))),
        "issues": issues,
    }


def _answer(packet: dict[str, Any]) -> dict[str, Any]:
    spine = _dict(packet.get("answer_spine"))
    return {
        "direct_answer": str(spine.get("default_read") or "").strip(),
        "confidence": str(spine.get("confidence") or "not_specified").strip(),
        "why_this_read": str(spine.get("why_this_read") or "").strip(),
        "why_not_stronger": str(spine.get("why_not_stronger") or "").strip(),
        "what_would_change_this": str(spine.get("what_would_change_this") or "").strip(),
    }


def _writer_decision_logic(packet: dict[str, Any]) -> dict[str, Any]:
    logic = _dict(packet.get("analyst_decision_logic"))
    return {
        key: logic.get(key)
        for key in (
            "bounded_bottom_line",
            "support_summary",
            "strongest_counterweight",
            "counterweight_weighting",
            "reconciled_cruxes",
            "scope_boundaries",
            "practical_implications",
            "do_not_overstate",
        )
        if logic.get(key)
    }


def _writer_argument_plan(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in _list(packet.get("analyst_argument_plan"))[:6]:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "step_id": row.get("step_id"),
                "section": row.get("section"),
                "writing_goal": row.get("writing_goal"),
                "required_points": _string_list(row.get("required_points"))[:4],
                "source_labels": _string_list(row.get("source_labels"))[:6],
                "transition_from_previous": row.get("transition_from_previous"),
            }
        )
    return rows


def _writer_evidence_unit(item: dict[str, Any], *, source_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    role = str(item.get("role") or "context_only")
    budget = QUANTITY_BUDGET_BY_ROLE.get(role, 1)
    quantities = _writer_quantities(item, source_lookup=source_lookup, budget=budget)
    source_labels = _source_labels_for_item(item, source_lookup)
    return {
        "unit_id": str(item.get("item_id") or ""),
        "section": ROLE_SECTION.get(role, "context"),
        "role": role,
        "must_use": bool(item.get("must_use")),
        "claim": _short_text(str(item.get("reader_claim") or ""), 620),
        "decision_relevance": _short_text(str(item.get("decision_relevance") or ""), 360),
        "caveat": _short_text(str(item.get("caveat") or ""), 260),
        "source_labels": source_labels,
        "primary_source_label": source_labels[0] if source_labels else "",
        "source_appraisal": item.get("source_appraisal") if isinstance(item.get("source_appraisal"), dict) else {},
        "source_use_warnings": _string_list(item.get("source_use_warnings")),
        "allowed_wording": item.get("allowed_wording") if isinstance(item.get("allowed_wording"), dict) else {},
        "quantities": quantities,
        "quantity_budget": budget,
        "lineage": item.get("lineage", {}),
    }


def _writer_quantities(
    item: dict[str, Any],
    *,
    source_lookup: dict[str, dict[str, Any]],
    budget: int,
) -> list[dict[str, Any]]:
    rows = []
    lineage_by_source = {
        str(row.get("source_evidence_item_id") or ""): row
        for row in _list(item.get("quantity_binding_lineage"))
        if isinstance(row, dict)
    }
    for quantity in _list(item.get("quantities")):
        if not isinstance(quantity, dict) or not str(quantity.get("value") or "").strip():
            continue
        source_evidence_item_id = str(quantity.get("source_evidence_item_id") or "").strip()
        lineage = lineage_by_source.get(source_evidence_item_id, {})
        source_label = _quantity_source_label(quantity, item, source_evidence_item_id=source_evidence_item_id)
        source = source_lookup.get(_source_key(source_label), {})
        rows.append(
            {
                "value": str(quantity.get("value") or "").strip(),
                "interpretation": _short_text(str(quantity.get("interpretation") or ""), 420),
                "source_evidence_item_id": source_evidence_item_id,
                "source_label": source.get("source_label") or source_label,
                "source_display": source.get("display_label") or source.get("source_label") or source_label,
                "binding_confidence": quantity.get("binding_confidence") or lineage.get("binding_confidence") or "",
                "binding_source": lineage.get("binding_source") or "",
            }
        )
    return rows[: max(0, budget)]


def _quantity_source_label(quantity: dict[str, Any], item: dict[str, Any], *, source_evidence_item_id: str) -> str:
    quantity_sources = _string_list(quantity.get("source_labels"))
    if quantity_sources:
        return quantity_sources[0]
    lineage_sources = _string_list(item.get("source_labels"))
    if not source_evidence_item_id:
        return lineage_sources[0] if lineage_sources else str(item.get("source_label") or "")
    for source in lineage_sources:
        if source:
            return source
    return str(item.get("source_label") or "")


def _source_labels_for_item(item: dict[str, Any], source_lookup: dict[str, dict[str, Any]]) -> list[str]:
    labels = []
    for label in _string_list(item.get("source_labels")) or _string_list(item.get("source_label")):
        source = source_lookup.get(_source_key(label), {})
        labels.append(str(source.get("display_label") or source.get("source_label") or label))
    return _dedupe(labels)


def _sections(evidence_units: list[dict[str, Any]]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    for unit in evidence_units:
        section = str(unit.get("section") or "context")
        sections.setdefault(section, []).append(str(unit.get("unit_id") or ""))
    return sections


def _source_lookup(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup = {}
    labels = [
        str(row.get("source_label") or "")
        for row in _list(packet.get("source_trail"))
        if isinstance(row, dict)
    ]
    common_prefix = _common_token_prefix(labels)
    for row in _list(packet.get("source_trail")):
        if not isinstance(row, dict):
            continue
        source_label = str(row.get("source_label") or row.get("source_id") or "").strip()
        display = _display_source_label(row, common_prefix=common_prefix)
        source = {
            "source_id": str(row.get("source_id") or "").strip(),
            "source_label": source_label,
            "display_label": display,
            "source_url": str(row.get("source_url") or "").strip(),
        }
        for alias in _dedupe([source_label, source["source_id"], display]):
            if alias:
                lookup[_source_key(alias)] = source
    return lookup


def _source_aliases(packet: dict[str, Any]) -> dict[str, str]:
    lookup = _source_lookup(packet)
    aliases = {}
    for source in lookup.values():
        label = source.get("source_label", "")
        display = source.get("display_label", "")
        if label and display:
            aliases[label] = display
    return dict(sorted(aliases.items()))


def _source_trail(packet: dict[str, Any]) -> list[dict[str, Any]]:
    lookup = _source_lookup(packet)
    rows = {}
    for source in lookup.values():
        key = source.get("source_id") or source.get("source_label")
        rows[key] = source
    return list(rows.values())


def _display_source_label(source: dict[str, Any], *, common_prefix: list[str]) -> str:
    for key in ("citation_label", "display_label"):
        value = str(source.get(key) or "").strip()
        if value:
            return value
    label = str(source.get("source_label") or source.get("source_id") or "").strip()
    if common_prefix:
        tokens = label.replace("_", " ").split()
        if [token.lower() for token in tokens[: len(common_prefix)]] == [token.lower() for token in common_prefix]:
            stripped = " ".join(tokens[len(common_prefix) :]).strip()
            if stripped:
                return stripped
    return label


def _common_token_prefix(labels: list[str]) -> list[str]:
    tokenized = [label.replace("_", " ").split() for label in labels if label.strip()]
    if len(tokenized) < 2:
        return []
    prefix: list[str] = []
    for tokens in zip(*tokenized):
        lowered = {token.lower() for token in tokens}
        if len(lowered) != 1:
            break
        prefix.append(tokens[0])
    if len(prefix) < 2:
        return []
    return prefix


def _do_not_overstate(packet: dict[str, Any]) -> list[str]:
    values = _string_list(_dict(packet.get("analyst_decision_logic")).get("do_not_overstate"))
    values.extend(_string_list(_dict(packet.get("analyst_synthesis_packet")).get("must_not_overstate")))
    values.extend(
        [
            "Use causal wording only when the source-backed unit itself supports causal inference.",
            "Use 'safe' only with explicit scope and uncertainty boundaries.",
        ]
    )
    return _dedupe(values)[:10]


def _excluded_quantity_values(packet: dict[str, Any]) -> list[str]:
    report = _dict(packet.get("analyst_quantity_binding_report"))
    return [
        str(row.get("value") or "").strip()
        for row in _list(report.get("rejected_bindings"))
        if isinstance(row, dict) and str(row.get("value") or "").strip()
    ][:30]


def _source_key(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())
