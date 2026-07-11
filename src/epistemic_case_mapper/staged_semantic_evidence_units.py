from __future__ import annotations

import re
from typing import Any

EVIDENCE_UNIT_SCHEMA_ID = "source_evidence_unit_v1"
EVIDENCE_UNIT_REPORT_SCHEMA_ID = "source_evidence_unit_quality_report_v1"
SOURCE_QUANTITY_TUPLES_SCHEMA_ID = "source_quantity_tuples_v1"


def source_evidence_unit_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "unit_id": {"type": "string"},
            "source_id": {"type": "string"},
            "proposition": {"type": "string"},
            "evidence_type": {"type": "string"},
            "population": {"type": "string"},
            "exposure_or_intervention": {"type": "string"},
            "comparator": {"type": "string"},
            "endpoint": {"type": "string"},
            "estimate": {"type": "string"},
            "uncertainty_interval": {"type": "string"},
            "method": {"type": "string"},
            "caveat": {"type": "string"},
            "time_horizon": {"type": "string"},
            "source_quote": {"type": "string"},
            "source_span": {"type": "string"},
            "quote_lineage": {"type": "array", "items": {"type": "object"}},
            "quantities": {"type": "array", "items": {"type": "object"}},
            "scope_conditions": {"type": "array", "items": {"type": "string"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["unit_id", "source_id", "proposition", "source_quote", "source_span", "quote_lineage"],
    }


def build_source_evidence_units(
    source_card: dict[str, Any],
    *,
    source_id: str,
    source_text: str,
) -> dict[str, Any]:
    units = []
    quantity_tuples = []
    quote_count = 0
    exact_quote_count = 0
    warning_counts: dict[str, int] = {}
    for index, claim in enumerate(_list(source_card.get("canonical_claims")), start=1):
        if not isinstance(claim, dict):
            continue
        unit = _unit_from_claim(index, claim, source_id=source_id, source_text=source_text)
        if unit is None:
            _increment(warning_counts, "invalid_claim_shape")
            continue
        quote_count += len(unit["quote_lineage"])
        exact_quote_count += sum(1 for row in unit["quote_lineage"] if row.get("quote_match_status") == "exact_or_normalized")
        for warning in unit["warnings"]:
            _increment(warning_counts, warning)
        units.append(unit)
        quantity_tuples.extend(_quantity_tuples_for_unit(unit))
    report = {
        "schema_id": EVIDENCE_UNIT_REPORT_SCHEMA_ID,
        "status": "ready" if units else "warning",
        "source_id": source_id,
        "unit_count": len(units),
        "quantity_tuple_count": len(quantity_tuples),
        "quote_count": quote_count,
        "exact_quote_count": exact_quote_count,
        "warning_counts": warning_counts,
        "issues": [] if units else ["no_source_evidence_units"],
    }
    return {
        "source_evidence_units": {
            "schema_id": "source_evidence_units_v1",
            "source_id": source_id,
            "units": units,
        },
        "source_quantity_tuples": {
            "schema_id": SOURCE_QUANTITY_TUPLES_SCHEMA_ID,
            "source_id": source_id,
            "tuples": quantity_tuples,
        },
        "source_evidence_unit_quality_report": report,
    }


def _unit_from_claim(index: int, claim: dict[str, Any], *, source_id: str, source_text: str) -> dict[str, Any] | None:
    proposition = _compact(str(claim.get("claim") or ""))
    if not proposition:
        return None
    quotes = _quote_lineage(claim, source_text=source_text)
    if not quotes:
        return None
    source_quote = str(quotes[0].get("quote") or "")
    warnings = []
    if not _lexically_supported(proposition, source_quote):
        warnings.append("weak_quote_claim_overlap")
    quantities = [_quantity_row(value) for value in _string_list(claim.get("quantities"))]
    typed = _typed_fields(proposition, quantities, claim)
    return {
        "schema_id": EVIDENCE_UNIT_SCHEMA_ID,
        "unit_id": f"{_safe_id(source_id)}_eu{index:03d}",
        "source_id": source_id,
        "proposition": proposition,
        "evidence_type": typed["evidence_type"],
        "population": typed["population"],
        "exposure_or_intervention": typed["exposure_or_intervention"],
        "comparator": typed["comparator"],
        "endpoint": typed["endpoint"],
        "estimate": typed["estimate"],
        "uncertainty_interval": typed["uncertainty_interval"],
        "method": typed["method"],
        "caveat": typed["caveat"],
        "time_horizon": typed["time_horizon"],
        "source_quote": source_quote,
        "source_span": str(quotes[0].get("line_hint") or ""),
        "quote_lineage": quotes,
        "quantities": quantities,
        "scope_conditions": _string_list(claim.get("scope_conditions")),
        "question_relevance": str(claim.get("question_relevance") or ""),
        "decision_importance": str(claim.get("decision_importance") or ""),
        "why_it_matters": _compact(str(claim.get("why_it_matters") or "")),
        "warnings": warnings,
    }


def _quote_lineage(claim: dict[str, Any], *, source_text: str) -> list[dict[str, str]]:
    rows = []
    for row in _list(claim.get("supporting_quotes")):
        if not isinstance(row, dict):
            continue
        quote = _clean_quote(str(row.get("quote") or ""))
        if not quote:
            continue
        rows.append(
            {
                "quote": quote,
                "line_hint": str(row.get("line_hint") or ""),
                "quote_match_status": "exact_or_normalized" if _quote_matches_source(quote, source_text) else "not_found",
            }
        )
    return rows


def _typed_fields(proposition: str, quantities: list[dict[str, Any]], claim: dict[str, Any]) -> dict[str, str]:
    text = proposition.lower()
    quantity_values = [str(row.get("value") or "") for row in quantities]
    return {
        "evidence_type": _evidence_type(text),
        "population": _scope_condition_at(0, claim),
        "exposure_or_intervention": _scope_condition_at(1, claim),
        "comparator": _comparator(text),
        "endpoint": _endpoint(text),
        "estimate": _first_quantity_of_type(quantities, {"percentage", "ratio", "rate", "dose", "unknown"}),
        "uncertainty_interval": _uncertainty_interval(quantity_values),
        "method": _method(text),
        "caveat": _caveat(text),
        "time_horizon": _first_quantity_of_type(quantities, {"duration", "date"}),
    }


def _quantity_row(value: str) -> dict[str, str]:
    cleaned = _compact(value, max_chars=160)
    return {
        "value": cleaned,
        "quantity_type": _quantity_type(cleaned),
        "local_interpretation": "",
    }


def _quantity_tuples_for_unit(unit: dict[str, Any]) -> list[dict[str, str]]:
    tuples = []
    for index, quantity in enumerate(_list(unit.get("quantities")), start=1):
        if not isinstance(quantity, dict):
            continue
        value = str(quantity.get("value") or "").strip()
        if not value:
            continue
        tuples.append(
            {
                "tuple_id": f"{unit['unit_id']}_q{index:03d}",
                "unit_id": str(unit.get("unit_id") or ""),
                "source_id": str(unit.get("source_id") or ""),
                "value": value,
                "quantity_type": str(quantity.get("quantity_type") or "unknown"),
                "endpoint": str(unit.get("endpoint") or ""),
                "comparator": str(unit.get("comparator") or ""),
                "population": str(unit.get("population") or ""),
                "source_span": str(unit.get("source_span") or ""),
                "source_quote": str(unit.get("source_quote") or ""),
            }
        )
    return tuples


def _quantity_type(value: str) -> str:
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


def _evidence_type(text: str) -> str:
    if any(term in text for term in ("randomized", "trial", "rct")):
        return "trial"
    if any(term in text for term in ("cohort", "observational", "associated", "association")):
        return "observational"
    if any(term in text for term in ("meta-analysis", "systematic review", "pooled")):
        return "synthesis"
    if any(term in text for term in ("guideline", "advice", "recommend")):
        return "guidance"
    if any(term in text for term in ("mechanism", "biomarker", "pathway")):
        return "mechanistic"
    return "unspecified"


def _endpoint(text: str) -> str:
    patterns = [
        r"\brisk of ([A-Za-z0-9 /-]+)",
        r"\brate of ([A-Za-z0-9 /-]+)",
        r"\bassociated with ([A-Za-z0-9 /-]+)",
        r"\breduced ([A-Za-z0-9 /-]+)",
        r"\bincreased ([A-Za-z0-9 /-]+)",
        r"\blower ([A-Za-z0-9 /-]+)",
        r"\bhigher ([A-Za-z0-9 /-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _compact(match.group(1), max_chars=120)
    return ""


def _comparator(text: str) -> str:
    match = re.search(r"\b(compared with|compared to|versus|vs\.?)\s+([^.;,]+)", text)
    return _compact(match.group(2), max_chars=120) if match else ""


def _method(text: str) -> str:
    if "meta-analysis" in text:
        return "meta-analysis"
    if "systematic review" in text:
        return "systematic review"
    if "randomized" in text or "trial" in text:
        return "trial"
    if "cohort" in text:
        return "cohort"
    return ""


def _caveat(text: str) -> str:
    markers = ("but", "however", "although", "except", "limited", "conditional")
    for marker in markers:
        match = re.search(rf"\b{marker}\b(.+)$", text)
        if match:
            return _compact(match.group(0), max_chars=180)
    return ""


def _scope_condition_at(index: int, claim: dict[str, Any]) -> str:
    conditions = _string_list(claim.get("scope_conditions"))
    return conditions[index] if len(conditions) > index else ""


def _first_quantity_of_type(quantities: list[dict[str, Any]], types: set[str]) -> str:
    for quantity in quantities:
        if str(quantity.get("quantity_type") or "") in types:
            return str(quantity.get("value") or "")
    return ""


def _uncertainty_interval(quantity_values: list[str]) -> str:
    for value in quantity_values:
        if re.search(r"\b(ci|confidence interval|credible interval)\b", value, flags=re.IGNORECASE):
            return value
    for value in quantity_values:
        if re.search(r"\d+(\.\d+)?\s*[-–]\s*\d+(\.\d+)?", value):
            return value
    return ""


def _lexically_supported(proposition: str, quote: str) -> bool:
    claim_terms = _content_terms(proposition)
    quote_terms = _content_terms(quote)
    if not claim_terms:
        return True
    overlap = claim_terms & quote_terms
    return len(overlap) >= min(3, max(2, len(claim_terms) // 3))


def _content_terms(text: str) -> set[str]:
    stop = {
        "the", "and", "or", "of", "to", "in", "a", "an", "for", "with", "by", "on", "as",
        "is", "are", "was", "were", "be", "been", "this", "that", "it", "from", "at",
    }
    return {
        term
        for term in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", text.lower())
        if term not in stop
    }


def _quote_matches_source(quote: str, source_text: str) -> bool:
    cleaned = _clean_quote(quote)
    return cleaned in source_text or _normalize_space(cleaned) in _normalize_space(source_text)


def _clean_quote(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().strip('"').strip("'")).strip()


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_compact(str(item)) for item in value if str(item).strip()]
    if value:
        return [_compact(str(value))]
    return []


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def _compact(value: str, max_chars: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "..."


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1
