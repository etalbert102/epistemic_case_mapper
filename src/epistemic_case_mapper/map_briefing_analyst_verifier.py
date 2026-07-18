from __future__ import annotations

from typing import Any


def build_analyst_decision_model_verification_report(
    *,
    analyst_decision_model: dict[str, Any],
    ledger: dict[str, Any],
    parse_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify hard analyst-model invariants before writer projection.

    This verifier deliberately keeps semantic judgments report-only. It blocks
    only source-truth invariants deterministic code can check reliably: IDs,
    source universe membership, result tuple identity, and source-span presence.
    """

    model = analyst_decision_model if isinstance(analyst_decision_model, dict) else {}
    ledger_rows = _ledger_rows_by_id(ledger)
    known_evidence_ids = set(ledger_rows)
    active_universe = _active_universe(model, ledger_rows)
    known_sources = _known_sources(ledger_rows)
    known_tuple_ids = _known_result_tuple_ids(ledger_rows)

    referenced_group_ids = _group_evidence_ids(model)
    disposition_ids = _disposition_ids(model)
    memo_decision_ids = _memo_relevance_ids(model)
    quantity_decision_ids = _quantity_decision_ids(model)
    unknown_evidence_ids = sorted(
        (referenced_group_ids | disposition_ids | memo_decision_ids | quantity_decision_ids) - known_evidence_ids
    )
    active_unknown_ids = sorted(set(active_universe.get("full_reasoning_evidence_item_ids", [])) - known_evidence_ids)
    unknown_source_ids = sorted(set(active_universe.get("source_ids", [])) - known_sources)
    unknown_tuple_ids = sorted(_referenced_result_tuple_ids(model) - known_tuple_ids)
    quantity_decisions_without_tuple_ids = _quantity_decisions_without_tuple_ids(model, ledger_rows)
    practical_unknown_ids = _practical_implication_unknown_ids(model, known_evidence_ids, known_sources)
    missing_source_spans = _missing_source_spans(ledger_rows)
    parse_issues = _list((parse_report or {}).get("issues"))
    fatal_issues = [
        *(["unknown_evidence_item_ids"] if unknown_evidence_ids else []),
        *(["active_universe_unknown_evidence_item_ids"] if active_unknown_ids else []),
        *(["active_universe_unknown_source_ids"] if unknown_source_ids else []),
        *(["unknown_result_tuple_ids"] if unknown_tuple_ids else []),
        *(["practical_implication_unknown_ids"] if practical_unknown_ids else []),
    ]
    warnings = [
        *(["quantity_decisions_without_result_tuple_ids"] if quantity_decisions_without_tuple_ids else []),
        *(["ledger_rows_missing_source_span"] if missing_source_spans else []),
        *(["analyst_parse_warnings_present"] if parse_issues else []),
        *(["missing_counterweight_dispositions"] if not _list(model.get("counterweight_dispositions")) else []),
        *(["missing_cruxes_or_update_triggers"] if not (_list(model.get("cruxes")) or _list(model.get("update_triggers"))) else []),
    ]
    return {
        "schema_id": "analyst_decision_model_verification_report_v1",
        "status": "blocked" if fatal_issues else "ready" if not warnings else "warning",
        "accepted": not fatal_issues,
        "fatal_issues": fatal_issues,
        "warnings": warnings,
        "known_evidence_item_count": len(known_evidence_ids),
        "known_source_count": len(known_sources),
        "known_result_tuple_count": len(known_tuple_ids),
        "unknown_evidence_item_ids": unknown_evidence_ids,
        "active_universe_unknown_evidence_item_ids": active_unknown_ids,
        "active_universe_unknown_source_ids": unknown_source_ids,
        "unknown_result_tuple_ids": unknown_tuple_ids,
        "quantity_decisions_without_result_tuple_ids": quantity_decisions_without_tuple_ids,
        "practical_implication_unknown_ids": practical_unknown_ids,
        "ledger_rows_missing_source_span": missing_source_spans,
        "parse_issues": parse_issues,
        "semantic_checks": {
            "status": "report_only",
            "checks": [
                "semantic_entailment",
                "causal_overstatement",
                "counterweight_disposition_adequacy",
                "action_support",
            ],
        },
    }


def _ledger_rows_by_id(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("evidence_item_id") or ""): row
        for row in _list(ledger.get("rows"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }


def _active_universe(model: dict[str, Any], ledger_rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    universe = model.get("active_evidence_universe")
    if isinstance(universe, dict):
        return {
            "full_reasoning_evidence_item_ids": _list_text(universe.get("full_reasoning_evidence_item_ids")),
            "routed_away_evidence_item_ids": _list_text(universe.get("routed_away_evidence_item_ids")),
            "source_ids": _list_text(universe.get("source_ids")),
        }
    return {
        "full_reasoning_evidence_item_ids": sorted(ledger_rows),
        "routed_away_evidence_item_ids": [],
        "source_ids": sorted(_known_sources(ledger_rows)),
    }


def _known_sources(ledger_rows: dict[str, dict[str, Any]]) -> set[str]:
    return {source_id for row in ledger_rows.values() for source_id in _list_text(row.get("source_ids"))}


def _known_result_tuple_ids(ledger_rows: dict[str, dict[str, Any]]) -> set[str]:
    ids = set()
    for row in ledger_rows.values():
        for quantity in _list(row.get("quantity_tuples")) + _list(row.get("result_quantity_tuples")):
            if isinstance(quantity, dict):
                tuple_id = str(quantity.get("result_tuple_id") or quantity.get("tuple_id") or "").strip()
                if tuple_id:
                    ids.add(tuple_id)
    return ids


def _group_evidence_ids(model: dict[str, Any]) -> set[str]:
    return {
        evidence_id
        for group in _list(model.get("evidence_groups"))
        if isinstance(group, dict)
        for evidence_id in _list_text(group.get("covered_evidence_item_ids"))
    }


def _disposition_ids(model: dict[str, Any]) -> set[str]:
    return {
        str(row.get("evidence_item_id") or "").strip()
        for row in _list(model.get("evidence_dispositions"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }


def _memo_relevance_ids(model: dict[str, Any]) -> set[str]:
    return {
        str(row.get("evidence_item_id") or "").strip()
        for row in _list(model.get("memo_relevance_decisions"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }


def _quantity_decision_ids(model: dict[str, Any]) -> set[str]:
    return {
        str(row.get("evidence_item_id") or "").strip()
        for row in _list(model.get("quantity_relevance_decisions"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }


def _referenced_result_tuple_ids(model: dict[str, Any]) -> set[str]:
    return {
        tuple_id
        for row in _list(model.get("quantity_relevance_decisions"))
        if isinstance(row, dict)
        for tuple_id in _list_text(row.get("result_tuple_ids"))
    }


def _quantity_decisions_without_tuple_ids(model: dict[str, Any], ledger_rows: dict[str, dict[str, Any]]) -> list[str]:
    rows = []
    for row in _list(model.get("quantity_relevance_decisions")):
        if not isinstance(row, dict):
            continue
        inclusion = str(row.get("memo_inclusion") or "")
        evidence_id = str(row.get("evidence_item_id") or "")
        if inclusion not in {"must_use", "supporting_context"}:
            continue
        if _list_text(row.get("result_tuple_ids")):
            continue
        if _known_result_tuple_ids({evidence_id: ledger_rows.get(evidence_id, {})}):
            rows.append(evidence_id)
    return sorted(set(rows))


def _practical_implication_unknown_ids(model: dict[str, Any], known_evidence_ids: set[str], known_sources: set[str]) -> list[dict[str, str]]:
    rows = []
    for index, implication in enumerate(_list(model.get("practical_implications")), start=1):
        if not isinstance(implication, dict):
            continue
        for evidence_id in _list_text(implication.get("evidence_item_ids")):
            if evidence_id not in known_evidence_ids:
                rows.append({"row": str(index), "id_type": "evidence_item_id", "id": evidence_id})
        for source_id in _list_text(implication.get("source_ids")):
            if source_id not in known_sources:
                rows.append({"row": str(index), "id_type": "source_id", "id": source_id})
    return rows


def _missing_source_spans(ledger_rows: dict[str, dict[str, Any]]) -> list[str]:
    return [
        evidence_id
        for evidence_id, row in ledger_rows.items()
        if str(row.get("source_excerpt") or "").strip() and not str(row.get("source_span") or row.get("span_id") or "").strip()
    ]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _list_text(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []
