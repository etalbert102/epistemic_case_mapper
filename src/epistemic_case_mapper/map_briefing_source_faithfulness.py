from __future__ import annotations

import re
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
                "source_claim": str(ledger_row.get("claim") or ""),
                "claim_context": ledger_row.get("claim_context") if isinstance(ledger_row.get("claim_context"), dict) else {},
                "relation_endpoint_answer_matrix": ledger_row.get("relation_endpoint_answer_matrix")
                if isinstance(ledger_row.get("relation_endpoint_answer_matrix"), dict)
                else {},
            }
        )
    return warnings[:24]


def source_faithfulness_warning_reason(ledger_row: dict[str, Any], adjudication_row: dict[str, Any]) -> str:
    signals = set(_string_list(ledger_row.get("source_bottom_line_signals")))
    memo_use = str(adjudication_row.get("memo_use") or "")
    answer_relation = str(adjudication_row.get("answer_relation") or "")
    support_like = memo_use == "load_bearing_primary_support" or answer_relation == "supports_answer"
    if support_like and _is_comparator_or_substitution_row(ledger_row) and not _decision_context_asks_comparator(adjudication_row):
        return "comparator_substitution_claim_used_as_direct_answer_support"
    if not signals:
        return ""
    target = " ".join(
        [
            str(adjudication_row.get("target_answer_option") or ""),
            str(adjudication_row.get("effect_on_final_answer") or ""),
            str(adjudication_row.get("rationale") or ""),
            str(adjudication_row.get("_decision_context") or ""),
        ]
    ).lower()
    counter_like = memo_use == "load_bearing_counterweight" or answer_relation == "challenges_answer"
    neutral_or_benefit_target = any(term in target for term in ("neutral", "benefit", "beneficial", "safe", "not harmful", "not meaningfully harmful"))
    harmful_target = any(term in target for term in ("harmful", "risk", "unsafe", "worse", "higher harm"))
    if "increased_harm_or_risk_signal" in signals and support_like and neutral_or_benefit_target:
        return "source_bottom_line_increased_risk_but_row_supports_neutral_or_beneficial_answer"
    if {"no_clear_association_signal", "reduced_harm_or_risk_signal"} & signals and counter_like and harmful_target and not neutral_or_benefit_target:
        return "source_bottom_line_does_not_show_harm_but_row_challenges_as_harmful"
    return ""


def _is_comparator_or_substitution_row(ledger_row: dict[str, Any]) -> bool:
    context = ledger_row.get("claim_context") if isinstance(ledger_row.get("claim_context"), dict) else {}
    quantity_text = " ".join(
        " ".join(
            str(quantity.get(field) or "")
            for field in ("local_interpretation", "measures", "source_quote", "retention_phrase", "interpretation")
        )
        for quantity in _list(ledger_row.get("claim_quantities"))
        if isinstance(quantity, dict)
    )
    text = " ".join(
        [
            str(ledger_row.get("claim") or ""),
            str(ledger_row.get("natural_bottom_line") or ""),
            str(context.get("exposure_or_option") or ""),
            str(context.get("stated_scope") or ""),
            str(context.get("applicability_limits") or ""),
            " ".join(_string_list(ledger_row.get("must_preserve_terms"))),
            quantity_text,
        ]
    ).lower()
    if re.search(r"\breplac\w*\b|\bsubstitut\w*\b|\balternative to\b", text):
        return True
    return bool(
        re.search(
            r"\binstead of (?:a |an |the |one |other |another )?"
            r"(?:serving|option|treatment|intervention|product|therapy|food|drug|program|source)\b",
            text,
        )
    )


def _decision_context_asks_comparator(adjudication_row: dict[str, Any]) -> bool:
    text = str(adjudication_row.get("_decision_context") or "").lower()
    return any(
        marker in text
        for marker in (
            "replace",
            "substitut",
            "instead of",
            "compared with",
            "compared to",
            "versus",
            " vs ",
            "which option",
            "which alternative",
        )
    )


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
    ledger_by_id = {
        str(row.get("evidence_item_id") or ""): row
        for row in _list(ledger.get("rows"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }
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
        repaired = repair_adjudication_row(row, str(warning.get("warning") or ""), ledger_by_id.get(evidence_id, {}))
        repaired_rows.append(repaired)
        if repaired != row:
            repaired_ids.add(evidence_id)
    repaired = dict(adjudication)
    repaired["rows"] = repaired_rows
    after = source_faithfulness_warnings(ledger, repaired)
    status = "repaired" if repaired_ids and not after else "repaired_with_unresolved_warnings" if repaired_ids else "unresolved"
    return repaired, _repair_report(before, after, sorted(repaired_ids), status)


def repair_adjudication_row(row: dict[str, Any], warning_reason: str, ledger_row: dict[str, Any] | None = None) -> dict[str, Any]:
    ledger_row = ledger_row if isinstance(ledger_row, dict) else {}
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
    if warning_reason == "comparator_substitution_claim_used_as_direct_answer_support":
        repaired = dict(row)
        claim = _short_text(str(ledger_row.get("claim") or ""), 360)
        context = ledger_row.get("claim_context") if isinstance(ledger_row.get("claim_context"), dict) else {}
        comparator = _short_text(str(context.get("exposure_or_option") or claim), 260)
        repaired["memo_use"] = "mechanism_or_context"
        repaired["answer_relation"] = "contextualizes_answer"
        repaired["effect_on_final_answer"] = "contextualizes current_best_answer"
        repaired["decision_contribution"] = _short_text(f"Comparator/substitution context: {claim}", 520)
        repaired["use_in_reasoning"] = "comparator/context"
        repaired["key_qualifier"] = _short_text(f"Preserve comparator direction: {comparator}", 320)
        repaired["quantity_takeaway"] = _short_text(
            "Quantities from this row measure the comparator or substitution contrast, not the direct effect of the target option.",
            260,
        )
        repaired["rationale"] = _short_text(
            " ".join(
                part
                for part in (
                    str(row.get("rationale") or ""),
                    "Source-faithfulness repair preserved comparator direction and routed this away from direct primary support.",
                )
                if part
            ),
            620,
        )
        repaired["misuse_warning"] = _short_text(
            "Do not present this as the direct effect of the target option; preserve the comparator or substitution direction.",
            260,
        )
        repaired["source_weight_note"] = _short_text(
            "Source-faithfulness repair: comparator/substitution evidence can contextualize the answer but should not be rewritten as direct target-option evidence.",
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
