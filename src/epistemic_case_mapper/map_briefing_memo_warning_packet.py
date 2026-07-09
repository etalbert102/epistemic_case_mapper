from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    list_value as _list,
    norm as _norm,
    string_list as _string_list,
)


def build_memo_warning_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Convert packet telemetry into actionable memo-writing warnings.

    The warning packet is deliberately narrow: it routes source-grounded,
    review-worthy evidence that was omitted from the memo-ready packet without
    making deterministic semantic edits to the memo.
    """

    packet = packet if isinstance(packet, dict) else {}
    coverage = packet.get("coverage_report", {}) if isinstance(packet.get("coverage_report"), dict) else {}
    source_labels = _source_labels(packet)
    warnings: list[dict[str, Any]] = []
    for key, severity, warning_type in (
        ("truly_lost_decision_critical", "critical", "omitted_decision_critical_evidence"),
        ("truly_lost_moderate_context", "moderate", "omitted_moderate_context"),
    ):
        for row in _list(coverage.get(key)):
            if not isinstance(row, dict):
                continue
            warning = _warning_from_omitted_row(
                row,
                severity=severity,
                warning_type=warning_type,
                index=len(warnings) + 1,
                source_labels=source_labels,
            )
            if warning:
                warnings.append(warning)
    return {
        "schema_id": "memo_warning_packet_v1",
        "method": "route_calibrated_packet_warnings_without_deterministic_semantic_repair",
        "actionable_warning_count": len(warnings),
        "critical_warning_count": sum(1 for row in warnings if row.get("severity") == "critical"),
        "moderate_warning_count": sum(1 for row in warnings if row.get("severity") == "moderate"),
        "warnings": warnings,
        "synthesis_guidance": [
            "Address each warning naturally if the provided claim and source label are sufficient.",
            "If the evidence should not change the answer, use it to bound scope or state a limitation.",
            "Do not mention warning IDs, telemetry, packet trimming, or internal validation.",
        ],
    }


def build_warning_resolution_report(
    memo: str,
    memo_warning_packet: dict[str, Any],
    *,
    source_aliases: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    warnings = [row for row in _list(memo_warning_packet.get("warnings")) if isinstance(row, dict)]
    statuses = [_warning_status(memo, warning, source_aliases=source_aliases or {}) for warning in warnings]
    unresolved = [row for row in statuses if row.get("status") == "unresolved"]
    possible = [row for row in statuses if row.get("status") == "possibly_addressed"]
    needs_repair = [*unresolved, *possible]
    return {
        "schema_id": "memo_warning_resolution_report_v1",
        "status": "ready" if not needs_repair else "warning",
        "warning_count": len(statuses),
        "addressed_count": sum(1 for row in statuses if row.get("status") == "addressed"),
        "possibly_addressed_count": len(possible),
        "unresolved_count": len(unresolved),
        "needs_repair_count": len(needs_repair),
        "warnings_needing_repair": needs_repair,
        "unresolved_warnings": unresolved,
        "possibly_addressed_warnings": possible,
        "warning_statuses": statuses,
    }


def unresolved_warning_repair_items(
    warning_resolution_report: dict[str, Any],
    memo_warning_packet: dict[str, Any],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    by_id = {
        str(row.get("warning_id")): row
        for row in _list(memo_warning_packet.get("warnings"))
        if isinstance(row, dict)
    }
    items = []
    for row in _list(warning_resolution_report.get("warnings_needing_repair")):
        if not isinstance(row, dict):
            continue
        warning = by_id.get(str(row.get("warning_id")))
        if not warning:
            continue
        items.append(
            {
                "warning_id": warning.get("warning_id"),
                "warning_type": warning.get("warning_type"),
                "severity": warning.get("severity"),
                "claim": warning.get("claim"),
                "source_labels": warning.get("source_labels", []),
                "quantity_values": warning.get("quantity_values", []),
                "repair_instruction": warning.get("repair_instruction"),
                "missing_anchor_terms": row.get("missing_anchor_terms", []),
            }
        )
        if len(items) >= limit:
            break
    return items


def _warning_from_omitted_row(
    row: dict[str, Any],
    *,
    severity: str,
    warning_type: str,
    index: int,
    source_labels: dict[str, str],
) -> dict[str, Any]:
    claim = str(row.get("claim") or "").strip()
    source_ids = _string_list(row.get("source_ids"))
    labels = _dedupe([source_labels.get(source_id, source_id) for source_id in source_ids if source_id])
    quantity_values = _string_list(row.get("quantity_values"))
    if not claim and not labels and not quantity_values:
        return {}
    action = (
        "Incorporate this as a load-bearing caveat or counterweight if it changes the practical read; "
        "otherwise use it to bound the confidence or scope of the answer."
    )
    return {
        "warning_id": f"memo_warning_{index:03d}",
        "warning_type": warning_type,
        "severity": severity,
        "decision_role": row.get("decision_role"),
        "source_ids": source_ids,
        "source_labels": labels,
        "quantity_values": quantity_values,
        "claim": claim,
        "anchor_terms": _content_terms(" ".join([claim, " ".join(quantity_values)]))[:10],
        "expected_memo_action": "incorporate_or_bound",
        "repair_instruction": action,
    }


def _warning_status(memo: str, warning: dict[str, Any], *, source_aliases: dict[str, list[str]]) -> dict[str, Any]:
    warning_id = str(warning.get("warning_id") or "")
    labels = _string_list(warning.get("source_labels"))
    claim = str(warning.get("claim") or "")
    quantities = _string_list(warning.get("quantity_values"))
    anchors = _string_list(warning.get("anchor_terms")) or _content_terms(claim)
    memo_body = _memo_without_sources(memo)
    source_retained = not labels or any(
        _contains_text(memo_body, alias)
        for label in labels
        for alias in _dedupe([label, *source_aliases.get(label, [])])
    )
    retained_quantities = [value for value in quantities if _contains_quantity(memo, value)]
    missing_quantities = [value for value in quantities if value not in retained_quantities]
    present_anchors = [term for term in anchors if _contains_text(memo, term)]
    required = min(3, len(anchors))
    enough_anchors = len(present_anchors) >= required if required else bool(source_retained or retained_quantities)
    addressed = source_retained and enough_anchors and not missing_quantities
    possibly = not addressed and enough_anchors
    return {
        "warning_id": warning_id,
        "warning_type": warning.get("warning_type"),
        "severity": warning.get("severity"),
        "status": "addressed" if addressed else "possibly_addressed" if possibly else "unresolved",
        "source_retained": source_retained,
        "anchor_terms_present": present_anchors,
        "missing_anchor_terms": [term for term in anchors if term not in present_anchors][:6],
        "missing_quantities": missing_quantities,
        "claim": claim,
        "source_labels": labels,
    }


def _source_labels(packet: dict[str, Any]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for row in _list(packet.get("source_trail")):
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id") or "").strip()
        label = str(row.get("source_label") or row.get("citation_label") or row.get("display_label") or "").strip()
        if source_id and label:
            labels[source_id] = label
    return labels


def _contains_text(text: str, needle: str) -> bool:
    needle = str(needle).strip()
    return not needle or needle.lower() in str(text).lower()


def _contains_quantity(text: str, quantity: str) -> bool:
    if _contains_text(text, quantity):
        return True
    normalized_text = _norm(text)
    numbers = re.findall(r"\d+(?:\.\d+)?", quantity)
    return bool(numbers) and all(number in normalized_text for number in numbers)


def _memo_without_sources(memo: str) -> str:
    return re.split(r"\n##+\s+Sources\b", str(memo), maxsplit=1, flags=re.IGNORECASE)[0]


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
    return _dedupe(
        [
            term.lower()
            for term in re.findall(r"[A-Za-z][A-Za-z-]{3,}", text)
            if term.lower() not in stop
        ]
    )
