from __future__ import annotations

import re
from typing import Any


def build_memo_packet_retention_report(memo_markdown: str, packet: dict[str, Any] | None) -> dict[str, Any]:
    """Audit whether final memo prose retained packet-level obligations.

    This is intentionally warning-oriented. It checks stable packet anchors
    deterministically, then reports misses for model repair or human review.
    """

    packet = packet if isinstance(packet, dict) else {}
    retain_rows = [row for row in packet.get("must_retain_ledger", []) if isinstance(row, dict)]
    bundle_rows = [row for row in packet.get("evidence_bundles", []) if isinstance(row, dict)]
    bundle_lookup = {str(row.get("bundle_id", "")).strip(): row for row in bundle_rows if str(row.get("bundle_id", "")).strip()}
    source_labels = _source_label_lookup(packet)
    retained_items = [_retain_item_status(row, memo_markdown, bundle_lookup, source_labels) for row in retain_rows]
    bundle_items = [_bundle_status(row, memo_markdown) for row in bundle_rows if _bundle_requires_surface_check(row)]
    issues = _retention_issues(retained_items, bundle_items)
    status = "ready" if not issues else "warning"
    if any(issue.get("severity") == "critical" for issue in issues):
        status = "critical_warnings"
    return {
        "schema_id": "memo_packet_retention_report_v1",
        "status": status,
        "packet_present": bool(packet),
        "must_retain_count": len(retain_rows),
        "retained_must_retain_count": sum(1 for row in retained_items if row.get("retained")),
        "checked_bundle_count": len(bundle_items),
        "retained_bundle_count": sum(1 for row in bundle_items if row.get("retained")),
        "missing_critical_count": sum(1 for issue in issues if issue.get("severity") == "critical"),
        "missing_high_count": sum(1 for issue in issues if issue.get("severity") == "high"),
        "retained_items": retained_items,
        "bundle_items": bundle_items,
        "issues": issues,
    }


def _retain_item_status(
    row: dict[str, Any],
    memo: str,
    bundle_lookup: dict[str, dict[str, Any]],
    source_labels: dict[str, str],
) -> dict[str, Any]:
    statement = str(row.get("statement", "")).strip()
    source_ids = _string_list(row.get("source_ids"))
    source_names = [source_labels[source_id] for source_id in source_ids if source_labels.get(source_id)]
    required_terms = _string_list(row.get("required_terms"))
    bundle_ids = _bundle_ids_for_retain_item(row, bundle_lookup)
    bundle_sources = [
        label
        for bundle_id in bundle_ids
        for label in _string_list(bundle_lookup.get(bundle_id, {}).get("source_labels"))
    ]
    source_names = _dedupe(source_names + bundle_sources)
    bundle_quantities = [
        quantity
        for bundle_id in bundle_ids
        for quantity in _string_list(bundle_lookup.get(bundle_id, {}).get("quantity_values"))
    ]
    required_terms = _dedupe(required_terms + bundle_quantities)
    missing_terms = [term for term in required_terms if not _required_term_retained(memo, term)]
    missing_sources = [label for label in source_names if not _contains_text(memo, label)]
    statement_retained = _mentions_enough_content_terms(memo, statement, minimum=3)
    retained = not missing_terms and not missing_sources and statement_retained
    return {
        "item_id": row.get("item_id"),
        "decision_role": row.get("decision_role"),
        "importance": row.get("importance"),
        "omission_policy": row.get("omission_policy"),
        "statement_retained": statement_retained,
        "missing_required_terms": missing_terms,
        "missing_source_labels": missing_sources,
        "bundle_ids": bundle_ids,
        "retained": retained,
    }


def _bundle_status(row: dict[str, Any], memo: str) -> dict[str, Any]:
    claim = str(row.get("claim", "")).strip()
    quantities = _string_list(row.get("quantity_values"))
    source_labels = _string_list(row.get("source_labels"))
    missing_quantities = [quantity for quantity in quantities if not _contains_text(memo, quantity)]
    missing_sources = [label for label in source_labels if not _contains_text(memo, label)]
    claim_retained = _mentions_enough_content_terms(memo, claim, minimum=3)
    return {
        "bundle_id": row.get("bundle_id"),
        "decision_role": row.get("decision_role"),
        "weight": row.get("weight"),
        "claim_retained": claim_retained,
        "missing_quantities": missing_quantities,
        "missing_source_labels": missing_sources,
        "retained": claim_retained and not missing_quantities and not missing_sources,
    }


def _retention_issues(retained_items: list[dict[str, Any]], bundle_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for row in retained_items:
        if row.get("retained"):
            continue
        severity = _retain_severity(row)
        issue_parts = []
        if not row.get("statement_retained"):
            issue_parts.append("statement")
        if row.get("missing_required_terms"):
            issue_parts.append("required_terms")
        if row.get("missing_source_labels"):
            issue_parts.append("source_labels")
        issues.append(
            {
                "severity": severity,
                "issue_type": "missing_must_retain_item",
                "item_id": row.get("item_id"),
                "decision_role": row.get("decision_role"),
                "missing_parts": issue_parts,
                "missing_required_terms": row.get("missing_required_terms", []),
                "missing_source_labels": row.get("missing_source_labels", []),
            }
        )
    for row in bundle_items:
        if row.get("retained"):
            continue
        issues.append(
            {
                "severity": "high" if row.get("weight") in {"critical", "high"} else "medium",
                "issue_type": "weak_bundle_retention",
                "bundle_id": row.get("bundle_id"),
                "decision_role": row.get("decision_role"),
                "claim_retained": row.get("claim_retained"),
                "missing_quantities": row.get("missing_quantities", []),
                "missing_source_labels": row.get("missing_source_labels", []),
            }
        )
    return issues


def _retain_severity(row: dict[str, Any]) -> str:
    importance = str(row.get("importance") or "").strip().lower()
    policy = str(row.get("omission_policy") or "").strip().lower()
    if importance == "critical" or policy == "must_include":
        return "critical"
    if importance == "high":
        return "high"
    return "medium"


def _bundle_requires_surface_check(row: dict[str, Any]) -> bool:
    role = str(row.get("decision_role") or "").strip()
    weight = str(row.get("weight") or "").strip()
    return bool(row.get("quantity_values")) or role in {"strongest_support", "counterweight", "scope_boundary", "decision_crux"} or weight in {
        "critical",
        "high",
    }


def _bundle_ids_for_retain_item(row: dict[str, Any], bundle_lookup: dict[str, dict[str, Any]]) -> list[str]:
    explicit = _string_list(row.get("bundle_ids"))
    if explicit:
        return [bundle_id for bundle_id in explicit if bundle_id in bundle_lookup]
    claim_ids = set(_string_list(row.get("claim_ids")))
    source_ids = set(_string_list(row.get("source_ids")))
    matched = []
    for bundle_id, bundle in bundle_lookup.items():
        if claim_ids and claim_ids & set(_string_list(bundle.get("claim_ids"))):
            matched.append(bundle_id)
            continue
        if source_ids and source_ids & set(_string_list(bundle.get("source_ids"))):
            matched.append(bundle_id)
    return matched[:5]


def _source_label_lookup(packet: dict[str, Any]) -> dict[str, str]:
    labels = {}
    for row in packet.get("source_trail", []) if isinstance(packet.get("source_trail"), list) else []:
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id") or "").strip()
        label = str(row.get("source_label") or "").strip()
        if source_id and label:
            labels[source_id] = label
    return labels


def _contains_text(text: str, needle: str) -> bool:
    needle = str(needle).strip()
    if not needle:
        return True
    return needle.lower() in text.lower()


def _required_term_retained(text: str, term: str) -> bool:
    term = str(term).strip()
    if not term:
        return True
    numbers = _number_tokens(term)
    if numbers and len(_content_terms(term)) > 1:
        return all(_contains_text(text, number) for number in numbers) and _mentions_enough_content_terms(text, term, minimum=2)
    if _requires_exact_term_match(term):
        return _contains_text(text, term)
    return _mentions_enough_content_terms(text, term, minimum=2)


def _requires_exact_term_match(term: str) -> bool:
    return bool(re.search(r"\d|%|[$]", term)) or len(_content_terms(term)) <= 1


def _number_tokens(text: str) -> list[str]:
    return re.findall(r"\$?\d+(?:\.\d+)?%?", text)


def _mentions_enough_content_terms(text: str, statement: str, *, minimum: int) -> bool:
    terms = _content_terms(statement)
    if not terms:
        return True
    required = min(minimum, len(terms))
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered) >= required


def _content_terms(text: str) -> list[str]:
    stop = {
        "about",
        "after",
        "again",
        "also",
        "because",
        "before",
        "between",
        "could",
        "current",
        "decision",
        "does",
        "from",
        "have",
        "into",
        "more",
        "should",
        "source",
        "that",
        "their",
        "there",
        "this",
        "those",
        "under",
        "when",
        "where",
        "which",
        "while",
        "with",
        "would",
    }
    terms = []
    for term in re.findall(r"[a-z0-9][a-z0-9-]{2,}", text.lower()):
        if term not in stop and term not in terms:
            terms.append(term)
    return terms


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
