from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.evidence_bundles import normalize_assertion_bundles

CLAIM_QUANTITY_SCHEMA_ID = "claim_bound_quantity_v1"

CLAIM_QUANTITY_ROLES = {
    "effect_estimate",
    "uncertainty_interval",
    "baseline_or_absolute_risk",
    "exposure_or_intervention_level",
    "population_descriptor",
    "study_descriptor",
    "time_horizon",
    "threshold_or_guideline",
    "cost_or_resource",
    "context",
    "source_reported_quantity",
}

CLAIM_QUANTITY_RETENTION_HINTS = {"must_retain", "use_if_space", "audit_only"}


def claim_quantity_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "value": {"type": "string"},
            "quantity_role": {"type": "string", "enum": sorted(CLAIM_QUANTITY_ROLES)},
            "measures": {"type": "string"},
            "local_interpretation": {"type": "string"},
            "source_quote": {"type": "string"},
            "line_hint": {"type": "string"},
            "retention_hint": {"type": "string", "enum": sorted(CLAIM_QUANTITY_RETENTION_HINTS)},
        },
        "required": ["value", "quantity_role", "measures", "local_interpretation", "source_quote", "line_hint", "retention_hint"],
    }


def normalize_claim_quantity_rows(
    value: Any,
    *,
    supporting_quotes: list[dict[str, Any]] | None = None,
    claim_id: str = "",
    source_id: str = "",
    source_span: str = "",
    source_quote: str = "",
    claim_text: str = "",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _list(value):
        row = _quantity_row(
            item,
            supporting_quotes=supporting_quotes or [],
            claim_id=claim_id,
            source_id=source_id,
            source_span=source_span,
            source_quote=source_quote,
            claim_text=claim_text,
        )
        if row:
            rows.append(row)
    return _dedupe_rows(rows)


def claim_quantity_values(rows: Any) -> list[str]:
    return _dedupe(
        [
            str(row.get("value") or "").strip()
            for row in _list(rows)
            if isinstance(row, dict) and str(row.get("value") or "").strip()
        ]
    )


def merged_claim_quantities(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for claim in claims:
        source_card = claim.get("whole_doc_source_card") if isinstance(claim.get("whole_doc_source_card"), dict) else {}
        claim_rows = [*_list(claim.get("claim_quantities")), *_list(source_card.get("claim_quantities"))]
        raw_rows = claim_rows if claim_rows else [*_list(claim.get("quantity_values")), *_list(source_card.get("quantities"))]
        rows.extend(
            normalize_claim_quantity_rows(
                raw_rows,
                claim_id=str(claim.get("claim_id") or ""),
                source_id=str(claim.get("source_id") or ""),
                source_span=str(claim.get("source_span") or ""),
                source_quote=str(claim.get("source_quote") or claim.get("excerpt") or ""),
                claim_text=str(claim.get("claim") or ""),
            )
        )
    return _dedupe_rows(rows)


def quantity_type(value: str) -> str:
    text = value.lower()
    if re.search(r"\b(19|20)\d{2}\b", text):
        return "date"
    if re.search(r"\b\d+(\.\d+)?\s*(years?|months?|weeks?|days?)\b", text):
        return "duration"
    if re.search(r"\b(n\s*=\s*)?\d{2,3}(,\d{3})+\b", text):
        return "sample_size"
    if "%" in text or "percent" in text or "percentage" in text:
        return "percentage"
    if re.search(r"\b(rr|hr|or|risk ratio|hazard ratio|odds ratio)\b", text):
        return "ratio"
    if re.search(r"\b\d+(\.\d+)?\s*/\s*(week|wk|day|d|month|year|yr)\b", text):
        return "dose"
    if re.search(r"\b\d+(\.\d+)?\b", text):
        return "unknown"
    return "not_numeric"


def _quantity_row(
    item: Any,
    *,
    supporting_quotes: list[dict[str, Any]],
    claim_id: str = "",
    source_id: str = "",
    source_span: str = "",
    source_quote: str = "",
    claim_text: str = "",
) -> dict[str, Any]:
    if isinstance(item, dict):
        value = _compact(
            str(item.get("value") or item.get("quantity") or item.get("quantity_text") or item.get("text") or ""),
            max_chars=160,
        )
        if not value:
            return {}
        bundles = normalize_assertion_bundles(
            [item],
            claim_id=claim_id,
            source_id=source_id,
            source_span=source_span,
            source_quote=source_quote,
            claim_text=claim_text,
            supporting_quotes=supporting_quotes,
        )
        return {
            "schema_id": CLAIM_QUANTITY_SCHEMA_ID,
            "value": value,
            "quantity_type": _compact(str(item.get("quantity_type") or quantity_type(value)), max_chars=80),
            "quantity_role": _normalize_role(item.get("quantity_role") or item.get("role")),
            "measures": _compact(str(item.get("measures") or item.get("measured_construct") or item.get("endpoint") or ""), max_chars=180),
            "local_interpretation": _compact(str(item.get("local_interpretation") or item.get("interpretation") or ""), max_chars=240),
            "source_quote": _compact(str(item.get("source_quote") or _first_quote(supporting_quotes)), max_chars=300),
            "line_hint": _compact(str(item.get("line_hint") or _first_line_hint(supporting_quotes)), max_chars=80),
            "retention_hint": _normalize_retention_hint(item.get("retention_hint")),
            "assertion_bundles": bundles,
            "evidence_bundle_id": str(bundles[0].get("evidence_bundle_id") or "") if bundles else "",
        }
    value = _compact(str(item or ""), max_chars=160)
    if not value:
        return {}
    bundles = normalize_assertion_bundles(
        [{"value": value}],
        claim_id=claim_id,
        source_id=source_id,
        source_span=source_span,
        source_quote=source_quote,
        claim_text=claim_text,
        supporting_quotes=supporting_quotes,
    )
    return {
        "schema_id": CLAIM_QUANTITY_SCHEMA_ID,
        "value": value,
        "quantity_type": quantity_type(value),
        "quantity_role": "source_reported_quantity",
        "measures": "",
        "local_interpretation": "",
        "source_quote": _compact(_first_quote(supporting_quotes), max_chars=300),
        "line_hint": _compact(_first_line_hint(supporting_quotes), max_chars=80),
        "retention_hint": "use_if_space",
        "assertion_bundles": bundles,
        "evidence_bundle_id": str(bundles[0].get("evidence_bundle_id") or "") if bundles else "",
    }


def _normalize_role(value: Any) -> str:
    role = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return role if role in CLAIM_QUANTITY_ROLES else "source_reported_quantity"


def _normalize_retention_hint(value: Any) -> str:
    hint = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return hint if hint in CLAIM_QUANTITY_RETENTION_HINTS else "use_if_space"


def _first_quote(quotes: list[dict[str, Any]]) -> str:
    for row in quotes:
        if isinstance(row, dict) and str(row.get("quote") or "").strip():
            return str(row.get("quote") or "").strip()
    return ""


def _first_line_hint(quotes: list[dict[str, Any]]) -> str:
    for row in quotes:
        if isinstance(row, dict) and str(row.get("line_hint") or "").strip():
            return str(row.get("line_hint") or "").strip()
    return ""


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return [value] if value else []


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (_norm(row.get("value", "")), _norm(row.get("quantity_role", "")), _norm(row.get("measures", "")))
        if not row.get("value") or key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _norm(value)
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _compact(value: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9.%/-]+", " ", str(value).lower())).strip()
