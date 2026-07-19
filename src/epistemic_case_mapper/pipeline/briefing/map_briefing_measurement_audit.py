from __future__ import annotations

import re
from collections import Counter
from typing import Any


def build_scoped_metric_report(
    *,
    scaffold: dict[str, Any],
    prioritized_map: dict[str, Any],
    runtime_budget_report: dict[str, Any],
    packet_retention_report: dict[str, Any],
) -> dict[str, Any]:
    input_scope = _dict(scaffold.get("input_map_scope_counts"))
    source_cards = _dict(scaffold.get("source_evidence_cards"))
    packet = _dict(scaffold.get("decision_briefing_packet"))
    metrics = [
        _metric("claim_count", "input_generated_map", input_scope.get("claim_count"), "input_map_scope_counts"),
        _metric("relation_count", "input_generated_map", input_scope.get("relation_count"), "input_map_scope_counts"),
        _metric("claim_count", "briefing_prioritized_map", len(_list(prioritized_map.get("claims"))), "prioritized_map"),
        _metric("relation_count", "briefing_prioritized_map", len(_list(prioritized_map.get("relations"))), "prioritized_map"),
        _metric("source_card_count", "source_evidence_cards", source_cards.get("source_card_count"), "source_evidence_cards"),
        _metric("anchored_source_card_count", "source_evidence_cards", source_cards.get("anchored_card_count"), "source_evidence_cards"),
        _metric("evidence_bundle_count", "decision_packet", len(_list(packet.get("evidence_bundles"))), "decision_briefing_packet"),
        _metric("must_retain_count", "decision_packet", len(_list(packet.get("must_retain_ledger"))), "decision_briefing_packet"),
        _metric(
            "retained_must_retain_count",
            "final_reader_memo",
            packet_retention_report.get("retained_must_retain_count"),
            "memo_packet_retention_report",
        ),
        _metric("model_call_count", "late_briefing_stages", runtime_budget_report.get("model_call_count"), "runtime_budget_report"),
    ]
    metrics = [row for row in metrics if row.get("value") is not None]
    return {
        "schema_id": "scoped_metric_report_v1",
        "status": "ready",
        "metrics": metrics,
        "ambiguous_metric_names": _ambiguous_metric_names(metrics),
        "notes": [
            "Metrics are scoped to the artifact they actually measure.",
            "Runtime budget counts late briefing stages unless an upstream runner supplies extraction-stage counters.",
        ],
    }


def build_final_source_lineage_report(memo_markdown: str, scaffold: dict[str, Any]) -> dict[str, Any]:
    packet = _dict(scaffold.get("decision_briefing_packet"))
    packet_sources = _packet_source_rows(packet)
    memo_sources = _memo_source_entries(memo_markdown)
    matched_source_ids = set()
    memo_rows = []
    for entry in memo_sources:
        match = _match_memo_source(entry, packet_sources)
        if match.get("packet_match_status") == "matched":
            matched_source_ids.add(str(match["source_id"]))
        memo_rows.append({**entry, **match})
    packet_ids = {str(row.get("source_id")) for row in packet_sources if row.get("appears_in_packet")}
    unused_memo_sources = [row for row in memo_rows if row.get("packet_match_status") != "matched"]
    missing_packet_sources = sorted(packet_ids - matched_source_ids)
    status = "warning" if unused_memo_sources or missing_packet_sources else "aligned"
    return {
        "schema_id": "final_source_lineage_report_v1",
        "status": status,
        "memo_source_count": len(memo_sources),
        "packet_source_count": len(packet_ids),
        "matched_packet_source_count": len(matched_source_ids),
        "unused_memo_source_count": len(unused_memo_sources),
        "missing_packet_source_count": len(missing_packet_sources),
        "memo_sources": memo_rows,
        "unused_memo_sources": unused_memo_sources,
        "missing_packet_source_ids": missing_packet_sources,
    }


def build_pipeline_measurement_audit(
    *,
    scoped_metric_report: dict[str, Any],
    source_lineage_report: dict[str, Any],
    relation_value_report: dict[str, Any],
    packet_retention_report: dict[str, Any],
    runtime_budget_report: dict[str, Any],
    section_role_quality_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues = []
    section_role_quality_report = _dict(section_role_quality_report)
    for name in scoped_metric_report.get("ambiguous_metric_names", []):
        issues.append(_issue("info", "metric_has_multiple_scopes", metric=name))
    if section_role_quality_report.get("status") == "warning":
        issues.append(
            _issue(
                "warning",
                "section_role_quality_warnings_present",
                count=section_role_quality_report.get("issue_count", 0),
            )
        )
    if str(relation_value_report.get("connectivity_status")) == "not_computable_missing_endpoint_ids":
        issues.append(
            _issue(
                "warning",
                "relation_connectivity_not_computable",
                missing_relation_count=relation_value_report.get("missing_endpoint_relation_count", 0),
            )
        )
    if source_lineage_report.get("unused_memo_source_count"):
        issues.append(
            _issue("warning", "memo_sources_include_sources_not_in_packet", count=source_lineage_report.get("unused_memo_source_count"))
        )
    if source_lineage_report.get("missing_packet_source_count"):
        issues.append(_issue("warning", "packet_sources_missing_from_memo_sources", count=source_lineage_report.get("missing_packet_source_count")))
    if _has_heuristic_retention_misses(packet_retention_report):
        issues.append(_issue("info", "retention_report_contains_heuristic_misses"))
    if runtime_budget_report.get("scope") == "late_briefing_stages_only":
        issues.append(_issue("info", "runtime_budget_excludes_upstream_extraction_and_relation_mapping"))
    return {
        "schema_id": "pipeline_measurement_audit_v1",
        "status": "warning" if any(issue["severity"] == "warning" for issue in issues) else "pass",
        "issues": issues,
        "measurement_principles": [
            "Compare metrics only when their scopes match.",
            "Treat heuristic text-retention misses as repair targets, not proof of absence.",
            "Treat non-computable telemetry as a data-shape bug, not a weak score.",
        ],
    }


def _packet_source_rows(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in _list(packet.get("source_trail")):
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _memo_source_entries(markdown: str) -> list[dict[str, str]]:
    match = re.search(r"(?im)^##\s+Sources\s*$", markdown)
    if not match:
        return []
    section = markdown[match.end() :]
    next_heading = re.search(r"(?m)^##\s+", section)
    if next_heading:
        section = section[: next_heading.start()]
    entries = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("-"):
            continue
        text = stripped.lstrip("-").strip()
        link = re.search(r"\[([^\]]+)\]\(([^)]+)\)", text)
        if link:
            entries.append({"source_label": link.group(1).strip(), "source_url": link.group(2).strip()})
        elif text:
            entries.append({"source_label": text, "source_url": ""})
    return entries


def _match_memo_source(entry: dict[str, str], packet_sources: list[dict[str, Any]]) -> dict[str, Any]:
    label = str(entry.get("source_label") or "")
    url = str(entry.get("source_url") or "")
    for row in packet_sources:
        aliases = _source_aliases(row)
        if url and url in aliases:
            return _source_match(row, "url")
        if any(_normalize(alias) == _normalize(label) for alias in aliases if alias):
            return _source_match(row, "label_alias")
    return {"packet_match_status": "not_in_packet", "match_method": "not_found", "source_id": ""}


def _source_match(row: dict[str, Any], match_method: str) -> dict[str, Any]:
    if row.get("appears_in_packet"):
        return {"packet_match_status": "matched", "match_method": match_method, "source_id": row.get("source_id")}
    return {"packet_match_status": "known_source_not_in_packet", "match_method": match_method, "source_id": row.get("source_id")}


def _source_aliases(row: dict[str, Any]) -> list[str]:
    return _dedupe(
        [
            str(row.get("source_id") or "").strip(),
            str(row.get("source_label") or "").strip(),
            str(row.get("citation_label") or "").strip(),
            str(row.get("display_label") or "").strip(),
            str(row.get("source_url") or "").strip(),
        ]
    )


def _has_heuristic_retention_misses(report: dict[str, Any]) -> bool:
    statuses = []
    for row in _list(report.get("retained_items")) + _list(report.get("bundle_items")):
        if isinstance(row, dict):
            statuses.extend(match.get("match_method") for match in _list(row.get("required_term_matches")))
            statuses.extend(match.get("match_method") for match in _list(row.get("quantity_matches")))
            statuses.extend(match.get("match_method") for match in _list(row.get("source_label_matches")))
    return bool(Counter(status for status in statuses if status == "not_found"))


def _metric(name: str, scope: str, value: Any, source_artifact: str) -> dict[str, Any]:
    if value is None:
        return {}
    return {"metric": name, "scope": scope, "value": value, "source_artifact": source_artifact}


def _ambiguous_metric_names(metrics: list[dict[str, Any]]) -> list[str]:
    values_by_name: dict[str, set[str]] = {}
    for row in metrics:
        values_by_name.setdefault(str(row.get("metric")), set()).add(f"{row.get('scope')}={row.get('value')}")
    return sorted(name for name, values in values_by_name.items() if len(values) > 1)


def _issue(severity: str, issue_type: str, **details: Any) -> dict[str, Any]:
    return {"severity": severity, "issue_type": issue_type, **details}


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
