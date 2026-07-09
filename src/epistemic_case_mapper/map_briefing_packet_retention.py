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
    source_aliases = _source_alias_lookup(packet)
    retained_items = [_retain_item_status(row, memo_markdown, bundle_lookup, source_aliases) for row in retain_rows]
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
    source_aliases: dict[str, list[str]],
) -> dict[str, Any]:
    statement = str(row.get("statement", "")).strip()
    source_ids = _string_list(row.get("source_ids"))
    source_names = [source_aliases[source_id][0] for source_id in source_ids if source_aliases.get(source_id)]
    source_match_inputs = [(source_aliases[source_id][0], source_aliases[source_id]) for source_id in source_ids if source_aliases.get(source_id)]
    required_terms = _string_list(row.get("required_terms"))
    bundle_ids = _bundle_ids_for_retain_item(row, bundle_lookup)
    bundle_sources = [
        label
        for bundle_id in bundle_ids
        for label in _string_list(bundle_lookup.get(bundle_id, {}).get("source_labels"))
    ]
    source_names = _dedupe(source_names + bundle_sources)
    source_match_inputs.extend((label, [label]) for label in bundle_sources)
    bundle_quantities = [
        quantity
        for bundle_id in bundle_ids
        for quantity in _string_list(bundle_lookup.get(bundle_id, {}).get("quantity_values"))
    ]
    required_terms = _dedupe(required_terms + bundle_quantities)
    required_term_matches = [_required_term_match(memo, term) for term in required_terms]
    source_label_matches = [_source_label_match(memo, label, aliases) for label, aliases in source_match_inputs]
    missing_terms = [row["term"] for row in required_term_matches if not row["retained"]]
    missing_sources = [row["label"] for row in source_label_matches if not row["retained"]]
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
        "required_term_matches": required_term_matches,
        "source_label_matches": source_label_matches,
        "bundle_ids": bundle_ids,
        "retained": retained,
    }


def _bundle_status(row: dict[str, Any], memo: str) -> dict[str, Any]:
    claim = str(row.get("claim", "")).strip()
    quantities = _string_list(row.get("quantity_values"))
    source_labels = _string_list(row.get("source_labels"))
    quantity_matches = [_required_term_match(memo, quantity) for quantity in quantities]
    source_label_matches = [_source_label_match(memo, label, [label]) for label in source_labels]
    missing_quantities = [row["term"] for row in quantity_matches if not row["retained"]]
    missing_sources = [row["label"] for row in source_label_matches if not row["retained"]]
    claim_retained = _mentions_enough_content_terms(memo, claim, minimum=3)
    return {
        "bundle_id": row.get("bundle_id"),
        "decision_role": row.get("decision_role"),
        "weight": row.get("weight"),
        "claim_retained": claim_retained,
        "missing_quantities": missing_quantities,
        "missing_source_labels": missing_sources,
        "quantity_matches": quantity_matches,
        "source_label_matches": source_label_matches,
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


def _source_alias_lookup(packet: dict[str, Any]) -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {}
    for row in packet.get("source_trail", []) if isinstance(packet.get("source_trail"), list) else []:
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id") or "").strip()
        row_aliases = _dedupe(
            [
                str(row.get("source_label") or "").strip(),
                str(row.get("citation_label") or "").strip(),
                str(row.get("display_label") or "").strip(),
                str(row.get("source_url") or "").strip(),
            ]
        )
        if source_id and row_aliases:
            aliases[source_id] = row_aliases
    return aliases


def _contains_text(text: str, needle: str) -> bool:
    needle = str(needle).strip()
    if not needle:
        return True
    return needle.lower() in text.lower()


def _required_term_retained(text: str, term: str) -> bool:
    return bool(_required_term_match(text, term)["retained"])


def _required_term_match(text: str, term: str) -> dict[str, Any]:
    term = str(term).strip()
    if not term:
        return {"term": term, "retained": True, "match_method": "empty_term"}
    if _contains_text(text, term):
        return {"term": term, "retained": True, "match_method": "exact"}
    normalized_text = _normalize_for_match(text)
    normalized_term = _normalize_for_match(term)
    if normalized_term and normalized_term in normalized_text:
        return {"term": term, "retained": True, "match_method": "normalized_text"}
    numbers = _number_tokens(term)
    if numbers and len(_content_terms(term)) > 1:
        retained = all(_normalized_number_present(normalized_text, number) for number in numbers) and _mentions_enough_content_terms(
            text,
            term,
            minimum=2,
        )
        return {
            "term": term,
            "retained": retained,
            "match_method": "normalized_numeric" if retained else "not_found",
        }
    if _requires_exact_term_match(term):
        return {"term": term, "retained": False, "match_method": "not_found"}
    retained = _mentions_enough_content_terms(text, term, minimum=2)
    return {"term": term, "retained": retained, "match_method": "content_terms" if retained else "not_found"}


def _source_label_match(text: str, label: str, aliases: list[str]) -> dict[str, Any]:
    label = str(label).strip()
    for alias in _dedupe([label, *aliases]):
        if not alias:
            continue
        if _contains_text(text, alias):
            return {"label": label, "retained": True, "match_method": "exact_alias", "matched_alias": alias}
        normalized_alias = _normalize_for_match(alias)
        if normalized_alias and normalized_alias in _normalize_for_match(text):
            return {"label": label, "retained": True, "match_method": "normalized_alias", "matched_alias": alias}
    return {"label": label, "retained": False, "match_method": "not_found"}


def _requires_exact_term_match(term: str) -> bool:
    return bool(re.search(r"\d|%|[$]", term)) or len(_content_terms(term)) <= 1


def _number_tokens(text: str) -> list[str]:
    return re.findall(r"\$?\d[\d,]*(?:\.\d+)?%?", text)


def _normalize_for_match(text: str) -> str:
    normalized = str(text).lower()
    normalized = re.sub(r"[\u2010-\u2015]", "-", normalized)
    normalized = re.sub(r"\s*([=:/<>])\s*", r"\1", normalized)
    normalized = re.sub(r"\bconfidence interval\b", "ci", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _normalized_number_present(normalized_text: str, number: str) -> bool:
    normalized_number = _normalize_for_match(number)
    variants = {normalized_number, normalized_number.replace(",", "")}
    return any(variant and variant in normalized_text.replace(",", "") for variant in variants)


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
