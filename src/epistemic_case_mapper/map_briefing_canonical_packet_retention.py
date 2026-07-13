from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_quantity_retention import quantity_retained, retention_quantity_rows


def build_canonical_packet_retention_report(
    memo: str,
    packet: dict[str, Any],
    *,
    source_aliases: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    canonical = _dict(packet.get("canonical_decision_writer_packet"))
    if not canonical:
        return {
            "schema_id": "canonical_packet_retention_report_v1",
            "status": "not_available",
            "issues": [],
            "checklist_statuses": [],
            "skeleton_statuses": [],
        }
    checklist_statuses = [
        _checklist_retention_status(memo, row, source_aliases=source_aliases or {})
        for row in _list(canonical.get("mandatory_retention_checklist"))
        if isinstance(row, dict)
    ]
    skeleton_statuses = _skeleton_retention_statuses(memo, _dict(canonical.get("decision_brief_skeleton")))
    checklist_issues = [row for row in checklist_statuses if not row.get("retained")]
    skeleton_issues = [
        row
        for row in skeleton_statuses
        if not row.get("retained") and row.get("field") in {"direct_answer", "main_reason", "strongest_counterweight"}
    ]
    issues = [*checklist_issues, *skeleton_issues]
    return {
        "schema_id": "canonical_packet_retention_report_v1",
        "status": "ready" if not issues else "warning",
        "validation_basis": "canonical_decision_writer_packet",
        "mandatory_retention_count": len(checklist_statuses),
        "retained_mandatory_count": sum(1 for row in checklist_statuses if row.get("retained")),
        "missing_mandatory_count": len(checklist_issues),
        "missing_quantity_count": sum(len(row.get("missing_quantities", [])) for row in checklist_issues),
        "skeleton_field_count": len(skeleton_statuses),
        "retained_skeleton_field_count": sum(1 for row in skeleton_statuses if row.get("retained")),
        "missing_skeleton_field_count": len(skeleton_issues),
        "checklist_statuses": checklist_statuses,
        "skeleton_statuses": skeleton_statuses,
        "issues": issues,
    }


def canonical_repair_items(retention_report: dict[str, Any], *, limit: int = 10) -> list[dict[str, Any]]:
    canonical = _dict(retention_report.get("canonical_packet_retention_report"))
    rows = []
    for issue in _list(canonical.get("issues")):
        if not isinstance(issue, dict):
            continue
        rows.append(
            {
                "issue_type": issue.get("issue_type"),
                "field": issue.get("field"),
                "role": issue.get("role"),
                "statement": issue.get("statement"),
                "source_ids": issue.get("source_ids", []),
                "quantities": issue.get("quantities", []),
                "missing_quantities": issue.get("missing_quantities", []),
                "writing_job": issue.get("writing_job"),
            }
        )
    return rows[:limit]


def _checklist_retention_status(
    memo: str,
    row: dict[str, Any],
    *,
    source_aliases: dict[str, list[str]],
) -> dict[str, Any]:
    statement = str(row.get("statement") or row.get("claim") or "").strip()
    source_ids = _string_list(row.get("source_ids"))
    quantities = retention_quantity_rows(row)
    missing_quantities = [quantity["value"] for quantity in quantities if not quantity_retained(memo, quantity)]
    source_retained = _source_ids_retained(memo, source_ids, source_aliases)
    claim_retained = _mentions_enough_terms(memo, _content_terms(statement), minimum=3)
    retained = source_retained and claim_retained and not missing_quantities
    return {
        "issue_type": "missing_canonical_retention_item",
        "retained": retained,
        "source_retained": source_retained,
        "claim_retained": claim_retained,
        "missing_quantities": missing_quantities,
        "role": row.get("role"),
        "statement": statement,
        "source_ids": source_ids,
        "quantities": row.get("quantities", []),
        "writing_job": row.get("prose_instruction") or row.get("writing_job"),
    }


def _skeleton_retention_statuses(memo: str, skeleton: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for field in ("direct_answer", "scope", "confidence", "main_reason", "strongest_counterweight", "counterweight_disposition", "practical_implication"):
        value = str(skeleton.get(field) or "").strip()
        if not value:
            continue
        terms = _content_terms(value)
        rows.append(
            {
                "issue_type": "missing_canonical_skeleton_field",
                "field": field,
                "statement": value,
                "retained": _mentions_enough_terms(memo, terms, minimum=min(4, max(2, len(terms) // 2))),
                "validation_terms": terms,
            }
        )
    return rows


def _source_ids_retained(memo: str, source_ids: list[str], source_aliases: dict[str, list[str]]) -> bool:
    if not source_ids:
        return True
    aliases = _dedupe(alias for source_id in source_ids for alias in [source_id, *source_aliases.get(source_id, [])] if alias)
    return any(_contains_text(memo, alias) for alias in aliases)


def _mentions_enough_terms(text: str, terms: list[str], *, minimum: int) -> bool:
    if not terms:
        return True
    retained = sum(1 for term in terms if _contains_text(text, term))
    return retained >= min(minimum, len(terms))


def _content_terms(text: str) -> list[str]:
    stopwords = {
        "about",
        "after",
        "also",
        "because",
        "being",
        "between",
        "could",
        "from",
        "have",
        "into",
        "more",
        "should",
        "than",
        "that",
        "their",
        "there",
        "this",
        "with",
        "would",
    }
    terms = []
    for raw in str(text or "").replace("/", " ").replace("-", " ").split():
        term = "".join(char for char in raw.lower() if char.isalnum())
        if len(term) >= 4 and term not in stopwords:
            terms.append(term)
    return _dedupe(terms)[:12]


def _contains_text(text: str, needle: str) -> bool:
    needle = str(needle).strip()
    return not needle or needle.lower() in str(text or "").lower()
