from __future__ import annotations

import hashlib
import re
from typing import Any


ASSERTION_BUNDLE_SCHEMA_ID = "source_assertion_bundle_v1"


def normalize_assertion_bundles(
    value: Any,
    *,
    claim_id: str = "",
    source_id: str = "",
    source_span: str = "",
    source_quote: str = "",
    claim_text: str = "",
    supporting_quotes: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows = []
    for item in _list(value):
        row = assertion_bundle_from_quantity(
            item,
            claim_id=claim_id,
            source_id=source_id,
            source_span=source_span,
            source_quote=source_quote,
            claim_text=claim_text,
            supporting_quotes=supporting_quotes or [],
        )
        if row:
            rows.append(row)
    return _dedupe_bundles(rows)


def assertion_bundle_from_quantity(
    quantity: Any,
    *,
    claim_id: str = "",
    source_id: str = "",
    source_span: str = "",
    source_quote: str = "",
    claim_text: str = "",
    supporting_quotes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if isinstance(quantity, dict):
        value = _compact(str(quantity.get("value") or quantity.get("quantity") or quantity.get("quantity_text") or quantity.get("text") or ""), 180)
        if not value:
            return {}
        quote = str(quantity.get("source_quote") or source_quote or _first_quote(supporting_quotes or [])).strip()
        span = str(quantity.get("line_hint") or quantity.get("source_span") or source_span or _first_line_hint(supporting_quotes or [])).strip()
        source_ids = _string_list(quantity.get("source_ids")) or _string_list(quantity.get("source_id")) or _string_list(source_id)
        endpoint = str(quantity.get("endpoint") or quantity.get("measures") or quantity.get("measured_construct") or "").strip()
        population = str(quantity.get("population") or quantity.get("subgroup") or "").strip()
        comparator = str(quantity.get("comparator") or quantity.get("comparison") or "").strip()
        statistic_type = str(quantity.get("statistic_type") or quantity.get("quantity_type") or _statistic_type(value)).strip()
        interval = str(quantity.get("interval") or quantity.get("confidence_interval") or _interval_from_text(value)).strip()
        estimate = str(quantity.get("estimate") or _estimate_from_text(value, statistic_type=statistic_type)).strip()
        direction = str(quantity.get("direction") or _direction_from_text(" ".join([claim_text, value, str(quantity.get("local_interpretation") or quantity.get("interpretation") or "")]))).strip()
        return _drop_empty(
            {
                "schema_id": ASSERTION_BUNDLE_SCHEMA_ID,
                "evidence_bundle_id": str(quantity.get("evidence_bundle_id") or quantity.get("bundle_id") or "").strip()
                or _bundle_id(
                    source_ids=source_ids,
                    claim_id=claim_id,
                    value=value,
                    endpoint=endpoint,
                    population=population,
                    comparator=comparator,
                    statistic_type=statistic_type,
                ),
                "claim_id": claim_id,
                "source_ids": source_ids,
                "source_span": span,
                "source_quote": _compact(quote, 420),
                "value": value,
                "estimate": estimate,
                "interval": interval,
                "statistic_type": statistic_type,
                "unit_or_denominator": str(quantity.get("unit_or_denominator") or _unit_or_denominator(value)).strip(),
                "endpoint": endpoint,
                "population": population,
                "exposure_or_comparator": str(quantity.get("exposure_or_comparator") or quantity.get("exposure") or comparator).strip(),
                "time_horizon": str(quantity.get("time_horizon") or "").strip(),
                "direction": direction,
                "uncertainty_interpretation": str(
                    quantity.get("uncertainty_interpretation")
                    or _uncertainty_interpretation(value, interval=interval, statistic_type=statistic_type)
                ).strip(),
                "allowed_inference": str(quantity.get("allowed_inference") or quantity.get("local_interpretation") or quantity.get("interpretation") or "").strip(),
                "forbidden_inference": str(quantity.get("forbidden_inference") or _forbidden_inference(statistic_type, " ".join([claim_text, quote]))).strip(),
                "quantity_role": str(quantity.get("quantity_role") or quantity.get("role") or "").strip(),
                "retention_hint": str(quantity.get("retention_hint") or "").strip(),
                "missing_fields": _missing_fields(
                    {
                        "source_ids": source_ids,
                        "source_span": span,
                        "source_quote": quote,
                        "statistic_type": statistic_type,
                        "endpoint": endpoint,
                    }
                ),
            }
        )
    value = _compact(str(quantity or ""), 180)
    if not value:
        return {}
    return assertion_bundle_from_quantity(
        {"value": value},
        claim_id=claim_id,
        source_id=source_id,
        source_span=source_span,
        source_quote=source_quote,
        claim_text=claim_text,
        supporting_quotes=supporting_quotes,
    )


def bundle_quantities_for_prompt(bundles: Any) -> list[dict[str, Any]]:
    rows = []
    for bundle in _list(bundles):
        if not isinstance(bundle, dict):
            continue
        rows.append(
            _drop_empty(
                {
                    "evidence_bundle_id": bundle.get("evidence_bundle_id"),
                    "value": bundle.get("value"),
                    "estimate": bundle.get("estimate"),
                    "interval": bundle.get("interval"),
                    "statistic_type": bundle.get("statistic_type"),
                    "endpoint": bundle.get("endpoint"),
                    "population": bundle.get("population"),
                    "exposure_or_comparator": bundle.get("exposure_or_comparator"),
                    "time_horizon": bundle.get("time_horizon"),
                    "direction": bundle.get("direction"),
                    "uncertainty_interpretation": bundle.get("uncertainty_interpretation"),
                    "allowed_inference": bundle.get("allowed_inference"),
                    "forbidden_inference": bundle.get("forbidden_inference"),
                    "source_ids": bundle.get("source_ids"),
                    "source_span": bundle.get("source_span"),
                }
            )
        )
    return rows


def semantic_realization_report(memo: str, bundles: Any) -> dict[str, Any]:
    issues = []
    text = str(memo or "")
    for bundle in _list(bundles):
        if not isinstance(bundle, dict):
            continue
        value = str(bundle.get("value") or "").strip()
        estimate = str(bundle.get("estimate") or "").strip()
        if not value or not _surface_present(value, text) and not (estimate and _surface_present(estimate, text)):
            continue
        nearby = _near_bundle_surface(text, value=value, estimate=estimate)
        statistic_type = str(bundle.get("statistic_type") or "").lower()
        if statistic_type in {"relative_risk", "risk_ratio"} and re.search(r"\bhazard ratio\b|\bHR\b", nearby, re.I):
            issues.append(_issue("statistic_swap_rr_as_hr", bundle))
        if statistic_type == "hazard_ratio" and re.search(r"\brelative risk\b|\bRR\b", nearby, re.I):
            issues.append(_issue("statistic_swap_hr_as_rr", bundle))
        interval = str(bundle.get("interval") or "").strip()
        if interval and not _surface_present(interval, _near_bundle_surface(text, value=value, estimate=estimate, window=360)):
            issues.append(_issue("detached_or_missing_interval", bundle))
        if _interval_crosses_null(interval) and re.search(r"\b(significant|clear increase|clearly increased|clearly reduced)\b", nearby, re.I):
            issues.append(_issue("null_crossing_interval_overstated", bundle))
        forbidden = str(bundle.get("forbidden_inference") or "").lower()
        if "causal" in forbidden and re.search(r"\b(causes|prevents|leads to|reduces)\b", nearby, re.I):
            issues.append(_issue("forbidden_causal_language", bundle))
    return {
        "schema_id": "semantic_realization_report_v1",
        "status": "pass" if not issues else "warning",
        "issue_count": len(issues),
        "issues": issues,
    }


def collect_assertion_bundles(value: Any) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    _collect_assertion_bundles(value, rows=rows, seen=seen)
    return rows


def bundle_reconciliation_report(
    *,
    memo: str,
    packet: dict[str, Any],
    selected_bundle_ids: list[str] | None = None,
) -> dict[str, Any]:
    bundles = collect_assertion_bundles(packet)
    realization = semantic_realization_report(memo, bundles)
    known_ids = {
        str(bundle.get("evidence_bundle_id") or "").strip()
        for bundle in bundles
        if isinstance(bundle, dict) and str(bundle.get("evidence_bundle_id") or "").strip()
    }
    selected = {str(bundle_id).strip() for bundle_id in (selected_bundle_ids or []) if str(bundle_id).strip()}
    return {
        "schema_id": "evidence_bundle_reconciliation_report_v1",
        "status": "pass" if realization.get("status") == "pass" and not (selected - known_ids) else "warning",
        "known_bundle_count": len(known_ids),
        "selected_bundle_count": len(selected),
        "unknown_selected_bundle_ids": sorted(selected - known_ids),
        "realization_report": realization,
        "bundle_index": _bundle_index_rows(bundles),
    }


def _issue(code: str, bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": code,
        "evidence_bundle_id": bundle.get("evidence_bundle_id"),
        "value": bundle.get("value"),
        "statistic_type": bundle.get("statistic_type"),
        "endpoint": bundle.get("endpoint"),
    }


def _collect_assertion_bundles(value: Any, *, rows: list[dict[str, Any]], seen: set[str]) -> None:
    if isinstance(value, dict):
        if value.get("schema_id") == ASSERTION_BUNDLE_SCHEMA_ID or value.get("evidence_bundle_id"):
            bundle_id = str(value.get("evidence_bundle_id") or "").strip()
            if bundle_id and bundle_id not in seen:
                seen.add(bundle_id)
                rows.append(value)
                return
        for child in value.values():
            _collect_assertion_bundles(child, rows=rows, seen=seen)
    elif isinstance(value, list):
        for child in value:
            _collect_assertion_bundles(child, rows=rows, seen=seen)


def _bundle_index_rows(bundles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _drop_empty(
            {
                "evidence_bundle_id": bundle.get("evidence_bundle_id"),
                "claim_id": bundle.get("claim_id"),
                "source_ids": bundle.get("source_ids"),
                "value": bundle.get("value"),
                "statistic_type": bundle.get("statistic_type"),
                "endpoint": bundle.get("endpoint"),
                "population": bundle.get("population"),
                "interval": bundle.get("interval"),
                "allowed_inference": bundle.get("allowed_inference"),
                "forbidden_inference": bundle.get("forbidden_inference"),
            }
        )
        for bundle in bundles
        if isinstance(bundle, dict)
    ]


def _bundle_id(
    *,
    source_ids: list[str],
    claim_id: str,
    value: str,
    endpoint: str,
    population: str,
    comparator: str,
    statistic_type: str,
) -> str:
    basis = "|".join(
        [
            ",".join(source_ids),
            claim_id,
            _norm(value),
            _norm(endpoint),
            _norm(population),
            _norm(comparator),
            _norm(statistic_type),
        ]
    )
    return "bundle_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def _dedupe_bundles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for row in rows:
        key = (
            _norm(row.get("value")),
            _norm(row.get("endpoint")),
            _norm(row.get("population")),
            _norm(row.get("exposure_or_comparator")),
            _norm(row.get("statistic_type")),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def _statistic_type(value: str) -> str:
    text = value.lower()
    if re.search(r"\b(hr|hazard ratio)\b", text):
        return "hazard_ratio"
    if re.search(r"\b(rr|relative risk|risk ratio)\b", text):
        return "relative_risk"
    if re.search(r"\b(or|odds ratio)\b", text):
        return "odds_ratio"
    if re.search(r"\b(md|mean difference)\b", text):
        return "mean_difference"
    if re.search(r"\bci|confidence interval\b", text):
        return "uncertainty_interval"
    if "%" in text or "percent" in text:
        return "percentage"
    if re.search(r"\d", text):
        return "numeric_value"
    return "not_numeric"


def _estimate_from_text(value: str, *, statistic_type: str) -> str:
    if statistic_type == "uncertainty_interval":
        return ""
    match = re.search(r"[-+]?\d+(?:\.\d+)?", value)
    return match.group(0) if match else ""


def _interval_from_text(value: str) -> str:
    match = re.search(r"(?:95\s*%\s*)?(?:CI|confidence interval)?\s*[\[(]?\s*[-+]?\d+(?:\.\d+)?\s*(?:-|–|—|to)\s*[-+]?\d+(?:\.\d+)?\s*[\])]?", value, flags=re.I)
    if not match or not re.search(r"(?:-|–|—|to)", match.group(0)):
        return ""
    return re.sub(r"\s+", " ", match.group(0)).strip().strip("()[]")


def _unit_or_denominator(value: str) -> str:
    match = re.search(r"\b(?:per|/)\s*([a-z][a-z\s]{1,40})", value, flags=re.I)
    return match.group(0).strip() if match else ""


def _direction_from_text(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("increase", "higher", "elevat", "harm", "risk")):
        return "increase_or_higher"
    if any(token in lowered for token in ("decrease", "lower", "reduce", "protect")):
        return "decrease_or_lower"
    if any(token in lowered for token in ("no association", "not associated", "neutral", "null")):
        return "near_null_or_no_clear_association"
    return ""


def _uncertainty_interpretation(value: str, *, interval: str, statistic_type: str) -> str:
    if interval and _interval_crosses_null(interval):
        return "interval crosses the null; do not describe as clearly significant"
    if statistic_type == "uncertainty_interval":
        return "uncertainty interval; pair with its estimate before using"
    return ""


def _forbidden_inference(statistic_type: str, text: str) -> str:
    lowered = text.lower()
    pieces = []
    if any(token in lowered for token in ("cohort", "observational", "associated", "association")):
        pieces.append("do not present observational association as causal")
    if statistic_type == "uncertainty_interval":
        pieces.append("do not use interval without paired estimate")
    return "; ".join(pieces)


def _interval_crosses_null(interval: str) -> bool:
    numbers = [float(item) for item in re.findall(r"[-+]?\d+(?:\.\d+)?", str(interval or ""))]
    if len(numbers) < 2:
        return False
    lo, hi = min(numbers[-2:]), max(numbers[-2:])
    return lo <= 1.0 <= hi


def _near_value(text: str, value: str, *, window: int = 220) -> str:
    if not value:
        return ""
    index = str(text or "").lower().find(str(value).lower())
    if index < 0:
        numbers = re.findall(r"\d+(?:\.\d+)?", value)
        index = min([str(text or "").find(number) for number in numbers if str(text or "").find(number) >= 0] or [-1])
    if index < 0:
        return ""
    return str(text or "")[max(0, index - window) : index + len(value) + window]


def _near_bundle_surface(text: str, *, value: str, estimate: str, window: int = 220) -> str:
    near = _near_value(text, value, window=window)
    if near:
        return near
    return _near_value(text, estimate, window=window)


def _surface_present(value: str, text: str) -> bool:
    value = str(value or "").strip()
    if not value:
        return False
    if value.lower() in str(text or "").lower():
        return True
    numbers = re.findall(r"\d+(?:\.\d+)?", value)
    return bool(numbers) and all(number in str(text or "") for number in numbers)


def _missing_fields(row: dict[str, Any]) -> list[str]:
    return [key for key, value in row.items() if value in ("", None, [])]


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


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _compact(value: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9.%/-]+", " ", str(value or "").lower())).strip()


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}
