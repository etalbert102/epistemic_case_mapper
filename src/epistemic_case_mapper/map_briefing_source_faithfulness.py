from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


def source_faithfulness_warnings(ledger: dict[str, Any], adjudication: dict[str, Any]) -> list[dict[str, Any]]:
    ledger_by_id = {
        str(row.get("evidence_item_id") or ""): row
        for row in _list(ledger.get("rows"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }
    warnings = []
    decision_context = _decision_context_text(ledger)
    for row in _list(adjudication.get("rows")):
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_item_id") or "")
        ledger_row = ledger_by_id.get(evidence_id, {})
        reason = source_faithfulness_warning_reason(ledger_row, {**row, "_decision_context": decision_context})
        if not reason:
            continue
        warnings.append(
            {
                "evidence_item_id": evidence_id,
                "warning": reason,
                "memo_use": row.get("memo_use"),
                "answer_relation": row.get("answer_relation"),
                "target_answer_option": row.get("target_answer_option"),
                "source_bottom_line_signals": _string_list(ledger_row.get("source_bottom_line_signals")),
                "source_bottom_lines": _list(ledger_row.get("source_bottom_lines"))[:3],
                "relation_endpoint_answer_matrix": ledger_row.get("relation_endpoint_answer_matrix")
                if isinstance(ledger_row.get("relation_endpoint_answer_matrix"), dict)
                else {},
            }
        )
    return warnings[:24]


def source_faithfulness_warning_reason(ledger_row: dict[str, Any], adjudication_row: dict[str, Any]) -> str:
    signals = set(_string_list(ledger_row.get("source_bottom_line_signals")))
    if not signals:
        return ""
    memo_use = str(adjudication_row.get("memo_use") or "")
    answer_relation = str(adjudication_row.get("answer_relation") or "")
    target = " ".join(
        [
            str(adjudication_row.get("target_answer_option") or ""),
            str(adjudication_row.get("effect_on_final_answer") or ""),
            str(adjudication_row.get("rationale") or ""),
            str(adjudication_row.get("_decision_context") or ""),
        ]
    ).lower()
    support_like = memo_use == "load_bearing_primary_support" or answer_relation == "supports_answer"
    counter_like = memo_use == "load_bearing_counterweight" or answer_relation == "challenges_answer"
    neutral_or_benefit_target = any(term in target for term in ("neutral", "benefit", "beneficial", "safe", "not harmful", "not meaningfully harmful"))
    harmful_target = any(term in target for term in ("harmful", "risk", "unsafe", "worse", "higher harm"))
    if "increased_harm_or_risk_signal" in signals and support_like and neutral_or_benefit_target:
        return "source_bottom_line_increased_risk_but_row_supports_neutral_or_beneficial_answer"
    if {"no_clear_association_signal", "reduced_harm_or_risk_signal"} & signals and counter_like and harmful_target and not neutral_or_benefit_target:
        return "source_bottom_line_does_not_show_harm_but_row_challenges_as_harmful"
    return ""


def _decision_context_text(ledger: dict[str, Any]) -> str:
    frame = ledger.get("stable_final_answer_frame") if isinstance(ledger.get("stable_final_answer_frame"), dict) else {}
    return " ".join(
        part
        for part in (
            str(ledger.get("decision_question") or ""),
            str(frame.get("current_best_answer") or ""),
            str(frame.get("selected_answer_option_id") or ""),
        )
        if part
    )


def repair_adjudication_source_faithfulness(
    ledger: dict[str, Any],
    adjudication: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    before = source_faithfulness_warnings(ledger, adjudication)
    if not before:
        return adjudication, _repair_report(before, [], [], "not_needed")
    repaired_rows = []
    repaired_ids = set()
    warning_by_id = {str(row.get("evidence_item_id") or ""): row for row in before}
    for row in _list(adjudication.get("rows")):
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_item_id") or "")
        warning = warning_by_id.get(evidence_id)
        if not warning:
            repaired_rows.append(row)
            continue
        repaired = repair_adjudication_row(row, str(warning.get("warning") or ""))
        repaired_rows.append(repaired)
        if repaired != row:
            repaired_ids.add(evidence_id)
    repaired = dict(adjudication)
    repaired["rows"] = repaired_rows
    after = source_faithfulness_warnings(ledger, repaired)
    status = "repaired" if repaired_ids and not after else "repaired_with_unresolved_warnings" if repaired_ids else "unresolved"
    return repaired, _repair_report(before, after, sorted(repaired_ids), status)


def repair_adjudication_row(row: dict[str, Any], warning_reason: str) -> dict[str, Any]:
    if warning_reason == "source_bottom_line_increased_risk_but_row_supports_neutral_or_beneficial_answer":
        repaired = dict(row)
        repaired["memo_use"] = "load_bearing_counterweight"
        repaired["answer_relation"] = "challenges_answer"
        repaired["effect_on_final_answer"] = "weakens current_best_answer"
        repaired["rationale"] = _short_text(
            " ".join(
                part
                for part in (
                    str(row.get("rationale") or ""),
                    "Source bottom-line polarity indicates this row should bound or challenge the supported answer, not serve as primary support.",
                )
                if part
            ),
            620,
        )
        repaired["misuse_warning"] = _short_text(
            "Do not use this row as primary support for the answer until the source-bottom-line conflict is explicitly resolved.",
            260,
        )
        repaired["source_weight_note"] = _short_text(
            "Source-faithfulness repair routed this row away from primary support because source-level polarity conflicts with the assigned answer role.",
            320,
        )
        return repaired
    return row


def _repair_report(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    repaired_ids: list[str],
    status: str,
) -> dict[str, Any]:
    return {
        "schema_id": "analyst_source_faithfulness_repair_report_v1",
        "status": status,
        "warning_count_before": len(before),
        "warning_count_after": len(after),
        "repaired_evidence_item_ids": repaired_ids,
        "warnings_before": before,
        "warnings_after": after,
    }
