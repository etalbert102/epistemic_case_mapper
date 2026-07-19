from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.pipeline.map.staged_semantic_claim_quantities import normalize_claim_quantity_rows, quantity_type

EVIDENCE_UNIT_SCHEMA_ID = "source_evidence_unit_v1"
EVIDENCE_UNIT_REPORT_SCHEMA_ID = "source_evidence_unit_quality_report_v1"
SOURCE_QUANTITY_TUPLES_SCHEMA_ID = "source_quantity_tuples_v1"
SOURCE_RESULT_QUANTITY_SCHEMA_ID = "source_result_quantity_tuple_v1"


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
            "natural_bottom_line": {"type": "string"},
            "must_preserve_terms": {"type": "array", "items": {"type": "string"}},
            "claim_context": {"type": "object"},
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
            "canonical_record_type": SOURCE_RESULT_QUANTITY_SCHEMA_ID,
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
    quantities = normalize_claim_quantity_rows(
        claim.get("claim_quantities") or claim.get("quantities"),
        supporting_quotes=quotes,
        claim_id=str(claim.get("claim_id") or ""),
        source_id=source_id,
        source_span=str(quotes[0].get("line_hint") or ""),
        source_quote=source_quote,
        claim_text=proposition,
    )
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
        "natural_bottom_line": _compact(str(claim.get("natural_bottom_line") or "")),
        "must_preserve_terms": _string_list(claim.get("must_preserve_terms")),
        "claim_context": _claim_context(claim),
        "source_quote": source_quote,
        "source_span": str(quotes[0].get("line_hint") or ""),
        "quote_lineage": quotes,
        "quantities": quantities,
        "assertion_bundles": _assertion_bundles_from_quantities(quantities),
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
    del proposition
    context = _claim_context(claim)
    return {
        "evidence_type": str(context.get("evidence_design") or "unspecified"),
        "population": str(context.get("population") or _scope_condition_at(0, claim)),
        "exposure_or_intervention": str(context.get("exposure_or_option") or _scope_condition_at(1, claim)),
        "comparator": str(context.get("comparator") or ""),
        "endpoint": str(context.get("outcome_or_endpoint") or ""),
        "estimate": str(context.get("stated_dose_or_threshold") or _first_quantity_of_type(quantities, {"percentage", "ratio", "rate", "dose", "unknown"})),
        "uncertainty_interval": str(context.get("uncertainty_interval") or ""),
        "method": str(context.get("evidence_design") or ""),
        "caveat": _compact("; ".join(_string_list(context.get("stated_limitations")) + _string_list(context.get("applicability_limits")))),
        "time_horizon": _first_quantity_of_type(quantities, {"duration", "date"}),
    }


def _claim_context(claim: dict[str, Any]) -> dict[str, str]:
    context = claim.get("claim_context") if isinstance(claim.get("claim_context"), dict) else {}
    fields = (
        "population",
        "exposure_or_option",
        "outcome_or_endpoint",
        "evidence_design",
        "comparator",
        "uncertainty_interval",
        "stated_dose_or_threshold",
        "stated_scope",
        "stated_limitations",
        "applicability_limits",
    )
    return {field: _compact(str(context.get(field) or "")) for field in fields if str(context.get(field) or "").strip()}


def _quantity_tuples_for_unit(unit: dict[str, Any]) -> list[dict[str, str]]:
    tuples = []
    claim_context = _claim_context(unit)
    for index, quantity in enumerate(_list(unit.get("quantities")), start=1):
        if not isinstance(quantity, dict):
            continue
        value = str(quantity.get("value") or "").strip()
        if not value:
            continue
        estimate_type = _estimate_type(quantity)
        interval_low, interval_high, interval_type = _interval_parts(value)
        tuple_id = f"{unit['unit_id']}_q{index:03d}"
        tuples.append(
            {
                "schema_id": SOURCE_RESULT_QUANTITY_SCHEMA_ID,
                "result_tuple_id": tuple_id,
                "tuple_id": tuple_id,
                "unit_id": str(unit.get("unit_id") or ""),
                "claim_id": str(unit.get("unit_id") or ""),
                "source_id": str(unit.get("source_id") or ""),
                "value": value,
                "quantity_type": str(quantity.get("quantity_type") or "unknown"),
                "quantity_role": str(quantity.get("quantity_role") or ""),
                "measures": str(quantity.get("measures") or ""),
                "local_interpretation": str(quantity.get("local_interpretation") or ""),
                "population": str(unit.get("population") or claim_context.get("population") or ""),
                "exposure_or_intervention": str(unit.get("exposure_or_intervention") or claim_context.get("exposure_or_option") or ""),
                "comparator": str(unit.get("comparator") or ""),
                "endpoint": str(unit.get("endpoint") or ""),
                "design": str(unit.get("method") or unit.get("evidence_type") or claim_context.get("evidence_design") or ""),
                "estimate_type": estimate_type,
                "estimate": value if estimate_type != "interval" else "",
                "interval_type": interval_type,
                "interval_low": interval_low,
                "interval_high": interval_high,
                "units": str(quantity.get("units") or ""),
                "time_horizon": str(unit.get("time_horizon") or ""),
                "source_span": str(unit.get("source_span") or ""),
                "source_quote": str(unit.get("source_quote") or ""),
                "binding_rule": "result_tuple_id_preserves_source_local_quantity_with_unit_context",
            }
        )
    return tuples


def build_quantity_tuple_binding_report(quantity_tuples: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [str(row.get("result_tuple_id") or row.get("tuple_id") or "").strip() for row in quantity_tuples if isinstance(row, dict)]
    missing_ids = [index for index, value in enumerate(ids) if not value]
    duplicate_ids = sorted({value for value in ids if value and ids.count(value) > 1})
    missing_source_identity = [
        str(row.get("result_tuple_id") or row.get("tuple_id") or f"row_{index}")
        for index, row in enumerate(quantity_tuples, start=1)
        if isinstance(row, dict) and not str(row.get("source_id") or "").strip()
    ]
    missing_quote_or_span = [
        str(row.get("result_tuple_id") or row.get("tuple_id") or f"row_{index}")
        for index, row in enumerate(quantity_tuples, start=1)
        if isinstance(row, dict) and (not str(row.get("source_quote") or "").strip() or not str(row.get("source_span") or "").strip())
    ]
    interval_without_estimate_context = [
        str(row.get("result_tuple_id") or row.get("tuple_id") or f"row_{index}")
        for index, row in enumerate(quantity_tuples, start=1)
        if isinstance(row, dict)
        and str(row.get("estimate_type") or "") == "interval"
        and not str(row.get("local_interpretation") or row.get("measures") or row.get("endpoint") or "").strip()
    ]
    issues = [
        *(["missing_result_tuple_id"] if missing_ids else []),
        *(["duplicate_result_tuple_id"] if duplicate_ids else []),
        *(["missing_source_identity"] if missing_source_identity else []),
        *(["missing_quote_or_span"] if missing_quote_or_span else []),
        *(["interval_without_result_context"] if interval_without_estimate_context else []),
    ]
    return {
        "schema_id": "quantity_tuple_binding_report_v1",
        "status": "ready" if not issues else "warning",
        "tuple_count": len(quantity_tuples),
        "result_tuple_id_count": len([value for value in ids if value]),
        "duplicate_result_tuple_ids": duplicate_ids,
        "missing_result_tuple_id_rows": missing_ids,
        "missing_source_identity_ids": missing_source_identity,
        "missing_quote_or_span_ids": missing_quote_or_span,
        "interval_without_result_context_ids": interval_without_estimate_context,
        "issues": issues,
    }


def build_quantity_tuple_mutation_eval(quantity_tuples: list[dict[str, Any]]) -> dict[str, Any]:
    baseline = build_quantity_tuple_binding_report(quantity_tuples)
    mutations: list[dict[str, Any]] = []
    if len(quantity_tuples) >= 2:
        swap_index = len(quantity_tuples) - 1
        swapped = [dict(row) for row in quantity_tuples]
        swapped[0]["source_quote"], swapped[swap_index]["source_quote"] = (
            swapped[swap_index].get("source_quote", ""),
            swapped[0].get("source_quote", ""),
        )
        mutations.append(_mutation_result("swapped_source_quote", swapped, original=quantity_tuples))
        swapped_population = [dict(row) for row in quantity_tuples]
        swapped_population[0]["population"], swapped_population[swap_index]["population"] = (
            swapped_population[swap_index].get("population", ""),
            swapped_population[0].get("population", ""),
        )
        mutations.append(_mutation_result("swapped_population", swapped_population, original=quantity_tuples))
    if quantity_tuples:
        missing_id = [dict(row) for row in quantity_tuples]
        missing_id[0]["result_tuple_id"] = ""
        missing_id[0]["tuple_id"] = ""
        mutations.append(_mutation_result("missing_tuple_id", missing_id, original=quantity_tuples))
    caught = [row for row in mutations if row.get("detected")]
    return {
        "schema_id": "quantity_tuple_mutation_eval_v1",
        "status": "ready" if len(caught) == len(mutations) else "warning",
        "baseline_status": baseline["status"],
        "mutation_count": len(mutations),
        "detected_mutation_count": len(caught),
        "mutations": mutations,
        "issues": [] if len(caught) == len(mutations) else ["undetected_quantity_tuple_mutation"],
    }


def _mutation_result(name: str, mutated: list[dict[str, Any]], *, original: list[dict[str, Any]]) -> dict[str, Any]:
    report = build_quantity_tuple_binding_report(mutated)
    changed_bindings = _changed_tuple_bindings(original, mutated)
    detected = bool(report["issues"] or changed_bindings)
    return {
        "mutation": name,
        "detected": detected,
        "binding_changes": changed_bindings,
        "report_issues": report["issues"],
    }


def _changed_tuple_bindings(original: list[dict[str, Any]], mutated: list[dict[str, Any]]) -> list[dict[str, str]]:
    baseline = {
        str(row.get("result_tuple_id") or row.get("tuple_id") or ""): _binding_fingerprint(row)
        for row in original
        if isinstance(row, dict) and str(row.get("result_tuple_id") or row.get("tuple_id") or "").strip()
    }
    changes = []
    for row in mutated:
        if not isinstance(row, dict):
            continue
        tuple_id = str(row.get("result_tuple_id") or row.get("tuple_id") or "").strip()
        if not tuple_id or tuple_id not in baseline:
            continue
        mutated_fingerprint = _binding_fingerprint(row)
        if mutated_fingerprint != baseline[tuple_id]:
            changes.append({"result_tuple_id": tuple_id, "warning": "result_tuple_binding_changed"})
    return changes


def _binding_fingerprint(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(row.get(field) or "").strip()
        for field in (
            "source_id",
            "claim_id",
            "population",
            "exposure_or_intervention",
            "comparator",
            "endpoint",
            "design",
            "estimate_type",
            "estimate",
            "interval_type",
            "interval_low",
            "interval_high",
            "units",
            "time_horizon",
            "source_quote",
            "source_span",
        )
    )


def _estimate_type(quantity: dict[str, Any]) -> str:
    role = str(quantity.get("quantity_role") or "").lower()
    value = str(quantity.get("value") or "").lower()
    if "interval" in role or re.search(r"\b(ci|confidence interval|credible interval)\b", value):
        return "interval"
    if "ratio" in value or re.search(r"\b(hr|rr|or)\b", value):
        return "ratio"
    if "%" in value or "percent" in value:
        return "percentage"
    if any(char.isdigit() for char in value):
        return "numeric"
    return "stated_quantity"


def _interval_parts(value: str) -> tuple[str, str, str]:
    text = str(value or "").replace("−", "-").replace("–", "-")
    if not re.search(r"\b(ci|confidence interval|credible interval)\b", text, flags=re.IGNORECASE):
        return "", "", ""
    bounds = re.findall(r"-?\d+(?:\.\d+)?", text)
    if len(bounds) < 2:
        return "", "", "confidence_interval"
    return bounds[-2], bounds[-1], "confidence_interval"


def _scope_condition_at(index: int, claim: dict[str, Any]) -> str:
    conditions = _string_list(claim.get("scope_conditions"))
    return conditions[index] if len(conditions) > index else ""


def _first_quantity_of_type(quantities: list[dict[str, Any]], types: set[str]) -> str:
    for quantity in quantities:
        if str(quantity.get("quantity_type") or "") in types:
            return str(quantity.get("value") or "")
    return ""


def _assertion_bundles_from_quantities(quantities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for quantity in quantities:
        if not isinstance(quantity, dict):
            continue
        for bundle in quantity.get("assertion_bundles") or []:
            if not isinstance(bundle, dict):
                continue
            bundle_id = str(bundle.get("evidence_bundle_id") or "")
            if bundle_id and bundle_id not in seen:
                seen.add(bundle_id)
                rows.append(bundle)
    return rows


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
